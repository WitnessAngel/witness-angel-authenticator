# Witness Angel Recorder: GUI-free core (phase 1)

Reimplementation of the Recorder 1.0 core in Python on `wacryptolib` `warecorder_stable` (OI-100/101 decided),
written from `witness-angel-recorder/specifications/`. Everything here is importable **without Flet**, by the
GUI process and by the background service. The Flet GUI (phase 2) is built on top of the API below.

## Running

```bash
.venv-recorder/bin/python -m waflet_recorder --service     # background service (cron on a Pi, GUI spawns it on a PC)
.venv-recorder/bin/python -m pytest -q                     # whole suite (authenticator + recorder)
.venv-recorder/bin/python -m pytest -q tests/recorder      # recorder only
```

Use `.venv-recorder` only (Python 3.14, flet 1.0.5, oscpy, pytest, wacryptolib from `warecorder_stable`; nothing was
added to it). Recorder tests read the spec fixtures from `../../witness-angel-recorder/specifications/fixtures`
(override with `WA_RECORDER_FIXTURES`; the tests that need them are skipped when absent). ffmpeg (`/usr/bin/ffmpeg`)
is needed for the real-recording tests. Env: `WA_LOG_LEVEL` (an invalid value falls back to INFO), `WA_SERVICE_SCRIPT`
(1.0 compatible override of the service command, `<script>|<args>`).

Data lives in `~/.witnessangel/` exactly as in 1.0: `warecorder_config.ini`, `keystore_pool/`, `cryptainers/`,
`cache/video_preview_image.jpg`, `recording_in_progress`, `.wa_device_uid.json`, `.witnessangel{0,1}.sock`;
logs are now `logs/service.log` and `logs/gui.log` (one bounded file per process, OI-48) instead of `log.txt`.

## Structure and why

```
waflet_components/              (extended, backward compatible, authenticator tests unchanged)
  config.py                     + getboolean/getint/getfloat, reload(), atomic save (OI-33), retry on a half-written file
  storage.py                    + StorageRoots recorder paths, bootstrap_recorder_storage, is_raspberry_pi (OI-43)
  authenticator_services.py     get_gateway_proxy(url, timeout=None)
waflet_recorder/                ALL recorder logic. Not in waflet_components: nothing here is shared with the
                                Authenticator (sensors, service, OSC, cryptoconf, claimant), so 03 §12's "recorder_services.py"
                                is split by topic into this package; the components stay app-agnostic.
  settings.py                   RecorderSettings: typed view of the 28 keys; config_defaults.ini = the 1.0 file
  checkup.py  probes.py         the six [OK]/[KO] checks (EN/FR), ffmpeg / PulseAudio / Pi camera probes
  cryptoconf.py                 build_cryptoconf (byte-equal to fixtures/cryptoconf_*.json)
  cryptainers.py                storage (atomic writes, purge), naming, listing, details, deletion, free space
  sensors.py  toolchain.py      supervised capture subprocesses (RTSP, Pi libcamera/arecord), toolchain build/start/stop
  osc.py  service.py            OSC transport (byte-compatible), the service process and its state machine
  service_control.py            GUI side: spawn/stop the service, commands, supervisor poll, GuiChannel listener
  guardians.py                  keystore pool: list, import (USB, gateway), delete, selection
  decryption.py  claimant.py    local + remote decryption and report; revelation requests (create, list), device uid
  peripherals.py  logs.py       Pi peripherals interface (no-op default), per-process logging
  locale_fr.py                  French catalog (registered first by `import waflet_recorder`)
tests/recorder/                 rec_helpers.py (fixtures), test_rec_*.py
```

## API for the GUI phase

All functions are synchronous and may block (subprocess, filesystem, network): run them on the app worker, except
the explicitly cheap ones. Expected failures raise `ServiceError` subclasses carrying an English `msgid` (translate
with `tr._(exc.msgid)`), other errors are wacryptolib exceptions.

