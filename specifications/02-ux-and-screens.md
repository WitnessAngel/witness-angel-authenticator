# 02 — UX and Screens

This file specifies everything the user sees and does in the **Witness Angel Authenticator** app (version 1.5): screens, labels, dialogs, validation rules, enabled/disabled states, background-thread behaviour and platform-specific UX. It is written so the app can be rebuilt from scratch in another framework. Kivy code is cited as evidence, but the behaviour is described as observable results.

Related specifications:
- `03-business-logic.md`: what the library functions named here do (keystore initialization, key generation, passphrase checks, trustee decryption).
- `04-data-and-protocols.md`: the on-disk keystore format, ZIP archives, the config file, and the gateway JSON-RPC methods and payloads.

Citation convention: `path:line`, relative to the WitnessAngel workspace root. To keep lines short, **`WAC/`** stands for `witness-angel-components/src/wacomponents/` and **`WAA/`** stands for `witness-angel-authenticator/`. Line numbers in `.kv` files are the file's own line numbers.

Translations: the source strings are English. French comes from `WAA/locale/fr/LC_MESSAGES/witnessangel.po` first, then from `WAC/locale/fr/LC_MESSAGES/witnessangel.po` (`WAA/waauthenticator/waauthenticator_gui.py:26`, `WAC/i18n.py:473-488`). Every UI string below is given as **EN / FR**. A string with no French translation is shown in English in the French UI and is marked *(no FR)*.

---

## 1. Global application shell

### 1.1 Window, theme, and general layout

| Aspect | Behaviour | Source |
|---|---|---|
| Window title (desktop) | `Witness Angel - Authenticator` (never translated) | `WAA/waauthenticator/waauthenticator_gui.py:39`, `WAC/application/generic_gui.py:52` |
| App icon | `icons/witness_angel_logo_blue_64x64.png` | `WAA/waauthenticator/waauthenticator_gui.py:46` |
| Theme | Material Design, light theme, primary palette **Blue**, hue **900** | `WAC/application/generic_gui.py:53-55` |
| Android orientation | Portrait only; not fullscreen (the status bar stays visible) | `WAA/buildozer.spec:53,76` |
| Android permissions | Only `android.permission.INTERNET`. The authenticator never shows a runtime permission prompt. | `WAA/buildozer.spec:97` |
| Root layout | A box padded by `application_margins` (the safe-area insets, see §8.3). It holds the stack of 5 screens with a **global wait spinner** overlaid on top. | `WAA/waauthenticator/waauthenticator_gui.kv:10-46` |
| Screen transitions | The toolkit's default slide transition (a swap transition is commented out). | `WAA/waauthenticator/waauthenticator_gui.kv:7,19` |
| Mobile app pause | When the user switches apps, the app pauses and resumes without restarting or losing state. | `WAC/application/generic_gui.py:57-67` |

**Global wait spinner.** A 46×46 dp circular indeterminate spinner, centred on the window and hidden by default (`WAC/widgets/popups.py:132-136`). It is shown while background tasks run. It does **not** block input: buttons underneath stay clickable. (The toolkit spinner is not modal, and no code disables input.)

### 1.2 Screens

The app registers exactly 5 screens (`WAA/waauthenticator/waauthenticator_gui.kv:21-43`, names from `WAC/screens/base.py:23-27`):

| Id | Title (EN / FR) | Purpose |
|---|---|---|
| `authenticator_management` (main/home) | Authenticators / Authentifieurs | Pick a storage location and see its state. Entry point for all operations. |
| `authenticator_creation_form` | Create Authenticator / Créer un Authentifieur | Create a new authenticator: owner, passphrase, hint, and 3 keypairs. |
| `authenticator_publication_form` | Publish authenticator / Publier l'authentifieur | Compare the local authenticator with the gateway and publish its public part. |
| `authenticator_revelation_request_management` | Authorization requests / Demandes d'autorisation | List the decryption ("revelation") requests from the gateway, in 3 tabs. |
| `authenticator_revelation_request_detail` | Authorization request details / Détails des demandes d'autorisation | Show one request and accept or reject it. |

**Shared state.** The four secondary screens all work on the **selected authenticator directory** (`selected_authenticator_dir`). It is owned by the main screen and mirrored into the others (`WAA/waauthenticator/waauthenticator_gui.kv:28,33,38,43`). No other state is passed between screens, except that the list screen hands the chosen request object to the detail screen (§6.4).

### 1.3 Top bars

Every screen starts with a top app bar (elevation 8). It has a title, an optional left action (a Back arrow), and right-side icon actions. Each icon has a tooltip label (`WAC/widgets/layout_components.kv:26-29`). Tooltip labels:

| Icon | Tooltip EN / FR |
|---|---|
| `arrow-left` | Back / Retour |
| `refresh` | Refresh / Rafraîchir |
| `earth` | Language / Langue |
| `help-circle-outline` | Help / Aide |
| `cog` | Settings / Paramètres |

### 1.4 Feedback primitives (framework-neutral definitions)

| Primitive | Look and behaviour | Source |
|---|---|---|
| **Toast** | A small temporary message. 1.5 s on desktop; native "short" toast on Android (about 2 s). It cannot be dismissed. | `WAC/widgets/popups.py:26-33` |
| **Snackbar** | A full-width bar at the bottom of the screen, shown for 3.5 s. Used for errors. | `WAC/widgets/popups.py:36-44` |
| **Dialog** | A modal dialog with a title, a text or custom content, optional action buttons, and **always** a last "close" button (default label Close / Fermer; often overridden to Cancel / Annuler). Tapping outside does **not** close it (`auto_dismiss=False`). Only one dialog is "registered" as current at a time; that is the dialog that ESC/BACK closes. | `WAC/widgets/popups.py:61-87,95-126` |
| **Help popup** | A dialog that is 95% of the window width, with the body text at 13 sp, the given title, and a single Close / Fermer button. | `WAC/widgets/popups.py:90-92` |
| **Unexpected-error guard** | Most user-triggered handlers are wrapped in a guard. Any uncaught exception is logged with its traceback and shows a **snackbar**: `Abnormal error caught: <ExceptionClassName>` / `Erreur anormale détectée : <ExceptionClassName>`. The operation then stops silently; the screen is not reset. | `WAC/widgets/popups.py:46-58`, `WAC/logging/handlers.py:31-38` |

**Background task model.** Long operations run on a **single background worker thread**. Tasks queue one after another and never run concurrently (`WAC/utilities/__init__.py:26-28`). The standard helper works in four steps (`WAC/application/generic_gui.py:121-137`):
1. Show the spinner.
2. Run the task on the worker thread.
3. On success, run the result callback on the UI thread.
4. Always hide the spinner.

If the task raises, the result callback is **not** called and the unexpected-error snackbar is shown. The keypair-generation flow uses an older variant (`process_method_with_gui_spinner`, `WAC/widgets/popups.py:142-156`) that also shows and hides the spinner.

### 1.5 Back navigation (ESC on desktop, BACK on Android)

`WAA/waauthenticator/waauthenticator_gui.py:92-105`:
1. If a registered dialog or file browser is open, close it and stop.
2. Otherwise, if the current screen is not the main screen, go **straight to the main screen**. This happens even from the request-detail screen, whose on-screen Back arrow goes to the request list instead.
3. Otherwise, let the key through. On Android this closes or backgrounds the app; on desktop ESC normally closes the window.

