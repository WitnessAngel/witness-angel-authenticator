Witness Angel - Authenticator Manager
########################################

This cross-platform app allows "Key Guardians" of the Witness Angel ecosystem
to create and edit "authenticators", i.e. folders or devices containing a set
of public/private keypairs for use with "write only" encryption systems.

Instead of pip, we use `poetry <https://github.com/sdispater/poetry>`_ to install dependencies.

After installing Poetry itself, run this command in repo root, to install python dependencies::

    $ poetry install

Then run the program with::

    $ poetry run python main.py

Or if you're already inside the proper python virtualenv (e.g. in a `poetry shell`)::

    $ python main.py

To generate an executable version of the program (only tested on Windows)::

    $ python -m PyInstaller pyinstaller.spec

    Note that arguments like "--windowed --onefile" are overridden by the content of the spec file
