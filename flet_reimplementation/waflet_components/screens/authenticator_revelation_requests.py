"""Authorization requests list and detail screens (02 §6). Use `app.selected_authenticator_dir`,
`app.get_gateway_proxy()`; the list hands the chosen request to the detail screen via `app.selected_revelation_request`."""
import logging

import flet as ft
from jsonrpc_requests import JSONRPCError
from wacryptolib.exceptions import KeystoreDoesNotExist, AuthenticationError, KeyLoadingError

from ..app_base import Screen
from ..authenticator_services import (
    list_revelation_requests, accept_revelation_request, reject_revelation_request,
    check_revelation_request_acceptable, ServiceError, EmptyRevelationRequestError, REVELATION_REQUEST_STATUSES,
)
from ..formatting import COLON, format_revelation_request_label, format_authenticator_label, format_keypair_label, shorten_uid
from ..i18n import tr
from ..widgets import top_bar, icon_action, passphrase_field, readonly_text_box

logger = logging.getLogger(__name__)

TAB_LABELS = {"PENDING": "Pending", "ACCEPTED": "Accepted", "REJECTED": "Rejected"}
SYMKEY_STATUS_LABELS = {"PENDING": "Pending", "DECRYPTED": "Decrypted", "PRIVATE_KEY_MISSING": "Private key missing",
                        "CORRUPTED": "Corrupted", "METADATA_MISMATCH": "Metadata mismatch"}


def map_listing_error(exc):
    """Snackbar msgid for an expected listing failure, else None (02 §6.1)."""
    if isinstance(exc, KeystoreDoesNotExist):
        return "Authenticator does not exist in remote registry"
    if isinstance(exc, AuthenticationError):
        return "The keystore secret of authenticator is not valid"
    if isinstance(exc, (JSONRPCError, OSError)):
        return "Error querying gateway server, please check its url and your connectivity"
    if isinstance(exc, ServiceError):
        return exc.msgid
    return None


def format_request_summary(request):
    """Detail summary box (02 §6.2), with translated status (OI-51)."""
    target = request["target_public_authenticator"]
    return "\n".join([
        tr._("Status") + COLON() + tr._(TAB_LABELS.get(request["revelation_request_status"], request["revelation_request_status"])),
        tr._("Authenticator") + COLON() + format_authenticator_label(target["keystore_owner"], target["keystore_uid"]),
        tr._("Description") + COLON() + request["revelation_request_description"],
        tr._("Local key for response") + COLON() + format_keypair_label(request["revelation_response_key_algo"],
                                                                          request["revelation_response_keychain_uid"]),
    ])


def format_symkey_request_info(symkey_request):
    key = symkey_request["target_public_authenticator_key"]
    status = symkey_request["symkey_decryption_status"]
    return "\n".join([
        tr._("Concerned authenticator key") + COLON() + format_keypair_label(key["key_algo"], key["keychain_uid"]),
        tr._("Cryptainer metadata") + COLON() + str(symkey_request["cryptainer_metadata"]),
        tr._("Decryption status") + COLON() + tr._(SYMKEY_STATUS_LABELS.get(status, status)),
    ])


class AuthenticatorRevelationRequestManagementScreen(Screen):
    name = "authenticator_revelation_request_management"
    parent_screen = "authenticator_management"
    detail_screen = "authenticator_revelation_request_detail"

    def __init__(self, app):
        super().__init__(app)
        self.requests_by_status = {status: [] for status in REVELATION_REQUEST_STATUSES}
        self.success_toast = None  # OI-49: a pending toast replaces the list's own "updated" toast

    def build(self):
        self.tab_lists = {status: ft.ListView(expand=True) for status in REVELATION_REQUEST_STATUSES}
        self.tabs = ft.Tabs(length=3, selected_index=0, expand=True, content=ft.Column(expand=True, controls=[
            ft.TabBar(scrollable=False, tabs=[ft.Tab(label=tr._(TAB_LABELS[s])) for s in REVELATION_REQUEST_STATUSES]),
            ft.TabBarView(expand=True, controls=[self.tab_lists[s] for s in REVELATION_REQUEST_STATUSES]),
        ]))
        self._render()
        return self.tabs

    def build_appbar(self):
        return top_bar(self.app, tr._("Authorization requests"), back=True, actions=[
            icon_action(ft.Icons.REFRESH, "Refresh", lambda e: self.app.guarded(self.fetch)()),
            icon_action(ft.Icons.HELP_OUTLINE, "Help", lambda e: self.show_help()),
        ])

    def on_enter(self):
        self.app.guarded(self.fetch)()

    def _render(self):
        for status, listview in self.tab_lists.items():
            requests = self.requests_by_status[status]
            if not requests:
                listview.controls = [ft.Container(ft.Text(tr._("Empty"), size=20), alignment=ft.Alignment.CENTER,
                                                  padding=40)]
                continue
            listview.controls = [
                ft.ListTile(  # OI-44 (decide): the whole row opens the detail
                    leading=ft.Icon(ft.Icons.SWAP_HORIZ),
                    title=ft.Text(format_revelation_request_label(r["created_at"], r["revelation_request_description"])),
                    subtitle=ft.Text(tr.f("Symkey decryption requests: {count}", count=len(r["symkey_decryption_requests"]))),
                    trailing=ft.Icon(ft.Icons.ARROW_FORWARD),
                    on_click=lambda e, r=r: self.app.guarded(self.open_detail)(r))
                for r in requests]

    def fetch(self):
        self.tabs.selected_index = 0
        authenticator_dir = self.app.selected_authenticator_dir

        def _done(grouped):
            self.requests_by_status = grouped
            self._render()
            self.app.page.update()
            self.app.toast(self.success_toast or tr._("Authorization requests were updated"))
            self.success_toast = None

        def _error(exc):
            self.success_toast = None
            msgid = map_listing_error(exc)
            if msgid is None:
                return False
            self.requests_by_status = {status: [] for status in REVELATION_REQUEST_STATUSES}
            self._render()
            self.app.page.update()
            self.app.snackbar(tr._(msgid))
            return True

        self.app.run_in_background(lambda: list_revelation_requests(authenticator_dir, self.app.get_gateway_proxy()),
                                   _done, _error)

    def open_detail(self, request):
        self.app.selected_revelation_request = request
        self.app.go(self.detail_screen)

    def show_help(self):
        self.app.show_help(tr._("Authorization requests page"), "\n".join([
            tr._("This page summarizes the authorization requests that have been sent to the selected authenticator, by people wishing to decrypt some of their containers."),
            tr._("These requests can be freely rejected. Else, to accept them, you must input your passphrase, which will be used to load your private keys and generate authorization tokens for the requester."),
            tr._("For now, it is not possible to change the status of a request which has been accepted or rejected."),
        ]))