| Module / function | Purpose |
|---|---|
| `waflet_components.storage.compute_storage_roots` / `bootstrap_recorder_storage` / `is_raspberry_pi` / `get_wait_time_multiplier` | roots (`roots.keystore_pool_dir`, `default_cryptainers_dir`, `exports_dir`, `preview_image`, `recording_marker`, `device_uid_file`, `logs_dir`) and platform |
| `settings.load_recorder_config(roots)` -> `AppConfig`; `RecorderSettings(config, roots, is_raspberry_pi)` | typed getters (properties named like the keys), `set_selected_keyguardians(uids)`, `reload()`; `config.set(section, key, value)` saves atomically; `is_valid_gateway_url` for the settings dialog |
| `logs.setup_process_logging(roots, "gui")` | stderr + `logs/gui.log` |
| `checkup.run_checkup(settings, pool, refresh=False)` -> `CheckupResult` | `.ok`, `.lines` (`CheckupLine(ok, message)`), `.text` for the homepage panel. Run off the UI thread |
| `service_control.ServiceController(roots)` | `start_service()` (detached), `stop_service(wait_s)` (blocking, 45 s), `start_recording()`, `stop_recording()`, `broadcast_recording_state()`, `broadcast_service_status()`, `is_service_alive()`, `ping()` |
| `service_control.ServiceSupervisor(controller)` | `poll()` every `POLL_INTERVAL_S * multiplier` s (spawns the service after 3 silent polls), `on_answer()` |
| `service_control.GuiChannel(roots, on_recording_state, on_service_status, on_log, supervisor)` | `start()`/`stop()`; callbacks run on the OSC thread: `True`/`False`/`None` (change in progress) and the 04 §11.1 status dict (`recording`, `refusal{at, checkup[], error}`, `sensors[{name,state,last_data_utc,error}]`, `storage{free_bytes,full}`); marshal them to the UI thread |
| `guardians.open_keystore_pool(roots)`; `list_guardians(pool)`; `get_selected_guardian_uids(settings, pool)` | key guardian screen (`corrupted` entries are listed, never raise) |
| `guardians.import_from_authdevices(pool, authenticator_dirs, include_private_keys)` / `import_from_gateway(pool, proxy, text)` / `delete_guardians(pool, uids, protected_uids)` | import (auto-select `result["new"]`), delete (pass the recording guardians as protected) |
| `waflet_components.storage.list_usb_authdevices(platform)` | USB discovery, entries have `authenticator_dir` |
| `cryptainers.open_management_storage(dir, pool)` (None if invalid); `list_cryptainers`, `get_cryptainer_details`, `delete_cryptainers` | containers screen |
| `decryption.PassphraseMapper`; `get_trustee_status(storage, pool, names, mapper)`; `check_passphrase(pool, statuses, mapper, text)` | decryption preparation (`result` is `recognized`, `already_entered` or `no_match`; never display the passphrase) |
| `decryption.decrypt_cryptainers(storage, pool, names, mapper, exports_dir, gateway_url, requestor_uid)` | one result per cryptainer: `success`, `report`, `export_path`, `report_path`; `format_operation_report(report)` for the screen |
| `claimant.get_wa_device_uid(roots)`; `create_revelation_requests(...)`; `list_requests_by_cryptainer(proxy, uid)` | authorization requests (`result["ok"]`, `result["errors"][{keystore_uid, kind, message}]`) |
| `waflet_components.authenticator_services.get_gateway_proxy(url, timeout=10)` | gateway proxy, read `settings.wagateway_url` at each use |
| `service.run_service()` | what `main.py --service` does (the GUI never calls it) |

GUI to-do hints: `RecorderSettings.cryptainer_dir`, `max_cryptainer_age_day` etc. are plain properties for the
settings dialog; any value may raise `ValueError` if hand-edited (the checkup already handles it). Persist the
language yourself (OI-83); the service always speaks English (its checkup lines in the status are English).

## Open issues (05-open-issues.md): what was done

**Fixed**

