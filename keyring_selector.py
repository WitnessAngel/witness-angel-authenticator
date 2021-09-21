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
from kivy.uix.widget import Widget
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
from wacryptolib.exceptions import KeyLoadingError
from wacryptolib.key_generation import load_asymmetric_key_from_pem_bytestring
from wacryptolib.key_storage import FilesystemKeyStorage
from wacryptolib.utilities import get_metadata_file_path
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

class FolderKeyStoreListItem(Factory.ThinTwoLineAvatarIconListItem):

    ''' FAILED attempt at fixing button position
    def __init__(self):
        super().__init__()
        #print(">>>>>>>>>>>>>>", self._EventDispatcher__event_stack)
        print(">>>>>>>>>>>>>>>>>>", self.size, self.__class__.__mro__, "\n", self.__class__, "\n", self.__dict__, hex(id(self)))
        ##Clock.schedule_once(lambda x: self.dispatch('on_focus'))
        def force_reset(*args):
            prop = self.property('size')
            # dispatch this property on the button instance
            prop.dispatch(self)
        Clock.schedule_once(force_reset, timeout=1)
    '''

class KeyringSelectorScreen(Screen):

    ##keyring_list_entries = None  # Pairs (widget, metadata)

    # Used to reselect same entry after e.g. a refresh
    # FIXME MAKE THEM PUBLIC!!!!!!!!!
    _selected_authenticator_path = ObjectProperty(None, allownone=True) # Path corresponding to a selected authenticator entry
    _selected_custom_folder_path = ObjectProperty(None, allownone=True)  # Custom folder selected for FolderKeyStoreListItem entry

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Clock.schedule_once(lambda *args, **kwargs: self.refresh_keyring_list())  # "on_pre_enter" is not called for 1st screen
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
        #self.authentication_device_list = authentication_device_list

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
        folder_keyring_widget.ids.open_folder_btn.bind(on_press=self.file_manager_open)  #
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


    authenticator_status = ObjectProperty(None, allownone=True)
    ###authenticator_status_message = StringProperty()

    AUTHENTICATOR_INITIALIZATION_STATUS_ICONS = {
        True: "check-circle-outline",  # or check-bold
        False: "checkbox-blank-off-outline",
        None: "file-question-outline",
    }

    def get_authenticator_status_message(self, authenticator_status):
        _ = self._app.tr._
        if authenticator_status is None:
            return _("No valid authenticator location selected")
        elif not authenticator_status:
            return _("Authenticator is not yet initialized")
        else:
            return _("Authenticator is initialized")

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
            authenticator_status = None

        elif not authenticator_path.exists():
            authenticator_info_text = self._app.tr._("Selected authenticator folder is invalid\nFull path: %s" % authenticator_path)
            authenticator_status = None

        elif not is_authenticator_initialized(authenticator_path):
            authenticator_info_text = self._app.tr._("Full path: %s") % authenticator_path
            authenticator_status = False

        elif is_authenticator_initialized(authenticator_path):
            authenticator_status = True
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
        self.authenticator_status = authenticator_status

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

    def show_authenticator_destroy_confirmation_dialog(self):
        _ = self._app.tr._
        authenticator_path = self._selected_authenticator_path
        self._dialog = MDDialog(
            auto_dismiss=True,
            title=_("Destroy authenticator"),
            text=_("Beware, it will make all encrypted data using these keys impossible to read."),
            #size_hint=(0.8, 1),
            buttons=[MDFlatButton(text="I'm sure", on_release=lambda *args: self.close_dialog_and_destroy_authenticator(authenticator_path)),
                     MDFlatButton(text="Cancel", on_release=lambda *args: self.close_dialog())],
        )
        self._dialog.open()

    def close_dialog(self):
        self._dialog.dismiss()

    def _delete_authenticator_data(self, authenticator_path):
        # FIXME protect against any OSERROR here!!
        _ = self._app.tr._
        metadata_file_path = get_metadata_file_path(authenticator_path)
        key_files = authenticator_path.glob("*.pem")
        for filepath in [metadata_file_path] + list(key_files):
            filepath.unlink(missing_ok=True)
        MDDialog(
             auto_dismiss=True,
                title=_("Destruction is over"),
                text=_("All authentication data from folder %s has been removed.") % authenticator_path,
            ).open()
        self.refresh_keyring_list()

    def close_dialog_and_destroy_authenticator(self, authenticator_path):
        self.close_dialog()
        print("IN close_dialog_and_destroy_authenticator")
        self._delete_authenticator_data(authenticator_path=authenticator_path)

    def show_checkup_dialog(self):
        _ = self._app.tr._
        authenticator_path = self._selected_authenticator_path
        self._dialog = MDDialog(
            auto_dismiss=True,
            title=_("Sanity check"),
            type="custom",
            content_cls=Factory.AuthenticatorTesterContent(),
            #size_hint=(0.8, 1),
            buttons=[MDFlatButton(text="Check", on_release=lambda *args: self.close_dialog_and_check_authenticator(authenticator_path)),
                     MDFlatButton(text="Cancel", on_release=lambda *args: self.close_dialog())],
        )
        self._dialog.open()

    def close_dialog_and_check_authenticator(self, authenticator_path):
        _ = self._app.tr._
        passphrase = self._dialog.content_cls.ids.tester_passphrase.text
        self.close_dialog()
        result = self._test_authenticator_password(authenticator_path=authenticator_path, passphrase=passphrase)
        MDDialog(
             auto_dismiss=True,
                title=_("Checkup result"),
                text=_("Result: %s") % str(result),
            ).open()

    def _test_authenticator_password(self, authenticator_path, passphrase):
        filesystem_key_storage = FilesystemKeyStorage(authenticator_path)

        missing_private_keys = []
        undecodable_private_keys = []

        keypair_identifiers = filesystem_key_storage.list_keypair_identifiers()

        for key_information in keypair_identifiers:
            keychain_uid = key_information["keychain_uid"]
            key_type = key_information["key_type"]
            if not key_information["private_key_present"]:
                missing_private_keys.append(keychain_uid)
                continue
            private_key_pem = filesystem_key_storage.get_private_key(keychain_uid=keychain_uid, key_type=key_type)
            try:
                key_obj = load_asymmetric_key_from_pem_bytestring(
                   key_pem=private_key_pem, key_type=key_type, passphrase=passphrase
                )
                assert key_obj, key_obj
            except KeyLoadingError:
                undecodable_private_keys.append(keychain_uid)

        return dict(keypair_count=len(keypair_identifiers),
                    missing_private_keys=missing_private_keys,
                    undecodable_private_keys=undecodable_private_keys)


