import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.append(str(Path(__file__).parent.joinpath("src")))

    from wacomponents.launcher import launch_main_module_with_crash_handler
    launch_main_module_with_crash_handler("waauthenticator.waauthenticator_gui", client_type="APPLICATION")
