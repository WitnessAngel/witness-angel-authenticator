"""Authenticator business logic, GUI-free (03). Everything crypto/keystore/gateway goes through wacryptolib.

Functions raise wacryptolib exceptions or the small `ServiceError` subclasses below; screens map them to texts.
"""
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from wacryptolib.authenticator import initialize_authenticator, is_authenticator_initialized
from wacryptolib.cipher import encrypt_bytestring, decrypt_bytestring
from wacryptolib.exceptions import (
    KeyLoadingError, KeyDoesNotExist, DecryptionError, SchemaValidationError, ValidationError,
)
from wacryptolib.keygen import generate_keypair, load_asymmetric_key_from_pem_bytestring
from wacryptolib.keystore import FilesystemKeystore, ReadonlyFilesystemKeystore, load_keystore_metadata
from wacryptolib.utilities import generate_uuid0, load_from_json_bytes, dump_to_json_bytes

from .storage import is_folder_writable

logger = logging.getLogger(__name__)

GENERATED_KEYS_COUNT = 3
KEY_ALGO = "RSA_OAEP"
PASSPHRASE_MIN_LENGTH = 20
MAX_WA_CHARFIELD_LENGTH = 100
REVELATION_REQUEST_STATUSES = ("PENDING", "ACCEPTED", "REJECTED")


class ServiceError(Exception):
    """Expected, user-facing failure; `msgid` is an English i18n msgid."""
    msgid = "Operation failed, check logs."


class UnsupportedAlgorithmError(ServiceError):
    msgid = "Unsupported algorithm in this request"


class EmptyRevelationRequestError(ServiceError):
    msgid = "This request contains no key to decrypt"


class NotPendingError(ServiceError):
    msgid = "Only pending requests can be accepted or rejected"


class NoGatewaySecretError(ServiceError):
    msgid = "This authenticator has no gateway secret and cannot be published or receive requests"


class MissingPrivateKeysError(ServiceError):
    msgid = "Some private keys are missing, publication is refused (run a Check first)"


class NoKeypairError(ServiceError):
    msgid = "This authenticator has no keypair and cannot be published"


class InvalidArchiveError(ServiceError):
    msgid = "The archive does not contain a valid authenticator"


class TargetNotEmptyError(ServiceError):
    msgid = "The target folder is not empty"


class NotInitializedError(ServiceError):
    msgid = "No authenticator found in this folder"


class AtomicFilesystemKeystore(FilesystemKeystore):
    """OI-22: PEM files are written to a temp sibling then renamed; content and names are unchanged."""

    def _write_to_storage_file(self, filepath: Path, data: bytes):
        assert self._keys_dir in filepath.parents
        tmp_path = filepath.with_name(filepath.name + ".tmp")  # Never matches the *_key.pem listing glob
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, filepath)


# ---------------------------------------------------------------- local state (03 §3.1)

def compute_authenticator_status(authenticator_dir) -> dict:
    """Ternary status of 02 §3.3. `reason` names the information text to display."""
    if not authenticator_dir:
        return dict(status=None, reason="no_location")
    authenticator_dir = Path(authenticator_dir)
    result = dict(authenticator_dir=authenticator_dir)
    if not is_authenticator_initialized(authenticator_dir):
        parent = authenticator_dir.parent
        if not parent.is_dir():
            reason = "parent_missing"
        elif not authenticator_dir.exists():
            reason = None if is_folder_writable(parent) else "parent_not_writable"
        elif not authenticator_dir.is_dir():
            reason = "not_a_folder"
        else:
            reason = None if is_folder_writable(authenticator_dir) else "folder_not_writable"
        return dict(result, status=None if reason else False, reason=reason or "not_initialized")
    try:
        metadata = load_keystore_metadata(authenticator_dir)
    except (SchemaValidationError, ValueError, TypeError) as exc:  # OI-18: JSONDecodeError is a ValueError
        logger.warning("Invalid authenticator metadata in %s: %r", authenticator_dir, exc)
        return dict(result, status=None, reason="invalid_data")
    keypairs = ReadonlyFilesystemKeystore(authenticator_dir).list_keypair_identifiers()
    return dict(result, status=True, reason="initialized", metadata=metadata, keypairs=keypairs,
                has_secret=bool(metadata.get("keystore_secret")))  # OI-17


# ---------------------------------------------------------------- creation (03 §4)

