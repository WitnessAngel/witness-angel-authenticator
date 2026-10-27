"""Probes of the host system: ffmpeg version, PulseAudio microphones, legacy Pi camera (03 §4.3.1, §6.1, 04 §12)."""
import logging
import re
import subprocess
import time

logger = logging.getLogger(__name__)

_FFMPEG_CACHE_TTL_S = 60
_ffmpeg_cache = {}


def parse_ffmpeg_version(output: str):
    """`(major, minor)` or None. OI-38: any number of digits, "n5.1"/"N-..." snap and git builds tolerated
    (git builds with no number give None, which callers treat as "recent")."""
    match = re.search(r"ffmpeg version\s+\D?(\d+)\.(\d+)", output.lower())
    return (int(match.group(1)), int(match.group(2))) if match else None


def get_ffmpeg_version(use_cache=True):
    """Return (version tuple or None, error kind): error kind is "missing" (no binary), "unknown" (no parsable
    version) or None. Cached 60 s, because the checkup runs at every setting change (OI-37)."""
    cached = _ffmpeg_cache.get("value")
    if use_cache and cached and time.monotonic() - cached[0] < _FFMPEG_CACHE_TTL_S:
        return cached[1]
    try:
        output = subprocess.check_output(["ffmpeg", "-version"], stderr=subprocess.STDOUT, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Error while calling ffmpeg to retrieve version: %r", exc)
        value = (None, "missing")
    else:
        version = parse_ffmpeg_version(output.decode("ascii", "ignore"))
        value = (version, None if version else "unknown")
    _ffmpeg_cache["value"] = (time.monotonic(), value)
    return value


def list_pulseaudio_microphone_names():
    """PulseAudio sources whose name contains "input", in PulseAudio order (monitors are ignored)."""
    import pulsectl  # Pi only, not installed elsewhere

    with pulsectl.Pulse("witness-angel-device") as pulse:
        return [source.name for source in pulse.source_list() if "input" in source.name.lower()]


def is_legacy_rpi_camera_enabled():
    try:
        return "supported=1 " in subprocess.check_output(["vcgencmd", "get_camera"], text=True)
    except (OSError, subprocess.CalledProcessError):
        return False
