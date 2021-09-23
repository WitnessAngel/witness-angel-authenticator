import locale

import os
import sys
from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import Label
from kivymd.uix.list import IconLeftWidget
from kivymd.uix.screen import Screen

from wacryptolib.authentication_device import (
    list_available_authentication_devices,
    initialize_authentication_device,
    _get_key_storage_folder_path, load_authentication_device_metadata,
)
from wacryptolib.key_generation import generate_asymmetric_keypair
from wacryptolib.key_storage import FilesystemKeyStorage
from wacryptolib.utilities import generate_uuid0
from waguilib.i18n import Lang
from waguilib.widgets.layout_helpers import activate_widget_debug_outline



"""
class A:  # TODO put back translation tooling
    def _(self, a):
        return a
"""
LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")

#activate_widget_debug_outline()

# VERY rough detection of user language, will often not work under Windows but it's OK
_lang_code, _charset = locale.getlocale()
DEFAULT_LANGUAGE = "fr" if "fr" in _lang_code.lower() else "en"

class MainApp(MDApp):


    tr = Lang(DEFAULT_LANGUAGE, locale_dir=LOCALE_DIR)  # ("en")  # FIXME replace this with real trans

    kv_file = "wa_keygen_gui.kv"
    keygen_panel = None

    #authentication_device_list = ()
    #authentication_device_selected = None

    class COLORS:  # FIXME OBSOLETE
        LIGHT_GREY = [1, 1, 1, 0.4]
        MEDIUM_GREY = [0.6, 0.6, 0.6, 1]
        DARK_GREY = [0.3, 0.3, 0.3, 0.4]
        DARKEST_BLUE = [0.1372, 0.2862, 0.5294, 1]
        DARK_BLUE = [0.1272, 0.2662, 0.4294, 1]
        BUTTON_BACKGROUND = [51, 23, 186, 1]  # Not same format as others, as its' a tint
        WHITE = [1, 1, 1, 1]

    def __init__(self, **kwargs):
        self.title = "Witness Angel - Guardian Authenticator"
        super(MainApp, self).__init__(**kwargs)

    @property
    def screen_manager(self):
        if not self.root: return  # Early introspection
        return self.root

    @property
    def ___keyring_selector_screen(self):
        """Beware, here we lookup not the config file but the in-GUI data!"""
        if not self.root:
            return  # Early introspection
        return self.screen_manager.get_screen("keyring_selector_screen")

    def build(self):

        self.theme_cls.primary_palette = "Blue"
        #self.theme_cls.theme_style = "Dark"  # "Light"
        self.theme_cls.primary_hue = "900"  # "500"

        # FIXME - DUPLICATED WITH WAGUILIB NOW
        # Ensure that we don't need to click TWICE to gain focus on Kivy Window and then on widget!
        def force_window_focus(*args, **kwargs):
            Window.raise_window()
        Window.bind(on_cursor_enter=force_window_focus)

        #self.authentication_device_selected = None
        #self.orientation = "vertical"
        #self.screen = Screen()
        #self.list_detected_devices()
        #return self.screen


def resourcePath():
    '''Returns path containing content - either locally or in pyinstaller tmp file'''
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS)

    return os.path.join(os.path.abspath("."))


if __name__ == "__main__":
    import kivy.resources
    kivy.resources.resource_add_path(resourcePath()) # Pyinstaller workaround
    MainApp().run()
