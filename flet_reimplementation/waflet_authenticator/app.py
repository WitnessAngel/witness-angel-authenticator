"""Witness Angel Authenticator, Flet edition: app class, config, screen registration, settings schema."""
from pathlib import Path
from urllib.parse import urlparse

from waflet_components.app_base import WaFletApp, run_app
from waflet_components.authenticator_services import get_gateway_proxy
from waflet_components.i18n import tr
from waflet_components.screens.authenticator_creation_form import AuthenticatorCreationFormScreen
from waflet_components.screens.authenticator_management import AuthenticatorManagementScreen
from waflet_components.screens.authenticator_publication_form import AuthenticatorPublicationFormScreen
from waflet_components.screens.authenticator_revelation_requests import (
    AuthenticatorRevelationRequestManagementScreen, AuthenticatorRevelationRequestDetailScreen,
)
from waflet_components.storage import migrate_custom_dir

from . import PROGRAM_VERSION, locale_fr


class WaAuthenticatorApp(WaFletApp):
    title = "Witness Angel - Authenticator"  # Never translated
    config_filename = "wakeygen_config.ini"  # Historical name, same keys as 1.5
    config_defaults_path = Path(__file__).parent / "config_defaults.ini"
    settings_title = "Authenticator settings"
    app_catalogs = [locale_fr.CATALOG]
    screen_classes = [AuthenticatorManagementScreen, AuthenticatorCreationFormScreen, AuthenticatorPublicationFormScreen,
                      AuthenticatorRevelationRequestManagementScreen, AuthenticatorRevelationRequestDetailScreen]
    home_screen = AuthenticatorManagementScreen.name

    selected_authenticator_dir = None  # Owned by the main screen, read by the others
    selected_revelation_request = None

    def on_start(self):
        stored = self.config.get("authenticator", "custom_authenticator_dir")
        migrated = migrate_custom_dir(stored, self.storage_roots)
        if migrated != stored:
            self.config.set("authenticator", "custom_authenticator_dir", migrated)

    @property
    def custom_folder(self):
        value = self.config.get("authenticator", "custom_authenticator_dir")
        return str(Path(value).absolute()) if value else ""  # Empty is "none", never the cwd

    @custom_folder.setter
    def custom_folder(self, value):
        self.config.set("authenticator", "custom_authenticator_dir", value or "")  # Persisted immediately

    @property
    def gateway_url(self):
        return self.config.get("network", "wagateway_url")  # Read at every call: changes apply at once

    def get_gateway_proxy(self):
        return get_gateway_proxy(self.gateway_url)  # New proxy per operation, like 1.5

    def get_settings_schema(self):
        return [
            dict(type="string", title=tr._("Witness Angel Gateway URL"),
                 desc=tr._("Registry where authenticators can be published"), section="network", key="wagateway_url"),
            dict(type="title", title="Authenticator v%s by Witness Angel" % PROGRAM_VERSION),
        ]

    def validate_setting(self, section, key, value):
        if (section, key) == ("network", "wagateway_url"):
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.netloc:  # OI-47 (decide): https only
                return "The gateway URL must start with https://"
        return None


def main(**run_kwargs):
    return run_app(WaAuthenticatorApp, **run_kwargs)
