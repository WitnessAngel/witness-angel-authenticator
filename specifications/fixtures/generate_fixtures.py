"""Regenerate the interop fixtures of the Authenticator specification (see 04 §10).

Run with an interpreter where the shipped wacryptolib (branch poc/pure-python-crypto-utils) is importable:

    FORCE_WACRYPTOLIB_FALLBACK_BACKEND=1 python generate_fixtures.py

The output overwrites the sibling fixture files. Values are random (uids, keys, secret), so a regeneration
changes every file; the self-check at the end must pass.
"""

import base64
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("FORCE_WACRYPTOLIB_FALLBACK_BACKEND", "1")  # Same as the shipped app (main.py)

from wacryptolib.authenticator import initialize_authenticator
from wacryptolib.cipher import encrypt_bytestring, decrypt_bytestring
from wacryptolib.keygen import generate_keypair, generate_symkey, load_asymmetric_key_from_pem_bytestring, _encode_passphrase
from wacryptolib.keystore import FilesystemKeystore, load_keystore_metadata
from wacryptolib.trustee import TrusteeApi
from wacryptolib.utilities import dump_to_json_bytes, dump_to_json_str, load_from_json_bytes, generate_uuid0

HERE = Path(__file__).parent

# Leading/trailing spaces (stripped), U+FB01 "fi" ligature, U+212B ANGSTROM SIGN and a decomposed "e"+U+0301:
# all four are changed by strip()+NFKC, so an implementation skipping normalisation fails to load the keys.
PASSPHRASE_RAW = " Ma phrase ﬁnale Ångström café 2026 "
PASSPHRASE_NORMALIZED_EQUIVALENT = "Ma phrase finale Ångström café 2026"
PASSPHRASE_WRONG = "Ma phrase finale Angstrom cafe 2026"  # Looks similar, but different bytes after NFKC


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def write_json(path: Path, data):
    path.write_bytes(dump_to_json_bytes(data))  # Canonical Extended JSON, as the app and the gateway emit it


def make_authenticator(target: Path, owner: str, hint: str, keypair_count: int):
    if target.exists():
        shutil.rmtree(target)
    target.mkdir()
    initialize_authenticator(target, keystore_owner=owner, keystore_passphrase_hint=hint)
    keystore = FilesystemKeystore(target)
    for _ in range(keypair_count):
        keypair = generate_keypair(key_algo="RSA_OAEP", passphrase=PASSPHRASE_RAW)
        keystore.set_keypair(keychain_uid=generate_uuid0(), key_algo="RSA_OAEP",
                             public_key=keypair["public_key"], private_key=keypair["private_key"])
    return keystore


