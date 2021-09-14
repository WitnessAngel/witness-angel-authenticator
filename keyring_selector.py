import logging
from functools import partial

import shutil
import functools
from pathlib import Path

from kivy.factory import Factory
from kivy.lang import Builder
from kivy.properties import ObjectProperty
from kivy.uix import boxlayout
from kivy.uix.screenmanager import Screen
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.config import Config
from kivy.properties import StringProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.screenmanager import ScreenManager
from kivy.uix.textinput import TextInput
from kivymd.uix.textfield import MDTextField
from kivymd.app import MDApp
from kivymd.theming import ThemableBehavior
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import OneLineIconListItem, MDList, IconLeftWidget
from kivymd.uix.screen import Screen
from kivymd.uix.snackbar import Snackbar

from wacryptolib.authentication_device import list_available_authentication_devices

Builder.load_file(str(Path(__file__).parent / 'keyring_selector.kv'))


class KeyringSelectorScreen(Screen):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Clock.schedule_once(lambda *args, **kwargs: self.refresh_keyring_list())


    def refresh_keyring_list(self):
        #return
        #self.keygen_panel = Factory.IdentityManagementPanel()
        print(">>>>> IN refresh_keyring_list")

        authentication_device_list = list_available_authentication_devices()
        self.authentication_device_list = authentication_device_list

        #first_device_list_item = None

        authentication_device_list_widget = self.ids.authentication_device_list
        authentication_device_list_widget.clear_widgets()

        user_key_store_list_item = Factory.UserKeyStoreListItem()
        authentication_device_list_widget.add_widget(user_key_store_list_item)

        folder_key_store_list_item = Factory.FolderKeyStoreListItem()
        authentication_device_list_widget.add_widget(folder_key_store_list_item)

        for index, authentication_device in enumerate(authentication_device_list):
            device_list_item = Factory.ThinTwoLineAvatarIconListItem(
                text="[b]Path:[/b] %s" % (str(authentication_device["path"])),
                secondary_text="[b]Label:[/b] %s" % (str(authentication_device["label"])),
                #_height=dp(60),
                #bg_color=self.COLORS.DARK_BLUE,
            )
            device_list_item.add_widget(IconLeftWidget(icon="usb-flash-drive"))
            #####device_list_item._onrelease_callback = partial(self.show_authentication_device_info, list_item_index=index)
            #####device_list_item.bind(on_release=device_list_item._onrelease_callback)
            authentication_device_list_widget.add_widget(device_list_item)
