"""Recording sensors (03 §6, 04 §12): one supervised capture subprocess per sensor, one cryptainer per record.

Replaces the cryptolib's `PeriodicSubprocessStreamRecorder` to fix OI-16 (start result), OI-17 (a dead capture
process is restarted with exponential backoff, one new cryptainer each time), OI-18 (a failing rollover is retried
and reported), OI-19 (no empty cryptainer when the binary is missing or nothing was captured) and OI-20 (a record
never overwrites an existing cryptainer name). Data flow is unchanged: subprocess stdout -> encryption pipeline.
"""
import logging
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .cryptainers import RecorderEncryptionPipeline, build_cryptainer_filename_base
from .probes import get_ffmpeg_version

logger = logging.getLogger(__name__)

PREVIEW_IMAGE_WIDTH_PX = 140
PREVIEW_IMAGE_HEIGHT_PX = 104
RTSP_SOCKET_TIMEOUT_US = "5000000"
BACKOFF_START_S, BACKOFF_MAX_S = 1, 60
HEALTHY_RUN_S = 60  # A capture alive for that long resets the backoff
TERMINATE_TIMEOUT_S, KILL_TIMEOUT_S, READER_JOIN_TIMEOUT_S = 10, 5, 30


class SensorState:
    RUNNING = "running"
    RESTARTING = "restarting"
    FAILED = "failed"
    STOPPED = "stopped"


class ActivityNotificationType:
    RECORDING_PROGRESS = "RECORDING_PROGRESS"  # With "notification_color"
    IMAGE_PREVIEW = "IMAGE_PREVIEW"  # With "notification_image" (picamera/LCD only)


def next_backoff_s(current):
    return min(max(current * 2, BACKOFF_START_S), BACKOFF_MAX_S) if current else BACKOFF_START_S