def main():
    # 1. A well-formed authenticator, as created by the 1.5 GUI (3 RSA_OAEP keypairs)
    auth_dir = HERE / "authenticator.keystore"
    keystore = make_authenticator(auth_dir, owner="Jane Doe éè", hint="usual sentence, normalised", keypair_count=3)
    metadata = load_keystore_metadata(auth_dir)
    keypairs = keystore.list_keypair_identifiers()

    (HERE / "passphrase.json").write_text(json.dumps({
        "raw": PASSPHRASE_RAW,
        "normalized_utf8_hex": _encode_passphrase(PASSPHRASE_RAW).hex(),
        "equivalent_after_normalization": PASSPHRASE_NORMALIZED_EQUIVALENT,
        "wrong": PASSPHRASE_WRONG,
    }, indent=2) + "\n")

    # 2. Listing edge cases: one complete keypair, one public-only keypair, and files the listing must skip
    edge_dir = HERE / "edge_cases.keystore"
    edge_keystore = make_authenticator(edge_dir, owner="Edge Cases", hint="same passphrase as authenticator.keystore", keypair_count=1)
    orphan_uid = generate_uuid0()
    orphan = generate_keypair(key_algo="RSA_OAEP", passphrase=PASSPHRASE_RAW)
    edge_keystore.set_public_key(keychain_uid=orphan_uid, key_algo="RSA_OAEP", public_key=orphan["public_key"])
    (edge_dir / ("%s_RSA_OAEP_public_key.pem" % str(generate_uuid0()).upper())).write_bytes(orphan["public_key"])
    (edge_dir / "not-a-uuid_RSA_OAEP_public_key.pem").write_bytes(orphan["public_key"])
    (edge_dir / "notes.txt").write_text("Unrelated file, must be ignored by the keypair listing.\n")

    # 3. A gateway response for list_authenticator_revelation_requests, built exactly like the server serializer does
    response_uid = generate_uuid0()
    response_keypair = generate_keypair(key_algo="RSA_OAEP")  # Claimant's one-time key: private key UNPROTECTED (PKCS#1)
    (HERE / "gateway").mkdir(exist_ok=True)
    (HERE / "gateway" / "claimant_response_private_key.pem").write_bytes(response_keypair["private_key"])

    public_authenticator = {
        "keystore_uid": metadata["keystore_uid"],
        "keystore_owner": metadata["keystore_owner"],
        "keystore_creation_datetime": metadata["keystore_creation_datetime"],
        "public_keys": [{"keychain_uid": k["keychain_uid"], "key_algo": k["key_algo"],
                         "key_value": keystore.get_public_key(keychain_uid=k["keychain_uid"], key_algo=k["key_algo"])}
                        for k in keypairs],
    }

    expected_plaintexts = []
    symkey_requests = []
    for idx, (keypair, cipher_algo) in enumerate(zip(keypairs[:2], ["AES_EAX", "CHACHA20_POLY1305"])):
        key_struct_bytes = dump_to_json_bytes(generate_symkey(cipher_algo))  # What a recorder wraps
        public_key = load_asymmetric_key_from_pem_bytestring(
            keystore.get_public_key(keychain_uid=keypair["keychain_uid"], key_algo="RSA_OAEP"), key_algo="RSA_OAEP")
        request_data = dump_to_json_bytes(encrypt_bytestring(key_struct_bytes, cipher_algo="RSA_OAEP", key_dict=dict(key=public_key)))
        expected_plaintexts.append({"symkey_decryption_request_data": request_data, "key_struct_bytes": key_struct_bytes})
        symkey_requests.append({
            "target_public_authenticator_key": public_authenticator["public_keys"][idx],
            "cryptainer_name": "20261024_120000_camera_%d.mp4.crypt" % idx,
            "cryptainer_uid": generate_uuid0(),
            "cryptainer_metadata": None if idx == 0 else {"location": "Paris", "count": 3},
            "symkey_decryption_request_data": request_data,
            "symkey_decryption_response_data": b"",
            "symkey_decryption_status": "PENDING",
        })

    pending_request = {
        "target_public_authenticator": public_authenticator,
        "revelation_request_uid": generate_uuid0(),
        "revelation_requestor_uid": generate_uuid0(),
        "revelation_request_description": "Judicial request n° 42, please accept",
        "revelation_response_public_key": response_keypair["public_key"],
        "revelation_response_keychain_uid": response_uid,
        "revelation_response_key_algo": "RSA_OAEP",
        "revelation_request_status": "PENDING",
        "symkey_decryption_requests": symkey_requests,
        "created_at": datetime(2026, 10, 24, 12, 0, 0, 123000, tzinfo=timezone.utc),
    }
    rejected_request = dict(pending_request, revelation_request_uid=generate_uuid0(), revelation_request_status="REJECTED",
                            revelation_request_description="Old request that was rejected",
                            created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    empty_request = dict(pending_request, revelation_request_uid=generate_uuid0(), symkey_decryption_requests=[],
                         revelation_request_description="Pending request with an empty symkey list (edge case)",
                         created_at=datetime(2026, 10, 23, 8, 0, 0, tzinfo=timezone.utc))

    write_json(HERE / "gateway" / "list_authenticator_revelation_requests.response.json",
               {"jsonrpc": "2.0", "id": 5776600559367167158, "result": [pending_request, rejected_request, empty_request]})
    write_json(HERE / "gateway" / "get_public_authenticator.response.json",
               {"jsonrpc": "2.0", "id": 1234, "result": public_authenticator})
    write_json(HERE / "gateway" / "error_KeystoreDoesNotExist.response.json", {
        "jsonrpc": "2.0", "id": 1234,
        "error": {"name": "Error", "code": 400,
                  "message": "Error: Server-side exception occurred, see error data for details",
                  "data": {"status_slugs": ["wacryptolib.exceptions.FunctionalError",
                                            "wacryptolib.exceptions.ExistenceError",
                                            "wacryptolib.exceptions.KeystoreDoesNotExist"],
                           "data": None, "message_translated": None,
                           "message_untranslated": "Authenticator %s does not exist in database" % metadata["keystore_uid"]}}})
    write_json(HERE / "gateway" / "expected_plaintexts.json", expected_plaintexts)

    # 4. What the 1.5 app sends back for the pending request (response ciphertexts are randomized by OAEP)
    trustee_api = TrusteeApi(keystore=FilesystemKeystore(auth_dir))
    response_key = load_asymmetric_key_from_pem_bytestring(response_keypair["public_key"], key_algo="RSA_OAEP")
    results = []
    for item in symkey_requests:
        plaintext = trustee_api.decrypt_with_private_key(
            keychain_uid=item["target_public_authenticator_key"]["keychain_uid"], cipher_algo="RSA_OAEP",
            cipherdict=load_from_json_bytes(item["symkey_decryption_request_data"]), passphrases=[PASSPHRASE_RAW])
        results.append({
            "symkey_decryption_request_data": item["symkey_decryption_request_data"],
            "symkey_decryption_response_data": dump_to_json_bytes(
                encrypt_bytestring(plaintext, cipher_algo="RSA_OAEP", key_dict=dict(key=response_key))),
            "symkey_decryption_status": "DECRYPTED",
        })
    write_json(HERE / "gateway" / "accept_revelation_request.request.json", {
        "id": 5776600559367167159, "jsonrpc": "2.0", "method": "accept_revelation_request",
        "params": {"authenticator_keystore_secret": metadata["keystore_secret"],
                   "revelation_request_uid": pending_request["revelation_request_uid"],
                   "symkey_decryption_results": results}})

    self_check()


def self_check():
    """Assertions a reimplementation can mirror in its own test suite."""
    auth_dir = HERE / "authenticator.keystore"
    keystore = FilesystemKeystore(auth_dir)
    keypairs = keystore.list_keypair_identifiers()
    assert len(keypairs) == 3 and all(k["private_key_present"] for k in keypairs)
    for passphrase in (PASSPHRASE_RAW, PASSPHRASE_NORMALIZED_EQUIVALENT):
        for k in keypairs:
            load_asymmetric_key_from_pem_bytestring(
                keystore.get_private_key(keychain_uid=k["keychain_uid"], key_algo="RSA_OAEP"), key_algo="RSA_OAEP",
                passphrase=passphrase)
    try:
        load_asymmetric_key_from_pem_bytestring(
            keystore.get_private_key(keychain_uid=keypairs[0]["keychain_uid"], key_algo="RSA_OAEP"), key_algo="RSA_OAEP",
            passphrase=PASSPHRASE_WRONG)
        raise AssertionError("wrong passphrase accepted")
    except Exception as exc:
        assert exc.__class__.__name__ == "KeyLoadingError", exc

    edge = FilesystemKeystore(HERE / "edge_cases.keystore").list_keypair_identifiers()
    assert [k["private_key_present"] for k in edge] in ([True, False], [False, True]), edge

    response = load_from_json_bytes((HERE / "gateway" / "list_authenticator_revelation_requests.response.json").read_bytes())
    expected = load_from_json_bytes((HERE / "gateway" / "expected_plaintexts.json").read_bytes())
    request = load_from_json_bytes((HERE / "gateway" / "accept_revelation_request.request.json").read_bytes())
    response_private_key = load_asymmetric_key_from_pem_bytestring(
        (HERE / "gateway" / "claimant_response_private_key.pem").read_bytes(), key_algo="RSA_OAEP")
    pending = response["result"][0]
    assert isinstance(pending["revelation_request_uid"], uuid.UUID)
    for item, exp, result in zip(pending["symkey_decryption_requests"], expected, request["params"]["symkey_decryption_results"]):
        assert item["symkey_decryption_request_data"] == exp["symkey_decryption_request_data"] == result["symkey_decryption_request_data"]
        plaintext = TrusteeApi(keystore=keystore).decrypt_with_private_key(
            keychain_uid=item["target_public_authenticator_key"]["keychain_uid"], cipher_algo="RSA_OAEP",
            cipherdict=load_from_json_bytes(item["symkey_decryption_request_data"]), passphrases=[PASSPHRASE_RAW])
        assert plaintext == exp["key_struct_bytes"]
        assert decrypt_bytestring(load_from_json_bytes(result["symkey_decryption_response_data"]), cipher_algo="RSA_OAEP",
                                  key_dict=dict(key=response_private_key)) == plaintext
    print("Fixtures OK")


if __name__ == "__main__":
    main()