class AuthenticatorRevelationRequestDetailScreen(Screen):
    name = "authenticator_revelation_request_detail"
    parent_screen = "authenticator_revelation_request_management"

    def build(self):
        request = self.app.selected_revelation_request
        pending = request["revelation_request_status"] == "PENDING"
        empty_message = None
        try:
            if pending:
                check_revelation_request_acceptable(request)
        except EmptyRevelationRequestError as exc:  # OI-03 (c): Accept disabled, Reject stays available
            empty_message = tr._(exc.msgid)
        except ServiceError:
            pass  # Unsupported algorithm: refused with a dialog on Accept
        rows = [ft.ListTile(leading=ft.Icon(ft.Icons.KEY),
                            title=ft.Text(tr.f("Key of container {uid}", uid=shorten_uid(s["cryptainer_uid"]))),
                            subtitle=ft.Text(s["cryptainer_name"]),
                            trailing=ft.Icon(ft.Icons.INFO_OUTLINE),
                            on_click=lambda e, s=s: self.app.show_dialog(tr._("Symkey decryption request"),
                                                                         format_symkey_request_info(s)))
                for s in request["symkey_decryption_requests"]]
        self.accept_button = ft.Button(content=tr._("Accept"), icon=ft.Icons.CHECK, expand=True,
                                       disabled=not pending or bool(empty_message),
                                       on_click=lambda e: self.app.guarded(self.ask_accept)())
        self.reject_button = ft.Button(content=tr._("Reject"), icon=ft.Icons.CLOSE, expand=True, disabled=not pending,
                                       on_click=lambda e: self.app.guarded(self.ask_reject)())
        return ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, scroll=ft.ScrollMode.AUTO, controls=[
            ft.Container(ft.Text(format_revelation_request_label(request["created_at"], request["revelation_request_description"]),
                                 weight=ft.FontWeight.BOLD),
                         height=40, bgcolor=ft.Colors.BLUE_50, padding=ft.Padding.symmetric(horizontal=10),
                         alignment=ft.Alignment.CENTER_LEFT),
            readonly_text_box(format_request_summary(request), text_size=13),
            *rows,
            *([ft.Text(empty_message, italic=True)] if empty_message else []),
            ft.Row([self.accept_button, self.reject_button]),
        ])

    def build_appbar(self):
        return top_bar(self.app, tr._("Authorization request details"), back=True)

    def _back_to_list(self, toast_msgid):
        self.app.screens[self.parent_screen].success_toast = tr._(toast_msgid)
        self.app.go(self.parent_screen)

    def ask_accept(self):
        request = self.app.selected_revelation_request
        try:
            check_revelation_request_acceptable(request)
        except ServiceError as exc:
            self.app.show_dialog(tr._("Accept"), tr._(exc.msgid))
            return
        field = passphrase_field()
        accept = lambda: self.accept(field.value)
        field.on_submit = lambda e: self.app.run_dialog_action(accept)
        self.app.show_dialog(tr._("Enter your authenticator passphrase"), content=ft.Column(
            [ft.Text(tr._("This will allow unmasking the requested Symkey parts")), field], tight=True),
            actions=[self.app.action_button(tr._("Accept"), accept)], close_label=tr._("Cancel"))

    def accept(self, passphrase):
        request, authenticator_dir = self.app.selected_revelation_request, self.app.selected_authenticator_dir

        def _error(exc):
            if isinstance(exc, KeyLoadingError):  # Wrong passphrase: nothing was sent
                self.app.snackbar(tr._("Loading of authenticator private key failed (wrong passphrase?)"))
                return True
            if isinstance(exc, ServiceError):
                self.app.show_dialog(tr._("Accept"), tr._(exc.msgid))
                return True
            return False

        self.app.run_in_background(
            lambda: accept_revelation_request(authenticator_dir, request, passphrase, self.app.get_gateway_proxy()),
            lambda _: self._back_to_list("The decryption request was accepted"), _error)

    def ask_reject(self):
        self.app.show_dialog(tr._("Do you want to reject this request?"), "",
                             actions=[self.app.action_button(tr._("Reject"), self.reject)], close_label=tr._("Cancel"))

    def reject(self):
        request, authenticator_dir = self.app.selected_revelation_request, self.app.selected_authenticator_dir
        self.app.run_in_background(
            lambda: reject_revelation_request(authenticator_dir, request, self.app.get_gateway_proxy()),
            lambda _: self._back_to_list("The authorization request was rejected"))
