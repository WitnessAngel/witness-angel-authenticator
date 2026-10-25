import asyncio
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wacryptolib.exceptions import (  # noqa: E402
    KeystoreDoesNotExist, KeystoreAlreadyExists, AuthenticationError, ValidationError,
)
from wacryptolib.utilities import load_from_json_bytes  # noqa: E402

FIXTURES = ROOT.parent / "specifications" / "fixtures"
PASSPHRASES = json.loads((FIXTURES / "passphrase.json").read_text(encoding="utf8"))


def load_fixture(name):
    return load_from_json_bytes((FIXTURES / "gateway" / name).read_bytes())


@pytest.fixture
def authenticator_dir(tmp_path):
    """A writable copy of fixtures/authenticator.keystore."""
    target = tmp_path / "authenticator.keystore"
    shutil.copytree(FIXTURES / "authenticator.keystore", target)
    return target


@pytest.fixture
def edge_cases_dir(tmp_path):
    target = tmp_path / "edge.keystore"
    shutil.copytree(FIXTURES / "edge_cases.keystore", target)
    return target


class FakeGateway:
    """In-memory gateway applying the server rules of 03 §7.3 / 04 §7.3, fed with the fixture payloads."""

    def __init__(self, secret, published=None, requests=None):
        self.secret = secret
        self.published = published
        self.requests = requests if requests is not None else load_fixture(
            "list_authenticator_revelation_requests.response.json")["result"]
        self.calls = []

    def _auth(self, secret):
        if secret != self.secret:
            raise AuthenticationError("bad secret")

    def get_public_authenticator(self, keystore_uid, keystore_secret=None):
        self.calls.append(("get_public_authenticator", dict(keystore_uid=keystore_uid, keystore_secret=keystore_secret)))
        if self.published is None:
            raise KeystoreDoesNotExist("Authenticator %s does not exist in database" % keystore_uid)
        if keystore_secret is not None:
            self._auth(keystore_secret)
        return self.published

    def set_public_authenticator(self, **params):
        self.calls.append(("set_public_authenticator", params))
        if self.published is not None:
            raise KeystoreAlreadyExists("already")
        assert set(params) <= {"keystore_uid", "keystore_owner", "keystore_secret", "public_keys", "keystore_creation_datetime"}
        assert params["public_keys"] and params["keystore_owner"]
        self.published = dict(keystore_uid=params["keystore_uid"], keystore_owner=params["keystore_owner"],
                              keystore_creation_datetime=params.get("keystore_creation_datetime"),
                              public_keys=params["public_keys"])

    def list_authenticator_revelation_requests(self, authenticator_keystore_uid, authenticator_keystore_secret):
        self.calls.append(("list_authenticator_revelation_requests", {}))
        self._auth(authenticator_keystore_secret)
        return self.requests

    def _find(self, uid):
        request = next(r for r in self.requests if r["revelation_request_uid"] == uid)
        if request["revelation_request_status"] != "PENDING":
            raise ValidationError("not pending")
        return request

    def accept_revelation_request(self, authenticator_keystore_secret, revelation_request_uid, symkey_decryption_results):
        self.calls.append(("accept_revelation_request", dict(results=symkey_decryption_results)))
        self._auth(authenticator_keystore_secret)
        request = self._find(revelation_request_uid)
        if not symkey_decryption_results:
            raise ValidationError("empty results")
        for item in symkey_decryption_results:  # Gateway rules 1 and 5
            if set(item) != {"symkey_decryption_request_data", "symkey_decryption_response_data", "symkey_decryption_status"}:
                raise ValidationError("bad keys")
            if item["symkey_decryption_status"] not in ("DECRYPTED", "PRIVATE_KEY_MISSING", "CORRUPTED", "METADATA_MISMATCH"):
                raise ValidationError("bad status")
            if (item["symkey_decryption_status"] == "DECRYPTED") != bool(item["symkey_decryption_response_data"]):
                raise ValidationError("incoherent status/data")
        expected = {s["symkey_decryption_request_data"] for s in request["symkey_decryption_requests"]}
        if {i["symkey_decryption_request_data"] for i in symkey_decryption_results} != expected:  # Rule 4
            raise ValidationError("request data mismatch")
        request["revelation_request_status"] = "ACCEPTED"

    def reject_revelation_request(self, authenticator_keystore_secret, revelation_request_uid):
        self.calls.append(("reject_revelation_request", {}))
        self._auth(authenticator_keystore_secret)
        self._find(revelation_request_uid)["revelation_request_status"] = "REJECTED"


@pytest.fixture
def fake_gateway():
    from wacryptolib.keystore import load_keystore_metadata
    return FakeGateway(secret=load_keystore_metadata(FIXTURES / "authenticator.keystore")["keystore_secret"])


class StubPage:
    """Just enough of ft.Page for building screens without a Flet session."""

    def __init__(self):
        self.views, self.overlay, self.dialogs = [], [], []
        self.width = 420
        self.web = False

    def update(self, *controls):
        pass

    def show_dialog(self, dialog):
        dialog.open = True
        self.dialogs.append(dialog)

    def pop_dialog(self):
        return None

    def run_task(self, handler, *args):
        asyncio.run(handler(*args))


@pytest.fixture
def stub_app(tmp_path, monkeypatch):
    from waflet_authenticator.app import WaAuthenticatorApp
    from waflet_components.i18n import tr
    from waflet_components.storage import compute_storage_roots

    monkeypatch.setattr("waflet_components.storage.list_usb_authdevices", lambda platform: [])
    monkeypatch.setenv("LANG", "en")
    app = WaAuthenticatorApp(StubPage(), storage_roots=compute_storage_roots("desktop", tmp_path / "home"))
    app.setup()
    yield app
    app._executor.shutdown(wait=True)
    tr.lang = "en"


def flush(app):
    """Wait for the single worker to finish queued tasks (their UI callbacks run inline on the stub page)."""
    app._executor.submit(lambda: None).result()
