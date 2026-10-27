"""App-agnostic Flet shell: config, i18n, single background worker + blocking spinner, feedback
helpers, navigation stack, Back/Escape handling, settings dialog (01 §2, 02 §1)."""
import functools
import logging
import logging.handlers
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import flet as ft

from .config import AppConfig
from .i18n import tr, detect_language, SUPPORTED_LANGUAGES
from .storage import discover_storage_roots, bootstrap_storage, detect_platform

logger = logging.getLogger(__name__)

TOAST_DURATION_MS = 1500
SNACKBAR_DURATION_MS = 3500


def setup_logging():
    logging.basicConfig(stream=sys.stderr, level=os.environ.get("WA_LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    logging.Formatter.converter = __import__("time").gmtime  # UTC timestamps (01 §2.4)


class Screen:
    """A full-page screen. Subclasses implement `build()` -> list of controls; the View is made here."""
    name = ""
    title = ""
    parent_screen = None  # Screen name that Back returns to; None for the home screen
    top_level = False  # Top-level screens get the navigation drawer (when the app defines `drawer_entries`)

    def __init__(self, app):
        self.app = app

    def build(self):  # pragma: no cover - abstract
        raise NotImplementedError

    def build_view(self):
        return ft.View(route="/" + self.name, appbar=self.build_appbar(), padding=0, can_pop=self.can_go_back(),
                       drawer=self.app.build_drawer(self.name) if self.top_level else None,
                       controls=[ft.SafeArea(expand=True, content=ft.Container(padding=10, expand=True,
                                                                              content=self.build()))])

    def build_appbar(self):
        return None

    def on_enter(self):
        pass

    def can_go_back(self):
        return True

    def on_language_change(self):
        pass


class WaFletApp:
    """Subclass and set: title, config_filename, config_defaults_path, screen_classes, home_screen."""
    title = "Witness Angel"
    config_filename = "config.ini"
    config_defaults_path = None
    screen_classes = []
    home_screen = ""
    app_catalogs = []  # Registered before the components catalog, so they win
    log_filename = "app.log"
    language_setting = None  # ("section", "key") of the config where the language choice is persisted (OI-83)
    drawer_entries = []  # [(icon, label msgid, screen name)]: navigation drawer of the top-level screens
    drawer_logo = None  # bytes of a PNG shown on top of the drawer
    settings_instant = False  # True: every settings control saves at once (valid values only), no OK button

    def __init__(self, page, storage_roots=None):
        self.page = page
        self.storage_roots = storage_roots
        self.config = None
        self.screens = {cls.name: cls(self) for cls in self.screen_classes}
        self.stack = []  # Names of the screens currently in page.views
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wa-worker")  # Never concurrent
        self._current_dialog = None
        self._spinner = ft.Container(visible=False, left=0, top=0, right=0, bottom=0, alignment=ft.Alignment.CENTER,
                                     bgcolor=ft.Colors.with_opacity(0.25, ft.Colors.BLACK),
                                     content=ft.ProgressRing(width=46, height=46))
        self.busy = False

    # ------------------------------------------------------------ startup

    async def start(self):
        if self.storage_roots is None:
            self.storage_roots = await discover_storage_roots(self.page)
        self.setup()
        self.page.update()

    def setup(self):
        """Synchronous part of startup, also used by tests with a stub page."""
        bootstrap_storage(self.storage_roots)
        log_file = str(self.storage_roots.logs_dir / self.log_filename)
        if not any(getattr(h, "baseFilename", None) == log_file for h in logging.getLogger().handlers):
            log_handler = logging.handlers.RotatingFileHandler(  # OI-58: "check logs" now points somewhere
                log_file, maxBytes=1_000_000, backupCount=3, encoding="utf8", delay=True)
            log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
            logging.getLogger().addHandler(log_handler)
        self.config = AppConfig(self.storage_roots.internal_app_root / self.config_filename, self.config_defaults_path)
        for catalog in reversed(self.app_catalogs):
            tr.add_catalog(catalog, first=True)  # App catalogs win over the components one (OI-50)
        tr.lang = detect_language()
        if self.language_setting:
            stored = self.config.get(*self.language_setting)
            if stored in SUPPORTED_LANGUAGES:
                tr.lang = stored
        page = self.page
        page.title = self.title  # Deliberately untranslated
        page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE_900)
        page.theme_mode = ft.ThemeMode.LIGHT
        page.on_keyboard_event = self._on_keyboard_event
        page.on_view_pop = self._on_view_pop
        page.overlay.append(self._spinner)
        self.on_start()
        self.go(self.home_screen)

    def on_start(self):
        pass

    @property
    def platform(self):
        return self.storage_roots.platform if self.storage_roots else detect_platform()

    @property
    def is_mobile(self):
        return self.platform in ("android", "ios")

    # ------------------------------------------------------------ navigation

    def go(self, name):
        """Show screen `name`; the view stack is the chain of parent screens (Back pops one level)."""
        chain, current = [], name
        while current:
            chain.insert(0, current)
            current = self.screens[current].parent_screen
        self.stack = chain
        self.page.views.clear()
        self.page.views.extend(self.screens[n].build_view() for n in chain)
        self.page.update()
        self.screens[name].on_enter()

    @property
    def current_screen(self):
        return self.screens[self.stack[-1]] if self.stack else None

    def refresh_current_screen(self):
        """Rebuild the current screen in place (after a language switch, for instance)."""
        self.page.views[-1] = self.current_screen.build_view()
        self.page.update()

    def go_back(self):
        screen = self.current_screen
        if screen and screen.parent_screen and screen.can_go_back():
            self.go(screen.parent_screen)

    def handle_back(self) -> bool:
        """01 §2.2: close the dialog, else go up one level (OI-43), else let the key through."""
        if self._current_dialog is not None:
            self.close_dialog()
            return True
        screen = self.current_screen
        if screen and screen.parent_screen:
            self.go_back()  # Ignored while the screen refuses it (OI-12, key generation)
            return True
        return False

    def _on_keyboard_event(self, e):
        if e.key == "Escape":
            self.handle_back()

    def _on_view_pop(self, e):
        self.handle_back()

    # ------------------------------------------------------------ navigation drawer (02 §1.3)

    def build_drawer(self, current_name):
        if not self.drawer_entries:
            return None
        names = [name for _icon, _label, name in self.drawer_entries]

        async def _changed(e):
            await self.page.close_drawer()  # OI-93: closed explicitly
            self.guarded(self.go)(names[int(e.control.selected_index)])

        logo = [ft.Container(ft.Image(src=self.drawer_logo, width=150, height=150), alignment=ft.Alignment.CENTER,
                             padding=20)] if self.drawer_logo else []
        return ft.NavigationDrawer(
            selected_index=names.index(current_name) if current_name in names else None, on_change=_changed,
            controls=[*logo, *(ft.NavigationDrawerDestination(icon=icon, label=tr._(label))
                               for icon, label, _name in self.drawer_entries), *self.build_drawer_extras()])

    def build_drawer_extras(self):
        return []

    def open_drawer(self):
        self.page.run_task(self.page.show_drawer)

    # ------------------------------------------------------------ worker

    def call_on_ui(self, func, *args):
        """Marshal `func(*args)` to the UI event loop."""
        async def _runner():
            func(*args)
        try:
            self.page.run_task(_runner)
        except Exception:  # No running session (tests, shutdown): call inline
            func(*args)

    def set_busy(self, busy):
        self.busy = busy
        self._spinner.visible = busy  # The overlay absorbs taps, so no second operation can start (OI-27)
        self.page.update()

    def run_in_background(self, task, on_success=None, on_error=None):
        """01 §2.3: spinner, single worker, callback on the UI thread, spinner always hidden."""
        self.set_busy(True)

        def _done(future):
            exc = future.exception()
            def _finish():
                self.set_busy(False)
                if exc is not None:
                    if on_error is None or not on_error(exc):
                        self.report_unexpected_error(exc)
                elif on_success:
                    self.guarded(on_success)(future.result())
            self.call_on_ui(_finish)

        self._executor.submit(task).add_done_callback(_done)

    def report_unexpected_error(self, exc):
        logger.error("Abnormal error caught", exc_info=exc)
        self.snackbar(tr.f("Abnormal error caught: {error}", error=exc.__class__.__name__))

    def guarded(self, func):
        """Wrap a UI handler so that any exception shows the 'Abnormal error' snackbar (02 §1.4)."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                self.report_unexpected_error(exc)
        return wrapper

    # ------------------------------------------------------------ feedback

    def toast(self, message):
        self.page.show_dialog(ft.SnackBar(ft.Text(message), duration=ft.Duration(milliseconds=TOAST_DURATION_MS),
                                          behavior=ft.SnackBarBehavior.FLOATING))

    def snackbar(self, message):
        self.page.show_dialog(ft.SnackBar(ft.Text(message), duration=ft.Duration(milliseconds=SNACKBAR_DURATION_MS)))

    def show_dialog(self, title, text=None, content=None, actions=(), close_label=None, on_close=None, width=None):
        """Modal dialog with optional actions and always a last close button (02 §1.4)."""
        def _close(e=None):
            self.close_dialog()
            if on_close:
                on_close()
        body = content if content is not None else ft.Text(text or "", selectable=True)
        dialog = ft.AlertDialog(modal=True, title=ft.Text(title), scrollable=True,
                                content=ft.Container(body, width=width),
                                actions=[*actions, ft.TextButton(close_label or tr._("Close"), on_click=_close)])
        dialog._wa_on_close = on_close
        self.close_dialog(run_callback=False)
        self._current_dialog = dialog
        self.page.show_dialog(dialog)
        return dialog

    def close_dialog(self, run_callback=True):
        dialog, self._current_dialog = self._current_dialog, None
        if dialog is None:
            return
        dialog.open = False
        self.page.update()
        if run_callback and getattr(dialog, "_wa_on_close", None):
            callback, dialog._wa_on_close = dialog._wa_on_close, None
            callback()

    def run_dialog_action(self, handler):
        """Close the current dialog (without its close-callback) then run `handler`."""
        self.close_dialog(run_callback=False)
        self.guarded(handler)()

    def action_button(self, label, handler):
        return ft.TextButton(label, on_click=lambda e: self.run_dialog_action(handler))

    def show_help(self, title, text):
        width = self.page.width * 0.95 if isinstance(self.page.width, (int, float)) else None
        self.show_dialog(title, content=ft.Text(text, size=13, selectable=True), width=width)

    # ------------------------------------------------------------ settings

    settings_title = "Settings"

    def get_settings_schema(self):
        """List of {"type": "string"|"title", "title", "desc", "section", "key"} (Kivy-like schema)."""
        return []

    def validate_setting(self, section, key, value):
        """Return an error msgid, or None."""
        return None

    def on_setting_changed(self, section, key):
        """Instant mode: called after each saved change."""

    def on_settings_closed(self):
        """Instant mode: called when the dialog is closed."""

    def open_settings(self):
        if self.settings_instant:
            return self._open_instant_settings()
        fields = []
        controls = []
        for item in self.get_settings_schema():
            if item["type"] == "title":
                controls.append(ft.Text(item["title"], weight=ft.FontWeight.BOLD))
                continue
            field = ft.TextField(label=item["title"], helper=item.get("desc"), dense=True,
                                 value=self.config.get(item["section"], item["key"]))
            fields.append((item, field))
            controls.append(field)

        def _save():
            for item, field in fields:
                value = field.value.strip()
                error = self.validate_setting(item["section"], item["key"], value)
                if error:
                    self.show_dialog(tr._("Validation error"), tr._(error))
                    return
            for item, field in fields:
                self.config.set(item["section"], item["key"], field.value.strip())

        self.show_dialog(tr._(self.settings_title), content=ft.Column(controls, tight=True, width=400),
                         actions=[self.action_button(tr._("OK"), _save)], close_label=tr._("Cancel"))

    # ponytail: instant mode, types: title, string, bool, options ("options": [(value, label)]), numeric
    # ("numeric": "int"|"float", "gt"/"ge": exclusive/inclusive lower bound). Values are checked before saving.
    def _check_numeric(self, item, raw):
        try:
            number = (int if item.get("numeric") == "int" else float)(raw)
        except ValueError:
            return "Please enter a whole number" if item.get("numeric") == "int" else "Please enter a number"
        if "gt" in item and not number > item["gt"]:
            return tr.f("The value must be greater than {limit}", limit=item["gt"])
        if "ge" in item and not number >= item["ge"]:
            return tr.f("The value must be {limit} or more", limit=item["ge"])
        return None

    def apply_setting(self, item, raw):
        """Validate then save one value; returns the (translated) error or None."""
        error = self._check_numeric(item, raw) if item["type"] == "numeric" else None
        error = error or self.validate_setting(item["section"], item["key"], raw)
        if error:
            return tr._(error)
        self.config.set(item["section"], item["key"], raw)
        self._settings_dirty = True
        self.on_setting_changed(item["section"], item["key"])
        return None

    def _open_instant_settings(self):
        self._settings_dirty = False
        controls = []
        for item in self.get_settings_schema():
            kind, title, desc = item["type"], item["title"], item.get("desc")
            if kind == "title":
                controls.append(ft.Text(item["title"], weight=ft.FontWeight.BOLD, size=16))
                continue
            value = self.config.get(item["section"], item["key"])
            if kind == "bool":
                control = ft.Switch(label=title, value=value.strip().lower() in ("1", "true", "yes", "on"))
                control.on_change = lambda e, item=item, c=control: self.guarded(self.apply_setting)(item, "1" if c.value else "0")
            elif kind == "options":
                blank = "-"  # Dropdown keys cannot be empty
                control = ft.Dropdown(label=title, dense=True, value=value or blank, options=[
                    ft.DropdownOption(key=v or blank, text=label) for v, label in item["options"]])
                control.on_select = lambda e, item=item, c=control: self.guarded(self.apply_setting)(
                    item, "" if c.value == blank else c.value)
            else:  # string, numeric
                control = ft.TextField(label=title, dense=True, value=value)

                def _changed(e, item=item, c=control):
                    c.error = None
                    c.error_text = self.guarded(self.apply_setting)(item, c.value.strip())
                    self.page.update()
                control.on_change = _changed
            controls.append(control)
            if desc:
                controls.append(ft.Text(desc, size=12, color=ft.Colors.GREY_700))
        self.show_dialog(tr._(self.settings_title), content=ft.Column(controls, tight=True, width=420, spacing=8),
                         close_label=tr._("Close"), on_close=self._settings_closed)

    def _settings_closed(self):
        dirty, self._settings_dirty = self._settings_dirty, False
        if dirty:
            self.on_settings_closed()

    # ------------------------------------------------------------ language

    def switch_language(self, lang):
        tr.switch_lang(lang)
        if self.language_setting:
            self.config.set(*self.language_setting, lang)  # OI-83
        self.refresh_current_screen()
        self.current_screen.on_language_change()


def run_app(app_class, **run_kwargs):
    """Entry point helper: `ft.run(main)` with logging set up."""
    setup_logging()

    async def main(page: ft.Page):
        page.wa_app = app_class(page)
        await page.wa_app.start()

    return ft.run(main, **run_kwargs)
