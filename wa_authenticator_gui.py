
import os
from pathlib import Path

from kivy.core.window import Window
from kivy.properties import ListProperty
from kivy.resources import resource_find, resource_add_path
from kivy.metrics import dp

from wacomponents.default_settings import IS_IOS
from wacomponents.i18n import tr
from wacomponents.locale import LOCALE_DIR as GUILIB_LOCALE_DIR  # DEFAULT LOCALE DIR
from wacomponents.devices.keyboard_codes import KeyCodes
from wacomponents.screens.base import WAScreenName
from wacomponents.widgets.popups import has_current_dialog, close_current_dialog

from wacomponents.application.generic_gui import WaGenericGui

if False:  #  ACTIVATE TO DEBUG GUI
    from wacomponents.widgets.layout_components import activate_widget_debug_outline
    activate_widget_debug_outline()


ROOT_DIR = Path(__file__).parent

tr.add_locale_dirs(ROOT_DIR / "locale", GUILIB_LOCALE_DIR)

resource_add_path(ROOT_DIR)


class WaAuthenticatorApp(WaGenericGui):

    title_app_window = "Witness Angel - Authenticator"  # Untranslated

    @property
    def title_conf_panel(self):
        return tr._("Authenticator settings")

    kv_file = resource_find("wa_authenticator_gui.kv")
    icon = resource_find("icons/witness_angel_logo_blue_64x64.png")

    config_file_basename = "wakeygen_config.ini"

    # Format: [padding_left, padding_top, padding_right, padding_bottom].
    application_margins = ListProperty([0, 0, 0, 0])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(on_keyboard=self.handle_back_button)

    def on_start(self):
        super().on_start()
        main_screen = self.root.ids.screen_manager.get_screen(
                     WAScreenName.authenticator_management
                )
        assert hasattr(main_screen, "selected_custom_folder_path")
        main_screen.selected_custom_folder_path = self.get_custom_authenticator_dir()

        main_screen.bind(selected_custom_folder_path=self._handle_selected_custom_folder_path_changed)

        if IS_IOS:
            # We use this system: https://gist.github.com/Dirk-Sandberg/f5e9e4399002c69003d161e700e943a1
            from pyobjus import autoclass
            notch_detector = autoclass("NotchDetector").alloc().init()
            top_notch = notch_detector.getTopNotch()
            bottom_notch = notch_detector.getBottomNotch()
            left_notch = notch_detector.getLeftNotch()
            right_notch = notch_detector.getRightNotch()
            all_notches = [dp(left_notch), dp(top_notch), dp(right_notch), dp(bottom_notch)]
            print(">>>>>> IOS NOTCH CALLS RETURNED", all_notches)
            self.application_margins = all_notches

    def _handle_selected_custom_folder_path_changed(self, source, custom_authenticator_dir):
        """Persist any "currently selected custom folder" to config file"""
        self.config["keygen"]["custom_authenticator_dir"] = str(custom_authenticator_dir)
        self.save_config()

    def handle_back_button(self, widget, key, *args):

        if key == KeyCodes.ESCAPE:  # Also means BACK button on android

            # Close the current open popup or file browser, if any
            if has_current_dialog():
                close_current_dialog()
                return True

            # Go back to main page,
            if self.root.ids.screen_manager.current != WAScreenName.authenticator_management:
                self.root.ids.screen_manager.current = WAScreenName.authenticator_management
                return True

        # Else, let the key propagate (and app close if necessary)
        return False

    def get_wagateway_url(self):
        return self.config.get("keygen", "wagateway_url")

    def get_custom_authenticator_dir(self):
        raw_value = self.config.get("keygen", "custom_authenticator_dir").strip()
        return Path(raw_value).absolute() if raw_value else None  # Beware, "" must not be interpreted as "./"

    def get_config_schema_data(self):
        return [
            {
                "key": "wagateway_url",
                "type": "string_truncated",
                "title": tr._("Witness Angel Gateway URL"),
                "desc": tr._("Registry where authenticators can be published"),
                "section": "keygen",
            }
        ]

def main():
    WaAuthenticatorApp().run()
