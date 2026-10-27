"""Cryptainer storage, naming, atomic writes, purge, listing, deletion (03 §7-8, §10.6, 04 §5). GUI-free.

The files stay exactly those of the cryptolib (`<base>.crypt`, `.crypt.payload`, `.crypt~`); only the write
sequence is safer (OI-46): JSON via temp file + fsync + rename, payload fsynced before the final JSON appears.
"""
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wacryptolib.cryptainer import (
    CryptainerEncryptionPipeline, CryptainerStorage, ReadonlyCryptainerStorage, CRYPTAINER_DATETIME_FORMAT,
    gather_trustee_dependencies, get_cryptoconf_summary,
)
from wacryptolib.utilities import dump_to_json_bytes

logger = logging.getLogger(__name__)

PROGRESS_BYTE_THRESHOLD = 100 * 1024  # 03 §6.7: activity notification per ~100 KiB of plaintext
MIN_SANE_CLOCK = datetime(2025, 9, 1, tzinfo=timezone.utc)  # OI-47: before this the clock is obviously wrong
ORPHAN_PAYLOAD_MIN_AGE_S = 3600  # A payload without JSON is only an orphan once creation has surely failed (OI-46)


def build_cryptainer_filename_base(sensor_name, start_datetime, record_extension):
    """`<YYYYmmdd_HHMMSS UTC>_<sensor>_cryptainer<.ext>` (04 §5.3)."""
    assert record_extension.startswith("."), record_extension
    return "%s_%s_cryptainer%s" % (start_datetime.astimezone(timezone.utc).strftime(CRYPTAINER_DATETIME_FORMAT),
                                   sensor_name, record_extension)


