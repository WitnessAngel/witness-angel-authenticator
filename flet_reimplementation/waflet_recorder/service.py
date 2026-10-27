"""The background recording service (01 §2, 03 §4): OSC commands in, recording toolchain out. GUI-free.

Run with `python -m waflet_recorder --service` (cron on a Pi, `ServiceController.start_service()` on a PC).

Fixes applied: OI-04 (flock single instance), OI-05 (shutdown always completes, never blocks the listener),
OI-06 (socket mode 0600), OI-11 (state under a lock), OI-14 (marker only after a successful start, kept on service
shutdown, removed only by an explicit stop), OI-15..18 + OI-44 (refusals and sensor health reported, 04 §11.1),
OI-45 (periodic purge when idle), OI-23 (peripheral failures never kill the service).
"""
import logging
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from wacryptolib.utilities import dump_to_json_str

from waflet_components.storage import compute_storage_roots, bootstrap_recorder_storage, is_raspberry_pi

from . import osc
from .checkup import run_checkup
from .cryptainers import purge_now, get_free_space_info
from .guardians import open_keystore_pool
from .logs import setup_process_logging
from .peripherals import create_peripherals
from .sensors import SensorState
from .settings import RecorderSettings, load_recorder_config
from .toolchain import build_recording_toolchain

logger = logging.getLogger(__name__)

STATUS_FORMAT = "service_status_1.0"
MAX_STATUS_TEXT = 200


class ServiceLock:
    """Exclusive lock held for the whole life of the service process (OI-04); released by the OS on any exit."""

    def __init__(self, roots):
        self._path = roots.internal_app_root / ".witnessangel_service.lock"
        self._file = None

    def acquire(self) -> bool:
        self._file = open(self._path, "a+")
        try:
            if osc.IS_WINDOWS:  # pragma: no cover
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self._file.close()
            self._file = None
            return False

    def release(self):
        if self._file:
            self._file.close()  # Closing the descriptor releases the lock
            self._file = None


def _truncate(text):
    return text if text is None or len(text) <= MAX_STATUS_TEXT else text[:MAX_STATUS_TEXT]


