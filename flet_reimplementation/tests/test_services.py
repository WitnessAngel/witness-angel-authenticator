import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from wacryptolib.cipher import decrypt_bytestring
from wacryptolib.exceptions import KeyLoadingError, KeystoreDoesNotExist
from wacryptolib.keygen import load_asymmetric_key_from_pem_bytestring
from wacryptolib.keystore import load_keystore_metadata, ReadonlyFilesystemKeystore
from wacryptolib.utilities import load_from_json_bytes, dump_to_json_bytes

from conftest import FIXTURES, PASSPHRASES, FakeGateway, load_fixture
from waflet_components import authenticator_services as services
from waflet_components.config import AppConfig
from waflet_components.formatting import (
    shorten_uid, convert_bytes_to_human_representation, format_utc_datetime_label, format_revelation_request_label,
    format_keypair_label, format_path_for_display,
)
from waflet_components.i18n import tr, detect_language, Translator
from waflet_components.screens.authenticator_management import (
    format_authenticator_info, format_check_result, format_location_texts,
)
from waflet_components.screens.authenticator_publication_form import format_publication_report
from waflet_components.screens.authenticator_revelation_requests import map_listing_error
from waflet_components.storage import (
    compute_storage_roots, bootstrap_storage, list_authenticator_locations, migrate_custom_dir, is_folder_writable,
    is_folder_accessible, LocationType,
)


@pytest.fixture(autouse=True)
def english():
    tr.lang = "en"
    yield
    tr.lang = "en"


def claimant_decrypt(response_data):
    key = load_asymmetric_key_from_pem_bytestring((FIXTURES / "gateway" / "claimant_response_private_key.pem").read_bytes(),
                                                  key_algo="RSA_OAEP")
    return decrypt_bytestring(load_from_json_bytes(response_data), cipher_algo="RSA_OAEP", key_dict=dict(key=key))


def pending_request(gateway):
    return gateway.requests[0]


# ------------------------------------------------------------------ passphrase / check

@pytest.mark.parametrize("passphrase", [PASSPHRASES["raw"], PASSPHRASES["equivalent_after_normalization"]])
def test_check_passphrase_success_with_normalisation(authenticator_dir, passphrase):
    result = services.check_authenticator_passphrase(authenticator_dir, passphrase)
    assert result["success"] and result["keypair_count"] == 3
    title, text = format_check_result(result)
    assert title == "Checkup result: Success" and text == "Keypairs successfully tested: 3"


def test_check_passphrase_wrong(authenticator_dir):
    result = services.check_authenticator_passphrase(authenticator_dir, PASSPHRASES["wrong"])
    assert not result["success"] and len(result["undecodable_private_keys"]) == 3
    title, text = format_check_result(result)
    assert title == "Checkup result: Failure"
    assert text.startswith("Keypairs tested: 3\nMissing private keys: -\nWrong passphrase for keys:  RSA-OAEP …")


def test_edge_cases_listing_and_check(edge_cases_dir):
    keys = ReadonlyFilesystemKeystore(edge_cases_dir).list_keypair_identifiers()
    assert sorted(k["private_key_present"] for k in keys) == [False, True]
    result = services.check_authenticator_passphrase(edge_cases_dir, PASSPHRASES["raw"])
    assert not result["success"] and len(result["missing_private_keys"]) == 1 and not result["undecodable_private_keys"]
    with pytest.raises(services.MissingPrivateKeysError):  # OI-28
        services.check_publishable(edge_cases_dir)


# ------------------------------------------------------------------ status of a location

def test_status_initialized(authenticator_dir):
    result = services.compute_authenticator_status(authenticator_dir)
    assert result["status"] is True and result["has_secret"] and len(result["keypairs"]) == 3
    text = format_authenticator_info(result, display_path=str)
    assert "User: Jane Doe éè" in text and "Password hint: usual sentence, normalised" in text
    assert "Creation date: 2026-10-24 at 21:25:20 UTC" in text
    assert "ID: 104e5e09-ee47-4f4c-0cf4-df6c409f2462" in text
    assert "Keypairs:\n    RSA-OAEP …85c8b5592a4a\n    RSA-OAEP …10712294b9f4\n    RSA-OAEP …eb6b76b30e06" in text
    tr.lang = "fr"
    text = format_authenticator_info(result, display_path=str)
    assert "Utilisateur : Jane Doe éè" in text and "Date de création : 2026-10-24 à 21:25:20 UTC" in text


