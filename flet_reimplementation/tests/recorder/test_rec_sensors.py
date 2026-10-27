"""Sensor command lines, supervision (rollover, restart, missing binary), real recordings through ffmpeg,
purge, naming, and the 04 §14.1 "new -> old" acceptance test (stock library decrypts what we write)."""
import os
import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from wacryptolib.cryptainer import ReadonlyCryptainerStorage, load_cryptainer_from_filesystem, check_cryptainer_sanity

from rec_helpers import *  # noqa: F401,F403
from rec_helpers import FIXTURES, GUARDIAN_A, GUARDIAN_B, needs_fixtures, passphrases, make_settings
from waflet_recorder import sensors as sensors_module
from waflet_recorder.cryptainers import (
    RecorderCryptainerStorage, build_cryptainer_filename_base, purge_orphan_payloads, purge_now, list_cryptainers,
    open_management_storage, get_free_space_info,
)
from waflet_recorder.cryptoconf import build_cryptoconf
from waflet_recorder.sensors import (
    RtspCameraSensor, RaspberryLibcameraSensor, RaspberryAlsaMicrophoneSensor, StreamSensor, SensorState, next_backoff_s,
)
from waflet_recorder.toolchain import build_recording_toolchain, NoSensorStartedError, StorageFullError

needs_ffmpeg = pytest.mark.skipif(not Path("/usr/bin/ffmpeg").exists(), reason="ffmpeg missing")


# ------------------------------------------------------------------ command lines (04 §12)

def test_rtsp_command_line_default():
    sensor = RtspCameraSensor(None, 60, "rtsp://cam/s", preview_image_path=Path("/c/video_preview_image.jpg"), ffmpeg_version=(5, 0))
    assert sensor.build_command_line() == [
        "ffmpeg", "-y", "-hide_banner", "-timeout", "5000000", "-rtsp_flags", "prefer_tcp", "-fflags", "+igndts",
        "-i", "rtsp://cam/s", "-vcodec", "copy", "-an", "-map", "0", "-f", "ismv", "-movflags", "empty_moov+delay_moov",
        "-probesize", "128", "-analyzeduration", "500", "-loglevel", "info", "-f", "mp4", "pipe:1",
        "-frames:v", "1", "-filter:v", "scale=140:-1,hue=s=0", "/c/video_preview_image.jpg"]
    assert sensor.record_extension == ".mp4"


def test_rtsp_command_line_variants():
    old = RtspCameraSensor(None, 60, "rtsp://c", ffmpeg_version=(4, 4))
    assert "-stimeout" in old.build_command_line() and "-timeout" not in old.build_command_line()
    custom = RtspCameraSensor(None, 60, "rtsp://c", ["-c:v", "libx264"], " mkv ", ffmpeg_version=(10, 1))
    command = custom.build_command_line()
    assert "-timeout" in command and command[command.index("-i") + 2:command.index("-loglevel")] == ["-c:v", "libx264"]
    assert command[-3:] == ["-f", "mkv", "pipe:1"] and custom.record_extension == ".mkv"  # No preview output


def test_pi_command_lines():
    video = RaspberryLibcameraSensor(None, 60)
    assert video.build_command_line() == ["libcamera-vid", "--timeout", "0", "--nopreview", "--output", "-",
                                          "--flush", "--framerate", "30"] and video.record_extension == ".h264"
    muxed = RaspberryLibcameraSensor(None, 60, "alsa_input.usb", ["--width", "640"], [])
    assert muxed.build_command_line() == [
        "libcamera-vid", "--timeout", "0", "--nopreview", "--output", "pipe:", "--width", "640", "--codec", "libav",
        "--libav-format", "mpegts", "-q", "95", "--libav-audio", "--audio-codec", "aac", "--audio-bitrate", "16000",
        "--audio-device", "alsa_input.usb", "--flush", "--framerate", "30"] and muxed.record_extension == ".mpegts"
    assert RaspberryAlsaMicrophoneSensor(None, 60).build_command_line() == [
        "arecord", "-t", "wav", "-c", "1", "-r", "22050", "-f", "S16_LE"]  # OI-27 decided: 22050
    compressed = RaspberryAlsaMicrophoneSensor(None, 60, True)
    assert compressed.build_command_line() == ["ffmpeg", "-f", "alsa", "-loglevel", "error", "-i", "default", "-ac", "1",
                                               "-acodec", "libmp3lame", "-ab", "128k", "-f", "mp3", "pipe:1"]
    assert compressed.record_extension == ".mp3"
    custom = RaspberryAlsaMicrophoneSensor(None, 60, False, ["-D", "hw:1"], "raw")
    assert custom.build_command_line() == ["arecord", "-t", "raw", "-D", "hw:1"] and custom.record_extension == ".raw"


