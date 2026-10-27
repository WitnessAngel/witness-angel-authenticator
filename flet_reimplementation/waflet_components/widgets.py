"""Reusable widgets: top bar, language menu, passphrase field, in-app folder/file browser."""
import logging
from pathlib import Path

import flet as ft

from .i18n import tr, LANGUAGE_NAMES

logger = logging.getLogger(__name__)


def icon_action(icon, tooltip_msgid, on_click, disabled=False):
    return ft.IconButton(icon=icon, tooltip=tr._(tooltip_msgid), on_click=on_click, disabled=disabled)


def top_bar(app, title, back=False, actions=(), disabled=False, menu=False):
    """02 §1.3: title, optional Back arrow (or `menu` hamburger opening the drawer), right-side icon actions."""
    leading = icon_action(ft.Icons.ARROW_BACK, "Back", lambda e: app.go_back(), disabled=disabled) if back else None
    if menu:
        leading = icon_action(ft.Icons.MENU, "Menu", lambda e: app.open_drawer())
    for action in actions:
        action.disabled = disabled
    return ft.AppBar(title=ft.Text(title), leading=leading, automatically_imply_leading=False, elevation=8,
                     bgcolor=ft.Colors.BLUE_900, color=ft.Colors.WHITE, actions=list(actions))


def language_menu(app):
    return ft.PopupMenuButton(
        icon=ft.Icons.LANGUAGE, tooltip=tr._("Language"),
        items=[ft.PopupMenuItem(content=ft.Text(name), on_click=lambda e, code=code: app.switch_language(code))
               for code, name in LANGUAGE_NAMES.items()])


def passphrase_field(autofocus=False, label_msgid="Passphrase", **kwargs):
    """OI-13 (decide): masked, with a reveal toggle."""
    return ft.TextField(label=tr._(label_msgid), password=True, can_reveal_password=True, autofocus=autofocus,
                        **kwargs)


def readonly_text_box(value="", **kwargs):
    return ft.TextField(value=value, read_only=True, multiline=True, **kwargs)


class FileBrowserDialog:
    """In-app browser (like 1.5's MDFileManager) used on desktop and web, where native pickers need
    zenity/kdialog or are unavailable. `select_folders=True` picks a folder, else a file with `extensions`."""

    def __init__(self, app, start_dir, on_select, select_folders=True, extensions=()):
        self.app, self.on_select = app, on_select
        self.select_folders, self.extensions = select_folders, tuple(e.lower() for e in extensions)
        self.current = Path(start_dir)
        self.listing = ft.ListView(height=360, width=480, spacing=0)
        self.path_label = ft.Text(selectable=True, size=12)

    def entries(self):
        try:
            children = sorted(self.current.iterdir(), key=lambda p: p.name.lower())
        except OSError as exc:
            logger.warning("Cannot list %s: %r", self.current, exc)
            children = []
        folders = [p for p in children if p.is_dir()]
        files = [] if self.select_folders else [p for p in children if p.is_file() and p.suffix.lower() in self.extensions]
        return folders, files

    def _refresh(self):
        folders, files = self.entries()
        self.path_label.value = str(self.current)
        rows = []
        if self.current.parent != self.current:
            rows.append(ft.ListTile(leading=ft.Icon(ft.Icons.ARROW_UPWARD), title=ft.Text(".."), dense=True,
                                    on_click=lambda e: self._open(self.current.parent)))
        rows += [ft.ListTile(leading=ft.Icon(ft.Icons.FOLDER), title=ft.Text(p.name), dense=True,
                             on_click=lambda e, p=p: self._open(p)) for p in folders]
        rows += [ft.ListTile(leading=ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED), title=ft.Text(p.name), dense=True,
                             on_click=lambda e, p=p: self._choose(p)) for p in files]
        self.listing.controls = rows

    def _open(self, path):
        self.current = path
        self._refresh()
        self.app.page.update()

    def _choose(self, path):
        self.app.close_dialog()
        self.app.guarded(self.on_select)(path)

    def show(self):
        self._refresh()
        actions = [ft.TextButton(tr._("Select this folder"), on_click=lambda e: self._choose(self.current))] \
            if self.select_folders else []
        self.app.show_dialog(tr._("Select a folder") if self.select_folders else tr._("Select a file"),
                             content=ft.Column([self.path_label, self.listing], tight=True),
                             actions=actions, close_label=tr._("Cancel"))


def pick_path(app, start_dir, on_select, select_folders=True, extensions=()):
    """Native OS picker on mobile (SAF / document picker paths), in-app browser elsewhere."""
    if not app.is_mobile:
        FileBrowserDialog(app, start_dir, on_select, select_folders, extensions).show()
        return

    async def _native():
        picker = ft.FilePicker()
        if select_folders:
            result = await picker.get_directory_path(initial_directory=str(start_dir))
        else:
            files = await picker.pick_files(initial_directory=str(start_dir), file_type=ft.FilePickerFileType.CUSTOM,
                                            allowed_extensions=[e.lstrip(".") for e in extensions])
            result = files[0].path if files else None
        if result:
            app.guarded(on_select)(Path(result))

    app.page.run_task(_native)


def empty_state():
    """02 §6.2: centred "Empty" message of an empty list."""
    return ft.Container(ft.Text(tr._("Empty"), size=20), alignment=ft.Alignment.CENTER, padding=40)


def banner(text):
    """The elevated one-line strip under each top bar (02 §1.4); `.content.value` can be updated."""
    return ft.Container(ft.Text(text), height=40, bgcolor=ft.Colors.BLUE_50, padding=ft.Padding.symmetric(horizontal=10),
                        alignment=ft.Alignment.CENTER_LEFT)


def selectable_row(title, checked, on_toggle, on_info=None, subtitle=None):
    """Checkbox + text + optional (i) icon (02 §5.2, §6.2). `on_toggle(bool)`, `on_info()`."""
    return ft.ListTile(
        leading=ft.Checkbox(value=checked, on_change=lambda e: on_toggle(bool(e.control.value))),
        title=ft.Text(title, size=14), subtitle=ft.Text(subtitle) if subtitle else None, dense=True,
        trailing=ft.IconButton(icon=ft.Icons.INFO_OUTLINE, tooltip=tr._("Details"), on_click=lambda e: on_info())
        if on_info else None)
