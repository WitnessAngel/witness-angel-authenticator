"""Typed access to `warecorder_config.ini` (01 §6.2, 03 §3). GUI-free, used by the GUI and the service.

Value errors (a hand-edited "2.0" threshold...) raise `ValueError`; the checkup turns them into `[KO]` lines (OI-35).
"""
import json
import logging
import shlex
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from waflet_components.config import AppConfig

CONFIG_FILENAME = "warecorder_config.ini"  # Same name as the Kivy app: existing settings are found
CONFIG_DEFAULTS_PATH = Path(__file__).parent / "config_defaults.ini"
DEFAULT_RTSP_FORMAT, DEFAULT_ARECORD_FORMAT, DEFAULT_FFMPEG_ALSA_FORMAT = "mp4", "wav", "mp3"
logger = logging.getLogger(__name__)
MIN_FFMPEG_VERSION = (4, 3)  # Hardcoded in 1.0 too, not a setting


def load_recorder_config(roots) -> AppConfig:
    return AppConfig(roots.internal_app_root / CONFIG_FILENAME, CONFIG_DEFAULTS_PATH)


class RecorderSettings:
    """Thin typed view over an `AppConfig`; `reload()` re-reads the file (service: at each start request)."""

    def __init__(self, config: AppConfig, roots, is_raspberry_pi=False):
        self.config = config
        self.roots = roots
        self.is_raspberry_pi = is_raspberry_pi

    def reload(self):
        self.config.reload()

    # ---- helpers
    def _str(self, section, key):
        return self.config.get(section, key).strip()

    def _bool(self, section, key):
        return self.config.getboolean(section, key)

    def _args(self, key):  # "parameters" settings: shlex-split, a non-empty list REPLACES the defaults (OI-29)
        return shlex.split(self._str("sensor", key))

    # ---- [sensor]
    enable_local_camera = property(lambda s: s._bool("sensor", "enable_local_camera"))
    local_camera_rotation = property(lambda s: s.config.getint("sensor", "local_camera_rotation"))
    enable_local_microphone = property(lambda s: s._bool("sensor", "enable_local_microphone"))
    compress_local_microphone_recording = property(lambda s: s._bool("sensor", "compress_local_microphone_recording"))
    enable_local_camera_microphone_muxing = property(lambda s: s._bool("sensor", "enable_local_camera_microphone_muxing"))
    enable_ip_camera = property(lambda s: s._bool("sensor", "enable_ip_camera"))
    ip_camera_url = property(lambda s: s._str("sensor", "ip_camera_url"))
    recording_duration_mn = property(lambda s: s.config.getfloat("sensor", "recording_duration_mn"))
    live_preview_interval_s = property(lambda s: s.config.getfloat("sensor", "live_preview_interval_s"))
    libcameravid_video_parameters = property(lambda s: s._args("libcameravid_video_parameters"))
    libcameravid_audio_parameters = property(lambda s: s._args("libcameravid_audio_parameters"))
    raspivid_parameters = property(lambda s: s._args("raspivid_parameters"))
    arecord_parameters = property(lambda s: s._args("arecord_parameters"))
    arecord_output_format = property(lambda s: s._str("sensor", "arecord_output_format"))
    ffmpeg_alsa_parameters = property(lambda s: s._args("ffmpeg_alsa_parameters"))
    ffmpeg_alsa_output_format = property(lambda s: s._str("sensor", "ffmpeg_alsa_output_format"))
    ffmpeg_rtsp_parameters = property(lambda s: s._args("ffmpeg_rtsp_parameters"))
    ffmpeg_rtsp_output_format = property(lambda s: s._str("sensor", "ffmpeg_rtsp_output_format"))  # Stripped (1.0 did not)

    @property
    def picamera_parameters(self):
        raw = self._str("sensor", "picamera_parameters")
        if not raw:
            return None
        parameters = json.loads(raw)
        if not isinstance(parameters, dict) or "resolution" not in parameters:  # A real check, not an assert
            raise ValueError("picamera_parameters must be a JSON object with a 'resolution' key")
        return parameters

    # ---- [keyguardian]
    keyguardian_threshold = property(lambda s: s.config.getint("keyguardian", "keyguardian_threshold"))

    @property
    def selected_keyguardians(self):
        """UUID strings in config order. Malformed ones are skipped (OI-36); unknown ones are dropped by the callers."""
        result = []
        for item in self.config.get("keyguardian", "selected_keyguardians").split(","):
            item = item.strip()
            try:
                result.append(str(UUID(item)))
            except ValueError:
                if item:
                    logger.warning("Ignoring malformed selected key guardian %r", item)
        return result

    def set_selected_keyguardians(self, uids):
        self.config.set("keyguardian", "selected_keyguardians", ",".join(str(u) for u in uids))

    # ---- [storage]
    @property
    def cryptainer_dir(self) -> Path:
        """Empty setting means the internal folder. The path may not exist (the checkup says so)."""
        value = self._str("storage", "cryptainer_dir")
        return Path(value) if value else self.roots.default_cryptainers_dir

    max_cryptainer_age_day = property(lambda s: s.config.getint("storage", "max_cryptainer_age_day"))

    # ---- [peripheral]
    epaper_type = property(lambda s: s._str("peripheral", "epaper_type").lower())
    lcd_type = property(lambda s: s._str("peripheral", "lcd_type").lower())
    enable_screen_buttons = property(lambda s: s._bool("peripheral", "enable_screen_buttons"))
    enable_button_shim = property(lambda s: s._bool("peripheral", "enable_button_shim"))

    # ---- [network]
    wagateway_url = property(lambda s: s._str("network", "wagateway_url"))  # Read at each call (OI-72)


def is_valid_gateway_url(url) -> bool:
    """OI-41: for the settings dialog (the gateway is not a recording precondition, so not in the checkup)."""
    parsed = urlparse(url or "")
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)