---

## 2. Navigation map

```mermaid
flowchart TD
    M["Main: Authenticators<br/>(authenticator_management)"]
    C["Create Authenticator<br/>(authenticator_creation_form)"]
    P["Publish authenticator<br/>(authenticator_publication_form)"]
    L["Authorization requests<br/>(authenticator_revelation_request_management)"]
    D["Authorization request details<br/>(authenticator_revelation_request_detail)"]
    S[["Settings panel (overlay)"]]

    M -- "Initialize button<br/>(status = not initialized)" --> C
    M -- "Publish button<br/>(status = initialized)" --> P
    M -- "Authorizations button<br/>(status = initialized)" --> L
    M -- "cog icon" --> S
    L -- "arrow icon on a request row" --> D

    C -- "Back arrow (disabled during generation)<br/>or success/failure dialog dismissed" --> M
    P -- "Back arrow" --> M
    L -- "Back arrow" --> M
    D -- "Back arrow, or after Accept/Reject succeeded" --> L

    C -. "ESC/BACK" .-> M
    P -. "ESC/BACK" .-> M
    L -. "ESC/BACK" .-> M
    D -. "ESC/BACK (skips the list!)" .-> M
```

What runs each time a screen is entered (its "on enter" hook):

| Screen | On enter | Source |
|---|---|---|
| Main | Rebuild the location list and reselect the previously selected entry. Also runs once at startup. | `WAC/screens/authenticator_management.kv:32`, `WAC/screens/authenticator_management.py:97-99` |
| Create | Reset the form: fields empty and enabled, button enabled, status text empty, progress 0, top bar enabled | `WAC/screens/authenticator_creation_form.kv:6`, `.py:51-56` |
| Publish | Refresh the synchronization status (gateway query in the background) | `WAC/screens/authenticator_publication_form.kv:5` |
| Requests list | Switch to the first tab and fetch the requests (gateway query in the background) | `WAC/screens/authenticator_revelation_request_management.kv:6`, `.py:127-143` |
| Request detail | Nothing; its content is set up by the list screen before navigating | `WAC/screens/authenticator_revelation_request_detail.kv:9` |

---

## 3. Main screen — "Authenticators" (`authenticator_management`)

Sources: `WAC/screens/authenticator_management.py`, `WAC/screens/authenticator_management.kv`.

### 3.1 Layout (top to bottom, whole screen vertically scrollable)

1. **Top bar.** Title `Authenticators` / `Authentifieurs`. No left action. Right actions in this order: **Refresh**, **Language**, **Help**, **Settings** (`.kv:38-40`).
2. **Banner** (elevated strip, 40 dp): `Please select an authenticator location` / `Veuillez sélectionner un emplacement d'authentifieur` (`.kv:42-46`).
3. **Location list** (scrollable, takes a flexible share of the height) (`.kv:48-52`). See §3.2.
4. **Status strip** (elevated, 40 dp). A status icon (80 dp wide) followed by the status message (`.kv:54-65`). See §3.3.
5. **Information area.** Read-only, selectable and copyable multi-line text (scrollable, flexible height). Initial text: `No information available` / `Aucune information disponible` (`.kv:67-72`). See §3.4.
6. **Button group A** (2 columns), enabled **only when status = "not initialized"** (`.kv:74-87`):
   - **Initialize** (bold label; icon `account-key-outline`) / `Initialiser`
   - **Import** (icon `database-import-outline`) / `Importer`
7. **Button group B** (2 columns, 10 px padding), enabled **only when status = "initialized"** (`.kv:89-121`):
   - **Export** (`database-export-outline`) / `Exporter`
   - **Check** (`crosshairs-question`) / `Vérifier`
   - **Destroy** (`delete-alert-outline`) / `Détruire`
   - **Publish** (`share-all`) / `Publier`
   - **Authorizations** (`lock-open-outline`) / `Autorisations`

   (Rows: Export | Check, Destroy | Publish, Authorizations alone.)

### 3.2 Location list — entries and ordering

The list is rebuilt from scratch on every refresh (`.py:117-172`). Order is fixed:

| # | Entry | Primary text EN / FR | Secondary text EN / FR | Left icon | Right icon | Resolved authenticator directory |
|---|---|---|---|---|---|---|
| 1 | **User profile** (internal app storage) | User profile / Profil utilisateur | Stored inside system disk / Stocké dans le disque système | `account-box` | – | `INTERNAL_APP_ROOT/authenticator.keystore` (§7.1) |
| 2 | **Custom location** | Custom location / Emplacement personnalisé | The selected folder shown via the path shortener (§7.4), or `Please select a folder` / `Veuillez sélectionner un dossier` | `folder` | `file-find-outline`: opens the folder browser | `<selected folder>/authenticator.keystore`, or *empty* when no folder is selected |
| 3…n | **One entry per detected USB drive partition**, in detection order (desktop only) | `Drive {drive} ({label})` / `Disque {drive} ({label})`, where drive = mount point and label = partition label or `no name` / `sans nom` | `Size: {size}, Filesystem: {filesystem}` / `Taille : {size}, Format : {filesystem}`. Size uses 1024 steps without decimals (e.g. `14GB`); filesystem is upper-cased | `usb-flash-drive` | – | `<mountpoint>/.authenticator` if that folder exists, else `<mountpoint>/authenticator.keystore` (`witness-angel-cryptolib/src/wacryptolib/authdevice.py:13-17`) |

Details:
- USB detection calls `wacryptolib.authdevice.list_available_authdevices()`. On Android, a `ModuleNotFoundError` (no udev) gives an empty list (`.py:121-124`). On iOS the library returns an empty list (`authdevice.py:38-39`).
- Size formatting: `convert_bytes_to_human_representation` (`WAC/utilities/__init__.py:93-99`), with units `bytes, KB, MB, GB, TB`, integer part only, no space before the unit.
- **Selection.** Tapping a row selects it. Every row gets the light background and the selected row gets the darkest background (`.py:260-265`). Selecting a row immediately recomputes the status and information (§3.3, §3.4).
- **Default selection** after a refresh: the previously selected directory if it still matches a row; otherwise row 1, **User profile** (`.py:223-247`).
- After each refresh, on **desktop only**, a toast says `Refreshed authenticator locations` / `Emplacements d'authentifieurs rafraichis`. Mobile does not show it, because it would be intrusive (`.py:169-170`).
- When the language changes from this screen, the list is rebuilt so the drive labels are translated again (`.py:112-114`).

### 3.3 Status computation (ternary)

The status is computed by `display_authenticator_info()` (`.py:257-371`). It drives the status strip and the enabled state of the button groups:

| Condition (checked in order) | Status | Icon | Status message EN / FR | Information area text |
|---|---|---|---|---|
| Resolved dir is empty (Custom location with no folder chosen) | **None** (invalid) | `file-question-outline` | No valid location selected / Aucun emplacement valide sélectionné | `Please select an authenticator folder` / `Veuillez sélectionner un dossier d'authentifieur` |
| Not initialized (`wacryptolib.authenticator.is_authenticator_initialized(dir)` is false), and **parent folder does not exist** | None | same | same | `Path: <dir>` / `Chemin : <dir>` + blank line + `Selected folder is invalid!` / `Le dossier sélectionné est invalide !` |
| Not initialized, dir missing, and **parent not writable** | None | same | same | Path line + `Beware, parent folder is NOT writable!` / `Attention, le dossier parent n'est PAS accessible en écriture !` |
| Not initialized, dir exists but **is not a folder** | None | same | same | Path line + `Beware, this is not a folder!` / `Attention, ce n'est pas un dossier !` |
| Not initialized, dir is a folder but **not writable** | None | same | same | Path line + `Beware, this folder is NOT writable!` / `Attention, ce dossier n'est PAS accessible en écriture !` |
| Not initialized but creatable | **False** (not initialized) | `checkbox-blank-off-outline` | Authenticator not initialized / Authentifieur non initialisé | `Path: <dir>` only |
| Initialized but the metadata fails schema validation (`load_keystore_metadata` raises `SchemaValidationError`) | None | `file-question-outline` | No valid location selected | `Invalid authenticator data in <dir>` / `Données d'authentifieur invalides dans <dir>`. This uses the **raw** path, not the shortened one. |
| Initialized and valid | **True** (initialized) | `check-circle-outline` | Authenticator initialized / Authentifieur initialisé | The information block below |

"Writable" is tested by actually creating and deleting a temporary sub-folder and file named `~test-folder-<random>/~test-file.tmp` (`WAC/system_permissions.py:597-614`). "Readable" means the folder can be listed (`WAC/system_permissions.py:617-628`). The "parent exists" check only looks at the parent folder, because creation makes only one folder level.

**Information block for an initialized authenticator** (`.py:307-364`). The separator is `COLON()`: EN `": "`, FR `" : "`.

```
Path: <shortened path>

User: <keystore_owner>
Password hint: <keystore_passphrase_hint>
Creation date: <YYYY-MM-DD at HH:MM:SS UTC>   (or the hard-coded French "Inconnu" if the field is missing)
ID: <full keystore_uid>

Keypairs:
    RSA-OAEP …<last uid segment>                  (one line per keypair, indented 4 spaces)
    RSA-OAEP …<last uid segment> (missing private key)
```

Labels EN / FR: `Path`/`Chemin`, `User`/`Utilisateur`, `Password hint`/`Indice de phrase secrète`, `Creation date`/`Date de création`, `ID`/`ID`, `Keypairs`/`Paires de clés`. In the date, `at` / `à`. The keypair label (`WAC/utilities/__init__.py:128-151`) is `<key_algo with "_"→"-"> …<last segment of keychain uid>`, plus ` (missing private key)` / ` (clé privée manquante)` when the private key file is absent. Keypairs appear in the order returned by `FilesystemKeystore.list_keypair_identifiers()`; see 03/04 for that ordering.

### 3.4 Actions on the main screen

| Action | Precondition (UI) | Effect | Feedback |
|---|---|---|---|
| **Refresh** icon | always | Rebuild the list (§3.2) and keep the selection | desktop toast (§3.2) |
| **Language** icon | always | Opens a dropdown below the icon with `English` and `Français` (always shown in those native names) | see §8.2 |
| **Help** icon | always | Help popup titled `Authenticator management page` / `Page de gestion des authentifieurs` (texts in §3.5) | – |
| **Settings** icon | always | Opens the settings panel (§8.1) | – |
| Tap a row | always | Select it and update the status | – |
| Folder icon on "Custom location" | always | Folder browser (§7.2) | toast if storage is inaccessible |
| **Initialize** | status = False | Go to the Create screen | – |
| **Import** | status = False | ZIP file browser (§7.3) | dialogs (§3.6) |
| **Export** | status = True | Confirmation dialog, then export (§3.6) | dialogs |
| **Check** | status = True | Passphrase dialog, then the check (§3.7) | result dialog |
| **Destroy** | status = True | Confirmation dialog, then deletion (§3.8) | dialog |
| **Publish** | status = True | Go to the Publish screen | – |
| **Authorizations** | status = True | Go to the Requests list screen | – |

### 3.5 Main-screen help text

Shown as one popup, with paragraphs separated by single or double line breaks (`.py:570-594`):
1. `On this page, you can manage your authenticators, which are actually digital keychains identified by unique IDs.` / `Sur cette page, vous pouvez gérer vos authentifieurs, qui sont en fait des trousseaux de clés numériques identifiés par des ID uniques.`
2. `These keychains contain both public keys, which can be freely shared, and their corresponding private keys, protected by passphrases, which must be kept hidden.` / `Ces trousseaux contiennent à la fois des clés publiques, qui peuvent être partagées librement, et les clés privées correspondantes, protégées par des phrases secrètes, qui doivent rester cachées.`
3. *(blank line)* `Authenticators can be stored in your user profile or in a custom folder, especially at the root of removable devices.` / `Les authentifieurs peuvent être stockés dans votre profil utilisateur ou dans un dossier personnalisé, notamment à la racine des périphériques amovibles.`
4. `You can initialize new authenticators from scratch, import/export them from/to ZIP archives, or check their integrity by providing their passphrases.` / `Vous pouvez initialiser de nouveaux authentifieurs à partir de zéro, les importer/exporter depuis/vers des archives ZIP, ou vérifier leur intégrité en fournissant leurs phrases secrètes.`
5. *(blank line)* `Note that if you destroy an authenticator, or lose its passphrase, the WitnessAngel recordings which used it as a trusted third party might not be decryptable anymore.` *(no FR: the msgstr is empty, `WAC/locale/fr/LC_MESSAGES/witnessangel.po:543-546`)*

### 3.6 Import / Export

**Export** (`.py:400-437`):
1. A dialog titled `Export authenticator` / `Exporter l'authentifieur`, text `The exported archive should be kept in a secure place.` / `L'archive exportée doit être gardée en lieu sûr.`, buttons **Confirm** / `Confirmer` and **Cancel** / `Annuler`.
2. On Confirm, the dialog closes. The exports folder `EXTERNAL_EXPORTS_DIR` (§7.1) must be an existing, readable and **writable** folder. If not, the toast `External storage is not accessible` / `Stockage externe non accessible` appears and nothing else happens.
3. The app builds a ZIP of the whole authenticator folder. The name is `authenticator_id<last uid segment>_date<YYYYMMDDHHMMSS UTC>.zip` and it is written to the exports folder. This runs **synchronously on the UI thread**, with no spinner.
4. A dialog titled `Export successful` / `Exportation réussie`, text `Authenticator archive exported to <shortened path>` / `L'archive de l'authentifieur a été exportée vers <path>`, button Close.

**Import** (`.py:373-398`), available only when the selected location is *not initialized* but creatable:
1. If the exports folder is missing or unreadable: toast `External storage is not accessible`.
2. Otherwise a file browser opens on the exports folder, showing only `.zip` files (`.py:105-110`).
3. When a file is picked, the browser closes. The ZIP is extracted **into the selected authenticator directory**, creating it if needed. Existing files may be **overwritten**. Nothing is validated. This runs synchronously, with no spinner.
4. A dialog titled `Import successful` / `Importation réussie`, text `Authenticator archive unpacked from <archive file name>, its integrity has not been checked though.` / `L'archive d'authentifieur a été décompressée depuis <nom>, son intégrité n'a cependant pas été vérifiée.`
5. The list refreshes, so the status usually becomes "initialized".

Errors (a corrupt ZIP, I/O errors) show the unexpected-error snackbar.

