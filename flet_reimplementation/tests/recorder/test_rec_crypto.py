"""Cryptoconf, guardians pool, decryption of spec fixtures, claimant requests, 04 §14.1 acceptance test."""
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from wacryptolib.cryptainer import CryptainerStorage, ReadonlyCryptainerStorage, check_cryptoconf_sanity
from wacryptolib.exceptions import ExistenceError, KeystoreDoesNotExist
from wacryptolib.keystore import FilesystemKeystorePool
from wacryptolib.utilities import generate_uuid0

from rec_helpers import *  # noqa: F401,F403
from rec_helpers import (FIXTURES, GUARDIAN_A, GUARDIAN_B, needs_fixtures, passphrases, load_fixture_json, make_settings)
from waflet_recorder import claimant, decryption, guardians
from waflet_recorder.cryptainers import RecorderCryptainerStorage, open_management_storage, list_cryptainers
from waflet_recorder.cryptoconf import build_cryptoconf, NoEncryptionKeyError

pytestmark = needs_fixtures
EXPECTED = None


def expected_payload():
    return (FIXTURES / "expected_payload.bin").read_bytes()


def chooser_for(conf):
    wanted = {s["key_cipher_layers"][0]["keychain_uid"] for s in conf["payload_cipher_layers"][0]["key_cipher_layers"][0]["key_shared_secret_shards"]}
    return lambda keys: next(k for k in keys if k["keychain_uid"] in wanted)


@pytest.mark.parametrize("threshold", [1, 2])
def test_cryptoconf_equals_fixture(pool, threshold):
    fixture = load_fixture_json("cryptoconf_threshold_%d_of_2.json" % threshold)
    conf = build_cryptoconf(threshold, [GUARDIAN_A, GUARDIAN_B], pool, choose=chooser_for(fixture))
    assert conf == fixture
    check_cryptoconf_sanity(conf)


def test_cryptoconf_uses_only_rsa_oaep_and_secrets(pool):
    conf = build_cryptoconf(1, [GUARDIAN_A], pool)
    layer = conf["payload_cipher_layers"][0]["key_cipher_layers"][0]["key_shared_secret_shards"][0]["key_cipher_layers"][0]
    assert layer["key_cipher_algo"] == "RSA_OAEP"


def test_cryptoconf_guardian_without_key(pool, pool_roots):
    for pem in (pool_roots.keystore_pool_dir / "foreign_keystores" / ("keystore_%s" % GUARDIAN_B)).glob("*.pem"):
        pem.unlink()
    with pytest.raises(NoEncryptionKeyError):
        build_cryptoconf(1, [GUARDIAN_B], pool)


def test_cryptoconf_ignores_corrupted_unselected_keystore(pool, pool_roots):
    bad = pool_roots.keystore_pool_dir / "foreign_keystores" / ("keystore_%s" % uuid.uuid4())
    bad.mkdir()  # No metadata: OI-51
    assert build_cryptoconf(1, [GUARDIAN_A], pool)
    listed = guardians.list_guardians(pool)
    assert [g["corrupted"] for g in listed].count(True) == 1 and len(listed) == 3


def test_selected_guardians_filtered_and_ordered(pool, pool_roots):
    settings = make_settings(pool_roots, **{"keyguardian.selected_keyguardians": "%s,%s,%s" % (
        GUARDIAN_B, uuid.uuid4(), GUARDIAN_A)})
    assert guardians.get_selected_guardian_uids(settings, pool) == [GUARDIAN_B, GUARDIAN_A]


# ------------------------------------------------------------------ guardian import / deletion

def test_import_from_authdevices_strips_secret_and_hint(roots):
    pool = guardians.open_keystore_pool(roots)
    dirs = [FIXTURES / "authdevices" / d / "authenticator.keystore" for d in ("usb_A", "usb_B")]
    result = guardians.import_from_authdevices(pool, dirs + [roots.internal_app_root / "nothing"], include_private_keys=True)
    assert len(result["new"]) == 2 and result["skipped"] == 1 and not result["updated"]
    for uid in result["new"]:
        text = (roots.keystore_pool_dir / "foreign_keystores" / ("keystore_%s" % uid) / "keystore_metadata.json").read_text()
        assert "keystore_secret" not in text and "keystore_passphrase_hint" not in text
        assert list((roots.keystore_pool_dir / "foreign_keystores" / ("keystore_%s" % uid)).glob("*_private_key.pem"))
    again = guardians.import_from_authdevices(pool, dirs[:1], include_private_keys=False)
    assert again["updated"] == result["new"][:1] or len(again["updated"]) == 1
    assert not list((roots.keystore_pool_dir / "foreign_keystores").glob("~*"))  # No temp folder left


