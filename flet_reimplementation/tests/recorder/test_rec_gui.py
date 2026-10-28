"""Recorder GUI on a stub page (no Flet session): every screen is built and the key actions are driven through the
screen objects, with a fake service controller and a fake gateway."""
import configparser
import dataclasses
import os
import shutil
import time

import flet as ft
import pytest

from conftest import StubPage
from rec_helpers import *  # noqa: F401,F403
from rec_helpers import FIXTURES, GUARDIAN_A, GUARDIAN_B, needs_fixtures, passphrases
from test_rec_crypto import FakeGatewayProxy, expected_payload
from waflet_components.i18n import tr
from waflet_recorder.app import WaRecorderApp, OFFLINE, IDLE, RECORDING
from waflet_recorder.settings import CONFIG_DEFAULTS_PATH
from waflet_recorder.screens.homepage import classify_preview, format_age

pytestmark = needs_fixtures

CRYPTAINER = "20261026_120000_rtsp_camera_cryptainer.mp4.crypt"  # 1-of-2, guardian A decrypts with its passphrase


class FakeController:
    def __init__(self):
        self.calls = []

    def start_recording(self, env=""):
        self.calls.append("start")

    def stop_recording(self):
        self.calls.append("stop")

    def stop_service(self, wait_s=None):
        self.calls.append(("stop_service", wait_s))

    def start_service(self):
        self.calls.append("spawn")

    def broadcast_recording_state(self):
        self.calls.append("poll")

    def broadcast_service_status(self):
        pass


def texts(control, seen=None):
    seen = set() if seen is None else seen
    if id(control) in seen:
        return []
    seen.add(id(control))
    found = []
    for field in dataclasses.fields(control):
        value = getattr(control, field.name, None)
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, str):
                found.append(item)
            elif isinstance(item, ft.BaseControl):
                found += texts(item, seen)
    return found


def find(control, kind, seen=None):
    seen = set() if seen is None else seen
    if id(control) in seen:
        return []
    seen.add(id(control))
    found = [control] if isinstance(control, kind) else []
    for field in dataclasses.fields(control):
        value = getattr(control, field.name, None)
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, ft.BaseControl):
                found += find(item, kind, seen)
    return found


def settle(app):
    for _ in range(2):
        app._executor.submit(lambda: None).result()
        app.checkup_executor.submit(lambda: None).result()


def make_app(roots, **kwargs):
    app = WaRecorderApp(StubPage(), storage_roots=roots, controller=FakeController(), is_pi=kwargs.pop("is_pi", False))
    app.setup()
    settle(app)
    return app


@pytest.fixture
def app(pool_roots, monkeypatch):
    monkeypatch.setenv("LANG", "en")
    app = make_app(pool_roots)
    app.config.set("network", "wagateway_url", "")  # Never reach a real gateway from tests
    yield app
    app._executor.shutdown(wait=True)
    app.checkup_executor.shutdown(wait=True)


@pytest.fixture
def cryptainers_app(app):
    shutil.copytree(FIXTURES / "cryptainers", app.settings.cryptainer_dir, dirs_exist_ok=True)
    return app


def dialog_texts(app):
    return texts(app.page.dialogs[-1])


def press(dialog, label):
    """Click the dialog action having this label."""
    button = next(b for b in find(dialog, ft.TextButton) if b.content == label or getattr(b, "text", None) == label)
    button.on_click(None)


# ------------------------------------------------------------------ shell

def test_every_screen_builds_and_drawer(app, cryptainers_app):
    assert app.stack == ["recorder_homepage"]
    assert set(app.screens) == {"recorder_homepage", "foreign_keystore_management", "cryptainer_storage_management",
                                "cryptainer_decryption_process", "cryptainer_decryption_result",
                                "claimant_revelation_request_creation_form", "claimant_revelation_request_management",
                                "claimant_revelation_request_detail"}
    app.screens["cryptainer_storage_management"].selection.add(CRYPTAINER)
    for name in app.screens:
        app.go(name)
        settle(app)
        assert app.stack[-1] == name and isinstance(app.page.views[-1], ft.View)
    drawer = app.build_drawer("recorder_homepage")
    assert [d.label for d in drawer.controls if isinstance(d, ft.NavigationDrawerDestination)] == \
        ["Recorder", "Key Guardians", "Containers"]
    assert app.page.views[-1].drawer is None  # Only top-level screens carry it
    app.go("foreign_keystore_management")
    assert app.page.views[-1].drawer is not None


