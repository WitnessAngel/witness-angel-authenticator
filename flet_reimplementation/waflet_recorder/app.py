"""Witness Angel Recorder, Flet edition: app class, shared GUI state, service link, settings schema (02 §1, §4)."""
import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import flet as ft

from waflet_components.app_base import WaFletApp, run_app
from waflet_components.authenticator_services import get_gateway_proxy
from waflet_components.i18n import tr
from waflet_components.storage import bootstrap_recorder_storage, is_raspberry_pi, get_wait_time_multiplier

from . import PROGRAM_VERSION, locale_fr
from .checkup import run_checkup
from .cryptainers import open_management_storage
from .decryption import PassphraseMapper
from .guardians import open_keystore_pool, get_selected_guardian_uids
from .screens.claimant import (
    ClaimantRequestFormScreen, ClaimantRequestListScreen, ClaimantRequestDetailScreen,
)
from .screens.containers import ContainersScreen
from .screens.decryption import DecryptionProcessScreen, DecryptionResultScreen
from .screens.guardians import KeyGuardiansScreen
from .screens.homepage import HomepageScreen
from .service_control import ServiceController, ServiceSupervisor, GuiChannel, POLL_INTERVAL_S
from .settings import RecorderSettings, CONFIG_FILENAME, CONFIG_DEFAULTS_PATH, is_valid_gateway_url

logger = logging.getLogger(__name__)

PREVIEW_REFRESH_S = 15  # 02 §3.5
DECRYPTION_FLOW = ("cryptainer_decryption_process", "cryptainer_decryption_result",
                   "claimant_revelation_request_creation_form")  # Passphrases live only inside this flow (OI-68)
ASSETS_DIR = Path(__file__).parent / "assets"

# Record button states (02 §3.2): (enabled, pressed)
OFFLINE, IDLE, RECORDING = (False, False), (True, False), (True, True)

_active_app = None  # Web mode: one GUI socket per machine, a new session replaces the previous one