| OI | Change |
|---|---|
| 02, 13 | Stop wait 45 s (> the service's 30 s flush); `stop_service` is blocking and meant for the worker. |
| 03 | Service spawned with `start_new_session` (detached); stderr in `logs/service.stderr.log`. |
| 04 | `flock` lock file `.witnessangel_service.lock` plus socket probe; no blind unlink of a live socket. |
| 05 | Shutdown runs off the listener thread, always completes (30 s flush, then exit anyway). |
| 08 | Unknown OSC addresses are logged correctly. |
| 11 | Start/stop state under a lock (pending-change counter). |
| 14 | Marker created only after a successful start, kept at service shutdown, removed only by an explicit stop. |
| 15, 16, 17, 18 | Proposed status message of 04 §11.1 implemented (`/broadcast_service_status`, `/receive_service_status`): refusal reason, per-sensor state, start fails if no sensor started, dead capture restarted with 1-60 s backoff, rollover failures retried. |
| 19, 20 | No empty cryptainer (missing binary, nothing captured); a name already used makes the sensor wait for the next second. |
| 28 | Default RTSP codec block cleaned: the overridden `-f ismv` and the no-effect `-probesize/-analyzeduration` are dropped; output is the same fragmented MP4. |
| 32, 33 | One parser without interpolation; atomic save; reload retries once. |
| 34, 35, 36, 37, 38, 39, 42, 43 | Writable probe; bad numbers give `[KO]` lines; malformed UIDs skipped and reported; ffmpeg version cached 60 s and parsed with `\d+.\d+` (unknown = recent); ffmpeg only required by sensors using it, PulseAudio errors give `[KO]`; `15` not `15.0`; Pi detection also reads the device-tree model. |
| 41 | `is_valid_gateway_url` (for the settings dialog). |
| 44 | Free-space margin checked at start (`StorageFullError`), reported in the status. No quota (no setting exists). |
| 45, 46, 47 | Periodic purge in the service; orphan payloads purged after 1 h; JSON via temp+fsync+rename, payload fsynced first; purge refused if the clock is before 2025-09. |
| 49, 51, 52, 53, 54 | Delete iterates a copy; corrupted keystores listed not fatal and ignored by the cryptoconf; USB import builds a temp folder then renames, missing private keys skipped; delete refused for recording guardians; RSA_OAEP keys only, `secrets`. |
| 66, 67(core), 68, 69, 70, 71, 72, 73, 74, 76 | Neutral duplicate-passphrase result; `PassphraseMapper` is an instance with `clear()`; failures are results; no silent overwrite of exports, header-only loads; reports written once; one gateway call per batch; 10 s timeout; per-guardian errors; list fetched at each call. |
| 06 | Socket file mode 0600 (names unchanged for interop). |
| 23 | Peripheral failures never kill the service. |
| 27 | `arecord` default rate 22050. |

**Decided / kept / not applied**

| OI | Choice |
|---|---|
| 01, 10 | Android out of scope; `/switch_daemonize_service` accepted and ignored. |
| 12 | Peripheral notifications run on their own worker. |
| 14 | As recommended (see above). |
| 29, 40 | Kept (parameters replace defaults, URL scheme only). |
| 30 | Default config unchanged (RTSP demo stream), as shipped. |
| 50 | Selection is only stored in the config; "used for recording" vs list selection is a GUI matter. |
| 55 | **Not applied**: AES_CBC stays, for equality with the fixtures; `build_cryptoconf(payload_cipher_algo=...)` takes `AES_EAX`/`CHACHA20_POLY1305`. Owner decision pending. |
| 77 | Response keys stay unprotected; a key whose submissions all failed is deleted. |
| 9 | Kept: booleans as OSC int32, ternary `""`; receivers accept `i`, `T`/`F` and `""`. |

## Not done

- Raspberry Pi hardware drivers (e-paper, LCD, GPIO buttons, Button SHIM): `peripherals.py` defines the interface and a no-op default only.
- picamera (legacy camera stack) and raspivid sensors: a legacy stack logs an error and the local camera is skipped. Pi sensors are tested by command line and with shim binaries only.
- Streaming decryption (OI-70): the library loads whole payloads.
- Windows: UDP ports and `msvcrt` lock are written but untested.
- Translations of the settings dialog labels (GUI phase).
