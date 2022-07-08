Witness Angel Authenticator
##################################

Application homepage: https://witnessangel.com/en/authenticator-application/

This cross-platform app allows "Key Guardians" of the Witness Angel ecosystem
to create and edit their "authenticators".

These authenticators are actually sets of public/private keypairs, for use with "write only" encryption systems like FlightBox.

Instead of pip, we use `poetry <https://github.com/sdispater/poetry>`_ to install dependencies.

After installing Poetry itself, run this command in repository root, to install python dependencies::

    $ poetry install

Then run the program with::

    $ poetry run python main.py

Or if you're already inside the proper python virtualenv (e.g. in a `poetry shell`), use::

    $ python main.py

To only launch the recorder service, not the GUI application, end this command with "main.py --service" (the GUi itself relaunches the recorder service if it's not active).

To generate an executable version of the program::

    $ pip install -U pyinstaller
    $ python -m PyInstaller pyinstaller.spec

    Note that arguments like "--windowed --onefile" are overridden by the content of the spec file

To build a debug APK and deploy it via USB on an android device (only works on Linux)::

    Install "buildozer" with pip, and then do:

    $ buildozer android debug deploy run logcat

To force the startup language of the GUI application, set the LANG environment variable to "fr" or "en".


