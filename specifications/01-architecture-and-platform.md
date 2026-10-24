# 01 - Architecture and platform specification

Witness Angel Authenticator, version 1.5 (`witness-angel-authenticator/waauthenticator/waauthenticator_gui.py:30`, `witness-angel-authenticator/pyproject.toml:8`).

Sibling files: [02](02-ux-and-screens.md) (screens and flows), [03](03-business-logic.md) (authenticator lifecycle, revelation requests), [04](04-data-and-protocols.md) (keystore on-disk format, gateway JSON-RPC, crypto), [05](05-open-issues.md) (open issues, `OI-nn`).

Conventions: citation prefixes and source baseline in the [README](README.md#source-baseline-and-citation-prefixes); normative tags in the [README](README.md#normative-language). This file owns: storage roots and folder access, config file, threading model, Back key, language detection, safe-area insets.

Structure of this document:

- Part A (sections 1-8): functional and platform requirements, written framework-neutrally. A reimplementation must keep these.
- Part B (sections 9-12): incidental Kivy/KivyMD/buildozer implementation details. They are documented for traceability and are not requirements.
- Section 13: pointer to the open issues ([05](05-open-issues.md)).

---

# PART A - Requirements a reimplementation must keep

## 1. Purpose, scope, actors

### 1.1 Purpose
A cross-platform app (Android, iOS, Windows, Linux, macOS) for "Key Guardians", the trusted third parties of the Witness Angel ecosystem. A guardian can (`AUTH/Readme.rst:4-12`):

- create an "authenticator": a passphrase-protected keystore holding asymmetric keypairs plus metadata;
- publish its public part to a web registry (the "gateway");
- accept or reject "revelation requests", emitted when someone needs to decrypt recordings (for example in judicial processes);
- manage, import, export and check the integrity of authenticators.

The app also fits any workflow where sensitive data is protected by remote individuals, especially shared-secret schemes (`AUTH/Readme.rst:13`).

### 1.2 Actors

| Actor | Role | Evidence |
|---|---|---|
| Key guardian | The app's user. Owns the authenticator and its passphrase, and answers requests. | `AUTH/Readme.rst:7` |
| Claimant / requestor | Another person or device that asks for decryption of recordings. It does not use this app. The app only receives their requests, through the gateway. | `AUTH/waauthenticator/waauthenticator_gui.kv:35-43` (revelation request screens) |
| Gateway | Remote web service, default `https://api.witnessangel.com/gateway/jsonrpc/`, reached over JSON-RPC. It is a registry of published authenticators and a mailbox of revelation requests. | `AUTH/waauthenticator/config_defaults.ini:5`, `COMP/application/_common_runtime_support.py:192-195` |
| Crash-report endpoint | `https://api.witnessangel.com/support/crashdumps/`, an HTTP POST target, hardcoded. | `COMP/launcher.py:69-71` |

### 1.3 Position in the ecosystem
Evidenced in code: the Witness Angel Recorder (and any "revelation station") uses published authenticators as trusted third parties to secure its recordings. The Authenticator is the guardian-side counterpart (`AUTH/Readme.rst:10`). The same `COMP` package also contains recorder, claimant and cryptainer screens (`COMP/screens/base.py:12-20`, `COMP/application/recorder_gui.py`). Those are out of scope here. The authenticator app loads only the five "AUTHENTICATOR" screens (`COMP/screens/base.py:22-27`).

## 2. Functional lifecycle requirements

### 2.1 Startup and shutdown behaviour

1. On a mobile OS, any unhandled exception at launch or while running the app is caught, an HTTP POST is sent to the crash endpoint, and the exception is re-raised (see 2.5).
2. Logging is configured before any UI starts (see 2.4).
3. The config file is loaded after the data directories exist. It is seeded from the shipped defaults (see 3).
4. After the UI is built, the app does two things:
   - It seeds the main screen's "custom folder" value from the config key `authenticator.custom_authenticator_dir`.
   - It observes that value, and each change is persisted immediately to the config file (`AUTH/waauthenticator/waauthenticator_gui.py:57-63, 87-90`).
5. The app then applies the platform safe-area handling (section 5).
6. Pause: the app accepts being paused and resumed by the OS without restart (`COMP/application/generic_gui.py:57-67`). There is no state save or restore on pause or resume (`on_resume` is a no-op).

### 2.2 Back / Escape key (all platforms)
The Android BACK button arrives as the Escape key. Handler (`AUTH/waauthenticator/waauthenticator_gui.py:92-105`). First matching rule wins:

1. If a modal dialog or the folder chooser is open, close it and consume the key.
2. Else, if the current screen is not the "authenticator management" home screen, navigate to the home screen and consume the key.
3. Else, do not consume the key. The OS default applies (app closes).

A reimplementation must keep a "current dialog" registry (register, test, close) to support rule 1 (`COMP/widgets/popups.py:98-117`).

### 2.3 Threading model (requirement: no blocking of the UI thread)

- Long operations MUST run off the UI thread, on a single background worker (one thread, tasks queued in order, never concurrent, to avoid concurrent key operations) (`COMP/utilities/__init__.py:26-28`).
- The standard helper (`_offload_task_with_spinner`, `COMP/application/generic_gui.py:121-137`) works in four steps: show the spinner; run the task on the worker; on success run the result callback on the UI thread with the task's return value; always hide the spinner, even on error. If the task raises, the callback is not called.
- The spinner is a small centred indeterminate spinner. INFO: it does not block input in 1.5 ([05 OI-27](05-open-issues.md#d-publication)); a reimplementation SHOULD block the controls that would start a second operation.
- Unhandled exceptions in a background task are logged, and a snackbar "Abnormal error caught: <ExceptionClassName>" is shown (3.5 s, [02 §1.4](02-ux-and-screens.md#14-feedback-primitives-framework-neutral-definitions)). The exception is then re-raised inside the worker (`COMP/widgets/popups.py:47-58`).
- Tasks offloaded with spinner: publication-status lookup, publication, revelation-request listing (`COMP/screens/authenticator_publication_form.py:219,252`, `authenticator_revelation_request_management.py:143`).
- Keypair generation also uses the single worker **and shows the spinner** (`_offloaded_initialize_authenticator` is decorated with `@process_method_with_gui_spinner`, `COMP/screens/authenticator_creation_form.py:100-101`, `COMP/widgets/popups.py:142-156`). In addition it locks its own form (`COMP/screens/authenticator_creation_form.py:159-177`): the form fields and toolbar are disabled and the passphrase field is overwritten with `***`. The status text states that generation "might take a few minutes", and a progress bar advances. On completion a "Success" or "Failure" dialog appears, then the app returns to home ([02 §4.3](02-ux-and-screens.md#43-generation-after-valid-input)).
- In 1.5, Check, Accept, Reject, Export, Import and Destroy run on the UI thread instead; a reimplementation SHOULD offload them too ([05 OI-42](05-open-issues.md#f-user-interface)).
- Any UI update from a worker must be marshalled to the UI thread (`Clock.schedule_once` in the Kivy implementation).

### 2.4 Logging

- Logs go to stderr with a UTC timestamp formatter (`SafeUtcFormatter`, `DEFAULT_UTC_LOG_FORMAT`). The root level is read from env var `WA_LOG_LEVEL` and defaults to INFO (`COMP/application/_app_presetup.py:48-58`).
- A log directory `<INTERNAL_APP_ROOT>/logs` is created (`COMP/default_settings.py:139-140`), but no file log handler is installed anywhere in `COMP` (no `FileHandler`), so it stays empty ([05 OI-58](05-open-issues.md#h-platform-build-release)).
- A pluggable callback handler exists to forward records elsewhere (`COMP/logging/handlers.py`). It is used for the recorder console and not by the authenticator.
- `main.py` forces `WA_LOG_LEVEL=DEBUG`, marked "TEMPORARY" (`AUTH/main.py:2`; [05 OI-53](05-open-issues.md#h-platform-build-release)).

### 2.5 Crash handling

- Only when running on Android is the exception reported (detected by env var `ANDROID_ARGUMENT`). There is an explicit FIXME for iOS (`COMP/launcher.py:65`). On desktop the exception just propagates.
- Report content (`COMP/logging/crashdumps.py`):
  - header `SOFTWARE: WACLIENT` and `WACLIENT_TYPE: APPLICATION`;
  - on Android: BRAND, DEVICE, MANUFACTURER, MODEL, PRODUCT, BASE_OS, CODENAME, RELEASE, SDK_INT;
  - the full Python traceback.
- Transport: form-encoded POST with a single field `crashdump`. Failure is ignored ("If it fails, it fails"). The report is also printed to stdout.
- Privacy note: no user data is collected beyond device model and traceback. Tracebacks could still contain paths. The report is sent without user consent (no prompt): [05 OI-56](05-open-issues.md#h-platform-build-release) (decide).

### 2.6 Internationalisation

- Supported languages: `en` (source language, no catalog needed) and `fr` (`COMP/i18n.py:24`).
- Language detection order, at startup only (`COMP/i18n.py:19-59`):
  1. Env var `LANG`, if exactly `en` or `fr` after trim and lowercase. Values like `en_US.UTF-8` are NOT honoured.
  2. Android: Java default locale language.
  3. iOS: first preferred language from the OS.
  4. Desktop: Python `locale.getdefaultlocale()` (the language part, for example `fr_FR` → `fr`).
  5. Rule: any code starting with `fr` gives French, everything else gives English.
- There is no language setting in the settings panel. The language switcher is the globe icon of the main screen ([02 §8.2](02-ux-and-screens.md#82-languages)); its choice is not persisted.
- Catalogs:
  - gettext domain `witnessangel`, `.po` source compiled to `.mo`, loaded with `fallback=True` (`COMP/i18n.py:65-71`).
  - Two catalog directories are chained, app first, then components (`COMP/i18n.py:104-122`). A missing translation falls back to the English msgid.
  - **Confirmed bug:** the app registers `ROOT_DIR / "locale"`, that is `AUTH/waauthenticator/locale`, which does not exist (`AUTH/waauthenticator/waauthenticator_gui.py:24-26`). The app catalog lives at `AUTH/locale/fr/LC_MESSAGES/witnessangel.{po,mo}` (and at the root of the AAB). So in 1.5 **only the components catalog** `COMP/locale/fr/LC_MESSAGES/witnessangel.{po,mo}` is used, and the three strings that only the app catalog translates (settings panel title and item) show in English to French users ([05 OI-50](05-open-issues.md#g-internationalisation), disposition *fix*).
  - Messages use named placeholders (`{name}`) for formatted strings. They are interpolated from caller variables by `tr.f(tr._("..."))`. A reimplementation needs equivalent named-placeholder substitution, because msgids are the English text.
  - Some UI strings are looked up lazily, so a language switch refreshes live widgets. The window title `"Witness Angel - Authenticator"` is deliberately untranslated (`AUTH/waauthenticator/waauthenticator_gui.py:39`).
- Regenerating catalogs: `AUTH/update_i18n.sh` runs xgettext, then msgmerge, then msgfmt. It only handles `fr`.

## 3. Configuration (framework-neutral)

- File: `wakeygen_config.ini` (historical "keygen" name), INI format, located at `<INTERNAL_APP_ROOT>/wakeygen_config.ini` (`AUTH/waauthenticator/waauthenticator_gui.py:48`, `COMP/application/_common_runtime_support.py:42-45`).
- Initialisation: defaults come from the shipped `config_defaults.ini`. User values from the file override them. Missing keys silently take defaults. New defaults are written to disk only on the next config save.
- Saving: whole-file rewrite at each save (`COMP/application/generic_gui.py:97-102`).

| Section | Key | Default | Meaning | Edited via |
|---|---|---|---|---|
| `[authenticator]` | `custom_authenticator_dir` | empty | Absolute path of the folder chosen as "custom folder" location. Empty means none. Must NOT be read as the current directory. The path is made absolute on read (`AUTH/waauthenticator/waauthenticator_gui.py:110-112`). | Written automatically when the user picks a folder. Not in the settings panel. |
| `[network]` | `wagateway_url` | `https://api.witnessangel.com/gateway/jsonrpc/` | JSON-RPC endpoint of the gateway. | Settings panel |

Settings panel (`AUTH/waauthenticator/waauthenticator_gui.py:114-124`): title "Authenticator settings" (translatable through the app catalog, so shown in English in 1.5, see 2.6). It has one editable text item (truncated display):

- title: "Witness Angel Gateway URL";
- description: "Registry where authenticators can be published";
- plus a non-editable title line `Authenticator v<PROGRAM_VERSION> by Witness Angel`.

The gateway URL is **not validated**. A validator `check_witness_angel_gateway_url` (scheme presence only) exists in `COMP/application/_common_runtime_support.py:134-143`, but nothing in the components or the app calls it. An invalid URL only shows up as a network-error snackbar at the next gateway call ([05 OI-47](05-open-issues.md#f-user-interface), decide). The URL is read from config at every gateway call, so a change applies immediately.

Device identity: `COMP/application/_common_runtime_support.py:180-190` can create `<INTERNAL_APP_ROOT>/.wa_device_uid.json` holding `{"wa_device_uid": <uuid0>}`. Only the claimant screens call it; the authenticator never creates this file. See [04](04-data-and-protocols.md) for gateway interaction.

## 4. Storage locations (exact, per OS)

Defined in `COMP/default_settings.py:79-166`. Platform detection is by Kivy `platform` (`android`, `ios`, otherwise desktop) (`COMP/default_settings.py:19-21`).

| Name | Android | iOS | Desktop (Windows/Linux/macOS) |
|---|---|---|---|
| `INTERNAL_APP_ROOT` (app-private data, config, logs, internal authenticator) | `Context.getFilesDir()`, normally `/data/user/0/org.witnessangel.authenticator/files` | `<home>/Library/Application Support` (may not exist yet; created with parents) | `<home>/.witnessangel` (`%USERPROFILE%\.witnessangel` on Windows, `~/.witnessangel` on Linux/macOS), where `<home>` = plyer `storagepath.get_home_dir()` |
| `INTERNAL_CACHE_DIR` | `getCacheDir()` | `<home>/tmp` | `<INTERNAL_APP_ROOT>/cache` |
| `EXTERNAL_APP_ROOT` (user-visible area; start folder of the folder chooser) | `getExternalFilesDir(null)`, i.e. `/storage/emulated/0/Android/data/org.witnessangel.authenticator/files`. It is `None` if unavailable (for example ejected SD card). | `<home>/Documents` (exposed to the Files app through Xcode flags) | `<INTERNAL_APP_ROOT>/external` |
| `EXTERNAL_APP_ROOT_PREFIX` (used only to shorten paths for display as `<sdcard>/...`) | `Environment.getExternalStorageDirectory()` | none | none |
| `EXTERNAL_EXPORTS_DIR` (default for ZIP exports, and start folder for import) | `<EXTERNAL_APP_ROOT>/exports` | `<Documents>/exports` | `<INTERNAL_APP_ROOT>/external/exports` |

Derived (all platforms, under `INTERNAL_APP_ROOT`):

| Path | Content |
|---|---|
| `wakeygen_config.ini` | Config (section 3) |
| `logs/` | Log directory (created, see 2.4) |
| `authenticator.keystore/` | The "user profile" authenticator (`INTERNAL_AUTHENTICATOR_DIR`). A legacy `authenticator/` folder is renamed to `authenticator.keystore` at startup if the new one does not exist (`COMP/default_settings.py:142-148`). |
| `keystore_pool/`, `cryptainers/` | Created at startup (`COMP/default_settings.py:150-154`). They belong to recorder and claimant features; the authenticator never uses them ([05 OI-23](05-open-issues.md#c-local-storage-import-export-destroy)). |
| `.wa_device_uid.json` | Not created by the authenticator (section 3). |

Directory creation: `INTERNAL_APP_ROOT` is created with parents. The external and export dirs are created best-effort, and permission errors are swallowed (`COMP/default_settings.py:156-166`).

Where an authenticator lives: the management screen offers three location types (`COMP/screens/authenticator_management.py:55-58, 177-191`):

| Type | Directory |
|---|---|
| `USER_PROFILE` | `INTERNAL_AUTHENTICATOR_DIR` (above) |
| `CUSTOM_FOLDER` | `<custom_authenticator_dir>/authenticator.keystore` (only if a custom folder has been selected) |
| `USB_DEVICE` | `<partition mount point>/authenticator.keystore`, or `<mount point>/.authenticator` if that hidden folder exists (`CRYPTO/authdevice.py:12-16`) |

Removable-drive discovery (`CRYPTO/authdevice.py:20-47`):

- Windows: WMI query `Win32_DiskDrive`, keeping devices whose PNP id starts with `USBSTOR`.
- Linux: pyudev `block` devices with attribute `removable == 1`, then their partitions matched against mounted partitions from psutil.
- macOS: `system_profiler -xml SPUSBDataType` parsed as plist. If the tool is missing (iOS simulator) the result is an empty list.
- iOS: no detection, always empty.
- Android: the 1.5 build runs Python 3.14, where `sys.platform == "android"`. That value falls into the `else` (macOS) branch. Its `assert sys_platform.startswith("darwin")` is stripped from the release bytecode (verified on `wacryptolib/authdevice.pyc` in the AAB), `system_profiler` is absent, so the result is an empty list with a warning. Android therefore has no USB discovery; users reach removable storage only through the folder chooser (custom folder) ([05 OI-24](05-open-issues.md#c-local-storage-import-export-destroy)). INFO: with Python ≤3.12 builds `sys.platform` was `linux`, the Linux branch failed to import `pyudev`, and the screen's `except ModuleNotFoundError` gave the same empty list (`COMP/screens/authenticator_management.py:121-124`).
- Each returned device exposes `device_type`, `partition_label`, `partition_mountpoint`, `filesystem_format`, `filesystem_size` and `authenticator_dir`.

Folder-access checks (`COMP/system_permissions.py:74-105`): a folder is "writable" only if a temp subfolder plus a file can be created and removed in it. `os.access` is considered unreliable on Windows. "Readable" means the folder can be listed. A folder selection is refused with the toast "External storage is not accessible" if the folder is unset, not a directory, unreadable, or (when required) unwritable. The previously saved custom folder is re-used as the chooser start path only if it still exists and is readable. Android scoped-storage changes can invalidate it. Otherwise `EXTERNAL_APP_ROOT` is the start path (`COMP/screens/authenticator_management.py:195-220`).

Creation constraint: when creating an authenticator, only one level of folder is created (`mkdir(parents=False)`) (`COMP/screens/authenticator_creation_form.py:164-166`).

Path display rule (`COMP/application/_common_runtime_support.py:68-82`): a path starting with the Android external-storage root is shown as `<sdcard>/...`. A path starting with the user's home is shown as `~/...`.

### 4.4 Folder access (requirement level)

1.5 expresses every location as an **absolute POSIX path**, chosen in an in-app file browser (KivyMD `MDFileManager`) and stored as text in the config file. That is an implementation detail. What a reimplementation MUST provide:

1. **Internal location.** A private, persistent, per-app folder (Android `Context.getFilesDir()`, iOS `Library/Application Support`, desktop `~/.witnessangel`) holding `authenticator.keystore/`. On Android and iOS the existing folder MUST be reused across app updates, so that existing authenticators are found (same application id `org.witnessangel.authenticator`, same sub-path).
2. **Custom location.** Persistent read/write access to **one user-chosen folder**, including the right to create the `authenticator.keystore` sub-folder in it and to create, read, overwrite and delete files there. The access MUST survive app restarts. Native mechanisms satisfy this: an Android Storage Access Framework tree URI with `takePersistableUriPermission` (read + write), an iOS security-scoped bookmark of a folder picked with the document picker (`UIDocumentPickerViewController`, folder mode), a plain path on desktop. Removable drives are reached the same way on mobile.
3. **Exports folder.** A user-visible folder where ZIP exports are written and from where imports are picked (`EXTERNAL_EXPORTS_DIR` above). On mobile, a reimplementation MAY instead use the OS "save as" / "open" pickers, as long as the archive format of [04 §2.4](04-data-and-protocols.md#24-zip-export-archive) is kept.
4. **Removable drives on desktop.** Listing USB partitions (as above) is a convenience; picking the drive as a custom folder MUST also work.

Migration rule for the stored `custom_authenticator_dir` (written by 1.5 as an absolute path):

- On desktop, keep reading it as a path.
- On Android, an absolute path under the app-specific external dir (`/storage/emulated/0/Android/data/org.witnessangel.authenticator/files/…`) can still be opened directly; any other path SHOULD be treated as "no custom folder" and the user asked to pick the folder again (no grant exists for it).
- On iOS, a path containing `/Documents/` SHOULD be re-resolved relative to the *current* app container's `Documents` folder (the container UUID changes between installs and updates, which is the cause of the "custom location not remembered" bug, [05 OI-16](05-open-issues.md#c-local-storage-import-export-destroy)); otherwise ask again.
- Once migrated, store the native grant (URI or bookmark) instead of the path. The config key MAY keep its name.

## 5. Platform-specific behaviour (requirements)

### 5.1 Android

- Permissions: only `android.permission.INTERNET` is declared (`AUTH/buildozer.spec:97`). No storage permissions are requested: the app works only in app-private storage plus folders chosen by the user (see 4.4). A legacy runtime-permission helper exists in the components lib but is unused (`COMP/system_permissions.py:53-71`, named `__OBSOLETE_...`).
- Orientation: portrait only.
- Min API 26, target/compile API 36.
- Back button: see 2.2.
- Safe-area (system bars) handling:
  1. The app content is inset by the system-bar insets, as `[left, top, right, bottom]` in pixels. On API 30+ it uses the system-bars insets. Below API 30 it uses the legacy system-window insets (`COMP/application/android_helpers.py:141-194`).
  2. The insets are re-evaluated on rotation, navigation-mode change, keyboard and multi-window changes.
  3. The app must apply them as padding of the root layout (`AUTH/waauthenticator/waauthenticator_gui.kv:12`). When the window is not edge-to-edge, the insets are zero, so there is no double margin.
  4. Edge-to-edge is enforced by Android 15 (SDK 35+). The fix was introduced in commit `d30849b` "Inset app content from Android system bars (edge-to-edge fix)".
- Display-cutout mode: presetup calls `window.addFlags(2)` with a comment saying "LAYOUT_IN_DISPLAY_CUTOUT_MODE_NEVER" (`COMP/application/_app_presetup.py:77`). The value is wrong and a reimplementation should not set it ([05 OI-54](05-open-issues.md#h-platform-build-release)).
- Ctypes fix: `ctypes.pythonapi` is re-bound to `libpython<maj>.<min>.so`, because the default is broken on Android. It is needed for wacryptolib (`COMP/application/android_helpers.py:134-138`).
- Language detection: Java locale.
- Back-up flag: `android.allow_backup = True` ([05 OI-57](05-open-issues.md#h-platform-build-release), decide).

### 5.2 iOS

- Safe-area / notch: at start, query a native `NotchDetector` object for top/bottom/left/right notch sizes and use them as `[left, top, right, bottom]` margins (`AUTH/waauthenticator/waauthenticator_gui.py:65-76`). Contract: each getter returns the key window's `safeAreaInsets` edge (iOS 11+; 0 before), in **points**, truncated to an `int`; the app converts points to pixels with Kivy `dp()` (1 pt ≈ 1 dp). The values are read once at startup, not on rotation. The class is not in this repo: it comes from a gist (`:66`) and lives in the Xcode project's `main.m` (workspace archive `Xcode-toolchain-ios-authenticator.zip`, `authenticator-ios/main.m:193-305`). A reimplementation uses the platform's safe-area API instead.
- Storage: sandboxed (section 4). The `Documents` folder is the only user-visible area. It is exposed in the Files app by two `Info.plist` keys, both `true`: `UIFileSharingEnabled` and `LSSupportsOpeningDocumentsInPlace` (`authenticator-ios/authenticator-Info.plist`). Other keys there: `UIRequiresFullScreen`, `UIStatusBarHidden` = true, `ITSAppUsesNonExemptEncryption` = false; iPhone orientations portrait and upside-down, iPad all four; a `NSCameraUsageDescription` asking the user to refuse (the app never uses the camera).
- No removable-drive discovery.
- Crash reporting is not wired (FIXME).
- Config file location is the same relative scheme: `<Library/Application Support>/wakeygen_config.ini`.

### 5.3 Desktop

- Window: focus is forced on cursor enter (`Window.raise_window()`), so that one click is enough to focus and click. Multitouch emulation dots from right or middle click are disabled (`COMP/application/_app_presetup.py:118-130`).
- Paths: see section 4. The hidden folder `.witnessangel` is under the user home on all three OSes.
- Windows: removable drives need WMI/pywin32. Linux needs pyudev. They are optional dependencies of wacryptolib (`witness-angel-cryptolib/pyproject.toml:52-54`).
- Raspberry Pi is detected through `/proc/cpuinfo`, which sets `WAIT_TIME_MULTIPLIER = 4`. It is used by recorder polling intervals, not by the authenticator (`COMP/default_settings.py:60-65`).

## 6. Non-functional requirements

| Topic | Requirement or evidence |
|---|---|
| Supported OS | Android API 26+ (Android 8.0), target API 36; iOS (kivy-ios build, versions not pinned in repo); Windows, Linux, macOS via PyInstaller (`AUTH/pyproject.toml:27-33` classifiers). The Android archs shipped are armeabi-v7a, arm64-v8a, x86, x86_64. |
| Google Play 16 KB pages | The 64-bit native libs must be aligned to 16 KB (required since 1 Nov 2025). See section 11. |
| Keygen performance | Generation of the keypairs is expected to take "a few minutes" on mobile (UI text, `COMP/screens/authenticator_creation_form.py:172`). It runs on a worker with all inputs locked. The pure-Python fallback crypto backend is forced on every OS (section 10) and may contribute; RSA prime generation itself stays in pycryptodome (on a desktop PC, 5 keypairs take about 4 s with the fallback forced) ([05 OI-53](05-open-issues.md#h-platform-build-release)). Key sizes and counts are in [03 §4.3](03-business-logic.md#43-generated-data-summary). |
| Offline vs online | Offline: create, open, check, import/export ZIP, change location. Online (gateway needed): publication status, publish, list and answer revelation requests. The only declared network permission is INTERNET. Network errors are surfaced through the JSON-RPC error handler (`status_slugs_response_error_handler`, `COMP/application/_common_runtime_support.py:18,194`). |
| Security-relevant | Private keys are protected by a passphrase. Passphrase fields are not masked while typing; the creation field is overwritten with `***` after submit ([05 OI-13](05-open-issues.md#b-creation-check-passphrase)). The keystore is plain files in a user-visible or app-private folder. The crash reporter sends tracebacks without consent. `allow_backup` is enabled on Android. The release signing script holds hardcoded secrets ([05 OI-60](05-open-issues.md#h-platform-build-release)). Crypto details are in [04](04-data-and-protocols.md). |
| Concurrency | One background worker. No concurrent key operations. |
| Persistence of UI state | Only `custom_authenticator_dir` is persisted. The selected authenticator and screen are not restored across restarts (selection falls back to the default entry, `COMP/screens/authenticator_management.py:222-235`). |

## 7. Module inventory (what each layer must provide)

A reimplementation must supply equivalents of these capabilities, whatever the language:

| Capability | Source of the current implementation |
|---|---|
| Platform detection, path resolution, directory bootstrapping | `COMP/default_settings.py` |
| Config load/save with defaults, settings panel schema | `COMP/application/generic_gui.py`, `_common_runtime_support.py` |
| Folder-writability/readability probes | `COMP/system_permissions.py` |
| i18n (gettext, named placeholders, language detection) | `COMP/i18n.py` |
| Background worker + wait spinner + error snackbar | `COMP/utilities/__init__.py`, `COMP/application/generic_gui.py`, `COMP/widgets/popups.py` |
| Dialog registry (for Back handling), toast/snackbar | `COMP/widgets/popups.py` |
| Safe-area insets (Android, iOS) | `COMP/application/android_helpers.py`, `AUTH/waauthenticator/waauthenticator_gui.py` |
| Crash report upload | `COMP/launcher.py`, `COMP/logging/crashdumps.py` |
| Authenticator keystore, key generation, trustee API, removable-device discovery, JSON-RPC client | `CRYPTO/` (see below) |

Crypto library modules used by the authenticator-relevant screens (role only; details in `04-data-and-protocols.md`): `wacryptolib.authdevice` (removable drive listing), `.authenticator` (initialise and test the initialized state), `.keystore` (filesystem keystore, metadata loading, read-only keystore), `.keygen` (keypair generation, PEM loading), `.cipher` (bytestring encryption), `.trustee` (TrusteeApi: operations as a key guardian), `.exceptions`, `.utilities` (uuid0 generation, JSON file/bytes helpers, exception-logging helper), `.jsonrpc_client` (gateway proxy), `._crypto_backend.pycryptodome` (backend, with fallback switch). Sources: imports in `COMP/screens/authenticator_*.py` and `COMP/application/_common_runtime_support.py:18-19`.

## 8. Build/release requirements (framework-neutral)

- Android: release artifact is an Android App Bundle (`.aab`) signed with an upload key. Multi-arch (armeabi-v7a, arm64-v8a, x86, x86_64). Application id `org.witnessangel.authenticator`. Version name `1.5`, version code `2635003`.
- 64-bit native libs must be 16 KB page-aligned, verified by an ELF-segment check (section 11.5).
- Desktop: single executable per OS named `witness_angel_authenticator_<version with dots as dashes>`, with a console window kept (`USE_CONSOLE = True`). On macOS it is an `.app` bundle, id `org.witnessangel.authenticator`, with entitlements, and codesigned if `MACOS_CODESIGN_IDENTITY` is set.
- Version sources: a single version string `1.5` must agree between `pyproject.toml` and the app code. Debug builds assert this at import time (`AUTH/waauthenticator/waauthenticator_gui.py:30-35`).

---

# PART B - Incidental implementation details (Kivy / KivyMD / buildozer)

> **Kivy primer (for readers new to the stack).** *Kivy* is a Python GUI toolkit; *KivyMD* adds Material Design widgets (`MDApp` is its application class). A *kv* file is Kivy's declarative UI language: widget tree, properties and bindings, roughly like QML or XAML. A *ScreenManager* holds full-page *Screens* and switches between them with a transition. *RecycleView* is a virtualised list. *Clock.schedule_once(f)* runs `f` on the UI thread at the next frame, which is how worker threads hand results back. A Kivy *property* is an observable attribute; kv expressions re-evaluate when it changes. *SettingsWithSpinner* is Kivy's built-in settings panel, built from a JSON list of items. *python-for-android* (p4a) packages Python plus native libs into an Android app; *buildozer* drives p4a (and kivy-ios for iOS) from a `buildozer.spec` file; *pyjnius* / *pyobjus* call Java / Objective-C from Python. *PyInstaller* builds the desktop executables.

## 9. Component architecture

### 9.1 Three repositories and layering

```mermaid
flowchart TB
    subgraph AUTH["witness-angel-authenticator (app shell)"]
        MAIN["main.py"]
        GUI["waauthenticator/waauthenticator_gui.py<br/>WaAuthenticatorApp"]
        KV["waauthenticator_gui.kv<br/>ScreenManager + WaitSpinner"]
        CFG["config_defaults.ini"]
        LOC1["locale/ (fr)"]
    end
    subgraph COMP["witness-angel-components (wacomponents)"]
        LAUNCH["launcher.py<br/>crash handler"]
        PRE["application/_app_presetup.py"]
        GEN["application/generic_gui.py<br/>WaGenericGui(MDApp)"]
        RT["application/_common_runtime_support.py<br/>WaRuntimeSupportMixin"]
        AH["application/android_helpers.py"]
        DS["default_settings.py<br/>paths + platform flags"]
        SP["system_permissions.py"]
        I18N["i18n.py"]
        UT["utilities/ (worker pool)"]
        WID["widgets/ (popups, layout)"]
        SCR["screens/authenticator_*.py (5 used)"]
        CD["logging/crashdumps.py"]
        LOC2["locale/ (fr)"]
    end
    subgraph CRYPTO["witness-angel-cryptolib (wacryptolib)"]
        KS["keystore / authenticator / trustee"]
        KG["keygen / cipher / _crypto_backend"]
        AD["authdevice"]
        RPC["jsonrpc_client"]
    end
    GW[("Witness Angel Gateway (JSON-RPC)")]
    CRASH[("Crash endpoint (HTTP POST)")]

    MAIN --> LAUNCH
    LAUNCH --> PRE
    LAUNCH -->|imports and calls main| GUI
    GUI --> GEN
    GEN --> RT
    GUI --> KV --> SCR
    SCR --> KS
    SCR --> KG
    SCR --> AD
    RT --> RPC
    RPC --> GW
    CD --> CRASH
    LAUNCH --> CD
    GEN --> UT
    GEN --> WID
    RT --> DS
    SCR --> DS
    SCR --> SP
    GUI --> I18N
    GUI --> AH
    GUI -.-> CFG
    I18N --> LOC1
    I18N --> LOC2
```

Layering rules:

- The app shell (`AUTH`) contains only the application class, KV root layout, default config, and translations. It holds no business logic. All screens live in `COMP`.
- `COMP` holds the GUI framework glue, screens, platform helpers and path logic.
- `CRYPTO` holds everything cryptographic and keystore-related, plus the JSON-RPC client.
- Other `COMP` areas (`devices/`, `sensors/`, `service_control/`, `recording_toolchain.py`, recorder and claimant screens) are recorder-side and out of scope. The service launch path in `launcher.py` (`--service`, OSC socket) is unused by this app.
- Directories `___wacomponents`, `___wacryptolib` and `___buildozer.spec.reference_v1..v4` in the authenticator repo are stale copies and references. They exist but were deliberately not analysed.

### 9.2 Class and file map

| Class / file | Role | Source |
|---|---|---|
| `WaAuthenticatorApp(WaGenericGui)` | Concrete app: title, icon, kv file, config name, margins property, back handler, settings schema | `AUTH/waauthenticator/waauthenticator_gui.py:38-124` |
| `WaGenericGui(WaRuntimeSupportMixin, MDApp)` | Base for standalone GUI apps: theme (Blue palette, hue 900), pause/resume, config/settings, spinner and offload helpers | `COMP/application/generic_gui.py:34-137` |
| `WaRuntimeSupportMixin` | Config paths, path formatting, status checkers, device uid, gateway proxy | `COMP/application/_common_runtime_support.py:22-195` |
| `ImprovedSettingsWithSpinner` | Kivy settings class with an added `string_truncated` item type | `COMP/application/generic_gui.py:28-31` |
| `_Translator` / `tr` | gettext facade, observable for live kv refresh | `COMP/i18n.py:74-151` |
| `WAScreenName` | Registry of screen names | `COMP/screens/base.py:9-27` |

The root kv (`AUTH/waauthenticator/waauthenticator_gui.kv`) has a BoxLayout padded by `app.application_margins`. It contains a ScreenManager with 5 screens and a `WaitSpinner` (id `wait_spinner`). Four of the screens receive `selected_authenticator_dir` bound from the management screen. Screen details are in `02-ux-and-screens.md`.

## 10. Startup sequence (as implemented)

1. `AUTH/main.py` (9 lines):
   - sets `WA_LOG_LEVEL=DEBUG` ("TEMPORARY") and `FORCE_WACRYPTOLIB_FALLBACK_BACKEND=1` ("SAME BEHAVIOUR FOR ALL OSes");
   - prints the Python version;
   - under `__main__`, calls `launch_main_module_with_crash_handler("waauthenticator.waauthenticator_gui", client_type="APPLICATION")`.
2. `launcher.launch_main_module_with_crash_handler` (`COMP/launcher.py:41-77`):
   - asserts client_type is `APPLICATION` or `SERVICE`;
   - calls `setup_app_environment(setup_kivy_gui=True)`;
   - imports the main module (this triggers config and path loading, plus `tr.add_locale_dirs`) and calls its `main()`;
   - on Android, catches exceptions, posts the crash dump and re-raises.
3. `_presetup_app_environment` (`COMP/application/_app_presetup.py:5-137`), uses `print()` rather than logging, since it runs before logging exists:
   - sets `KIVY_NO_ARGS`, `KIVY_NO_FILELOG`, `KIVY_NO_CONSOLELOG` to `1`;
   - optionally installs a typeguard import hook if env var `WA_ENABLE_TYPEGUARD` names a package;
   - loads Kivy's logger early and restores the real `sys.stderr` afterwards;
   - adds a stderr handler to the root logger and sets the level from `WA_LOG_LEVEL`;
   - on Android: patches ctypes, then runs the window-flag call on the UI thread;
   - registers shared assets (`wacomponents.assets.register_common_resources`);
   - GUI only: disables the mouse multitouch emulation on desktop, binds the focus fix, and loads the shared layout kv.
   - Each step is wrapped in try/except that prints `>>>>>>>> FAILED ...` and continues.
4. Import side effects of `waauthenticator_gui.py`:
   - adds locale dirs, `ROOT_DIR/"locale"` then the components locale dir (`:26`);
   - adds `ROOT_DIR` to Kivy resource paths (`:28`);
   - runs the version self-check (`:30-35`).
5. `WaAuthenticatorApp().run()`:
   - `build_config` seeds defaults, then `load_config`;
   - `build` sets the title, palette Blue and hue 900;
   - the kv root is loaded (the `kv_file` class attribute);
   - `__init__` binds `Window.on_keyboard` to the back handler (`AUTH/waauthenticator/waauthenticator_gui.py:53-55`).
6. `on_start` (`:57-85`): seeds and binds the custom folder (see 2.1), then applies the iOS notch or Android insets listener. The Android listener object is kept on `self`, so the JNI proxy is not garbage collected.

**Release builds run without asserts.** The 1.5 Android bytecode is compiled optimised: in `wacryptolib/authdevice.pyc` from the AAB, the `assert` and its `'darwin'` constant are absent. So `__debug__` is false and every `assert` is skipped in release: the version self-check (`AUTH/waauthenticator/waauthenticator_gui.py:30-35`), and the library asserts listed in [05 OI-40](05-open-issues.md#e-data-formats-and-crypto). Statements in this spec that rely on an assert are marked "debug builds only". Desktop runs from source (`python main.py`) keep asserts.

Env vars summary:

| Var | Effect |
|---|---|
| `WA_LOG_LEVEL` | Root log level (main.py overrides it to DEBUG) |
| `FORCE_WACRYPTOLIB_FALLBACK_BACKEND` | Makes wacryptolib patch pycryptodome internals and use the pure-Python fallback (`CRYPTO/_crypto_backend/pycryptodome.py:160`) |
| `LANG` | Forces `en` or `fr` |
| `WA_ENABLE_TYPEGUARD` | Debug typeguard import hook |
| `WA_PACKAGE_NAME` | Used only by the Android notification helpers (marked "FIXME BROKEN"), not by the authenticator |
| `ANDROID_ARGUMENT` | Detects the Android process for the crash handler |
| `MACOS_CODESIGN_IDENTITY` | PyInstaller macOS signing |

## 11. Build and release

### 11.1 Dependencies (`AUTH/pyproject.toml`)

| Item | Value |
|---|---|
| Name / version / licence | `witness-angel-authenticator` / `1.5` / GPL-2.0-or-later (`:2-5`) |
| Python | `>=3.8, <3.13` (`:25`) |
| wacryptolib, wacomponents | git dependencies, branch `wakeygen_stable` (the comment says they must be manually installed at selected versions) |
| Kivy | `^2.2.1` with extra `base` |
| KivyMD | zip of upstream commit `1152d3c312` |
| plyer | `^2.1.0` |
| psutil | `^5.9.5` |
| Pillow | `^10.0.0` |
| Dev | `PyInstaller >=5.2` |
| Build backend | `poetry.masonry.api` |

Sibling versions: cryptolib `0.12` (`witness-angel-cryptolib/pyproject.toml:8`, requires Python `>=3.10`), components `0.1` (`witness-angel-components/pyproject.toml:8`). The pyproject says branch `wakeygen_stable` for both, but the build vendors whatever is checked out: components on `wakeygen_stable` @ `4ebc5d2`, cryptolib on **`poc/pure-python-crypto-utils` @ `85b5dc7`** (116 commits ahead of `wakeygen_stable`; it adds `utilities/`, `vendors/`, `_crypto_backend/fallback_adapter.py` and the top-level `extjson` import). The 1.5 AAB contains exactly that layout. See the [README baseline](README.md#source-baseline-and-citation-prefixes) and [05 OI-59](05-open-issues.md#h-platform-build-release).

### 11.2 `buildozer.spec` (Android, active values)

| Key | Value |
|---|---|
| `title` / `package.name` / `package.domain` | `Authenticator` / `authenticator` / `org.witnessangel` |
| Version | read by regex from `pyproject.toml` (`version.regex`, `version.filename`) |
| `android.numeric_version` | `2635003` (the versionCode, set explicitly) |
| `source.dir`, `source.include_exts` | `.`; `py,png,jpg,kv,atlas,ini,json,mo` |
| `source.exclude_dirs` | `tests, bin, build, dist, venv, _stuffs` |
| `android.blacklist_src` | `buildozer_blacklist.txt` (excludes pycryptodome `SelfTest`) |
| `orientation` / `fullscreen` | `portrait` / `0` |
| `android.permissions` | `android.permission.INTERNET` |
| `android.api` / `android.minapi` | `36` / `26` |
| `android.ndk` / `android.ndk_path` | `29` / `/opt/android-ndk-r29` |
| `android.archs` | `armeabi-v7a,arm64-v8a,x86,x86_64` |
| `android.allow_backup` | `True` |
| `android.release_artifact` | `aab` |
| p4a | branch `develop`, commit `70f92243` |
| `buildozer.build_dir` | `/root/.buildozer_files_authenticator` |
| `requirements` | kivy==2.3.1, kivymd zip `1152d3c312`, pycryptodome==3.20.0, plyer==2.1.0, decorator==5.1.1, docutils==0.20.1, pymongo==4.8.0, jsonrpc-requests==0.4.0, multitimer==0.3, uuid0==0.2.7, pytz==2024.1, psutil==6.0.0, pillow==10.4.0, pybase62==1.0.0, schema==0.7.7, jsonschema==4.23.0, click==8.1.7, requests==2.32.3, urllib3==2.2.2, charset_normalizer==3.3.2, idna==3.7, certifi==2024.7.4, attrs==23.2.0, pyrsistent==0.20.0, chardet==5.2.0, importlib-resources==6.4.0, zipp==3.19.2, pyaes==1.6.1 |
| Assets | presplash `assets/android_presplash_authenticator_512px.png`; icon `assets/icon_authenticator_512x512.png` |
| iOS | kivy-ios `master`, ios-deploy `1.10.0`; codesign identity fields are placeholders (`<email>`, `<string>`) |

The wacryptolib and wacomponents packages are NOT in the Android `requirements`. They are vendored into the project root by `scripts/sync_android_subpackages.sh` (section 11.4). `pymongo`, `pybase62`, `pyaes` and others come from wacryptolib's own needs.

### 11.3 PyInstaller (`AUTH/pyinstaller.spec`)

- Entry point `main.py`. Output dir is forced to `bin/`, to match buildozer.
- Hidden imports: all submodules of `waauthenticator`, `wacomponents` and `plyer`. Data files of both packages are collected. KivyMD hooks path is used.
- Excludes: `_tkinter`, `Tkinter`, `enchant`, `twisted`, `cv2`, `numpy`, `pygame`.
- Windows: icon `.ico` plus SDL2 and GLEW dependency binaries (`kivy_deps`). macOS: `.icns` and `BUNDLE` (`:81-88`). Elsewhere: the `.png`.
- Single-file executable, UPX on, console on. The commented block at the end is an unused directory build.
- The version is read from `pyproject.toml` by regex (`:12-14`).

### 11.4 Containerfile and scripts

| Item | Purpose |
|---|---|
| `AUTH/Containerfile` | Ubuntu 24.04 image: JDK 17, build libs, Rust, Python 3.14 (deadsnakes) venv `/opt/venv_p4a_develop`, buildozer master, `legacy-cgi`, `setuptools`, `cython==3.0.12`, and Android NDK r29 (checksum pinned) baked in at `/opt/android-ndk-r29`. Default CMD: `buildozer -v android debug`. Build with Podman. |
| `scripts/sync_android_subpackages.sh` | Copies `wacryptolib` and `wacomponents` from sibling checkouts (`../witness-angel-cryptolib/src`, `../witness-angel-components/src`; overridable with `CRYPTOLIB_SRC`, `COMPONENTS_SRC`) into the repo root, removing `__pycache__` and `.pyc/.pyo`. Needed because the container only mounts this project. Symlinks would dangle. The copies are git-ignored. |
| `scripts/build_release_signed.sh` | Runs a signed release `.aab` build in Podman (Windows host, Git Bash paths). It forwards P4A_RELEASE_* env vars, and sets Gradle `-Xmx4g` and no daemon (OOM at signing). It copies the `.aab` found under `.../dists/*/build/outputs/bundle/release/` to a non-removable output dir, because the removable `P:` drive is not writable from the container. |
| `scripts/check_16kb_alignment.sh` | Takes an `.apk`/`.aab`/directory, extracts it if needed, and runs `readelf` on `lib/*/*.so`. It requires LOAD alignment of at least 0x4000 (16384) for `arm64-v8a` and `x86_64`. 32-bit archs are exempt. Exit 1 if any 64-bit lib is 4 KB-aligned. |
| `scripts/README_android_16kb_build.md` | Runbook for the Podman workflow. |
| `scripts/update_wa_subcomponents.cmd` | Windows helper to update the sub-components (not analysed further). |
| `scripts/test1.sh`, `test2.sh`, `test3.sh` | Untracked signing-debug scripts ([05 OI-60](05-open-issues.md#h-platform-build-release)). |
| `update_i18n.sh` | See 2.6. |
| `bundletool-all-1.15.4.jar`, `bin/apktool_2.8.1.jar` | Untracked tool jars. |

### 11.5 OpenSpec change `openspec/changes/android-16kb-page-build/`
Files: `proposal.md`, `design.md`, `tasks.md`, `specs/android-16kb-build/spec.md`. Content:

- Rationale: since 1 Nov 2025, Google Play requires 16 KB page-size support for apps targeting Android 15+ on 64-bit.
- Fix recipe, from kivy/python-for-android#3165: buildozer master + p4a `develop` + Python 3.14 + `android.api = 36` + `android.ndk = 29`.
- Tasks 1-7 are all checked, except 5.4 ("Restore full `android.archs` and run the release build") which is unchecked in `tasks.md`. Yet `buildozer.spec` has all four archs and the 1.5 `.aab` exists in `bin/`, so the task checkbox is stale.
- The legacy `p4a_hacks.diff` is explicitly NOT used by this pipeline (`scripts/README_android_16kb_build.md`, task 7.4).
- `openspec/changes/archive/` is empty. The change has not been archived.

### 11.6 Versioning

- Single source of truth is `version` in `pyproject.toml` (`1.5`). buildozer reads it by regex. PyInstaller reads it by regex.
- The `PROGRAM_VERSION = "1.5"` constant in the GUI module is checked against the pyproject text at import in non-optimised runs (`assert 'version = "1.5"' in pyproject text`). It runs only if `pyproject.toml` is found next to the package (desktop or dev tree) and `__debug__` is true. In a PyInstaller or Android package the file is absent, so the check is skipped.
- `android.numeric_version` (`2635003`) is independent and manual (last commit: "Bump Android versionCode to 2635003 for 1.5 release").
- The window settings panel shows the version string.

## 12. KivyMD/Kivy-specific mechanics worth knowing

- The `tr` object is an `Observable`, so kv expressions using `tr._("...")` refresh when the language switches.
- Settings are Kivy's `SettingsWithSpinner` built from a JSON schema list (`type`, `key`, `title`, `desc`, `section`) (`COMP/application/generic_gui.py:88-91`).
- The theme is the KivyMD "Blue" primary palette at hue 900. There is no dark-mode toggle (commented out) (`:53-55`).
- Android insets use a pyjnius `PythonJavaClass` implementing `View.OnApplyWindowInsetsListener`, installed on the content view on the UI thread, then `requestApplyInsets()`.
- The kv root's `padding: app.application_margins` is the single place where safe-area margins are consumed (`AUTH/waauthenticator/waauthenticator_gui.kv:12`).

---

## 13. Open issues

The architecture and platform issues formerly numbered 1-17 here are now in [05-open-issues.md](05-open-issues.md), with dispositions. Mapping: #1 → OI-16, #2 → OI-62, #3 → OI-54, #4 → OI-53, #5 → OI-60, #6 → OI-62, #7 → OI-61, #8 → OI-59, #9 → OI-50 (now confirmed), #10 → OI-56 and OI-57, #11 → OI-63, #12 → OI-63, #13 → OI-63, #14 → OI-62, #15 → OI-62, #16 → OI-24, #17 → OI-58.
