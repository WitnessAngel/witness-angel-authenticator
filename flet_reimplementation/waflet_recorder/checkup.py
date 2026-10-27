"""The checkup: six ordered `[OK]`/`[KO]` checks gating the start of a recording (03 §4.3.1, 02 §3.3). GUI-free.

Run it off the UI thread (it spawns `ffmpeg -version`, lists PulseAudio sources and probes the cryptainer folder).
"""
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

from waflet_components.i18n import tr
from waflet_components.storage import is_folder_writable

from . import probes
from .guardians import get_selected_guardian_uids, list_guardian_uids
from .settings import MIN_FFMPEG_VERSION

logger = logging.getLogger(__name__)


@dataclass
class CheckupLine:
    ok: bool
    message: str

    def __str__(self):
        return ("[OK] " if self.ok else "[KO] ") + self.message


@dataclass
class CheckupResult:
    lines: list = field(default_factory=list)

    @property
    def ok(self):
        return all(line.ok for line in self.lines)

    @property
    def text(self):
        """The multi-line text of the homepage checkup panel."""
        return "\n".join(str(line) for line in self.lines)

    @property
    def messages(self):
        return [str(line) for line in self.lines]


def _bad_setting(key, exc):
    return CheckupLine(False, tr.f('Invalid value for setting "{key}"', key=key))


def check_sensors(settings, list_microphones=probes.list_pulseaudio_microphone_names) -> CheckupLine:
    titles = []
    if settings.is_raspberry_pi:
        if settings.enable_local_camera:
            titles.append(tr._("local camera"))  # Existence of the camera is not checked
        if settings.enable_local_microphone:
            titles.append(tr._("local microphone"))
            try:
                microphones = list_microphones()
            except Exception as exc:  # OI-39: PulseAudio unavailable is a [KO] line, not a crash
                logger.warning("PulseAudio microphone listing failed: %r", exc)
                microphones = []
            if not microphones:
                return CheckupLine(False, tr._("Local microphone not found"))
    if settings.enable_ip_camera:
        url = settings.ip_camera_url
        titles.append(tr.f("IP camera {url}", url=url))
        try:
            valid = bool(url) and bool(urlparse(url).scheme)  # Any scheme, reachability is not tested (OI-40, keep)
        except ValueError:
            valid = False
        if not valid:
            return CheckupLine(False, tr.f('Wrong IP camera url: "{camera_url}"', camera_url=url))
    if not titles:
        return CheckupLine(False, tr._("No sensors are enabled"))
    return CheckupLine(True, tr.f("Sensors: {titles}", titles=", ".join(titles)))


def check_keyguardians(settings, pool) -> CheckupLine:
    count = len(get_selected_guardian_uids(settings, pool))
    threshold = settings.keyguardian_threshold
    message = tr.f("{keyguardian_count} key guardian(s) selected, {keyguardian_threshold} of which necessary for decryption",
                   keyguardian_count=count, keyguardian_threshold=threshold)
    dropped = len(settings.selected_keyguardians) - count
    if dropped > 0:  # OI-36: say that the selection was filtered
        message += " " + tr.f("({dropped} selected key guardian(s) not found were ignored)", dropped=dropped)
    return CheckupLine(0 < threshold <= count, message)


def check_cryptainer_dir(settings) -> CheckupLine:
    cryptainer_dir = settings.cryptainer_dir
    if not cryptainer_dir.is_dir():
        return CheckupLine(False, tr.f('Invalid container storage: "{cryptainer_dir}"', cryptainer_dir=cryptainer_dir))
    if not is_folder_writable(cryptainer_dir):  # OI-34
        return CheckupLine(False, tr.f('Container storage is not writable: "{cryptainer_dir}"',
                                       cryptainer_dir=cryptainer_dir))
    return CheckupLine(True, tr.f("Container storage: {cryptainer_dir}", cryptainer_dir=cryptainer_dir))


def check_recording_duration(settings) -> CheckupLine:
    duration = settings.recording_duration_mn
    return CheckupLine(duration > 0, tr.f("Each container stores {recording_duration_mn} mn(s) of video",
                                          recording_duration_mn="%g" % duration))  # OI-42: 15, not 15.0


def check_retention(settings) -> CheckupLine:
    days = settings.max_cryptainer_age_day
    return CheckupLine(days > 0, tr.f("Containers are kept for {max_cryptainer_age_day} day(s)",
                                      max_cryptainer_age_day=days))


def _ffmpeg_needed(settings):
    return settings.enable_ip_camera or (settings.is_raspberry_pi and settings.enable_local_microphone
                                         and settings.compress_local_microphone_recording)


def check_ffmpeg(settings, refresh=False) -> CheckupLine:
    version, error = probes.get_ffmpeg_version(use_cache=not refresh)
    minimum = "%d.%d" % MIN_FFMPEG_VERSION
    if error == "missing":
        if not _ffmpeg_needed(settings):  # OI-39: only the sensors using ffmpeg require it
            return CheckupLine(True, tr._("Ffmpeg module is not required by the enabled sensors"))
        return CheckupLine(False, tr._("Ffmpeg module not found, please ensure it is in your PATH"))
    if error == "unknown":  # OI-38: unknown (git/snap build) is treated as recent
        return CheckupLine(True, tr._("Ffmpeg module is installed, but beware its version couldn't be determined"))
    shown = "%d.%d" % version
    if version >= MIN_FFMPEG_VERSION:
        return CheckupLine(True, tr.f("Ffmpeg module is installed with a compatible {ffmpeg_version} version",
                                      ffmpeg_version=shown))
    ok = not _ffmpeg_needed(settings)
    return CheckupLine(ok, tr.f("Ffmpeg module is installed but this {ffmpeg_version} version is below required {min_ffmpeg_version}",
                                ffmpeg_version=shown, min_ffmpeg_version=minimum))


def run_checkup(settings, pool, refresh=False, list_microphones=probes.list_pulseaudio_microphone_names) -> CheckupResult:
    """All six checkers always run; the global status is the AND of the lines. A setting that cannot be parsed
    gives a `[KO]` line instead of an exception (OI-35, OI-36). `refresh=True` bypasses the ffmpeg cache."""
    checkers = [
        ("sensors", lambda: check_sensors(settings, list_microphones)),
        ("keyguardian_threshold", lambda: check_keyguardians(settings, pool)),
        ("cryptainer_dir", lambda: check_cryptainer_dir(settings)),
        ("recording_duration_mn", lambda: check_recording_duration(settings)),
        ("max_cryptainer_age_day", lambda: check_retention(settings)),
        ("ffmpeg", lambda: check_ffmpeg(settings, refresh=refresh)),
    ]
    result = CheckupResult()
    for key, checker in checkers:
        try:
            result.lines.append(checker())
        except ValueError as exc:  # configparser conversion errors
            result.lines.append(_bad_setting(key, exc))
    return result
