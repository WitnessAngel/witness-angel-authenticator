from wa_authenticator_gui import WaAuthenticatorApp

if __name__ == "__main__":
    from wacomponents.launcher import launch_app_or_service_with_crash_handler
    launch_app_or_service_with_crash_handler("wa_authenticator_gui", client_type="APPLICATION")