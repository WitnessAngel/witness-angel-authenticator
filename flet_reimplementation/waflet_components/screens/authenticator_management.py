"""Main screen "Authenticators" (02 §3).

App contract (duck-typed): `app.storage_roots`, `app.custom_folder` (read/write property persisted by the app),
`app.selected_authenticator_dir` (shared with the other screens), plus the WaFletApp helpers.
"""
import logging
from pathlib import Path

import flet as ft

from ..app_base import Screen
from ..authenticator_services import (
    compute_authenticator_status, check_authenticator_passphrase, export_authenticator, import_authenticator,
    destroy_authenticator, ServiceError,
)
from ..formatting import (
    COLON, format_keypair_label, format_utc_datetime_label, format_path_for_display, indent_text,
    convert_bytes_to_human_representation,
)
from ..i18n import tr
from ..storage import list_authenticator_locations, LocationType, is_folder_accessible
from ..widgets import top_bar, icon_action, language_menu, passphrase_field, readonly_text_box, pick_path

logger = logging.getLogger(__name__)

STATUS_ICONS = {None: ft.Icons.HELP_CENTER_OUTLINED, False: ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                True: ft.Icons.CHECK_CIRCLE_OUTLINE}
STATUS_MESSAGES = {None: "No valid location selected", False: "Authenticator not initialized",
                   True: "Authenticator initialized"}
INVALID_REASON_MESSAGES = {
    "parent_missing": "Selected folder is invalid!",
    "parent_not_writable": "Beware, parent folder is NOT writable!",
    "not_a_folder": "Beware, this is not a folder!",
    "folder_not_writable": "Beware, this folder is NOT writable!",
}


def format_location_texts(location):
    """(primary, secondary) texts of a location row (02 §3.2)."""
    kind = location["location_type"]
    if kind == LocationType.USER_PROFILE:
        return tr._("User profile"), tr._("Stored inside system disk")
    if kind == LocationType.CUSTOM_FOLDER:
        folder = location.get("custom_folder")
        return tr._("Custom location"), (format_path_for_display(folder) if folder else tr._("Please select a folder"))
    device = location["authdevice"]
    return (tr.f("Drive {drive} ({label})", drive=device["partition_mountpoint"],
                 label=device["partition_label"] or tr._("no name")),
            tr.f("Size: {size}, Filesystem: {filesystem}",
                 size=convert_bytes_to_human_representation(device["filesystem_size"]),
                 filesystem=str(device["filesystem_format"]).upper()))


def format_authenticator_info(status_result, display_path=format_path_for_display):
    """Information-area text for a status computed by `compute_authenticator_status` (02 §3.3)."""
    reason = status_result["reason"]
    if reason == "no_location":
        return tr._("Please select an authenticator folder")
    authenticator_dir = status_result["authenticator_dir"]
    if reason == "invalid_data":
        return tr.f("Invalid authenticator data in {path}", path=authenticator_dir)  # Raw path, as in 1.5
    path_line = tr._("Path") + COLON() + display_path(authenticator_dir)
    if reason in INVALID_REASON_MESSAGES:
        return path_line + "\n\n" + tr._(INVALID_REASON_MESSAGES[reason])
    if reason == "not_initialized":
        return path_line
    metadata = status_result["metadata"]
    created = metadata.get("keystore_creation_datetime")
    keypairs = "\n".join(format_keypair_label(k["key_algo"], k["keychain_uid"], k["private_key_present"])
                         for k in status_result["keypairs"])
    lines = [
        path_line, "",
        tr._("User") + COLON() + metadata["keystore_owner"],
        tr._("Password hint") + COLON() + metadata.get("keystore_passphrase_hint", ""),  # OI-17
        tr._("Creation date") + COLON() + (format_utc_datetime_label(created, show_time=True) if created
                                           else tr._("Unknown")),  # OI-51
        tr._("ID") + COLON() + str(metadata["keystore_uid"]), "",
        tr._("Keypairs") + COLON().rstrip() + "\n" + indent_text(keypairs),
    ]
    text = "\n".join(lines)
    if not status_result["has_secret"]:
        text += "\n\n" + tr._("This authenticator has no gateway secret and cannot be published or receive requests")
    return text


