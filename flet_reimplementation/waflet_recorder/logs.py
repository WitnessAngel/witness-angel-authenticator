"""Per-process logging (01 §5, OI-48): stderr + one small rotating file per process, UTC, validated level."""
import logging
import logging.handlers
import os
import sys
import time

LOG_FORMAT = "%(asctime)sZ - %(levelname)s - %(message)s"
LOG_MAX_BYTES, LOG_BACKUP_COUNT = 5 * 1024 ** 2, 3  # ~20 MB per process, instead of 2 GB shared (OI-48)


class SafeUtcFormatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record):
        try:
            return super().format(record)
        except Exception:  # Never raise from logging: bad %-arguments
            return "%r -- %r" % (record.msg, record.args)


def resolve_log_level(name=None):
    level = getattr(logging, (name or os.environ.get("WA_LOG_LEVEL", "INFO")).strip().upper(), None)
    return level if isinstance(level, int) else logging.INFO  # An invalid WA_LOG_LEVEL no longer prevents startup


def setup_process_logging(roots, process_name):
    """`process_name`: "service" or "gui" -> `<INTERNAL_APP_ROOT>/logs/<process_name>.log`. Idempotent per process."""
    root = logging.getLogger()
    root.setLevel(resolve_log_level())
    if getattr(root, "_wa_recorder_logging", False):
        return
    formatter = SafeUtcFormatter(LOG_FORMAT)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)
    roots.logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(roots.logs_dir / (process_name + ".log"),
                                                        maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
                                                        encoding="utf8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    root._wa_recorder_logging = True
