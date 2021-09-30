
import os

os.environ["WACLIENT_TYPE"] = "APPLICATION"  # IMPORTANT
from waguilib import kivy_presetup  # IMPORTANT
del kivy_presetup

from pathlib import Path

from kivy.core.window import Window
from kivymd.app import MDApp
from kivy.resources import resource_find, resource_add_path

from waguilib.android_helpers import patch_ctypes_module
from waguilib.i18n import tr
from waguilib.importable_settings import IS_ANDROID
from waguilib.locale import LOCALE_DIR as GUILIB_LOCALE_DIR  # DEFAULT LOCALE
from waguilib.key_codes import KeyCodes
from waguilib.widgets.popups import has_current_dialog, close_current_dialog
from waguilib.widgets.layout_helpers import activate_widget_debug_outline, load_layout_helper_widgets


if False:  #  ACTIVATE IF NEEDED TO DEBUG
    activate_widget_debug_outline()

load_layout_helper_widgets()

if IS_ANDROID:
    patch_ctypes_module()  # Necessary for wacryptolib


ROOT_DIR = Path(__file__).parent
LOCALE_DIR = ROOT_DIR / "locale"
tr.add_locale_dirs(LOCALE_DIR, GUILIB_LOCALE_DIR)

resource_add_path(ROOT_DIR)

class WaAuthenticatorApp(MDApp):

    kv_file = resource_find("wa_authenticator_gui.kv")
    icon = resource_find("icons/witness_angel_logo_blue_32x32.png")

    def __init__(self, **kwargs):
        self.title = "Witness Angel - Authenticator Manager"  # Untranslated
        super().__init__(**kwargs)
        Window.bind(on_keyboard=self.handle_back_button)

    def build(self):
        self.theme_cls.primary_palette = "Blue"
        #self.theme_cls.theme_style = "Dark"  # or "Light"
        self.theme_cls.primary_hue = "900"  # "500"

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
