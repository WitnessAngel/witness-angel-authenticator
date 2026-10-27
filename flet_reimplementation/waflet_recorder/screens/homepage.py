"""Recorder homepage (02 §3): record button state machine, checkup panel, preview image, toolbar."""
import logging
import time

import flet as ft

from waflet_components.app_base import Screen
from waflet_components.i18n import tr
from waflet_components.widgets import top_bar, icon_action, language_menu, readonly_text_box

logger = logging.getLogger(__name__)


def format_age(seconds):
    if seconds < 90:
        return tr.f("{count} s", count=int(seconds))
    if seconds < 5400:
        return tr.f("{count} mn", count=int(seconds // 60))
    return tr.f("{count} h", count=int(seconds // 3600))


def classify_preview(age_s, recording, recording_duration_mn):
    """OI-31: the image is current only while recording and no older than twice the clip duration."""
    return "current" if recording and age_s <= 2 * recording_duration_mn * 60 else "stale"


class HomepageScreen(Screen):
    name = "recorder_homepage"
    title = "Recorder"
    top_level = True

    def __init__(self, app):
        super().__init__(app)
        self.record_button = self.record_label = self.status_text = self.checkup_box = None
        self.preview_image = self.preview_caption = None
        self._preview = None  # (bytes, mtime) of the file last read, None if absent

    # ------------------------------------------------------------ layout

    def build(self):
        self.record_label = ft.Text(tr._("Start Recording"), size=26, weight=ft.FontWeight.BOLD)
        self.record_button = ft.Button(content=self.record_label, expand=True, height=80, disabled=True,
                                       on_click=lambda e: self.app.guarded(self.on_record_pressed)())
        self.status_text = ft.Text("", color=ft.Colors.ORANGE_900, visible=False)
        self.checkup_box = readonly_text_box("", expand=True, text_size=13)
        self.preview_image = ft.Image(src=self.app.logo_bytes or b"", fit=ft.BoxFit.CONTAIN, expand=True)
        self.preview_caption = ft.Text("", size=12, italic=True, visible=False)
        self.render_state()
        self.render_checkup()
        self.show_preview()
        return ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
            ft.Row([ft.Container(expand=1), ft.Container(self.record_button, expand=8), ft.Container(expand=1)]),
            self.status_text,
            ft.Container(self.checkup_box, expand=4),
            ft.Container(ft.Column([self.preview_image, self.preview_caption], expand=True,
                                   horizontal_alignment=ft.CrossAxisAlignment.CENTER), expand=4),
        ])

    def build_appbar(self):
        return top_bar(self.app, tr._(self.title), menu=True, actions=[
            icon_action(ft.Icons.REFRESH, "Refresh", lambda e: self.app.guarded(self.app.refresh_checkup)()),
            icon_action(ft.Icons.WARNING_AMBER, "Reset background service",
                        lambda e: self.app.guarded(self.ask_reset_service)()),
            language_menu(self.app),
            icon_action(ft.Icons.SETTINGS, "Settings", lambda e: self.app.guarded(self.app.open_settings)()),
        ])

    def on_enter(self):
        self.app.refresh_checkup()  # 02 §2: all checks re-run on entering
        self.app.guarded(self._reload_preview)()

    def on_language_change(self):
        self.app.refresh_checkup()

    # ------------------------------------------------------------ record button

    def render_state(self):
        """Button label/enabled/pressed from `app.record_state`, plus the degraded-sensors line (OI-16..18)."""
        if self.record_button is None:
            return
        enabled, pressed = self.app.record_state
        self.record_button.disabled = not enabled
        self.record_label.value = tr._("Stop Recording") if pressed else tr._("Start Recording")
        self.record_button.style = ft.ButtonStyle(bgcolor=ft.Colors.RED_700 if pressed else None,
                                                  color=ft.Colors.WHITE if pressed else None)
        status = self.app.service_status or {}
        degraded = [s for s in status.get("sensors") or [] if s["state"] in ("restarting", "failed")]
        self.status_text.visible = bool(pressed and degraded)
        self.status_text.value = tr.f("Recording (degraded): {sensors}", sensors=", ".join(
            "%s %s" % (s["name"], tr._(s["state"])) for s in degraded)) if degraded else ""
        self.app.page.update()

    def on_record_pressed(self):
        """Only user actions send commands (OI-22). The button stays disabled until the service answers."""
        app = self.app
        enabled, pressed = app.record_state
        if not enabled:
            return
        app.record_state = (False, pressed)
        self.render_state()
        if pressed:
            app.controller.stop_recording()
            return

        def _checked(result):
            if result.ok:
                app.controller.start_recording()
            else:
                app.record_state = (True, False)  # Nothing was sent: no broadcast will come
                self.render_state()
                app.snackbar(tr._("Configuration errors prevent recording"))

        app.refresh_checkup(on_done=_checked)

    def render_checkup(self):
        if self.checkup_box is None:
            return
        self.checkup_box.value = "\n".join(self.app.checkup_lines())
        self.app.page.update()

    # ------------------------------------------------------------ reset service (OI-13)

    def ask_reset_service(self):
        self.app.show_dialog(
            tr._("Reset background service"),
            tr._("This stops the background service, and the recording in progress if any. It is restarted "
                 "automatically within seconds. Continue?"),
            actions=[self.app.action_button(tr._("Confirm"), self.reset_service)], close_label=tr._("Cancel"))

    def reset_service(self):
        app = self.app
        app.record_state = (False, False)
        self.render_state()
        wait_s = 45 * app.wait_multiplier
        app.run_in_background(lambda: app.controller.stop_service(wait_s))  # Off the UI thread, with the spinner

    # ------------------------------------------------------------ preview (02 §3.5, OI-31)

    def load_preview(self):
        """Blocking file read (called in a thread)."""
        path = self.app.storage_roots.preview_image
        try:
            self._preview = (path.read_bytes(), path.stat().st_mtime)
        except OSError:
            self._preview = None

    def _reload_preview(self):  # No spinner for a background refresh
        def _task():
            self.load_preview()
            self.app.call_on_ui(self.show_preview)
        self.app.checkup_executor.submit(_task)

    def show_preview(self):
        if self.preview_image is None:
            return
        preview = self._preview
        if preview is None:
            self.preview_image.src, self.preview_image.opacity = self.app.logo_bytes or b"", 1
            self.preview_caption.visible = False
        else:
            data, mtime = preview
            age = max(0, time.time() - mtime)
            try:
                duration = self.app.settings.recording_duration_mn
            except ValueError:
                duration = 15
            current = classify_preview(age, self.app.recording, duration) == "current"
            self.preview_image.src, self.preview_image.opacity = data, 1 if current else 0.3
            self.preview_caption.visible = not current
            self.preview_caption.value = tr.f("Last preview, taken {age} ago", age=format_age(age))
        self.app.page.update()