### 3.7 Check (passphrase / integrity test)

`.py:473-563`:
1. A dialog titled `Sanity check` / `Contrôle d'intégrité` with custom content:
   - a description line, `Test integrity and passphrase of authenticator` / `Tester l'intégrité et la phrase secrète de l'authentifieur`;
   - a single-line text field with hint `Passphrase` / `Phrase secrète`. It **gets the keyboard focus when the dialog opens**. The text is **not masked**.

   Buttons: **Check** / `Vérifier` and **Cancel** / `Annuler`.
2. On Check, the dialog closes and the test runs **synchronously on the UI thread** (no spinner; the UI freezes while keys are decrypted). The passphrase is used **as typed (not trimmed)**. For each keypair returned by `FilesystemKeystore.list_keypair_identifiers()`:
   - if the private key is absent, the keypair counts as "missing";
   - otherwise `wacryptolib.keygen.load_asymmetric_key_from_pem_bytestring(key_pem, key_algo, passphrase)` is tried, and a `KeyLoadingError` makes the keypair count as "wrong passphrase".
3. A result dialog with a Close button:
   - **Success**: there is at least 1 keypair, none missing, none undecodable. Title `Checkup result: Success` / `Résultat du contrôle : Succès`. Text `Keypairs successfully tested: <n>` / `Paires de clés testées avec succès : <n>`.
   - **Failure**: any other outcome, **including 0 keypairs**. Title `Checkup result: Failure` / `Résultat du contrôle : Échec`. Text over three lines:
     `Keypairs tested: <n>` / `Paires de clés testées : <n>`
     `Missing private keys: <comma-separated keypair labels or ->` / `Clés privées manquantes : …`
     `Wrong passphrase for keys:  <labels or ->` (two spaces after the colon) / `Mauvaise phrase secrète pour les clés :  …`

### 3.8 Destroy

`.py:439-471`:
1. A dialog titled `Destroy authenticator` / `Détruire l'authentifieur`, text `Beware, this might make encrypted data using these keys impossible to decrypt.` / `Attention, cela peut rendre impossible le déchiffrement des données chiffrées utilisant ces clés.`, buttons **Confirm** / `Confirmer` and **Cancel** / `Annuler`. The target directory is captured **when the dialog opens**.
2. On Confirm, the **whole authenticator folder is deleted recursively**. This runs synchronously, with no spinner and no second confirmation.
3. A dialog titled `Deletion is over` / `Destruction terminée`, text `Folder <raw absolute path> has been properly removed.` / `Le dossier <path> a été correctement supprimé.`
4. The list refreshes, and the status becomes "not initialized".

If the folder is already gone, the internal `ValueError("Path … not found …")` shows as the snackbar `Abnormal error caught: ValueError`.

---

## 4. Create screen — "Create Authenticator" (`authenticator_creation_form`)

Sources: `WAC/screens/authenticator_creation_form.py`, `.kv`.

### 4.1 Layout

1. **Top bar.** Title `Create Authenticator` / `Créer un Authentifieur`. Left: **Back** (to main). Right: **Help** (`.kv:11-15`).
2. A label `Authenticator: <shortened target dir>` / `Authentifieur : <dir>` (`.kv:21-22`).
3. Three single-line text fields with floating hint labels (`.kv:24-42`). **None is masked; the passphrase is typed in clear text.**
   - `User name` / `Utilisateur`
   - `Passphrase` / `Phrase secrète`
   - `Passphrase hint` / `Indice de phrase secrète`
4. A 20 px spacer, then the **Initialize** / `Initialiser` button. It is outlined, takes half the width, is centred, and is 50 dp high (`.kv:46-58`).
5. A flexible empty space, then the operation status label (empty by default) (`.kv:62-68`).
6. A horizontal progress bar 10 dp high, value 0–100, starting at 0 (`.kv:70-75`).

On every entry the form is reset: fields emptied and enabled, button enabled, status text empty, progress 0, top bar enabled (`.py:51-56`).

### 4.2 Validation (on Initialize)

All three values are **trimmed** first (`.py:58-63`). The rules are checked in this order, and only the first failure is reported (`.py:65-84`):

| # | Rule | Error text EN / FR |
|---|---|---|
| 1 | All three fields non-empty | `Please enter a username, passphrase and passphrase hint.` / `Veuillez entrer un nom d'utilisateur, une phrase secrète et son indice.` |
| 2 | No field longer than **100** characters | `Username, passphrase and passphrase hint must not exceed 100 characters` / `Le nom d'utilisateur, la phrase secrète et son indice ne doivent pas dépasser 100 caractères.` |
| 3 | Passphrase at least **20** characters, **unless it starts with `¤`** (a test back door that allows short passphrases) | `Passphrase must be at least 20 characters long.` / `La phrase secrète doit faire au moins 20 caractères de long.` |

The error appears in a dialog titled `Validation error` / `Erreur de validation` with a Close button. The form keeps its values.

There is no rule on character classes, no confirmation field, and no check that the hint differs from the passphrase.

### 4.3 Generation (after valid input)

`.py:157-192`:
1. On the UI thread:
   - If the target directory does not exist, it is created. Only one level is created; the parent must exist.
   - The Initialize button is **disabled**.
   - The passphrase field text is replaced by `***` for privacy. The real value has already been captured.
   - The status label shows `Please wait, generation of cryptographic keys might take a few minutes.` / `Veuillez attendre, la génération des clés cryptographiques peut prendre quelques minutes.`
   - All three fields are unfocused and **disabled**. They keep their current text, including `***`.
   - The whole **top bar is disabled**, so Back and Help are unusable.
2. On the background worker, with the spinner shown (`.py:100-136`):
   - Progress goes to **10%**.
   - The UI calls `wacryptolib.authenticator.initialize_authenticator(dir, keystore_owner, keystore_passphrase_hint)`, which writes the metadata.
   - **3 times** (`GENERATED_KEYS_COUNT`, `.py:34`), it calls `wacryptolib.keygen.generate_keypair(key_algo="RSA_OAEP", passphrase=…)` and then `FilesystemKeystore.set_keypair(keychain_uid=generate_uuid0(), key_algo="RSA_OAEP", public_key, private_key)`. After key *i*, progress = `10 + int(i*90/3)`, i.e. **40% → 70% → 100%**.
   - Any exception is caught and logged, and the run is marked a failure.
3. On the UI thread, the result dialog (Close button):
   - Success: title `Success` / `Succès`, text `Initialization successfully completed.` / `Initialisation complétée avec succès.`
   - Failure: title `Failure` / `Échec`, text `Operation failed, check logs.` / `Opération échouée, vérifiez les logs.`

   In **both cases**, closing the dialog (button or ESC/BACK) goes back to the **main screen**. The main screen then refreshes and shows the new status.

There is no cancel button during generation (but see the ESC/BACK issue in §10).

### 4.4 Help text

