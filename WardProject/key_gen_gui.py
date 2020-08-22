from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial

from kivy.clock import Clock
from kivy.factory import Factory
from kivy.uix.image import Image
from kivymd.app import MDApp
from kivymd.uix.list import IRightBodyTouch, ILeftBody
from kivymd.uix.selectioncontrol import MDCheckbox
from wacryptolib.key_device import (
    list_available_key_devices,
    initialize_key_device,
    _get_metadata_file_path,
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

        if self.key_device_selected == None:
            user_error = "Please select USB"
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
        list_devices = list_available_key_devices()
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

        self.screen.remove_widget(self.list)
        self.get_detected_devices()

    def initialize_rsa_key(self):
        try:
            keys_count = 7
            print(">starting initialize_rsa_key")

            Clock.schedule_once(partial(self._do_update_progress_bar, 10))

            initialize_key_device(self.key_device_selected, self.list.ids.userfield.text)
            metadata_file = _get_metadata_file_path(self.key_device_selected)
            metadata_folder = metadata_file.parent
            private_key_dir = metadata_folder.joinpath("crypto_keys")
            private_key_dir.mkdir(exist_ok=True)

            object_FilesystemKeyStorage = FilesystemKeyStorage(private_key_dir)

            for i in range(1, keys_count+1):
                print(">WIP initialize_rsa_key", id)
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
            print(">finish_initialization")
            Clock.schedule_once(self.finish_initialization)
        except Exception as exc:
            print(">>>>>>>>>>>>>>>> ERROR THREAD", exc)


    def build(self):
        self.key_device_selected = None
        self.orientation = "vertical"
        self.screen = Screen()
        self.get_detected_devices()
        return self.screen

    def get_info_key_selected(self, linelist):
        list_devices = list_available_key_devices()
        for i in self.list.ids.scroll.children:
            i.bg_color = [0.1372, 0.2862, 0.5294, 1]
        linelist.bg_color = [0.6, 0.6, 0.6, 1]

        self.list.ids.button_initialize.disabled = False
        self.list.ids.userfield.disabled = False
        self.list.ids.passphrasefield.disabled = False
        self.list.ids.userfield.fill_color = [1, 1, 1, 0.4]
        self.list.ids.passphrasefield.fill_color = [1, 1, 1, 0.4]
        self.l = Label(text="")
        self.alertMessage = Label(text="")
        self.list.ids.labelInfoUsb1.clear_widgets()
        self.list.ids.label_alert.clear_widgets()
        self.list.ids.labelInfoUsb1.add_widget(self.l)
        self.list.ids.label_alert.add_widget(self.alertMessage)
        for index, key_device in enumerate(list_devices):
            if linelist.text == "[color=#FFFFFF][b]Path:[/b] " + str(key_device["path"]) + "[/color]":
                self.key_device_selected = key_device
                if str(key_device["is_initialized"]) == "True":
                    self.list.ids.button_initialize.disabled = True
                    self.list.ids.userfield.disabled = True
                    self.list.ids.passphrasefield.disabled = True
                    self.list.ids.userfield.fill_color = [0.3, 0.3, 0.3, 0.4]
                    self.list.ids.passphrasefield.fill_color = [0.3, 0.3, 0.3, 0.4]
                    self.l = Label(
                        text="USB information : Size %s   |   Fst :%s | and it is initialized"
                             % (str(key_device["size"]), str(key_device["format"]))
                    )
                    self.alertMessage = Label(
                        text="You have to format the key or manually delete the private folder"
                    )
                    meta = load_from_json_file(
                        key_device["path"] + "\.key_storage\.metadata.json"
                    )
                    self.list.ids.userfield.text = meta["user"]
                    self.list.ids.userfield.disabled = True
                    self.list.ids.userfield.fill_color = [0.3, 0.3, 0.3, 0.4]

                else:
                    self.l = Label(
                        text="USB information : Size %s   |   Fst :%s | and it is not initialized"
                             % (str(key_device["size"]), str(key_device["format"]))
                    )
                    self.alertMessage = Label(
                        text="Please fill in the username and passphrase to initialize the usb key"
                    )
                    self.list.ids.userfield.text = ""
                self.list.ids.labelInfoUsb1.add_widget(self.l)
                self.list.ids.label_alert.add_widget(self.alertMessage)

    def update_progress_bar(self, percent):
        print(">>>>>update_progress_bar")
        Clock.schedule_once(partial(self._do_update_progress_bar, percent))

    def _do_update_progress_bar(self, percent, *args, **kwargs):
        print(">>>>>>", self.list.ids)
        self.list.ids.barProgress.value = percent

    def initialize(self):
        self.l.text = "Please wait a few seconds."
        self.alertMessage.text = "the operation is being processed."
        self.list.ids.button_initialize.disabled = True
        THREAD_POOL_EXECUTOR.submit(self.initialize_rsa_key)

    def finish_initialization(self, *args, **kwargs):

        # Store the reference, in case you want to show things again in standard output
        ##old_stdout = sys.stdout

        # This variable will store everything that is sent to the standard output
        ##result = StringIO()
        ##sys.stdout = result

        """
        try:
            self.initialize_rsa_key()
        except PermissionError:
            print("Oops!  That was no valid operation.  Try again...")
        """

        # Redirect again the std output to screen
        ##sys.stdout = old_stdout

        # Then, get the stdout like a string and process it!
        ##result_string = result.getvalue()
        ##self.list.ids.errors.add_widget(Label(text=result_string, font_size="20sp"))

        self._do_update_progress_bar(0)  # Reset

        if self.success:
            self.list.ids.errors.add_widget(
                Label(text="successful operation", font_size="28sp", color=[0, 1, 0, 1])
            )

            self.l.text = "Processing completed."
            self.alertMessage.text = "successful operation."


if __name__ == "__main__":
    MainApp().run()
