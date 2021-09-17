
from enum import Enum, unique
from textwrap import dedent

from functools import partial

import shutil
import functools
from pathlib import Path

from kivy.factory import Factory
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.screen import Screen


Builder.load_file(str(Path(__file__).parent / 'authenticator_creation_form.kv'))




class AuthenticatorCreationScreen(Screen):
    pass
