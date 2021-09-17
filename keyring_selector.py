import logging
from enum import Enum, unique
from textwrap import dedent

from functools import partial

import shutil
import functools
from pathlib import Path

from kivy.factory import Factory
from kivy.lang import Builder
from kivy.properties import ObjectProperty, BooleanProperty
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
from kivymd.uix.filemanager import MDFileManager
from kivymd.uix.textfield import MDTextField
from kivymd.app import MDApp
from kivymd.theming import ThemableBehavior
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import OneLineIconListItem, MDList, IconLeftWidget, TwoLineAvatarIconListItem
from kivymd.uix.screen import Screen
from kivymd.uix.snackbar import Snackbar

from wacryptolib.authentication_device import list_available_authentication_devices, \
    get_authenticator_path_for_authentication_device
from wacryptolib.authenticator import is_authenticator_initialized, load_authenticator_metadata
from waguilib.importable_settings import INTERNAL_AUTHENTICATOR_DIR, EXTERNAL_APP_ROOT
from waguilib.utilities import convert_bytes_to_human_representation

Builder.load_file(str(Path(__file__).parent / 'keyring_selector.kv'))


@unique
class KeyringType(Enum):
   USER_PROFILE = 1
   CUSTOM_FOLDER = 2
   USB_DEVICE = 3

"""
class FolderKeyStoreListItem(TwoLineAvatarIconListItem):  # 
    def __init__(self):
        raise XXXXXXXX
"""