Title `Authenticator creation page` / `Page de création d'authentifieur` (`.py:194-209`):
1. `On this page, you can initialize an authenticator inside an empty folder; this authenticator actually consists in metadata files as well as a set of asymmetric keypairs.` / `Sur cette page, vous pouvez initialiser un authentifieur dans un dossier vide ; cet authentifieur consiste en réalité en des fichiers de métadonnées, ainsi qu'en un ensemble de paires de clés asymétriques.`
2. `To proceed, you have to input your user name or pseudo, a long passphrase (e.g. consisting of 4 different words), and a public hint to help your remember your passphrase later.` / `Pour procéder, vous devez entrer votre nom d'utilisateur ou pseudo, une longue phrase secrète (par exemple, composée de 4 mots différents), et un indice public pour vous aider à vous souvenir de votre phrase secrète plus tard.`
3. `You should keep your passphrase somewhere safe (in a digital password manager, on a paper in a vault...), because if you forget any of its aspects (upper/lower case, accents, spaces...), there is no way to recover it.` / `Vous devez conserver votre phrase secrète en lieu sûr (dans un gestionnaire de mots de passe numérique, sur un papier dans un coffre-fort...), car si vous oubliez l'un de ses aspects (majuscules/minuscules, accents, espaces...), il n'y a aucun moyen de la récupérer.`

---

## 5. Publish screen — "Publish authenticator" (`authenticator_publication_form`)

Sources: `WAC/screens/authenticator_publication_form.py`, `.kv`. Reached only when the status is "initialized".

### 5.1 Layout

1. **Top bar.** Title `Publish authenticator` / `Publier l'authentifieur`. Left: **Back** (to main). Right: **Refresh**, **Help** (`.kv:10-14`).
2. A scrollable, read-only, selectable text area (about 8/10 of the height) holding the synchronization report. It is empty at first (`.kv:21-31`).
3. A 20 px spacer, then the **Publish** / `Publier` button. It is half width, centred, 50 dp high, and **disabled unless publishing is allowed** (default: disabled) (`.kv:35-47`).

### 5.2 Refresh synchronization status (on enter and on Refresh)

`.py:115-219`:
1. On the UI thread, the text area is cleared. The local metadata and public-key list are read **synchronously**, using `load_keystore_metadata` and `ReadonlyFilesystemKeystore.list_keypair_identifiers()`.
2. On the background worker (spinner shown), the UI calls `gateway_proxy.get_public_authenticator(keystore_uid=…)`. An `ExistenceError` means "not published". A `JSONRPCError` or `OSError` becomes the error message `Error querying gateway server, please check its url and you connectivity` *(sic, "you")* / `Erreur lors de l'appel au serveur gateway, veuillez vérifier son url et votre connectivité`.
3. On the UI thread, the Publish button is first disabled again, then:
   - **Gateway error.** The text area shows `No information available` / `Aucune information disponible` and a snackbar shows the error message. Stop.
   - **Not published.** Status `NOT PUBLISHED` / `NON PUBLIÉ`, message `The local authenticator does not exist in the remote repository.` / `L'authentifieur local n'existe pas dans le dépôt distant.` The **Publish button becomes enabled**.
   - **Published.** Status `PUBLISHED` / `PUBLIÉ`. The local and remote key sets are compared as `(keychain_uid, key_algo)` pairs (`.py:76-99`):
     - In sync: message `The remote authenticator is up to date.` / `L'authentifieur distant est à jour.`
     - Out of sync: message `An inconsistency has been detected between the local and remote authenticator.` / `Une incohérence a été détectée entre l'authentifieur local et distant`, plus an "Error details" block (below).
     - The Publish button stays disabled either way: a published authenticator cannot be modified.
4. The report text:

```
Authenticator path: <shortened path>
User: <keystore_owner>
ID: <full keystore_uid>

Gateway: <configured gateway URL>
Remote status: <NOT PUBLISHED | PUBLISHED>
Message: <message>
[if published:]

Provide the Authenticator ID to users wanting to rely on you as a Key Guardian
[if inconsistent:]

Error details:
    Exceeding key(s) in remote: <…>
    Missing key(s) in remote: <…>
```

   Labels EN / FR: `Authenticator path`/`Chemin d'authentifieur`, `User`/`Utilisateur`, `ID`, `Gateway`/`Passerelle`, `Remote status`/`Statut distant`, `Message`/`Message`, `Provide the Authenticator ID to users wanting to rely on you as a Key Guardian`/`Fournissez l'ID d'Authentifieur aux utilisateurs désirant vous ajouter comme Gardien de Clés`, `Error details`/`Détails d'erreurs`, `Exceeding key(s) in remote`/`Clés en excès côté distant`, `Missing key(s) in remote`/`Clés manquantes côté distant`. Key lists use shortened uids (`…<last segment>`), comma-separated, or `-` when empty. They currently render wrapped in a tuple representation; see §10.

5. A toast: `Remote authenticator status has been updated` / `Le statut de l'authentifieur distant a été actualisé`.

### 5.3 Publish

`.py:221-252`. On **Publish**, the background worker (spinner shown) builds the payload: `keystore_owner`, `keystore_uid`, `keystore_secret`, optionally `keystore_creation_datetime`, and `public_keys` = a list of `{keychain_uid, key_algo, key_value}`, where key_value comes from `ReadonlyFilesystemKeystore.get_public_key`. It then calls `gateway_proxy.set_public_authenticator(**payload)`; see 04. On success, the synchronization status is refreshed (§5.2), so the screen typically shows PUBLISHED and the button becomes disabled. On failure, the unexpected-error snackbar appears and nothing is refreshed. **No confirmation dialog is shown before this irreversible action.**

### 5.4 Help text

Title `Authenticator publishing` / `Publication de l'authentifieur` (`.py:254-266`):
1. `This page allows to publish the PUBLIC part of an authenticator to a remote Witness Angel Gateway, so that other users may import it to secure their recordings.` / `Cette page permet de publier la partie PUBLIC d'un authentifiant sur une passerelle Witness Angel distante, afin que d'autres utilisateurs puissent l'importer pour sécuriser leurs enregistrements.`
2. `For now, a published authenticator can't be modified or deleted.` / `Pour l'instant, un authentifiant publié ne peut pas être modifié ou supprimé.`
3. `In case of incoherences between the keys locally and remotely stored, these errors are displayed here.` / `En cas d'incohérences entre les clés stockées localement et à distance, ces erreurs sont affichées ici.`

---

## 6. Authorization requests

### 6.1 List screen — "Authorization requests" (`authenticator_revelation_request_management`)

Sources: `WAC/screens/authenticator_revelation_request_management.py`, `.kv`. Reached only when the status is "initialized".

**Layout:**
1. **Top bar.** Title `Authorization requests` / `Demandes d'autorisation`. Left: **Back** (to main). Right: **Refresh**, **Help** (`.kv:11-15`).
2. **Tabs**, stretched across the full width, in this order (`.kv:17-58`):
   1. `Pending` / `En cours`, for status `PENDING`
   2. `Accepted` / `Accepté`, for status `ACCEPTED`
   3. `Rejected` / `Rejeté`, for status `REJECTED`
3. Each tab holds a scrollable list. When the list is empty, the tab shows a large centred placeholder (20 sp) `Empty` / `Vide`.

**List row** (`WAC/widgets/layout_components.kv:111-121`). Two lines:
- left icon `file-arrow-left-right`;
- primary text `Request "<description, truncated to 40 chars + …>" (<YYYY-MM-DD>)` / `Demande "<…>" (<date>)` (`WAC/utilities/__init__.py:170-190`);
- secondary text `Symkey decryption requests: <n>` / `Requêtes de déchiffrement de symkey : <n>`;
- right icon `arrow-right-bold-hexagon-outline`. **Only tapping this icon** opens the detail screen. Tapping the row itself does nothing.

