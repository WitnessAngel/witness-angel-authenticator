Witness Angel Authenticator
##################################

Presentation
===============================

This cross-platform app allows trusted third parties of the Witness Angel ecosystem, called "Key Guardians",
to create and edit their "authenticators" (digital identities and secure keychains).

These digital identities can be published to a web registry, so that Witness Angel devices can easily retrieve them to secure their local recordings. The application also allows the user to accept/reject authorization requests, emitted when someone needs to decrypt recordings for judicial processes.

More generally, this app can be used for any workflow where sensitive data must be protected by remote individuals, especially in "shared secret" encryption schemes.

Application homepage with download links: https://witnessangel.com/en/authenticator-application/


Getting started with development
=======================================

Instead of pip, we use `poetry <https://github.com/sdispater/poetry>`_ to install dependencies.

After installing Poetry itself, run this command in repository root, to install python dependencies::

    $ poetry install

Then run the program with::

    $ poetry run python main.py

Or if you're already inside the proper python virtualenv (e.g. in a `poetry shell`), use::

    $ python main.py

To only launch the recorder service, not the GUI application, end this command with "main.py --service" (the GUI itself relaunches the recorder service if it's not active).

To generate an executable version of the program for Windows/MacOs/Linux::

    $ pip install -U pyinstaller
    $ python -m PyInstaller pyinstaller.spec

    Note that arguments like "--windowed --onefile" are overridden by the content of the spec file

    On MacOS, setting MACOS_CODESIGN_IDENTITY environment variable is necessary

To build the Android app (debug, or a signed production bundle) with the **16 KB memory
page-size support** that Google Play requires for Android 15+, see the dedicated section
`Building for Android (16 KB page size)`_ below. The build runs in a reproducible Podman
container, so it works from any host (Windows/macOS/Linux).

To create an iOS release, it's more complicated (buildozer failed so far), see https://kivy.org/doc/stable/guide/packaging-ios.html

To force the startup language of the GUI application, set the "LANG" environment variable to "fr" or "en".


Building for Android (16 KB page size)
=======================================

Since November 1st, 2025, Google Play requires every app targeting Android 15+ to support
**16 KB memory page sizes** on 64-bit devices. We build with **buildozer master +
python-for-android `develop` + Python 3.14 + Android API 36 + NDK r29**, which produces
16 KB-aligned ``arm64-v8a`` / ``x86_64`` libraries. ``buildozer.spec`` is already configured
for this (``android.api = 36``, ``android.ndk = 29``, ``p4a.branch = develop``,
``p4a.commit`` pinned).

The build runs inside a reproducible **Podman** (Docker-free) Ubuntu 24.04 container, so it
no longer requires a Linux host. A deeper runbook (troubleshooting, exact tool versions, the
dependency fixes for Python 3.14) lives in ``scripts/README_android_16kb_build.md``.

Prerequisites
-------------------------------

- Install `Podman <https://podman.io/>`_ and start its machine. On this Windows host the CLI
  is not on ``PATH``; reference it by absolute path and define a shell variable once per
  Git Bash session (Linux/macOS users can just use ``podman``)::

    $ PODMAN="/c/Users/chamb/AppData/Local/Programs/Podman/podman.exe"
    $ "$PODMAN" --version                 # 5.8.2+
    $ "$PODMAN" machine start             # if not already running

- The project here lives on the removable ``P:`` drive, which the Podman WSL machine does not
  auto-mount. Mount it once (persists across reboots via the machine's ``/etc/fstab``)::

    $ MSYS_NO_PATHCONV=1 "$PODMAN" machine ssh \
        "grep -q '/mnt/p drvfs' /etc/fstab || echo 'P: /mnt/p drvfs metadata,uid=1000,gid=1000,umask=022 0 0' | sudo tee -a /etc/fstab; sudo mount /mnt/p"

  Because of this, ``podman`` bind mounts must use ``MSYS_NO_PATHCONV=1`` and a Windows-style
  source path (``'P:\\...'``), not the ``/p/...`` form (Git Bash would mangle it). If your
  checkout is on a fixed drive (``C:``/``D:``) you can skip the mount step and adjust the paths.

One-time setup
-------------------------------

Pull the base image, create a persistent cache volume, and build the toolchain image
(installs Python 3.14, buildozer master, Rust, Cython 3.0.12, NDK build deps)::

    $ cd /p/Workspace/WitnessAngel/witness-angel-authenticator
    $ "$PODMAN" pull docker.io/library/ubuntu:24.04
    $ "$PODMAN" volume create wa_build_home
    $ "$PODMAN" build -t wa-authenticator-build:16kb - < Containerfile

The image build is piped from ``Containerfile`` via stdin on purpose (the ``P:`` drive breaks
the normal build-context upload). It takes ~10-15 min the first time.

Vendor the sub-packages (required before every build)
------------------------------------------------------------

The app depends on the ``wacryptolib`` and ``wacomponents`` packages, which live in sibling
Git checkouts (``../witness-angel-cryptolib`` and ``../witness-angel-components``). On desktop
they are pip-installed; for Android they must sit as plain source dirs at the project root so
``source.dir = .`` bundles them into the APK. They are **git-ignored** here and must be
populated, or the app crashes on launch with ``ModuleNotFoundError: wacomponents``.

A symlink would dangle inside the build container (only this project dir is bind-mounted, not
its siblings), so copy the real sources with the helper script::

    $ bash scripts/sync_android_subpackages.sh
    # override locations if needed:
    # CRYPTOLIB_SRC=/path/to/witness-angel-cryptolib/src \
    # COMPONENTS_SRC=/path/to/witness-angel-components/src bash scripts/sync_android_subpackages.sh

Re-run this whenever those packages change.

Debug build
-------------------------------

Build a debug APK. The first run also downloads the Android SDK + NDK r29 and compiles every
recipe, so it is long; caches in the ``wa_build_home`` volume make later builds much faster.
For fast iteration you may temporarily set ``android.archs = arm64-v8a`` in ``buildozer.spec``::

    $ MSYS_NO_PATHCONV=1 "$PODMAN" run --rm \
        -v 'P:\\Workspace\\WitnessAngel\\witness-angel-authenticator:/kivy_app_build' \
        -v 'wa_build_home:/root' \
        wa-authenticator-build:16kb \
        bash -lc "cd /kivy_app_build && source /opt/venv_p4a_develop/bin/activate && buildozer -v android debug"

The signed/unsigned APK is written to ``bin/`` on the host (the project is bind-mounted).

Verify 16 KB alignment (every 64-bit ``.so`` must be ``0x4000``-aligned; 32-bit archs are
exempt; the non-ELF ``libpybundle.so`` data blob is skipped)::

    $ MSYS_NO_PATHCONV=1 "$PODMAN" run --rm \
        -v 'P:\\Workspace\\WitnessAngel\\witness-angel-authenticator:/kivy_app_build' \
        wa-authenticator-build:16kb \
        bash -lc 'cd /kivy_app_build && bash scripts/check_16kb_alignment.sh bin/*.apk'

A passing run ends with ``RESULT: PASS``.

Run it on a device
-------------------------------

The container builds the artifact but cannot reach USB devices. Install/run the produced APK
from the host with the Android platform-tools (``adb`` already on this machine's ``PATH``)::

    $ adb install -r bin/authenticator-*-debug.apk
    $ adb shell monkey -p org.witnessangel.authenticator -c android.intent.category.LAUNCHER 1
    $ adb logcat | grep -i python      # view app logs

Production build (signed .aab, with secrets)
----------------------------------------------------

Google Play needs a signed Android App Bundle (``android.release_artifact = aab``). Signing
uses python-for-android's ``P4A_RELEASE_*`` environment variables. **Never commit the keystore
or its passwords** - ``witnessangel_android.keystore`` is git-ignored (``*.keystore``), and the
helper script below prompts for passwords without storing, logging, or exposing them in the
process list.

You need the keystore file at the repo root and its **alias**. If you don't remember the
alias, list it (prompts for the store password)::

    $ keytool -list -keystore witnessangel_android.keystore

Then run the signing wrapper **interactively** (it prompts for alias + passwords)::

    $ bash scripts/build_release_signed.sh
    Keystore alias: <your-alias>
    Keystore (store) password: ********
    Key password [blank = same as store]: ********

It produces ``bin/authenticator-<version>-release.aab``. Verify its alignment before
uploading to the Play Console::

    $ MSYS_NO_PATHCONV=1 "$PODMAN" run --rm \
        -v 'P:\\Workspace\\WitnessAngel\\witness-angel-authenticator:/kivy_app_build' \
        wa-authenticator-build:16kb \
        bash -lc 'cd /kivy_app_build && bash scripts/check_16kb_alignment.sh bin/*.aab'

The wrapper sets these variables for the build (only the last two are secret):

================================  ====================================================  ========
Variable                          Meaning                                               Secret
================================  ====================================================  ========
``P4A_RELEASE_KEYSTORE``          in-container path to the keystore                     no
``P4A_RELEASE_KEYALIAS``          key alias                                             no
``P4A_RELEASE_KEYSTORE_PASSWD``   keystore (store) password                             yes
``P4A_RELEASE_KEYALIAS_PASSWD``   key password                                          yes
================================  ====================================================  ========