def test_naming_and_backoff():
    when = datetime(2026, 3, 15, 14, 20, 0, tzinfo=timezone(timedelta(hours=2)))
    assert build_cryptainer_filename_base("rtsp_camera", when, ".mp4") == "20260315_122000_rtsp_camera_cryptainer.mp4"
    delays, current = [], 0
    for _ in range(9):
        current = next_backoff_s(current)
        delays.append(current)
    assert delays == [1, 2, 4, 8, 16, 32, 60, 60, 60]


# ------------------------------------------------------------------ fake binaries on PATH, driving the REAL ffmpeg

SHIMS = {
    # "ffmpeg": RTSP input is replaced by a local lavfi source; real ffmpeg encodes it to fragmented mp4 on stdout
    "ffmpeg": '''#!/bin/sh
if [ "$1" = "-version" ]; then exec /usr/bin/ffmpeg -version; fi
for last; do :; done
DURATION=${WA_SHIM_DURATION:-3600}
case "$last" in
  *.jpg) /usr/bin/ffmpeg -y -loglevel error -f lavfi -i testsrc=size=160x120:rate=5 -frames:v 1 -vf scale=140:-1,hue=s=0 "$last" ;;
esac
exec /usr/bin/ffmpeg -loglevel error -re -f lavfi -i testsrc=size=160x120:rate=10:duration=$DURATION -c:v libx264 \\
  -preset ultrafast -g 5 -f mp4 -movflags empty_moov+frag_keyframe pipe:1
''',
    "arecord": "#!/bin/sh\nexec yes audiodata\n",
    "libcamera-vid": "#!/bin/sh\nexec yes videodata\n",
    "libcamera-jpeg": '#!/bin/sh\nwhile [ "$1" != "--output" ]; do shift; done\necho jpeg > "$2"\n',
}


@pytest.fixture
def shim_path(tmp_path, monkeypatch):
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    for name, body in SHIMS.items():
        path = shim_dir / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", "%s:%s" % (shim_dir, os.environ["PATH"]))
    return shim_dir


@pytest.fixture
def recording_setup(pool_roots, pool, tmp_path):
    out = tmp_path / "out"
    out.mkdir()

    def make(is_pi=False, threshold=1, guardians=(GUARDIAN_A, GUARDIAN_B), **overrides):
        if threshold == 2:  # Guardian B is public-only in the fixture pool: give the test its private keys
            from waflet_recorder.guardians import import_from_authdevice
            import_from_authdevice(pool, FIXTURES / "authdevices" / "usb_B" / "authenticator.keystore", True)
        values = {"storage.cryptainer_dir": out, "keyguardian.keyguardian_threshold": threshold,
                  "keyguardian.selected_keyguardians": ",".join(str(g) for g in guardians),
                  "sensor.ip_camera_url": "rtsp://127.0.0.1/shim", "sensor.recording_duration_mn": 0.03}
        values.update(overrides)
        return make_settings(pool_roots, is_pi=is_pi, **values)

    return make, out, pool, pool_roots


def stock_decrypt(out, pool, name):
    """The unmodified library, no code of ours (04 §14.1 item 2)."""
    storage = ReadonlyCryptainerStorage(out, keystore_pool=pool)
    storage.check_cryptainer_sanity(name)
    mapper = {None: [passphrases()["usb_A"], passphrases()["usb_B"]]}
    data, report = storage.decrypt_cryptainer_from_storage(name, passphrase_mapper=mapper)
    assert data is not None, report.format_entries()
    return data


