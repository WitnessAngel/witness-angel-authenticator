
from enum import Enum, unique
from textwrap import dedent

from functools import partial

import shutil
import functools
from pathlib import Path

from kivy.factory import Factory
from kivy.lang import Builder
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.screen import Screen

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


Builder.load_file(str(Path(__file__).parent / 'authenticator_creation_form.kv'))


THREAD_POOL_EXECUTOR = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="keygen_worker"  # SINGLE worker for now, to avoid concurrency
)

GENERATED_KEYS_COUNT = 7


class AuthenticatorCreationScreen(Screen):

    _selected_authenticator_path = ObjectProperty(None, allownone=True)

    def go_to_home_screen(self):
        self.manager.current = "keyring_selector_screen"


    def get_form_values(self):
        return dict(user=self.ids.formfield_username.text.strip(),
                    passphrase=self.ids.formfield_passphrase.text.strip(),
                    passphrase_hint=self.ids.formfield_passphrasehint.text.strip())

    def show_validate(self):

        if not self.authentication_device_selected:
            return  # Abormal state of button, which should be disabled...

        form_values = self.get_form_values()

        if all(form_values.values()):
            self.initialize_authentication_device(form_values=form_values)
        else:
            user_error = "Please enter a username, passphrase and passphrase hint."
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
            #if not first_device_list_item:
            #    first_device_list_item = device_list_item

        #self.screen.add_widget(self.keygen_panel)

        #if first_device_list_item:
        #    self.show_authentication_device_info(first_device_list_item, list_item_index=0)

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


    def set_form_fields_status(self, enabled):

        form_ids=self.ids
        form_fields = [
            form_ids.formfield_username,
            form_ids.formfield_passphrase,
            form_ids.formfield_passphrasehint,
        ]

        for text_field in form_fields:
            text_field.focus = False
            text_field.disabled = not enabled
            Animation.cancel_all(text_field, "fill_color", "_line_width", "_hint_y", "_hint_lbl_font_size")  # Unfocus triggered an animation, we must disable it
            if enabled:
                #text_field.fill_color = self.COLORS.LIGHT_GREY
                text_field.text = ""  # RESET
            else:
                pass #text_field.fill_color = self.COLORS.DARK_GREY

    def update_progress_bar(self, percent):
        #print(">>>>>update_progress_bar")
        Clock.schedule_once(partial(self._do_update_progress_bar, percent))

    def _do_update_progress_bar(self, percent, *args, **kwargs):
        #print(">>>>>>", self.ids)
        self.ids.barProgress.value = percent

    def initialize_authentication_device(self, form_values):
        self.status_title.text = "Please wait a few seconds."
        self.status_message.text = "The operation is being processed."

        self.ids.btn_refresh.disabled = True

        self.ids.button_initialize.disabled = True
        self.ids.formfield_passphrase.text = "***"  # PRIVACY

        for device_list_item in list(self.ids.authentication_device_list.children):
            #device_list_item.bg_color=self.COLORS.LIGHT_GREY Nope
            device_list_item.unbind(on_release=device_list_item._onrelease_callback)

        self.set_form_fields_status(enabled=False)

        THREAD_POOL_EXECUTOR.submit(self._offloaded_initialize_rsa_key, form_values=form_values)

    def finish_initialization(self, *args, success, **kwargs):

        self.ids.btn_refresh.disabled = False
        self._do_update_progress_bar(0)  # Reset

        if success:
            self.status_title.text = "Processing completed"
            self.status_message.text = "Operation successful"
        else:
            self.status_title.text = "Errors occurred"
            self.status_message.text = "Operation failed, check logs"