def test_status_variants(tmp_path, authenticator_dir):
    assert services.compute_authenticator_status(None)["status"] is None
    assert services.compute_authenticator_status(tmp_path / "new")["status"] is False
    assert services.compute_authenticator_status(tmp_path / "missing" / "x")["reason"] == "parent_missing"
    (tmp_path / "file").write_text("x")
    assert services.compute_authenticator_status(tmp_path / "file")["reason"] == "not_a_folder"
    metadata_file = authenticator_dir / "keystore_metadata.json"
    original = metadata_file.read_bytes()
    metadata_file.write_text("{not json")  # OI-18
    result = services.compute_authenticator_status(authenticator_dir)
    assert result["status"] is None and result["reason"] == "invalid_data"
    assert format_authenticator_info(result) == "Invalid authenticator data in %s" % authenticator_dir
    metadata = load_from_json_bytes(original)
    del metadata["keystore_passphrase_hint"], metadata["keystore_secret"]  # OI-17
    metadata_file.write_bytes(dump_to_json_bytes(metadata))
    result = services.compute_authenticator_status(authenticator_dir)
    assert result["status"] is True and not result["has_secret"]
    assert "Password hint: \n" in format_authenticator_info(result, display_path=str)
    with pytest.raises(services.NoGatewaySecretError):
        services.list_revelation_requests(authenticator_dir, None)


# ------------------------------------------------------------------ creation

def test_validate_creation_form():
    ok = "x" * 20
    assert services.validate_creation_form(" a ", " %s " % ok, " h ")[0] == dict(
        keystore_owner="a", passphrase=ok, keystore_passphrase_hint="h")
    assert services.validate_creation_form("a", "", "h")[1] == "Please enter a username, passphrase and passphrase hint."
    assert services.validate_creation_form("a" * 101, ok, "h")[1].startswith("Username, passphrase")
    assert services.validate_creation_form("a", "short", "h")[1] == "Passphrase must be at least 20 characters long."
    assert services.validate_creation_form("a", "¤short", "h")[1] is not None  # OI-10: back door removed


def test_create_authenticator(tmp_path):
    target = tmp_path / "authenticator.keystore"
    progress = []
    services.create_authenticator(target, "Owner", PASSPHRASES["raw"], "hint", progress_callback=progress.append)
    assert progress == [10, 40, 70, 100]
    metadata = load_keystore_metadata(target)
    assert set(metadata) == {"keystore_type", "keystore_format", "keystore_uid", "keystore_owner",
                             "keystore_passphrase_hint", "keystore_secret", "keystore_creation_datetime"}
    assert metadata["keystore_type"] == "authenticator" and metadata["keystore_format"] == "keystore_1.0"
    assert re.fullmatch(r"[A-Za-z0-9_-]{86}", metadata["keystore_secret"])
    names = sorted(p.name for p in target.iterdir())
    assert len(names) == 7 and "keystore_metadata.json" in names
    for name in names[:-1]:
        assert re.fullmatch(r"[-0-9a-f]{36}_RSA_OAEP_(public|private)_key\.pem", name)
        assert (target / name).read_bytes().startswith(
            b"-----BEGIN ENCRYPTED PRIVATE KEY-----" if "private" in name else b"-----BEGIN PUBLIC KEY-----")
    assert services.check_authenticator_passphrase(target, PASSPHRASES["equivalent_after_normalization"])["success"]


def test_create_authenticator_rolls_back(tmp_path):
    target = tmp_path / "authenticator.keystore"

    def boom(percent):
        if percent > 10:
            raise RuntimeError("disk full")
    with pytest.raises(RuntimeError):
        services.create_authenticator(target, "Owner", "x" * 20, "hint", progress_callback=boom)
    assert not target.exists()  # OI-11
    target.mkdir()  # Pre-existing empty folder: only created files are removed
    with pytest.raises(RuntimeError):
        services.create_authenticator(target, "Owner", "x" * 20, "hint", progress_callback=boom)
    assert target.is_dir() and not list(target.iterdir())


