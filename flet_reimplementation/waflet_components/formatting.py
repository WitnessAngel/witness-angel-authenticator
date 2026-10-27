"""Display helpers shared by all screens (02 §3.3 "Exact formatting functions")."""
from datetime import datetime, timezone
from pathlib import Path
from textwrap import indent

from .i18n import tr

TEXT_INDENT = "    "


def COLON():
    return tr._(": ")


def shorten_uid(uid, prefix="…"):
    return prefix + str(uid).split("-")[-1]


def truncate_chars(string, max_length, suffix="…"):
    return string if len(string) <= max_length else string[:max_length] + suffix


def convert_bytes_to_human_representation(size):
    for unit in ["bytes", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return "%i%s" % (int(size), unit)
        size /= 1024.0
    return "%iTB" % int(size * 1024)


def indent_text(text):
    return indent(text, TEXT_INDENT)


def format_keypair_label(key_algo, keychain_uid, private_key_present=None):
    label = "%s %s" % (key_algo.replace("_", "-"), shorten_uid(keychain_uid))
    if private_key_present is False:
        label += " " + tr._("(missing private key)")
    return label


def format_authenticator_label(owner, keystore_uid):
    return "%s (ID %s)" % (owner or tr._("Unknown"), shorten_uid(keystore_uid))


def format_utc_datetime_label(dt: datetime, show_time=False):
    dt = dt.astimezone(timezone.utc)  # OI-40: a real conversion instead of a debug-only assert
    label = dt.date().isoformat()
    if show_time:
        label += " " + tr._("at") + " " + dt.time().replace(microsecond=0).isoformat() + " UTC"
    return label


def format_revelation_request_label(created_at, description):
    return tr.f(
        'Request "{description}" ({date})',
        description=truncate_chars(description, 40),
        date=format_utc_datetime_label(created_at),
    )


def format_path_for_display(path, home_dir=None, sdcard_prefix=None):
    """02 §7.4: '' stays '', Android external storage becomes <sdcard>/..., home becomes ~/..."""
    if not path:
        return ""
    path = Path(path)
    for root, label in ((sdcard_prefix, "<sdcard>"), (home_dir or Path.home(), "~")):
        if root:
            try:
                return str(Path(label) / path.relative_to(root))
            except ValueError:
                pass
    return str(path)


def format_keypair_label_with_privacy(key_algo, keychain_uid, private_key_present):
    """02 §5.3, §7.1: `RSA-OAEP …a1b2c3d4 (private key present|not present)`."""
    suffix = tr._("(private key present)") if private_key_present else tr._("(private key not present)")
    return "%s %s %s" % (key_algo.replace("_", "-"), shorten_uid(keychain_uid), suffix)


def format_trustee_label(owner, keystore_uid, trustee_type):
    """02 §6.3: `<owner> (ID …<uid>, type <trustee_type>)`."""
    return "%s (ID %s, %s)" % (owner or tr._("Unknown"), shorten_uid(keystore_uid) if keystore_uid else tr._("Unknown"),
                               tr.f("type {trustee_type}", trustee_type=trustee_type))
