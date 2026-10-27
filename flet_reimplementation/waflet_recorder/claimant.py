"""Claimant side of the revelation flow: device uid, request creation and listing (03 §10.8-10.9, 04 §10). GUI-free.

Fixes applied: OI-72 (settings read at use), OI-73 (HTTP timeout), OI-74 (per-guardian errors, nothing lost),
OI-76 (the list is fetched at each call). OI-77 (decide): response keys stay unprotected, but are deleted again
when no request at all could be submitted with them.
"""
import logging
from pathlib import Path

from jsonrpc_requests import JSONRPCError
from wacryptolib.cryptainer import gather_decryptable_symkeys
from wacryptolib.exceptions import KeystoreDoesNotExist, KeyDoesNotExist
from wacryptolib.keystore import generate_keypair_for_storage
from wacryptolib.utilities import generate_uuid0, load_from_json_file, dump_to_json_file

from waflet_components.authenticator_services import ServiceError

logger = logging.getLogger(__name__)

DESCRIPTION_MIN_LENGTH = 10
RESPONSE_KEY_ALGO = "RSA_OAEP"


class NoAuthenticatorSelectedError(ServiceError):
    msgid = "Please select authenticators"


class DescriptionTooShortError(ServiceError):
    msgid = "Description must be at least 10 characters long."


class GatewayUnreachableError(ServiceError):
    msgid = "Network error, please check the gateway url"


def get_wa_device_uid(roots):
    """Persistent requestor uid (04 §2.1). Created lazily, at the first call (01 §7 SHOULD)."""
    path = roots.device_uid_file
    try:
        return load_from_json_file(path)["wa_device_uid"]
    except FileNotFoundError:
        uid = generate_uuid0()
        path.parent.mkdir(parents=True, exist_ok=True)
        dump_to_json_file(path, {"wa_device_uid": uid})
        return uid


def create_revelation_requests(storage, pool, requestor_uid, gateway_proxy, cryptainer_names, selected_keystore_uids,
                               description) -> dict:
    """Submit one request per ticked guardian, all sharing one new response keypair.
    Returns dict(total, ok=[uids], errors=[dict(keystore_uid, kind, message)], response_keychain_uid).
    Validation errors raise before anything is created or sent."""
    selected = {str(u) for u in selected_keystore_uids}
    if not selected:
        raise NoAuthenticatorSelectedError()
    description = description.strip()
    if len(description) < DESCRIPTION_MIN_LENGTH:
        raise DescriptionTooShortError()
    pairs = [(str(name), storage.load_cryptainer_from_storage(name, include_payload_ciphertext=False))
             for name in cryptainer_names]
    per_trustee = gather_decryptable_symkeys(pairs)
    keyfactory = pool.get_local_keyfactory()
    response_uid = generate_uuid0()
    keypair = generate_keypair_for_storage(RESPONSE_KEY_ALGO, keystore=keyfactory, keychain_uid=response_uid)
    result = dict(total=len(selected), ok=[], errors=[], response_keychain_uid=response_uid)
    for trustee_conf, requests in per_trustee.values():
        uid = trustee_conf.get("keystore_uid")
        if trustee_conf["trustee_type"] != "authenticator" or str(uid) not in selected:
            continue
        try:
            gateway_proxy.submit_revelation_request(
                authenticator_keystore_uid=uid, revelation_requestor_uid=requestor_uid,
                revelation_request_description=description, revelation_response_public_key=keypair["public_key"],
                revelation_response_keychain_uid=response_uid, revelation_response_key_algo=RESPONSE_KEY_ALGO,
                symkey_decryption_requests=requests)
            result["ok"].append(uid)
        except KeystoreDoesNotExist:
            result["errors"].append(dict(keystore_uid=uid, kind="authenticator_missing",
                                         message="Authenticator %s does not exist in sql storage" % str(uid)[-9:]))
        except KeyDoesNotExist:
            result["errors"].append(dict(keystore_uid=uid, kind="key_missing", message=(
                "Public key needed does not exist in key storage in %s authenticator" % str(uid)[-9:])))
        except Exception as exc:  # OI-74: network, JSON-RPC, gateway refusal: reported, the loop goes on
            logger.error("Submission to guardian %s failed: %r", uid, exc)
            result["errors"].append(dict(keystore_uid=uid, kind="other", message=repr(exc)))
    if not result["ok"]:  # OI-77: a response key nobody will ever use
        for suffix in ("_public_key.pem", "_private_key.pem"):
            (Path(keyfactory._keys_dir) / ("%s_%s%s" % (response_uid, RESPONSE_KEY_ALGO, suffix))).unlink(missing_ok=True)
    return result


def list_requests_by_cryptainer(gateway_proxy, requestor_uid) -> list:
    """03 §10.9: groups by cryptainer uid, newest uid first. Each group: cryptainer_uid, cryptainer_name, entries
    (request fields without the symkey list + `symkey_decryption_request`). Raises GatewayUnreachableError."""
    try:
        requests = gateway_proxy.list_requestor_revelation_requests(revelation_requestor_uid=requestor_uid)
    except (JSONRPCError, OSError) as exc:
        raise GatewayUnreachableError() from exc
    groups = {}
    for request in requests:
        base = {k: v for k, v in request.items() if k != "symkey_decryption_requests"}
        for symkey_request in request["symkey_decryption_requests"]:
            group = groups.setdefault(symkey_request["cryptainer_uid"], dict(
                cryptainer_uid=symkey_request["cryptainer_uid"], cryptainer_name=symkey_request["cryptainer_name"], entries=[]))
            group["entries"].append(dict(base, symkey_decryption_request=symkey_request))
    return sorted(groups.values(), key=lambda g: g["cryptainer_uid"].int, reverse=True)
