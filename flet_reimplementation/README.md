# Witness Angel Authenticator — Flet reimplementation

A reimplementation of the Witness Angel Authenticator 1.5 (Kivy) with **Flet 1.0**, written from
`../specifications/`. It stays interoperable with existing authenticator folders, ZIP exports and the
gateway, because all crypto, keystore and JSON-RPC work goes through `wacryptolib`.

## Running

From this folder, with the bundled virtualenv:

```bash
.venv/bin/python -m waflet_authenticator          # desktop window (needs the flet desktop client, see limitations)
.venv/bin/python main.py                          # same
.venv/bin/python -c "import flet as ft; from waflet_authenticator.app import main; main(view=ft.AppView.WEB_BROWSER, port=8550)"
.venv/bin/python -m pytest -q                     # test suite
```

Environment variables: `WA_LOG_LEVEL` (default `INFO`) and `LANG` (`en`/`fr` forces the language).
Data lives in `~/.witnessangel/` on desktop: config `wakeygen_config.ini`, `authenticator.keystore/`,
`external/exports/` and `logs/app.log`. These are the same paths and file names as 1.5.

## Structure

```
waflet_components/              reusable, app-agnostic (counterpart of witness-angel-components)
  app_base.py                   WaFletApp: startup, config, i18n, single worker + input-blocking spinner,
                                toast/snackbar/dialog helpers, view stack, Back/Escape, settings dialog
  authenticator_services.py     ALL business logic, GUI-free (status, create, check, export/import/destroy,
                                publication, revelation requests), via wacryptolib only
  storage.py                    storage roots per OS (01 §4), folder probes, location discovery, path migration
  config.py  i18n.py  locale_fr.py  formatting.py  widgets.py
  screens/                      the 5 authenticator screens, parametrised through the app object
waflet_authenticator/           the thin app: WaAuthenticatorApp (title, config file name/defaults,
                                screen registration, settings schema, URL validation), app FR catalog, version
main.py                         entry point
tests/                          pytest: service layer against specifications/fixtures + GUI smoke tests
SPEC_GAPS.md                    what the spec did not say, and how each gap was resolved
```

The screens rely on a small duck-typed app contract: `storage_roots`, `custom_folder` (persisted),
`selected_authenticator_dir`, `selected_revelation_request`, `gateway_url`, `get_gateway_proxy()`.
They do not import the app.

## Open issues (05-open-issues.md): what was done

**Fixed** (disposition *fix*):

| OI | Change |
|---|---|
| 01, 02, 03, 04, 07 | Accept: a missing private key gives `PRIVATE_KEY_MISSING` + `b""`; undecryptable data gives `CORRUPTED` + `b""`; the response key is parsed with `revelation_response_key_algo`; non-RSA_OAEP, empty or duplicate requests are checked first; each private key is decrypted once. |
| 05 | Unknown request statuses are logged and skipped. |
| 10 | The `¤` passphrase back door is removed. |
| 11 | A failed creation is rolled back: only the files and folder it created are removed. |
| 12 | Back/Escape is ignored while keys are generated (the view cannot be popped). |
| 16 | Partial fix: the 01 §4.4 migration rules for stored paths are applied (iOS `/Documents/` re-rooting, Android grant-less paths dropped). No native grants (see limitations). |
| 17, 18 | A missing hint shows as empty. With no secret, Publish/Authorizations are disabled and a message is shown. Any parse or schema error shows "Invalid authenticator data". |
| 19 | Destroy re-checks "initialized" first and reports I/O errors clearly. |
| 22 | Key PEM files are written atomically (temp file + fsync + rename). The metadata file is still written by wacryptolib, but a failed creation is rolled back. |
| 27, 42 | Check, Accept, Reject, Export, Import, Destroy, keygen and gateway calls all run on the single worker. The spinner overlay blocks input, so no double Publish. |
| 33 | The key lists in the inconsistency report are plain comma-separated text. |
| 40 | The meaningful asserts became real checks (algorithm check, UTC conversion). |
| 49 | Only one toast after Accept/Reject. |
| 50, 51 | The app FR catalog is loaded ("Paramètres de l'Authentifieur"…). Typos are fixed, statuses are translated, "authentifieur" is used throughout. |
| 54 | No window flags are set; safe areas come from `ft.SafeArea`. |

