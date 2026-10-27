"""Cryptoconf built from the settings at each recording start (03 §5, 04 §4.3). Byte-compatible with 1.0.

OI-51: only the selected guardians are read. OI-54: only RSA_OAEP keys, `secrets` PRNG, clear error if none.
OI-55 (decide, NOT applied): payload cipher stays AES_CBC for fixture equality; `payload_cipher_algo` can be
changed by the caller (AES_EAX / CHACHA20_POLY1305 are streamable and read by every existing tool).
"""
import secrets

from wacryptolib.cryptainer import check_cryptoconf_sanity

from waflet_components.authenticator_services import ServiceError

KEY_ALGO = "RSA_OAEP"
PAYLOAD_CIPHER_ALGO = "AES_CBC"


class NoEncryptionKeyError(ServiceError):
    msgid = "A selected key guardian has no usable public key"


def build_cryptoconf(threshold, selected_uids, pool, payload_cipher_algo=PAYLOAD_CIPHER_ALGO, choose=secrets.choice):
    """`selected_uids`: UUIDs in selection order (one shard each); `choose(keys)` picks one key per guardian."""
    shards = []
    for uid in selected_uids:
        owner = pool.get_foreign_keystore_metadata(uid)["keystore_owner"]
        keys = [k for k in pool.get_foreign_keystore(uid).list_keypair_identifiers() if k["key_algo"] == KEY_ALGO]
        if not keys:
            raise NoEncryptionKeyError("Key guardian %s (%s) has no %s public key" % (uid, owner, KEY_ALGO))
        key = choose(keys)
        shards.append({"key_cipher_layers": [{
            "key_cipher_algo": key["key_algo"],
            "keychain_uid": key["keychain_uid"],
            "key_cipher_trustee": {"trustee_type": "authenticator", "keystore_uid": uid, "keystore_owner": owner},
        }]})
    conf = {"payload_cipher_layers": [{
        "payload_cipher_algo": payload_cipher_algo,
        "key_cipher_layers": [{
            "key_cipher_algo": "[SHARED_SECRET]",
            "key_shared_secret_threshold": threshold,
            "key_shared_secret_shards": shards,
        }],
        "payload_signatures": [],
    }]}
    check_cryptoconf_sanity(conf)
    return conf
