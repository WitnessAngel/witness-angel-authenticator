# 04 - Data formats and protocols specification

Witness Angel Authenticator, version 1.5. This file gives the byte-level formats a reimplementation needs to stay compatible with:

- existing authenticator folders (on disk, and in ZIP exports),
- the Witness Angel gateway (JSON-RPC over HTTPS),
- the cryptolib clients on the other side of the protocol (recorders, claimants).

Everything here is language-neutral. The Python code is cited only as evidence. This file owns the folder content, the file and wire formats, and the crypto parameters; storage *locations* are in [01 §4](01-architecture-and-platform.md#4-storage-locations-exact-per-os).

Sibling files: [01](01-architecture-and-platform.md) (storage roots, config file, build), [02](02-ux-and-screens.md) (UI), [03](03-business-logic.md) (rules and state machines; referenced below as "03 §x"), [05](05-open-issues.md) (open issues, `OI-nn`). Citation prefixes and source baseline: [README](README.md#source-baseline-and-citation-prefixes). Normative tags (MUST / SHOULD / INFO): [README](README.md#normative-language).

Worked examples were produced by running the real cryptolib code (`initialize_authenticator`, `generate_keypair`, `FilesystemKeystore`, `encrypt_bytestring`, `TrusteeApi`, `JsonRpcProxy.serialize`). Long base64 values are cut and marked `…`. Complete, untruncated vectors are in [fixtures/](fixtures/) (§10).

Library versions:

- The app pins **pycryptodome 3.20.0** (`AUTH/buildozer.spec:40`).
- The examples in §2-§5 were produced with pycryptodome 4.2.0; the fixtures (§10) with pycryptodome 3.24.1, which has the same defaults as 3.20. The only visible difference is the PBKDF2 iteration count (§4.3).

---

## 0. Normative interop requirements (checklist)

A reimplementation MUST satisfy every line below. Each line links to the section with the details. The fixtures in §10 exercise most of them.

**On disk**

1. MUST find authenticators at the same folder names: `authenticator.keystore`, legacy `.authenticator` on removable drives, legacy `authenticator` in the internal profile (renamed at startup) ([03 §2](03-business-logic.md#2-authenticator-locations)).
2. MUST name key files `<str(UUID) lowercase>_<key_algo>_{public,private}_key.pem`, MUST list them with the regex of §2.1 and skip non-matching names, and MUST sort keypairs by `(keychain_uid as 128-bit int, key_algo)` (§2.1).
3. MUST write `keystore_metadata.json` with exactly the fields of §2.2 (the schema refuses extra keys), and MUST read the legacy `.keystore.json` when `keystore_metadata.json` is absent (§2.1).
4. MUST treat a folder as "initialized" when either metadata file exists, whatever its content (§2.1, [03 §3.1](03-business-logic.md#31-local-authenticator-state)).
5. MUST keep ZIP exports readable by 1.5: entries at the archive root, no folder prefix (§2.4).

**Encodings**

6. MUST read both canonical and relaxed Extended JSON, including pymongo `bson.json_util` CANONICAL output (older authenticators and the gateway use it); SHOULD write canonical (§3).
7. MUST accept any 16-byte value as a UUID (uuid0 has no RFC version bits) (§1).
8. MUST use timezone-aware UTC datetimes; MUST tolerate millisecond truncation (§1, §3.1).

**Keys and crypto**

9. MUST normalise every passphrase as `UTF-8(NFKC(strip(passphrase)))` before using it, on creation, Check and Accept alike. Otherwise existing keys with non-ASCII passphrases do not open (§4.3).
10. MUST generate RSA-2048 (exponent 65537) keypairs with `key_algo = "RSA_OAEP"`; MUST refuse keys under 2048 bits (§4.1).
11. MUST write public keys as SPKI PEM and private keys as PKCS#8 `ENCRYPTED PRIVATE KEY` (PBES2, PBKDF2-HMAC-SHA1, AES-256-CBC) (§4.2, §4.3).
12. MUST read private keys with any PBKDF2 iteration count, and also unencrypted PKCS#1/PKCS#8 keys; MUST report every load failure as "wrong passphrase or corrupted key" (`KeyLoadingError`) (§4.3).
13. MUST implement RSA-OAEP exactly as §5.2: SHA-512 for hash and MGF1, empty label, 60-byte plaintext chunks, `{"ciphertext_chunks": [...]}`, and on read also the legacy key `digest_list`.

**Gateway**

14. MUST call the JSON-RPC methods of §7.3 with **named** parameters only, in an Extended JSON body (§7.1).
15. MUST map error responses through `data.status_slugs` to the deepest known error class (§7.2).
16. MUST NOT send private keys, the passphrase or the passphrase hint to the gateway ([03 §10.3](03-business-logic.md#103-properties-a-reimplementation-must-keep)).
17. For `accept_revelation_request`, MUST send exactly one result per distinct `symkey_decryption_request_data`, MUST echo that value **byte for byte**, and MUST pair status and data as: `DECRYPTED` ⇔ non-empty response data, any other status ⇔ `b""` (§7.3.4).
18. MUST encrypt each revelation response only with `revelation_response_public_key`, using RSA-OAEP as in §5.2; MUST refuse a request whose `revelation_response_key_algo` or target `key_algo` is not `RSA_OAEP` ([05 OI-03](05-open-issues.md#a-revelation-requests-accept--reject)).
19. MUST NOT call `set_public_authenticator` twice for the same `keystore_uid` (it is not idempotent) and MUST NOT publish an authenticator without public keys (§7.3.2).
20. MUST keep `keystore_owner` at 100 code points or fewer (§7.3.2).

---

## 1. Primitive encodings (used everywhere)

| Logical type | Canonical in-memory form | Notes |
|---|---|---|
| UUID | 16 bytes, RFC 4122 byte order (`uuid.bytes`) | Text form: lowercase hyphenated `8-4-4-4-12`. Used in filenames. |
| uuid0 (all generated uids) | 6 bytes big-endian = `floor(unix_time * 10000)` (100 µs units), then 10 bytes from the OS CSPRNG | No RFC version/variant bits are set (`VENDORS/uuid0/core.py:79-87`, `CRYPTO/utilities/time_utils.py:11-22`). Any 16-byte value must be accepted as a UUID. |
| datetime | Timezone-aware instant | Naive datetimes are refused by the schema (`CRYPTO/keystore.py:57`) and by the JSON encoder (`AUTH/extjson.py:227-229`). Serialized with **millisecond** precision (§3). Displayed in UTC ([02 §3.3](02-ux-and-screens.md#33-status-computation-ternary)). |
| bytes | Raw octets | Serialized as base64 (§3) |
| text | Unicode | JSON text is UTF-8. `ensure_ascii` is on, so non-ASCII characters are written as `\uXXXX` escapes. |

---

## 2. On-disk layout of an authenticator

### 2.1 Folder content

The folder name depends on the location ([03 §2](03-business-logic.md#2-authenticator-locations)): `authenticator.keystore`, legacy `.authenticator` on USB drives, legacy `authenticator` in the profile (renamed on startup).

```
authenticator.keystore/
├── keystore_metadata.json                                    # metadata (§2.2)
├── <keychain_uid>_RSA_OAEP_public_key.pem                     # x3 in GUI-created authenticators
└── <keychain_uid>_RSA_OAEP_private_key.pem                    # x3
```

| File | Rule | Evidence |
|---|---|---|
| `keystore_metadata.json` | Current metadata file name | `CRYPTO/keystore.py:112-116` |
| `.keystore.json` | **Legacy** metadata file name. Read only if `keystore_metadata.json` is missing. Its presence also counts as "initialized". | `CRYPTO/keystore.py:98-107`, `:119-123`, `CRYPTO/authenticator.py:83-88` |
| `<uid>_<ALGO>_public_key.pem` | `uid` = `str(UUID)`, lowercase hyphenated; `ALGO` = `RSA_OAEP` | `CRYPTO/keystore.py:404-419` |
| `<uid>_<ALGO>_private_key.pem` | Same naming. Present only together with its public file. | same |
| `free_keys/<ALGO>/<10-11 digit random>_{public,private}_key.pem` | Pre-generated key pool of the generic `FilesystemKeystore`. **Not used** by authenticators. A reimplementation may ignore it. | `CRYPTO/keystore.py:526-589` |

Listing rules, MUST (`CRYPTO/keystore.py:406, 439-477`; exercised by `fixtures/edge_cases.keystore`):

- Enumerate `*_public_key.pem` with the regex `^(?P<keychain_uid>[-0-9a-z]+)_(?P<key_algo>[_a-zA-Z]+)_public_key.pem$`.
- Skip a file, with a warning, if its name does not match or its uid does not parse as a UUID. Uppercase hex uids are therefore skipped.
- `private_key_present` is true if the sibling file with suffix `_private_key.pem` exists.
- Results are sorted by `(keychain_uid, key_algo)`, with UUIDs compared as 128-bit integers (`:192-194`).

Write order for a keypair: public file first, then private file (`CRYPTO/keystore.py:231-233`). Files are written in place: no temp file, no fsync, no explicit permissions (default umask).

### 2.2 `keystore_metadata.json` schema

Validated by `KEYSTORE_METADATA_SCHEMA` (`CRYPTO/keystore.py:52-64`). Extra keys are **refused**: python-schema dicts are closed by default.

| Field | Type (decoded) | Required | Encoding on disk | Constraints / meaning |
|---|---|---|---|---|
| `keystore_type` | string | yes | plain string | `"authenticator"` (the schema also allows `"keyfactory"` for other keystores) |
| `keystore_format` | string | yes | plain string | exactly `"keystore_1.0"` (`KEYSTORE_FORMAT`, `:50`) |
| `keystore_uid` | UUID | yes | `{"$binary":{"base64":…,"subType":"04"}}` | uuid0, the identity of the authenticator, published |
| `keystore_owner` | string | yes | plain string | non-empty. GUI: stripped, ≤100 chars. Gateway column max 100. |
| `keystore_creation_datetime` | datetime | no ("recent field") | `{"$date":{"$numberLong":"<ms>"}}` | tz-aware UTC at creation |
| `keystore_secret` | string | no ("recent field") | plain string | `token_urlsafe(64)`: 86 chars `[A-Za-z0-9_-]`. Gateway bearer credential ([03 §1](03-business-logic.md#1-domain-concepts)). |
| `keystore_passphrase_hint` | string | no (schema) / yes (authenticator) | plain string | non-empty if present. Readers MUST tolerate its absence, and the absence of `keystore_secret` ([05 OI-17](05-open-issues.md#c-local-storage-import-export-destroy)). |

The schema only accepts decoded native types (UUID, datetime). The file is first parsed with Extended JSON (§3) and then validated.

Byte-exact example (a real file: one line, keys sorted, `", "` and `": "` separators, no trailing newline):

```json
{"keystore_creation_datetime": {"$date": {"$numberLong": "1792875147037"}}, "keystore_format": "keystore_1.0", "keystore_owner": "Jane Doe", "keystore_passphrase_hint": "my cat name twice", "keystore_secret": "HZ8S0eU27Z_bDZtBw_cGtmqi59Ya8EQv8zTyQ9hdJ6jSXhbAZN2SVZ-0sU74ee4IjQF5wPMUYyjpPdrkJ8dKoA", "keystore_type": "authenticator", "keystore_uid": {"$binary": {"base64": "EE5c3NclBJg7czxGtRnIQQ==", "subType": "04"}}}
```

Here `keystore_uid` = `104e5cdc-d725-0498-3b73-3c46b519c841`. A reader MUST also accept the relaxed forms (§3.3), for example `{"$uuid":"104e5cdcd72504983b733c46b519c841"}` and `{"$date":"2026-10-24T20:52:27.037Z"}`.

### 2.3 Keystore tree (in-memory export/import format)

This format is used when importing authenticators into other apps' keystore pools. The authenticator app itself does not use it, but a reimplementation might. Schema `KEYSTORE_TREE_SCHEMA` = the metadata fields plus:

```
"keypairs": [ { "keychain_uid": UUID, "key_algo": <one of SUPPORTED_CIPHER_ALGOS>, "public_key": bytes (PEM), "private_key": bytes (PEM) | null } ]
```

(`CRYPTO/keystore.py:66-78`, export `:486-515`, import `:602-641`). When it is imported as a *foreign* keystore, `keystore_secret` and `keystore_passphrase_hint` are removed first (`CRYPTO/authenticator.py:21`, `CRYPTO/operations.py:165-168`).

### 2.4 ZIP export archive

- Format: standard ZIP, DEFLATE (method 8). Entries are the folder's files at the archive root, with no directory prefix. Subfolders would be included with relative paths (`shutil.make_archive(root_dir=authenticator_dir)`, `COMP/screens/authenticator_management.py:430-432`).
- Example entries: `104e5cdc-…_RSA_OAEP_private_key.pem`, `104e5cdc-…_RSA_OAEP_public_key.pem`, `keystore_metadata.json`.
- Name: `authenticator_id<last hyphen group of keystore_uid>_date<UTC %Y%m%d%H%M%S>.zip`, in `<EXTERNAL_APP_ROOT>/exports/` (`authenticator_management.py:420-431`, `COMP/default_settings.py:129`).
- Import extracts all entries into the selected authenticator folder (`authenticator_management.py:390`). See [03 §8](03-business-logic.md#8-export-import-deletion) and [05 OI-20](05-open-issues.md#c-local-storage-import-export-destroy).
- INFO: 1.5 extracts every entry and its listing skips non-matching names, so extra files in an archive are harmless to it.

### 2.5 App configuration

The INI file contains `[authenticator] custom_authenticator_dir` (absolute path or empty) and `[network] wagateway_url` (default `https://api.witnessangel.com/gateway/jsonrpc/`) (`AUTH/waauthenticator/config_defaults.ini:1-7`, `AUTH/waauthenticator/waauthenticator_gui.py:87-112`). File location, handling and the migration rule for `custom_authenticator_dir`: [01 §3](01-architecture-and-platform.md#3-configuration-framework-neutral) and [01 §4.4](01-architecture-and-platform.md#44-folder-access-requirement-level). INFO: the config file is private to the app; it is not an interop surface.

---

## 3. Serialization: Extended JSON ("extjson")

All JSON written by the cryptolib (metadata files, JSON-RPC bodies, ciphertext dicts nested in bytes) goes through one Extended JSON codec. The format is MongoDB Extended JSON v2. Three implementations matter:

| Codec | Used by | Default mode |
|---|---|---|
| vendored `extjson` module: `AUTH/extjson.py` (untracked, "VENDORED FROM witness-angel-cryptolib", shipped in the 1.5 AAB as top-level `extjson.pyc`), same code as `VENDORS/extjson.py` | the 1.5 app (cryptolib branch `poc/pure-python-crypto-utils`, re-exported by `CRYPTO/utilities/__init__.py:9-10`) | canonical (`dumps(..., canonical=True)`, `AUTH/extjson.py:104-110`) |
| pymongo `bson.json_util` with `JSONMode.CANONICAL`, `UuidRepresentation.STANDARD`, `tz_aware=True` | **the gateway** (it pins cryptolib branch `waserver_stable`, `witness-angel-server/pyproject.toml:33`), and every app built on `wakeygen_stable` or older, so most existing authenticator folders | canonical (`git show waserver_stable:src/wacryptolib/utilities.py`, lines 24-28) |
| upstream ExtJson 0.2.0 (`../ExtJson/extjson.py`) | nothing shipped | relaxed |

The two canonical writers produce **identical bytes** for every type in this data model (checked on bytes, UUID, aware datetime, int32, int64 and non-ASCII text, with pymongo 4.13.2). So the gateway's JSON-RPC responses and older metadata files have exactly the layout described below.

Requirements:

- Readers MUST accept pymongo `json_util` CANONICAL output: older authenticators (pre-POC builds) and every gateway response are written by it.
- Readers MUST accept the relaxed forms (§3.3) too.
- Parsing strictness is the codec's own. pymongo also accepts the legacy `{"$binary": "<b64>", "$type": "00"}` form and wrappers this app never uses (`$oid`, `$regex`…); the vendored parser does not. Only the forms of §3.1-§3.3 are ever produced by Witness Angel code.
- Error type on invalid JSON (INFO): the vendored codec raises `JSONDecodeError` (or `TypeError` for a bad wrapper); the pymongo-based cryptolib raises `SchemaValidationError`. A reimplementation should report both as "invalid data" ([05 OI-18](05-open-issues.md#c-local-storage-import-export-destroy)).

### 3.1 Writer (canonical mode, what the app emits)

Encoders are chosen by exact Python type first, then by `isinstance` (`AUTH/extjson.py:144-164`, `:255-265`):

| Native type | Emitted JSON |
|---|---|
| `dict` | object. Values are converted recursively. Keys must be strings. |
| `list`, `tuple` | array, converted recursively |
| `str`, `bool`, `null` | unchanged (`bool` is checked before `int`) |
| `bytes` | `{"$binary": {"base64": "<RFC 4648 std alphabet, padded, no newlines>", "subType": "00"}}` |
| `UUID` | `{"$binary": {"base64": "<base64 of 16 bytes>", "subType": "04"}}` |
| aware `datetime` | `{"$date": {"$numberLong": "<floor(epoch_ms)>"}}`. Sub-millisecond precision is **lost**. |
| `int` with -2^31 ≤ n < 2^31 | `{"$numberInt": "<decimal>"}` |
| other `int` | `{"$numberLong": "<decimal>"}` |
| `float` | `{"$numberDouble": "<repr>"}`, or `"NaN"`, `"Infinity"`, `"-Infinity"` |
| `Decimal` | `{"$numberDecimal": "<str>"}` |

Text layout: `json.dumps(obj, sort_keys=True)` with Python defaults: separators `", "` and `": "`, `ensure_ascii=True`, no indentation, no trailing newline. Then UTF-8 encoding (`AUTH/extjson.py:46-92`).

**Byte-exactness matters in one place only:** `symkey_decryption_request_data` is compared byte-for-byte by the gateway and the claimant ([03 §7.3](03-business-logic.md#73-accept-the-decryption-algorithm)). The authenticator MUST NOT re-serialize it; it echoes the received bytes. Everywhere else, any semantically equal JSON is accepted.

Worked example. `dump_to_json_bytes({"d": datetime(2024,5,1,12,0,0,123000,UTC), "n": 5, "big": 2**40})` gives:

```json
{"big": {"$numberLong": "1099511627776"}, "d": {"$date": {"$numberLong": "1714564800123"}}, "n": {"$numberInt": "5"}}
```

### 3.2 Reader

`loads` parses standard JSON, then walks the tree **bottom-up**. Any object with **exactly one key**, where that key is one of `$date`, `$binary`, `$uuid`, `$undefined`, `$numberInt`, `$numberLong`, `$numberDouble`, `$numberDecimal`, is replaced by the native value (`AUTH/extjson.py:167-190`, `:347-357`). Other objects are left as they are.

| Wrapper | Accepted value | Result |
|---|---|---|
| `$binary` | an object with exactly the keys `base64` (string) and `subType` (string of ≤2 hex chars) | subType `0` → bytes; `4` → UUID from 16 bytes; anything else → `TypeError` (`:270-290`) |
| `$uuid` | a string accepted by `UUID(str)`: 32 hex chars, hyphens and braces allowed | UUID (`:340-344`) |
| `$date` | int (epoch ms, already decoded from `$numberLong`) or an ISO-8601 string **with** an offset | aware datetime. Ints decode as UTC. ISO strings keep their offset. Naive → `TypeError` (`:293-306`) |
| `$numberInt` / `$numberLong` | decimal string | int |
| `$numberDouble` | string | float |
| `$numberDecimal` | string | Decimal |
| `$undefined` | anything | null |

Because decoding is bottom-up, a canonical `{"$date":{"$numberLong":"…"}}` first turns its inner object into an int, and then the `$date` wrapper turns that int into a datetime.

Ambiguity a reimplementation MUST copy: a user-level dict that has a single key such as `$date` is indistinguishable from a wrapper. No such dicts exist in the authenticator data model.

### 3.3 Relaxed mode

The upstream ExtJson 0.2.0 package (`../ExtJson/extjson.py:380`) defaults to `canonical=False`. In that mode it emits `{"$uuid":"<32 hex>"}`, `{"$date":"YYYY-MM-DDTHH:MM:SS[.mmm]Z"}` and plain ints, while bytes stay `$binary` subtype 00 (`AUTH/extjson.py:227-248`). The cryptolib's own extended-JSON micro-schemas say "RELAXED is the default and expected format" (`CRYPTO/utilities/validation_utils.py:29-61`). Readers MUST accept **both** modes. Writers SHOULD keep the canonical mode, for compatibility with older readers ([05 OI-34](05-open-issues.md#e-data-formats-and-crypto)).

---

## 4. Asymmetric keys

### 4.1 Algorithms used by the authenticator

| Purpose | `key_algo` | Parameters | Evidence |
|---|---|---|---|
| Authenticator keypairs | `RSA_OAEP` | RSA, 2048-bit modulus, public exponent 65537 (pycryptodome `RSA.generate` default). The minimum accepted anywhere is 2048. | `CRYPTO/keygen.py:56-101`, `:129-139`, `:192-195`, `CRYPTO/_crypto_backend/pycryptodome.py:321-326` |
| Claimant's one-time response key (input to the authenticator) | `RSA_OAEP` | Same generation, private key **unprotected**, kept in the claimant's local keyfactory | `COMP/screens/claimant_revelation_request_creation_form.py:92-103` |

Other algorithms in the registry, not used by authenticators: `RSA_PSS`, `DSA_DSS`, `ECC_DSS` (curve p521 by default). Their private-key protections differ: DSA uses PBKDF2-HMAC-SHA1 + 3DES-CBC, ECC uses PBKDF2-HMAC-SHA1 + AES-128-CBC (`CRYPTO/keygen.py:204-231`, `CRYPTO/_crypto_backend/pycryptodome.py:372-383`).

### 4.2 Public key PEM

- DER `SubjectPublicKeyInfo` (algorithm OID rsaEncryption `1.2.840.113549.1.1.1`, NULL parameters), wrapped in PEM label `PUBLIC KEY`.
- 64-character base64 lines, LF line endings, **no trailing newline** (verified on the fixtures: the last byte is the final `-`). About 450 bytes for RSA-2048.
- This exact byte string is both the file content and the `key_value` sent to the gateway.
- Readers MUST accept PEM with or without a trailing newline (and with CRLF line endings). Writers SHOULD write it without. No component compares PEM bytes: the gateway stores `key_value` as given, and the publication check compares only `(keychain_uid, key_algo)`.

```
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtHrjVacMhHXPbyrPBh5u
…
JwIDAQAB
-----END PUBLIC KEY-----
```

### 4.3 Private key PEM (passphrase-protected)

Produced by `RsaKey.export_key(format="PEM", passphrase=<bytes>, pkcs=8, protection="PBKDF2WithHMAC-SHA1AndAES256-CBC")` (`CRYPTO/_crypto_backend/pycryptodome.py:365-369`).

| Layer | Value |
|---|---|
| PEM label | `ENCRYPTED PRIVATE KEY`. 64-char lines, LF, no trailing newline (same reader rule as §4.2). 1857 bytes for RSA-2048 with 1000 iterations. |
| Outer DER | PKCS#8 `EncryptedPrivateKeyInfo` |
| Encryption scheme | PBES2 (OID `1.2.840.113549.1.5.13`) |
| KDF | PBKDF2 (OID `1.2.840.113549.1.5.12`). PRF is HMAC-SHA1, the default, so no PRF field is encoded. |
| Salt | 8 random bytes (pycryptodome default `salt_size`) |
| Iteration count | Not set by wacryptolib, so the library default applies. **1000** (`INTEGER 0x03E8`) with pycryptodome 3.20.0 (the app pin; `Crypto/IO/_PBES.py:322`) and up to 3.24.1 (the fixtures). **600000** with pycryptodome 4.2.0 (observed: `INTEGER 0x0927C0`). Writers SHOULD pin a value explicitly ([05 OI-14](05-open-issues.md#b-creation-check-passphrase)). |
| Derived key length | 32 bytes |
| Cipher | AES-256-CBC (OID `2.16.840.1.101.3.4.1.42`), 16-byte random IV, PKCS#7 padding |
| Plaintext | PKCS#8 `PrivateKeyInfo` holding a PKCS#1 `RSAPrivateKey` |
| Passphrase bytes | **MUST** be `UTF-8(NFKC(strip(passphrase)))` (`CRYPTO/keygen.py:16-18`), applied by the key layer on every generate *and* load, whatever the screen passed. `strip()` removes Unicode whitespace at both ends (Python `str.strip()` semantics). An empty result is refused at export (`:176-178`). Test vector: `fixtures/passphrase.json`. |

ASN.1 dump of a real file (`openssl asn1parse`):

```
SEQUENCE
  SEQUENCE
    OBJECT  :PBES2
    SEQUENCE
      SEQUENCE
        OBJECT :PBKDF2
        SEQUENCE
          OCTET STRING  2D11D4AB24A39B71          # salt (8 bytes)
          INTEGER       :0927C0                   # 600000 here (pycryptodome 4.x); 1000 with 3.20
      SEQUENCE
        OBJECT :aes-256-cbc
        OCTET STRING  56D1C33E675DCF795FE8A05CA4C738AA   # IV
  OCTET STRING  [1232 bytes ciphertext]
```

The file can be checked with `openssl pkcs8 -in <file> -passin pass:<passphrase>`.

Reader requirements:

- Load with pycryptodome-equivalent `import_key(pem, passphrase)`. Accept any PBES2/PBKDF2 iteration count, and also unencrypted PKCS#1 (`RSA PRIVATE KEY`) and PKCS#8 keys, because `TrusteeApi` tries "no passphrase" first (`CRYPTO/trustee.py:94`).
- Note: recent pycryptodome versions (3.24 already) check a *maximum* iteration count on decryption (`_DEFAULT_MAX_ITERATION_COUNT = 50000000`); 3.21 and older have no limit. Keys made with 1000 or 600000 iterations are under any limit.
- Any parse or decrypt failure must be reported as `KeyLoadingError` (`CRYPTO/keygen.py:120-126`).

The claimant's *unprotected* response private key (not handled by the authenticator) is exported as PKCS#1 `-----BEGIN RSA PRIVATE KEY-----`.

---

## 5. Ciphers and payload formats

### 5.1 Symmetric ciphers (context only)

The authenticator never uses symmetric ciphers directly. It handles symkeys as opaque bytes. For reference, the key dicts that end up inside `key_struct_bytes` are:

| `cipher_algo` | Key dict | Mode details | Evidence |
|---|---|---|---|
| `AES_CBC` | `{key: 32 bytes, iv: 16 bytes}` | PKCS#7 padding, block 16 | `CRYPTO/keygen.py:38-41`, `CRYPTO/_crypto_backend/pycryptodome.py:205-223` |
| `AES_EAX` | `{key: 32 bytes, nonce: 16 bytes}` | 16-byte tag, stored separately (`{"ciphertext","tag"}`) | `CRYPTO/keygen.py:44-47`, `pycryptodome.py:229-247` |
| `CHACHA20_POLY1305` | `{key: 32 bytes, nonce: 12 bytes}` | 16-byte tag, no AAD | `CRYPTO/keygen.py:50-53`, `pycryptodome.py:253-273` |

Example of a serialized symkey, as it travels as `key_struct_bytes` (176 bytes):

```json
{"key": {"$binary": {"base64": "YtMqf/ShofOohxbc5BLA/akmw+LmxIQiHH7ntG3SE2Q=", "subType": "00"}}, "nonce": {"$binary": {"base64": "34nNyLtUUQtUvDW/L51drg==", "subType": "00"}}}
```

If the cryptainer uses a Shamir shared secret, the plaintext is instead the Extended-JSON encoding of a shard. If key layers are nested, it is an intermediate key ciphertext (`CRYPTO/cryptainer/_decryptor.py:520-556`). The authenticator does not need to know which.

### 5.2 RSA-OAEP chunked encryption (the format the authenticator decrypts and produces)

`encrypt_bytestring(plaintext, cipher_algo="RSA_OAEP", key_dict={"key": <RSA public key>})` (`CRYPTO/cipher.py:52-65`, `:211-226`):

1. Check key size ≥ 2048 bits.
2. Split the plaintext into consecutive **60-byte** chunks (`RSA_OAEP_CHUNKS_SIZE = 60`, `CRYPTO/cipher.py:24`). The last chunk may be shorter. No padding. An empty plaintext gives zero chunks (`CRYPTO/utilities/data_utils.py:89-114`).
3. Encrypt each chunk separately with RSAES-OAEP (PKCS#1 v2.x):
   - hash = **SHA-512**
   - MGF1 with **SHA-512**
   - label = empty
   
   (`CRYPTO/_crypto_backend/pycryptodome.py:279-291`). Each ciphertext chunk is exactly `k` bytes, where `k` is the modulus length (256 bytes for RSA-2048).
4. Result (the "cipherdict"): `{"ciphertext_chunks": [chunk_1, …, chunk_n]}`, each chunk as bytes.

Decryption (`CRYPTO/cipher.py:229-248`):

- Read `digest_list` if present (legacy name), else `ciphertext_chunks`.
- Decrypt each chunk with OAEP-SHA512 and concatenate in order.
- A `ValueError` becomes `DecryptionError`.

There is no MAC and nothing binds the chunks together: reordering or dropping chunks is not detected at this layer ([05 OI-37](05-open-issues.md#e-data-formats-and-crypto)).

Serialized cipherdict, i.e. `symkey_decryption_request_data` / `symkey_decryption_response_data`. It is the Extended-JSON bytes of the dict above. Real example: a 176-byte symkey gives 3 chunks of 256 bytes, and the serialized bytes are 1193 long:

```json
{"ciphertext_chunks": [{"$binary": {"base64": "kuf4oKbzrQIfyO736PwQDxKlVy//3y15dQVMCFOYdqwihYxUfbKERBLZw3vGv0BULOiAKw6hDFXdV+8pxj1UuB8Ji98jxu/DtT7ILnSR2bL5Uel4F…", "subType": "00"}}, {"$binary": {…}}, {"$binary": {…}}]}
```

### 5.3 Authenticator processing of one symkey request (exact pipeline)

```
request_data (bytes, from gateway)
  └─ ExtJSON.load ─> {"ciphertext_chunks":[c1..cn]}
       └─ for each ci: RSA-OAEP-SHA512 decrypt with authenticator private key[keychain_uid]
            (private key = PKCS#8 decrypt of <keychain_uid>_RSA_OAEP_private_key.pem with passphrase)
       └─ plaintext = c1' || … || cn'                    (= key_struct_bytes, opaque)
  └─ split plaintext into 60-byte chunks
       └─ each: RSA-OAEP-SHA512 encrypt with revelation_response_public_key (PEM, SubjectPublicKeyInfo)
  └─ response_data = ExtJSON.dump_bytes({"ciphertext_chunks":[r1..rm]})
result = {"symkey_decryption_request_data": request_data (unchanged),
          "symkey_decryption_response_data": response_data,
          "symkey_decryption_status": "DECRYPTED"}
```

Evidence: `COMP/screens/authenticator_revelation_request_detail.py:202-240`, `CRYPTO/trustee.py:192-230`. The claimant side reverses the last step with its response private key (`CRYPTO/cryptainer/_decryptor.py:146-215`).

---

## 6. Schema validation summary

| Schema | Where | Applied to | Evidence |
|---|---|---|---|
| `KEYSTORE_METADATA_SCHEMA` | client | the metadata dict, after Extended-JSON decoding, at creation and at every load | `CRYPTO/keystore.py:52-64`, `:81-109`, `CRYPTO/authenticator.py:66` |
| `KEYSTORE_TREE_SCHEMA` | client | keystore tree export/import. `key_algo` is checked against `SUPPORTED_CIPHER_ALGOS` = `AES_CBC`, `AES_EAX`, `CHACHA20_POLY1305`, `RSA_OAEP` ([05 OI-38](05-open-issues.md#e-data-formats-and-crypto)). | `CRYPTO/keystore.py:66-78`, `CRYPTO/cipher.py:471-502` |
| `PUBLIC_AUTHENTICATOR_SCHEMA` | gateway | `set_public_authenticator` params | `SERVER/apps/wagateway/core.py:369-386` |
| `REVELATION_REQUEST_INPUT_PARAMETERS_SCHEMA` | gateway | `submit_revelation_request` params | `SERVER/apps/wagateway/core.py:348-367` |
| inline schemas | gateway | `get_public_authenticator`, `list_*`, `reject_*`, `accept_*` params | `SERVER/apps/wagateway/core.py:65-68`, `:184-187`, `:199-205`, `:220-225`, `:246-270` |
| micro-schemas | both | `schema_uid` / `schema_binary` / `schema_int`, for native types or for Extended-JSON wrappers | `CRYPTO/utilities/validation_utils.py:24-70` |

The library is python-`schema` 0.7.x (vendored). A violation becomes `SchemaValidationError` (`CRYPTO/utilities/validation_utils.py:14-21`). The gateway validates *decoded* values (`extended_json_format=False`, `SERVER/apps/wagateway/core.py:346`). Field types must therefore decode to the expected native types: UUID, bytes, aware datetime.

---

## 7. Gateway JSON-RPC protocol

### 7.1 Transport

| Aspect | Value | Evidence |
|---|---|---|
| Endpoint | the configured `wagateway_url`, default `https://api.witnessangel.com/gateway/jsonrpc/` (server route `gateway/` + `jsonrpc/`) | `AUTH/waauthenticator/config_defaults.ini:7`, `SERVER/urls.py:21`, `SERVER/apps/wagateway/urls.py:11` |
| HTTP method and headers | `POST`, headers `Content-Type: application/json`, `Accept: application/json-rpc`, plus the `requests` defaults (`User-Agent: python-requests/2.32.3`, `Accept-Encoding: gzip, deflate`, `Connection: keep-alive`). The gateway ignores all of them; a reimplementation is free to send its own User-Agent. | `jsonrpc_requests/jsonrpc.py:40-47` |
| Body | The ASCII bytes of the Extended JSON text (`ensure_ascii`), so the charset question never arises. | `CRYPTO/jsonrpc_client.py:63-66` |
| Session | A new proxy, hence a new `requests.Session` (no connection reuse between operations), is created for every gateway operation, from the URL read from config at that moment. | `COMP/application/_common_runtime_support.py:192-195` |
| Timeout | 10 s, applied by `requests` **separately** to the connect phase and to each socket read (not a total deadline). | `CRYPTO/jsonrpc_client.py:17, 58-59` |
| Retries | None (`requests` default adapter, 0 retries). A failure is reported at once. | - |
| TLS | Certificate verification on (`requests` default `verify=True`), with the CA bundle of the `certifi` package (pinned `certifi==2024.7.4` on Android). There is no certificate pinning. A reimplementation MUST verify certificates against a public CA store. | `AUTH/buildozer.spec:40` |
| Redirects | Followed (`requests` default, up to 30). INFO: on 301/302/303 `requests` re-sends as **GET** without body, which the gateway answers with an error, so a redirected URL does not work in practice. Configure the final URL. | - |
| Proxies | Honoured from the environment (`HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`) on desktop; there is no proxy setting in the app. | - |
| HTTP status | Any status other than 200 raises `TransportError("Got non-200 response from server, status code: …")`. A connection, DNS, TLS or timeout failure raises `TransportError("Error calling method …")`. Both are `JSONRPCError` subclasses. | `jsonrpc_requests/jsonrpc.py:52-62` |
| Envelope | JSON-RPC 2.0: `{"jsonrpc":"2.0","method":…,"params":{…},"id":…}`; `params` is omitted when there are no parameters. The **whole envelope** is Extended JSON, so the random id (1 … `sys.maxsize`, i.e. 2^63-1 on 64-bit, 2^31-1 on 32-bit ARM) goes out as `{"$numberLong":"…"}` (or `$numberInt` when it fits in 32 bits). The gateway decodes requests and encodes responses with pymongo `bson.json_util` CANONICAL (its cryptolib branch `waserver_stable`, see §3), monkey-patched into django-jsonrpc; its responses carry `Content-Type: application/json`. | `CRYPTO/jsonrpc_client.py:63-75`, `jsonrpc_requests/jsonrpc.py:89-96`, `SERVER/utils.py:40-46, 65-68` |
| Parameters | **By name only.** The gateway rejects positional params with `ValidationError` ("must be passed as keyword arguments"), and unknown or missing params with `ValidationError` ("Incorrect input arguments"). The client never unpacks a single dict argument. | `SERVER/utils.py:98-115`, `CRYPTO/jsonrpc_client.py:83-97` |
| Success | HTTP 200, `{"jsonrpc":"2.0","id":…,"result":<value>}` | django-jsonrpc |

Example request body, byte-exact form from `JsonRpcProxy.serialize`:

```json
{"id": {"$numberLong": "5776600559367167158"}, "jsonrpc": "2.0", "method": "accept_revelation_request", "params": {"authenticator_keystore_secret": "SECRET", "revelation_request_uid": {"$binary": {"base64": "EE5c3PPk6ZDZdXkzP1UeAA==", "subType": "04"}}, "symkey_decryption_results": [{"symkey_decryption_request_data": {"$binary": {"base64": "YWI=", "subType": "00"}}, "symkey_decryption_response_data": {"$binary": {"base64": "Y2Q=", "subType": "00"}}, "symkey_decryption_status": "DECRYPTED"}]}}
```

### 7.2 Errors

**Functional errors** (any `wacryptolib.exceptions.FunctionalError` raised by the gateway) come back as HTTP **200** with:

```json
{"jsonrpc": "2.0", "id": …,
 "error": {"name": "Error", "code": 400,
           "message": "Error: Server-side exception occurred, see error data for details",
           "data": {"status_slugs": ["wacryptolib.exceptions.FunctionalError",
                                     "wacryptolib.exceptions.ExistenceError",
                                     "wacryptolib.exceptions.KeystoreDoesNotExist"],
                    "data": null, "message_translated": null,
                    "message_untranslated": "Authenticator … does not exist in database"}}}
```

(`SERVER/utils.py:83-95`; `name`/`message` layout from django-jsonrpc `Error.json_rpc_format`.)

- `status_slugs` lists the exception's MRO from the most generic to the most specific. It excludes `object`, `BaseException` and `Exception`. Each entry is the fully qualified class name (`CRYPTO/error_handling.py:42-61`).
- The client walks a tree built from all builtin exceptions plus the `FunctionalError` subclasses. It raises the deepest known class, with `message_untranslated` as its message, or `Exception` if nothing matches (`CRYPTO/jsonrpc_client.py:19-39`, `CRYPTO/error_handling.py:91-110`).
- An error without `data` is re-raised as `jsonrpc_requests.ProtocolError`.

**Unexpected server errors** become django-jsonrpc `OtherError` (code 500, HTTP **500**). The client then raises `jsonrpc_requests.TransportError("Got non-200 response…")`. Connection failures also raise `TransportError`. Both are subclasses of `JSONRPCError`, which the UI catches next to `OSError` ([03 §7.2](03-business-logic.md#72-fetching-and-classifying-requests)).

Exception classes and their slugs (all prefixed `wacryptolib.exceptions.`):

| Class | Full slug path |
|---|---|
| `KeystoreDoesNotExist` | `FunctionalError` › `ExistenceError` › `KeystoreDoesNotExist` |
| `KeystoreAlreadyExists` | `FunctionalError` › `ExistenceError` › `KeystoreAlreadyExists` |
| `KeyDoesNotExist` | `FunctionalError` › `ExistenceError` › `KeyDoesNotExist` |
| `ExistenceError` | `FunctionalError` › `ExistenceError` |
| `AuthenticationError` | `FunctionalError` › `AuthenticationError` |
| `ValidationError` | `FunctionalError` › `ValidationError` |
| `SchemaValidationError` | `FunctionalError` › `ValidationError` › `SchemaValidationError` |

### 7.3 Methods used by the authenticator

All parameter types below are the *decoded* types. On the wire they use the §3 encodings.

#### 7.3.1 `get_public_authenticator`

| | |
|---|---|
| Caller | Publish screen status check (`COMP/screens/authenticator_publication_form.py:45`) |
| Params | `keystore_uid`: UUID; `keystore_secret`: str or null (optional, **not sent** by the app) |
| Result | `{"keystore_uid": UUID, "keystore_owner": str, "keystore_creation_datetime": datetime or null, "public_keys": [{"keychain_uid": UUID, "key_algo": str, "key_value": bytes (public PEM)}]}` (`SERVER/apps/wagateway/serializers.py:61-78`) |
| Errors | `KeystoreDoesNotExist` (unknown uid); `AuthenticationError` (wrong secret, if one is given); `SchemaValidationError` |
| Side effect | increments the retrieval counter (`SERVER/apps/wagateway/core.py:75-76`) |

#### 7.3.2 `set_public_authenticator`

| | |
|---|---|
| Caller | Publish button (`COMP/screens/authenticator_publication_form.py:221-245`) |
| Params | `keystore_uid`: UUID; `keystore_owner`: non-empty str, which the client MUST keep at ≤100 code points (the gateway schema does not check the length; with its default SQLite database a longer value is stored as is, with a strict SQL backend the call would fail with HTTP 500 → `TransportError`; [05 OI-31](05-open-issues.md#d-publication)); `keystore_secret`: non-empty str; `public_keys`: **non-empty** list of `{keychain_uid: UUID, key_algo: one of SUPPORTED_CIPHER_ALGOS, key_value: bytes}`; `keystore_creation_datetime`: aware datetime or null (optional; the app omits it when it is absent locally) |
| Result | `null` |
| Errors | `KeystoreAlreadyExists` (uid already published: **not idempotent**); `SchemaValidationError`; `ValidationError` (bad arguments) |
| Server storage | secret hashed with Django `make_password` (`SERVER/apps/wagateway/models.py:48-56`) |

Example params as sent (decoded view):

```
{"keystore_owner": "Jane Doe",
 "keystore_uid": UUID("104e5cdc-d725-0498-3b73-3c46b519c841"),
 "keystore_secret": "HZ8S0eU27Z_…",
 "keystore_creation_datetime": 2026-10-24T20:52:27.037+00:00,
 "public_keys": [{"keychain_uid": UUID("104e5cdc-f3e4-e990-d975-79333f551e00"),
                  "key_algo": "RSA_OAEP",
                  "key_value": b"-----BEGIN PUBLIC KEY-----\nMIIBIjAN…\n-----END PUBLIC KEY-----"}, …]}
```

#### 7.3.3 `list_authenticator_revelation_requests`

| | |
|---|---|
| Caller | Authorization requests list (`COMP/screens/authenticator_revelation_request_management.py:106-109`) |
| Params | `authenticator_keystore_uid`: UUID; `authenticator_keystore_secret`: str |
| Result | a list of **revelation request** objects (below), in every status |
| Errors | `KeystoreDoesNotExist`; `AuthenticationError`; `SchemaValidationError` |

Revelation request object (`SERVER/apps/wagateway/serializers.py:81-122`):

| Field | Type | Meaning |
|---|---|---|
| `target_public_authenticator` | public authenticator object (as in 7.3.1) | the authenticator the request targets |
| `revelation_request_uid` | UUID | id used by accept/reject |
| `revelation_requestor_uid` | UUID | claimant device id |
| `revelation_request_description` | str | free text from the claimant (claimant UI requires ≥10 chars) |
| `revelation_response_public_key` | bytes | claimant's one-time response public key (PEM) |
| `revelation_response_keychain_uid` | UUID | claimant's id for that key |
| `revelation_response_key_algo` | str | cipher to use for responses (`RSA_OAEP` in practice) |
| `revelation_request_status` | `PENDING` / `ACCEPTED` / `REJECTED` | [03 §3.3](03-business-logic.md#33-revelation-request-and-symkey-decryption-states-gateway-owned) |
| `symkey_decryption_requests` | list of objects (below) | |
| `created_at` | datetime | request creation time; the client sorts by it |

Symkey decryption request object:

| Field | Type | Meaning |
|---|---|---|
| `target_public_authenticator_key` | `{keychain_uid: UUID, key_algo: str, key_value: bytes}` | which authenticator keypair must decrypt |
| `cryptainer_name` | str (≤100) | display only |
| `cryptainer_uid` | UUID | display only |
| `cryptainer_metadata` | object or null | display only (shown as a Python `str()` of the dict) |
| `symkey_decryption_request_data` | bytes | serialized RSA-OAEP cipherdict (§5.2) |
| `symkey_decryption_response_data` | bytes | `b""` until the request is accepted |
| `symkey_decryption_status` | `PENDING` / `DECRYPTED` / `PRIVATE_KEY_MISSING` / `CORRUPTED` / `METADATA_MISMATCH` | [03 §3.3](03-business-logic.md#33-revelation-request-and-symkey-decryption-states-gateway-owned) |

Reader rules:

- An empty `symkey_decryption_requests` list is valid in a response (the submit schema allows it), but such a request can only be rejected: `accept` requires a non-empty results list ([05 OI-03](05-open-issues.md#a-revelation-requests-accept--reject)).
- `symkey_decryption_request_data` values are unique within one request (the gateway refuses duplicates at submit, `SERVER/apps/wagateway/core.py:139-145`).
- `revelation_response_key_algo` and `target_public_authenticator_key.key_algo` can be any `SUPPORTED_CIPHER_ALGOS` value as far as the gateway is concerned; the authenticator MUST refuse anything but `RSA_OAEP` (checklist item 18).
- An unknown `revelation_request_status` SHOULD be ignored with a log line, not crash the listing ([05 OI-05](05-open-issues.md#a-revelation-requests-accept--reject)).
- `keystore_creation_datetime` and `cryptainer_metadata` may be null.

Full wire example of a response (canonical Extended JSON as the gateway emits it, re-indented, one item of each list shown, base64 cut). The complete, untruncated file is `fixtures/gateway/list_authenticator_revelation_requests.response.json`; a real 2023 gateway output with the same structure is `fixtures/gateway/observed_2023_list_requestor_revelation_requests.result.json`.

```json
{"id": {"$numberLong": "5776600559367167158"}, "jsonrpc": "2.0",
 "result": [
  {"created_at": {"$date": {"$numberLong": "1792843200123"}},
   "revelation_request_description": "Judicial request n\u00b0 42, please accept",
   "revelation_request_status": "PENDING",
   "revelation_request_uid": {"$binary": {"base64": "EE5eCnaE3FtVRwiv/UGULA==", "subType": "04"}},
   "revelation_requestor_uid": {"$binary": {"base64": "EE5eCnaE69s2G1WBeyrWzg==", "subType": "04"}},
   "revelation_response_key_algo": "RSA_OAEP",
   "revelation_response_keychain_uid": {"$binary": {"base64": "EE5eCmjjqJYVSk1OcRJWIg==", "subType": "04"}},
   "revelation_response_public_key": {"$binary": {"base64": "LS0tLS1CRUdJTiBQVUJMSUMg…", "subType": "00"}},
   "symkey_decryption_requests": [
    {"cryptainer_metadata": {"count": {"$numberInt": "3"}, "location": "Paris"},
     "cryptainer_name": "20261024_120000_camera_1.mp4.crypt",
     "cryptainer_uid": {"$binary": {"base64": "EE5eCnaEAXgrb/KwNyMmFA==", "subType": "04"}},
     "symkey_decryption_request_data": {"$binary": {"base64": "eyJjaXBoZXJ0ZXh0X2NodW5r…", "subType": "00"}},
     "symkey_decryption_response_data": {"$binary": {"base64": "", "subType": "00"}},
     "symkey_decryption_status": "PENDING",
     "target_public_authenticator_key": {
       "key_algo": "RSA_OAEP",
       "key_value": {"$binary": {"base64": "LS0tLS1CRUdJTiBQVUJMSUMg…", "subType": "00"}},
       "keychain_uid": {"$binary": {"base64": "EE5eChPwueTT/hBxIpS59A==", "subType": "04"}}}},
    "…"],
   "target_public_authenticator": {
     "keystore_creation_datetime": {"$date": {"$numberLong": "1792877120263"}},
     "keystore_owner": "Jane Doe \u00e9\u00e8",
     "keystore_uid": {"$binary": {"base64": "EE5eCe5HT0wM9N9sQJ8kYg==", "subType": "04"}},
     "public_keys": [
       {"key_algo": "RSA_OAEP",
        "key_value": {"$binary": {"base64": "LS0tLS1CRUdJTiBQVUJMSUMg…", "subType": "00"}},
        "keychain_uid": {"$binary": {"base64": "EE5eCfLtD06hpYXItVkqSg==", "subType": "04"}}},
       "…"]}},
  "…"]}
```

Points a parser must get right: `created_at` is a nested `$date`/`$numberLong`; integers inside `cryptainer_metadata` are `$numberInt`; an empty response is `$binary` with an empty base64 string (decodes to `b""`); `symkey_decryption_request_data` decodes to bytes that are themselves Extended JSON (§5.2); the PEM `key_value`s are bytes, not strings.

#### 7.3.4 `accept_revelation_request`

| | |
|---|---|
| Caller | Accept button (`COMP/screens/authenticator_revelation_request_detail.py:242-247`) |
| Params | `authenticator_keystore_secret`: str; `revelation_request_uid`: UUID; `symkey_decryption_results`: non-empty list of `{symkey_decryption_request_data: bytes, symkey_decryption_response_data: bytes, symkey_decryption_status: one of DECRYPTED, PRIVATE_KEY_MISSING, CORRUPTED, METADATA_MISMATCH}` (exactly these three keys) |
| Results to build (MUST) | One result per distinct `symkey_decryption_request_data` of the request, with that value echoed unchanged. Per item: decrypted → `DECRYPTED` + `ExtJSON(RSA_OAEP(response key, plaintext))`; private key file absent → `PRIVATE_KEY_MISSING` + `b""`; ciphertext does not decrypt → `CORRUPTED` + `b""`. A wrong passphrase aborts the whole operation without any call. Order of results is free (the gateway compares sets). Example: `fixtures/gateway/accept_revelation_request.request.json`. |
| Result | `null`; the request becomes `ACCEPTED` |
| Errors | `ExistenceError` (unknown request uid); `AuthenticationError`; `ValidationError` (status not PENDING; request-data set mismatch; status/data incoherence); `SchemaValidationError` |
| Rules | [03 §7.3](03-business-logic.md#73-accept-the-decryption-algorithm), gateway rules 1-6 (`SERVER/apps/wagateway/core.py:241-343`) |

#### 7.3.5 `reject_revelation_request`

| | |
|---|---|
| Caller | Reject button (`COMP/screens/authenticator_revelation_request_detail.py:264-267`) |
| Params | `authenticator_keystore_secret`: str; `revelation_request_uid`: UUID |
| Result | `null`; the request becomes `REJECTED` |
| Errors | `ExistenceError`; `AuthenticationError`; `ValidationError` (status not PENDING) |

#### 7.3.6 Other gateway methods (not called by the authenticator)

| Method | Caller | Params |
|---|---|---|
| `submit_revelation_request` | claimant | `authenticator_keystore_uid`, `revelation_requestor_uid`, `revelation_request_description` (non-empty), `revelation_response_public_key` (bytes), `revelation_response_keychain_uid`, `revelation_response_key_algo`, `symkey_decryption_requests: [{cryptainer_uid, cryptainer_name, cryptainer_metadata (dict or null), symkey_decryption_request_data (bytes, unique within the request), keychain_uid, key_algo}]` |
| `list_requestor_revelation_requests` | claimant | `revelation_requestor_uid` → the same list structure as 7.3.3 |

(`SERVER/apps/wagateway/views.py:51-79`, `SERVER/apps/wagateway/core.py:114-193`, `:348-367`.)

---

## 8. Platform crypto backend notes

The formats above do not depend on the backend. This section is INFO, except the last list.

| Context | Backend | Evidence |
|---|---|---|
| **Authenticator app 1.5, every OS** | pycryptodome with its C internals patched (the "fallback" backend), **forced** by `main.py`, which sets `FORCE_WACRYPTOLIB_FALLBACK_BACKEND=1` before any import ("SAME BEHAVIOUR FOR ALL OSes"): AES-CBC via pure-Python `pyaes`, Python XOR, hashlib-based hashers (PBKDF2 slow path), legacy Python OAEP decode. Other AES modes (EAX) are **not** available (`assert mode == MODE_CBC`). That is enough for the authenticator: PKCS#8 uses AES-CBC, and RSA-OAEP needs no AES. | `AUTH/main.py:3`, `CRYPTO/_crypto_backend/pycryptodome.py:10-151, 154-166` |
| cryptolib library default (other apps, CLI, gateway) | pycryptodome C extensions, except on iOS (detected by `import ios`), where the fallback is always used because `dlopen()` of the C extensions is forbidden. | `CRYPTO/_crypto_backend/pycryptodome.py:154-160` |

A reimplementation SHOULD use a native crypto library on every platform ([05 OI-53](05-open-issues.md#h-platform-build-release)).

Random bytes always come from `os.urandom` (`CRYPTO/_crypto_backend/__init__.py:49-51`). pycryptodome's own RNG is used inside RSA generation, OAEP and PKCS#8 salt and IV.

A reimplementation in another language needs:

- RSA-2048 key generation
- PKCS#8 PBES2 (PBKDF2-HMAC-SHA1, AES-256-CBC) read and write
- SPKI PEM read and write
- RSAES-OAEP with SHA-512 and MGF1-SHA-512
- an Extended JSON codec as in §3

---

## 9. Open issues

The data-format and crypto issues formerly numbered P-1 … P-15 are now in [05-open-issues.md](05-open-issues.md#e-data-formats-and-crypto) (OI-14, OI-21, OI-22, OI-32, OI-34 … OI-41).

---

## 10. Test vectors (fixtures)

Folder [fixtures/](fixtures/) holds vectors produced by the shipped cryptolib (`CRYPTO/` at the README baseline, pycryptodome 3.24.1, so **1000 PBKDF2 iterations** like the 1.5 app, fallback backend forced as in `main.py`). `fixtures/generate_fixtures.py` regenerates them and ends with a self-check that a reimplementation can mirror. Uids, keys and the secret are random, so a regeneration changes every file.

| File | Content | What to test |
|---|---|---|
| `passphrase.json` | `raw` = the passphrase used for all keys: `" Ma phrase ﬁnale Ångström café 2026 "` (leading and trailing space, U+FB01 ligature, U+212B ANGSTROM SIGN, decomposed `e`+U+0301). `normalized_utf8_hex` = the bytes fed to PBKDF2. `equivalent_after_normalization` = a different string that MUST also open the keys. `wrong` = a near miss that MUST fail. | §4.3 normalisation (checklist item 9) |
| `authenticator.keystore/` | A complete authenticator as the 1.5 GUI creates it: metadata (non-ASCII owner) and 3 RSA_OAEP keypairs. | metadata parsing (§2.2), listing order (§2.1), PKCS#8 decryption, Check = Success with 3 keys; `openssl pkcs8 -in <private>.pem -passin pass:<normalized passphrase>` also opens them |
| `edge_cases.keystore/` | One complete keypair, one public key **without** private key, a public key file with an **uppercase** uid, a file `not-a-uuid_RSA_OAEP_public_key.pem`, and `notes.txt`. Same passphrase. | the listing MUST return exactly 2 keypairs (one with `private_key_present = false`) and skip the 3 other files; Check = Failure with 1 missing private key; publication refusal ([05 OI-28](05-open-issues.md#d-publication)) |
| `gateway/list_authenticator_revelation_requests.response.json` | Full JSON-RPC response with 3 requests for `authenticator.keystore`: a `PENDING` one with 2 symkey decryption requests (keys 1 and 2; one with null metadata, one with a metadata dict), a `REJECTED` one, and a `PENDING` one with an **empty** symkey list. | response parsing (§7.3.3), grouping and newest-first sort, OI-03 (c) |
| `gateway/expected_plaintexts.json` | For each symkey request of the pending request: `symkey_decryption_request_data` and the expected decrypted `key_struct_bytes` (an `AES_EAX` and a `CHACHA20_POLY1305` symkey dict). | RSA-OAEP decryption (§5.2) |
| `gateway/claimant_response_private_key.pem` | The claimant's one-time response private key (unprotected PKCS#1), matching `revelation_response_public_key`. | decrypt your own `symkey_decryption_response_data` and compare with the expected plaintext (OAEP is randomised, so ciphertexts never match byte for byte) |
| `gateway/accept_revelation_request.request.json` | The request body the 1.5 code produces when accepting the pending request. | envelope and params layout (§7.3.4); the `request_data` echo |
| `gateway/get_public_authenticator.response.json` | Response for `authenticator.keystore` once published. | publication status comparison ([03 §6.2](03-business-logic.md#62-already-published-detection-and-idempotency)) |
| `gateway/error_KeystoreDoesNotExist.response.json` | A functional error response (§7.2). | error mapping to "not published" / "does not exist in remote registry" |
| `gateway/observed_2023_list_requestor_revelation_requests.result.json` | One request copied from a real gateway response captured in 2023 (`witness-angel-components/list_requestor_revelation_requests_fixture.json`), written by pymongo `json_util`. Its keys are unrelated to the fixtures above. | parsing real gateway output: null `keystore_creation_datetime`, empty `$binary` |
