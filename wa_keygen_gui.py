import sys, os

#if sys.platform == "win32":
#    os.environ["KIVY_GL_BACKEND"] = "angle_sdl2"

from concurrent.futures.thread import ThreadPoolExecutor
from functools import partial

from kivy.core.window import Window
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

    class COLORS:
        LIGHT_GREY = [1, 1, 1, 0.4]
        MEDIUM_GREY = [0.6, 0.6, 0.6, 1]
        DARK_GREY = [0.3, 0.3, 0.3, 0.4]
        DARKEST_BLUE = [0.1372, 0.2862, 0.5294, 1]
        DARK_BLUE = [0.1272, 0.2662, 0.4294, 1]
        BUTTON_BACKGROUND = [51, 23, 186, 1]  # Not same format as others, as its' a tint
        WHITE = [1, 1, 1, 1]

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
            self.initialize_authentication_device(form_values=form_values)
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

        for index, authentication_device in enumerate(authentication_device_list):
            device_list_item = Factory.ListItemWithCheckbox(
                text="[color=#FFFFFF][b]Path:[/b] %s[/color]" % (str(authentication_device["path"])),
                secondary_text="[color=#FFFFFF][b]Label:[/b] %s[/color]" % (str(authentication_device["label"])),
                bg_color=self.COLORS.DARK_BLUE,
            )
            device_list_item._onrelease_callback = partial(self.show_authentication_device_info, list_item_index=index)
            device_list_item.bind(on_release=device_list_item._onrelease_callback)
            self.keygen_panel.ids.scroll.add_widget(device_list_item)
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

            filesystem_key_storage = FilesystemKeyStorage(key_storage_folder)

            for i in range(1, GENERATED_KEYS_COUNT+1):
                #print(">WIP initialize_rsa_key", id)
                key_pair = generate_asymmetric_keypair(
                    key_type="RSA_OAEP",
                    passphrase=form_values["passphrase"]
                )
                filesystem_key_storage.set_keys(
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

        # Ensure that we don't need to click TWICE to gain focus on Kivy Window and then on widget!
        def force_window_focus(*args, **kwargs):
            Window.raise_window()
        Window.bind(on_cursor_enter=force_window_focus)

        self.authentication_device_selected = None
        self.orientation = "vertical"
        self.screen = Screen()
        self.list_detected_devices()
        return self.screen

    def set_form_fields_status(self, enabled):

        keygen_panel_ids=self.keygen_panel.ids
        form_fields = [
            keygen_panel_ids.userfield,
            keygen_panel_ids.passphrasefield,
            keygen_panel_ids.passphrasehintfield,
        ]

        for text_field in form_fields:
            text_field.focus = False
            text_field.disabled = not enabled
            Animation.cancel_all(text_field, "fill_color", "_line_width", "_hint_y", "_hint_lbl_font_size")  # Unfocus triggered an animation, we must disable it
            if enabled:
                text_field.fill_color = self.COLORS.LIGHT_GREY
                text_field.text = ""  # RESET
            else:
                text_field.fill_color = self.COLORS.DARK_GREY

    def show_authentication_device_info(self, list_item_obj, list_item_index):

        keygen_panel_ids=self.keygen_panel.ids

        authentication_device_list = self.authentication_device_list
        for i in keygen_panel_ids.scroll.children:
            i.bg_color = self.COLORS.DARK_BLUE

        list_item_obj.bg_color = self.COLORS.MEDIUM_GREY

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

    def update_progress_bar(self, percent):
        #print(">>>>>update_progress_bar")
        Clock.schedule_once(partial(self._do_update_progress_bar, percent))

    def _do_update_progress_bar(self, percent, *args, **kwargs):
        #print(">>>>>>", self.keygen_panel.ids)
        self.keygen_panel.ids.barProgress.value = percent

    def initialize_authentication_device(self, form_values):
        self.status_title.text = "Please wait a few seconds."
        self.status_message.text = "The operation is being processed."

        self.keygen_panel.ids.btn_refresh.disabled = True

        self.keygen_panel.ids.button_initialize.disabled = True
        self.keygen_panel.ids.passphrasefield.text = "***"  # PRIVACY

        for device_list_item in list(self.keygen_panel.ids.scroll.children):
            #device_list_item.bg_color=self.COLORS.LIGHT_GREY Nope
            device_list_item.unbind(on_release=device_list_item._onrelease_callback)

        self.set_form_fields_status(enabled=False)

        THREAD_POOL_EXECUTOR.submit(self._offloaded_initialize_rsa_key, form_values=form_values)

    def finish_initialization(self, *args, success, **kwargs):

        self.keygen_panel.ids.btn_refresh.disabled = False
        self._do_update_progress_bar(0)  # Reset

        if success:
            self.status_title.text = "Processing completed"
            self.status_message.text = "Operation successful"
        else:
            self.status_title.text = "Errors occurred"
            self.status_message.text = "Operation failed, check logs"


def resourcePath():
    '''Returns path containing content - either locally or in pyinstaller tmp file'''
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS)

    return os.path.join(os.path.abspath("."))


if __name__ == "__main__":
    import kivy.resources
    kivy.resources.resource_add_path(resourcePath()) # Pyinstaller workaround
    MainApp().run()