def test_import_skips_missing_private_key(roots, tmp_path):
    source = tmp_path / "usb" / "authenticator.keystore"
    shutil.copytree(FIXTURES / "authdevices" / "usb_A" / "authenticator.keystore", source)
    next(source.glob("*_private_key.pem")).unlink()
    pool = guardians.open_keystore_pool(roots)
    info = guardians.import_from_authdevice(pool, source, include_private_keys=True)  # OI-52: no abort
    assert info["private_keys_skipped"] == 1 and not info["updated"]


class FakeGatewayProxy:
    def __init__(self):
        self.calls = []
        self.published = {}
        self.fail_for = {}

    def get_public_authenticator(self, keystore_uid):
        if keystore_uid not in self.published:
            raise KeystoreDoesNotExist("nope")
        return self.published[keystore_uid]

    def submit_revelation_request(self, **params):
        self.calls.append(params)
        if params["authenticator_keystore_uid"] in self.fail_for:
            raise self.fail_for[params["authenticator_keystore_uid"]]

    def list_requestor_revelation_requests(self, revelation_requestor_uid):
        self.calls.append(("list", revelation_requestor_uid))
        return load_fixture_json("gateway", "list_requestor_revelation_requests.response.json")["result"]


def test_import_from_gateway(roots):
    pool = guardians.open_keystore_pool(roots)
    gateway = FakeGatewayProxy()
    response = load_fixture_json("gateway", "get_public_authenticator.response.json")["result"]
    gateway.published[response["keystore_uid"]] = response
    info = guardians.import_from_gateway(pool, gateway, " %s \n" % str(response["keystore_uid"]).upper())
    assert info["owner"] == response["keystore_owner"] and not info["updated"]
    keystore = pool.get_foreign_keystore(response["keystore_uid"])
    assert len(keystore.list_keypair_identifiers()) == len(response["public_keys"])
    assert not any(k["private_key_present"] for k in keystore.list_keypair_identifiers())
    with pytest.raises(guardians.BadGuardianUidError):
        guardians.import_from_gateway(pool, gateway, "xyz")
    with pytest.raises(guardians.GatewayAuthenticatorNotFoundError):
        guardians.import_from_gateway(pool, gateway, str(uuid.uuid4()))


def test_delete_guardians_oi49_oi53(pool, pool_roots):
    with pytest.raises(guardians.GuardianInUseError):
        guardians.delete_guardians(pool, [GUARDIAN_A, GUARDIAN_B], protected_uids=[GUARDIAN_B])
    assert len(pool.list_foreign_keystore_uids()) == 2  # Nothing deleted
    selection = [GUARDIAN_A, GUARDIAN_B]
    result = guardians.delete_guardians(pool, selection)
    assert len(result["deleted"]) == 2 and selection == [GUARDIAN_A, GUARDIAN_B]  # Whole selection, list untouched
    assert pool.list_foreign_keystore_uids() == []


# ------------------------------------------------------------------ decrypting spec fixtures

@pytest.fixture
def cryptainer_dir(tmp_path):
    target = tmp_path / "cryptainers"
    shutil.copytree(FIXTURES / "cryptainers", target)
    return target


