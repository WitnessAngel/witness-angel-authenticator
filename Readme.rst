Witness Angel Keygen
#############################

This Kivy GUI allows one to list and initialize WitnessAngel "authentication devices",
i.e. USB keys containing a set of public/private keypairs for use with "write only"
encryption systems.

Instead of pip, we use `poetry <https://github.com/sdispater/poetry>`_ to install dependencies.

Afyer installing Poetry itself, run this command to install python dependencies::

    $ poetry install

Then run the program with::

    $ poetry run python wa_keygen_gui.py

Or if you're already inside the proper python virtualenv (e.g. in a `poetry shell`)::

    $ python wa_keygen_gui.py

To generate an executable version of the keygen (only tested on Windows)::

    $ python -m PyInstaller wa_keygen_gui.spec