def validate_creation_form(keystore_owner, passphrase, passphrase_hint):
    """Return (cleaned values dict, None) or (None, error msgid). The `¤` back door is removed (OI-10)."""
    values = dict(keystore_owner=keystore_owner.strip(), passphrase=passphrase.strip(),
                  keystore_passphrase_hint=passphrase_hint.strip())
    if not all(values.values()):
        return None, "Please enter a username, passphrase and passphrase hint."
    if any(len(v) > MAX_WA_CHARFIELD_LENGTH for v in values.values()):
        return None, "Username, passphrase and passphrase hint must not exceed 100 characters"
    if len(values["passphrase"]) < PASSPHRASE_MIN_LENGTH:
        return None, "Passphrase must be at least 20 characters long."
    return values, None


def create_authenticator(authenticator_dir, keystore_owner, passphrase, keystore_passphrase_hint,
                         keypair_count=GENERATED_KEYS_COUNT, progress_callback=None):
    """Metadata then `keypair_count` RSA_OAEP keypairs. On any failure, files created here are removed (OI-11)."""
    authenticator_dir = Path(authenticator_dir)
    created_dir = not authenticator_dir.exists()
    if created_dir:
        authenticator_dir.mkdir(parents=False)  # Only one level is created (01 §4)
    preexisting = set(authenticator_dir.iterdir())
    progress = progress_callback or (lambda percent: None)
    try:
        metadata = initialize_authenticator(authenticator_dir, keystore_owner=keystore_owner,
                                            keystore_passphrase_hint=keystore_passphrase_hint)
        progress(10)
        keystore = AtomicFilesystemKeystore(authenticator_dir)
        for i in range(1, keypair_count + 1):
            keypair = generate_keypair(key_algo=KEY_ALGO, passphrase=passphrase)
            keystore.set_keypair(keychain_uid=generate_uuid0(), key_algo=KEY_ALGO,
                                 public_key=keypair["public_key"], private_key=keypair["private_key"])
            progress(10 + int(i * 90 / keypair_count))
        return metadata
    except BaseException:
        logger.exception("Authenticator creation failed in %s, rolling back", authenticator_dir)
        if created_dir:
            shutil.rmtree(authenticator_dir, ignore_errors=True)
        else:
            for path in set(authenticator_dir.iterdir()) - preexisting:
                path.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- check (03 §5)

def _load_private_key(keystore, keychain_uid, key_algo, passphrase):
    """Like TrusteeApi: try "no passphrase" first (OI-08 keep), then the given one; KeyLoadingError otherwise."""
    pem = keystore.get_private_key(keychain_uid=keychain_uid, key_algo=key_algo)
    try:
        return load_asymmetric_key_from_pem_bytestring(pem, key_algo=key_algo, passphrase=None)
    except KeyLoadingError:
        return load_asymmetric_key_from_pem_bytestring(pem, key_algo=key_algo, passphrase=passphrase)


def check_authenticator_passphrase(authenticator_dir, passphrase) -> dict:
    keystore = ReadonlyFilesystemKeystore(authenticator_dir)
    keypairs = keystore.list_keypair_identifiers()
    missing, undecodable = [], []
    for key in keypairs:
        identifier = (key["key_algo"], key["keychain_uid"])
        if not key["private_key_present"]:
            missing.append(identifier)
            continue
        try:
            pem = keystore.get_private_key(keychain_uid=key["keychain_uid"], key_algo=key["key_algo"])
            load_asymmetric_key_from_pem_bytestring(pem, key_algo=key["key_algo"], passphrase=passphrase)
        except KeyLoadingError:
            undecodable.append(identifier)
    return dict(keypair_count=len(keypairs), missing_private_keys=missing, undecodable_private_keys=undecodable,
                success=bool(keypairs) and not missing and not undecodable)


# ---------------------------------------------------------------- export / import / destroy (03 §8)

def export_authenticator(authenticator_dir, exports_dir, now=None) -> Path:
    metadata = load_keystore_metadata(Path(authenticator_dir))  # Invalid metadata makes the export fail
    now = now or datetime.now(timezone.utc)
    stem = "authenticator_id%s_date%s" % (str(metadata["keystore_uid"]).split("-")[-1], now.strftime("%Y%m%d%H%M%S"))
    archive = shutil.make_archive(str(Path(exports_dir) / stem), "zip", root_dir=str(authenticator_dir))
    return Path(archive)


