"""OSC datagrams, GUI/service channel, service state machine (in-process fake toolchain) and a real service subprocess."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
from wacryptolib.utilities import generate_uuid0

from rec_helpers import *  # noqa: F401,F403
from rec_helpers import FIXTURES, GUARDIAN_A, GUARDIAN_B, ROOT, needs_fixtures, make_settings
from test_rec_sensors import SHIMS, needs_ffmpeg, stock_decrypt  # noqa: F401
from waflet_components.storage import compute_storage_roots, bootstrap_recorder_storage
from waflet_recorder import osc
from waflet_recorder.checkup import CheckupResult, CheckupLine
from waflet_recorder.guardians import open_keystore_pool
from waflet_recorder.service import RecorderService, ServiceLock, STATUS_FORMAT
from waflet_recorder.service_control import ServiceController, ServiceSupervisor, GuiChannel, default_service_command
from waflet_recorder.settings import RecorderSettings, load_recorder_config

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="unix sockets")


def wait_until(condition, timeout=15, message="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError("Timeout waiting for " + message)


@pytest.fixture
def short_roots():
    """Unix socket paths are limited to ~100 bytes: pytest's tmp_path is too long."""
    home = Path(tempfile.mkdtemp(prefix="wa"))
    roots = compute_storage_roots("desktop", home)
    bootstrap_recorder_storage(roots)
    yield roots
    shutil.rmtree(home, ignore_errors=True)


def test_osc_datagrams_match_fixtures():
    for message in json.loads((FIXTURES / "osc_messages.json").read_text()) if FIXTURES.is_dir() else []:
        assert osc.encode_message(message["address"], *eval(message["python_values"])).hex() == message["datagram_hex"]


def test_ternary_parsing():
    assert [osc.parse_ternary(v) for v in (1, 0, True, False, "", None)] == [True, False, True, False, None, None]


def test_listener_and_sender_over_real_unix_socket(short_roots):
    received = []
    unknown_ok = []
    listener = osc.OscListener(short_roots, osc.GUI_SOCKET_INDEX, {osc.RECEIVE_RECORDING_STATE: lambda v: received.append(v),
                                                                   osc.LOG_OUTPUT: lambda text: 1 / 0}, name="t")
    listener.start()
    assert oct(short_roots.osc_socket_path(0).stat().st_mode & 0o777) == "0o600"  # OI-06
    sender = osc.OscSender(short_roots, osc.GUI_SOCKET_INDEX)
    sender.send(osc.RECEIVE_RECORDING_STATE, True)
    sender.send(osc.RECEIVE_RECORDING_STATE, "")
    sender.send(osc.LOG_OUTPUT, "boom")  # A failing handler does not stop the server
    sender.send("/unknown/address", 1, "x")  # OI-08: logged, no crash
    sender.send(osc.RECEIVE_RECORDING_STATE, False)
    wait_until(lambda: len(received) == 3)
    assert received == [1, "", 0]
    listener.stop()
    assert not short_roots.osc_socket_path(0).exists()
    assert sender.send(osc.PING) is False  # Peer gone: swallowed


def test_supervisor_spawn_schedule():
    class Controller:
        def __init__(self):
            self.log = []

        def start_service(self):
            self.log.append("spawn")

        def broadcast_recording_state(self):
            self.log.append("state")

        def broadcast_service_status(self):
            self.log.append("status")

    controller = Controller()
    supervisor = ServiceSupervisor(controller)
    outcomes = [supervisor.poll() for _ in range(3)]
    assert outcomes == ["queried", "queried", "spawned"] and supervisor.unanswered == -8  # 3rd unanswered poll
    outcomes = [supervisor.poll() for _ in range(10)]
    assert outcomes.count("spawned") == 0 and supervisor.unanswered == 2
    supervisor.on_answer()
    assert supervisor.unanswered == 0


def test_supervisor_second_spawn_on_11th_unanswered_poll():
    class Controller:
        spawns = 0

        def start_service(self): Controller.spawns += 1
        def broadcast_recording_state(self): pass
        def broadcast_service_status(self): pass

    supervisor = ServiceSupervisor(Controller())
    results = [supervisor.poll() for _ in range(14)]
    assert [i + 1 for i, r in enumerate(results) if r == "spawned"] == [3, 14]  # 11 polls after the first spawn


