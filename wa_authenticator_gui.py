
import os

os.environ["WACLIENT_TYPE"] = "APPLICATION"  # IMPORTANT
from waguilib import kivy_presetup  # IMPORTANT
del kivy_presetup

from pathlib import Path

from kivymd.app import MDApp
from kivy.resources import resource_find, resource_add_path

from waguilib.i18n import tr
from waguilib.locale import LOCALE_DIR as GUILIB_LOCALE_DIR  # DEFAULT LOCALE


if False:  #  ACTIVATE IF NEEDED TO DEBUG
    from waguilib.widgets.layout_helpers import activate_widget_debug_outline
    activate_widget_debug_outline()


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

    def build(self):
        self.theme_cls.primary_palette = "Blue"
        #self.theme_cls.theme_style = "Dark"  # or "Light"
        self.theme_cls.primary_hue = "900"  # "500"