def import_authenticator(archive_path, authenticator_dir) -> Path:
    """OI-20 (decide): extract into a temp sibling, validate, refuse a non-empty target, then move into place."""
    authenticator_dir = Path(authenticator_dir)
    if authenticator_dir.exists() and any(authenticator_dir.iterdir()):
        raise TargetNotEmptyError()
    if not zipfile.is_zipfile(archive_path):
        raise InvalidArchiveError()
    tmp_dir = Path(tempfile.mkdtemp(prefix="~import-", dir=authenticator_dir.parent))
    try:
        shutil.unpack_archive(str(archive_path), extract_dir=str(tmp_dir), format="zip")
        try:
            load_keystore_metadata(tmp_dir)
        except Exception as exc:
            raise InvalidArchiveError() from exc
        if not ReadonlyFilesystemKeystore(tmp_dir).list_keypair_identifiers():
            raise InvalidArchiveError()
        authenticator_dir.mkdir(exist_ok=True)
        for item in tmp_dir.iterdir():
            item.rename(authenticator_dir / item.name)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return authenticator_dir


def destroy_authenticator(authenticator_dir):
    authenticator_dir = Path(authenticator_dir)
    if not is_authenticator_initialized(authenticator_dir):  # OI-19 guard, like the CLI
        raise NotInitializedError()
    shutil.rmtree(authenticator_dir)


# ---------------------------------------------------------------- publication (03 §6)

def _require_secret(metadata):
    if not metadata.get("keystore_secret"):
        raise NoGatewaySecretError()
    return metadata["keystore_secret"]


def get_publication_status(authenticator_dir, gateway_proxy) -> dict:
    """Return local info + remote status "NOT_PUBLISHED"/"PUBLISHED", raising on gateway errors.

    OI-29 (decide): the secret is sent, so a record published with another secret raises AuthenticationError.
    """
    from wacryptolib.exceptions import ExistenceError

    metadata = load_keystore_metadata(Path(authenticator_dir))
    secret = _require_secret(metadata)
    local_keys = ReadonlyFilesystemKeystore(authenticator_dir).list_keypair_identifiers()
    result = dict(metadata=metadata, local_keys=local_keys, exceeding_keys=[], missing_keys=[])
    try:
        remote = gateway_proxy.get_public_authenticator(keystore_uid=metadata["keystore_uid"], keystore_secret=secret)
    except ExistenceError:
        return dict(result, remote_status="NOT_PUBLISHED")
    local_set = {(k["keychain_uid"], k["key_algo"]) for k in local_keys}
    remote_set = {(k["keychain_uid"], k["key_algo"]) for k in remote["public_keys"]}
    return dict(result, remote_status="PUBLISHED",
                exceeding_keys=sorted(remote_set - local_set, key=lambda k: (k[0].int, k[1])),
                missing_keys=sorted(local_set - remote_set, key=lambda k: (k[0].int, k[1])))


def check_publishable(authenticator_dir):
    """OI-28 / OI-32: no publication with missing private keys or without keypairs."""
    keys = ReadonlyFilesystemKeystore(authenticator_dir).list_keypair_identifiers()
    if not keys:
        raise NoKeypairError()
    if not all(k["private_key_present"] for k in keys):
        raise MissingPrivateKeysError()


def publish_authenticator(authenticator_dir, gateway_proxy):
    metadata = load_keystore_metadata(Path(authenticator_dir))
    check_publishable(authenticator_dir)
    if len(metadata["keystore_owner"]) > MAX_WA_CHARFIELD_LENGTH:  # Checklist item 20
        raise ValidationError("keystore_owner exceeds %d characters" % MAX_WA_CHARFIELD_LENGTH)
    keystore = ReadonlyFilesystemKeystore(authenticator_dir)
    params = dict(
        keystore_owner=metadata["keystore_owner"],
        keystore_uid=metadata["keystore_uid"],
        keystore_secret=_require_secret(metadata),
        public_keys=[dict(keychain_uid=k["keychain_uid"], key_algo=k["key_algo"],
                          key_value=keystore.get_public_key(keychain_uid=k["keychain_uid"], key_algo=k["key_algo"]))
                     for k in keystore.list_keypair_identifiers()],
    )
    if metadata.get("keystore_creation_datetime"):
        params["keystore_creation_datetime"] = metadata["keystore_creation_datetime"]
    gateway_proxy.set_public_authenticator(**params)  # Never the passphrase, hint or private keys


# ---------------------------------------------------------------- revelation requests (03 §7)