def test_decrypt_1_of_2_with_passphrase_alone(cryptainer_dir, pool, tmp_path):
    storage = open_management_storage(cryptainer_dir, pool)
    names = [e["name"] for e in list_cryptainers(storage)]
    assert names[0].startswith("20261026_130000_to") and len(names) == 3  # Newest first, unfinished not listed
    name = "20261026_120000_rtsp_camera_cryptainer.mp4.crypt"
    mapper = decryption.PassphraseMapper()
    statuses = decryption.get_trustee_status(storage, pool, [name], mapper)
    assert [s["owner"] for s in statuses] == ["Alice Guardian", "Bob Gardien é"]
    assert statuses[0]["found"] and not statuses[0]["missing_private_keys"] and statuses[1]["missing_private_keys"]
    exports = tmp_path / "exports"
    failed = decryption.decrypt_cryptainers(storage, pool, [name], mapper, exports, None, None)[0]
    assert not failed["success"] and not list(exports.glob("*.mp4"))
    assert decryption.check_passphrase(pool, statuses, mapper, "wrong")["result"] == "no_match"
    assert decryption.check_passphrase(pool, statuses, mapper, passphrases()["usb_A"])["result"] == "recognized"
    assert decryption.check_passphrase(pool, statuses, mapper, passphrases()["usb_A"])["result"] == "already_entered"  # OI-66
    result = decryption.decrypt_cryptainers(storage, pool, [name], mapper, exports, None, None, now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))[0]
    assert result["success"] and result["export_path"].read_bytes() == expected_payload()
    assert result["export_path"].name == "20261026_120000_rtsp_camera_cryptainer.mp4"
    assert result["report_path"].name == name + "_revelation_report_20260102_030405.txt"
    again = decryption.decrypt_cryptainers(storage, pool, [name], mapper, exports, None, None)[0]
    assert again["export_path"].name == "20261026_120000_rtsp_camera_cryptainer_2.mp4"  # OI-70: no overwrite
    mapper.clear()
    assert not mapper.as_dict()


def test_decrypt_2_of_2_through_gateway_fixture(cryptainer_dir, pool, tmp_path, monkeypatch):
    storage = open_management_storage(cryptainer_dir, pool)
    gateway = FakeGatewayProxy()
    monkeypatch.setattr(decryption, "get_gateway_proxy", lambda url, timeout=None: gateway)
    names = ["20261026_121500_rpi_microphone_cryptainer.wav.crypt"] * 2
    results = decryption.decrypt_cryptainers(storage, pool, names, decryption.PassphraseMapper(), tmp_path / "ex",
                                             "https://gw/", load_fixture_json("wa_device_uid.json")["wa_device_uid"])
    assert [r["success"] for r in results] == [True, True]
    assert results[0]["export_path"].read_bytes() == expected_payload()
    assert len([c for c in gateway.calls if c[0] == "list"]) == 1  # OI-72: one gateway call per batch
    assert "2 found" in decryption.format_operation_report(results[0]["report"])


def test_decrypt_gateway_down_is_reported(cryptainer_dir, pool, tmp_path, monkeypatch):
    class Down:
        def list_requestor_revelation_requests(self, **kw):
            raise OSError("down")
    monkeypatch.setattr(decryption, "get_gateway_proxy", lambda url, timeout=None: Down())
    storage = open_management_storage(cryptainer_dir, pool)
    result = decryption.decrypt_cryptainers(storage, pool, ["20261026_121500_rpi_microphone_cryptainer.wav.crypt"],
                                            decryption.PassphraseMapper(), tmp_path, "https://gw/", generate_uuid0())[0]
    text = decryption.format_operation_report(result["report"])
    assert not result["success"] and "WARNING: Asymmetric Decryption Error (OSError)\nMessage: Unable to reach remote server https://gw/" in text


def test_decrypt_unreadable_cryptainer_is_a_failure_result(cryptainer_dir, pool, tmp_path):
    (cryptainer_dir / "20261026_120000_rtsp_camera_cryptainer.mp4.crypt.payload").unlink()  # OI-69
    storage = open_management_storage(cryptainer_dir, pool)
    result = decryption.decrypt_cryptainers(storage, pool, ["20261026_120000_rtsp_camera_cryptainer.mp4.crypt"],
                                            decryption.PassphraseMapper(), tmp_path, None, None)[0]
    assert not result["success"] and result["report"].has_errors()