**Ordering:** within each tab, rows are sorted by `created_at`, **newest first** (`.py:64`).

**Fetch** (on enter and on Refresh) (`.py:99-143`):
1. Switch to the first tab (Pending).
2. On the background worker (spinner shown): read the local metadata, then call `gateway_proxy.list_authenticator_revelation_requests(authenticator_keystore_secret=…, authenticator_keystore_uid=…)`. Requests are grouped by `revelation_request_status` into the keys PENDING, ACCEPTED and REJECTED.
3. Outcome:

| Outcome | Feedback EN / FR | Lists |
|---|---|---|
| Success | toast `Authorization requests were updated` / `Requêtes d'autorisation mises à jour` | filled |
| `KeystoreDoesNotExist` (not published) | snackbar `Authenticator does not exist in remote registry` / `L'authentifieur n'existe pas dans le registre distant` | all cleared → "Empty" |
| `AuthenticationError` | snackbar `The keystore secret of authenticator is not valid` / `Le secret de keystpre de l'authentifieur n'est pas valide` *(FR typo "keystpre")* | cleared |
| `JSONRPCError` / `OSError` | snackbar `Error querying gateway server, please check its url and your connectivity` / `Erreur lors de l'appel au serveur gateway, veuillez vérifier son url et votre connectivité` | cleared |
| Any other exception (e.g. an unknown status value → `KeyError`) | snackbar `Abnormal error caught: <Class>` | **not cleared** (stale content stays) |

**Help:** title `Authorization requests page` / `Page de demandes d'autorisation` (`.py:145-162`):
1. `This page summarizes the authorization requests that have been sent to the selected authenticator, by people wishing to decrypt some of their containers.` / `Cette page résume les demandes d'autorisation qui ont été envoyées à l'authentifieur sélectionné, par des personnes souhaitant déchiffrer certains de leurs conteneurs.`
2. `These requests can be freely rejected. Else, to accept them, you must input your passphrase, which will be used to load your private keys and generate authorization tokens for the requester.` / `Les demandes peuvent être librement rejetées. Sinon, pour les accepter, vous devez saisir votre phrase secrète, qui sera utilisée pour charger vos clés privées et générer des jetons d'autorisation pour le demandeur.`
3. `For now, it is not possible to change the status of a request which has been accepted or rejected.` / `Pour l'instant, il n'est pas possible de modifier le statut d'une demande qui a été acceptée ou rejetée.`

### 6.2 Detail screen — "Authorization request details" (`authenticator_revelation_request_detail`)

Sources: `WAC/screens/authenticator_revelation_request_detail.py`, `.kv`.

**Layout** (whole screen scrollable):
1. **Top bar.** Title `Authorization request details` / `Détails des demandes d'autorisation`. Left: **Back** (to the **list** screen). No right actions (`.kv:15-18`).
2. A banner (elevated, 40 dp) with the request label, in the same format as the list row's primary text (`.kv:20-23`).
3. A read-only multi-line summary box (`.kv:25-31`, built at `.py:71-88`):

```
Status: <raw status, e.g. PENDING>             (value not translated)
Authenticator: <owner> (ID …<uid tail>)       (owner "Unknown"/"Inconnu(e)" if empty)
Description: <full description>
Local key for response: <ALGO-NAME …<uid tail>>
```

   Labels: `Status`/`Statut`, `Authenticator`/`Authentifieur`, `Description`/`Description`, `Local key for response`/`Clé locale pour la réponse`.
4. A list of **symkey decryption requests**, in server order (`.py:90-108`). Each is a two-line row:
   - left icon `key`;
   - primary `Key of container …<cryptainer uid tail>` / `Clé du conteneur …`;
   - secondary = the cryptainer name;
   - right icon `information-outline`, which opens a dialog.

   The dialog is titled `Symkey decryption request` / `Requêtes de déchiffrement de la Symkey` with a **Close** / `Fermer` button and the text:
   ```
   Concerned authenticator key: <ALGO …uid tail>
   Cryptainer metadata: <raw dict representation>
   Decryption status: <raw status>
   ```
   Labels: `Concerned authenticator key`/`Clé d'authentifieur concernée`, `Cryptainer metadata`/`Metadata du cryptainer `, `Decryption status`/`Statut de déchiffrement`.
5. Two buttons, enabled **only when the request came from the PENDING tab** (`.py:53`, `.kv:37-52`):
   - **Accept** (icon `check`) / `Accepter`
   - **Reject** (icon `close`) / `Rejeter`

### 6.3 Accept flow

`.py:145-252`:
1. A dialog titled `Enter your authenticator passphrase` / `Entrez votre phrase secrète d'authentifieur`. Description `This will allow unmasking the requested Symkey parts` / `Cela permettra de révéler les morceaux de Symkey requis`. A passphrase field (`Passphrase` / `Phrase secrète`), **not masked, not auto-focused**. Buttons **Accept** / `Accepter` and **Cancel** / `Annuler`.
2. On Accept, the dialog closes and processing runs **synchronously on the UI thread**, with no spinner. RSA decryption of several keys may freeze the UI. The passphrase is used as typed (not trimmed). Steps:
   - Read the local metadata (for `keystore_secret`).
   - Build `TrusteeApi(FilesystemKeystore(dir))`.
   - For each symkey decryption request: `trustee_api.decrypt_with_private_key(keychain_uid, cipher_algo, cipherdict, passphrases=[passphrase])`.
     - `KeyDoesNotExist` → status `PRIVATE_KEY_MISSING`. **This path is buggy; see §10.**
     - `KeyLoadingError` → snackbar `Loading of authenticator private key failed (wrong passphrase?)` / `Le chargement de la clé privée d'authentifieur a échoué (mauvaise phrase secrète ?)`. **The whole operation is aborted** and nothing is sent; the user stays on the detail screen.
     - Otherwise, the decrypted bytes are re-encrypted with the request's response public key (`encrypt_bytestring`) and the item gets status `DECRYPTED`.
   - Call `gateway_proxy.accept_revelation_request(authenticator_keystore_secret, revelation_request_uid, symkey_decryption_results)`.
3. On success: a toast `The decryption request was accepted` / `La demande de déchiffrement a été acceptée`, then go to the **list screen**. Entering the list triggers a refetch, whose own toast `Authorization requests were updated` replaces the first one (a known FIXME, `WAC/screens/authenticator_revelation_request_management.py:113`). The accepted request then appears in the Accepted tab.
4. Gateway or other errors show the unexpected-error snackbar, and the user stays on the detail screen.

### 6.4 Reject flow

`.py:171-189, 254-271`:
1. A simple dialog titled `Do you want to reject this request?` / `Voulez-vous rejeter cette requête ?`, with no body and buttons **Reject** / `Rejeter` and **Cancel** / `Annuler`.
2. On Reject: synchronously (no spinner), the UI calls `gateway_proxy.reject_revelation_request(authenticator_keystore_secret, revelation_request_uid)`. No passphrase is needed.
3. On success: a toast `The authorization request was rejected` / `La demande d'autorisation a été rejetée`, then go back to the list (it refetches). Errors show the snackbar.

---

## 7. Authenticator location selection UX

### 7.1 Storage roots per platform

`WAC/default_settings.py:274-361`:

