"""Import every module and build every screen against a stub page (no Flet session)."""
import dataclasses
import importlib
import pkgutil
import shutil

import flet as ft

from conftest import FIXTURES, PASSPHRASES, flush, load_fixture
import waflet_authenticator
import waflet_components
from waflet_components.i18n import tr


def test_import_every_module():
    for package in (waflet_components, waflet_authenticator):
        for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            if not info.name.endswith("__main__"):  # Would start the app
                importlib.import_module(info.name)


def _texts(control, seen=None):
    """All strings found in a control tree (for cheap assertions)."""
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
                found += _texts(item, seen)
    return found


def test_every_screen_builds(stub_app, monkeypatch, fake_gateway):
    app, page = stub_app, stub_app.page
    monkeypatch.setattr(type(app), "get_gateway_proxy", lambda self: fake_gateway)
    assert app.stack == ["authenticator_management"] and len(page.views) == 1
    management = app.screens["authenticator_management"]
    assert management.status_result["status"] is False  # Fresh user profile
    assert "Initialize" in _texts(page.views[0])

    # Use a copy of the fixture authenticator as custom location
    custom = app.storage_roots.external_app_root / "usbkey"
    shutil.copytree(FIXTURES / "authenticator.keystore", custom / "authenticator.keystore")
    management._on_folder_selected(custom)
    assert management.status_result["status"] is True and app.custom_folder == str(custom)
    assert not management.button_publish.disabled and management.group_a[0].disabled

    for name in app.screens:
        if name == "authenticator_revelation_request_detail":
            app.selected_revelation_request = load_fixture("list_authenticator_revelation_requests.response.json")["result"][0]
        app.go(name)
        flush(app)
        assert app.stack[-1] == name and len(page.views) == len(app.stack)
        assert isinstance(page.views[-1], ft.View)

    # Request list got filled from the fake gateway, detail screen has its buttons enabled for a pending request
    listing = app.screens["authenticator_revelation_request_management"]
    assert len(listing.requests_by_status["PENDING"]) == 2
    detail = app.screens["authenticator_revelation_request_detail"]
    assert not detail.accept_button.disabled and not detail.reject_button.disabled

    # Accept through the screen (worker + callbacks), then we are back on the refreshed list
    detail.accept(PASSPHRASES["raw"])
    flush(app)
    flush(app)
    assert app.stack[-1] == "authenticator_revelation_request_management"
    assert len(listing.requests_by_status["ACCEPTED"]) == 1

    # Back/Escape: dialog first, then one level up, then let through on the home screen
    app.go("authenticator_revelation_request_detail")
    app.show_dialog("t", "x")
    assert app.handle_back() and app._current_dialog is None and app.stack[-1] == "authenticator_revelation_request_detail"
    assert app.handle_back() and app.stack[-1] == "authenticator_revelation_request_management"  # OI-43
    app.go("authenticator_management")
    assert app.handle_back() is False


def test_dialogs_settings_and_language(stub_app):
    app = stub_app
    management = app.screens["authenticator_management"]
    management.show_help()
    app.open_settings()
    assert "Authenticator v1.5 by Witness Angel" in _texts(app._current_dialog)
    app.close_dialog()
    app.switch_language("fr")
    assert app.page.views[-1].appbar.title.value == "Authentifieurs"
    assert management.status_text.value == "Authentifieur non initialisé"
    app.switch_language("en")
    management.check_passphrase()
    assert app._current_dialog.title.value == "Sanity check"


def test_creation_screen_flow(stub_app):
    app = stub_app
    app.go("authenticator_creation_form")
    screen = app.screens["authenticator_creation_form"]
    screen.keypair_count = 1  # Keep the test fast
    screen.owner_field.value, screen.passphrase_field.value, screen.hint_field.value = "Me", "short", "hint"
    screen.submit()
    assert app._current_dialog.title.value == "Validation error"
    app.close_dialog()
    screen.passphrase_field.value = PASSPHRASES["raw"]
    screen.submit()
    assert screen.passphrase_field.value == "***" and screen.initialize_button.disabled
    assert app.handle_back() and app.stack[-1] == "authenticator_creation_form"  # OI-12: Back ignored
    flush(app)
    assert app._current_dialog.title.value == "Success"
    app.handle_back()  # Closing the result dialog returns home
    assert app.stack == ["authenticator_management"]
    assert app.screens["authenticator_management"].status_result["status"] is True
    tr.lang = "en"