def _fsync_path(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path: Path, data: bytes):
    tmp_path = path.with_name(path.name + ".tmp")  # Matches neither "*.crypt" nor "*.crypt~" listings
    with open(tmp_path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


class RecorderEncryptionPipeline(CryptainerEncryptionPipeline):
    """Cryptolib streaming pipeline + atomic JSON writes + progress notifications + discard of empty records."""

    def __init__(self, *args, progress_callback=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._progress_callback = progress_callback
        self._pending_byte_count = 0
        self.plaintext_byte_count = 0
        self._discarded = False

    def encrypt_chunk(self, chunk: bytes):
        self.plaintext_byte_count += len(chunk)
        if self._progress_callback:
            self._pending_byte_count += len(chunk)
            if self._pending_byte_count > PROGRESS_BYTE_THRESHOLD:
                self._pending_byte_count = 0
                self._progress_callback()
        super().encrypt_chunk(chunk)

    def _dump_current_cryptainer_to_filesystem(self, is_temporary):
        if is_temporary:
            _atomic_write(self._cryptainer_filepath_temp, dump_to_json_bytes(self._wip_cryptainer))
            return
        payload_path = self._cryptainer_filepath.with_name(self._cryptainer_filepath.name + ".payload")
        _fsync_path(payload_path)  # The ciphertext is durable before the JSON that references it
        _atomic_write(self._cryptainer_filepath, dump_to_json_bytes(self._wip_cryptainer))
        self._cryptainer_filepath_temp.unlink(missing_ok=True)

    def discard(self):
        """Abandon the record and remove its files (OI-19: no empty cryptainers). Safe to call once."""
        if self._discarded:
            return
        self._discarded = True
        if not self._output_data_stream.closed:
            self._output_data_stream.close()
        for path in (self._cryptainer_filepath_temp, self._cryptainer_filepath,
                     self._cryptainer_filepath.with_name(self._cryptainer_filepath.name + ".payload")):
            path.unlink(missing_ok=True)


class RecorderCryptainerStorage(CryptainerStorage):
    """CryptainerStorage whose purge tolerates concurrent deletions, a wrong clock (OI-47) and orphan payloads."""

    def _delete_cryptainer(self, cryptainer_name):
        try:
            super()._delete_cryptainer(cryptainer_name)
        except FileNotFoundError:  # Purge race with the GUI (03 §9): already gone
            pass

    def _purge_exceeding_cryptainers(self) -> int:
        if datetime.now(timezone.utc) < MIN_SANE_CLOCK:
            logger.error("System clock looks wrong (before %s), cryptainers purge skipped", MIN_SANE_CLOCK.date())
            return 0
        deleted = super()._purge_exceeding_cryptainers()
        return deleted + purge_orphan_payloads(self._cryptainer_dir)


def purge_orphan_payloads(cryptainer_dir: Path, min_age_s=ORPHAN_PAYLOAD_MIN_AGE_S) -> int:
    deleted = 0
    now = datetime.now().timestamp()
    for payload in Path(cryptainer_dir).glob("*.crypt.payload"):
        base = payload.name[:-len(".payload")]
        if (payload.with_name(base).exists() or payload.with_name(base + "~").exists()):
            continue
        try:
            if now - payload.stat().st_mtime > min_age_s:
                logger.info("Deleting orphan payload %s", payload.name)
                payload.unlink()
                deleted += 1
        except FileNotFoundError:
            pass
    return deleted


def open_recording_storage(cryptainer_dir, pool, cryptoconf, max_age_day) -> RecorderCryptainerStorage:
    """The storage of one recording session (03 §4.3.2): one encryption worker, age purge only."""
    return RecorderCryptainerStorage(
        cryptainer_dir=cryptainer_dir, keystore_pool=pool, default_cryptoconf=cryptoconf, max_workers=1,
        max_cryptainer_age=timedelta(days=max_age_day))


def open_management_storage(cryptainer_dir, pool, read_only=True):
    """GUI-side storage; None if the folder is invalid (03 §10.6). It never purges (no limits)."""
    cryptainer_dir = Path(cryptainer_dir)
    if not cryptainer_dir.is_dir():
        return None
    klass = ReadonlyCryptainerStorage if read_only else CryptainerStorage
    return klass(cryptainer_dir=cryptainer_dir, keystore_pool=pool)


def purge_now(cryptainer_dir, pool, max_age_day) -> int:
    """Periodic purge when not recording (OI-45)."""
    if not Path(cryptainer_dir).is_dir():
        return 0
    storage = open_recording_storage(cryptainer_dir, pool, None, max_age_day)
    try:
        return storage.purge_exceeding_cryptainers()
    finally:
        storage._thread_pool_executor.shutdown(wait=False)


# ---------------------------------------------------------------- listing / details / deletion (03 §10.6)

def list_cryptainers(storage) -> list:
    """Finished cryptainers, newest first: dicts name (str), size (int or None if deleted meanwhile),
    creation_datetime (UTC). Numbering from 1 is up to the display (OI-89)."""
    if storage is None:
        return []
    entries = []
    for name in storage.list_cryptainer_names(as_sorted_list=True, finished=True):
        try:
            size = storage._get_cryptainer_size(name)
        except FileNotFoundError:
            size = None
        entries.append(dict(name=str(name), size=size,
                            creation_datetime=storage._get_cryptainer_datetime_utc(name)))
    entries.reverse()
    return entries


def get_cryptainer_details(storage, name) -> dict:
    """Header without the payload (OI-70 part: no full ciphertext load). Raises on unreadable files."""
    cryptainer = storage.load_cryptainer_from_storage(name, include_payload_ciphertext=False)
    dependencies = gather_trustee_dependencies([cryptainer])["encryption"]
    owners = sorted(conf.get("keystore_owner") or "" for conf, _keys in dependencies.values())
    return dict(name=name, cryptainer_uid=cryptainer["cryptainer_uid"], cryptainer_format=cryptainer["cryptainer_format"],
                trustee_owners=owners, summary=get_cryptoconf_summary(cryptainer))


def delete_cryptainers(storage, names) -> int:
    """Remove `.crypt` and `.crypt.payload`; already-missing files are ignored. Returns the deleted count."""
    count = 0
    for name in list(names):
        try:
            storage.delete_cryptainer(name)
            count += 1
        except FileNotFoundError:
            pass
    return count


def get_latest_cryptainer_info(cryptainer_dir):
    """Newest finished cryptainer (by name) and the total count, e.g. for status displays."""
    names = sorted(Path(cryptainer_dir).glob("*.crypt"))
    if not names:
        return None, 0
    newest = names[-1]
    return dict(name=newest.name, size=newest.stat().st_size), len(names)


def get_free_space_info(cryptainer_dir, margin_bytes=None):
    """`dict(free_bytes, total_bytes, full)`: full = free space below the margin (default 200 MiB or 2%), OI-44."""
    usage = shutil.disk_usage(cryptainer_dir)
    margin = margin_bytes if margin_bytes is not None else max(200 * 1024 ** 2, usage.total // 50)
    return dict(free_bytes=usage.free, total_bytes=usage.total, full=usage.free < margin)
