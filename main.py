import sys
from pathlib import Path

print(">>>> WITNESS ANGEL PYTHON VERSION: %s <<<<" % sys.version)

if __name__ == "__main__":
    from wacomponents.launcher import launch_main_module_with_crash_handler
    launch_main_module_with_crash_handler("waauthenticator.waauthenticator_gui", client_type="APPLICATION")