def test_back_rules(app):
    app.go("cryptainer_storage_management")
    app.show_dialog("t", "x")
    assert app.handle_back() and app._current_dialog is None and app.stack[-1] == "cryptainer_storage_management"
    assert app.handle_back() and app.stack[-1] == "recorder_homepage"  # 01 §4.6
    assert not app.handle_back()  # Home: the OS decides
    app.go("claimant_revelation_request_detail")
    assert app.handle_back() and app.stack[-1] == "claimant_revelation_request_management"


def test_language_persisted_and_restored(pool_roots):
    app = make_app(pool_roots)
    app.switch_language("fr")
    assert app.config.get("gui", "language") == "fr"
    assert "Lancer Enregistrement" in texts(app.page.views[-1])
    again = make_app(pool_roots)  # A new process reads the config
    assert tr.lang == "fr" and "Lancer Enregistrement" in texts(again.page.views[-1])
    assert "Gardiens des Clés" in [d.label for d in again.build_drawer("x").controls if isinstance(d, ft.NavigationDrawerDestination)]


# ------------------------------------------------------------------ settings (02 §4)

def test_settings_schema_by_platform(pool_roots):
    desktop = make_app(pool_roots, is_pi=False)
    keys = [i["key"] for i in desktop.get_settings_schema() if "key" in i]
    assert keys == ["enable_ip_camera", "ip_camera_url", "recording_duration_mn", "keyguardian_threshold", "cryptainer_dir",
                    "max_cryptainer_age_day", "wagateway_url", "ffmpeg_rtsp_parameters", "ffmpeg_rtsp_output_format"]
    pi = make_app(pool_roots, is_pi=True)
    pi_keys = [i["key"] for i in pi.get_settings_schema() if "key" in i]
    defaults = configparser.ConfigParser(interpolation=None)
    defaults.read(CONFIG_DEFAULTS_PATH)
    all_keys = {k for sec in ("sensor", "keyguardian", "storage", "peripheral", "network") for k in defaults[sec]}
    assert set(pi_keys) == all_keys - {"selected_keyguardians"} and len(pi_keys) == 27  # Every key of 01 §6.2
    assert {"epaper_type", "lcd_type", "enable_button_shim", "live_preview_interval_s", "local_camera_rotation"} <= set(pi_keys)
    assert "Peripherals" in [i["title"] for i in pi.get_settings_schema() if i["type"] == "title"]


def test_settings_dialog_validates_and_saves_at_once(app):
    app.open_settings()
    dialog = app.page.dialogs[-1]
    fields = {f.label: f for f in find(dialog, ft.TextField)}
    duration = fields["Media recording duration (mn)"]
    duration.value = "0.5"
    duration.on_change(type("E", (), {"control": duration})())
    assert duration.error is None and app.config.get("sensor", "recording_duration_mn") == "0.5"  # OI-35: decimals
    for bad, error in (("abc", "Please enter a number"), ("0", "The value must be greater than 0"), ("-3", "The value must be greater than 0")):
        duration.value = bad
        duration.on_change(None)
        assert duration.error == error and app.config.get("sensor", "recording_duration_mn") == "0.5"
    threshold = fields["Key guardian threshold"]
    threshold.value = "1.5"
    threshold.on_change(None)
    assert threshold.error == "Please enter a whole number"
    url = fields["Witness Angel Gateway URL"]
    url.value = "ftp://x"
    url.on_change(None)
    assert url.error and app.config.get("network", "wagateway_url") == ""  # OI-41
    url.value = "https://gw.example/rpc/"
    url.on_change(None)
    assert url.error is None and app.settings.wagateway_url == "https://gw.example/rpc/"
    switch = next(s for s in find(dialog, ft.Switch) if s.label == "IP camera")
    switch.value = False
    switch.on_change(None)
    assert app.config.get("sensor", "enable_ip_camera") == "0"
    settle(app)
    assert "[KO] No sensors are enabled" in app.checkup_lines()  # Live checkup behind the panel (02 §3.4)
    app.page.dialogs[-1]  # Closing: the toast about the next restart
    app.close_dialog()
    assert any("only apply at next recording restart" in t for t in texts(app.page.dialogs[-1]))


