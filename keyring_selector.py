import logging
from enum import Enum, unique

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


@unique
class KeyringType(Enum):
   USER_PROFILE = 1
   CUSTOM_FOLDER = 2
   USB_DEVICE = 3


class KeyringSelectorScreen(Screen):

    keyring_list_entries = None  # Pairs (widget, metadata)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Clock.schedule_once(lambda *args, **kwargs: self.refresh_keyring_list())


    def refresh_keyring_list(self):
        #return
        #self.keygen_panel = Factory.IdentityManagementPanel()
        print(">>>>> IN refresh_keyring_list")

        authentication_device_list = list_available_authentication_devices()  # TODO rename to usb devices?
        self.authentication_device_list = authentication_device_list

        #first_device_list_item = None

        authentication_device_list_widget = self.ids.authentication_device_list  # FIXME rename this
        authentication_device_list_widget.clear_widgets()

        keyring_list_entries = []  # Pairs (widget, metadata)

        # TODO rename key_store to keyring
        profile_keyring_widget = Factory.UserKeyStoreListItem()
        keyring_list_entries.append((profile_keyring_widget, dict(keyring_type=KeyringType.USER_PROFILE)))

        folder_keyring_widget = Factory.FolderKeyStoreListItem()
        keyring_list_entries.append((folder_keyring_widget, dict(keyring_type=KeyringType.CUSTOM_FOLDER)))


        for index, authentication_device in enumerate(authentication_device_list):
            keyring_widget = Factory.ThinTwoLineAvatarIconListItem(
                text="[b]Path:[/b] %s" % (str(authentication_device["path"])),
                secondary_text="[b]Label:[/b] %s" % (str(authentication_device["label"])),
                #_height=dp(60),
                #bg_color=self.COLORS.DARK_BLUE,
            )
            keyring_widget.add_widget(IconLeftWidget(icon="usb-flash-drive"))
            keyring_list_entries.append((keyring_widget, dict(keyring_type=KeyringType.USB_DEVICE, **authentication_device)))

            #####device_list_item._onrelease_callback = partial(self.show_authentication_device_info, list_item_index=index)
            #####device_list_item.bind(on_release=device_list_item._onrelease_callback)

        for (keyring_widget, keyring_metadata) in keyring_list_entries:
            keyring_widget._onrelease_callback = partial(self.display_keyring_info, keyring_metadata=keyring_metadata)
            keyring_widget.bind(on_release=keyring_widget._onrelease_callback)
            authentication_device_list_widget.add_widget(keyring_widget)


    def display_keyring_info(self, keyring_widget, keyring_metadata): ##list_item_obj, list_item_index):

        print(">>>>> IN refresh_keyring_list")

        authentication_device_list_widget = self.ids.authentication_device_list

        for child in authentication_device_list_widget.children:
            assert hasattr(child, "opposite_colors"), child
            child.bg_color = keyring_widget.theme_cls.bg_light
        print(">>>keyring_widget", keyring_widget.bg_color)
        keyring_widget.bg_color = keyring_widget.theme_cls.bg_darkest

        textarea = self.ids.authentication_device_information

        textarea.text = str(keyring_metadata)

        """
        keygen_panel_ids=self.keygen_panel.ids

        authentication_device_list = self.authentication_device_list


        #list_item_obj.bg_color = self.COLORS.MEDIUM_GREY

        keygen_panel_ids.button_initialize.disabled = False

        self.status_title = Label(text="")
        self.status_message = Label(text="")

        keygen_panel_ids.status_title_layout.clear_widgets()
        keygen_panel_ids.status_title_layout.add_widget(self.status_title)

        keygen_panel_ids.status_message_layout.clear_widgets()
        keygen_panel_ids.status_message_layout.add_widget(self.status_message)

        authentication_device = authentication_device_list[list_item_index]
        self.authentication_device_selected = authentication_device

        if authentication_device["is_initialized"]:
            keygen_panel_ids.button_initialize.disabled = True

            self.set_form_fields_status(enabled=False)

            self.status_message = Label(
                text="To reset the USB key, manually delete the key-storage folder on it"
            )
            try:
                metadata = load_authentication_device_metadata(authentication_device)
            except FileNotFoundError:
                pass  # User has removed the key or folder in the meantime...
            else:
                keygen_panel_ids.userfield.text = metadata["user"]
                keygen_panel_ids.passphrasehintfield.text = metadata.get("passphrase_hint", "")

        else:

            self.set_form_fields_status(enabled=True)

            self.status_message = Label(
                text="Please fill in the form below to initialize the usb key"
            )
            keygen_panel_ids.userfield.text = ""

        self.status_title = Label(
            text="USB key : size %s, fileystem %s, initialized=%s"
                 % (authentication_device["size"], authentication_device["format"], authentication_device["is_initialized"])
        )
        keygen_panel_ids.status_title_layout.add_widget(self.status_title)
        keygen_panel_ids.status_message_layout.add_widget(self.status_message)
        """
