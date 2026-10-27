"""Key guardians = foreign keystores of the keystore pool (03 §10.1-10.5, 04 §2.2, §3). GUI-free.

Fixes applied: OI-36 (bad UIDs skipped), OI-49 (iterate over copies), OI-51 (corrupted keystores are listed as such,
never raise), OI-52 (a new keystore is built in a temp folder then renamed; a missing private key is skipped),
OI-53 (deletion refused for guardians of the ongoing recording, via `protected_uids`).
"""
import logging
import os
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from wacryptolib.exceptions import ExistenceError, KeyDoesNotExist
from wacryptolib.keystore import (
    FilesystemKeystorePool, FilesystemKeystore, ReadonlyFilesystemKeystore, validate_keystore_tree,
)

from waflet_components.authenticator_services import ServiceError

logger = logging.getLogger(__name__)

NEVER_IMPORTED_FIELDS = ("keystore_secret", "keystore_passphrase_hint")  # 04 §0 item 4: MUST NOT be copied


class GuardianInUseError(ServiceError):
    msgid = "This key guardian is used by the ongoing recording and cannot be removed"


class GatewayAuthenticatorNotFoundError(ServiceError):
    msgid = "Authenticator does not exist"


class BadGuardianUidError(ServiceError):
    msgid = "Badly formed hexadecimal UUID string"


def open_keystore_pool(roots) -> FilesystemKeystorePool:
    roots.keystore_pool_dir.mkdir(parents=True, exist_ok=True)
    return FilesystemKeystorePool(root_dir=roots.keystore_pool_dir)


def _foreign_dir(pool):
    return pool._root_dir / FilesystemKeystorePool.FOREIGN_KEYSTORES_DIRNAME  # ponytail: private attr, no public getter


def list_guardian_uids(pool):
    """Sorted UUIDs of `keystore_<uuid>` folders; folders with a malformed name are skipped (the cryptolib raises)."""
    uids = []
    for path in _foreign_dir(pool).glob(FilesystemKeystorePool.FOREIGN_KEYSTORE_PREFIX + "*"):
        try:
            uids.append(UUID(path.name[len(FilesystemKeystorePool.FOREIGN_KEYSTORE_PREFIX):]))
        except ValueError:
            logger.warning("Skipping foreign keystore folder with abnormal name %s", path.name)
    return sorted(uids)


def list_guardians(pool) -> list:
    """One dict per guardian: keystore_uid, keystore_owner, keystore_creation_datetime, keypairs
    (key_algo, keychain_uid, private_key_present), corrupted (bool), error (str or None) (OI-51)."""
    guardians = []
    for uid in list_guardian_uids(pool):
        entry = dict(keystore_uid=uid, keystore_owner=None, keystore_creation_datetime=None, keypairs=[],
                     corrupted=False, error=None)
        try:
            metadata = pool.get_foreign_keystore_metadata(uid, include_keypair_identifiers=True)
            entry.update(keystore_owner=metadata["keystore_owner"], keypairs=metadata["keypair_identifiers"],
                         keystore_creation_datetime=metadata.get("keystore_creation_datetime"))
        except Exception as exc:  # Partial import, hand edit...
            logger.warning("Corrupted foreign keystore %s: %r", uid, exc)
            entry.update(corrupted=True, error=repr(exc))
        guardians.append(entry)
    return guardians


def get_selected_guardian_uids(settings, pool) -> list:
    """Configured selection, in config order, filtered to the guardians still in the pool (03 §4.3.1)."""
    available = set(list_guardian_uids(pool))
    result = []
    for uid_str in settings.selected_keyguardians:
        uid = UUID(uid_str)
        if uid in available and uid not in result:
            result.append(uid)
    return result


def _prepare_tree(tree):
    tree = {k: v for k, v in tree.items() if k not in NEVER_IMPORTED_FIELDS}
    validate_keystore_tree(tree)
    return tree


def import_tree_into_pool(pool, tree) -> bool:
    """Import a keystore tree; return True iff an existing guardian was updated. A new guardian appears
    atomically (temp folder renamed), an existing one is completed with the missing keys (OI-52)."""
    tree = _prepare_tree(tree)
    uid = tree["keystore_uid"]
    final_dir = pool._get_foreign_keystore_dir(uid)
    if final_dir.exists():
        return pool.import_foreign_keystore_from_keystore_tree(tree)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="~import-", dir=final_dir.parent))  # Not matched by "keystore_*"
    try:
        FilesystemKeystore(tmp_dir).import_from_keystore_tree(tree)
        os.rename(tmp_dir, final_dir)
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return False


