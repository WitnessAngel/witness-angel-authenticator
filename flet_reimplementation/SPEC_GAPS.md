# Spec gaps found while reimplementing with Flet

Every place where `specifications/` was not enough and I had to read the original code, guess, or invent.
Overall the spec was sufficient for almost everything: the 04 §0 checklist and the fixtures were enough to build and
test the service layer without looking at the Kivy app. I opened the original code 4 times (items 1-4). Items 5-12
are gaps I resolved without code, by guessing or inventing.

## A. Answers found in the original code

| # | What was missing | Where in the spec | Answer, and where I found it |
|---|---|---|---|
| 1 | Check failure dialog: do the "Missing private keys" labels carry the ` (missing private key)` suffix? 02 §3.7 says "comma-separated keypair labels" and 02 §3.3 defines `format_keypair_label` with an optional suffix. | 02 §3.7, 03 §5 | No suffix: the labels are `format_keypair_label(key_algo, keychain_uid)` with no presence flag. `COMP/screens/authenticator_management.py:519-534`. |
| 2 | Is the folder the user picks as custom location checked for access? 01 §4 says "A folder selection is refused with the toast … if the folder is unset, not a directory, unreadable, or (when required) unwritable", which reads as if the chosen folder were validated. | 01 §4 (folder-access paragraph), 02 §7.2 | Only `EXTERNAL_APP_ROOT` is checked, before the chooser opens. The chosen folder is not validated; its problems show up later in the status strip. `COMP/screens/authenticator_management.py:195-220`. Also, `is_folder_readable`/`is_folder_writable` raise `RuntimeError` when the path does not exist (`COMP/system_permissions.py:74-105`); the spec does not mention this. |
| 3 | "Local key for response" in the detail summary: which uid is shown? The response keychain uid, or the target key's uid? | 02 §6.2 | `format_keypair_label(revelation_response_key_algo, revelation_response_keychain_uid)`. `COMP/screens/authenticator_revelation_request_detail.py:66-69`. |
| 4 | `convert_bytes_to_human_representation` for sizes of 1024 TB or more is not specified. | 02 §3.3 table | The loop ends and the raw float is returned (`COMP/utilities/__init__.py:93-99`). I render it as `<n>TB` instead. Cosmetic. |

I also copied `waauthenticator/config_defaults.ini` to get the exact file text. The spec (01 §3, 04 §2.5) already gives
the keys and defaults, so this was a convenience, not a gap.

## B. Gaps resolved without the code (guesses or inventions)

| # | Gap | What I did |
|---|---|---|
| 5 | **New user-facing strings required by "fix"/"decide" items have no exact text, and none has a French translation**: OI-03 ("Unsupported algorithm in this request", "This request contains no key to decrypt": EN given, no FR), OI-17 (EN given, no FR), OI-19 (I/O error message: no text), OI-20 (invalid archive, non-empty target: no text), OI-21 (sentence explaining the secret: no text), OI-26 (confirmation text: no text), OI-28 / OI-32 (refusal messages: no text), OI-29 ("published by someone else": no text), OI-47 (URL validation error: no text), OI-51 (translated status labels: no FR for DECRYPTED / PRIVATE_KEY_MISSING / CORRUPTED / METADATA_MISMATCH). | I wrote both EN and FR. They are marked `# NEW` in `waflet_components/locale_fr.py` and `waflet_authenticator/locale_fr.py`. A translator should review them. |
| 6 | Toolkit-provided labels have no EN/FR text: the settings popup buttons (02 §8.1 says "toolkit-provided OK/Cancel"), and every label of the file chooser (MDFileManager: title, "select this folder", the parent-folder entry). | I used OK / Cancel, and "Select a folder" / "Select a file" / "Select this folder" with French translations. |
| 7 | **Internal contradiction about destroying a corrupted authenticator.** The 03 §3.1 state machine has `Corrupted --> Uninitialized: Destroy`. But a corrupted folder has status `None` (02 §3.3), and 02 §3.1 enables Destroy only when status = True. So Destroy is unreachable for a corrupted folder. | I followed 02, so Destroy is disabled. To recover, the user has to delete the folder by hand. The spec should pick one behaviour. |
| 8 | OI-51 asks for "Unknown"/"Inconnu" when the creation date is missing, but the owner fallback of `format_authenticator_label` is "Unknown"/"Inconnu(e)" (02 §3.3). Both use the same English msgid, so one catalog cannot hold both. | Both use "Unknown" → "Inconnu(e)". Distinct msgids (or msgctxt) would be needed to show "Inconnu" for the date. |
| 9 | Direction of "Exceeding key(s) in remote" and "Missing key(s) in remote" is only implied. | Exceeding = remote − local, missing = local − remote. |
| 10 | OI-29 (decide) recommends sending `keystore_secret` to `get_public_authenticator`. The spec does not say how to show the resulting `AuthenticationError`, or what the gateway returns for a *valid* secret on an unpublished uid. | `AuthenticationError` → snackbar "This authenticator ID is already published with another secret"; `ExistenceError` → NOT PUBLISHED, as before. Not checked against a real gateway. |
| 11 | OI-20 (decide) says "validate the metadata and the key file names". It does not say whether an archive with valid metadata but **zero keypairs** is valid. | Refused as "The archive does not contain a valid authenticator". |
| 12 | 01 §4.4 requires persistent folder grants on mobile (SAF tree URI, iOS security-scoped bookmark), but it does not say what to do when the framework cannot take such grants. Flet 1.0's `FilePicker.get_directory_path` returns a path string and exposes no grant API. | Paths are stored, and the 01 §4.4 migration rules are applied at startup (`storage.migrate_custom_dir`). Persistent grants are listed as a known limitation in README. |

## C. Spec / fixture remarks (not blocking)

- The task brief says the venv has pycryptodome 4.2.0. The venv actually has **3.24.1**, so new keys get 1000 PBKDF2 iterations (04 §4.3, OI-14).
- `VENDORS/extjson.py` (the copy used by the editable cryptolib install) prints `CALLING JSON DUMPS …` on every dump. 05 OI-39 says the shipped copy does not, but a reimplementation that reuses the cryptolib from source gets the print on stdout.
- 04 §7.3.1 lists `keystore_secret` as optional for `get_public_authenticator`, but there is no wire fixture for that call carrying a secret.
- The fixtures were enough for every interop test: normalisation, listing edge cases, accept round trip with the claimant key, error mapping, and the `accept` envelope.