def test_pi_options_dropdown_blank_value(pool_roots):
    app = make_app(pool_roots, is_pi=True)
    app.open_settings()
    dropdown = next(d for d in find(app.page.dialogs[-1], ft.Dropdown) if d.label == "E-paper type")
    dropdown.value = "waveshare_2.7_epaper"
    dropdown.on_select(None)
    assert app.settings.epaper_type == "waveshare_2.7_epaper"
    dropdown.value = "-"
    dropdown.on_select(None)
    assert app.config.get("peripheral", "epaper_type") == ""


# ------------------------------------------------------------------ homepage (02 §3)

def test_record_button_state_machine(app):
    home = app.screens["recorder_homepage"]
    assert app.record_state == OFFLINE and home.record_button.disabled and home.record_label.value == "Start Recording"
    app.apply_recording_state(False)
    assert app.record_state == IDLE and not home.record_button.disabled
    settle(app)
    assert any("[KO] 1 key guardian" in line or "0 key guardian(s) selected" in line for line in app.checkup_lines())
    home.on_record_pressed()  # A KO check: nothing is sent, the button comes back
    settle(app)
    assert app.controller.calls == [] and app.record_state == IDLE
    assert "Configuration errors prevent recording" in texts(app.page.dialogs[-1])
    app.screens["foreign_keystore_management"].toggle(GUARDIAN_A, True)
    settle(app)
    home.on_record_pressed()
    assert home.record_button.disabled  # BUSY: no double click
    home.on_record_pressed()
    settle(app)
    assert app.controller.calls == ["start"]
    app.apply_recording_state(None)  # In progress
    assert home.record_button.disabled
    app.apply_recording_state(True)
    assert app.record_state == RECORDING and home.record_label.value == "Stop Recording" and not home.record_button.disabled
    home.on_record_pressed()
    assert app.controller.calls == ["start", "stop"] and home.record_button.disabled and home.record_label.value == "Stop Recording"
    app.apply_recording_state(False)
    assert home.record_label.value == "Start Recording" and not home.record_button.disabled


def test_service_status_messages(app):
    home = app.screens["recorder_homepage"]
    app.apply_recording_state(True)
    refusal = dict(at="2026-10-27T10:00:00", error=None, checkup=[dict(ok=True, message="Sensors: IP camera x"),
                                                                  dict(ok=False, message="0 key guardian(s) selected, 1 of which necessary for decryption")])
    app.apply_service_status(dict(recording=True, refusal=refusal, sensors=[dict(name="rtsp_camera", state="restarting",
                                  last_data_utc=None, error="boom")], storage=dict(free_bytes=1, full=True)))
    snackbars = [texts(d) for d in app.page.dialogs if isinstance(d, ft.SnackBar)]
    assert any("Recording could not start: 0 key guardian(s) selected" in " ".join(t) for t in snackbars)
    assert any("almost full" in " ".join(t) for t in snackbars)
    assert "[KO] 0 key guardian(s) selected, 1 of which necessary for decryption" in home.checkup_box.value  # The service's lines
    assert home.status_text.visible and "Recording (degraded): rtsp_camera restarting" in home.status_text.value
    count = len(app.page.dialogs)
    app.apply_service_status(dict(recording=True, refusal=refusal, sensors=[], storage=dict(free_bytes=1, full=True)))
    assert len(app.page.dialogs) == count  # One snackbar per transition
    app.refresh_checkup()
    settle(app)
    assert "Sensors: IP camera rtsp://" in home.checkup_box.value  # The GUI's own run replaces the old refusal


def test_preview_freshness(app, pool_roots):
    assert classify_preview(10, True, 15) == "current" and classify_preview(10, False, 15) == "stale"
    assert classify_preview(2 * 15 * 60 + 1, True, 15) == "stale" and format_age(30) == "30 s" and format_age(7200) == "2 h"
    home = app.screens["recorder_homepage"]
    home.load_preview()
    home.show_preview()
    assert home.preview_image.opacity == 1 and not home.preview_caption.visible  # Logo
    pool_roots.preview_image.parent.mkdir(parents=True, exist_ok=True)
    pool_roots.preview_image.write_bytes(b"\xff\xd8jpeg")
    app.apply_recording_state(True)
    home.load_preview()
    home.show_preview()
    assert home.preview_image.src == b"\xff\xd8jpeg" and home.preview_image.opacity == 1
    old = time.time() - 3 * 3600
    os.utime(pool_roots.preview_image, (old, old))
    home.load_preview()
    home.show_preview()
    assert home.preview_image.opacity < 1 and "Last preview" in home.preview_caption.value


