"""OSC control channel between GUI and service (01 §2.3, 04 §11). Message formats are those of 1.0, byte for byte.

Sockets (unchanged, so new and old processes interoperate): index 0 = GUI, 1 = service; Unix datagram sockets
`<INTERNAL_APP_ROOT>/.witnessangel{0,1}.sock`, UDP 127.0.0.1:6420/6421 on Windows.
Booleans travel as OSC int32 (oscpy), "state change in progress" as the empty string.
"""
import logging
import os
import socket
import stat
import sys
from pathlib import Path

from oscpy.client import OSCClient
from oscpy.parser import format_message
from oscpy.server import OSCThreadServer

logger = logging.getLogger(__name__)

GUI_SOCKET_INDEX, SERVICE_SOCKET_INDEX = 0, 1

# GUI -> service
PING = "/ping"
SWITCH_DAEMONIZE_SERVICE = "/switch_daemonize_service"  # Android only meaning; kept, never sent by the recorder GUI
START_RECORDING = "/start_recording"
STOP_RECORDING = "/stop_recording"
BROADCAST_RECORDING_STATE = "/broadcast_recording_state"
STOP_SERVER = "/stop_server"
BROADCAST_SERVICE_STATUS = "/broadcast_service_status"  # 04 §11.1 (proposal adopted: OI-15..18, OI-44)
# service -> GUI
RECEIVE_RECORDING_STATE = "/receive_recording_state"
RECEIVE_SERVICE_STATUS = "/receive_service_status"
LOG_OUTPUT = "/log_output"

IS_WINDOWS = sys.platform.startswith("win")


def encode_message(address, *values) -> bytes:
    """The exact datagram a peer receives (compare with fixtures/osc_messages.json)."""
    return format_message(address.encode("utf8"), list(values), encoding="utf8")[0]


def socket_options(roots, socket_index) -> dict:
    if IS_WINDOWS:
        return dict(address="127.0.0.1", port=6420 + socket_index, family="inet")
    return dict(address=str(roots.osc_socket_path(socket_index)), port=None, family="unix")


def is_peer_alive(roots, socket_index=SERVICE_SOCKET_INDEX) -> bool:
    """Liveness probe of 01 §4.1 (Unix: connect() to the socket file). Always False on Windows, where the
    single-instance guarantee comes from the lock file (`ServiceLock`)."""
    options = socket_options(roots, socket_index)
    if options["family"] != "unix":
        return False
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(options["address"])
        except (ConnectionRefusedError, FileNotFoundError):
            return False
        except OSError:
            return False
    return True


def parse_ternary(value):
    """`/receive_recording_state` argument -> True / False / None (change in progress). Accepts int, bool, T/F, ""."""
    if value == "" or value is None:
        return None
    return bool(value)


class RobustOSCThreadServer(OSCThreadServer):
    """Keeps listening whatever a handler raises (01 §2.3)."""

    def _listen(self):
        while self._must_loop:
            try:
                super()._listen()
                return
            except Exception:
                if self._must_loop:
                    logger.exception("OSC listener loop failed, restarting it")


class OscListener:
    """Binds one socket and dispatches addresses to plain callables (positional OSC arguments)."""

    def __init__(self, roots, socket_index, handlers: dict, name="listener"):
        self._roots, self._index, self._name = roots, socket_index, name
        self._server = RobustOSCThreadServer(encoding="utf8", default_handler=self._unknown_address)
        self._handlers = handlers
        self._sock = None

    def _unknown_address(self, address, *values):  # OI-08: 1.0 raised a TypeError here
        logger.error("Unknown OSC address %s called on %s listener, with arguments %s", address, self._name, list(values))

    def _wrap(self, address, handler):
        def safe(*values):
            try:
                handler(*values)
            except Exception:  # safe_catch_unhandled_exception
                logger.exception("Unhandled exception in OSC handler %s", address)
        return safe

    def start(self):
        options = socket_options(self._roots, self._index)
        if options["family"] == "unix":
            # Callers hold the service lock (or probed the socket) before binding: a leftover file is dead (OI-04)
            Path(options["address"]).unlink(missing_ok=True)
        logger.info("Binding OSC %s listener to %s", self._name, options)
        self._sock = self._server.listen(default=True, **options)
        if options["family"] == "unix":
            os.chmod(options["address"], stat.S_IRUSR | stat.S_IWUSR)  # OI-06: owner only
        for address, handler in self._handlers.items():
            self._server.bind(address, self._wrap(address, handler))

    def stop(self):
        try:
            self._server.terminate_server()  # First: the loop must not restart on the sockets closed below
            self._server.stop_all()
        except Exception:
            logger.exception("Error while stopping OSC listener")
        options = socket_options(self._roots, self._index)
        if options["family"] == "unix":
            Path(options["address"]).unlink(missing_ok=True)


class OscSender:
    """Fire-and-forget client towards the peer's socket; a missing peer is normal and swallowed."""

    def __init__(self, roots, to_socket_index):
        options = socket_options(roots, to_socket_index)
        family = options.pop("family")
        self._sock = socket.socket(socket.AF_UNIX if family == "unix" else socket.AF_INET, socket.SOCK_DGRAM)
        self._client = OSCClient(encoding="utf8", sock=self._sock, **options)

    def send(self, address, *values):
        logger.debug("OSC message sent: %s %s", address, values)
        try:
            self._client.send_message(address.encode("utf8"), list(values), safer=True)
            return True
        except OSError:  # ConnectionRefused / FileNotFound: peer not there (yet)
            return False
        except Exception as exc:
            logger.warning("Could not send OSC message %s%s: %r", address, values, exc)
            return False

    def close(self):
        self._sock.close()
