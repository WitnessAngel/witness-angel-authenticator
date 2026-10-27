"""Prepare decryption and Decryption report screens (02 §7)."""
import logging

import flet as ft

from waflet_components.app_base import Screen
from waflet_components.formatting import (
    COLON, format_keypair_label, format_keypair_label_with_privacy, format_path_for_display, format_trustee_label,
)
from waflet_components.i18n import tr
from waflet_components.widgets import top_bar, icon_action, passphrase_field, readonly_text_box, banner, empty_state

from .. import decryption as decryption_logic
from ..claimant import get_wa_device_uid
from ..settings import is_valid_gateway_url

logger = logging.getLogger(__name__)


class DecryptionProcessScreen(Screen):
    name = "cryptainer_decryption_process"
    title = "Prepare decryption"
    parent_screen = "cryptainer_storage_management"

    def __init__(self, app):
        super().__init__(app)
        self.statuses = []

    @property
    def names(self):
        return self.app.screens["cryptainer_storage_management"].selected_names()

    def build(self):
        self.container_list = ft.ListView(expand=True, spacing=0)
        self.guardian_list = ft.ListView(expand=True, spacing=0)
        self.remote_button = ft.Button(content=tr._("Request remote authorization"), icon=ft.Icons.SETTINGS_REMOTE, expand=True,
                                       disabled=True, on_click=lambda e: self.app.guarded(self.open_request_form)())
        self.report_button = ft.Button(content=tr._("Last decryption report"), icon=ft.Icons.FORMAT_LIST_BULLETED, expand=True,
                                       disabled=self.app.last_decryption_results is None,
                                       on_click=lambda e: self.app.go("cryptainer_decryption_result"))
        self._render_containers()
        self._render_guardians()
        return ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
            ft.Text(tr._("Containers selected for decryption"), weight=ft.FontWeight.BOLD),
            ft.Container(self.container_list, expand=2),
            ft.Text(tr._("Summary of related key guardians"), weight=ft.FontWeight.BOLD),
            ft.Container(self.guardian_list, expand=3),
            ft.Row([ft.Button(content=tr._("Add a passphrase"), icon=ft.Icons.KEY, expand=True,
                              on_click=lambda e: self.app.guarded(self.ask_passphrase)()),
                    ft.Button(content=tr._("Attempt decryption"), icon=ft.Icons.REMOVE_RED_EYE_OUTLINED, expand=True,
                              on_click=lambda e: self.app.guarded(self.attempt_decryption)())], wrap=True),
            ft.Row([self.remote_button, self.report_button], wrap=True),
        ])

    def build_appbar(self):
        return top_bar(self.app, tr._(self.title), back=True, actions=[
            icon_action(ft.Icons.REFRESH, "Refresh", lambda e: self.app.guarded(self.refresh)()),
            icon_action(ft.Icons.HOME, "Back to home", lambda e: self.app.go("recorder_homepage"))])

    def on_enter(self):
        self.refresh()

    # ------------------------------------------------------------ lists

    def refresh(self):
        names = list(self.names)

        def _status():
            return decryption_logic.get_trustee_status(self.app.open_cryptainer_storage(), self.app.pool, names,
                                                       self.app.passphrase_mapper)

        def _done(statuses):
            self.statuses = [s for s in statuses if s["trustee_type"] == "authenticator"]  # Others are ignored
            self.app.decryption_statuses = self.statuses
            self._render_containers()
            self._render_guardians()
            self.app.page.update()
            self.app.toast(tr._("Refreshed concerned containers"))

        def _error(exc):
            logger.warning("Cannot compute trustee status: %r", exc)
            self.statuses, self.app.decryption_statuses = [], []
            self._render_guardians()
            self.app.snackbar(tr._("This container cannot be read") + COLON() + (str(exc) or type(exc).__name__)[:200])
            return True

        self.app.run_in_background(_status, _done, _error)

    def _render_containers(self):
        self.container_list.controls = [ft.Text("N° %d%s%s" % (i, COLON(), name), size=13, selectable=True)
                                        for i, name in enumerate(self.names, 1)]

    def _render_guardians(self):
        self.remote_button.disabled = not self.statuses
        if not self.statuses:
            self.guardian_list.controls = [empty_state()]
            return
        self.guardian_list.controls = [self._row(s) for s in self.statuses]

    def _row(self, status):
        found, passphrase_set = status["found"], status["passphrase_set"]
        if not found:
            keys_text = tr._("Private keys needed were not found")
        elif status["missing_private_keys"]:
            keys_text = tr._("Private key(s) missing locally") + COLON() + ", ".join(
                format_keypair_label(k["key_algo"], k["keychain_uid"]) for k in status["missing_private_keys"])
        else:
            keys_text = tr._("Private keys needed for decryption are present")
        line2 = tr.f("Status: {found}, passphrase: {passphrase}", found=tr._("FOUND") if found else tr._("NOT FOUND"),
                     passphrase=tr._("SET") if passphrase_set else tr._("NOT SET"))
        return ft.ListTile(
            leading=ft.Icon(ft.Icons.KEY), is_three_line=True, dense=True,
            title=ft.Text(tr._("Key guardian") + COLON() + format_trustee_label(
                status["owner"], status["keystore_uid"], status["trustee_type"]), size=13),
            subtitle=ft.Text(line2 + "\n" + keys_text, size=12),
            trailing=ft.IconButton(icon=ft.Icons.INFO_OUTLINE, tooltip=tr._("Details"),
                                   on_click=lambda e, s=status: self.app.guarded(self.show_keypairs)(s)))

    def show_keypairs(self, status):
        missing = {(k["keychain_uid"], k["key_algo"]) for k in status["missing_private_keys"]}
        lines = [tr.f("Keypair n°{index}", index=i) + COLON() + format_keypair_label_with_privacy(
            k["key_algo"], k["keychain_uid"], (k["keychain_uid"], k["key_algo"]) not in missing)
            for i, k in enumerate(status["needed_keys"], 1)]
        self.app.show_dialog(tr._("Keypairs used"), "\n".join(lines))

    # ------------------------------------------------------------ passphrase (02 §7.1.1)

    def ask_passphrase(self):
        field = passphrase_field(autofocus=True)  # OI-67: masked
        check = lambda: self.check_passphrase(field.value)
        field.on_submit = lambda e: self.app.run_dialog_action(check)
        self.app.show_dialog(tr._("Add passphrase"), content=ft.Column(
            [ft.Text(tr._("Enter the passphrase for one of the key guardians")), field], tight=True),
            actions=[self.app.action_button(tr._("Check"), check)], close_label=tr._("Cancel"))

    def check_passphrase(self, passphrase):
        statuses = list(self.statuses)

        def _done(result):
            outcome = result["result"]
            word = {"recognized": tr._("Success"), "no_match": tr._("Failure"), "already_entered": tr._("Information")}[outcome]
            text = {"recognized": tr._("Passphrase recognized"),
                    "no_match": tr._("Passphrase doesn't match any relevant private key"),
                    "already_entered": tr._("This passphrase was already entered")}[outcome]  # OI-66: never echoed
            self.app.show_dialog(tr.f("Validation result: {result}", result=word), text)
            if outcome == "recognized":
                self.refresh_status_only()

        self.app.run_in_background(lambda: decryption_logic.check_passphrase(
            self.app.pool, statuses, self.app.passphrase_mapper, passphrase), _done)

    def refresh_status_only(self):
        for status in self.statuses:
            status["passphrase_set"] = self.app.passphrase_mapper.has_passphrase_for(status["trustee_id"])
        self._render_guardians()
        self.app.page.update()

    # ------------------------------------------------------------ decryption (02 §7.2)

    def attempt_decryption(self):
        app = self.app
        exports_dir = app.storage_roots.exports_dir
        if exports_dir is None:  # OI-70: no external folder
            return app.snackbar(tr._("No export folder is available on this device"))
        names = list(self.names)
        gateway_url = app.gateway_url if is_valid_gateway_url(app.gateway_url) else None

        def _decrypt():
            return decryption_logic.decrypt_cryptainers(
                app.open_cryptainer_storage(), app.pool, names, app.passphrase_mapper, exports_dir, gateway_url,
                get_wa_device_uid(app.storage_roots))

        def _done(results):
            app.last_decryption_results = results
            app.go("cryptainer_decryption_result")
            if not any(r["success"] for r in results):
                app.snackbar(tr._("All decryptions failed, see reports"))

        app.run_in_background(_decrypt, _done)

    def open_request_form(self):
        self.app.go("claimant_revelation_request_creation_form")