def test_reset_service_asks_then_stops_on_the_worker(app):
    home = app.screens["recorder_homepage"]
    app.apply_recording_state(False)
    home.ask_reset_service()
    assert app.controller.calls == []  # OI-13: confirmation first
    press(app.page.dialogs[-1], "Confirm")
    settle(app)
    assert app.controller.calls == [("stop_service", 45)] and app.record_state == OFFLINE


# ------------------------------------------------------------------ key guardians (02 §5)

def test_guardians_list_select_details_delete(app, pool_roots):
    screen = app.screens["foreign_keystore_management"]
    app.go(screen.name)
    settle(app)
    assert [g["keystore_uid"] for g in screen.guardians] == sorted([GUARDIAN_A, GUARDIAN_B])
    rows = " ".join(texts(screen.list_view))
    assert "Alice Guardian" in rows and "Bob Gardien" in rows
    screen.toggle(GUARDIAN_B, True)
    screen.toggle(GUARDIAN_A, True)
    assert app.settings.selected_keyguardians == [str(GUARDIAN_B), str(GUARDIAN_A)]  # Saved at once, in order
    screen.show_details(screen.guardians[0])
    body = " ".join(dialog_texts(app))
    assert "Type: AUTHENTICATOR" in body and "(private key" in body
    screen.ask_delete()
    assert "Alice Guardian" in " ".join(dialog_texts(app))  # OI-50: names the guardians
    app.apply_recording_state(True)
    press(app.page.dialogs[-1], "Confirm removal")
    settle(app)
    assert "cannot be removed" in " ".join(dialog_texts(app)) and len(screen.guardians) == 2  # OI-53
    app.apply_recording_state(False)
    screen.ask_delete()
    press(app.page.dialogs[-1], "Confirm removal")
    settle(app)
    assert screen.guardians == [] or all(g["keystore_uid"] not in (GUARDIAN_A, GUARDIAN_B) for g in screen.guardians)
    assert app.settings.selected_keyguardians == []  # OI-49: no leftover
    assert "Empty" in texts(screen.list_view)
    screen.ask_delete()
    assert "Please select key guardians to remove" in texts(app.page.dialogs[-1])


def test_guardians_import_from_usb_and_web(roots, monkeypatch):
    app = make_app(roots)
    screen = app.screens["foreign_keystore_management"]
    app.go(screen.name)
    settle(app)
    monkeypatch.setattr("waflet_recorder.screens.guardians.list_usb_authdevices", lambda platform: [])
    screen.import_from_usb()
    settle(app)
    assert "No connected authentication devices found" in texts(app.page.dialogs[-1])
    device = dict(authenticator_dir=FIXTURES / "authdevices" / "usb_A" / "authenticator.keystore")
    monkeypatch.setattr("waflet_recorder.screens.guardians.list_usb_authdevices", lambda platform: [device])
    screen.import_from_usb()
    settle(app)
    dialog = app.page.dialogs[-1]
    assert "Do you want to import the private keys (passphrase-protected) as well?" in texts(dialog)
    press(dialog, "Yes")
    settle(app)
    settle(app)
    assert "1 new authenticators imported, 0 updated, 0 skipped because corrupted" in texts(app.page.dialogs[-1])
    assert app.get_selected_guardian_uids() == [GUARDIAN_A]  # New guardians are auto-selected
    keypair = screen.guardians[0]["keypairs"][0]
    assert keypair["private_key_present"]
    # Gateway
    gateway = FakeGatewayProxy()
    response = load_fixture_json("gateway", "get_public_authenticator.response.json")["result"]
    gateway.published[response["keystore_uid"]] = response
    monkeypatch.setattr(type(app), "get_gateway_proxy", lambda self: gateway)
    screen.import_from_web("not-a-uuid")
    settle(app)
    assert "Import result: Failure" in texts(app.page.dialogs[-1]) and "Badly formed hexadecimal UUID string" in texts(app.page.dialogs[-1])
    screen.import_from_web("  %s " % str(response["keystore_uid"]).upper())
    settle(app)
    settle(app)
    assert "Import result: Success" in texts(app.page.dialogs[-1])
    assert response["keystore_uid"] in app.get_selected_guardian_uids() and len(screen.guardians) == 2
    screen.import_from_web("104eba5c-0000-0000-0000-000000000000")
    settle(app)
    assert "Authenticator does not exist" in texts(app.page.dialogs[-1])


# ------------------------------------------------------------------ containers (02 §6)

