# Spec gaps found while reimplementing the Recorder core

Where `specifications/` (01, 03, 04, 05, fixtures) was silent, ambiguous or wrong, and what I did. I opened the
original code (components snapshot) only for items A1-A3.

## A. Answers found in the original code

| # | Missing | Where | Answer |
|---|---|---|---|
| A1 | `check_camera_url` OK text ("IP camera url: ...") vs the sensors line "IP camera <url>" | 02 §3.3 vs 03 §4.3.1 | The checker's own message is discarded; the sensors line is `IP camera {url}` (`COMP/application/_common_runtime_support.py`, `REC/.../warecorder_common_runtime.py:181-210`). |
| A2 | Exact msgids/placeholders of the checkup | 02 §3.3 | Taken from `COMP/application/_common_runtime_support.py` (`{cryptainer_dir}`, `{keyguardian_count}` ...); the ffmpeg "below required" msgid has a trailing space in 1.0, dropped. |
| A3 | Report block format (separators, `> ` indent, `Info`/`Message` labels with `COLON`) | 04 §13 | `COMP/utilities/__init__.py:209-258`; implemented in `decryption.format_operation_report`. |

## B. Gaps resolved by guessing

| # | Gap | What I did |
|---|---|---|
| B1 | **Contradiction OI-55 vs fixtures**: the task requires equality with `cryptoconf_*.json` (AES_CBC) while OI-55 recommends an authenticated cipher. | AES_CBC by default, `payload_cipher_algo` parameter; owner decision still needed (see README). |
| B2 | Supervisor timing: 01 §4.4 says the second spawn is "the 11th consecutive unanswered poll"; counted from the first spawn it is poll 14 overall. | Implemented the counter exactly (3, then 3+11 = 14); spec wording could say "11 polls after the spawn". |
| B3 | OI-14 recommendation ("marker only after a successful start, kept on graceful shutdown") does not say what a *refused* autostart at boot does to an existing marker. | Marker left untouched (retry at next boot). |
| B4 | 04 §11.1 does not say who gets the pushed status when no GUI is listening, nor the status of `recording` when every sensor is in backoff. | Pushes only after a `/broadcast_service_status` request; `recording` is true while any sensor is `running` or `restarting`, so "all failed" reads as idle although the toolchain keeps retrying (a new start rebuilds it). |
| B5 | OI-16 "fail the start when none started" does not define "started" for a capture that launches but dies at once (unreachable camera). | Started = the capture process was launched. A dead capture is OI-17's job (restart with backoff), shown as `restarting`. |
| B6 | OI-17 does not say what to do with the empty cryptainer left by a capture that died before sending data. | The record is discarded (files removed), like OI-19; otherwise a restart loop would flood the disk with empty cryptainers. |
| B7 | OI-38 "treat unknown versions as recent" vs 02 §3.3 which gives KO for "version couldn't be determined". | Unknown version = `[OK]` with the "beware" text, and no timeout option passed to ffmpeg. |
| B8 | OI-39: spec gives no text when ffmpeg is missing but not needed. | New line `Ffmpeg module is not required by the enabled sensors` (`[OK]`). |
| B9 | OI-44 asks for a quota "for example a percentage of the partition" but there is no setting for it (the 28 keys are fixed). | Only a free-space margin (max(200 MiB, 2 % of the partition)) is enforced at start and reported; no quota. |
| B10 | OI-36 wants the checkup to mention dropped guardians but gives no text. | Appended `({n} selected key guardian(s) not found were ignored)` to the guardians line. |
| B11 | New texts without EN/FR in the spec: invalid setting value, writable probe KO, ffmpeg not required, dropped guardians, guardian/sensor/storage errors. | EN msgids chosen here, FR written by me, to be reviewed (all in `locale_fr.py`). |
| B12 | 03 §10.4/OI-53: how does the GUI know which guardians "belong to the ongoing recording"? | `delete_guardians(..., protected_uids)`: the caller passes `get_selected_guardian_uids()` when `status["recording"]` is true. |
| B13 | OI-47 "before the build date" has no date. | `MIN_SANE_CLOCK` = 2025-09-01 (after the last recorder commit `efbf4ce`). |
| B14 | OI-46 does not say how old an orphan `.payload` must be to be purged. | 1 hour, because a payload briefly exists alone while keys are generated. |
| B15 | 04 §14.1 item 2 ("stock library decrypts what we write") is trivially the same installed library; the independence is only that the test calls the library's own `ReadonlyCryptainerStorage` and `check_cryptainer_sanity`, not our code. | Done that way for 1-of-2 and 2-of-2, RTSP, libcamera and arecord sensors. |
| B16 | Language of the status/refusal lines: the service speaks English (01 §9.1) so the GUI shows English checkup lines from `refusal`. | Documented; the GUI can re-run its own translated checkup. |
| B17 | The Flet-side persistence of "selection of guardians" vs `selected_keyguardians` ordering ("order of checking"). | `set_selected_keyguardians` stores the given order; first = shard 1. |

## C. Spec / fixture remarks

- 04 §10.5 / fixtures: the 2-of-2 fixture cryptainer is decryptable with the gateway fixture and no passphrase, as stated; the local pool has no private key for guardian B, so tests needing a local 2-of-2 import `usb_B` with private keys first.
- `OscClient` with a Unix socket needs `port=None`; the 1.0 `safer=True` sleeps 10 ns only, so it does not make sends reliable (irrelevant: fire and forget).
- A Unix socket path over ~100 bytes fails to bind: `INTERNAL_APP_ROOT` must stay short (tests use `/tmp/waXXXX`). Not mentioned in 01 §8.1 beyond "limited".
- `FilesystemKeystorePool.list_foreign_keystore_uids` raises on a malformed folder name (OI-36 says only the setting); `guardians.list_guardian_uids` skips such folders.
- The checklist (04 §0 item 8) says the final JSON uses a `~` suffix while writing; with the atomic write the `.crypt~` is still written (also atomically) and `.crypt.tmp` / `.crypt~.tmp` are transient names which no listing matches.
