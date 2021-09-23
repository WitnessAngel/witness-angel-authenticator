
import os

os.environ["WACLIENT_TYPE"] = "APPLICATION"  # IMPORTANT
from waguilib import kivy_presetup  # IMPORTANT
del kivy_presetup

import sys
from kivymd.app import MDApp
from waguilib.i18n import tr
from waguilib.locale import LOCALE_DIR as GUILIB_LOCALE_DIR  # DEFAULT LOCALE

# IF NEEDED TO DEBUG
#activate_widget_debug_outline()


LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")
tr.add_locale_dirs(LOCALE_DIR, GUILIB_LOCALE_DIR)


class MainApp(MDApp):

    kv_file = "wa_keygen_gui.kv"

    def __init__(self, **kwargs):
        self.title = "Witness Angel - Guardian Authenticator"  # Untranslated
        super(MainApp, self).__init__(**kwargs)

    def build(self):
        self.theme_cls.primary_palette = "Blue"
        #self.theme_cls.theme_style = "Dark"  # or "Light"
        self.theme_cls.primary_hue = "900"  # "500"


def resourcePath():
    '''Returns path containing content - either locally or in pyinstaller tmp file'''
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS)
    return os.path.join(os.path.abspath("."))


if __name__ == "__main__":
    import kivy.resources
    kivy.resources.resource_add_path(resourcePath()) # Pyinstaller workaround
    MainApp().run()