def format_check_result(result):
    """(title, text) of the Check result dialog (02 §3.7)."""
    if result["success"]:
        return (tr.f("Checkup result: {result}", result=tr._("Success")),
                tr.f("Keypairs successfully tested: {count}", count=result["keypair_count"]))
    return (tr.f("Checkup result: {result}", result=tr._("Failure")),
            tr.f("Keypairs tested: {keypair_count}\nMissing private keys: {missing_private_keys}\n"
                 "Wrong passphrase for keys:  {undecodable_private_keys}",
                 keypair_count=result["keypair_count"],
                 missing_private_keys=", ".join(format_keypair_label(*k) for k in result["missing_private_keys"]) or "-",
                 undecodable_private_keys=", ".join(format_keypair_label(*k) for k in result["undecodable_private_keys"]) or "-"))


class AuthenticatorManagementScreen(Screen):
    name = "authenticator_management"
    creation_screen = "authenticator_creation_form"
    publication_screen = "authenticator_publication_form"
    revelation_requests_screen = "authenticator_revelation_request_management"

    def __init__(self, app):
        super().__init__(app)
        self.locations = []
        self.selected_index = 0
        self.status_result = dict(status=None, reason="no_location")

    # ------------------------------------------------------------ layout

    def build(self):
        self.location_list = ft.Column(spacing=0)
        self.status_icon = ft.Icon(STATUS_ICONS[None])
        self.status_text = ft.Text(tr._(STATUS_MESSAGES[None]))
        self.info_box = readonly_text_box(tr._("No information available"), min_lines=8, max_lines=14, text_size=13)
        btn = lambda label, icon, handler, **kw: ft.Button(content=tr._(label), icon=icon, expand=True,
                                                          on_click=lambda e: self.app.guarded(handler)(), **kw)
        self.group_a = [btn("Initialize", ft.Icons.VPN_KEY_OUTLINED, self.open_creation_form),
                        btn("Import", ft.Icons.DOWNLOAD, self.import_archive)]
        self.button_publish = btn("Publish", ft.Icons.SHARE, lambda: self.app.go(self.publication_screen))
        self.button_authorizations = btn("Authorizations", ft.Icons.LOCK_OPEN,
                                         lambda: self.app.go(self.revelation_requests_screen))
        self.group_b = [btn("Export", ft.Icons.UPLOAD, self.export_archive),
                        btn("Check", ft.Icons.GPS_FIXED, self.check_passphrase),
                        btn("Destroy", ft.Icons.DELETE_FOREVER_OUTLINED, self.destroy),
                        self.button_publish, self.button_authorizations]
        self._render_locations()
        self._render_status()
        strip = lambda content: ft.Container(content, height=40, bgcolor=ft.Colors.BLUE_50, border_radius=4,
                                             padding=ft.Padding.symmetric(horizontal=10), alignment=ft.Alignment.CENTER_LEFT)
        return ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
            strip(ft.Text(tr._("Please select an authenticator location"), weight=ft.FontWeight.BOLD)),
            self.location_list,
            strip(ft.Row([ft.Container(self.status_icon, width=80, alignment=ft.Alignment.CENTER), self.status_text])),
            self.info_box,
            ft.Row(self.group_a),
            ft.Row(self.group_b[0:2]), ft.Row(self.group_b[2:4]), ft.Row(self.group_b[4:5]),
        ])

    def build_appbar(self):
        return top_bar(self.app, tr._("Authenticators"), actions=[
            icon_action(ft.Icons.REFRESH, "Refresh", lambda e: self.app.guarded(self.refresh_locations)()),
            language_menu(self.app),
            icon_action(ft.Icons.HELP_OUTLINE, "Help", lambda e: self.show_help()),
            icon_action(ft.Icons.SETTINGS, "Settings", lambda e: self.app.open_settings()),
        ])

    def on_enter(self):
        self.refresh_locations()

    def on_language_change(self):
        self.refresh_locations(show_toast=False)

    # ------------------------------------------------------------ locations & status

    def refresh_locations(self, show_toast=True):
        previous_dir = self.app.selected_authenticator_dir
        self.locations = list_authenticator_locations(self.app.storage_roots, self.app.custom_folder)
        matching = [i for i, loc in enumerate(self.locations) if previous_dir and loc["authenticator_dir"] == previous_dir]
        self.select_location(matching[0] if matching else 0)
        if show_toast and not self.app.is_mobile:
            self.app.toast(tr._("Refreshed authenticator locations"))

    def select_location(self, index):
        self.selected_index = index
        self.status_result = compute_authenticator_status(self.locations[index]["authenticator_dir"])
        self.app.selected_authenticator_dir = self.status_result.get("authenticator_dir")
        self._render_locations()
        self._render_status()
        self.app.page.update()

    def _render_locations(self):
        rows = []
        for index, location in enumerate(self.locations):
            primary, secondary = format_location_texts(location)
            icon = {LocationType.USER_PROFILE: ft.Icons.ACCOUNT_BOX, LocationType.CUSTOM_FOLDER: ft.Icons.FOLDER,
                    LocationType.USB_DEVICE: ft.Icons.USB}[location["location_type"]]
            trailing = icon_action(ft.Icons.FIND_IN_PAGE_OUTLINED, "Select a folder",
                                   lambda e: self.app.guarded(self.open_folder_browser)()) \
                if location["location_type"] == LocationType.CUSTOM_FOLDER else None
            rows.append(ft.ListTile(leading=ft.Icon(icon), title=ft.Text(primary), subtitle=ft.Text(secondary),
                                    trailing=trailing, on_click=lambda e, i=index: self.app.guarded(self.select_location)(i),
                                    bgcolor=ft.Colors.BLUE_200 if index == self.selected_index else ft.Colors.BLUE_50))
        self.location_list.controls = rows

    def _render_status(self):
        status = self.status_result["status"]
        self.status_icon.icon = STATUS_ICONS[status]
        self.status_text.value = tr._(STATUS_MESSAGES[status])
        if self.locations:
            self.info_box.value = format_authenticator_info(
                self.status_result,
                display_path=lambda p: format_path_for_display(p, self.app.storage_roots.home_dir,
                                                               self.app.storage_roots.external_app_root_prefix))
        for button in self.group_a:
            button.disabled = status is not False
        for button in self.group_b:
            button.disabled = status is not True
        if status is True and not self.status_result["has_secret"]:
            self.button_publish.disabled = self.button_authorizations.disabled = True

    # ------------------------------------------------------------ actions

    def open_creation_form(self):
        self.app.go(self.creation_screen)

    def open_folder_browser(self):
        roots = self.app.storage_roots
        if not is_folder_accessible(roots.external_app_root):
            self.app.toast(tr._("External storage is not accessible"))
            return
        start = self.app.custom_folder
        start = Path(start) if start and is_folder_accessible(start) else roots.external_app_root
        pick_path(self.app, start, self._on_folder_selected, select_folders=True)

    def _on_folder_selected(self, folder):
        self.app.custom_folder = str(folder)
        self.locations = list_authenticator_locations(self.app.storage_roots, self.app.custom_folder)
        index = next(i for i, loc in enumerate(self.locations) if loc["location_type"] == LocationType.CUSTOM_FOLDER)
        self.select_location(index)  # Auto-select the custom location row

    def _selected_dir(self):
        return self.status_result.get("authenticator_dir")

    def _on_service_error(self, exc):
        if isinstance(exc, ServiceError):
            self.app.show_dialog(tr._("Failure"), tr._(exc.msgid))
            return True
        return False

    def import_archive(self):
        exports_dir = self.app.storage_roots.exports_dir
        if not is_folder_accessible(exports_dir):
            self.app.toast(tr._("External storage is not accessible"))
            return
        target_dir = self._selected_dir()

        def _on_selected(archive_path):
            def _done(_):
                self.app.show_dialog(tr._("Import successful"), tr.f(
                    "Authenticator archive unpacked from {archive}, its integrity has not been checked though.",
                    archive=archive_path.name))
                self.refresh_locations(show_toast=False)
            self.app.run_in_background(lambda: import_authenticator(archive_path, target_dir), _done,
                                       self._on_service_error)

        pick_path(self.app, exports_dir, _on_selected, select_folders=False, extensions=[".zip"])

    def export_archive(self):
        authenticator_dir = self._selected_dir()

        def _confirmed():
            exports_dir = self.app.storage_roots.exports_dir
            if not is_folder_accessible(exports_dir, require_writable=True):
                self.app.toast(tr._("External storage is not accessible"))
                return
            self.app.run_in_background(
                lambda: export_authenticator(authenticator_dir, exports_dir),
                lambda archive: self.app.show_dialog(tr._("Export successful"), tr.f(
                    "Authenticator archive exported to {path}", path=format_path_for_display(
                        archive, self.app.storage_roots.home_dir, self.app.storage_roots.external_app_root_prefix))))

        self.app.show_dialog(
            tr._("Export authenticator"),
            tr._("The exported archive should be kept in a secure place.") + "\n" +
            tr._("It contains the gateway secret, which gives access to the authorization requests of this authenticator."),
            actions=[self.app.action_button(tr._("Confirm"), _confirmed)], close_label=tr._("Cancel"))

    def check_passphrase(self):
        authenticator_dir = self._selected_dir()
        field = passphrase_field(autofocus=True)

        def _run():
            passphrase = field.value
            self.app.run_in_background(lambda: check_authenticator_passphrase(authenticator_dir, passphrase),
                                       lambda result: self.app.show_dialog(*format_check_result(result)))

        field.on_submit = lambda e: self.app.run_dialog_action(_run)
        self.app.show_dialog(tr._("Sanity check"), content=ft.Column(
            [ft.Text(tr._("Test integrity and passphrase of authenticator")), field], tight=True),
            actions=[self.app.action_button(tr._("Check"), _run)], close_label=tr._("Cancel"))

    def destroy(self):
        authenticator_dir = self._selected_dir()  # Captured when the dialog opens

        def _confirmed():
            def _done(_):
                self.app.show_dialog(tr._("Deletion is over"),
                                     tr.f("Folder {path} has been properly removed.", path=authenticator_dir))
                self.refresh_locations(show_toast=False)

            def _error(exc):
                if self._on_service_error(exc):
                    return True
                if isinstance(exc, OSError):  # OI-19: clear message instead of a bare class name
                    self.app.show_dialog(tr._("Failure"), tr.f("Deletion failed: {error}", error=exc))
                    self.refresh_locations(show_toast=False)
                    return True
                return False
            self.app.run_in_background(lambda: destroy_authenticator(authenticator_dir), _done, _error)

        self.app.show_dialog(tr._("Destroy authenticator"),
                             tr._("Beware, this might make encrypted data using these keys impossible to decrypt."),
                             actions=[self.app.action_button(tr._("Confirm"), _confirmed)], close_label=tr._("Cancel"))

    def show_help(self):
        self.app.show_help(tr._("Authenticator management page"), "\n".join([
            tr._("On this page, you can manage your authenticators, which are actually digital keychains identified by unique IDs."),
            tr._("These keychains contain both public keys, which can be freely shared, and their corresponding private keys, protected by passphrases, which must be kept hidden."),
            "",
            tr._("Authenticators can be stored in your user profile or in a custom folder, especially at the root of removable devices."),
            tr._("You can initialize new authenticators from scratch, import/export them from/to ZIP archives, or check their integrity by providing their passphrases."),
            "",
            tr._("Note that if you destroy an authenticator, or lose its passphrase, the WitnessAngel recordings which used it as a trusted third party might not be decryptable anymore."),
        ]))