# ------------------------------------------------------------------ export / import / destroy

def test_export_import_destroy(tmp_path, authenticator_dir):
    exports = tmp_path / "exports"
    exports.mkdir()
    archive = services.export_authenticator(authenticator_dir, exports, now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    assert archive.name == "authenticator_iddf6c409f2462_date20260102030405.zip"
    with zipfile.ZipFile(archive) as zf:
        assert sorted(zf.namelist()) == sorted(p.name for p in authenticator_dir.iterdir())  # Entries at the root

    target = tmp_path / "restored" / "authenticator.keystore"
    target.parent.mkdir()
    services.import_authenticator(archive, target)
    assert services.compute_authenticator_status(target)["status"] is True
    assert not [p for p in target.parent.iterdir() if p.name.startswith("~import")]
    with pytest.raises(services.TargetNotEmptyError):
        services.import_authenticator(archive, target)

    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("notes.txt", "hello")
    with pytest.raises(services.InvalidArchiveError):
        services.import_authenticator(bad, tmp_path / "other")

    services.destroy_authenticator(target)
    assert not target.exists()
    with pytest.raises(services.NotInitializedError):  # OI-19 guard
        services.destroy_authenticator(target)
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(services.NotInitializedError):
        services.destroy_authenticator(plain)
    assert plain.exists()


# ------------------------------------------------------------------ publication

def test_publication_flow(authenticator_dir, fake_gateway):
    status = services.get_publication_status(authenticator_dir, fake_gateway)
    assert status["remote_status"] == "NOT_PUBLISHED"
    assert fake_gateway.calls[0][1]["keystore_secret"] == fake_gateway.secret  # OI-29
    services.publish_authenticator(authenticator_dir, fake_gateway)
    sent = fake_gateway.calls[-1][1]
    assert "keystore_passphrase_hint" not in sent and all(set(k) == {"keychain_uid", "key_algo", "key_value"}
                                                          for k in sent["public_keys"])
    assert all(k["key_value"].startswith(b"-----BEGIN PUBLIC KEY-----") for k in sent["public_keys"])
    status = services.get_publication_status(authenticator_dir, fake_gateway)
    assert status["remote_status"] == "PUBLISHED" and not status["exceeding_keys"] and not status["missing_keys"]
    status["authenticator_dir"] = authenticator_dir
    report = format_publication_report(status, str, "https://gw/")
    assert "Remote status: PUBLISHED" in report and "The remote authenticator is up to date." in report


def test_publication_inconsistency_with_fixture(authenticator_dir):
    published = load_fixture("get_public_authenticator.response.json")["result"]
    published["public_keys"] = published["public_keys"][:2]
    gateway = FakeGateway(secret=load_keystore_metadata(authenticator_dir)["keystore_secret"], published=published)
    status = services.get_publication_status(authenticator_dir, gateway)
    assert len(status["missing_keys"]) == 1 and not status["exceeding_keys"]
    status["authenticator_dir"] = authenticator_dir
    report = format_publication_report(status, str, "https://gw/")
    assert "Missing key(s) in remote: …eb6b76b30e06" in report and "Exceeding key(s) in remote: -" in report
    assert "('" not in report  # OI-33


# ------------------------------------------------------------------ revelation requests

def test_list_revelation_requests(authenticator_dir, fake_gateway):
    fake_gateway.requests.append(dict(fake_gateway.requests[1], revelation_request_status="WEIRD"))  # OI-05
    grouped = services.list_revelation_requests(authenticator_dir, fake_gateway)
    assert [len(grouped[s]) for s in ("PENDING", "ACCEPTED", "REJECTED")] == [2, 0, 1]
    assert grouped["PENDING"][0]["created_at"] > grouped["PENDING"][1]["created_at"]  # Newest first
    assert format_revelation_request_label(grouped["PENDING"][0]["created_at"],
                                           grouped["PENDING"][0]["revelation_request_description"]) == \
        'Request "Judicial request n° 42, please accept" (2026-10-24)'


def test_listing_error_mapping():
    assert map_listing_error(KeystoreDoesNotExist()) == "Authenticator does not exist in remote registry"
    assert map_listing_error(OSError()) .startswith("Error querying gateway server")
    assert map_listing_error(KeyError()) is None


def test_accept_revelation_request(authenticator_dir, fake_gateway):
    request = pending_request(fake_gateway)
    results = services.accept_revelation_request(authenticator_dir, request, PASSPHRASES["raw"], fake_gateway)
    expected = load_fixture("expected_plaintexts.json")
    assert [r["symkey_decryption_request_data"] for r in results] == [e["symkey_decryption_request_data"] for e in expected]
    for result, exp in zip(results, expected):
        assert result["symkey_decryption_status"] == "DECRYPTED"
        assert claimant_decrypt(result["symkey_decryption_response_data"]) == exp["key_struct_bytes"]
    assert request["revelation_request_status"] == "ACCEPTED"  # The fake gateway accepted the payload


def test_accept_with_missing_private_key_and_corrupted_data(authenticator_dir, fake_gateway):
    request = pending_request(fake_gateway)
    first_key = request["symkey_decryption_requests"][0]["target_public_authenticator_key"]["keychain_uid"]
    (authenticator_dir / ("%s_RSA_OAEP_private_key.pem" % first_key)).unlink()
    corrupted = dict(request["symkey_decryption_requests"][1], symkey_decryption_request_data=dump_to_json_bytes(
        {"ciphertext_chunks": [b"\x00" * 256]}))
    request["symkey_decryption_requests"].append(corrupted)
    request["symkey_decryption_requests"].append(dict(corrupted))  # Duplicate: answered once (OI-03 d)
    results = services.accept_revelation_request(authenticator_dir, request, PASSPHRASES["raw"], fake_gateway)
    assert [(r["symkey_decryption_status"], r["symkey_decryption_response_data"] == b"") for r in results] == [
        ("PRIVATE_KEY_MISSING", True), ("DECRYPTED", False), ("CORRUPTED", True)]  # OI-01, OI-04
    assert request["revelation_request_status"] == "ACCEPTED"


def test_accept_refusals(authenticator_dir, fake_gateway):
    request = pending_request(fake_gateway)
    with pytest.raises(KeyLoadingError):
        services.accept_revelation_request(authenticator_dir, request, PASSPHRASES["wrong"], fake_gateway)
    assert not [c for c in fake_gateway.calls if c[0] == "accept_revelation_request"]  # Nothing sent
    with pytest.raises(services.EmptyRevelationRequestError):
        services.accept_revelation_request(authenticator_dir, fake_gateway.requests[2], PASSPHRASES["raw"], fake_gateway)
    with pytest.raises(services.UnsupportedAlgorithmError):
        services.check_revelation_request_acceptable(dict(request, revelation_response_key_algo="AES_CBC"))
    with pytest.raises(services.NotPendingError):
        services.check_revelation_request_acceptable(fake_gateway.requests[1])


def test_reject_revelation_request(authenticator_dir, fake_gateway):
    request = fake_gateway.requests[2]
    services.reject_revelation_request(authenticator_dir, request, fake_gateway)
    assert request["revelation_request_status"] == "REJECTED"


# ------------------------------------------------------------------ gateway wire format (real JsonRpcProxy)

class FakeResponse:
    status_code = 200

    def __init__(self, text):
        self.text = text


def test_jsonrpc_wire(authenticator_dir):
    proxy = services.get_gateway_proxy("https://example.invalid/gateway/jsonrpc/")
    sent = []
    error_body = (FIXTURES / "gateway" / "error_KeystoreDoesNotExist.response.json").read_text()
    proxy.request = lambda data: sent.append(data) or FakeResponse(error_body)
    assert services.get_publication_status(authenticator_dir, proxy)["remote_status"] == "NOT_PUBLISHED"
    body = load_from_json_bytes(sent[0].encode("ascii"))
    assert body["method"] == "get_public_authenticator" and isinstance(body["params"], dict)  # Named params only
    assert body["params"]["keystore_uid"] == UUID("104e5e09-ee47-4f4c-0cf4-df6c409f2462")

    list_body = (FIXTURES / "gateway" / "list_authenticator_revelation_requests.response.json").read_text()
    proxy.request = lambda data: sent.append(data) or FakeResponse(list_body)
    grouped = services.list_revelation_requests(authenticator_dir, proxy)
    assert len(grouped["PENDING"]) == 2

    proxy.request = lambda data: sent.append(data) or FakeResponse('{"jsonrpc": "2.0", "id": 1, "result": null}')
    services.accept_revelation_request(authenticator_dir, grouped["PENDING"][0], PASSPHRASES["raw"], proxy)
    params = load_from_json_bytes(sent[-1].encode("ascii"))["params"]
    reference = load_fixture("accept_revelation_request.request.json")["params"]
    assert set(params) == set(reference)
    assert [r["symkey_decryption_request_data"] for r in params["symkey_decryption_results"]] == \
        [r["symkey_decryption_request_data"] for r in reference["symkey_decryption_results"]]


def test_observed_2023_payload_parses():
    request = load_fixture("observed_2023_list_requestor_revelation_requests.result.json")
    request = request[0] if isinstance(request, list) else request
    assert isinstance(request["revelation_request_uid"], UUID)
    for symkey in request["symkey_decryption_requests"]:
        assert isinstance(symkey["symkey_decryption_request_data"], bytes)


# ------------------------------------------------------------------ storage & locations

def test_storage_roots_per_platform(tmp_path):
    desktop = compute_storage_roots("desktop", "/home/u")
    assert desktop.internal_authenticator_dir == Path("/home/u/.witnessangel/authenticator.keystore")
    assert desktop.exports_dir == Path("/home/u/.witnessangel/external/exports")
    android = compute_storage_roots("android", "/", app_support_dir="/data/user/0/org.witnessangel.authenticator/files",
                                    external_files_dir="/storage/emulated/0/Android/data/org.witnessangel.authenticator/files",
                                    sdcard_root="/storage/emulated/0")
    assert android.internal_authenticator_dir == Path("/data/user/0/org.witnessangel.authenticator/files/authenticator.keystore")
    assert format_path_for_display(android.exports_dir, "/nonexistent", android.external_app_root_prefix) == \
        "<sdcard>/Android/data/org.witnessangel.authenticator/files/exports"
    ios = compute_storage_roots("ios", "/var/app/NEW", app_support_dir="/var/app/NEW/Library/Application Support",
                                documents_dir="/var/app/NEW/Documents")
    assert migrate_custom_dir("/var/app/OLD/Documents/keys", ios) == "/var/app/NEW/Documents/keys"  # OI-16
    assert migrate_custom_dir("/elsewhere", ios) == ""
    assert migrate_custom_dir("/storage/emulated/0/Download", android) == ""
    assert migrate_custom_dir(str(android.external_app_root / "x"), android) == str(android.external_app_root / "x")
    assert migrate_custom_dir("", desktop) == ""
    assert format_path_for_display("/home/u/a/b", "/home/u") == "~/a/b" and format_path_for_display("") == ""


def test_bootstrap_and_locations(tmp_path):
    roots = compute_storage_roots("desktop", tmp_path)
    (tmp_path / ".witnessangel" / "authenticator").mkdir(parents=True)
    bootstrap_storage(roots)
    assert roots.internal_authenticator_dir.is_dir() and roots.exports_dir.is_dir()  # Legacy folder renamed
    assert is_folder_writable(roots.exports_dir) and is_folder_accessible(roots.exports_dir, require_writable=True)
    assert not is_folder_accessible(tmp_path / "nope") and not is_folder_accessible("")
    usb = tmp_path / "usb"
    (usb / ".authenticator").mkdir(parents=True)
    from wacryptolib.authdevice import _get_authenticator_dir_for_authdevice
    device = dict(device_type="USBSTOR", partition_label="", partition_mountpoint=str(usb),
                  filesystem_size=15 * 1024 ** 3, filesystem_format="vfat")
    device["authenticator_dir"] = _get_authenticator_dir_for_authdevice(device)
    locations = list_authenticator_locations(roots, "", authdevices=[device])
    assert [loc["location_type"] for loc in locations] == [LocationType.USER_PROFILE, LocationType.CUSTOM_FOLDER,
                                                           LocationType.USB_DEVICE]
    assert locations[1]["authenticator_dir"] is None and locations[2]["authenticator_dir"] == usb / ".authenticator"
    assert format_location_texts(locations[2]) == ("Drive %s (no name)" % usb, "Size: 15GB, Filesystem: VFAT")
    assert format_location_texts(locations[1]) == ("Custom location", "Please select a folder")
    custom = list_authenticator_locations(roots, str(tmp_path / "c"), authdevices=[])[1]
    assert custom["authenticator_dir"] == tmp_path / "c" / "authenticator.keystore"


# ------------------------------------------------------------------ i18n, formatting, config

def test_i18n():
    assert detect_language({"LANG": " FR "}) == "fr"
    assert detect_language({"LANG": "en_US.UTF-8"}, os_language="fr_FR") == "fr"  # Not honoured, OS wins
    assert detect_language({}, os_language="de_DE") == "en"
    translator = Translator()
    translator.add_catalog({"fr": {"Hello": "Bonjour app"}})
    translator.add_catalog({"fr": {"Hello": "Bonjour comp", "Bye {name}": "Au revoir {name}"}})
    assert translator._("Hello") == "Hello"
    translator.switch_lang("fr")
    assert translator._("Hello") == "Bonjour app" and translator.f("Bye {name}", name="X") == "Au revoir X"
    assert translator._("Missing") == "Missing"


def test_app_catalog_loaded(stub_app):
    tr.lang = "fr"
    assert tr._("Authenticator settings") == "Paramètres de l'Authentifieur"  # OI-50
    assert tr._("Authorization requests") == "Demandes d'autorisation"
    assert tr._("The keystore secret of authenticator is not valid").startswith("Le secret de keystore")  # OI-51


def test_formatting():
    uid = UUID("104e5cdc-d725-0498-3b73-3c46b519c841")
    assert shorten_uid(uid) == "…3c46b519c841"
    assert format_keypair_label("RSA_OAEP", uid, False) == "RSA-OAEP …3c46b519c841 (missing private key)"
    assert convert_bytes_to_human_representation(14 * 1024 ** 3 + 5) == "14GB"
    assert convert_bytes_to_human_representation(12) == "12bytes"
    dt = datetime(2024, 5, 1, 12, 0, 7, 123000, tzinfo=timezone.utc)
    assert format_utc_datetime_label(dt, show_time=True) == "2024-05-01 at 12:00:07 UTC"
    assert format_revelation_request_label(dt, "x" * 41) == 'Request "%s…" (2024-05-01)' % ("x" * 40)


def test_config_persistence(tmp_path, stub_app):
    defaults = Path(__file__).resolve().parents[1] / "waflet_authenticator" / "config_defaults.ini"
    config = AppConfig(tmp_path / "wakeygen_config.ini", defaults)
    assert config.get("network", "wagateway_url") == "https://api.witnessangel.com/gateway/jsonrpc/"
    assert config.get("authenticator", "custom_authenticator_dir") == ""
    config.set("authenticator", "custom_authenticator_dir", "/some/where")
    assert AppConfig(tmp_path / "wakeygen_config.ini", defaults).get("authenticator", "custom_authenticator_dir") == "/some/where"

    stub_app.custom_folder = str(tmp_path / "chosen")
    reloaded = AppConfig(stub_app.config.path, defaults)
    assert reloaded.get("authenticator", "custom_authenticator_dir") == str(tmp_path / "chosen")
    assert stub_app.config.path.name == "wakeygen_config.ini"
    assert stub_app.validate_setting("network", "wagateway_url", "http://x/") is not None  # OI-47
    assert stub_app.validate_setting("network", "wagateway_url", "https://x/jsonrpc/") is None