class RecorderService:
    SHUTDOWN_FLUSH_TIMEOUT_S = 30

    def __init__(self, roots, settings: RecorderSettings, pool, peripherals=None, toolchain_factory=build_recording_toolchain,
                 checkup_func=run_checkup, purge_interval_s=600, housekeeping_interval_s=5):
        self.roots, self.settings, self.pool = roots, settings, pool
        self._toolchain_factory, self._checkup_func = toolchain_factory, checkup_func
        self._purge_interval_s, self._housekeeping_interval_s = purge_interval_s, housekeeping_interval_s
        self._state_lock = threading.RLock()  # OI-11
        self._pending_changes = 0  # Starts/stops queued or running: > 0 is the 1.0 "_status_change_in_progress"
        self._toolchain = None
        self._refusal = None
        self._status_requested = False
        self._last_pushed_status = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="service_worker")
        self._peripheral_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="peripherals")  # OI-12
        self._termination_event = threading.Event()
        self._shutdown_started = False
        self.peripherals = peripherals or create_peripherals(settings)
        self._sender = osc.OscSender(roots, osc.GUI_SOCKET_INDEX)
        self._listener = osc.OscListener(roots, osc.SERVICE_SOCKET_INDEX, {
            osc.PING: self.ping,
            osc.SWITCH_DAEMONIZE_SERVICE: self.switch_daemonize_service,
            osc.START_RECORDING: self.start_recording,
            osc.STOP_RECORDING: self.stop_recording,
            osc.BROADCAST_RECORDING_STATE: self.broadcast_recording_state,
            osc.BROADCAST_SERVICE_STATUS: self.broadcast_service_status,
            osc.STOP_SERVER: self.stop_server,
        }, name="service")
        self._housekeeping_thread = threading.Thread(target=self._housekeeping, name="housekeeping", daemon=True)

    # ------------------------------------------------------------ lifecycle
    def start(self):
        """Open the control channel, set up peripherals, resume recording if the marker exists (03 §4.5)."""
        self._listener.start()
        if self.settings.is_raspberry_pi:
            try:
                self.peripherals.setup(self)
            except Exception:  # OI-23: never kill the service for a display
                logger.exception("Peripherals setup failed, continuing without them")
        self._housekeeping_thread.start()
        if self.roots.recording_marker.exists():
            logger.info("Recording marker found, resuming recording")
            return self.start_recording()
        return None

    def join(self):
        while not self._termination_event.wait(0.1):  # Polling keeps Ctrl-C working on Windows
            pass

    @property
    def in_progress(self):
        with self._state_lock:
            return self._pending_changes > 0

    @property
    def is_recording(self):
        toolchain = self._toolchain
        return bool(toolchain) and any(h["state"] in (SensorState.RUNNING, SensorState.RESTARTING)
                                       for h in toolchain.health())

    # ------------------------------------------------------------ OSC handlers (short, never block)
    def ping(self):
        logger.info("Ping successful!")
        self._send(osc.LOG_OUTPUT, "Pong")

    def switch_daemonize_service(self, value=False):
        logger.info("Service persistence switch to %s ignored (Android only)", bool(value))

    def start_recording(self, env=None):
        """Returns the worker future (tests, autostart), or None if ignored."""
        with self._state_lock:
            if self._pending_changes:
                logger.info("Service recording start ignored, because other status change is already in progress")
                return None
            self._pending_changes += 1
        logger.info("Service got command to START the recording")
        return self._executor.submit(self._offloaded_start_recording)

    def stop_recording(self, force=False):
        with self._state_lock:
            if self._pending_changes and not force:
                logger.info("Service recording stop ignored, because other status change is already in progress")
                return None
            self._pending_changes += 1
        logger.info("Service got command to STOP the recording")
        try:  # An explicit stop is the only thing which removes the marker (OI-14)
            self.roots.recording_marker.unlink()
        except FileNotFoundError:
            pass
        return self._executor.submit(self._offloaded_stop_recording)

    def toggle_recording(self):
        """For the physical buttons (01 §10.2)."""
        return self.stop_recording() if self.is_recording else self.start_recording()

    def broadcast_recording_state(self):
        """Ternary state: "" while a start/stop is in progress (OSC has no null), else int 0/1."""
        self._send(osc.RECEIVE_RECORDING_STATE, "" if self.in_progress else self.is_recording)

    def broadcast_service_status(self):
        self._status_requested = True
        self._push_status(force=True)

    def stop_server(self):
        """Never blocks the listener and always ends the service (OI-05)."""
        with self._state_lock:
            if self._shutdown_started:
                return
            self._shutdown_started = True
        logger.info("Service got command to SHUTDOWN entirely")
        threading.Thread(target=self._shutdown, name="service_shutdown", daemon=True).start()

    # ------------------------------------------------------------ worker jobs
    def _offloaded_start_recording(self):
        refusal = None
        try:
            if self._toolchain:
                if self.is_recording:
                    return
                self._drop_toolchain()  # Every sensor failed: rebuild everything
            self.settings.reload()  # Settings apply at each start (01 §6.1)
            checkup = self._checkup_func(self.settings, self.pool, refresh=True)
            if not checkup.ok:
                logger.error("Service failed to start recording because of configuration issues: %s",
                             "; ".join(checkup.messages))
                refusal = dict(checkup=[dict(ok=line.ok, message=_truncate(line.message)) for line in checkup.lines],
                               error=None)
                return
            toolchain = self._toolchain_factory(self.settings, self.pool, self.roots,
                                                activity_callback=self._on_activity)
            toolchain.start()  # Raises if no sensor could be started (OI-16)
            self._toolchain = toolchain
            self.roots.recording_marker.touch(exist_ok=True)  # Only now (OI-14)
            logger.info("Service successfully started recording")
        except Exception as exc:
            logger.error("Could not build or start recording toolchain: %r", exc, exc_info=True)
            refusal = dict(checkup=[], error=_truncate("%s: %s" % (type(exc).__name__, exc)))
        finally:
            with self._state_lock:
                self._refusal = refusal and dict(refusal, at=datetime.now(timezone.utc))
                self._pending_changes -= 1
            self._after_change()

    def _drop_toolchain(self):
        toolchain, self._toolchain = self._toolchain, None
        if toolchain:
            toolchain.stop()

    def _offloaded_stop_recording(self):
        try:
            if self._toolchain:
                logger.info("Service stopping recording")
                self._drop_toolchain()
                logger.info("Service successfully stopped recording")
        except Exception:
            logger.exception("Error while stopping the recording toolchain")
        finally:
            self._toolchain = None  # Next start rebuilds everything from fresh settings
            with self._state_lock:
                self._pending_changes -= 1
            self._after_change()

    def _after_change(self):
        self.broadcast_recording_state()
        self._push_status()
        self._peripheral_executor.submit(self._notify_peripherals_state)

    def _notify_peripherals_state(self):
        try:
            self.peripherals.on_recording_state_changed(self.is_recording)
        except Exception:
            logger.exception("Peripheral notification failed")

    def _on_activity(self, notification_type, **kwargs):
        self._peripheral_executor.submit(self._notify_peripherals_activity, notification_type, kwargs)

    def _notify_peripherals_activity(self, notification_type, kwargs):
        try:
            self.peripherals.on_activity(notification_type, **kwargs)
        except Exception:
            logger.exception("Peripheral activity notification failed")

    def _shutdown(self):
        try:
            if self._toolchain:
                future = self._executor.submit(self._offloaded_stop_recording_for_shutdown)
                future.result(timeout=self.SHUTDOWN_FLUSH_TIMEOUT_S)
        except Exception:
            logger.exception("Recording could not be flushed in time during shutdown")  # We exit anyway (OI-05)
        finally:
            self._housekeeping_stop = True
            try:
                self.peripherals.shutdown()
            except Exception:
                logger.exception("Peripherals shutdown failed")
            self._listener.stop()
            self._executor.shutdown(wait=False)
            self._peripheral_executor.shutdown(wait=False)
            self._termination_event.set()
            logger.info("Service shutdown is now complete")

    def _offloaded_stop_recording_for_shutdown(self):
        """Stop the toolchain WITHOUT touching the marker: a restarted service resumes recording (OI-14 b)."""
        with self._state_lock:
            self._pending_changes += 1
        self._offloaded_stop_recording()

    # ------------------------------------------------------------ status (04 §11.1)
    def get_service_status(self) -> dict:
        toolchain = self._toolchain
        sensors = [h for h in (toolchain.health() if toolchain else []) if h["state"] != SensorState.STOPPED]
        try:
            storage = get_free_space_info(self.settings.cryptainer_dir)
            storage = dict(free_bytes=storage["free_bytes"], full=storage["full"])
        except OSError:
            storage = dict(free_bytes=0, full=True)
        with self._state_lock:
            refusal = self._refusal
        return dict(
            status_format=STATUS_FORMAT,
            recording=None if self.in_progress else self.is_recording,
            refusal=refusal,
            sensors=[dict(h, error=_truncate(h["error"])) for h in sensors],
            storage=storage,
        )

    def _push_status(self, force=False):
        if not self._status_requested:
            return
        status = self.get_service_status()
        comparable = dict(status, sensors=[{k: v for k, v in s.items() if k != "last_data_utc"} for s in status["sensors"]])
        if not force and comparable == self._last_pushed_status:
            return
        self._last_pushed_status = comparable
        self._send(osc.RECEIVE_SERVICE_STATUS, dump_to_json_str(status))

    def _send(self, address, *values):
        self._sender.send(address, *values)

    # ------------------------------------------------------------ housekeeping thread
    _housekeeping_stop = False

    def _housekeeping(self):
        last_purge = 0.0
        while not self._housekeeping_stop and not self._termination_event.wait(self._housekeeping_interval_s):
            try:
                self._push_status()  # Only if something changed (sensor degraded, storage full...)
                if time.monotonic() - last_purge >= self._purge_interval_s:
                    last_purge = time.monotonic()
                    self.settings.reload()
                    purge_now(self.settings.cryptainer_dir, self.pool, self.settings.max_cryptainer_age_day)  # OI-45
            except Exception:
                logger.exception("Housekeeping failed")


def run_service(roots=None):
    """Entry point of `main.py --service`. Returns a process exit code."""
    roots = roots or compute_storage_roots("desktop", Path.home())
    bootstrap_recorder_storage(roots)
    setup_process_logging(roots, "service")
    lock = ServiceLock(roots)
    if not lock.acquire() or osc.is_peer_alive(roots):
        print(">>> %s - Witness Angel Recorder service already started and listening, aborting relaunch"
              % datetime.now().isoformat(sep=" ", timespec="seconds"))
        lock.release()
        return 0
    logger.info("Service process is starting")
    settings = RecorderSettings(load_recorder_config(roots), roots, is_raspberry_pi=is_raspberry_pi())
    service = RecorderService(roots, settings, open_keystore_pool(roots))
    signal.signal(signal.SIGTERM, lambda *_: service.stop_server())  # Flush the last records before exiting
    service.start()
    try:
        service.join()
    except KeyboardInterrupt:
        service.stop_server()
        service.join()
    finally:
        lock.release()
    return 0