class KeyringSelectorScreen(Screen):

    ##keyring_list_entries = None  # Pairs (widget, metadata)

    # Used to reselect same entry after e.g. a refresh
    _selected_authenticator_path = None # Path hcorresponding to a selected authenticator entry
    _selected_custom_folder_path = ObjectProperty(None)  # Custom folder selected for FolderKeyStoreListItem entry

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Clock.schedule_once(lambda *args, **kwargs: self.refresh_keyring_list())
        self._app = MDApp.get_running_app()
        self._file_manager = MDFileManager(
            selector="folder",
            exit_manager=self._file_manager_exit,
            select_path=self._file_manager_select_path,
        )

    def _file_manager_exit(self, *args):
        print(">>>>>>>> _file_manager_exit ")
        self._file_manager.close()

    def _file_manager_select_path(self, path, *args):
        self._selected_custom_folder_path = Path(path)
        self._file_manager.close()
        authenticator_widget = self.ids.authentication_device_list.children[-2]  # AUTOSELECT "custom folder" item
        authenticator_widget._onrelease_callback(authenticator_widget)
        print(">>>>>>>> _selected_authenticator_path = ", path)

    def file_manager_open(self, widget, *args):
        print(">>>>>>> OPENING file_manager_open via widget", widget)
        file_manager_path = EXTERNAL_APP_ROOT
        previously_selected_custom_folder_path = self._selected_custom_folder_path
        if previously_selected_custom_folder_path and previously_selected_custom_folder_path.is_dir():
            file_manager_path = previously_selected_custom_folder_path
        self._file_manager.show(str(file_manager_path))  # Soon use .show_disks!!

    def _get_authenticator_path(self,keyring_metadata):
        authenticator_path = INTERNAL_AUTHENTICATOR_DIR
        keyring_type = keyring_metadata["keyring_type"]
        if keyring_type == KeyringType.USER_PROFILE:
            authenticator_path = INTERNAL_AUTHENTICATOR_DIR
        elif keyring_type == KeyringType.CUSTOM_FOLDER:
            authenticator_path = self._selected_custom_folder_path
        else:
            assert keyring_type == KeyringType.USB_DEVICE
            authenticator_path = get_authenticator_path_for_authentication_device(keyring_metadata)
        return authenticator_path

    def reselect_previously_selected_authenticator(self):
        print(">>>>> IN reselect_previously_selected_authenticator")
        previously_selected_authenticator_path = self._selected_authenticator_path
        if previously_selected_authenticator_path:
            result = self._select_matching_authenticator_entry(previously_selected_authenticator_path)
            if not result:
                self._selected_authenticator_path = None  # Extra security
                self._select_default_authenticator_entry()
        else:
            self._select_default_authenticator_entry()

    def _select_default_authenticator_entry(self):
        authenticator_widget = self.ids.authentication_device_list.children[-1]  # ALWAYS EXISTS
        authenticator_widget._onrelease_callback(authenticator_widget)

    def _select_matching_authenticator_entry(self, authenticator_path):
        print(">>>>> IN _select_matching_authenticator_entry")
        authentication_device_list_widget = self.ids.authentication_device_list
        for authenticator_widget in authentication_device_list_widget.children:  # Starts from bottom of list so!
            target_authenticator_path = self._get_authenticator_path(authenticator_widget._keyring_metadata)
            if target_authenticator_path == authenticator_path:
                authenticator_widget._onrelease_callback(authenticator_widget)
                return True
        return False

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
        ##profile_keyring_widget.bind(on_touch_up=self.file_manager_open)  # .ids.mycontainer

        folder_keyring_widget = Factory.FolderKeyStoreListItem()  # FIXME bug of Kivy, can't put selected_path here
        folder_keyring_widget.selected_path=self._selected_custom_folder_path
        ##def set_child_selected_path(p):
        ##    folder_keyring_widget.selected_path = str(p)
        self.bind(_selected_custom_folder_path=folder_keyring_widget.setter('selected_path'))
        folder_keyring_widget.ids.mycontainer.bind(on_press=self.file_manager_open)  #
        keyring_list_entries.append((folder_keyring_widget, dict(keyring_type=KeyringType.CUSTOM_FOLDER)))


        for index, authentication_device in enumerate(authentication_device_list):

            device_size = convert_bytes_to_human_representation(authentication_device["size"])
            filesystem = authentication_device["format"].upper()

            keyring_widget = Factory.ThinTwoLineAvatarIconListItem(
                text="[b]Drive:[/b] %s (%s)" % (authentication_device["path"], authentication_device["label"]),
                secondary_text="Size: %s, Filesystem: %s" % (device_size, filesystem),
                #_height=dp(60),
                #bg_color=self.COLORS.DARK_BLUE,
            )
            keyring_widget.add_widget(IconLeftWidget(icon="usb-flash-drive"))
            keyring_list_entries.append((keyring_widget, dict(keyring_type=KeyringType.USB_DEVICE, **authentication_device)))

            #####device_list_item._onrelease_callback = partial(self.show_authentication_device_info, list_item_index=index)
            #####device_list_item.bind(on_release=device_list_item._onrelease_callback)

        for (keyring_widget, keyring_metadata) in keyring_list_entries:
            keyring_widget._keyring_metadata = keyring_metadata
            keyring_widget._onrelease_callback = partial(self.display_keyring_info, keyring_metadata=keyring_metadata)
            keyring_widget.bind(on_release=keyring_widget._onrelease_callback)
            authentication_device_list_widget.add_widget(keyring_widget)

        self.reselect_previously_selected_authenticator()  # Preserve previous selection across refreshes


    authenticator_status = BooleanProperty(None)
    authenticator_status_message = StringProperty()

    AUTHENTICATOR_INITIALIZATION_STATUS_ICONS = {
        True: "check-circle-outline",  # or check-bold
        False: "checkbox-blank-off-outline",
        None: "file-question-outline",
    }

    def display_keyring_info(self, keyring_widget, keyring_metadata): ##list_item_obj, list_item_index):

        print(">>>>> IN refresh_keyring_list")

        authentication_device_list_widget = self.ids.authentication_device_list  # FIXME rename to authenticator

        for child in authentication_device_list_widget.children:
            assert hasattr(child, "opposite_colors"), child
            child.bg_color = keyring_widget.theme_cls.bg_light
        print(">>>keyring_widget", keyring_widget.bg_color)
        keyring_widget.bg_color = keyring_widget.theme_cls.bg_darkest

        #keyring_type = keyring_metadata["keyring_type"]


        authenticator_info_text = ""

        authenticator_path = self._get_authenticator_path(keyring_metadata)

        '''
        if keyring_type == KeyringType.USER_PROFILE:
            pass

        elif keyring_type == KeyringType.CUSTOM_FOLDER:
            pass  # TODO

        else:
            assert keyring_type == KeyringType.USB_DEVICE
            authenticator_path = get_authenticator_path_for_authentication_device(keyring_metadata)
            '''

        # FIXMe handle OS errors here
        if not authenticator_path:
            authenticator_info_text = self._app.tr._("Please select an authenticator folder")

        elif not authenticator_path.exists():
            authenticator_info_text = self._app.tr._("Selected authenticator folder is invalid\nFull path: %s" % authenticator_path)

        elif not is_authenticator_initialized(authenticator_path):
            authenticator_info_text = self._app.tr._("Authenticator is not initialized\nFull path: %s") % authenticator_path

        elif is_authenticator_initialized(authenticator_path):

            authenticator_metadata = load_authenticator_metadata(authenticator_path)

            displayed_values = dict(
                authenticator_path=authenticator_path,
                authenticator_uid=authenticator_metadata["device_uid"],
                authenticator_user=authenticator_metadata["user"],
                authenticator_passphrase_hint=authenticator_metadata["passphrase_hint"],
            )

            authenticator_info_text = dedent(self._app.tr._("""\
                AUTHENTICATOR INFORMATION
                ID: {authenticator_uid}
                Full path: {authenticator_path}
                User: {authenticator_user}
                Password hint: {authenticator_passphrase_hint}
            """)).format(**displayed_values)

        textarea = self.ids.authentication_device_information
        textarea.text = authenticator_info_text

        self._selected_authenticator_path = authenticator_path  # Might be None

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