def test_containers_list_select_details_delete(cryptainers_app):
    app = cryptainers_app
    screen = app.screens["cryptainer_storage_management"]
    app.go(screen.name)
    settle(app)
    names = [e["name"] for e in screen.entries]
    assert len(names) == 3 and names[0].startswith("20261026_130000_to")  # Newest first
    shown = texts(screen.list_view)
    assert any(t.startswith("N° 1: 20261026_130000_to") for t in shown) and any(t.startswith("N° 3: " + CRYPTAINER) for t in shown)
    assert "selected: 0" in screen.banner.content.value
    screen.select_all()
    assert "selected: 3" in screen.banner.content.value
    screen.select_none()
    screen.guarded_toggle(CRYPTAINER, True)
    assert "selected: 1" in screen.banner.content.value
    screen.show_details(CRYPTAINER)
    settle(app)
    body = " ".join(dialog_texts(app))
    assert "Container ID" in body and "Alice Guardian" in body and "type authenticator" in body
    screen.show_details("20261026_123000_rtsp_camera_cryptainer.mp4.crypt")  # Unfinished: unreadable -> titled dialog
    settle(app)
    assert "cannot be read" in " ".join(dialog_texts(app)) and "20261026_123000" in " ".join(dialog_texts(app))
    screen.select_none()
    screen.ask_delete()
    assert "Please select containers to delete" in texts(app.page.dialogs[-1])
    screen.prepare_decryption()
    assert app.stack[-1] == "cryptainer_storage_management"
    screen.guarded_toggle(names[0], True)
    screen.ask_delete()
    press(app.page.dialogs[-1], "Confirm deletion")
    settle(app)
    settle(app)
    assert [e["name"] for e in screen.entries] == names[1:] and not (app.settings.cryptainer_dir / names[0]).exists()


def test_containers_invalid_storage_is_reported(app):
    app.config.set("storage", "cryptainer_dir", "/nonexistent/where")
    screen = app.screens["cryptainer_storage_management"]
    app.go(screen.name)
    settle(app)
    assert 'Invalid container storage: "/nonexistent/where"' in texts(screen.list_view)  # OI-80
    screen.select_all()  # OI-79: guarded no-op


# ------------------------------------------------------------------ decryption (02 §7)

def prepare(app, name=CRYPTAINER):
    containers = app.screens["cryptainer_storage_management"]
    app.go(containers.name)
    settle(app)
    containers.guarded_toggle(name, True)
    containers.prepare_decryption()
    settle(app)
    return app.screens["cryptainer_decryption_process"]


def test_decrypt_with_passphrase_and_report(cryptainers_app, pool_roots):
    app = cryptainers_app
    screen = prepare(app)
    assert app.stack[-1] == "cryptainer_decryption_process"
    rows = " ".join(texts(screen.guardian_list))
    assert "Alice Guardian" in rows and "Status: FOUND, passphrase: NOT SET" in rows
    assert "Private keys needed for decryption are present" in rows and "Private key(s) missing locally" in rows  # Bob has no private key
    assert screen.report_button.disabled is True and not screen.remote_button.disabled
    screen.ask_passphrase()
    field = find(app.page.dialogs[-1], ft.TextField)[0]
    assert field.password is True  # OI-67
    field.value = "wrong"
    press(app.page.dialogs[-1], "Check")
    settle(app)
    assert "Validation result: Failure" in texts(app.page.dialogs[-1])
    for expected in ("Validation result: Success", "Validation result: Information"):
        screen.ask_passphrase()
        find(app.page.dialogs[-1], ft.TextField)[0].value = passphrases()["usb_A"]
        press(app.page.dialogs[-1], "Check")
        settle(app)
        body = texts(app.page.dialogs[-1])
        assert expected in body
        assert not any(passphrases()["usb_A"] in t for t in body)  # OI-66: never echoed
    assert "passphrase: SET" in " ".join(texts(screen.guardian_list))
    screen.attempt_decryption()
    settle(app)
    assert app.stack[-1] == "cryptainer_decryption_result"
    result = app.last_decryption_results[0]
    assert result["success"] and result["export_path"].read_bytes() == expected_payload()
    assert result["export_path"].parent == pool_roots.exports_dir
    page = " ".join(texts(app.page.views[-1]))
    assert "1 out of 1 container(s) have been decrypted" in page and "SUCCESS" in page
    app.go_back()
    assert app.stack[-1] == "cryptainer_decryption_process"
    assert not screen.report_button.disabled
    app.go("cryptainer_storage_management")  # OI-68: leaving the flow forgets passphrases and report
    assert not app.passphrase_mapper.as_dict() and app.last_decryption_results is None


