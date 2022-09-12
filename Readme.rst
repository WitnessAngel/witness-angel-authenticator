Witness Angel Authenticator
##################################

Application homepage: https://witnessangel.com/en/authenticator-application/

This cross-platform app allows trusted third parties of the Witness Angel ecosystem, called "Key Guardians",
to create and edit their "authenticators" (digital identities and secure keychains).

These digital identities can be published to a web registry, so that Witness Angel devices can easily retrieve them to secure their local recordings. The application also allows the user to accept/reject authorization requests, emitted when someone needs to decrypt recordings for judicial processes.

More generally, this app can be used for any workflow where sensitive data must be protected by remote individuals, especially in "shared secret" encryption schemes.


Getting started
==================

Instead of pip, we use `poetry <https://github.com/sdispater/poetry>`_ to install dependencies.

After installing Poetry itself, run this command in repository root, to install python dependencies::

    $ poetry install

Then run the program with::

    $ poetry run python main.py

Or if you're already inside the proper python virtualenv (e.g. in a `poetry shell`), use::

    $ python main.py

To only launch the recorder service, not the GUI application, end this command with "main.py --service" (the GUI itself relaunches the recorder service if it's not active).

To generate an executable version of the program::

    $ pip install -U pyinstaller
    $ python -m PyInstaller pyinstaller.spec

    Note that arguments like "--windowed --onefile" are overridden by the content of the spec file

To build a debug APK and deploy it via USB on an android device (only works on Linux)::

    Create local symlinks "wacryptolib/" and "wacomponents/", pointing to "src/" folders of these Git repositories.

    Install "buildozer" with pip.

    And then do:

    $ buildozer android debug deploy run logcat

To force the startup language of the GUI application, set the "LANG" environment variable to "fr" or "en".