class StreamSensor:
    """Subclass: set `sensor_name`, `activity_notification_color`, implement `record_extension` and
    `build_command_line()`. `storage` must be a `RecorderCryptainerStorage`."""

    sensor_name = None
    activity_notification_color = None
    chunk_size = 2 * 1024 ** 2

    def __init__(self, storage, interval_s, activity_callback=None, sleep=None):
        assert self.sensor_name
        self._storage = storage
        self._interval_s = interval_s
        self._activity_callback = activity_callback
        self._stop_event = threading.Event()
        self._first_attempt = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._state, self._error, self._last_data_utc = SensorState.STOPPED, None, None
        self._process = None

    # ---- to override
    @property
    def record_extension(self):  # pragma: no cover - abstract
        raise NotImplementedError

    def build_command_line(self) -> list:  # pragma: no cover - abstract
        raise NotImplementedError

    def prepare_record(self):
        """Hook called before each capture launch (preview image snapshot...)."""

    # ---- status
    def _set_state(self, state, error=None):
        with self._lock:
            self._state, self._error = state, error

    def health(self) -> dict:
        with self._lock:
            return dict(name=self.sensor_name, state=self._state, last_data_utc=self._last_data_utc, error=self._error)

    # ---- lifecycle
    def start(self, first_attempt_timeout_s=15) -> bool:
        """Launch the supervision thread; True iff the first capture was launched (OI-16)."""
        self._stop_event.clear()
        self._first_attempt.clear()
        self._set_state(SensorState.RESTARTING)
        self._thread = threading.Thread(target=self._supervise, name="sensor_" + self.sensor_name, daemon=True)
        self._thread.start()
        self._first_attempt.wait(first_attempt_timeout_s)
        return self.health()["state"] == SensorState.RUNNING

    def stop(self):
        """Ask the thread to end the record in progress (the cryptainer is finalized) and quit."""
        self._stop_event.set()

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)
        self._set_state(SensorState.STOPPED)

    # ---- internals
    def _free_start_time(self):
        """OI-20: a name already used (same second) makes us wait for the next second, never overwrite."""
        start = datetime.now(timezone.utc).replace(microsecond=0)
        while True:
            base = build_cryptainer_filename_base(self.sensor_name, start, self.record_extension)
            directory = self._storage._cryptainer_dir
            if not any((directory / (base + suffix)).exists() for suffix in (".crypt", ".crypt~", ".crypt.payload")):
                return base
            start += timedelta(seconds=1)
            delay = (start - datetime.now(timezone.utc)).total_seconds()
            if delay > 0 and self._stop_event.wait(min(delay, 1.5)):
                return base

    def _supervise(self):
        backoff_s = 0
        while not self._stop_event.is_set():
            started_at = time.monotonic()
            try:
                outcome = self._record_one_period()
            except Exception as exc:  # Cryptainer creation (disk full, guardian deleted...) or Popen failure: OI-18/19
                logger.error("Sensor %s could not record: %r", self.sensor_name, exc)
                self._set_state(SensorState.FAILED, repr(exc))
                outcome = "failed"
            finally:
                self._first_attempt.set()
            if self._stop_event.is_set() or outcome == "rollover":
                backoff_s = 0
                continue
            if time.monotonic() - started_at >= HEALTHY_RUN_S:
                backoff_s = 0
            backoff_s = next_backoff_s(backoff_s)
            if self.health()["state"] != SensorState.FAILED:
                self._set_state(SensorState.RESTARTING, "capture process exited")
            logger.warning("Sensor %s restarts in %s s", self.sensor_name, backoff_s)
            self._stop_event.wait(backoff_s)

    def _record_one_period(self):
        """Capture one record. Returns "rollover" (period over), "stopped", or "died" (capture ended by itself)."""
        base = self._free_start_time()
        stream = self._storage.create_cryptainer_encryption_stream(
            base, cryptainer_metadata=None, dump_initial_cryptainer=True,
            cryptainer_encryption_stream_class=RecorderEncryptionPipeline,
            cryptainer_encryption_stream_extra_kwargs=dict(progress_callback=self._on_progress))
        try:
            self.prepare_record()
            command_line = self.build_command_line()
            logger.info("Calling %s sensor subprocess command: %s", self.sensor_name, " ".join(command_line))
            process = subprocess.Popen(command_line, bufsize=self.chunk_size * 6, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except BaseException:
            stream.discard()  # OI-19
            raise
        with self._lock:
            self._process = process
        self._set_state(SensorState.RUNNING)
        self._first_attempt.set()
        readers = [threading.Thread(target=self._read_stdout, args=(process, stream)),
                   threading.Thread(target=self._read_stderr, args=(process,))]
        for reader in readers:
            reader.start()
        deadline = time.monotonic() + self._interval_s
        outcome = "died"
        while process.poll() is None:
            if self._stop_event.is_set():
                outcome = "stopped"
                break
            if time.monotonic() >= deadline:
                outcome = "rollover"
                break
            self._stop_event.wait(0.2)
        self._terminate(process)
        for reader in readers:
            reader.join(READER_JOIN_TIMEOUT_S)
            if reader.is_alive():
                logger.critical("A reader thread of sensor %s did not exit", self.sensor_name)
        return outcome

    def _on_progress(self):
        with self._lock:
            self._last_data_utc = datetime.now(timezone.utc)
        if self._activity_callback and self.activity_notification_color:
            try:
                self._activity_callback(notification_type=ActivityNotificationType.RECORDING_PROGRESS,
                                        notification_color=self.activity_notification_color)
            except Exception:
                logger.exception("Activity notification failed")

    def _read_stdout(self, process, stream):
        """The reader owns finalization: it ends when the capture closes stdout, whatever the reason."""
        try:
            while True:
                chunk = process.stdout.read(self.chunk_size)
                if not chunk:
                    break
                stream.encrypt_chunk(chunk)
                with self._lock:
                    self._last_data_utc = datetime.now(timezone.utc)
            if stream.plaintext_byte_count == 0:
                logger.warning("Sensor %s captured nothing, record discarded", self.sensor_name)
                stream.discard()  # OI-19
            else:
                stream.finalize()
        except Exception as exc:  # E.g. disk full: the cryptainer stays unfinished (.crypt~), but the sensor survives
            logger.error("Sensor %s failed while encrypting: %r", self.sensor_name, exc)
            self._set_state(SensorState.FAILED, repr(exc))
        finally:
            process.stdout.close()

    def _read_stderr(self, process):
        for line in process.stderr:
            logger.info("Subprocess stderr (%s): %s", self.sensor_name, line.decode("utf8", "ignore").rstrip())
        process.stderr.close()

    def _terminate(self, process):
        """terminate(), 10 s, then kill(), 5 s (04 §12). stdin is closed first: some tools quit on EOF."""
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=TERMINATE_TIMEOUT_S)
        except Exception as exc:
            logger.warning("Failed normal termination of %s subprocess: %r, killing it", self.sensor_name, exc)
            process.kill()
            try:
                process.wait(timeout=KILL_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                logger.critical("Force-termination of dangling %s subprocess failed", self.sensor_name)
        finally:
            if process.stdin:
                try:
                    process.stdin.close()
                except OSError:
                    pass


class PreviewImageMixin:
    """Preview of the latest record: unencrypted, small and greyscale (03 §6.6)."""

    preview_image_path: Path = None

    def _delete_old_preview(self):
        if self.preview_image_path:
            Path(self.preview_image_path).unlink(missing_ok=True)


class RtspCameraSensor(PreviewImageMixin, StreamSensor):
    """ffmpeg reading RTSP, fragmented MP4 to stdout, no audio by default; the preview is a second ffmpeg output."""

    sensor_name = "rtsp_camera"
    activity_notification_color = (0, 150, 0)

    def __init__(self, storage, interval_s, video_stream_url, ffmpeg_rtsp_parameters=(), ffmpeg_rtsp_output_format="",
                 preview_image_path=None, ffmpeg_version=None, **kwargs):
        super().__init__(storage, interval_s, **kwargs)
        assert video_stream_url
        self._url = video_stream_url
        self._parameters = list(ffmpeg_rtsp_parameters)
        self._format = ffmpeg_rtsp_output_format.strip() or "mp4"
        self.preview_image_path = preview_image_path
        self._ffmpeg_version = ffmpeg_version  # Test hook; else probed at each record start (03 §6.4)

    @property
    def record_extension(self):
        return "." + self._format

    def prepare_record(self):
        self._delete_old_preview()  # ffmpeg regenerates it itself

    def build_command_line(self):
        version = self._ffmpeg_version or get_ffmpeg_version()[0]
        timeout = []
        if version is not None:  # Unknown version: no option at all (OI-38 treats it as recent only for the checkup)
            timeout = ["-timeout" if version[0] >= 5 else "-stimeout", RTSP_SOCKET_TIMEOUT_US]
        codec = self._parameters or ["-vcodec", "copy", "-an", "-map", "0",
                                     "-movflags", "empty_moov+delay_moov"]  # OI-28: dead -f ismv/-probesize options dropped
        command = (["ffmpeg", "-y", "-hide_banner"] + timeout
                   + ["-rtsp_flags", "prefer_tcp", "-fflags", "+igndts", "-i", self._url]
                   + codec + ["-loglevel", "info", "-f", self._format, "pipe:1"])
        if self.preview_image_path:
            command += ["-frames:v", "1", "-filter:v", "scale=%d:-1,hue=s=0" % PREVIEW_IMAGE_WIDTH_PX,
                        str(self.preview_image_path)]
        return command


# ---------------------------------------------------------------- Raspberry Pi sensors (command lines only tested)

class RaspberryLibcameraSensor(PreviewImageMixin, StreamSensor):
    """libcamera-vid to stdout; with an `alsa_device_name`, H.264 + AAC muxed as MPEG-TS (modern camera stack)."""

    sensor_name = "rpi_libcamera"

    def __init__(self, storage, interval_s, alsa_device_name=None, libcameravid_video_parameters=(),
                 libcameravid_audio_parameters=(), preview_image_path=None, **kwargs):
        super().__init__(storage, interval_s, **kwargs)
        self._alsa_device_name = alsa_device_name
        self._video_parameters = list(libcameravid_video_parameters)
        self._audio_parameters = list(libcameravid_audio_parameters)
        self.preview_image_path = preview_image_path

    @property
    def record_extension(self):
        return ".mpegts" if self._alsa_device_name else ".h264"

    def prepare_record(self):
        self._delete_old_preview()
        if self.preview_image_path:
            command = ["libcamera-jpeg", "--nopreview", "--output", str(self.preview_image_path), "--width",
                       str(PREVIEW_IMAGE_WIDTH_PX), "--height", str(PREVIEW_IMAGE_HEIGHT_PX), "--immediate"]
            try:
                subprocess.check_call(command, timeout=20)
            except (OSError, subprocess.SubprocessError) as exc:  # Only logged (03 §6.5)
                logger.warning("Couldn't generate screenshot in %s sensor: %r", self.sensor_name, exc)

    def build_command_line(self):
        command = ["libcamera-vid", "--timeout", "0", "--nopreview", "--output", "pipe:" if self._alsa_device_name else "-"]
        command += self._video_parameters or ["--flush", "--framerate", "30"]
        if self._alsa_device_name:
            command += ["--codec", "libav", "--libav-format", "mpegts", "-q", "95", "--libav-audio", "--audio-codec",
                        "aac", "--audio-bitrate", "16000", "--audio-device", self._alsa_device_name]
            command += self._audio_parameters or ["--flush", "--framerate", "30"]
        return command


class RaspberryAlsaMicrophoneSensor(StreamSensor):
    """`arecord` (raw/wav) or, when compressing, `ffmpeg -f alsa` (mp3) to stdout."""

    sensor_name = "rpi_microphone"
    activity_notification_color = (150, 30, 130)
    chunk_size = int(0.2 * 1024 ** 2)
    DEFAULT_ARECORD_PARAMETERS = ["-c", "1", "-r", "22050", "-f", "S16_LE"]  # OI-27 (decided): 22050, not 22005

    def __init__(self, storage, interval_s, compress_recording=False, arecord_parameters=(), arecord_output_format="",
                 ffmpeg_alsa_parameters=(), ffmpeg_alsa_output_format="", **kwargs):
        super().__init__(storage, interval_s, **kwargs)
        self._compress = compress_recording
        self._arecord_parameters = list(arecord_parameters)
        self._ffmpeg_alsa_parameters = list(ffmpeg_alsa_parameters)
        self._format = ((ffmpeg_alsa_output_format.strip() or "mp3") if compress_recording
                        else (arecord_output_format.strip() or "wav"))

    @property
    def record_extension(self):
        return "." + self._format

    def build_command_line(self):
        if self._compress:
            parameters = self._ffmpeg_alsa_parameters or ["-i", "default", "-ac", "1", "-acodec", "libmp3lame", "-ab", "128k"]
            return ["ffmpeg", "-f", "alsa", "-loglevel", "error"] + parameters + ["-f", self._format, "pipe:1"]
        return ["arecord", "-t", self._format] + (self._arecord_parameters or self.DEFAULT_ARECORD_PARAMETERS)
