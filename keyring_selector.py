from datetime import datetime
from enum import Enum, unique
from pathlib import Path
from textwrap import dedent
from functools import partial
import shutil

from kivy.clock import Clock
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.properties import ObjectProperty
from kivymd.app import MDApp
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.filemanager import MDFileManager
from kivymd.uix.list import IconLeftWidget
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.screen import Screen

from wacryptolib.authentication_device import list_available_authentication_devices, \
    get_authenticator_path_for_authentication_device
from wacryptolib.authenticator import is_authenticator_initialized, load_authenticator_metadata
from wacryptolib.exceptions import KeyLoadingError
from wacryptolib.key_generation import load_asymmetric_key_from_pem_bytestring
from wacryptolib.key_storage import FilesystemKeyStorage
from wacryptolib.utilities import get_metadata_file_path
from waguilib.importable_settings import INTERNAL_AUTHENTICATOR_DIR, EXTERNAL_APP_ROOT, EXTERNAL_DATA_EXPORTS_DIR
from waguilib.utilities import convert_bytes_to_human_representation

from wa_keygen_gui import tr


Builder.load_file(str(Path(__file__).parent / 'keyring_selector.kv'))


@unique
class KeyringType(Enum):
   USER_PROFILE = 1
   CUSTOM_FOLDER = 2
   USB_DEVICE = 3


def shorten_uid(uid):
   return str(uid).split("-")[-1]


