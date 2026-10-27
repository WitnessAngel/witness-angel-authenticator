"""Local + remote decryption of cryptainers and its report (03 §10.7, 04 §6.3, §10.5, §13). GUI-free.

Fixes applied: OI-66 (a repeated passphrase is reported neutrally, never echoed), OI-68 (the mapper is an
instance, `clear()`ed by the caller; tested against a key actually needed), OI-69 (a failure is a result, not
a silent omission), OI-70 (no silent overwrite of exports; header views do not load payloads), OI-71 (reports
written once, at decryption time), OI-72 (one gateway call per batch, settings read at use), OI-73 (HTTP timeout).
"""
import logging
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from jsonrpc_requests import JSONRPCError
from wacryptolib.cryptainer import (
    CryptainerDecryptor, DecryptionErrorType, DecryptionErrorCriticity, OperationReport, gather_trustee_dependencies,
)
from wacryptolib.exceptions import KeyLoadingError
from wacryptolib.keygen import load_asymmetric_key_from_pem_bytestring

from waflet_components.authenticator_services import get_gateway_proxy
from waflet_components.i18n import tr

logger = logging.getLogger(__name__)

GATEWAY_TIMEOUT_S = 10  # OI-73, as the Authenticator


class PassphraseMapper:
    """In-memory `{trustee_id: [passphrases]}` of one decryption flow (04 §8). Never persisted, never logged."""

    def __init__(self):
        self._passphrases = {}

    def add(self, trustee_id, passphrase):
        self._passphrases.setdefault(trustee_id, [])
        if passphrase not in self._passphrases[trustee_id]:
            self._passphrases[trustee_id].append(passphrase)

    def knows(self, passphrase) -> bool:
        return any(passphrase in values for values in self._passphrases.values())

    def has_passphrase_for(self, trustee_id) -> bool:
        return bool(self._passphrases.get(trustee_id))

    def as_dict(self) -> dict:
        return {key: list(values) for key, values in self._passphrases.items()}

    def clear(self):
        self._passphrases.clear()


# ---------------------------------------------------------------- trustee dependency status (03 §10.7.1)

def get_trustee_status(storage, pool, cryptainer_names, mapper) -> list:
    """One dict per trustee needed by the selected cryptainers, sorted by owner: trustee_id, trustee_type,
    keystore_uid, owner, found (local foreign keystore exists), passphrase_set, needed_keys ([{keychain_uid, key_algo}]),
    missing_private_keys (subset). Header-only loading: payloads are not read (OI-70)."""
    cryptainers = [storage.load_cryptainer_from_storage(name, include_payload_ciphertext=False) for name in cryptainer_names]
    dependencies = gather_trustee_dependencies(cryptainers)["encryption"]
    statuses = []
    for trustee_id, (trustee_conf, needed_keys) in dependencies.items():
        entry = dict(trustee_id=trustee_id, trustee_type=trustee_conf["trustee_type"], owner=trustee_conf.get("keystore_owner"),
                     keystore_uid=trustee_conf.get("keystore_uid"), found=False, passphrase_set=mapper.has_passphrase_for(trustee_id),
                     needed_keys=needed_keys, missing_private_keys=list(needed_keys))
        if entry["trustee_type"] == "authenticator":
            try:
                keystore = pool.get_foreign_keystore(entry["keystore_uid"])
                entry["owner"] = pool.get_foreign_keystore_metadata(entry["keystore_uid"])["keystore_owner"]
                entry["found"] = True
                present = {(k["keychain_uid"], k["key_algo"]) for k in keystore.list_keypair_identifiers()
                           if k["private_key_present"]}
                entry["missing_private_keys"] = [k for k in needed_keys if (k["keychain_uid"], k["key_algo"]) not in present]
            except Exception as exc:  # KeystoreDoesNotExist, corrupted metadata...
                logger.info("Trustee %s not usable locally: %r", trustee_id, exc)
        statuses.append(entry)
    statuses.sort(key=lambda e: e["owner"] or "")
    return statuses


def check_passphrase(pool, trustee_statuses, mapper, passphrase) -> dict:
    """03 §10.7.2 + OI-66/68. Returns dict(result="recognized"|"already_entered"|"no_match", trustee_ids=[...]).
    The passphrase is tried on a private key actually needed by the selection (one per trustee)."""
    if mapper.knows(passphrase):
        return dict(result="already_entered", trustee_ids=[])
    recognized = []
    for status in trustee_statuses:
        if status["trustee_type"] != "authenticator" or not status["found"]:
            continue
        keystore = pool.get_foreign_keystore(status["keystore_uid"])
        for key in status["needed_keys"]:
            if key in status["missing_private_keys"]:
                continue
            try:
                pem = keystore.get_private_key(keychain_uid=key["keychain_uid"], key_algo=key["key_algo"])
                load_asymmetric_key_from_pem_bytestring(pem, key_algo=key["key_algo"], passphrase=passphrase)
            except KeyLoadingError:
                continue
            mapper.add(status["trustee_id"], passphrase)
            recognized.append(status["trustee_id"])
            break
    return dict(result="recognized" if recognized else "no_match", trustee_ids=recognized)


