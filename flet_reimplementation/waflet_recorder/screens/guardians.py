"""Key Guardians screen (02 §5): list/select/delete imported guardians, import from USB and from the gateway."""
import logging
from uuid import UUID

import flet as ft

from waflet_components.app_base import Screen
from waflet_components.authenticator_services import ServiceError
from waflet_components.formatting import (
    COLON, format_keypair_label_with_privacy, format_authenticator_label,
)
from waflet_components.i18n import tr
from waflet_components.storage import list_usb_authdevices
from wacryptolib.authenticator import is_authenticator_initialized

from .. import guardians as guardian_logic
from waflet_components.widgets import top_bar, icon_action, empty_state, banner, selectable_row

logger = logging.getLogger(__name__)


class KeyGuardiansScreen(Screen):
    name = "foreign_keystore_management"
    title = "Key Guardians"
    top_level = True

    def __init__(self, app):
        super().__init__(app)
        self.guardians = []  # Last listing (dicts of guardians.list_guardians)

    def build(self):
        self.list_view = ft.ListView(expand=True, spacing=0)
        self.import_usb_button = ft.Button(content=tr._("Import from USB"), icon=ft.Icons.UPLOAD_FILE, expand=True,
                                           on_click=lambda e: self.app.guarded(self.import_from_usb)())
        self.import_web_button = ft.Button(content=tr._("Import from Web"), icon=ft.Icons.UPLOAD_FILE, expand=True,
                                           on_click=lambda e: self.app.guarded(self.ask_import_from_web)())
        self.delete_button = ft.Button(content=tr._("Delete"), icon=ft.Icons.DELETE_FOREVER, expand=True,
                                       on_click=lambda e: self.app.guarded(self.ask_delete)())
        self._render()
        return ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
            banner(tr._("Please select the key guardians used to secure recordings")),
            self.list_view,
            ft.Row([self.import_usb_button, self.import_web_button, self.delete_button]),
        ])

    def build_appbar(self):
        return top_bar(self.app, tr._(self.title), menu=True, actions=[
            icon_action(ft.Icons.REFRESH, "Refresh", lambda e: self.app.guarded(self.refresh)()),
            icon_action(ft.Icons.HOME, "Back to home", lambda e: self.app.go("recorder_homepage")),
        ])

    def on_enter(self):
        self.refresh()

    # ------------------------------------------------------------ list

    def refresh(self, show_toast=True):
        def _done(guardians):
            self.guardians = guardians
            self._render()
            self.app.page.update()
            if guardians and show_toast:
                self.app.toast(tr._("Refreshed imported key guardians"))
        self.app.run_in_background(lambda: guardian_logic.list_guardians(self.app.pool), _done)

    def selected_uids(self):
        return self.app.get_selected_guardian_uids()

    def _render(self):
        selected = set(self.selected_uids())
        if not self.guardians:
            self.list_view.controls = [empty_state()]
            return
        self.list_view.controls = [
            selectable_row(self.row_label(g), g["keystore_uid"] in selected,
                           lambda value, uid=g["keystore_uid"]: self.app.guarded(self.toggle)(uid, value),
                           lambda g=g: self.app.guarded(self.show_details)(g))
            for g in self.guardians]  # Already sorted by UID

    @staticmethod
    def row_label(guardian):
        label = tr._("User") + " " + format_authenticator_label(guardian["keystore_owner"], guardian["keystore_uid"])
        return label + (" (" + tr._("corrupted") + ")" if guardian["corrupted"] else "")

    def toggle(self, uid, checked):
        """Saved at once, so that the service sees it (02 §5.2)."""
        uids = [u for u in self.selected_uids() if u != uid]
        if checked:
            uids.append(uid)
        self.app.settings.set_selected_keyguardians(uids)
        self.app.refresh_checkup()

    def select(self, uids):
        """Add `uids` to the recording guardians (auto-selection of imports)."""
        current = self.selected_uids()
        self.app.settings.set_selected_keyguardians(current + [UUID(str(u)) for u in uids if UUID(str(u)) not in current])
        self.app.refresh_checkup()

    def show_details(self, guardian):
        lines = [tr._("Type") + COLON() + "AUTHENTICATOR", ""]
        if guardian["corrupted"]:
            lines.append(tr._("This key guardian is corrupted") + COLON() + str(guardian["error"]))
        for index, keypair in enumerate(guardian["keypairs"], 1):
            lines.append(tr._("Key n°") + str(index) + COLON() + format_keypair_label_with_privacy(
                keypair["key_algo"], keypair["keychain_uid"], keypair["private_key_present"]))
        self.app.show_dialog(tr.f("Key Guardian {owner}", owner=guardian["keystore_owner"] or tr._("Unknown")),
                             "\n".join(lines))

    # ------------------------------------------------------------ import from USB (02 §5.4)

    def import_from_usb(self):
        platform = self.app.storage_roots.platform

        def _detect():
            devices = list_usb_authdevices(platform)
            return devices, [d["authenticator_dir"] for d in devices if is_authenticator_initialized(d["authenticator_dir"])]

        def _detected(result):
            devices, initialized = result
            if not devices:
                return self.app.toast(tr._("No connected authentication devices found"))
            if not initialized:
                return self.app.toast(tr._("No initialized authentication devices found"))
            self.app.show_dialog(
                tr._("Import keys from USB drives"), tr._("Do you want to import the private keys (passphrase-protected) as well?"),
                actions=[self.app.action_button(tr._("Yes"), lambda: self.do_import_from_usb(initialized, True)),
                         self.app.action_button(tr._("No"), lambda: self.do_import_from_usb(initialized, False))],
                close_label=tr._("Cancel"))

        self.app.run_in_background(_detect, _detected)

    def do_import_from_usb(self, authenticator_dirs, include_private_keys):
        def _done(result):
            self.app.toast(tr.f("{count} new authenticators imported, {updated} updated, {corrupted} skipped because corrupted",
                                count=len(result["new"]), updated=len(result["updated"]), corrupted=result["skipped"]))
            self.select(result["new"])  # Updated ones keep their tick state
            self.refresh(show_toast=False)

        self.app.run_in_background(lambda: guardian_logic.import_from_authdevices(
            self.app.pool, authenticator_dirs, include_private_keys), _done)

    # ------------------------------------------------------------ import from the gateway (02 §5.5)

    def ask_import_from_web(self):
        field = ft.TextField(label=tr._("Authenticator ID"), autofocus=True)
        do_import = lambda: self.import_from_web(field.value)
        field.on_submit = lambda e: self.app.run_dialog_action(do_import)
        self.app.show_dialog(tr._("Import keys from web gateway"), content=ft.Column(
            [ft.Text(tr._("Enter the ID of the authenticator:")), field], tight=True),
            actions=[self.app.action_button(tr._("Import"), do_import)], close_label=tr._("Cancel"))

    def import_from_web(self, text):
        def _done(info):
            self.app.toast(tr._("Authentication device(s) updated"))
            self.select([info["keystore_uid"]])
            self.refresh(show_toast=False)
            self.app.show_dialog(tr.f("Import result: {result}", result=tr._("Success")),
                                 tr._("Authenticator has been imported successfully"))

        def _error(exc):
            if isinstance(exc, ServiceError):
                self.app.show_dialog(tr.f("Import result: {result}", result=tr._("Failure")), tr._(exc.msgid))
                return True
            return False  # Network or JSON-RPC error: the "Abnormal error" snackbar, like 1.0

        self.app.run_in_background(
            lambda: guardian_logic.import_from_gateway(self.app.pool, self.app.get_gateway_proxy(), text), _done, _error)

    # ------------------------------------------------------------ delete (02 §5.6, OI-49, OI-50, OI-53)

    def ask_delete(self):
        uids = self.selected_uids()
        if not uids:
            return self.app.toast(tr._("Please select key guardians to remove"))
        by_uid = {g["keystore_uid"]: g for g in self.guardians}
        names = "\n".join("- " + self.row_label(by_uid[u]) if u in by_uid else "- %s" % u for u in uids)  # OI-50
        self.app.show_dialog(
            tr._("Key guardian removal confirmation"),
            tr.f("Are you sure you want to remove {count} key guardian(s)?", count=len(uids)) + "\n\n" + names,
            actions=[self.app.action_button(tr._("Confirm removal"), lambda: self.delete(uids))],
            close_label=tr._("Cancel"))

    def delete(self, uids):
        # The ticked guardians secure the recordings: refuse while the service records (OI-53)
        protected = uids if self.app.recording else ()

        def _done(result):
            remaining = [u for u in self.selected_uids() if u not in result["deleted"]]
            self.app.settings.set_selected_keyguardians(remaining)  # Iterates over copies: no leftover (OI-49)
            self.app.refresh_checkup()
            self.app.toast(tr._("Selected imported authentication devices were deleted"))
            self.refresh(show_toast=False)

        def _error(exc):
            if isinstance(exc, ServiceError):
                self.app.show_dialog(tr._("Key guardian removal confirmation"), tr._(exc.msgid))
                return True
            return False

        self.app.run_in_background(lambda: guardian_logic.delete_guardians(self.app.pool, uids, protected), _done, _error)