def test_service_lock_is_exclusive(short_roots):
    first, second = ServiceLock(short_roots), ServiceLock(short_roots)
    assert first.acquire() and not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


# ------------------------------------------------------------------ in-process service with a fake toolchain

class FakeToolchain:
    def __init__(self, fail=False):
        self.fail, self.running, self.stopped = fail, False, 0

    def start(self):
        if self.fail:
            raise RuntimeError("camera busy")
        self.running = True
        return self.health()

    def stop(self):
        self.running = False
        self.stopped += 1

    def health(self):
        return [dict(name="rtsp_camera", state="running" if self.running else "stopped", last_data_utc=None, error=None)]


@pytest.fixture
def service_env(short_roots):
    states, statuses = [], []
    gui = GuiChannel(short_roots, on_recording_state=states.append, on_service_status=statuses.append)
    gui.start()
    settings = RecorderSettings(load_recorder_config(short_roots), short_roots)
    toolchains = []

    def factory(settings, pool, roots, activity_callback=None):
        toolchain = FakeToolchain(fail=getattr(factory, "fail", False))
        toolchains.append(toolchain)
        return toolchain

    ok = CheckupResult([CheckupLine(True, "fine")])
    ko = CheckupResult([CheckupLine(True, "fine"), CheckupLine(False, "No sensors are enabled")])
    checkups = {"result": ok}
    service = RecorderService(short_roots, settings, open_keystore_pool(short_roots), toolchain_factory=factory,
                              checkup_func=lambda *a, **k: checkups["result"], housekeeping_interval_s=0.1, purge_interval_s=3600)
    service.start()
    controller = ServiceController(short_roots)
    yield dict(service=service, controller=controller, states=states, statuses=statuses, factory=factory,
               toolchains=toolchains, checkups=checkups, ok=ok, ko=ko, roots=short_roots)
    service.stop_server()
    service._termination_event.wait(10)
    gui.stop()


def test_service_start_stop_and_marker(service_env):
    env = service_env
    controller, service, roots = env["controller"], env["service"], env["roots"]
    controller.broadcast_service_status()  # Subscribes to status pushes
    controller.start_recording()
    wait_until(lambda: env["states"][-1:] == [True], message="recording state")
    assert roots.recording_marker.exists() and service.is_recording
    controller.start_recording()  # Idempotent: no second toolchain
    controller.broadcast_recording_state()
    time.sleep(0.3)
    assert len(env["toolchains"]) == 1
    wait_until(lambda: env["statuses"] and env["statuses"][-1]["recording"] is True, message="status push")
    status = env["statuses"][-1]
    assert status["status_format"] == STATUS_FORMAT and status["sensors"][0]["name"] == "rtsp_camera" and status["refusal"] is None
    assert set(status["storage"]) == {"free_bytes", "full"}
    controller.stop_recording()
    wait_until(lambda: env["states"][-1:] == [False], message="idle state")
    assert not roots.recording_marker.exists() and env["toolchains"][0].stopped == 1


def test_service_checkup_refusal_is_reported_and_leaves_no_marker(service_env):
    env = service_env
    env["checkups"]["result"] = env["ko"]
    env["controller"].broadcast_service_status()
    env["controller"].start_recording()
    wait_until(lambda: env["statuses"] and env["statuses"][-1]["refusal"], message="refusal status")  # OI-15
    refusal = env["statuses"][-1]["refusal"]
    assert refusal["checkup"][1] == {"ok": False, "message": "No sensors are enabled"} and refusal["error"] is None
    assert not env["roots"].recording_marker.exists() and env["states"][-1] is False and not env["toolchains"]  # OI-14 a


def test_service_toolchain_failure_reported(service_env):
    env = service_env
    env["factory"].fail = True
    env["controller"].broadcast_service_status()
    env["controller"].start_recording()
    wait_until(lambda: env["statuses"] and env["statuses"][-1]["refusal"], message="refusal")
    assert env["statuses"][-1]["refusal"]["error"] == "RuntimeError: camera busy"
    assert env["states"][-1] is False and not env["roots"].recording_marker.exists()