@needs_fixtures
@needs_ffmpeg
@pytest.mark.parametrize("threshold", [1, 2])
def test_real_recording_rollover_and_stock_decryption(recording_setup, shim_path, threshold):
    make, out, pool, roots = recording_setup
    settings = make(threshold=threshold)
    notifications = []
    toolchain = build_recording_toolchain(settings, pool, roots, activity_callback=lambda **kw: notifications.append(kw))
    health = toolchain.start()
    assert [h["state"] for h in health] == ["running"]
    time.sleep(6)
    assert toolchain.health()[0]["last_data_utc"] is not None
    toolchain.stop()
    assert toolchain.health()[0]["state"] == SensorState.STOPPED
    storage = open_management_storage(out, pool)
    names = [e["name"] for e in list_cryptainers(storage)]
    assert len(names) >= 2, names  # Rollover every 1.8 s
    assert not list(out.glob("*.crypt~")) and not list(out.glob("*.tmp"))
    for name in names:
        assert "_rtsp_camera_cryptainer.mp4.crypt" in name
        data = stock_decrypt(out, pool, name)
        assert b"ftyp" in data[:32] and len(data) > 500
    assert roots.preview_image.exists() and roots.preview_image.stat().st_size > 0


@needs_fixtures
def test_pi_sensors_cryptainers_decryptable_by_stock_library(recording_setup, shim_path):
    make, out, pool, roots = recording_setup
    settings = make(is_pi=True, threshold=2, **{"sensor.enable_ip_camera": 0, "sensor.enable_local_camera_microphone_muxing": 0})
    toolchain = build_recording_toolchain(settings, pool, roots, list_microphones=lambda: ["alsa_input.x"],
                                          legacy_camera_check=lambda: False)
    assert [s.sensor_name for s in toolchain.sensors] == ["rpi_libcamera", "rpi_microphone"]
    toolchain.start()
    time.sleep(1.5)
    toolchain.stop()
    names = sorted(p.name for p in out.glob("*.crypt"))
    assert any("_rpi_libcamera_cryptainer.h264.crypt" in n for n in names) and any("_rpi_microphone_cryptainer.wav.crypt" in n for n in names)
    for name in names:
        data = stock_decrypt(out, pool, name)
        assert data.startswith((b"audiodata\naudiodata", b"videodata\nvideodata")) and len(data) > 100000
    assert roots.preview_image.read_bytes() == b"jpeg\n"


@needs_fixtures
@needs_ffmpeg
def test_dead_capture_is_restarted_with_backoff(recording_setup, shim_path, monkeypatch):
    make, out, pool, roots = recording_setup
    monkeypatch.setenv("WA_SHIM_DURATION", "1")  # ffmpeg exits by itself after 1 s (camera lost): OI-17
    settings = make(**{"sensor.recording_duration_mn": 10})
    toolchain = build_recording_toolchain(settings, pool, roots)
    toolchain.start()
    time.sleep(5.5)
    health = toolchain.health()[0]
    assert health["state"] in (SensorState.RUNNING, SensorState.RESTARTING)
    toolchain.stop()
    names = sorted(p.name for p in out.glob("*.crypt"))
    assert len(names) >= 2, names  # One new cryptainer per restart
    for name in names:
        assert stock_decrypt(out, pool, name)


@needs_fixtures
def test_missing_binary_leaves_no_files_and_refuses_start(recording_setup, monkeypatch):
    make, out, pool, roots = recording_setup
    monkeypatch.setenv("PATH", "/nonexistent")
    settings = make(**{"sensor.ip_camera_url": "rtsp://x/y"})
    toolchain = build_recording_toolchain(settings, pool, roots)
    toolchain.sensors[0]._ffmpeg_version = (6, 0)  # Avoid probing
    with pytest.raises(NoSensorStartedError):  # OI-16
        toolchain.start()
    assert list(out.iterdir()) == []  # OI-19: no empty cryptainer, no payload, no .crypt~


@needs_fixtures
def test_name_collision_never_overwrites(recording_setup):
    make, out, pool, roots = recording_setup
    storage = RecorderCryptainerStorage(out, pool, build_cryptoconf(1, [GUARDIAN_A], pool))

    class Dummy(StreamSensor):
        sensor_name = "dummy"
        record_extension = ".bin"

    sensor = Dummy(storage, 10)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    taken = out / (build_cryptainer_filename_base("dummy", now, ".bin") + ".crypt")
    taken.write_text("precious")
    base = sensor._free_start_time()
    assert base != build_cryptainer_filename_base("dummy", now, ".bin") and taken.read_text() == "precious"