**Decided** (disposition *decide*, the safest sensible option):

| OI | Choice |
|---|---|
| 13 | Passphrase fields are masked, with an eye toggle to reveal. |
| 14 | The KDF iteration count is left to wacryptolib/pycryptodome (1000 with the venv's pycryptodome 3.24.1). Pinning it would mean bypassing `wacryptolib.keygen`. Readers accept any count. |
| 15 | Kept: a wrong passphrase and a corrupted PEM give the same result. |
| 20 | Import extracts into a temp sibling folder, then requires valid metadata and at least one keypair. It refuses a non-empty target, then moves the files into place. |
| 21 | Export format unchanged. The dialog now says the archive holds the gateway secret. |
| 24 | USB listing on desktop only. Mobile reaches removable media through the OS folder picker. |
| 25 | Selected location and language are not persisted (same as 1.5). |
| 26 | Publish asks for confirmation and names the gateway URL. |
| 28, 32 | Publication is refused while a private key is missing, or when there is no keypair. |
| 29 | `keystore_secret` is sent to `get_public_authenticator`. An `AuthenticationError` means "published with another secret". The key bytes are still not compared. |
| 43 | Back/Escape goes up one level (detail → list), like the on-screen arrow. |
| 44 | Whole rows are tappable (request rows and container-key rows). |
| 45 | Kept: the "refreshed" toast shows on desktop only. |
| 47 | The gateway URL must be `https://` with a host. It is checked when settings are saved. |
| 53 | Logs at INFO by default. The fallback crypto backend is not forced: wacryptolib's native default is used. |
| 56 | No crash reporter at all, so nothing is sent without consent. |
| 57 | Packaging is not done here. When building with `flet build`, disable Android backup. |
| 58 | A rotating log file is written to `<INTERNAL_APP_ROOT>/logs/app.log`. |

## Verification done

- `.venv/bin/python -m pytest -q`: **30 passed**. These cover the fixture authenticator with its passphrase (raw, NFKC-equivalent and wrong) and the edge-case listing. They also cover status computation, creation (metadata fields, file names, PEM types, rollback), export/import/destroy, and publication against a fake gateway that enforces the server rules. Listing, accept and reject use the fixture payloads, and the accept results are decrypted with the claimant key back to `expected_plaintexts.json`. Further tests cover the real `JsonRpcProxy` wire format and error mapping (fake HTTP), storage roots and migration, i18n EN/FR, formatting and config persistence. Smoke tests import every module, build every screen on a stub page, and drive Accept, creation and Back handling.
- Web mode: the server answers HTTP 200. Headless Chrome, driven over CDP, ran a real session with no server traceback. In that session I created an authenticator (progress, Success dialog, Escape back home), ran Check (Success, 3 keys), opened Publish and Authorizations against an unreachable gateway (snackbar shown), switched to French, opened the settings dialog (French app catalog) and used the in-app folder browser.

## Known limitations vs the Kivy app

- **Not verified**: the desktop window mode (it needs the flet desktop client to be downloaded), Android/iOS builds, and a real gateway. All gateway tests use fakes built from the fixtures.
- First web run: Flet auto-installed `flet-web` 1.0.5 and its dependencies (fastapi, uvicorn, websockets…) into `.venv`.
- Mobile folder access: Flet exposes no SAF `takePersistableUriPermission` or iOS security-scoped bookmarks, so custom folders are stored as paths (01 §4.4 asks for native grants). The storage roots on mobile come from `ft.StoragePaths`. They should map to the 1.5 folders (`getFilesDir()`, `Library/Application Support`), but this is untested, and the application id must stay `org.witnessangel.authenticator`.
- Language detection on mobile uses Python's locale. Flet does not expose the device locale at startup.
- Translations are a Python dict, not gettext `.po`/`.mo`. The language is process-wide, so in web mode several sessions share it.
- Desktop and web use an in-app file browser, like MDFileManager; mobile uses the native picker. In web mode the server's filesystem is browsed.
- On the home screen, Escape does not close the desktop window (Kivy's default did). Android system Back closes the app as usual.
- The cryptolib's vendored extjson prints `CALLING JSON DUMPS` to stdout on every dump (OI-39). This is not fixable without modifying the cryptolib.
- No iOS notch handling beyond `ft.SafeArea`, no crash reporter, no packaging config (`flet build` metadata, icons).
