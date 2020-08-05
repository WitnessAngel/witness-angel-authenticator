from kivy.lang import Builder
from kivy.uix.progressbar import ProgressBar
from kivy.factory import Factory
from kivy.uix.image import Image
from kivy.uix.gridlayout import GridLayout
from kivymd.app import MDApp
from kivymd.uix.list import IRightBodyTouch, ILeftBody, MDList
from kivymd.uix.selectioncontrol import MDCheckbox
from key_device import list_available_key_devices,initialize_key_device,_get_metadata_file_path
from kivy.uix.scrollview import ScrollView
from kivymd.uix.button import MDRectangleFlatButton, MDFlatButton
from kivymd.uix.screen import Screen
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import Label
from wacryptolib.key_generation import generate_asymmetric_keypair
from wacryptolib.key_storage import FilesystemKeyStorage
from wacryptolib.utilities import load_from_json_file
from kivy.clock import Clock
import sys
from io import StringIO
from wacryptolib.utilities import generate_uuid0


class MyCheckbox(IRightBodyTouch, MDCheckbox):
    pass


class MyAvatar(ILeftBody, Image):
    pass


# FIXME, the project must only contain necessary icons and at proper resolutions (here Witness_Angel_LogotypeX.png are huge)

# FIXME - fix incorrect margins around main title etc.
# FIXME - selected usb key doesn't appear highlighted it seems
# FIXME - all fields and controls in the bottom must be disabled as long as no usb key is selected

class MainApp(MDApp):

    def __init__(self, **kwargs):
        self.title = "Witness Angel - WardProject"
        super(MainApp, self).__init__(**kwargs)

    def show_validate(self):

        if  self.key_device_selected== None:  # FIXME when I refresh, usb key must be properly deselected
            user_error = "Please select USB"
            title_dialog="USB not selected !!"
            self.open_dialog(user_error,title_dialog)
        else:
            # FIXME use "==" or here juste "if variable", almost never is (except "is None")
            # FIXME beware of FORMATTING (use Black)
            if (self.list.ids.userfield.text is not "" )and(self.list.ids.passphrasefield.text is not "" ):
                self.initialize_USB()
            elif (self.list.ids.userfield.text is "" )and(self.list.ids.passphrasefield.text is "" ):
                user_error = "Please enter a username and a passphrase"
                self.open_dialog(user_error)
            elif(self.list.ids.userfield.text is "" ):  # FIXME no need to try all combinations, if any of them is missing just say "Please enter a username and a passphrase", it will suffice and simplify code here
                user_error = "Please enter a username"
                self.open_dialog(user_error)
            elif (self.list.ids.passphrasefield.text is ""):
                user_error = "Please enter a passphrase"
                self.open_dialog(user_error)

    def open_dialog(self,user_error,title_dialog='Please fill in the empty field'):
        self.dialog = MDDialog(title=title_dialog,
                               text=user_error, size_hint=(0.8, 1),
                               buttons=[MDFlatButton(text='Close', on_release=self.close_dialog)]
                               )
        self.dialog.open()

    def close_dialog(self,obj):
        self.dialog.dismiss()

    def createList(self):  # FIXME wrong naming case
        self.list = Factory.Lists()
        self.screen.add_widget(self.list)
        self.list = Factory.Lists()
        list_devices = list_available_key_devices()
        for index, usb in enumerate(list_devices):
            self.lineCheck = Factory.ListItemWithCheckbox(text="Path :%s" % (str(usb["path"])),secondary_text="Label : %s" % (str(usb["label"])))
            self.lineCheck.bind(on_release=self.key_device_selected_fct)
            self.list.ids.scroll.add_widget(self.lineCheck)
            self.screen.add_widget(self.list)

    def refresh_list(self):

        self.screen.remove_widget(self.list)
        self.createList()



    def initialize_7_RSA_key_USB(self):  # FIXME wrong naming case

        initialize_key_device(self.key_device_selected, self.list.ids.userfield.text)
        metadata_file = _get_metadata_file_path(self.key_device_selected)
        metadata_folder=metadata_file.parent
        private_key_dir = metadata_folder.joinpath("private_key")
        private_key_dir.mkdir(exist_ok=True)
        object_FilesystemKeyStorage = FilesystemKeyStorage(private_key_dir)
        #7
        for i in range(2):
            key_pair = generate_asymmetric_keypair(key_type="RSA_OAEP",passphrase=self.list.ids.passphrasefield.text.encode())
            object_FilesystemKeyStorage.set_keys(keychain_uid=generate_uuid0(), key_type='RSA_OAEP',public_key=key_pair['public_key'], private_key=key_pair['private_key'])
        self.success = True



    def retry_initialisation(self):  # FIXME this "retry" button seems useless, we already have a "refresh"
        self.refresh_list()


    def build(self):
        self.key_device_selected = None
        self.orientation = 'vertical'
        self.screen = Screen()
        self.createList()
        return self.screen

    def key_device_selected_fct(self,linelist):  # FIXME wrong naming
        list_devices = list_available_key_devices()
        for index, key_device in enumerate(list_devices):
            if linelist.text == "Path :" + str(key_device["path"]):
                self.key_device_selected=key_device
                print(key_device["is_initialized"])
                if str(key_device["is_initialized"])=="True":
                    self.l = Label(text="USB information : Size %s   |   Fst :%s | and it is initialized" % (str(key_device["size"]), str(key_device["format"])))
                    self.alertMessage= Label(text="You have to format the key or manually delete the private folder" )
                    self.list.ids.button_initialize.disabled = True
                    meta = load_from_json_file(key_device["path"] + "\.key_storage\.metadata.json")
                    self.list.ids.userfield.text= meta["user"]
                else:
                    self.l = Label(text="USB information : Size %s   |   Fst :%s | and it is not initialized" % (str(key_device["size"]), str(key_device["format"])))
                    self.alertMessage = Label(text="Please fill in the username and passphrase to initialize the usb key")
                self.list.ids.labelInfoUsb1.add_widget(self.l)
                self.list.ids.label_alert.add_widget(self.alertMessage)

    def waiting_message(self):  # FIXME wrong naming
        self.l.text = "Please wait a few seconds."
        self.alertMessage.text = "the operation is being processed."

    def initialize_USB(self):  # FIXME wrong naming case
        self.waiting_message()

        # Store the reference, in case you want to show things again in standard output
        old_stdout = sys.stdout

        # This variable will store everything that is sent to the standard output
        result = StringIO()
        sys.stdout = result


        try:
            self.initialize_7_RSA_key_USB()
        except PermissionError:
            print("Oops!  That was no valid operation.  Try again...")



        # Redirect again the std output to screen
        sys.stdout = old_stdout

        # Then, get the stdout like a string and process it!
        result_string = result.getvalue()
        self.list.ids.errors.add_widget(Label(text=result_string, font_size='20sp'))
        self.success_message()

        # FIXME also refresh keys?

    def success_message(self):  # FIXME wrong naming
        if self.success :
            self.list.ids.errors.add_widget(Label(text="successful operation", font_size='20sp'))
            self.list.ids.button_initialize.disabled = True
            self.l.text = "Processing completed."
            self.alertMessage.text = "successful operation."





if __name__ == "__main__":
    MainApp().run()
