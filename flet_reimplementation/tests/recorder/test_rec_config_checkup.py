import configparser

import pytest

from rec_helpers import *  # noqa: F401,F403
from rec_helpers import make_settings, GUARDIAN_A, GUARDIAN_B, needs_fixtures
from waflet_components.config import AppConfig
from waflet_components.i18n import tr
from waflet_components.storage import compute_storage_roots, is_raspberry_pi
from waflet_recorder import checkup, probes
from waflet_recorder.settings import CONFIG_DEFAULTS_PATH, is_valid_gateway_url


def test_defaults_have_the_28_keys_of_the_spec():
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(CONFIG_DEFAULTS_PATH, encoding="utf8")
    assert sum(len(parser[s]) for s in parser.sections()) == 28
    assert parser.sections() == ["sensor", "keyguardian", "storage", "peripheral", "network"]
    assert parser["sensor"]["recording_duration_mn"] == "15" and parser["storage"]["max_cryptainer_age_day"] == "30"
    assert parser["network"]["wagateway_url"] == "https://api.witnessangel.com/gateway/jsonrpc/"


def test_settings_typed_getters_and_paths(roots):
    settings = make_settings(roots, **{"sensor.ffmpeg_rtsp_parameters": '-vcodec copy -x "a b%c"',
                                       "sensor.recording_duration_mn": "0.5", "sensor.ffmpeg_rtsp_output_format": " mkv "})
    assert settings.enable_ip_camera is True and settings.recording_duration_mn == 0.5
    assert settings.ffmpeg_rtsp_parameters == ["-vcodec", "copy", "-x", "a b%c"]  # '%' is fine: no interpolation (OI-32)
    assert settings.ffmpeg_rtsp_output_format == "mkv"
    assert settings.cryptainer_dir == roots.default_cryptainers_dir  # Empty setting
    assert roots.recording_marker.name == "recording_in_progress"
    assert roots.osc_socket_path(1).name == ".witnessangel1.sock"
    assert roots.keystore_pool_dir.name == "keystore_pool"


def test_config_save_is_atomic_and_reloadable(roots):
    config = AppConfig(roots.internal_app_root / "warecorder_config.ini", CONFIG_DEFAULTS_PATH)
    config.set("keyguardian", "keyguardian_threshold", 2)
    assert not list(roots.internal_app_root.glob("*.tmp"))
    other = AppConfig(config.path, CONFIG_DEFAULTS_PATH)
    assert other.getint("keyguardian", "keyguardian_threshold") == 2
    config.set("keyguardian", "keyguardian_threshold", 3)
    other.reload()
    assert other.getint("keyguardian", "keyguardian_threshold") == 3


def test_selected_keyguardians_skips_malformed(roots):
    settings = make_settings(roots, **{"keyguardian.selected_keyguardians": " %s, nope ,,%s" % (GUARDIAN_A, GUARDIAN_B)})
    assert settings.selected_keyguardians == [str(GUARDIAN_A), str(GUARDIAN_B)]
    settings.set_selected_keyguardians([GUARDIAN_B])
    assert settings.config.get("keyguardian", "selected_keyguardians") == str(GUARDIAN_B)


def test_gateway_url_validation():
    assert is_valid_gateway_url("https://x.org/rpc/") and not is_valid_gateway_url("x.org") and not is_valid_gateway_url("")


def test_raspberry_pi_detection(tmp_path):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("Hardware\t: BCM2835\n")
    assert is_raspberry_pi(cpuinfo, tmp_path / "none")
    cpuinfo.write_text("Hardware\t: Something\n")
    assert not is_raspberry_pi(cpuinfo, tmp_path / "none")
    model = tmp_path / "model"
    model.write_bytes(b"Raspberry Pi 5 Model B\x00")  # OI-43
    assert is_raspberry_pi(cpuinfo, model)


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    def setter(value):
        monkeypatch.setattr(probes, "get_ffmpeg_version", lambda use_cache=True: value)
    setter(((6, 1), None))
    return setter


def run(settings, pool, **kw):
    return checkup.run_checkup(settings, pool, list_microphones=lambda: ["alsa_input.x"], **kw)


@needs_fixtures
def test_checkup_all_ok(pool_roots, pool, fake_ffmpeg):
    settings = make_settings(pool_roots, **{"keyguardian.selected_keyguardians": "%s,%s" % (GUARDIAN_A, GUARDIAN_B),
                                            "keyguardian.keyguardian_threshold": 2,
                                            "sensor.ip_camera_url": "rtsp://cam/stream"})
    result = run(settings, pool)
    assert result.ok and len(result.lines) == 6
    assert result.messages == [
        "[OK] Sensors: IP camera rtsp://cam/stream",
        "[OK] 2 key guardian(s) selected, 2 of which necessary for decryption",
        "[OK] Container storage: %s" % pool_roots.default_cryptainers_dir,
        "[OK] Each container stores 15 mn(s) of video",
        "[OK] Containers are kept for 30 day(s)",
        "[OK] Ffmpeg module is installed with a compatible 6.1 version",
    ]


