"""Create screen "Create Authenticator" (02 §4). Uses `app.selected_authenticator_dir`."""
import logging

import flet as ft

from ..app_base import Screen
from ..authenticator_services import validate_creation_form, create_authenticator, GENERATED_KEYS_COUNT
from ..formatting import COLON, format_path_for_display
from ..i18n import tr
from ..widgets import top_bar, icon_action, passphrase_field

logger = logging.getLogger(__name__)


class AuthenticatorCreationFormScreen(Screen):
    name = "authenticator_creation_form"
    parent_screen = "authenticator_management"
    keypair_count = GENERATED_KEYS_COUNT

    def __init__(self, app):
        super().__init__(app)
        self.generating = False

    def build(self):
        self.generating = False  # Every entry resets the form (02 §4.1)
        roots = self.app.storage_roots
        target = format_path_for_display(self.app.selected_authenticator_dir, roots.home_dir, roots.external_app_root_prefix)
        self.owner_field = ft.TextField(label=tr._("User name"))
        self.passphrase_field = passphrase_field()
        self.hint_field = ft.TextField(label=tr._("Passphrase hint"))
        self.initialize_button = ft.OutlinedButton(content=tr._("Initialize"), height=50,
                                                   on_click=lambda e: self.app.guarded(self.submit)())
        self.status_label = ft.Text("")
        self.progress_bar = ft.ProgressBar(value=0, bar_height=10)
        return ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, scroll=ft.ScrollMode.AUTO, controls=[
            ft.Text(tr._("Authenticator") + COLON() + target),
            self.owner_field, self.passphrase_field, self.hint_field,
            ft.Container(height=20),
            ft.Row([ft.Container(self.initialize_button, expand=True)], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=20),
            self.status_label, self.progress_bar,
        ])

    def build_appbar(self):
        self.appbar = top_bar(self.app, tr._("Create Authenticator"), back=True,
                              actions=[icon_action(ft.Icons.HELP_OUTLINE, "Help", lambda e: self.show_help())])
        return self.appbar

    def can_go_back(self):
        return not self.generating  # OI-12: Back/ESC ignored while keys are generated

    def submit(self):
        values, error = validate_creation_form(self.owner_field.value, self.passphrase_field.value, self.hint_field.value)
        if error:
            self.app.show_dialog(tr._("Validation error"), tr._(error))
            return
        self._lock_form()
        authenticator_dir = self.app.selected_authenticator_dir

        def _progress(percent):
            self.app.call_on_ui(self._set_progress, percent)

        def _task():
            create_authenticator(authenticator_dir, keypair_count=self.keypair_count, progress_callback=_progress, **values)

        self.app.run_in_background(_task, on_success=lambda _: self._finish(True), on_error=lambda exc: self._finish(False))

    def _lock_form(self):
        self.generating = True
        self.app.page.views[-1].can_pop = False
        self.initialize_button.disabled = True
        self.passphrase_field.value = "***"
        self.passphrase_field.password = False
        for field in (self.owner_field, self.passphrase_field, self.hint_field):
            field.disabled = True
        self.appbar.leading.disabled = True
        for action in self.appbar.actions:
            action.disabled = True
        self.status_label.value = tr._("Please wait, generation of cryptographic keys might take a few minutes.")
        self.app.page.update()

    def _set_progress(self, percent):
        self.progress_bar.value = percent / 100
        self.app.page.update()

    def _finish(self, success):
        self.generating = False
        if success:
            title, text = tr._("Success"), tr._("Initialization successfully completed.")
        else:
            title, text = tr._("Failure"), tr._("Operation failed, check logs.")
        self.app.show_dialog(title, text, on_close=lambda: self.app.go(self.parent_screen))
        return True  # Error handled (logged by the service)

    def show_help(self):
        self.app.show_help(tr._("Authenticator creation page"), "\n".join([
            tr._("On this page, you can initialize an authenticator inside an empty folder; this authenticator actually consists in metadata files as well as a set of asymmetric keypairs."),
            tr._("To proceed, you have to input your user name or pseudo, a long passphrase (e.g. consisting of 4 different words), and a public hint to help your remember your passphrase later."),
            tr._("You should keep your passphrase somewhere safe (in a digital password manager, on a paper in a vault...), because if you forget any of its aspects (upper/lower case, accents, spaces...), there is no way to recover it."),
        ]))