# ---------------------------------------------------------------- decryption

class _PrefetchedRequestsDecryptor(CryptainerDecryptor):
    """CryptainerDecryptor using a gateway answer fetched once per batch (OI-72) instead of once per cryptainer."""

    def __init__(self, *args, requests=None, fetch_error=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._requests, self._fetch_error = requests or [], fetch_error

    def _get_multiple_gateway_revelation_request_list(self, gateway_urls, revelation_requestor_uid, operation_report):
        if self._fetch_error:  # Same report entry as the library's own network error
            operation_report.add_entry(
                entry_type=DecryptionErrorType.ASYMMETRIC_DECRYPTION_ERROR,
                entry_message="Unable to reach remote server %s" % gateway_urls[0], entry_exception=self._fetch_error)
        return self._requests


def fetch_revelation_requests(gateway_url, requestor_uid, timeout=GATEWAY_TIMEOUT_S):
    """Returns (requests list, error or None). Network and JSON-RPC errors are returned, not raised (03 §10.7.3)."""
    try:
        proxy = get_gateway_proxy(gateway_url, timeout=timeout)
        return proxy.list_requestor_revelation_requests(revelation_requestor_uid=requestor_uid), None
    except (JSONRPCError, OSError) as exc:
        return [], exc


def _unique_export_path(export_dir: Path, name: str) -> Path:
    path = export_dir / name
    counter = 1
    while path.exists():  # OI-70: never overwrite silently
        counter += 1
        path = export_dir / ("%s_%d%s" % (Path(name).stem, counter, Path(name).suffix))
    return path


def format_operation_report(report: OperationReport) -> str:
    """Text of 04 §13 / 02 §7.2: one block per entry, blank line between, `> ` per nesting level."""
    blocks = []
    for entry in report.get_all_entries():
        if entry["entry_criticity"] == DecryptionErrorCriticity.INFO:
            label = tr._("Info") + tr._(": ") + entry["entry_message"]
        else:
            suffix = " (%s)" % type(entry["entry_exception"]).__name__ if entry["entry_exception"] else ""
            label = (entry["entry_criticity"] + tr._(": ") + entry["entry_type"].replace("_", " ").title() + suffix
                     + "\n" + tr._("Message") + tr._(": ") + entry["entry_message"])
        blocks.append(textwrap.indent(label, "> " * entry["entry_nesting"]))
    return "\n\n".join(blocks)


def decrypt_cryptainers(storage, pool, names, mapper, export_dir, gateway_url, requestor_uid, now=None,
                        timeout=GATEWAY_TIMEOUT_S, write_reports=True) -> list:
    """Decrypt each cryptainer in turn, exporting the plaintext to `export_dir/<name without .crypt>`.
    Always returns one result per name: dict(name, success, report (OperationReport), export_path, report_path).
    Pass `gateway_url=None` to skip the remote retrieval. `now`: UTC datetime for the report file names."""
    export_dir = Path(export_dir)
    now = now or datetime.now(timezone.utc)
    requests, fetch_error = ([], None)
    if gateway_url and requestor_uid:
        requests, fetch_error = fetch_revelation_requests(gateway_url, requestor_uid, timeout)  # Once per batch
    results = []
    for name in names:
        name = str(name)
        result = dict(name=name, success=False, report=OperationReport(), export_path=None, report_path=None)
        results.append(result)
        try:
            cryptainer = storage.load_cryptainer_from_storage(name, include_payload_ciphertext=True)
            decryptor = _PrefetchedRequestsDecryptor(keystore_pool=pool, passphrase_mapper=mapper.as_dict(),
                                                     requests=requests, fetch_error=fetch_error)
            plaintext, report = decryptor.decrypt_payload(
                cryptainer, gateway_urls=[gateway_url] if gateway_url and requestor_uid else None,
                revelation_requestor_uid=requestor_uid if gateway_url else None)
            result["report"] = report
            if plaintext is not None:  # An empty payload is a success (empty file)
                export_dir.mkdir(parents=True, exist_ok=True)
                target = _unique_export_path(export_dir, name[:-len(".crypt")] if name.endswith(".crypt") else name)
                target.write_bytes(plaintext)
                result.update(success=True, export_path=target)
        except Exception as exc:  # OI-69: unreadable JSON, missing payload, unwritable export dir...
            logger.error("Decryption of %s failed unexpectedly: %r", name, exc, exc_info=True)
            result["report"].add_entry(entry_type=DecryptionErrorType.SYMMETRIC_DECRYPTION_ERROR,
                                       entry_criticity=DecryptionErrorCriticity.CRITICAL,
                                       entry_message=str(exc) or type(exc).__name__, entry_exception=exc)
        if write_reports and len(result["report"]):  # OI-71: once, now
            try:
                export_dir.mkdir(parents=True, exist_ok=True)
                report_path = export_dir / ("%s_revelation_report_%s.txt" % (name, now.strftime("%Y%m%d_%H%M%S")))
                report_path.write_text(format_operation_report(result["report"]), encoding="utf8")
                result["report_path"] = report_path
            except OSError as exc:
                logger.error("Could not write the report of %s: %r", name, exc)
    return results