@needs_fixtures
def test_checkup_ko_lines(pool_roots, pool, fake_ffmpeg, tmp_path):
    settings = make_settings(pool_roots, **{
        "sensor.ip_camera_url": "not a url", "keyguardian.keyguardian_threshold": 3,
        "keyguardian.selected_keyguardians": "%s,%s,%s" % (GUARDIAN_A, GUARDIAN_B, "104eba5c-0000-0000-0000-000000000000"),
        "storage.cryptainer_dir": tmp_path / "missing", "sensor.recording_duration_mn": 0, "storage.max_cryptainer_age_day": -1})
    fake_ffmpeg(((4, 2), None))
    result = run(settings, pool)
    assert not result.ok
    assert result.lines[0].message == 'Wrong IP camera url: "not a url"'
    assert result.lines[1].ok is False and "2 key guardian(s) selected, 3 of which" in result.lines[1].message
    assert "1 selected key guardian(s) not found were ignored" in result.lines[1].message
    assert result.lines[2].message == 'Invalid container storage: "%s"' % (tmp_path / "missing")
    assert [line.ok for line in result.lines[3:5]] == [False, False]
    assert result.lines[5].message == "Ffmpeg module is installed but this 4.2 version is below required 4.3"


def test_checkup_sensor_rules(roots, pool, fake_ffmpeg):
    none = make_settings(roots, **{"sensor.enable_ip_camera": 0})
    assert checkup.check_sensors(none).message == "No sensors are enabled" and not checkup.check_sensors(none).ok
    pi = make_settings(roots, is_pi=True, **{"sensor.enable_ip_camera": 0})
    assert checkup.check_sensors(pi, lambda: []).message == "Local microphone not found"
    assert checkup.check_sensors(pi, lambda: ["in"]).message == "Sensors: local camera, local microphone"
    pc = make_settings(roots, **{"sensor.enable_local_camera": 1})  # Ignored off a Pi
    assert checkup.check_sensors(pc).message.startswith("Sensors: IP camera ")

    def boom():
        raise RuntimeError("pulse down")
    assert checkup.check_sensors(pi, boom).message == "Local microphone not found"  # OI-39: no crash


def test_checkup_bad_number_is_a_ko_line_not_an_exception(roots, pool, fake_ffmpeg):
    settings = make_settings(roots, **{"keyguardian.keyguardian_threshold": "2.0"})
    result = run(settings, pool)
    assert result.lines[1].message == 'Invalid value for setting "keyguardian_threshold"' and not result.ok


def test_checkup_ffmpeg_rules(roots, fake_ffmpeg):
    settings = make_settings(roots)
    fake_ffmpeg((None, "missing"))
    assert checkup.check_ffmpeg(settings) == checkup.CheckupLine(False, "Ffmpeg module not found, please ensure it is in your PATH")
    fake_ffmpeg((None, "unknown"))
    assert checkup.check_ffmpeg(settings).ok  # OI-38
    fake_ffmpeg((None, "missing"))
    unused = make_settings(roots, **{"sensor.enable_ip_camera": 0})
    assert checkup.check_ffmpeg(unused).ok  # OI-39: no sensor needs it


def test_ffmpeg_version_parsing():
    assert probes.parse_ffmpeg_version("ffmpeg version 4.3.2-0+deb11 Copyright") == (4, 3)
    assert probes.parse_ffmpeg_version("ffmpeg version n5.1.2") == (5, 1)
    assert probes.parse_ffmpeg_version("ffmpeg version 10.1 Copyright") == (10, 1)  # OI-38: not 0.1
    assert probes.parse_ffmpeg_version("ffmpeg version N-1234-gabc") is None


def test_checkup_french(roots, pool, fake_ffmpeg):
    tr.lang = "fr"
    settings = make_settings(roots, **{"sensor.ip_camera_url": "rtsp://c"})
    result = run(settings, pool)
    assert result.messages[0] == "[OK] Capteurs : Caméra IP rtsp://c"
    assert result.messages[1].startswith("[KO] 0 gardien(s) de clés configuré(s), dont 1 nécessaire(s)")
    assert result.messages[4] == "[OK] Les conteneurs sont gardés 30 jour(s)"
