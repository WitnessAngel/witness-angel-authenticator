"""The recording toolchain, rebuilt at each start (03 §4.3.2, §4.4): one storage + the enabled sensors."""
import logging
from dataclasses import dataclass

from waflet_components.authenticator_services import ServiceError

from . import probes
from .cryptainers import open_recording_storage, get_free_space_info
from .cryptoconf import build_cryptoconf
from .guardians import get_selected_guardian_uids
from .sensors import (
    RtspCameraSensor, RaspberryLibcameraSensor, RaspberryAlsaMicrophoneSensor, SensorState,
)

logger = logging.getLogger(__name__)


class StorageFullError(ServiceError):
    msgid = "Not enough free space in the container storage"


class NoSensorStartedError(ServiceError):
    msgid = "No sensor could be started"


def select_sensors(settings, storage, preview_image_path, activity_callback=None, list_microphones=None,
                   legacy_camera_check=None) -> list:
    """Sensor selection of 03 §6.1. Off a Raspberry Pi only the IP camera exists. The legacy picamera/raspivid
    branch is not implemented: a legacy camera stack makes the local camera sensor unavailable (logged)."""
    interval_s = settings.recording_duration_mn * 60
    common = dict(activity_callback=activity_callback)
    sensors = []
    if settings.enable_ip_camera:
        sensors.append(RtspCameraSensor(
            storage, interval_s, settings.ip_camera_url, settings.ffmpeg_rtsp_parameters,
            settings.ffmpeg_rtsp_output_format, preview_image_path=preview_image_path, **common))
    if settings.is_raspberry_pi:
        audio_done = False
        if settings.enable_local_camera:
            if (legacy_camera_check or probes.is_legacy_rpi_camera_enabled)():
                logger.error("Legacy Raspberry Pi camera stack (picamera) is not supported by this recorder, "
                             "local camera ignored")
            else:
                microphone = None
                if settings.enable_local_camera_microphone_muxing and settings.enable_local_microphone:
                    microphone = (list_microphones or probes.list_pulseaudio_microphone_names)()[0]
                    audio_done = True
                sensors.append(RaspberryLibcameraSensor(
                    storage, interval_s, microphone, settings.libcameravid_video_parameters,
                    settings.libcameravid_audio_parameters, preview_image_path=preview_image_path, **common))
        if settings.enable_local_microphone and not audio_done:
            sensors.append(RaspberryAlsaMicrophoneSensor(
                storage, interval_s, settings.compress_local_microphone_recording, settings.arecord_parameters,
                settings.arecord_output_format, settings.ffmpeg_alsa_parameters,
                settings.ffmpeg_alsa_output_format, **common))
    return sensors


@dataclass
class RecordingToolchain:
    storage: object
    sensors: list
    cryptainer_dir: object

    def start(self) -> list:
        """Start every sensor; raise `NoSensorStartedError` (after stopping) if none could launch (OI-16).
        Returns the health list, where some sensors may already be degraded."""
        started = [sensor.start() for sensor in self.sensors]
        if not any(started):
            errors = "; ".join("%s: %s" % (h["name"], h["error"]) for h in self.health())
            self.stop()
            raise NoSensorStartedError("No sensor could be started (%s)" % errors)
        return self.health()

    def stop(self):
        """Stop sensors, wait for the last records to be finalized, then for the encryption worker + purge."""
        for sensor in self.sensors:
            sensor.stop()
        for sensor in self.sensors:
            sensor.join()
        self.storage.wait_for_idle_state()

    def health(self) -> list:
        return [sensor.health() for sensor in self.sensors]

    @property
    def is_running(self):
        return any(h["state"] != SensorState.STOPPED for h in self.health())


def build_recording_toolchain(settings, pool, roots, activity_callback=None, **select_kwargs) -> RecordingToolchain:
    """Raises if the folder is invalid (`NotADirectoryError`), full (`StorageFullError`), the cryptoconf cannot be
    built (`NoEncryptionKeyError`, schema errors) or no sensor is enabled."""
    cryptainer_dir = settings.cryptainer_dir
    if not cryptainer_dir.is_dir():
        raise NotADirectoryError(str(cryptainer_dir))
    if get_free_space_info(cryptainer_dir)["full"]:  # OI-44
        raise StorageFullError(str(cryptainer_dir))
    cryptoconf = build_cryptoconf(settings.keyguardian_threshold, get_selected_guardian_uids(settings, pool), pool)
    storage = open_recording_storage(cryptainer_dir, pool, cryptoconf, settings.max_cryptainer_age_day)
    sensors = select_sensors(settings, storage, roots.preview_image, activity_callback, **select_kwargs)
    if not sensors:
        raise ValueError("No sensors are enabled")
    return RecordingToolchain(storage=storage, sensors=sensors, cryptainer_dir=cryptainer_dir)