def test_decrypt_failure_shows_report_and_snackbar(cryptainers_app):
    app = cryptainers_app
    screen = prepare(app)
    screen.attempt_decryption()
    settle(app)
    assert app.stack[-1] == "cryptainer_decryption_result"
    assert not app.last_decryption_results[0]["success"]
    assert "All decryptions failed, see reports" in texts(app.page.dialogs[-1])
    assert "FAILURE" in " ".join(texts(app.page.views[-1])) and "0 out of 1" in " ".join(texts(app.page.views[-1]))


def test_french_decryption_screen(cryptainers_app):
    app = cryptainers_app
    prepare(app)
    app.switch_language("fr")
    page = " ".join(texts(app.page.views[-1]))
    assert "Tenter le déchiffrement" in page and "NON RENSEIGNÉE" in page and "TROUVÉ" in page


# ------------------------------------------------------------------ claimant (02 §8)

def test_request_form_submission_and_lists(cryptainers_app, monkeypatch):
    app = cryptainers_app
    gateway = FakeGatewayProxy()
    monkeypatch.setattr(type(app), "get_gateway_proxy", lambda self: gateway)
    prepare(app)
    form = app.screens["claimant_revelation_request_creation_form"]
    app.go(form.name)
    assert "Alice Guardian" in " ".join(texts(form.guardian_list)) and set(form.checks) == {GUARDIAN_A, GUARDIAN_B} or len(form.checks) == 2
    assert CRYPTAINER in form.summary.value
    form.send()
    assert "Please select authenticators" in texts(app.page.dialogs[-1])
    for box in form.checks.values():
        box.value = True
    form.description_field.value = "too short"
    form.send()
    assert "Description must be at least 10 characters long." in texts(app.page.dialogs[-1])
    form.description_field.value = "Police request 2026/456 for the incident"
    form.send()
    settle(app)
    dialog = app.page.dialogs[-1]
    assert "Successful requests: 2 out of 2" in texts(dialog) and app.stack[-1] == "claimant_revelation_request_creation_form"
    assert len(gateway.calls) == 2 and gateway.calls[0]["revelation_request_description"].startswith("Police request")
    press(dialog, "Close")  # OI-75: navigation on close
    assert app.stack[-1] == "cryptainer_storage_management"

    listing = app.screens["claimant_revelation_request_management"]
    app.go(listing.name)  # OI-76: fetched at each entry
    settle(app)
    assert [c for c in gateway.calls if isinstance(c, tuple)] and len(listing.groups) == 1
    assert "Authorization requests: 2" in texts(listing.list_view)
    listing.open_detail(listing.groups[0])
    detail = app.screens["claimant_revelation_request_detail"]
    page = " ".join(texts(app.page.views[-1]))
    assert "Container: 20261026_121500_rpi_microphone" in page and "Police request 2026/123" in page
    assert "Status: Accepted" in page  # OI-87: translated
    detail.show_summary(listing.groups[0]["entries"][0])
    body = " ".join(dialog_texts(app))
    assert "Description: Police request" in body and "Local key for response: RSA-OAEP" in body and "Symkey decryption status: Decrypted" in body


def test_request_form_gateway_errors(cryptainers_app, monkeypatch):
    app = cryptainers_app
    gateway = FakeGatewayProxy()
    from wacryptolib.exceptions import KeystoreDoesNotExist
    gateway.fail_for = {GUARDIAN_A: KeystoreDoesNotExist("x"), GUARDIAN_B: ConnectionError("down")}
    monkeypatch.setattr(type(app), "get_gateway_proxy", lambda self: gateway)
    prepare(app)
    form = app.screens["claimant_revelation_request_creation_form"]
    app.go(form.name)
    for box in form.checks.values():
        box.value = True
    form.description_field.value = "A long enough description"
    form.send()
    settle(app)
    body = "\n".join(texts(app.page.dialogs[-1]))
    assert "Successful requests: 0 out of 2" in body and "Error Report" in body and "does not exist in sql storage" in body

    class Down:
        def list_requestor_revelation_requests(self, **kw):
            raise OSError("down")
    monkeypatch.setattr(type(app), "get_gateway_proxy", lambda self: Down())
    app.go("claimant_revelation_request_management")
    settle(app)
    assert "Network error, please check the gateway url" in texts(app.page.dialogs[-1])