def test_old_to_new_acceptance_tar_and_all_features(tmp_path):
    """04 §14.1 item 1: the tar cryptainer and the all_features one are read by the pinned library."""
    pool = FilesystemKeystorePool(Path(shutil.copytree(FIXTURES / "keystore_pool", tmp_path / "pool")))
    storage = ReadonlyCryptainerStorage(FIXTURES / "cryptainers", keystore_pool=pool)
    mapper = {None: [passphrases()["usb_A"], passphrases()["usb_B"]]}
    plaintext, report = storage.decrypt_cryptainer_from_storage("20261026_130000_to_20261026_130010_cryptainer.tar.crypt",
                                                                passphrase_mapper=mapper)
    assert plaintext is not None
    from wacryptolib.cryptainer import load_cryptainer_from_filesystem, decrypt_payload_from_cryptainer
    pool2 = FilesystemKeystorePool(Path(shutil.copytree(FIXTURES / "all_features" / "keystore_pool", tmp_path / "pool2")))
    cryptainer = load_cryptainer_from_filesystem(FIXTURES / "all_features" / "all_features_inline.crypt")
    data, report = decrypt_payload_from_cryptainer(cryptainer, keystore_pool=pool2, passphrase_mapper=mapper)
    assert data is not None and not report.has_errors()


# ------------------------------------------------------------------ claimant

def test_create_revelation_requests_match_fixture_items(cryptainer_dir, pool, roots):
    storage = open_management_storage(cryptainer_dir, pool)
    gateway = FakeGatewayProxy()
    requestor = claimant.get_wa_device_uid(roots)
    assert claimant.get_wa_device_uid(roots) == requestor and roots.device_uid_file.exists()
    name = "20261026_121500_rpi_microphone_cryptainer.wav.crypt"
    result = claimant.create_revelation_requests(storage, pool, requestor, gateway, [name], [GUARDIAN_A, GUARDIAN_B],
                                                 "  Police request 2026/123, incident of 26 October ")
    assert result["total"] == 2 and len(result["ok"]) == 2 and not result["errors"]
    fixture = load_fixture_json("gateway", "submit_revelation_request_1.request.json")["params"]
    sent = {c["authenticator_keystore_uid"]: c for c in gateway.calls}
    call = sent[fixture["authenticator_keystore_uid"]]
    assert call["symkey_decryption_requests"] == fixture["symkey_decryption_requests"]  # Byte for byte
    assert call["revelation_request_description"] == fixture["revelation_request_description"]
    assert set(call) == set(fixture) and call["revelation_response_key_algo"] == "RSA_OAEP"
    assert call["revelation_response_public_key"].startswith(b"-----BEGIN PUBLIC KEY-----")
    assert len({c["revelation_response_keychain_uid"] for c in gateway.calls}) == 1  # One response key
    assert (pool.get_local_keyfactory().get_private_key(keychain_uid=result["response_keychain_uid"], key_algo="RSA_OAEP"))


def test_create_revelation_requests_errors(cryptainer_dir, pool, roots):
    storage = open_management_storage(cryptainer_dir, pool)
    gateway = FakeGatewayProxy()
    name = "20261026_121500_rpi_microphone_cryptainer.wav.crypt"
    with pytest.raises(claimant.NoAuthenticatorSelectedError):
        claimant.create_revelation_requests(storage, pool, generate_uuid0(), gateway, [name], [], "x" * 20)
    with pytest.raises(claimant.DescriptionTooShortError):
        claimant.create_revelation_requests(storage, pool, generate_uuid0(), gateway, [name], [GUARDIAN_A], "short")
    gateway.fail_for = {GUARDIAN_A: ConnectionError("net"), GUARDIAN_B: KeystoreDoesNotExist("x")}
    before = set(pool.get_local_keyfactory()._keys_dir.glob("*.pem"))
    result = claimant.create_revelation_requests(storage, pool, generate_uuid0(), gateway, [name], [GUARDIAN_A, GUARDIAN_B], "x" * 20)
    assert not result["ok"] and {e["kind"] for e in result["errors"]} == {"other", "authenticator_missing"}  # OI-74
    assert set(pool.get_local_keyfactory()._keys_dir.glob("*.pem")) == before  # OI-77: unused response key removed


def test_list_requests_grouped_by_cryptainer(pool):
    groups = claimant.list_requests_by_cryptainer(FakeGatewayProxy(), generate_uuid0())
    assert len(groups) == 1 and groups[0]["cryptainer_name"].startswith("20261026_121500_rpi_microphone")
    assert len(groups[0]["entries"]) == 2 and groups[0]["entries"][0]["symkey_decryption_request"]

    class Down:
        def list_requestor_revelation_requests(self, **kw):
            raise OSError
    with pytest.raises(claimant.GatewayUnreachableError):
        claimant.list_requests_by_cryptainer(Down(), generate_uuid0())