def import_from_authdevice(pool, authenticator_dir, include_private_keys) -> dict:
    """03 §10.2 for one device. Returns dict(keystore_uid, owner, updated, private_keys_skipped).
    Raises SchemaValidationError / ValidationError / KeystoreMetadataDoesNotExist for the caller to count as corrupted."""
    keystore = ReadonlyFilesystemKeystore(Path(authenticator_dir))
    tree = keystore.export_to_keystore_tree(include_private_keys=False)
    skipped = 0
    if include_private_keys:
        for keypair in tree["keypairs"]:
            try:  # OI-52: an authenticator lacking a private key no longer aborts the whole import
                keypair["private_key"] = keystore.get_private_key(keychain_uid=keypair["keychain_uid"],
                                                                  key_algo=keypair["key_algo"])
            except KeyDoesNotExist:
                skipped += 1
    updated = import_tree_into_pool(pool, tree)
    return dict(keystore_uid=tree["keystore_uid"], owner=tree["keystore_owner"], updated=updated,
                private_keys_skipped=skipped)


def import_from_authdevices(pool, authenticator_dirs, include_private_keys) -> dict:
    """Batch of `import_from_authdevice`. Result: new (list of uids), updated (list), skipped (count).
    The caller auto-selects `new` only (03 §10.2)."""
    result = dict(new=[], updated=[], skipped=0)
    for authenticator_dir in authenticator_dirs:
        try:
            imported = import_from_authdevice(pool, authenticator_dir, include_private_keys)
        except Exception as exc:  # SchemaValidationError, ValidationError (uid mismatch), missing metadata...
            logger.warning("Skipping corrupted authdevice %s: %r", authenticator_dir, exc)
            result["skipped"] += 1
            continue
        result["updated" if imported["updated"] else "new"].append(imported["keystore_uid"])
    return result


def parse_guardian_uid(text) -> UUID:
    try:
        return UUID(text.strip().lower())
    except ValueError as exc:
        raise BadGuardianUidError() from exc


def import_from_gateway(pool, gateway_proxy, uid_text) -> dict:
    """03 §10.3. Public keys only. Raises BadGuardianUidError / GatewayAuthenticatorNotFoundError; other errors
    (network, JSON-RPC) propagate. Returns dict(keystore_uid, owner, updated); the caller auto-selects the uid."""
    uid = parse_guardian_uid(uid_text)
    try:
        public_authenticator = gateway_proxy.get_public_authenticator(keystore_uid=uid)
    except ExistenceError as exc:  # Includes KeystoreDoesNotExist
        raise GatewayAuthenticatorNotFoundError() from exc
    tree = dict(
        keystore_type="authenticator", keystore_format="keystore_1.0",
        keystore_owner=public_authenticator["keystore_owner"], keystore_uid=public_authenticator["keystore_uid"],
        keypairs=[dict(keychain_uid=k["keychain_uid"], key_algo=k["key_algo"], public_key=k["key_value"],
                       private_key=None) for k in public_authenticator["public_keys"]],
    )
    if public_authenticator.get("keystore_creation_datetime"):
        tree["keystore_creation_datetime"] = public_authenticator["keystore_creation_datetime"]
    updated = import_tree_into_pool(pool, tree)
    return dict(keystore_uid=tree["keystore_uid"], owner=tree["keystore_owner"], updated=updated)


def delete_guardians(pool, uids, protected_uids=()) -> dict:
    """03 §10.4. Iterates over a copy (OI-49). `protected_uids` = guardians of the ongoing recording: refusing
    all of them (OI-53) before deleting anything. Returns dict(deleted=[...], failed=[(uid, error)])."""
    uids = list(uids)
    protected = {UUID(str(u)) for u in protected_uids}
    if any(UUID(str(u)) in protected for u in uids):
        raise GuardianInUseError()
    result = dict(deleted=[], failed=[])
    for uid in uids:
        try:
            shutil.rmtree(pool._get_foreign_keystore_dir(UUID(str(uid))))
            result["deleted"].append(uid)
        except OSError as exc:  # Logged, the loop continues (03 §10.4)
            logger.error("Could not delete key guardian %s: %r", uid, exc)
            result["failed"].append((uid, repr(exc)))
    return result
