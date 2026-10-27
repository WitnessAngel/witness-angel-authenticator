"""Recorder entry point (the Authenticator's is main.py): GUI, or `--service` for the background service."""
import sys

from waflet_recorder.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