def test_service_stop_server_keeps_marker_and_terminates(service_env):
    env = service_env
    env["controller"].start_recording()
    wait_until(lambda: env["service"].is_recording)
    env["controller"].stop_server()
    wait_until(env["service"]._termination_event.is_set, message="termination")  # OI-05
    assert env["roots"].recording_marker.exists() and env["toolchains"][0].stopped == 1  # OI-14 b
    assert not env["roots"].osc_socket_path(1).exists()


def test_service_ping_answers_pong(short_roots):
    logs = []
    gui = GuiChannel(short_roots, on_log=logs.append)
    gui.start()
    settings = RecorderSettings(load_recorder_config(short_roots), short_roots)
    service = RecorderService(short_roots, settings, open_keystore_pool(short_roots), housekeeping_interval_s=0.1)
    service.start()
    ServiceController(short_roots).ping()
    wait_until(lambda: logs == ["Pong"])
    service.stop_server()
    service._termination_event.wait(10)
    gui.stop()


# ------------------------------------------------------------------ real service process

@needs_fixtures
@needs_ffmpeg
def test_service_subprocess_end_to_end(tmp_path):
    home = Path(tempfile.mkdtemp(prefix="wa"))
    try:
        roots = compute_storage_roots("desktop", home)
        bootstrap_recorder_storage(roots)
        shutil.rmtree(roots.keystore_pool_dir)
        shutil.copytree(FIXTURES / "keystore_pool", roots.keystore_pool_dir)
        shim_dir = home / "bin"
        shim_dir.mkdir()
        (shim_dir / "ffmpeg").write_text(SHIMS["ffmpeg"])
        (shim_dir / "ffmpeg").chmod(0o755)
        config = make_settings(roots, **{"keyguardian.selected_keyguardians": "%s,%s" % (GUARDIAN_A, GUARDIAN_B),
                                        "keyguardian.keyguardian_threshold": 1, "sensor.recording_duration_mn": 0.05,
                                        "sensor.ip_camera_url": "rtsp://127.0.0.1/shim"}).config
        config.save()
        env = dict(os.environ, HOME=str(home), PATH="%s:%s" % (shim_dir, os.environ["PATH"]), PYTHONPATH=str(ROOT))
        states = []
        gui = GuiChannel(roots, on_recording_state=states.append)
        gui.start()
        controller = ServiceController(roots, env=env)
        supervisor = ServiceSupervisor(controller)
        controller.start_service()
        wait_until(controller.is_service_alive, message="service socket")
        process = controller._process

        second = subprocess.run(default_service_command(), cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        assert second.returncode == 0 and "already started" in second.stdout  # OI-04

        controller.start_recording()
        wait_until(lambda: states[-1:] == [True] or controller.broadcast_recording_state() or False, message="recording")
        wait_until(lambda: states[-1:] == [True], timeout=30)
        assert roots.recording_marker.exists()
        time.sleep(4)
        controller.stop_recording()
        wait_until(lambda: (controller.broadcast_recording_state(), states[-1:] == [False])[1], timeout=30, message="stopped")
        assert not roots.recording_marker.exists()
        pool = open_keystore_pool(roots)
        names = sorted(p.name for p in roots.default_cryptainers_dir.glob("*.crypt"))
        assert len(names) >= 1
        for name in names:
            assert b"ftyp" in stock_decrypt(roots.default_cryptainers_dir, pool, name)[:32]

        # Marker + restart: a stopped-by-shutdown service resumes recording by itself
        controller.start_recording()
        wait_until(lambda: (controller.broadcast_recording_state(), states[-1:] == [True])[1], timeout=30)
        controller.stop_service()  # Graceful, waits for exit
        assert process.poll() == 0 and roots.recording_marker.exists()
        controller.start_service()
        wait_until(lambda: (controller.broadcast_recording_state(), states[-1:] == [True])[1], timeout=30, message="autostart")
        controller.stop_recording()
        wait_until(lambda: (controller.broadcast_recording_state(), states[-1:] == [False])[1], timeout=30)
        controller.stop_service()
        assert controller._process is None and not controller.is_service_alive()
        gui.stop()
        log = (roots.logs_dir / "service.log").read_text()
        assert "Service process is starting" in log
    finally:
        shutil.rmtree(home, ignore_errors=True)
