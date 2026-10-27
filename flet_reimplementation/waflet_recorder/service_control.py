"""GUI side of the service channel (01 §2.2, §2.3, §4.4): spawn/stop the service, send commands, receive states.

Nothing here imports Flet: the GUI calls `ServiceSupervisor.poll()` from a timer, `GuiChannel` delivers
callbacks on the OSC listener thread (marshal them to the UI thread).
"""
import logging
import os
import subprocess
import sys
from pathlib import Path

from wacryptolib.utilities import load_from_json_str

from . import osc

logger = logging.getLogger(__name__)

SERVICE_FLUSH_TIMEOUT_S = 30  # The service allows itself that long to finalize the last records (03 §4.4)
SERVICE_STOP_WAIT_S = 45  # OI-02: must exceed the flush timeout; multiply by WAIT_TIME_MULTIPLIER on a Pi
POLL_INTERVAL_S = 2  # Multiplied by WAIT_TIME_MULTIPLIER (4 on a Pi)
UNANSWERED_POLLS_BEFORE_SPAWN = 2  # Spawn on the 3rd consecutive unanswered poll...
SPAWN_COUNTER_RESET = -8  # ...then again only on the 11th


def default_service_command():
    """`WA_SERVICE_SCRIPT` (1.0 compatible: `<script>|<args>`), else this package; frozen builds relaunch themselves."""
    configured = os.environ.get("WA_SERVICE_SCRIPT")
    if configured:
        return [sys.executable] + configured.split("|")
    if getattr(sys, "frozen", False):
        return [sys.executable, "--service"]
    return [sys.executable, "-m", "waflet_recorder", "--service"]


class ServiceController:
    """Fire-and-forget commands + process management. All methods are non-blocking except `stop_service`."""

    def __init__(self, roots, command=None, cwd=None, env=None):
        self._roots = roots
        self._command = command or default_service_command()
        self._cwd = cwd or str(Path(__file__).resolve().parents[1])
        self._env = env
        self._process = None  # Only set when this GUI spawned the service
        self._sender = osc.OscSender(roots, osc.SERVICE_SOCKET_INDEX)

    # ---- process
    def start_service(self):
        """Spawn the service detached from this process (OI-03), its stderr going to `logs/service.stderr.log`."""
        logger.info("Starting service with command %s", self._command)
        kwargs = dict(start_new_session=True) if not osc.IS_WINDOWS else dict(
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        self._roots.logs_dir.mkdir(parents=True, exist_ok=True)
        stderr = open(self._roots.logs_dir / "service.stderr.log", "ab")
        try:
            self._process = subprocess.Popen(self._command, shell=False, cwd=self._cwd, env=self._env,
                                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=stderr, **kwargs)
        finally:
            stderr.close()

    def stop_service(self, wait_s=SERVICE_STOP_WAIT_S):
        """Graceful stop; if this GUI spawned the service, wait `wait_s` then kill it (01 §2.2). Blocking: use a worker."""
        self.stop_server()
        process, self._process = self._process, None
        if process is None:
            return
        try:
            process.wait(timeout=wait_s)
        except subprocess.TimeoutExpired:
            logger.error("Service did not stop within %s s, killing it", wait_s)
            process.kill()
            process.wait(timeout=5)

    def is_service_alive(self):
        return osc.is_peer_alive(self._roots)

    # ---- commands (04 §11)
    def ping(self):
        self._sender.send(osc.PING)

    def switch_daemonize_service(self, value):
        self._sender.send(osc.SWITCH_DAEMONIZE_SERVICE, bool(value))

    def start_recording(self, env=""):
        self._sender.send(osc.START_RECORDING, env)

    def stop_recording(self):
        self._sender.send(osc.STOP_RECORDING)

    def broadcast_recording_state(self):
        self._sender.send(osc.BROADCAST_RECORDING_STATE)

    def broadcast_service_status(self):
        self._sender.send(osc.BROADCAST_SERVICE_STATUS)

    def stop_server(self):
        self._sender.send(osc.STOP_SERVER)


class ServiceSupervisor:
    """The GUI's self-healing poll of 01 §4.4. Call `poll()` every `POLL_INTERVAL_S * multiplier` seconds,
    `on_answer()` whenever the service answered (any `/receive_recording_state`)."""

    def __init__(self, controller):
        self._controller = controller
        self.unanswered = 0

    def poll(self):
        self.unanswered += 1
        if self.unanswered > UNANSWERED_POLLS_BEFORE_SPAWN:
            self.unanswered = SPAWN_COUNTER_RESET
            self._controller.start_service()
            return "spawned"
        self._controller.broadcast_recording_state()
        self._controller.broadcast_service_status()
        return "queried"

    def on_answer(self):
        self.unanswered = 0


class GuiChannel:
    """Listener on the GUI socket. Callbacks (called on the listener thread):
    `on_recording_state(True|False|None)` (None = start/stop in progress), `on_service_status(dict)` (04 §11.1),
    `on_log(str)`; `supervisor` (optional) is told about each answer."""

    def __init__(self, roots, on_recording_state=None, on_service_status=None, on_log=None, supervisor=None):
        self._on_recording_state = on_recording_state
        self._on_service_status = on_service_status
        self._on_log = on_log
        self._supervisor = supervisor
        self._listener = osc.OscListener(roots, osc.GUI_SOCKET_INDEX, {
            osc.RECEIVE_RECORDING_STATE: self._receive_recording_state,
            osc.RECEIVE_SERVICE_STATUS: self._receive_service_status,
            osc.LOG_OUTPUT: self._receive_log,
        }, name="application")

    def start(self):
        self._listener.start()

    def stop(self):
        self._listener.stop()

    def _receive_recording_state(self, value):
        if self._supervisor:
            self._supervisor.on_answer()
        if self._on_recording_state:
            self._on_recording_state(osc.parse_ternary(value))

    def _receive_service_status(self, text):
        if self._on_service_status:
            try:
                status = load_from_json_str(text)
            except ValueError as exc:
                logger.warning("Bad service status message: %r", exc)
                return
            self._on_service_status(status)

    def _receive_log(self, text):
        if self._on_log:
            self._on_log(text)