| Platform | `INTERNAL_APP_ROOT` (private) | `EXTERNAL_APP_ROOT` (folder-browser start) | `EXTERNAL_EXPORTS_DIR` (export/import) |
|---|---|---|---|
| Android | the app-private `files` dir (`Context.getFilesDir()`) | the app-specific external dir (`getExternalFilesDir(null)`, under `Android/data/<pkg>/files`). It may be *absent*, e.g. when the SD card is ejected. | `<external>/exports` |
| iOS | `~/Library/Application Support` | `~/Documents` (visible in the iOS Files app) | `~/Documents/exports` |
| Desktop | `~/.witnessangel` | `~/.witnessangel/external` | `~/.witnessangel/external/exports` |

- The "User profile" authenticator lives at `INTERNAL_APP_ROOT/authenticator.keystore`. On startup, a legacy folder `INTERNAL_APP_ROOT/authenticator` is renamed to that name if the new one does not exist (`WAC/default_settings.py:337-343`).
- The external and exports folders are created at startup on a best-effort basis; errors are ignored (`WAC/default_settings.py:351-361`).

### 7.2 Custom folder browser

`WAC/screens/authenticator_management.py:100-104, 193-221`:
- Opened by the `file-find-outline` icon on the Custom location row.
- If `EXTERNAL_APP_ROOT` is missing or unreadable, the toast `External storage is not accessible` appears and the browser does not open.
- **Start folder:** the previously chosen custom folder, if it still exists and is readable; otherwise `EXTERNAL_APP_ROOT`. The user can navigate anywhere the OS allows.
- The browser selects **folders**. Choosing one closes the browser and sets the custom folder. It then **automatically selects the Custom location row**, which recomputes the status. The authenticator itself goes in the sub-folder `authenticator.keystore` of the chosen folder.
- Closing the browser (its close control, or ESC/BACK) changes nothing.

### 7.3 ZIP file browser (Import)

The same browser component, in file mode, filtered to `.zip`, starting at `EXTERNAL_EXPORTS_DIR` (`.py:105-110, 373-379`).

### 7.4 Path display shortening

`format_path_for_display` (`WAC/application/_common_runtime_support.py:68-82`):
- An empty path displays as an empty string.
- On Android, a path under the external-storage root is shown as `<sdcard>/…`.
- A path under the user home is shown as `~/…`.

### 7.5 Persistence of the custom folder

- The config key `[authenticator] custom_authenticator_dir` defaults to empty (`WAA/waauthenticator/config_defaults.ini:1-3`).
- **At startup**, a non-empty value is turned into an absolute path and becomes the custom folder. An empty value means "none"; it must not be read as the current directory (`WAA/waauthenticator/waauthenticator_gui.py:57-63, 110-112`).
- **Every time the custom folder changes**, the new value is written immediately to the config file `INTERNAL_APP_ROOT/wakeygen_config.ini` (`WAA/waauthenticator/waauthenticator_gui.py:48, 87-90`, `WAC/application/generic_gui.py:97-106`).
- The **selected row is not persisted**. Every launch starts with "User profile" selected.

---

## 8. Settings, i18n, platform specifics

### 8.1 Settings panel

Opened from the cog icon on the main screen. On desktop, the toolkit's default F1 shortcut probably opens it too. The panel replaces the screen; its built-in Close button returns to the main screen (`WAC/application/generic_gui.py:28-31, 43-45, 88-95`). The toolkit's own technical settings are hidden.
- Panel title: `Authenticator settings` / `Paramètres Authentificator` (`WAA/waauthenticator/waauthenticator_gui.py:42-43`).
- Items (`WAA/waauthenticator/waauthenticator_gui.py:114-124`):
  1. **Witness Angel Gateway URL** / `URL de la Passerelle Witness Angel`, with description `Registry where authenticators can be published` / `Registre où les authentifieurs peuvent être publiés`. A free-text string, shown truncated on one line (15 sp). Tapping it opens the toolkit's standard text-edit popup with OK/Cancel (toolkit-provided labels, not from the app catalogs). Section `[network] wagateway_url`. Default `https://api.witnessangel.com/gateway/jsonrpc/` (`WAA/waauthenticator/config_defaults.ini:5-7`). It is **not validated**. It is saved to the config file and read again on every gateway call (`WAA/waauthenticator/waauthenticator_gui.py:107-108`, `WAC/application/_common_runtime_support.py:192-195`), so a change applies immediately with no restart.
  2. A title row `Authenticator v1.5 by Witness Angel` (never translated).

### 8.2 Languages

- Two languages: English (`en`) and French (`fr`).
- The **default** is detected at startup (`WAC/i18n.py:388-431`):
  - The `LANG` environment variable is used if it is exactly `en` or `fr`.
  - Otherwise: the Java default locale on Android, the first preferred language on iOS, or the system locale on desktop.
  - Anything starting with `fr` gives French; everything else gives English.
- The **switcher** is the `earth` icon on the main screen. It opens a dropdown of `English` and `Français`, 110 dp max height, opening downward (`WAC/widgets/layout_components.py:227-253`). Choosing one:
  - switches the catalog immediately;
  - updates every declaratively bound label on all screens;
  - rebuilds the main-screen location list;
  - destroys the settings panel so it is rebuilt in the new language next time (`WAC/application/generic_gui.py:108-110`).
- Text built in code on *other* screens (publish report, detail summary) keeps the old language until that screen is refreshed or rebuilt.
- The choice is **not persisted**; the next launch uses the detected default again.

### 8.3 Safe-area insets

- **iOS:** at start, the notch sizes (top, bottom, left, right) are read through a native `NotchDetector` class, converted with `dp()`, and used as outer padding for the whole app (`WAA/waauthenticator/waauthenticator_gui.py:65-76`).
- **Android:** a window-insets listener on the content view reports the system-bar insets in pixels as `[left, top, right, bottom]`, and these become the outer padding (`WAA/waauthenticator/waauthenticator_gui.py:78-85`, `WAC/application/android_helpers.py:141-195`). It re-fires on rotation, navigation-mode change, keyboard display, and multi-window changes. On non-edge-to-edge windows the insets arrive already consumed (zero), which avoids a double margin. This matters for Android 15+ (SDK 35), where edge-to-edge is enforced.
- **Android pre-setup** also adds a window flag (value `2`) meant to avoid display cutouts (`WAC/application/_app_presetup.py:73-80`); see §10.

### 8.4 Other platform notes

- On mobile, read-only text areas do not pop up the virtual keyboard when touched, but text can still be selected (`WAC/widgets/layout_components.py:256-281`).
- On desktop, multitouch emulation (red dots on right/middle click) is disabled. The window raises itself when the mouse enters it, so the first click registers (`WAC/application/_app_presetup.py:118-130`).
- USB drive detection exists only on desktop (Windows, Linux, macOS).
- On an unhandled crash at Android startup, a crash report is sent to `https://api.witnessangel.com/support/crashdumps/` and the app exits. This is not done on iOS or desktop (`WAC/launcher.py:61-76`).

---

## 9. End-to-end user journeys (summary)