class DecryptionResultScreen(Screen):
    name = "cryptainer_decryption_result"
    title = "Decryption report"
    parent_screen = "cryptainer_decryption_process"

    def build(self):
        roots = self.app.storage_roots
        results = self.app.last_decryption_results or []
        count = sum(1 for r in results if r["success"])
        export_dir = format_path_for_display(roots.exports_dir, roots.home_dir, roots.external_app_root_prefix)
        controls = [banner(tr._("Export folder") + COLON() + export_dir),
                    ft.Container(ft.Text(tr.f("{count} out of {total} container(s) have been decrypted",
                                              count=count, total=len(results)), size=18, weight=ft.FontWeight.BOLD),
                                 alignment=ft.Alignment.CENTER, padding=10)]
        for result in results:
            status = tr._("SUCCESS") if result["success"] else tr._("FAILURE")
            report = decryption_logic.format_operation_report(result["report"]) if len(result["report"]) else \
                tr._("No errors/warnings when decrypting the container")
            controls += [
                ft.Container(ft.Text(tr.f("Decryption status for {name}: {status}", name=result["name"], status=status),
                                     size=13, weight=ft.FontWeight.BOLD), bgcolor=ft.Colors.GREY_300,
                             alignment=ft.Alignment.CENTER, padding=6),
                readonly_text_box(report, text_size=12)]
            if result["report_path"]:
                controls.append(ft.Text(tr.f("Report saved to {path}", path=format_path_for_display(
                    result["report_path"], roots.home_dir, roots.external_app_root_prefix)), size=11, italic=True))
        return ft.Column(controls, expand=True, scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    def build_appbar(self):
        return top_bar(self.app, tr._(self.title), back=True, actions=[
            icon_action(ft.Icons.HOME, "Back to home", lambda e: self.app.go("recorder_homepage"))])
