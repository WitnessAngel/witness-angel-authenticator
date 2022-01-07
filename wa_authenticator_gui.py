
import os


from wacomponents.application._app_presetup import _presetup_app_environment
os.environ["WACLIENT_TYPE"] = "APPLICATION"  # IMPORTANT before anything
_presetup_app_environment(setup_kivy=True)


from pathlib import Path

from kivy.core.window import Window
from kivy.resources import resource_find, resource_add_path

from wacomponents.i18n import tr
from wacomponents.locale import LOCALE_DIR as GUILIB_LOCALE_DIR  # DEFAULT LOCALE DIR
from wacomponents.devices.keyboard_codes import KeyCodes
from wacomponents.widgets.popups import has_current_dialog, close_current_dialog

from wacomponents.application.generic_gui import WaGenericGui

if False:  #  ACTIVATE TO DEBUG GUI
    from wacomponents.widgets.layout_components import activate_widget_debug_outline
    activate_widget_debug_outline()


ROOT_DIR = Path(__file__).parent

tr.add_locale_dirs(ROOT_DIR / "locale", GUILIB_LOCALE_DIR)

resource_add_path(ROOT_DIR)


class WaAuthenticatorApp(WaGenericGui):

    title = "Witness Angel - Authenticator Manager"  # Untranslated
    kv_file = resource_find("wa_authenticator_gui.kv")
    icon = resource_find("icons/witness_angel_logo_blue_32x32.png")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(on_keyboard=self.handle_back_button)

    def handle_back_button(self, widget, key, *args):

        if key == KeyCodes.ESCAPE:  # Also means BACK button on android

            # Close the current open popup or file browser, if any
            if has_current_dialog():
                close_current_dialog()
                return True

            # Go back to main page,
            if self.root.ids.screen_manager.current != "authenticator_selector_screen":
                self.root.ids.screen_manager.current = "authenticator_selector_screen"
                return True

            # Else, let the key propagate (and app close if necessary)
