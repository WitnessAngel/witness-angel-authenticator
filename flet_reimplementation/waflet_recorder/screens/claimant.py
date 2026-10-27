"""Claimant side of the revelation flow: submit form, request list, request details (02 §8)."""
import logging

import flet as ft

from waflet_components.app_base import Screen
from waflet_components.authenticator_services import ServiceError
from waflet_components.formatting import (
    COLON, TEXT_INDENT, format_authenticator_label, format_keypair_label, format_revelation_request_label, shorten_uid,
)
from waflet_components.i18n import tr
from waflet_components.screens.authenticator_revelation_requests import TAB_LABELS, SYMKEY_STATUS_LABELS
from waflet_components.widgets import top_bar, icon_action, readonly_text_box, banner, empty_state

from .. import claimant as claimant_logic
from ..claimant import DESCRIPTION_MIN_LENGTH, get_wa_device_uid

logger = logging.getLogger(__name__)


def format_submission_error(error):
    uid = shorten_uid(error["keystore_uid"])
    if error["kind"] == "authenticator_missing":
        return tr.f("Authenticator {uid} does not exist in sql storage", uid=uid)
    if error["kind"] == "key_missing":
        return tr.f("Public key needed does not exist in key storage in {uid} authenticator", uid=uid)
    return error["message"]


def format_submission_report(result):
    ok = len(result["ok"])
    text = tr.f("Successful requests: {ok} out of {total}", ok=ok, total=result["total"])
    if ok != result["total"]:
        text += "\n\n" + tr._("Error Report") + COLON() + "\n" + "\n".join(
            TEXT_INDENT + format_submission_error(e) for e in result["errors"])
    return text


class ClaimantRequestFormScreen(Screen):
    name = "claimant_revelation_request_creation_form"
    title = "Submit authorization request"
    parent_screen = "cryptainer_decryption_process"

    def __init__(self, app):
        super().__init__(app)
        self.description = ""  # Kept over refreshes

    def build(self):
        self.summary = readonly_text_box("", text_size=13)
        self.guardian_list = ft.Column(spacing=0)
        self.description_field = ft.TextField(label=tr._("Enter a description (minimum 10 characters):"), multiline=True,
                                              min_lines=3, value=self.description,
                                              on_change=lambda e: setattr(self, "description", e.control.value))
        self.checks = {}
        self.refresh()
        return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
            banner(tr._("Send an authorization request to remote key guardian")),
            ft.Text(tr._("Summary") + COLON(), weight=ft.FontWeight.BOLD), self.summary,
            ft.Text(tr._("Select key guardian(s) to query"), weight=ft.FontWeight.BOLD), self.guardian_list,
            ft.Text(tr._("Justify the authorization request"), weight=ft.FontWeight.BOLD), self.description_field,
            ft.Row([ft.Button(content=tr._("Send my authorization request"), icon=ft.Icons.SEND_OUTLINED, height=60,
                              on_click=lambda e: self.app.guarded(self.send)())], alignment=ft.MainAxisAlignment.CENTER)])

    def build_appbar(self):
        return top_bar(self.app, tr._(self.title), back=True, actions=[
            icon_action(ft.Icons.REFRESH, "Refresh", lambda e: self.app.guarded(self.refresh_and_update)()),
            icon_action(ft.Icons.HOME, "Back to home", lambda e: self.app.go("recorder_homepage"))])

    @property
    def names(self):
        return self.app.screens["cryptainer_storage_management"].selected_names()

    def refresh_and_update(self):
        self.refresh()
        self.app.page.update()

    def refresh(self):
        """Summary and checklist (all unticked); the description text is kept."""
        self.summary.value = "\n".join([tr._("Container(s) selected") + COLON(), *(TEXT_INDENT + n for n in self.names),
                                        "", tr._("Gateway url") + COLON() + self.app.gateway_url])
        self.checks = {}
        rows = []
        for status in self.app.decryption_statuses:
            uid = status["keystore_uid"]
            if status["trustee_type"] != "authenticator" or uid is None:
                continue
            checkbox = ft.Checkbox(value=False)
            self.checks[uid] = checkbox
            rows.append(ft.ListTile(leading=ft.Icon(ft.Icons.KEY), dense=True, trailing=checkbox, title=ft.Text(
                tr._("Authenticator") + " " + format_authenticator_label(status["owner"], uid), size=14)))
        self.guardian_list.controls = rows

    # ------------------------------------------------------------ submission (02 §8.1)

    def send(self):
        selected = [uid for uid, box in self.checks.items() if box.value]
        description = self.description_field.value or ""
        if not selected:
            return self.app.toast(tr._("Please select authenticators"))
        if len(description.strip()) < DESCRIPTION_MIN_LENGTH:
            return self.app.toast(tr._("Description must be at least 10 characters long."))
        app, names = self.app, list(self.names)

        def _submit():
            return claimant_logic.create_revelation_requests(
                app.open_cryptainer_storage(), app.pool, get_wa_device_uid(app.storage_roots), app.get_gateway_proxy(),
                names, selected, description)

        def _done(result):  # OI-75: navigation happens when the dialog is closed
            app.show_dialog(tr._("Operation Report"), format_submission_report(result),
                            on_close=lambda: app.go("cryptainer_storage_management"))

        def _error(exc):
            if isinstance(exc, ServiceError):
                app.snackbar(tr._(exc.msgid))
                return True
            return False

        app.run_in_background(_submit, _done, _error)


