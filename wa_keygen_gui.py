import sys, os

#if sys.platform == "win32":
#    os.environ["KIVY_GL_BACKEND"] = "angle_sdl2"

from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.factory import Factory
from kivy.uix.image import Image
from kivymd.app import MDApp
from kivymd.uix.list import IRightBodyTouch, ILeftBody
from kivymd.uix.selectioncontrol import MDCheckbox
from wacryptolib.authentication_device import (
    list_available_authentication_devices,
    initialize_authentication_device,
    _get_key_storage_folder_path, load_authentication_device_metadata,
)
from kivymd.uix.button import  MDFlatButton
from kivymd.uix.screen import Screen
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import Label
from wacryptolib.key_generation import generate_asymmetric_keypair
from wacryptolib.key_storage import FilesystemKeyStorage

from wacryptolib.utilities import generate_uuid0

'''
class MyCheckbox(IRightBodyTouch, MDCheckbox):
    pass


class MyAvatar(ILeftBody, Image):
    pass
'''

THREAD_POOL_EXECUTOR = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="keygen_worker"  # SINGLE worker for now, to avoid concurrency
)

GENERATED_KEYS_COUNT = 7


class MainApp(MDApp):

    kv_file = "wa_keygen_gui.kv"
    keygen_panel = None

    authentication_device_list = ()
    authentication_device_selected = None

    def __init__(self, **kwargs):
        self.title = "Witness Angel - WardProject"
        super(MainApp, self).__init__(**kwargs)

    def get_form_values(self):
        return dict(user=self.keygen_panel.ids.userfield.text.strip(),
                    passphrase=self.keygen_panel.ids.passphrasefield.text.strip(),
                    passphrase_hint=self.keygen_panel.ids.passphrasehintfield.text.strip())

    def show_validate(self):

        if not self.authentication_device_selected:
            return  # Abormal state of button, which should be disabled...

        form_values = self.get_form_values()

        if all(form_values.values()):
            self.initialize(form_values=form_values)
        else:
            user_error = "Please enter a username, passphrase and passphrase_hint."
            self.open_dialog(user_error)

    def open_dialog(self, main_text, title_dialog="Please fill in empty fields"):
        self.dialog = MDDialog(
            title=title_dialog,
            text=main_text,
            size_hint=(0.8, 1),
            buttons=[MDFlatButton(text="Close", on_release=self.close_dialog)],
        )
        self.dialog.open()

    def close_dialog(self, obj):
        self.dialog.dismiss()

    def list_detected_devices(self):
        self.keygen_panel = Factory.KeygenPanel()
        authentication_device_list = list_available_authentication_devices()
        self.authentication_device_list = authentication_device_list

        for index, usb in enumerate(authentication_device_list):
            self.lineCheck = Factory.ListItemWithCheckbox(
                text="[color=#FFFFFF][b]Path:[/b] %s[/color]" % (str(usb["path"])),
                secondary_text="[color=#FFFFFF][b]Label:[/b] %s[/color]" % (str(usb["label"])),
                bg_color=[0.1372, 0.2862, 0.5294, 1],

            )
            self.lineCheck.bind(on_release=self.get_info_key_selected)
            self.keygen_panel.ids.scroll.add_widget(self.lineCheck)
        self.screen.add_widget(self.keygen_panel)

    def _offloaded_initialize_rsa_key(self, form_values):

        success = False

        try:

            #print(">starting initialize_rsa_key")

            Clock.schedule_once(partial(self._do_update_progress_bar, 10))

            initialize_authentication_device(self.authentication_device_selected,
                                             user=form_values["user"],
                                             extra_metadata=dict(passphrase_hint=form_values["passphrase_hint"]))
            key_storage_folder = _get_key_storage_folder_path(self.authentication_device_selected)
            assert key_storage_folder.is_dir()  # By construction...

            object_FilesystemKeyStorage = FilesystemKeyStorage(key_storage_folder)

            for i in range(1, GENERATED_KEYS_COUNT+1):
                #print(">WIP initialize_rsa_key", id)
                key_pair = generate_asymmetric_keypair(
                    key_type="RSA_OAEP",
                    passphrase=form_values["passphrase"]
                )
                object_FilesystemKeyStorage.set_keys(
                    keychain_uid=generate_uuid0(),
                    key_type="RSA_OAEP",
                    public_key=key_pair["public_key"],
                    private_key=key_pair["private_key"],
                )

                Clock.schedule_once(partial(self._do_update_progress_bar, 10 + int (i * 90 / GENERATED_KEYS_COUNT)))

            success = True

        except Exception as exc:
            print(">>>>>>>>>> ERROR IN THREAD", exc)  # FIXME add logging

        Clock.schedule_once(partial(self.finish_initialization, success=success))

    def build(self):
        self.authentication_device_selected = None
        self.orientation = "vertical"
        self.screen = Screen()
        self.list_detected_devices()
        return self.screen

    def get_info_key_selected(self, linelist):
        list_ids=self.keygen_panel.ids
        text_fields = [
            list_ids.userfield,
            list_ids.passphrasefield,
            list_ids.passphrasehintfield,
        ]

        authentication_device_list = self.authentication_device_list
        for i in list_ids.scroll.children:
            i.bg_color = [0.1372, 0.2862, 0.5294, 1]
        linelist.bg_color = [0.6, 0.6, 0.6, 1]

        list_ids.button_initialize.disabled = False

        for text_field in text_fields:
            text_field.focus = False
            text_field.disabled = False
            Animation.cancel_all(text_field, "fill_color", "_line_width", "_hint_y", "_hint_lbl_font_size")  # Unfocus triggered an animation
            text_field.fill_color = [1, 1, 1, 0.4]
            text_field.text = ""

        self.l = Label(text="")
        self.alertMessage = Label(text="")
        list_ids.labelInfoUsb1.clear_widgets()
        list_ids.label_alert.clear_widgets()
        list_ids.labelInfoUsb1.add_widget(self.l)
        list_ids.label_alert.add_widget(self.alertMessage)
        for index, authentication_device in enumerate(authentication_device_list):
            if linelist.text == "[color=#FFFFFF][b]Path:[/b] " + str(authentication_device["path"]) + "[/color]":  # FIXME
                self.authentication_device_selected = authentication_device
                if authentication_device["is_initialized"]:
                    list_ids.button_initialize.disabled = True

                    for text_field in text_fields:
                        text_field.disabled = True
                        text_field.fill_color = [0.3, 0.3, 0.3, 0.4]

                    self.alertMessage = Label(
                        text="To reset the USB key, manually delete the key-storage folder on it"
                    )
                    try:
                        metadata = load_authentication_device_metadata(authentication_device)
                    except FileNotFoundError:
                        pass  # User has removed the key or folder in the meantime...
                    else:
                        list_ids.userfield.text = metadata["user"]
                        list_ids.passphrasehintfield.text = metadata.get("passphrase_hint", "")

                else:

                    self.alertMessage = Label(
                        text="Please fill in the form below to initialize the usb key"
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
        #print(">>>>>>", self.keygen_panel.ids)
        self.keygen_panel.ids.barProgress.value = percent

    def initialize(self, form_values):
        self.l.text = "Please wait a few seconds."
        self.alertMessage.text = "The operation is being processed."
        self.keygen_panel.ids.btn_refresh.disabled = True
        self.keygen_panel.ids.button_initialize.disabled = True
        self.keygen_panel.ids.passphrasefield.text = "***"  # PRIVACY
        for c in list(self.keygen_panel.ids.scroll.children):
            c.bg_color=[1, 1, 1, 0.4]
        #self.keygen_panel.ids.scroll.bg_color=[1, 0.2862, 0.5294, 1]
        self.lineCheck.unbind(on_release=self.get_info_key_selected)

        THREAD_POOL_EXECUTOR.submit(self._offloaded_initialize_rsa_key, form_values=form_values)

    def finish_initialization(self, *args, success, **kwargs):

        self.keygen_panel.ids.btn_refresh.disabled = False
        self._do_update_progress_bar(0)  # Reset

        if success:
            #self.keygen_panel.ids.errors.add_widget(
            #    Label(text="Initialization successful", font_size="28sp", color=[0, 1, 0, 1])
            #)

            self.l.text = "Processing completed"
            self.alertMessage.text = "Operation successful"
        else:
            self.l.text = "Errors occurred"
            self.alertMessage.text = "Operation failed, check logs"


def resourcePath():
    '''Returns path containing content - either locally or in pyinstaller tmp file'''
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS)

    return os.path.join(os.path.abspath("."))


if __name__ == "__main__":
    import kivy.resources
    kivy.resources.resource_add_path(resourcePath()) # Pyinstaller workaround
    MainApp().run()