@needs_fixtures
def test_unfinished_cryptainer_during_record_then_finalized_atomically(recording_setup):
    make, out, pool, roots = recording_setup
    storage = RecorderCryptainerStorage(out, pool, build_cryptoconf(1, [GUARDIAN_A, GUARDIAN_B], pool))
    from waflet_recorder.cryptainers import RecorderEncryptionPipeline
    stream = storage.create_cryptainer_encryption_stream(
        "20261026_100000_x_cryptainer.bin", cryptainer_metadata=None, dump_initial_cryptainer=True,
        cryptainer_encryption_stream_class=RecorderEncryptionPipeline)
    assert (out / "20261026_100000_x_cryptainer.bin.crypt~").exists() and not (out / "20261026_100000_x_cryptainer.bin.crypt").exists()
    stream.encrypt_chunk(b"hello " * 1000)
    stream.finalize()
    assert sorted(p.name for p in out.iterdir()) == ["20261026_100000_x_cryptainer.bin.crypt", "20261026_100000_x_cryptainer.bin.crypt.payload"]
    check_cryptainer_sanity(load_cryptainer_from_filesystem(out / "20261026_100000_x_cryptainer.bin.crypt"))
    assert stock_decrypt(out, pool, "20261026_100000_x_cryptainer.bin.crypt") == b"hello " * 1000
    empty = storage.create_cryptainer_encryption_stream(
        "20261026_100001_x_cryptainer.bin", cryptainer_metadata=None, cryptainer_encryption_stream_class=RecorderEncryptionPipeline)
    empty.discard()
    assert len(list(out.iterdir())) == 2


# ------------------------------------------------------------------ purge (03 §8.1)

@needs_fixtures
def test_purge_by_age_finished_unfinished_and_orphans(recording_setup):
    make, out, pool, roots = recording_setup
    now = datetime.now(timezone.utc)

    def touch(ts, ext):
        (out / ("%s_rtsp_camera_cryptainer.mp4%s" % (ts.strftime("%Y%m%d_%H%M%S"), ext))).write_bytes(b"{}")

    old, recent = now - timedelta(days=31), now - timedelta(days=29)
    touch(old, ".crypt"); touch(old, ".crypt.payload")
    touch(old - timedelta(minutes=1), ".crypt~"); touch(old - timedelta(minutes=1), ".crypt.payload")
    touch(recent, ".crypt"); touch(recent, ".crypt.payload")
    orphan = out / "20260101_000000_rtsp_camera_cryptainer.mp4.crypt.payload"
    orphan.write_bytes(b"x")
    os.utime(orphan, (time.time() - 7200,) * 2)
    fresh_orphan = out / "20260101_000001_rtsp_camera_cryptainer.mp4.crypt.payload"
    fresh_orphan.write_bytes(b"x")
    assert purge_now(out, pool, 30) >= 2
    left = sorted(p.name for p in out.iterdir())
    assert left == sorted([recent.strftime("%Y%m%d_%H%M%S") + "_rtsp_camera_cryptainer.mp4" + s for s in (".crypt", ".crypt.payload")]
                          + [fresh_orphan.name])  # Old finished + unfinished + 2-hour orphan gone, fresh orphan kept
    assert purge_orphan_payloads(out, min_age_s=0) == 1


@needs_fixtures
def test_purge_refuses_with_wrong_clock(recording_setup, monkeypatch):
    make, out, pool, roots = recording_setup
    (out / "20200101_000000_x_cryptainer.bin.crypt").write_bytes(b"{}")
    from waflet_recorder import cryptainers

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2001, 1, 1, tzinfo=tz)
    monkeypatch.setattr(cryptainers, "datetime", FakeDatetime)
    assert purge_now(out, pool, 30) == 0 and len(list(out.iterdir())) == 1  # OI-47


@needs_fixtures
def test_storage_full_refuses_build(recording_setup, monkeypatch):
    make, out, pool, roots = recording_setup
    from waflet_recorder import toolchain
    monkeypatch.setattr(toolchain, "get_free_space_info", lambda d: {"free_bytes": 1, "full": True})
    with pytest.raises(StorageFullError):
        build_recording_toolchain(make(), pool, roots)
    assert get_free_space_info(out)["free_bytes"] > 0