def list_revelation_requests(authenticator_dir, gateway_proxy) -> dict:
    """Group by status, newest first; unknown statuses are logged and skipped (OI-05)."""
    metadata = load_keystore_metadata(Path(authenticator_dir))
    secret = _require_secret(metadata)
    requests = gateway_proxy.list_authenticator_revelation_requests(
        authenticator_keystore_secret=secret, authenticator_keystore_uid=metadata["keystore_uid"])
    grouped = {status: [] for status in REVELATION_REQUEST_STATUSES}
    for request in requests:
        status = request.get("revelation_request_status")
        if status not in grouped:
            logger.warning("Ignoring revelation request %s with unknown status %r",
                           request.get("revelation_request_uid"), status)
            continue
        grouped[status].append(request)
    for items in grouped.values():
        items.sort(key=lambda r: r["created_at"], reverse=True)
    return grouped


def check_revelation_request_acceptable(revelation_request):
    """OI-03 input checks, before any decryption."""
    if revelation_request["revelation_request_status"] != "PENDING":
        raise NotPendingError()
    symkey_requests = revelation_request["symkey_decryption_requests"]
    if revelation_request["revelation_response_key_algo"] != KEY_ALGO or any(
            s["target_public_authenticator_key"]["key_algo"] != KEY_ALGO for s in symkey_requests):
        raise UnsupportedAlgorithmError()
    if not symkey_requests:
        raise EmptyRevelationRequestError()


def build_symkey_decryption_results(authenticator_dir, revelation_request, passphrase) -> list:
    """03 §7.3 + fixes OI-01/02/03/04/07. A wrong passphrase raises KeyLoadingError (nothing must be sent)."""
    check_revelation_request_acceptable(revelation_request)
    keystore = FilesystemKeystore(authenticator_dir)
    response_key_algo = revelation_request["revelation_response_key_algo"]
    response_public_key = load_asymmetric_key_from_pem_bytestring(
        revelation_request["revelation_response_public_key"], key_algo=response_key_algo)  # OI-02
    private_keys = {}  # OI-07: each private key is decrypted once per Accept
    results, seen = [], set()
    for symkey_request in revelation_request["symkey_decryption_requests"]:
        request_data = symkey_request["symkey_decryption_request_data"]
        if request_data in seen:  # OI-03 (d)
            continue
        seen.add(request_data)
        target = symkey_request["target_public_authenticator_key"]
        cache_key = (target["keychain_uid"], target["key_algo"])
        status, response_data = "DECRYPTED", b""
        try:
            if cache_key not in private_keys:
                private_keys[cache_key] = _load_private_key(keystore, *cache_key, passphrase=passphrase)
            cipherdict = load_from_json_bytes(request_data)
            key_struct_bytes = decrypt_bytestring(cipherdict=cipherdict, cipher_algo=target["key_algo"],
                                                  key_dict=dict(key=private_keys[cache_key]))
            response_data = dump_to_json_bytes(encrypt_bytestring(
                key_struct_bytes, cipher_algo=response_key_algo, key_dict=dict(key=response_public_key)))
        except KeyDoesNotExist:
            status = "PRIVATE_KEY_MISSING"  # OI-01
        except (DecryptionError, ValueError, TypeError, KeyError) as exc:  # OI-04: garbage request data
            logger.warning("Symkey decryption request is corrupted: %r", exc)
            status = "CORRUPTED"
        if status != "DECRYPTED":
            response_data = b""  # Gateway coherence rule: only DECRYPTED carries data
        results.append(dict(symkey_decryption_request_data=request_data,  # Echoed byte for byte
                            symkey_decryption_response_data=response_data,
                            symkey_decryption_status=status))
    return results


def accept_revelation_request(authenticator_dir, revelation_request, passphrase, gateway_proxy):
    metadata = load_keystore_metadata(Path(authenticator_dir))
    secret = _require_secret(metadata)
    results = build_symkey_decryption_results(authenticator_dir, revelation_request, passphrase)
    gateway_proxy.accept_revelation_request(authenticator_keystore_secret=secret,
                                            revelation_request_uid=revelation_request["revelation_request_uid"],
                                            symkey_decryption_results=results)
    return results


def reject_revelation_request(authenticator_dir, revelation_request, gateway_proxy):
    metadata = load_keystore_metadata(Path(authenticator_dir))
    if revelation_request["revelation_request_status"] != "PENDING":
        raise NotPendingError()
    logger.info("Rejecting revelation request %s", revelation_request["revelation_request_uid"])
    gateway_proxy.reject_revelation_request(authenticator_keystore_secret=_require_secret(metadata),
                                            revelation_request_uid=revelation_request["revelation_request_uid"])


def get_gateway_proxy(url):
    from wacryptolib.jsonrpc_client import JsonRpcProxy, status_slugs_response_error_handler

    return JsonRpcProxy(url=url, response_error_handler=status_slugs_response_error_handler)