class FolderKeyStoreListItem(Factory.ThinTwoLineAvatarIconListItem):
    ''' FAILED attempt at fixing button position on this item
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

    # FIXME MAKE THEM PUBLIC!!!!!!!!!
    _selected_authenticator_path = ObjectProperty(None, allownone=True) # Path corresponding to a selected authenticator entry
    _selected_custom_folder_path = ObjectProperty(None, allownone=True)  # Custom folder selected for FolderKeyStoreListItem entry

    AUTHENTICATOR_ARCHIVE_FORMAT = "zip"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Clock.schedule_once(lambda *args, **kwargs: self.refresh_keyring_list())  # "on_pre_enter" is not called for 1st screen
        self._app = MDApp.get_running_app()
        self._folder_chooser = MDFileManager(
            selector="folder",
            exit_manager=self._folder_chooser_exit,
            select_path=self._folder_chooser_select_path,
        )
        self._archive_chooser = MDFileManager(
            selector="file",
            ext=["." + self.AUTHENTICATOR_ARCHIVE_FORMAT],
            exit_manager=self._archive_chooser_exit,
            select_path=self._close_archive_chooser_and_import_authenticator_from_archive,
        )

        language_menu_items = [
            {
                "text": lang,
                "viewclass": "OneLineListItem",
                "on_release": lambda x=lang_code: self.language_menu_select(x),
            } for (lang, lang_code) in [("English", "en"), ("French", "fr")]
        ]
        self._language_selector_menu = MDDropdownMenu(
            header_cls=Factory.LanguageMenuHeader(),
            #caller=self.screen.ids.button,
            items=language_menu_items,
            width_mult=2,
            position="bottom",
            ver_growth="down",
            max_height="110dp",
        )

    def language_menu_open(self, button):
        self._language_selector_menu.caller = button
        self._language_selector_menu.open()

    def language_menu_select(self, lang_code):
        self._language_selector_menu.dismiss()
        tr.switch_lang(lang_code)

    def _folder_chooser_exit(self, *args):
        self._folder_chooser.close()

    def _folder_chooser_select_path(self, path, *args):
        self._selected_custom_folder_path = Path(path)
        self._folder_chooser.close()
        authenticator_widget = self.ids.authentication_device_list.children[-2]  # AUTOSELECT "custom folder" item
        authenticator_widget._onrelease_callback(authenticator_widget)

    def folder_chooser_open(self, widget, *args):
        file_manager_path = EXTERNAL_APP_ROOT
        previously_selected_custom_folder_path = self._selected_custom_folder_path
        if previously_selected_custom_folder_path and previously_selected_custom_folder_path.is_dir():
            file_manager_path = previously_selected_custom_folder_path
        self._folder_chooser.show(str(file_manager_path))  # Soon use .show_disks!!

    def _archive_chooser_exit(self, *args):
        self._archive_chooser.close()

    def archive_chooser_open(self, *args):
        file_manager_path = EXTERNAL_APP_ROOT
        self._archive_chooser.show(str(file_manager_path))  # Soon use .show_disks!!

    def _get_authenticator_path(self,keyring_metadata):
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
        authentication_device_list_widget = self.ids.authentication_device_list
        for authenticator_widget in authentication_device_list_widget.children:  # Starts from bottom of list so!
            target_authenticator_path = self._get_authenticator_path(authenticator_widget._keyring_metadata)
            if target_authenticator_path == authenticator_path:
                authenticator_widget._onrelease_callback(authenticator_widget)
                return True
        return False

    def refresh_keyring_list(self):

        authentication_device_list = list_available_authentication_devices()  # TODO rename to usb devices?

        authentication_device_list_widget = self.ids.authentication_device_list  # FIXME rename this
        authentication_device_list_widget.clear_widgets()

        keyring_list_entries = []  # Pairs (widget, metadata)

        # TODO rename key_store to keyring
        profile_keyring_widget = Factory.UserKeyStoreListItem()
        keyring_list_entries.append((profile_keyring_widget, dict(keyring_type=KeyringType.USER_PROFILE)))

        folder_keyring_widget = Factory.FolderKeyStoreListItem()  # FIXME bug of Kivy, can't put selected_path here as argument
        folder_keyring_widget.selected_path = self._selected_custom_folder_path
        self.bind(_selected_custom_folder_path = folder_keyring_widget.setter('selected_path'))
        folder_keyring_widget.ids.open_folder_btn.bind(on_press=self.folder_chooser_open)  #
        keyring_list_entries.append((folder_keyring_widget, dict(keyring_type=KeyringType.CUSTOM_FOLDER)))

        for index, authentication_device in enumerate(authentication_device_list):

            device_size = convert_bytes_to_human_representation(authentication_device["size"])
            filesystem = authentication_device["format"].upper()

            keyring_widget = Factory.ThinTwoLineAvatarIconListItem(
                text=tr._("Drive: %s (%s)") % (authentication_device["path"], authentication_device["label"]),
                secondary_text=tr._("Size: %s, Filesystem: %s") % (device_size, filesystem),
            )
            keyring_widget.add_widget(IconLeftWidget(icon="usb-flash-drive"))
            keyring_list_entries.append((keyring_widget, dict(keyring_type=KeyringType.USB_DEVICE, **authentication_device)))

        for (keyring_widget, keyring_metadata) in keyring_list_entries:
            keyring_widget._keyring_metadata = keyring_metadata
            keyring_widget._onrelease_callback = partial(self.display_keyring_info, keyring_metadata=keyring_metadata)
            keyring_widget.bind(on_release=keyring_widget._onrelease_callback)
            authentication_device_list_widget.add_widget(keyring_widget)

        self.reselect_previously_selected_authenticator()  # Preserve previous selection across refreshes

    authenticator_status = ObjectProperty(None, allownone=True)

    AUTHENTICATOR_INITIALIZATION_STATUS_ICONS = {
        True: "check-circle-outline",  # or check-bold
        False: "checkbox-blank-off-outline",
        None: "file-question-outline",
    }

    def get_authenticator_status_message(self, authenticator_status):
        if authenticator_status is None:
            return tr._("No valid authenticator location selected")
        elif not authenticator_status:
            return tr._("Authenticator is not yet initialized")
        else:
            return tr._("Authenticator is initialized")

    def display_keyring_info(self, keyring_widget, keyring_metadata): ##list_item_obj, list_item_index):

        authentication_device_list_widget = self.ids.authentication_device_list  # FIXME rename to authenticator

        for child in authentication_device_list_widget.children:
            assert hasattr(child, "opposite_colors"), child
            child.bg_color = keyring_widget.theme_cls.bg_light
        keyring_widget.bg_color = keyring_widget.theme_cls.bg_darkest

        authenticator_info_text = ""
        authenticator_path = self._get_authenticator_path(keyring_metadata)

        # FIXMe handle OS errors here
        if not authenticator_path:
            authenticator_info_text = tr._("Please select an authenticator folder")
            authenticator_status = None

        elif not authenticator_path.exists():
            authenticator_info_text = tr._("Selected authenticator folder is invalid\nFull path: %s" % authenticator_path)
            authenticator_status = None

        elif not is_authenticator_initialized(authenticator_path):
            authenticator_info_text = tr._("Full path: %s") % authenticator_path
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

            authenticator_info_text = dedent(tr._("""\
                Full path: {authenticator_path}
                ID: {authenticator_uid}
                User: {authenticator_user}
                Password hint: {authenticator_passphrase_hint}
            """)).format(**displayed_values)

        textarea = self.ids.authentication_device_information
        textarea.text = authenticator_info_text

        self._selected_authenticator_path = authenticator_path  # Might be None
        self.authenticator_status = authenticator_status

    def show_authenticator_destroy_confirmation_dialog(self):
        authenticator_path = self._selected_authenticator_path
        self._dialog = MDDialog(
            auto_dismiss=True,
            title=tr._("Destroy authenticator"),
            text=tr._("Beware, it might make encrypted data using these keys impossible to decrypt."),
            #size_hint=(0.8, 1),
            buttons=[MDFlatButton(text="I'm sure", on_release=lambda *args: self.close_dialog_and_destroy_authenticator(authenticator_path)),
                     MDFlatButton(text="Cancel", on_release=lambda *args: self.close_dialog())],
        )
        self._dialog.open()

    def close_dialog(self):
        self._dialog.dismiss()

    def _delete_authenticator_data(self, authenticator_path):
        # FIXME protect against any OSERROR here!!
        metadata_file_path = get_metadata_file_path(authenticator_path)
        key_files = authenticator_path.glob("*.pem")
        for filepath in [metadata_file_path] + list(key_files):
            filepath.unlink(missing_ok=True)
        MDDialog(
             auto_dismiss=True,
                title=tr._("Deletion is over"),
                text=tr._("All authentication data from folder %s has been removed.") % authenticator_path,
            ).open()
        self.refresh_keyring_list()

    def close_dialog_and_destroy_authenticator(self, authenticator_path):
        self.close_dialog()
        self._delete_authenticator_data(authenticator_path=authenticator_path)

    def show_checkup_dialog(self):
        authenticator_path = self._selected_authenticator_path
        self._dialog = MDDialog(
            auto_dismiss=True,
            title=tr._("Sanity check"),
            type="custom",
            content_cls=Factory.AuthenticatorTesterContent(),
            buttons=[MDFlatButton(text="Check", on_release=lambda *args: self.close_dialog_and_check_authenticator(authenticator_path)),
                     MDFlatButton(text="Cancel", on_release=lambda *args: self.close_dialog())],
        )
        def _set_focus_on_passphrase(*args):
            self._dialog.content_cls.ids.tester_passphrase.focus = True
        self._dialog.bind(on_open=_set_focus_on_passphrase)
        self._dialog.open()

    def close_dialog_and_check_authenticator(self, authenticator_path):
        passphrase = self._dialog.content_cls.ids.tester_passphrase.text
        self.close_dialog()
        result_dict = self._test_authenticator_password(authenticator_path=authenticator_path, passphrase=passphrase)

        keypair_count= result_dict["keypair_count"]
        missing_private_keys = result_dict["missing_private_keys"]
        undecodable_private_keys = result_dict["undecodable_private_keys"]

        if keypair_count and not missing_private_keys and not undecodable_private_keys:
            result = tr._("Success")
            details = tr._("Keypairs successfully tested: %s") % keypair_count
        else:
            result = tr._("Failure")
            missing_private_keys_cast = [shorten_uid(k) for k in missing_private_keys]
            undecodable_private_keys_cast = [shorten_uid(k) for k in undecodable_private_keys]
            details = (tr._("Keypairs tested: %s\nMissing private keys: %s\nWrong passphrase for keys: %s") %
                        (keypair_count, ", ".join(missing_private_keys_cast) or "-", ", ".join(undecodable_private_keys_cast) or "-"))

        MDDialog(
            auto_dismiss=True,
            title=tr._("Checkup result: %s") % result,
            text=details,
            ).open()

    def _test_authenticator_password(self, authenticator_path, passphrase):  # FIXME rename this
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

    def export_authenticator_to_archive(self):
        authenticator_path = self._selected_authenticator_path

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        authenticator_metadata = load_authenticator_metadata(authenticator_path)
        device_uid = shorten_uid(authenticator_metadata["device_uid"])
        EXTERNAL_DATA_EXPORTS_DIR.mkdir(exist_ok=True)  # FIXME beware permissions on smartphone!!!
        archive_path_base = EXTERNAL_DATA_EXPORTS_DIR.joinpath("authenticator_uid%s_%s" % (device_uid, timestamp))
        archive_path = shutil.make_archive(base_name=archive_path_base, format=self.AUTHENTICATOR_ARCHIVE_FORMAT,
                            root_dir=authenticator_path)

        MDDialog(
            auto_dismiss=True,
            title=tr._("Export successful"),
            text=tr._("Authenticator archive exported to %s") % archive_path,
            ).open()

    def _close_archive_chooser_and_import_authenticator_from_archive(self, archive_path):
        self._archive_chooser.close()

        archive_path = Path(archive_path)
        authenticator_path = self._selected_authenticator_path

        # BEWARE - might override target files!
        shutil.unpack_archive(archive_path, extract_dir=authenticator_path, format=self.AUTHENTICATOR_ARCHIVE_FORMAT)

        MDDialog(
            auto_dismiss=True,
            title=tr._("Import successful"),
            text=tr._("Authenticator archive unpacked from %s, its integrity has not been checked though.") % archive_path.name,
            ).open()

        self.refresh_keyring_list()

    def display_help_popup(self):
        help_text = dedent(tr._("""\
        On this page, you can manage your authenticators, which are actually digital keychains identified by unique IDs.
        
        These keychains contain both public keys, which can be freely shared, and their corresponding private keys, protected by passphrases, which must be kept hidden.
        
        Authenticators can be stored in your user profile or in a custom folder, especially at the root of removable devices.
        
        You can initialize new authenticators from scratch, import/export them from/to ZIP archives, or check their integrity by providing their passphrases.
        
        Note that if you destroy an authenticator and all its exported ZIP archives, the WitnessAngel recordings which used it as a trusted third party might not be decryptable anymore (unless they used a shared secret with other trusted third parties).
        """))
        MDDialog(
            auto_dismiss=True,
            title=tr._("Authenticator management page"),
            text=help_text,
            ).open()