class ClaimantRequestListScreen(Screen):
    name = "claimant_revelation_request_management"
    title = "All authorization requests"
    parent_screen = "cryptainer_storage_management"

    def __init__(self, app):
        super().__init__(app)
        self.groups = []

    def build(self):
        self.list_view = ft.ListView(expand=True, spacing=0)
        self._render()
        return ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
            banner(tr._("View authorization requests submitted for each container")), self.list_view])

    def build_appbar(self):
        return top_bar(self.app, tr._(self.title), back=True, actions=[
            icon_action(ft.Icons.REFRESH, "Refresh", lambda e: self.app.guarded(self.fetch)()),
            icon_action(ft.Icons.HOME, "Back to home", lambda e: self.app.go("recorder_homepage"))])

    def on_enter(self):
        self.fetch()  # OI-76: at each visit, the call is cheap

    def fetch(self):
        app = self.app

        def _list():
            return claimant_logic.list_requests_by_cryptainer(app.get_gateway_proxy(), get_wa_device_uid(app.storage_roots))

        def _done(groups):
            self.groups, app.request_groups = groups, groups
            self._render()
            app.page.update()
            app.toast(tr._("Refreshed authorization requests"))

        def _error(exc):
            if isinstance(exc, ServiceError):  # The previous list is kept
                app.snackbar(tr._(exc.msgid))
                return True
            return False

        app.run_in_background(_list, _done, _error)

    def _render(self):
        if not self.groups:
            self.list_view.controls = [empty_state()]
            return
        self.list_view.controls = [
            ft.ListTile(leading=ft.Icon(ft.Icons.SWAP_HORIZ), title=ft.Text(
                "%s (ID %s)" % (g["cryptainer_name"], shorten_uid(g["cryptainer_uid"])), size=14),
                subtitle=ft.Text(tr._("Authorization requests") + COLON() + str(len(g["entries"]))),
                trailing=ft.IconButton(icon=ft.Icons.ARROW_FORWARD, tooltip=tr._("Details"),
                                       on_click=lambda e, g=g: self.app.guarded(self.open_detail)(g)))
            for g in self.groups]

    def open_detail(self, group):
        self.app.selected_request_group = group
        self.app.go("claimant_revelation_request_detail")


class ClaimantRequestDetailScreen(Screen):
    name = "claimant_revelation_request_detail"
    title = "Authorization request details"
    parent_screen = "claimant_revelation_request_management"

    def build(self):
        group = self.app.selected_request_group
        if not group:
            return ft.Column([banner(tr._("No information available"))])
        rows = [self._row(entry) for entry in group["entries"]]
        return ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
            banner(tr._("Container") + COLON() + "%s (ID %s)" % (group["cryptainer_name"], shorten_uid(group["cryptainer_uid"]))),
            ft.ListView(rows, expand=True, spacing=0)])

    def build_appbar(self):
        return top_bar(self.app, tr._(self.title), back=True, actions=[
            icon_action(ft.Icons.HOME, "Back to home", lambda e: self.app.go("recorder_homepage"))])

    @staticmethod
    def _owner(entry):
        return (entry.get("target_public_authenticator") or {}).get("keystore_owner") or tr._("Unknown")

    def _row(self, entry):
        status = entry["revelation_request_status"]
        title = format_revelation_request_label(entry["created_at"], entry["revelation_request_description"]) + " " + \
            tr.f("for {owner}", owner=self._owner(entry))
        return ft.ListTile(
            leading=ft.Icon(ft.Icons.KEY), dense=True, title=ft.Text(title, size=13),
            subtitle=ft.Text(tr._("Status") + COLON() + tr._(TAB_LABELS.get(status, status))),  # OI-87
            trailing=ft.IconButton(icon=ft.Icons.INFO_OUTLINE, tooltip=tr._("Details"),
                                   on_click=lambda e, entry=entry: self.app.guarded(self.show_summary)(entry)))

    def show_summary(self, entry):
        target = entry.get("target_public_authenticator") or {}
        key = entry["symkey_decryption_request"]["target_public_authenticator_key"]
        symkey_status = entry["symkey_decryption_request"]["symkey_decryption_status"]
        self.app.show_dialog(tr._("Authorization request summary"), "\n".join([
            tr._("Description") + COLON() + entry["revelation_request_description"], "",
            tr._("Authenticator") + COLON() + format_authenticator_label(target.get("keystore_owner"), target.get("keystore_uid")),
            tr._("Authenticator key") + COLON() + format_keypair_label(key["key_algo"], key["keychain_uid"]),
            tr._("Local key for response") + COLON() + format_keypair_label(
                entry["revelation_response_key_algo"], entry["revelation_response_keychain_uid"]), "",
            tr._("Symkey decryption status") + COLON() + tr._(SYMKEY_STATUS_LABELS.get(symkey_status, symkey_status))]))
