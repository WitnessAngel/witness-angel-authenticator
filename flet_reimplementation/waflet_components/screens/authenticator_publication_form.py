"""Publish screen "Publish authenticator" (02 §5). Uses `app.selected_authenticator_dir`,
`app.gateway_url` and `app.get_gateway_proxy()`."""
import logging

import flet as ft
from jsonrpc_requests import JSONRPCError
from wacryptolib.exceptions import AuthenticationError

from ..app_base import Screen
from ..authenticator_services import get_publication_status, publish_authenticator, check_publishable, ServiceError
from ..formatting import COLON, shorten_uid, indent_text, format_path_for_display
from ..i18n import tr
from ..widgets import top_bar, icon_action, readonly_text_box

logger = logging.getLogger(__name__)

GATEWAY_ERROR_MSGID = "Error querying gateway server, please check its url and your connectivity"


def format_publication_report(status, display_path, gateway_url):
    """Synchronization report text of 02 §5.2 (OI-33: plain comma-separated key lists)."""
    metadata = status["metadata"]
    published = status["remote_status"] == "PUBLISHED"
    inconsistent = bool(status["exceeding_keys"] or status["missing_keys"])
    if not published:
        message = tr._("The local authenticator does not exist in the remote repository.")
    elif inconsistent:
        message = tr._("An inconsistency has been detected between the local and remote authenticator.")
    else:
        message = tr._("The remote authenticator is up to date.")
    lines = [
        tr._("Authenticator path") + COLON() + display_path(status["authenticator_dir"]),
        tr._("User") + COLON() + metadata["keystore_owner"],
        tr._("ID") + COLON() + str(metadata["keystore_uid"]),
        "",
        tr._("Gateway") + COLON() + gateway_url,
        tr._("Remote status") + COLON() + (tr._("PUBLISHED") if published else tr._("NOT PUBLISHED")),
        tr._("Message") + COLON() + message,
    ]
    if published:
        lines += ["", tr._("Provide the Authenticator ID to users wanting to rely on you as a Key Guardian")]
    if published and inconsistent:
        keys = lambda items: ", ".join(shorten_uid(uid) for uid, _algo in items) or "-"
        lines += ["", tr._("Error details") + COLON().rstrip(), indent_text("\n".join([
            tr._("Exceeding key(s) in remote") + COLON() + keys(status["exceeding_keys"]),
            tr._("Missing key(s) in remote") + COLON() + keys(status["missing_keys"]),
        ]))]
    return "\n".join(lines)


class AuthenticatorPublicationFormScreen(Screen):
    name = "authenticator_publication_form"
    parent_screen = "authenticator_management"

    def build(self):
        self.report_box = readonly_text_box("", min_lines=14, expand=True, text_size=13)
        self.publish_button = ft.OutlinedButton(content=tr._("Publish"), height=50, disabled=True,
                                                on_click=lambda e: self.app.guarded(self.confirm_publication)())
        return ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[
            self.report_box, ft.Container(height=20),
            ft.Row([ft.Container(self.publish_button, expand=True)], alignment=ft.MainAxisAlignment.CENTER),
        ])

    def build_appbar(self):
        return top_bar(self.app, tr._("Publish authenticator"), back=True, actions=[
            icon_action(ft.Icons.REFRESH, "Refresh", lambda e: self.app.guarded(self.refresh_status)()),
            icon_action(ft.Icons.HELP_OUTLINE, "Help", lambda e: self.show_help()),
        ])

    def on_enter(self):
        self.app.guarded(self.refresh_status)()

    def _display_path(self, path):
        roots = self.app.storage_roots
        return format_path_for_display(path, roots.home_dir, roots.external_app_root_prefix)

    def refresh_status(self):
        authenticator_dir = self.app.selected_authenticator_dir
        gateway_url = self.app.gateway_url
        self.report_box.value = ""
        self.publish_button.disabled = True
        self.app.page.update()

        def _task():
            status = get_publication_status(authenticator_dir, self.app.get_gateway_proxy())
            status["authenticator_dir"] = authenticator_dir
            return status

        def _done(status):
            self.report_box.value = format_publication_report(status, self._display_path, gateway_url)
            self.publish_button.disabled = status["remote_status"] != "NOT_PUBLISHED"
            self.app.page.update()
            self.app.toast(tr._("Remote authenticator status has been updated"))

        self.app.run_in_background(_task, _done, self._on_gateway_error)

    def _on_gateway_error(self, exc):
        if isinstance(exc, AuthenticationError):
            msgid = "This authenticator ID is already published with another secret"
        elif isinstance(exc, (JSONRPCError, OSError)):
            msgid = GATEWAY_ERROR_MSGID
        elif isinstance(exc, ServiceError):
            msgid = exc.msgid
        else:
            return False
        logger.warning("Publication status/publish failed: %r", exc)
        self.report_box.value = tr._("No information available")
        self.app.page.update()
        self.app.snackbar(tr._(msgid))
        return True

    def confirm_publication(self):
        """OI-26 (decide): confirm the irreversible publication, naming the gateway."""
        try:
            check_publishable(self.app.selected_authenticator_dir)  # OI-28, OI-32
        except ServiceError as exc:
            self.app.show_dialog(tr._("Publish authenticator"), tr._(exc.msgid))
            return
        self.app.show_dialog(
            tr._("Publish authenticator"),
            tr.f("Publish the public keys of this authenticator to {gateway}? A published authenticator can't be modified or deleted.",
                 gateway=self.app.gateway_url),
            actions=[self.app.action_button(tr._("Publish"), self.publish)], close_label=tr._("Cancel"))

    def publish(self):
        authenticator_dir = self.app.selected_authenticator_dir
        self.publish_button.disabled = True  # OI-27
        self.app.run_in_background(lambda: publish_authenticator(authenticator_dir, self.app.get_gateway_proxy()),
                                   lambda _: self.refresh_status())

    def show_help(self):
        self.app.show_help(tr._("Authenticator publishing"), "\n".join([
            tr._("This page allows to publish the PUBLIC part of an authenticator to a remote Witness Angel Gateway, so that other users may import it to secure their recordings."),
            tr._("For now, a published authenticator can't be modified or deleted."),
            tr._("In case of incoherences between the keys locally and remotely stored, these errors are displayed here."),
        ]))