class WaRecorderApp(WaFletApp):
    title = "Witness Angel - Recorder"  # Never translated
    config_filename = CONFIG_FILENAME
    config_defaults_path = CONFIG_DEFAULTS_PATH
    settings_title = "Recorder settings"
    app_catalogs = [locale_fr.CATALOG]
    screen_classes = [HomepageScreen, KeyGuardiansScreen, ContainersScreen, DecryptionProcessScreen,
                      DecryptionResultScreen, ClaimantRequestFormScreen, ClaimantRequestListScreen,
                      ClaimantRequestDetailScreen]
    home_screen = HomepageScreen.name
    log_filename = "gui.log"
    language_setting = ("gui", "language")  # OI-83
    settings_instant = True
    drawer_entries = [(ft.Icons.HOME, "Recorder", "recorder_homepage"),
                      (ft.Icons.KEY, "Key Guardians", "foreign_keystore_management"),
                      (ft.Icons.LOCK, "Containers", "cryptainer_storage_management")]

    def __init__(self, page, storage_roots=None, controller=None, is_pi=None):
        super().__init__(page, storage_roots)
        self._controller, self._is_pi = controller, is_pi
        self.checkup_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wa-checkup")
        self.checkup_result, self._checkup_generation = None, 0
        self.record_state = OFFLINE
        self.service_status = None
        self.dismissed_refusal_at = None  # A refusal the user already moved past (new checkup run)
        self._notified_refusal_at, self._notified_storage_full = None, False
        self.selected_cryptainers = set()  # Names, shared by Containers, decryption and request screens
        self.passphrase_mapper = PassphraseMapper()
        self.last_decryption_results = None
        self.decryption_statuses = []  # Trustee statuses of the current selection, for the request form
        self.request_groups, self.selected_request_group = [], None
        self.channel, self._stopped = None, False

    # ------------------------------------------------------------ startup / services

    def on_start(self):
        roots = self.storage_roots
        bootstrap_recorder_storage(roots)
        self.settings = RecorderSettings(self.config, roots,
                                         is_raspberry_pi=is_raspberry_pi() if self._is_pi is None else self._is_pi)
        self.pool = open_keystore_pool(roots)
        self.wait_multiplier = get_wait_time_multiplier(self.settings.is_raspberry_pi)
        self.controller = self._controller or ServiceController(roots)
        self.supervisor = ServiceSupervisor(self.controller)
        logo = ASSETS_DIR / "warecorder_desktop_icon_512x512.png"
        self.logo_bytes = logo.read_bytes() if logo.exists() else None
        self.drawer_logo = self.logo_bytes

    async def start(self):
        await super().start()
        self.start_services()

    def start_services(self):
        """Needs the running event loop (not called by tests): OSC listener, 2 s poll, 15 s preview, first checkup."""
        global _active_app
        if _active_app is not None:
            _active_app.stop_services()
        _active_app = self
        self.page.on_close = lambda e: self.stop_services()
        self.channel = GuiChannel(
            self.storage_roots, supervisor=self.supervisor,
            on_recording_state=lambda value: self.call_on_ui(self.apply_recording_state, value),
            on_service_status=lambda status: self.call_on_ui(self.apply_service_status, status))
        self.channel.start()
        loop = asyncio.get_running_loop()
        loop.create_task(self._poll_loop())
        loop.create_task(self._preview_loop())
        self.refresh_checkup()

    def stop_services(self):
        self._stopped = True
        channel, self.channel = self.channel, None
        if channel:
            channel.stop()

    async def _poll_loop(self):
        interval = POLL_INTERVAL_S * self.wait_multiplier
        while not self._stopped:
            try:
                await asyncio.to_thread(self.supervisor.poll)  # 01 §4.4
            except Exception:
                logger.exception("Service poll failed")
            await asyncio.sleep(interval)

    async def _preview_loop(self):
        while not self._stopped:
            try:
                await asyncio.to_thread(self.screens["recorder_homepage"].load_preview)
                self.screens["recorder_homepage"].show_preview()
            except Exception:
                logger.exception("Preview refresh failed")
            await asyncio.sleep(PREVIEW_REFRESH_S)

    # ------------------------------------------------------------ shared state

    @property
    def gateway_url(self):
        return self.settings.wagateway_url  # Read at every call: changes apply at once (OI-72)

    def get_gateway_proxy(self):
        return get_gateway_proxy(self.gateway_url, timeout=10)

    def open_cryptainer_storage(self, read_only=True):
        return open_management_storage(self.settings.cryptainer_dir, self.pool, read_only=read_only)

    def get_selected_guardian_uids(self):
        return get_selected_guardian_uids(self.settings, self.pool)

    @property
    def recording(self):
        return self.record_state == RECORDING

    def go(self, name):
        if name not in DECRYPTION_FLOW:  # OI-68: passphrases (and the report they led to) are dropped on leaving
            self.passphrase_mapper.clear()
            self.last_decryption_results = None
        super().go(name)

    def handle_back(self) -> bool:
        """01 §4.6 / OI-91: dialog, else one level up, else (top-level pages) the home page, else the OS."""
        if self._current_dialog is None and self.current_screen and self.current_screen.top_level \
                and self.current_screen.name != self.home_screen:
            self.go(self.home_screen)
            return True
        return super().handle_back()

    # ------------------------------------------------------------ service state (called on the UI thread)

    def apply_recording_state(self, value):
        """True/False/None (change in progress), from `/receive_recording_state`."""
        self.record_state = RECORDING if value is True else IDLE if value is False else (False, self.record_state[1])
        self.screens["recorder_homepage"].render_state()

    def apply_service_status(self, status):
        """04 §11.1 status: refusal reason (OI-15), degraded sensors (OI-16..18), storage full (OI-44)."""
        self.service_status = status
        refusal = status.get("refusal")
        if refusal and refusal.get("at") != self._notified_refusal_at:
            self._notified_refusal_at = refusal.get("at")
            self.dismissed_refusal_at = None
            self.snackbar(self.refusal_summary(refusal))
        full = bool((status.get("storage") or {}).get("full"))
        if full and not self._notified_storage_full:
            self.snackbar(tr._("Container storage is almost full"))  # One per transition
        self._notified_storage_full = full
        self.screens["recorder_homepage"].render_checkup()
        self.screens["recorder_homepage"].render_state()

    @staticmethod
    def refusal_summary(refusal):
        first_ko = next((line["message"] for line in refusal.get("checkup") or [] if not line["ok"]), None)
        return tr._("Recording could not start") + tr._(": ") + (first_ko or refusal.get("error") or "")

    def checkup_lines(self):
        """02 §3.3 + "Proposed status display": the service's own lines after a refusal, else this GUI's run."""
        status = self.service_status or {}
        refusal = status.get("refusal")
        if refusal and refusal.get("at") != self.dismissed_refusal_at and refusal.get("checkup"):
            lines = [("[OK] " if line["ok"] else "[KO] ") + line["message"] for line in refusal["checkup"]]
            if refusal.get("error"):
                lines.append("[KO] " + tr._("Recording could not start") + tr._(": ") + refusal["error"])
        else:
            lines = self.checkup_result.messages if self.checkup_result else []
        if (status.get("storage") or {}).get("full"):
            lines.append("[KO] " + tr._("Container storage is almost full"))
        return lines

    def refresh_checkup(self, on_done=None):
        """Run the checkup off the UI thread (ffmpeg, PulseAudio...); stale runs are discarded."""
        refusal = (self.service_status or {}).get("refusal")
        if refusal:
            self.dismissed_refusal_at = refusal.get("at")  # The user asked for a fresh look at the configuration
        self._checkup_generation += 1
        generation = self._checkup_generation

        def _run():
            try:
                result = run_checkup(self.settings, self.pool)
            except Exception as exc:
                logger.exception("Checkup failed")
                self.call_on_ui(self.report_unexpected_error, exc)
                return
            if generation == self._checkup_generation:
                self.call_on_ui(self._checkup_done, result, on_done)

        self.checkup_executor.submit(_run)

    def _checkup_done(self, result, on_done):
        self.checkup_result = result
        self.screens["recorder_homepage"].render_checkup()
        if on_done:
            self.guarded(on_done)(result)

    # ------------------------------------------------------------ settings (02 §4)

    def on_setting_changed(self, section, key):
        self.refresh_checkup()  # 02 §3.4: live behind the panel

    def on_settings_closed(self):
        self.toast(tr._("Some configuration changes might only apply at next recording restart"))

    def validate_setting(self, section, key, value):
        if (section, key) == ("network", "wagateway_url") and not is_valid_gateway_url(value):
            return "The gateway URL must start with http:// or https://"  # OI-41
        return None

    def get_settings_schema(self):
        pi = self.settings.is_raspberry_pi
        schema = [dict(type="title", title=tr._("Sensors"))]

        def add(kind, section, key, title, desc, only_pi=False, **extra):
            if pi or not only_pi:
                schema.append(dict(type=kind, section=section, key=key, title=tr._(title), desc=tr._(desc), **extra))

        add("bool", "sensor", "enable_local_camera", "Local camera", "Enable attached camera", True)
        add("options", "sensor", "local_camera_rotation", "Local camera rotation",
            "Rotation angle of camera (Picamera only)", True, options=[(v, v) for v in ("0", "90", "180", "270")])
        add("bool", "sensor", "enable_local_microphone", "Local microphone", "Enable attached microphone", True)
        add("bool", "sensor", "compress_local_microphone_recording", "Compress audio", "Encode audio recording", True)
        add("bool", "sensor", "enable_local_camera_microphone_muxing", "Mux recordings",
            "Merge local video and audio (requires libcamera)", True)
        add("bool", "sensor", "enable_ip_camera", "IP camera", "Enable network camera")
        add("string", "sensor", "ip_camera_url", "IP Camera URL", "RTSP stream address")
        add("numeric", "sensor", "recording_duration_mn", "Media recording duration (mn)",
            "How long each audio/video clip must last", numeric="float", gt=0)  # OI-35: decimals allowed
        schema.append(dict(type="title", title=tr._("Key guardians")))
        add("numeric", "keyguardian", "keyguardian_threshold", "Key guardian threshold",
            "Count of key guardians required to decrypt data", numeric="int", ge=1)
        schema.append(dict(type="title", title=tr._("Storage")))
        add("string", "storage", "cryptainer_dir", "Container folder",
            "Folder to store containers (defaults to user profile)")
        add("numeric", "storage", "max_cryptainer_age_day", "Max retention period (days)",
            "For how long to keep a container before deletion", numeric="int", gt=0)
        if pi:
            schema.append(dict(type="title", title=tr._("Peripherals")))
            add("options", "peripheral", "epaper_type", "E-paper type", "Optional E-ink display", options=[
                ("", tr._("(none)")), ("waveshare_2.7_epaper", "waveshare_2.7_epaper"),
                ("waveshare_2.13_epaper_v3", "waveshare_2.13_epaper_v3"),
                ("waveshare_2.13_epaperb_v3", "waveshare_2.13_epaperb_v3"),
                ("dfrobot_2.13_epaper_v2", "dfrobot_2.13_epaper_v2")])
            add("options", "peripheral", "lcd_type", "LCD type", "Optional LCD display",
                options=[("", tr._("(none)")), ("waveshare_1.3_lcd", "waveshare_1.3_lcd")])
            add("bool", "peripheral", "enable_screen_buttons", "Screen buttons", "Enable epaper/lcd screen buttons")
            add("bool", "peripheral", "enable_button_shim", "5 buttons shim",
                "Enable Pimoroni buttonshim device (requires e-paper too)")
        schema.append(dict(type="title", title=tr._("Network")))
        add("string", "network", "wagateway_url", "Witness Angel Gateway URL", "Registry of key guardians")
        schema.append(dict(type="title", title=tr._("Advanced")))
        add("numeric", "sensor", "live_preview_interval_s", "Live preview interval",
            "How many seconds between live previews of Picamera (0 to disable)", True, numeric="float", ge=0)
        for key, title, desc in (
                ("libcameravid_video_parameters", "Libcameravid video params", "Replace libcameravid video parameters"),
                ("libcameravid_audio_parameters", "Libcameravid audio params", "Replace libcameravid audio parameters"),
                ("raspivid_parameters", "Raspivid params", "Replace raspivid parameters"),
                ("picamera_parameters", "Picamera params", "Json object to replace picamera parameters"),
                ("arecord_parameters", "Arecord params", "Replace arecord parameters"),
                ("arecord_output_format", "Arecord format", "Replace arecord output format (default: wav)"),
                ("ffmpeg_alsa_parameters", "Ffmpeg alsa params", "Replace ffmpeg alsa parameters"),
                ("ffmpeg_alsa_output_format", "Ffmpeg alsa format", "Replace ffmpeg alsa output format (default: mp3)")):
            add("string", "sensor", key, title, desc, True)
        add("string", "sensor", "ffmpeg_rtsp_parameters", "FFmpeg rtsp params",
            "Replace ffmpeg rtsp audio/video parameters")
        add("string", "sensor", "ffmpeg_rtsp_output_format", "Ffmpeg rtsp format",
            "Replace ffmpeg rtsp output format (default: mp4)")
        return schema

    # ------------------------------------------------------------ about (OI-90)

    def build_drawer_extras(self):
        return [ft.Divider(), ft.ListTile(leading=ft.Icon(ft.Icons.INFO_OUTLINE), title=ft.Text(tr._("About")),
                                          on_click=lambda e: self.guarded(self.show_about)())]

    def show_about(self):
        log_file = self.storage_roots.logs_dir / self.log_filename
        try:
            tail = "\n".join(log_file.read_text(encoding="utf8", errors="replace").splitlines()[-25:])
        except OSError:
            tail = ""
        self.show_dialog(tr._("About"), content=ft.Column([
            ft.Text("Witness Angel Recorder v%s" % PROGRAM_VERSION, weight=ft.FontWeight.BOLD),
            ft.Text(tr.f("Logs are stored in {path}", path=str(self.storage_roots.logs_dir)), selectable=True),
            ft.TextField(value=tail, read_only=True, multiline=True, min_lines=6, max_lines=12, text_size=11)],
            tight=True, width=480))


def main(**run_kwargs):
    return run_app(WaRecorderApp, **run_kwargs)
