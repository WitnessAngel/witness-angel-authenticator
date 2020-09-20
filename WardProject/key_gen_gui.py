from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial

from kivy.clock import Clock
from kivy.factory import Factory
from kivy.uix.image import Image
from kivymd.app import MDApp
from kivymd.uix.list import IRightBodyTouch, ILeftBody
from kivymd.uix.selectioncontrol import MDCheckbox
from wacryptolib.authentication_device import (
    list_available_authentication_devices,
    initialize_authentication_device,
    _get_metadata_file_path, _get_key_storage_folder_path, load_authentication_device_metadata,
)
from kivymd.uix.button import  MDFlatButton
from kivymd.uix.screen import Screen
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import Label
from wacryptolib.key_generation import generate_asymmetric_keypair
from wacryptolib.key_storage import FilesystemKeyStorage
from wacryptolib.utilities import load_from_json_file
import sys
from io import StringIO
from wacryptolib.utilities import generate_uuid0


class MyCheckbox(IRightBodyTouch, MDCheckbox):
    pass


class MyAvatar(ILeftBody, Image):
    pass


THREAD_POOL_EXECUTOR = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="keygen_worker"  # SINGLE worker for now, to avoid concurrency
)


class MainApp(MDApp):
    def __init__(self, **kwargs):
        self.title = "Witness Angel - WardProject"
        super(MainApp, self).__init__(**kwargs)

    def show_validate(self):

        if not self.authentication_device_selected:
            user_error = "Please select USB device"  # FIXME remove this useless case
            title_dialog = "USB not selected !!"
            self.open_dialog(user_error, title_dialog)
        else:
            if (self.list.ids.userfield.text != "") and (
                    self.list.ids.passphrasefield.text != ""
            ):
                self.initialize()
            else:
                user_error = "Please enter a username and a passphrase"
                self.open_dialog(user_error)

    def open_dialog(self, user_error, title_dialog="Please fill in the empty field"):
        self.dialog = MDDialog(
            title=title_dialog,
            text=user_error,
            size_hint=(0.8, 1),
            buttons=[MDFlatButton(text="Close", on_release=self.close_dialog)],
        )
        self.dialog.open()

    def close_dialog(self, obj):
        self.dialog.dismiss()

    def get_detected_devices(self):
        self.list = Factory.Lists()
        list_devices = list_available_authentication_devices()
        for index, usb in enumerate(list_devices):
            self.lineCheck = Factory.ListItemWithCheckbox(
                text="[color=#FFFFFF][b]Path:[/b] %s[/color]" % (str(usb["path"])),
                secondary_text="[color=#FFFFFF][b]Label:[/b] %s[/color]" % (str(usb["label"])),
                bg_color=[0.1372, 0.2862, 0.5294, 1],

            )
            self.lineCheck.bind(on_release=self.get_info_key_selected)
            self.list.ids.scroll.add_widget(self.lineCheck)
        self.screen.add_widget(self.list)

    def refresh_list(self):
        self.get_detected_devices()

    def initialize_rsa_key(self):
        for c in list(self.list.ids.scroll.children):
            c.bg_color=[1, 1, 1, 0.4]
        #self.list.ids.scroll.bg_color=[1, 0.2862, 0.5294, 1]
        self.lineCheck.unbind(on_release=self.get_info_key_selected)

        self.list.ids.btn_refresh.disabled = True
        try:
            keys_count = 7
            #print(">starting initialize_rsa_key")

            Clock.schedule_once(partial(self._do_update_progress_bar, 10))

            initialize_authentication_device(self.authentication_device_selected, self.list.ids.userfield.text)
            key_storage_folder = _get_key_storage_folder_path(self.authentication_device_selected)
            assert key_storage_folder.is_dir()  # By construction...

            object_FilesystemKeyStorage = FilesystemKeyStorage(key_storage_folder)

            for i in range(1, keys_count+1):
                #print(">WIP initialize_rsa_key", id)
                key_pair = generate_asymmetric_keypair(
                    key_type="RSA_OAEP",
                    passphrase=self.list.ids.passphrasefield.text.encode(),
                )
                object_FilesystemKeyStorage.set_keys(
                    keychain_uid=generate_uuid0(),
                    key_type="RSA_OAEP",
                    public_key=key_pair["public_key"],
                    private_key=key_pair["private_key"],
                )

                Clock.schedule_once(partial(self._do_update_progress_bar, 10 + int (i * 90 / keys_count)))

            self.success = True
            #print(">finish_initialization")
            self.list.ids.btn_refresh.disabled = False
            Clock.schedule_once(self.finish_initialization)
        except Exception as exc:
            print(">>>>>>>>>>>>>>>> ERROR IN THREAD", exc)  # FIXME add logging


    def build(self):
        self.authentication_device_selected = None
        self.orientation = "vertical"
        self.screen = Screen()
        self.get_detected_devices()
        return self.screen

    def get_info_key_selected(self, linelist):
        list_ids=self.list.ids
        list_devices = list_available_authentication_devices()
        for i in list_ids.scroll.children:
            i.bg_color = [0.1372, 0.2862, 0.5294, 1]
        linelist.bg_color = [0.6, 0.6, 0.6, 1]

        list_ids.button_initialize.disabled = False
        list_ids.userfield.disabled = False
        list_ids.passphrasefield.disabled = False
        list_ids.userfield.fill_color = [1, 1, 1, 0.4]
        list_ids.passphrasefield.fill_color = [1, 1, 1, 0.4]
        self.l = Label(text="")
        self.alertMessage = Label(text="")
        list_ids.labelInfoUsb1.clear_widgets()
        list_ids.label_alert.clear_widgets()
        list_ids.labelInfoUsb1.add_widget(self.l)
        list_ids.label_alert.add_widget(self.alertMessage)
        for index, authentication_device in enumerate(list_devices):
            if linelist.text == "[color=#FFFFFF][b]Path:[/b] " + str(authentication_device["path"]) + "[/color]":
                self.authentication_device_selected = authentication_device
                if str(authentication_device["is_initialized"]) == "True":
                    list_ids.button_initialize.disabled = True
                    list_ids.userfield.disabled = True
                    list_ids.passphrasefield.disabled = True
                    list_ids.userfield.fill_color = [0.3, 0.3, 0.3, 0.4]
                    list_ids.passphrasefield.fill_color = [0.3, 0.3, 0.3, 0.4]

                    self.alertMessage = Label(
                        text="You have to format the key or manually delete the private folder"
                    )
                    metadata = load_authentication_device_metadata(authentication_device)
                    list_ids.userfield.text = metadata["user"]
                    list_ids.userfield.disabled = True
                    list_ids.userfield.fill_color = [0.3, 0.3, 0.3, 0.4]

                else:

                    self.alertMessage = Label(
                        text="Please fill in the username and passphrase to initialize the usb key"
                    )
                    list_ids.userfield.text = ""

                self.l = Label(
                    text="USB key : size %s, fileystem %s, initialized=%s"
                         % (authentication_device["size"], authentication_device["format"], authentication_device["is_initialized"])
                )
                list_ids.labelInfoUsb1.add_widget(self.l)
                list_ids.label_alert.add_widget(self.alertMessage)

    def update_progress_bar(self, percent):
        #print(">>>>>update_progress_bar")
        Clock.schedule_once(partial(self._do_update_progress_bar, percent))

    def _do_update_progress_bar(self, percent, *args, **kwargs):
        #print(">>>>>>", self.list.ids)
        self.list.ids.barProgress.value = percent


    def initialize(self):
        self.l.text = "Please wait a few seconds."
        self.alertMessage.text = "the operation is being processed."
        self.list.ids.button_initialize.disabled = True
        THREAD_POOL_EXECUTOR.submit(self.initialize_rsa_key)

    def finish_initialization(self, *args, **kwargs):

        self._do_update_progress_bar(0)  # Reset

        if self.success:
            #self.list.ids.errors.add_widget(
            #    Label(text="Initialization successful", font_size="28sp", color=[0, 1, 0, 1])
            #)

            self.l.text = "Processing completed."
            self.alertMessage.text = "successful operation."


if __name__ == "__main__":
    MainApp().run()