1. **Create (first launch).** The app opens with "User profile" selected and the status "Authenticator not initialized". The user taps **Initialize**, fills in the name, a passphrase of at least 20 characters and the hint, then taps **Initialize**. Progress goes 10 → 40 → 70 → 100% (possibly minutes on mobile). The **Success** dialog appears; closing it returns to the main screen, which now shows "Authenticator initialized" and the information block with 3 RSA-OAEP keypairs.
2. **Create on a USB key or custom folder.** Select the Drive row (desktop), or tap the Custom location folder icon and pick a folder. Then continue as in journey 1.
3. **Check the passphrase.** **Check** → type the passphrase → **Check** → result dialog: Success with the keypair count, or Failure with the missing or undecodable keys.
4. **Publish.** **Publish** → the screen queries the gateway and shows NOT PUBLISHED → tap **Publish** → the spinner shows → the report refreshes to PUBLISHED / "up to date". Give the displayed **ID** to people who want you as their Key Guardian.
5. **Handle a request.** **Authorizations** → Pending tab → tap the arrow icon on a request → review the summary and container keys (ⓘ for details) → **Accept** → type the passphrase → **Accept** → toast → back on the list, where the request is now under Accepted. Or: **Reject** → confirm → toast → it moves to Rejected. Accepted or rejected requests are read-only, with their buttons disabled.
6. **Back up / restore.** **Export** → Confirm → ZIP in the exports folder. To restore, select a location that is not initialized (for example after Destroy) → **Import** → choose the ZIP.
7. **Destroy.** **Destroy** → Confirm → the folder is deleted → the status returns to "not initialized". The gateway copy, if published, is untouched and cannot be deleted from the app.

---

## 10. Open issues and observations

Bugs and risks found in the code. They are listed so a reimplementation can decide whether to copy them.

1. **Accept with a missing private key.** When `decrypt_with_private_key` raises `KeyDoesNotExist`, the loop still uses `key_struct_bytes`. On the first item this crashes (snackbar `Abnormal error caught: UnboundLocalError` or `NameError`). On a later item it **re-sends the previous item's decrypted symkey** under status `PRIVATE_KEY_MISSING`, which is a confidentiality issue (`WAC/screens/authenticator_revelation_request_detail.py:209-240`). Expected behaviour: skip encryption and send no response data for that item.
2. **Response key loaded with the wrong algorithm.** The requester's response public key is parsed with `key_algo=cipher_algo` (the authenticator key's algorithm) instead of `revelation_response_key_algo` (`…_detail.py:226-231`). It only works while both are RSA-OAEP.
3. **Inconsistent trimming of the passphrase.** Creation trims the passphrase (`authenticator_creation_form.py:61`), but Check and Accept use the raw input (`authenticator_management.py:510`, `…_detail.py:164`). A passphrase that began or ended with spaces at creation, or a stray trailing space at check time, will fail.
4. **Passphrase fields are never masked** (create form, Check dialog, Accept dialog). Only the create field is replaced by `***` after submission (`WAC/widgets/layout_components.kv:242-244`, `authenticator_creation_form.kv:36-38`).
5. **ESC/BACK during key generation.** The top bar is disabled, but the hardware BACK/ESC still navigates to the main screen while the worker keeps running. The success or failure dialog then appears over the main screen; meanwhile the user may start other operations on a half-initialized folder (`waauthenticator_gui.py:92-105`).
6. **Failed generation leaves a partial authenticator** (metadata with fewer than 3 keys). The status then shows "initialized", and there is no cleanup or rollback (`authenticator_creation_form.py:108-134`).
7. **Long operations block the UI thread:** Check, Accept (multiple RSA decryptions), Reject, Export, Import and Destroy all run synchronously with no spinner. Only key generation, publish-status refresh, publish, and the request fetch use the background worker.
8. **The spinner does not block input.** For example, Publish can be tapped twice during a publish. Calls are serialized by the single worker, but the second `set_public_authenticator` will probably fail with an error snackbar.
9. **No confirmation before Publish**, although the help text says publication is irreversible.
10. **Inconsistency details render as a Python tuple**, e.g. `('…abc, …def',)`, because of stray trailing commas (`authenticator_publication_form.py:157-158`).
11. **Untranslated or hard-coded strings:**
    - `"Inconnu"` (French) for a missing creation date, shown even in the English UI (`authenticator_management.py:329`);
    - raw status values (`PENDING`, `DECRYPTED` …) and the raw cryptainer metadata dict are shown untranslated;
    - the destroy/lose-passphrase help paragraph has no FR translation;
    - FR typos: "keystpre", "Paramètres Authentificator", and "authentifiant" vs "authentifieur" used inconsistently;
    - EN typo "you connectivity" (`authenticator_publication_form.py:111`);
    - the "Symkey decryption request" dialog title is translated in the plural.
12. **Help popup titles are translated twice** (`tr._(title)` on already-translated text, `WAC/widgets/popups.py:92`), and so is the `NO_DATA_MESSAGE` placeholder (`…_management.kv:27,39,53`). This is harmless unless a French string is itself a msgid.
13. **Import can overwrite files** in the target folder and validates nothing ("BEWARE" comment, `authenticator_management.py:389-390`). Only the ZIP extension is filtered.
14. **Destroy error handling** is a FIXME: any `OSError` other than "not found" shows only the generic snackbar, and a partial deletion is possible (`authenticator_management.py:459-466`).
15. **Leaking bindings on refresh.** Each list refresh binds the screen's custom-folder property to a new row widget and never unbinds the old ones (`authenticator_management.py:138`). The leak grows with every refresh.
16. **Custom folder not remembered on iOS.** A TODO file exists (`WAA/TODO FIX custom location not remembered on ios for WA authenticator.txt`, empty). The likely cause is that the absolute path is persisted, while the iOS app-container path changes between installs or updates. A relative or bookmark-based persistence would be needed.
17. **Selected location and language are not persisted** between launches; each launch starts on "User profile" with the auto-detected language.
18. **ESC/BACK from the detail screen jumps to the main screen**, whereas the on-screen Back arrow goes to the request list. The two are inconsistent.
19. **Request rows and container-key rows react only to their right-hand icon**, not to a tap on the row. This is easy to miss on mobile.
20. **Unknown request status from the server** raises `KeyError`. The tabs then keep stale data and only a generic snackbar appears (`…_management.py:91-97`).
21. **Android window flag.** `addFlags(2)` is commented as `LAYOUT_IN_DISPLAY_CUTOUT_MODE_NEVER`, but `2` is `FLAG_DIM_BEHIND` in `WindowManager.LayoutParams`; cutout mode is a separate attribute (`WAC/application/_app_presetup.py:77`).
22. **Units of the insets differ by platform.** iOS applies `dp()` to the notch values, while Android uses raw pixels. Both may be correct for their APIs, but this should be checked on real devices.
23. **Gateway URL is not validated.** An invalid URL only shows up as a network error snackbar. A validator `check_witness_angel_gateway_url` exists in the shared runtime but is unused by this app (`WAC/application/_common_runtime_support.py:134-143`).
24. **Test back door.** A passphrase starting with `¤` bypasses the 20-character minimum (`authenticator_creation_form.py:76-81`). It should be removed or gated in production.
25. **Desktop-only toast on refresh.** On mobile, refreshing locations gives no feedback at all.
26. **Debug flags in `main.py`.** `WA_LOG_LEVEL=DEBUG` is marked "TEMPORARY", and `FORCE_WACRYPTOLIB_FALLBACK_BACKEND=1` is set (`WAA/main.py:2-3`). Debug logging is active in release builds.
