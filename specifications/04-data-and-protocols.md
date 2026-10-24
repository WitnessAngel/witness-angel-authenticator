# 04 - Data formats and protocols specification

Witness Angel Authenticator, version 1.5. This file gives the byte-level formats a reimplementation needs to stay compatible with:

- existing authenticator folders (on disk, and in ZIP exports),
- the Witness Angel gateway (JSON-RPC over HTTPS),
- the cryptolib clients on the other side of the protocol (recorders, claimants).

Everything here is language-neutral. The Python code is cited only as evidence.

Sibling files: `01-architecture-and-platform.md` (storage roots, config file, build), `02-ux-and-screens.md` (UI), `03-business-logic.md` (rules and state machines; referenced below as "03 §x").

Citation convention: `path:line`, relative to the WitnessAngel workspace root.

| Prefix | Path |
|---|---|
| `AUTH/` | `witness-angel-authenticator/` |
| `COMP/` | `witness-angel-components/src/wacomponents/` |
| `CRYPTO/` | `witness-angel-cryptolib/src/wacryptolib/` |
| `VENDORS/` | `witness-angel-cryptolib/src/vendors/` |
| `SERVER/` | `witness-angel-server/src/waserver/` |

Worked examples were produced by running the real cryptolib code (`initialize_authenticator`, `generate_keypair`, `FilesystemKeystore`, `encrypt_bytestring`, `TrusteeApi`, `JsonRpcProxy.serialize`) in a scratch environment. Long base64 values are cut and marked `…`.

Library versions:

- The app pins **pycryptodome 3.20.0** (`AUTH/buildozer.spec:40`).
- The example run used pycryptodome 4.2.0. The only visible difference is the PBKDF2 iteration count (§4.3).

---

## 1. Primitive encodings (used everywhere)

| Logical type | Canonical in-memory form | Notes |
|---|---|---|
| UUID | 16 bytes, RFC 4122 byte order (`uuid.bytes`) | Text form: lowercase hyphenated `8-4-4-4-12`. Used in filenames. |
| uuid0 (all generated uids) | 6 bytes big-endian = `floor(unix_time * 10000)` (100 µs units), then 10 bytes from the OS CSPRNG | No RFC version/variant bits are set (`VENDORS/uuid0/core.py:79-87`, `CRYPTO/utilities/time_utils.py:11-22`). Any 16-byte value must be accepted as a UUID. |
| datetime | Timezone-aware instant | Naive datetimes are refused by the schema (`CRYPTO/keystore.py:57`) and by the JSON encoder (`AUTH/extjson.py:227-229`). Serialized with **millisecond** precision (§3). |
| bytes | Raw octets | Serialized as base64 (§3) |
| text | Unicode | JSON text is UTF-8. `ensure_ascii` is on, so non-ASCII characters are written as `\uXXXX` escapes. |

---

## 2. On-disk layout of an authenticator

### 2.1 Folder content

The folder name depends on the location (03 §2): `authenticator.keystore`, legacy `.authenticator` on USB drives, legacy `authenticator` in the profile (renamed on startup).

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

Listing rules (`CRYPTO/keystore.py:439-477`):

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
| `keystore_secret` | string | no ("recent field") | plain string | `token_urlsafe(64)`: 86 chars `[A-Za-z0-9_-]`. Gateway bearer credential (03 §1). |
| `keystore_passphrase_hint` | string | no (schema) / yes (authenticator) | plain string | non-empty if present |

The schema only accepts decoded native types (UUID, datetime). The file is first parsed with Extended JSON (§3) and then validated.

Byte-exact example (a real file: one line, keys sorted, `", "` and `": "` separators, no trailing newline):

```json
{"keystore_creation_datetime": {"$date": {"$numberLong": "1792875147037"}}, "keystore_format": "keystore_1.0", "keystore_owner": "Jane Doe", "keystore_passphrase_hint": "my cat name twice", "keystore_secret": "HZ8S0eU27Z_bDZtBw_cGtmqi59Ya8EQv8zTyQ9hdJ6jSXhbAZN2SVZ-0sU74ee4IjQF5wPMUYyjpPdrkJ8dKoA", "keystore_type": "authenticator", "keystore_uid": {"$binary": {"base64": "EE5c3NclBJg7czxGtRnIQQ==", "subType": "04"}}}
```

Here `keystore_uid` = `104e5cdc-d725-0498-3b73-3c46b519c841`. A reader must also accept the relaxed forms (§3.3), for example `{"$uuid":"104e5cdcd72504983b733c46b519c841"}` and `{"$date":"2026-10-24T20:52:27.037Z"}`.

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
- Import extracts all entries into the selected authenticator folder (`authenticator_management.py:390`). See 03 §8.

### 2.5 App configuration

The INI file contains `[authenticator] custom_authenticator_dir` (absolute path or empty) and `[network] wagateway_url` (default `https://api.witnessangel.com/gateway/jsonrpc/`) (`AUTH/waauthenticator/config_defaults.ini:1-7`, `AUTH/waauthenticator/waauthenticator_gui.py:87-112`). File location and handling: 01 §3.

---

## 3. Serialization: Extended JSON ("extjson")

All JSON written by the cryptolib (metadata files, JSON-RPC bodies, ciphertext dicts nested in bytes) goes through the vendored `extjson` module. It is a BSON-Extended-JSON-like format. The authenticator ships a copy at `AUTH/extjson.py` (untracked, "VENDORED FROM witness-angel-cryptolib"). The cryptolib copy is at `VENDORS/extjson.py`. Both write the **canonical** form by default (`dumps(..., canonical=True)`, `AUTH/extjson.py:104-110`, `VENDORS/extjson.py:98`). The cryptolib re-exports its helpers in `CRYPTO/utilities/__init__.py:9-10`.

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

**Byte-exactness matters in one place only:** `symkey_decryption_request_data` is compared byte-for-byte by the gateway and the claimant (03 §7.3). The authenticator never re-serializes it; it echoes the received bytes. Everywhere else, any semantically equal JSON is accepted.

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

Ambiguity a reimplementation must copy: a user-level dict that has a single key such as `$date` is indistinguishable from a wrapper. No such dicts exist in the authenticator data model.

### 3.3 Relaxed mode

The upstream ExtJson 0.2.0 package (`../ExtJson/extjson.py:380`) defaults to `canonical=False`. In that mode it emits `{"$uuid":"<32 hex>"}`, `{"$date":"YYYY-MM-DDTHH:MM:SS[.mmm]Z"}` and plain ints, while bytes stay `$binary` subtype 00 (`AUTH/extjson.py:227-248`). The cryptolib's own extended-JSON micro-schemas say "RELAXED is the default and expected format" (`CRYPTO/utilities/validation_utils.py:29-61`). Readers must accept **both** modes. Writers should keep the canonical mode, for compatibility with older readers.

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
- 64-character base64 lines, LF line endings, **no trailing newline**. About 450 bytes for RSA-2048.
- This exact byte string is both the file content and the `key_value` sent to the gateway.

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
| PEM label | `ENCRYPTED PRIVATE KEY`. 64-char lines, LF, no trailing newline. About 1857 bytes for RSA-2048. |
| Outer DER | PKCS#8 `EncryptedPrivateKeyInfo` |
| Encryption scheme | PBES2 (OID `1.2.840.113549.1.5.13`) |
| KDF | PBKDF2 (OID `1.2.840.113549.1.5.12`). PRF is HMAC-SHA1, the default, so no PRF field is encoded. |
| Salt | 8 random bytes (pycryptodome default `salt_size`) |
| Iteration count | Not set by wacryptolib, so the library default applies. **1000** with pycryptodome 3.20.0 (the app pin; `Crypto/IO/_PBES.py:322`). **600000** with pycryptodome 4.2.0 (observed: `INTEGER 0x0927C0`). |
| Derived key length | 32 bytes |
| Cipher | AES-256-CBC (OID `2.16.840.1.101.3.4.1.42`), 16-byte random IV, PKCS#7 padding |
| Plaintext | PKCS#8 `PrivateKeyInfo` holding a PKCS#1 `RSAPrivateKey` |
| Passphrase bytes | `UTF-8(NFKC(strip(passphrase)))` (`CRYPTO/keygen.py:16-18`). An empty result is refused at export (`:176-178`). |

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
- Note: pycryptodome ≥4 checks a *maximum* iteration count on decryption (its `_PBES.py` `max_iteration_count`). Keys made with old libraries (1000 iterations) are under any limit.
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

There is no MAC and nothing binds the chunks together: reordering or dropping chunks is not detected at this layer (§9 P-6).

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
| `KEYSTORE_TREE_SCHEMA` | client | keystore tree export/import. `key_algo` is checked against `SUPPORTED_CIPHER_ALGOS` = `AES_CBC`, `AES_EAX`, `CHACHA20_POLY1305`, `RSA_OAEP` (§9 P-9). | `CRYPTO/keystore.py:66-78`, `CRYPTO/cipher.py:471-502` |
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
| HTTP | `POST`, headers `Content-Type: application/json`, `Accept: application/json-rpc`, via `requests`. Timeout 10 s. A new proxy (and session) is created per operation. | `jsonrpc_requests/jsonrpc.py:40-47`, `CRYPTO/jsonrpc_client.py:17`, `COMP/application/_common_runtime_support.py:192-195` |
| Envelope | JSON-RPC 2.0: `{"jsonrpc":"2.0","method":…,"params":{…},"id":…}`. The **whole envelope** is Extended JSON, so the random id (1 … 2^63-1) usually goes out as `{"$numberLong":"…"}`. The gateway decodes requests and encodes responses with the same Extended JSON helpers (`SERVER/utils.py:43-46`). | `CRYPTO/jsonrpc_client.py:63-75`, `jsonrpc_requests/jsonrpc.py:89-96` |
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

**Unexpected server errors** become django-jsonrpc `OtherError` (code 500, HTTP **500**). The client then raises `jsonrpc_requests.TransportError("Got non-200 response…")`. Connection failures also raise `TransportError`. Both are subclasses of `JSONRPCError`, which the UI catches next to `OSError` (03 §7.2).

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
| Params | `keystore_uid`: UUID; `keystore_owner`: non-empty str (≤100 stored); `keystore_secret`: non-empty str; `public_keys`: **non-empty** list of `{keychain_uid: UUID, key_algo: one of SUPPORTED_CIPHER_ALGOS, key_value: bytes}`; `keystore_creation_datetime`: aware datetime or null (optional; the app omits it when it is absent locally) |
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
| `revelation_request_status` | `PENDING` / `ACCEPTED` / `REJECTED` | 03 §3.3 |
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
| `symkey_decryption_status` | `PENDING` / `DECRYPTED` / `PRIVATE_KEY_MISSING` / `CORRUPTED` / `METADATA_MISMATCH` | 03 §3.3 |

#### 7.3.4 `accept_revelation_request`

| | |
|---|---|
| Caller | Accept button (`COMP/screens/authenticator_revelation_request_detail.py:242-247`) |
| Params | `authenticator_keystore_secret`: str; `revelation_request_uid`: UUID; `symkey_decryption_results`: non-empty list of `{symkey_decryption_request_data: bytes, symkey_decryption_response_data: bytes, symkey_decryption_status: one of DECRYPTED, PRIVATE_KEY_MISSING, CORRUPTED, METADATA_MISMATCH}` |
| Result | `null`; the request becomes `ACCEPTED` |
| Errors | `ExistenceError` (unknown request uid); `AuthenticationError`; `ValidationError` (status not PENDING; request-data set mismatch; status/data incoherence); `SchemaValidationError` |
| Rules | 03 §7.3, gateway rules 1-6 (`SERVER/apps/wagateway/core.py:241-343`) |

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

| Platform | Backend | Evidence |
|---|---|---|
| Android, desktop | pycryptodome (C extensions) | `CRYPTO/_crypto_backend/pycryptodome.py:154-160` |
| iOS (or env `FORCE_WACRYPTOLIB_FALLBACK_BACKEND`) | pycryptodome with C internals patched: AES-CBC via pure-Python `pyaes`, Python XOR, hashlib-based hashers (PBKDF2 slow path), legacy Python OAEP decode. Other AES modes (EAX) are **not** available (`assert mode == MODE_CBC`). That is enough for the authenticator: PKCS#8 uses AES-CBC, and RSA-OAEP needs no AES. | `CRYPTO/_crypto_backend/pycryptodome.py:10-151` |

Random bytes always come from `os.urandom` (`CRYPTO/_crypto_backend/__init__.py:49-51`). pycryptodome's own RNG is used inside RSA generation, OAEP and PKCS#8 salt and IV.

A reimplementation in another language needs:

- RSA-2048 key generation
- PKCS#8 PBES2 (PBKDF2-HMAC-SHA1, AES-256-CBC) read and write
- SPKI PEM read and write
- RSAES-OAEP with SHA-512 and MGF1-SHA-512
- an Extended JSON codec as in §3

---

## 9. Open issues & observations

| # | Severity | Observation | Evidence |
|---|---|---|---|
| P-1 | Security | The PBKDF2 iteration count is not pinned by wacryptolib. With the pinned pycryptodome 3.20.0 it is only **1000** (HMAC-SHA1, 8-byte salt). Upgrading pycryptodome silently changes it to 600000 for new keys only. Setting `prot_params={"iteration_count": …}` explicitly would make the format deterministic. | `CRYPTO/_crypto_backend/pycryptodome.py:365-369` |
| P-2 | Interop risk | Two Extended JSON flavours coexist: the vendored copies default to canonical, upstream ExtJson 0.2.0 defaults to relaxed, and the cryptolib micro-schema comment says "RELAXED is the default". Readers handle both. Switching the dependency would change on-disk metadata and wire bytes, though `request_data` echoing stays safe. | `AUTH/extjson.py:104`, `VENDORS/extjson.py:98`, `../ExtJson/extjson.py:380`, `CRYPTO/utilities/validation_utils.py:29-61` |
| P-3 | Bug / noise | `VENDORS/extjson.py:104` has a leftover debug `print("CALLING JSON DUMPS", args, kwargs)` on every dump (seen in the example run). The `AUTH/extjson.py` copy does not have it. | `VENDORS/extjson.py:104` |
| P-4 | Interop | The JSON-RPC envelope `id` is Extended-JSON-wrapped (`{"$numberLong": …}`). This is non-standard JSON-RPC and only works with gateways that decode Extended JSON on the whole body. | `CRYPTO/jsonrpc_client.py:63-66` |
| P-5 | Robustness | `$binary` subType `03` (legacy UUID) is allowed by the extended micro-schema but **rejected** by the extjson parser. | `CRYPTO/utilities/validation_utils.py:51-54` vs `AUTH/extjson.py:285-290` |
| P-6 | Crypto design | RSA-OAEP over independent 60-byte chunks is non-standard. Chunk reordering, truncation or splicing is not detected. Integrity of the symkey relies on later layers (JSON parsing, AEAD of the payload). With SHA-512, a 2048-bit key could take 126 bytes per chunk. | `CRYPTO/cipher.py:24`, `:211-248` |
| P-7 | Precision | Datetimes are truncated to milliseconds in canonical mode. A reloaded `keystore_creation_datetime` differs from the in-memory value at creation (harmless). | `AUTH/extjson.py:227-232`, `:372-376` |
| P-8 | Robustness | Writes are non-atomic (no temp file and rename, no fsync) for the metadata and the PEM files. An interrupted write can leave a truncated PEM, which then reports as "wrong passphrase" (`KeyLoadingError`). | `CRYPTO/keystore.py:532-542`, `AUTH/extjson.py:85-92` |
| P-9 | Inconsistency | `KEYSTORE_TREE_SCHEMA`, and the gateway, validate `key_algo` against `SUPPORTED_CIPHER_ALGOS`. That list includes symmetric algos and excludes the signature key types (`RSA_PSS`, `DSA_DSS`, `ECC_DSS`). It works only because authenticators hold `RSA_OAEP` keys exclusively. TODO in code: a dedicated schema per keystore type. | `CRYPTO/keystore.py:62`, `:72`, `SERVER/apps/wagateway/core.py:378` |
| P-10 | Format | The listing regex `[-0-9a-z]+` skips uppercase UUID filenames, and the `.` in `.pem` is unescaped in the regex. Writers must use lowercase `str(UUID)`. | `CRYPTO/keystore.py:406` |
| P-11 | Legacy | A legacy `.keystore.json` is still read ("FIXME remove this asap ??"). If both files exist, `keystore_metadata.json` wins silently. | `CRYPTO/keystore.py:101-107` |
| P-12 | Security | The metadata file holds the gateway bearer secret in clear, with default file permissions. The ZIP export copies it as is. | §2.2, §2.4 |
| P-13 | Interop | The gateway refuses publication with zero public keys (`And([...], len)`), while the local schema accepts empty authenticators. | `SERVER/apps/wagateway/core.py:374-383` |
| P-14 | Interop | `get_public_authenticator` always returns `keystore_creation_datetime` (it may be null). Consumers must handle null (`CRYPTO/operations.py:234` does). | `SERVER/apps/wagateway/serializers.py:73-78` |
| P-15 | Doc gap | The cryptolib docs describe RSA-OAEP only in general terms. They do not give the SHA-512 hash, the 60-byte chunking or the PKCS#8 protection parameters. This file is the reference for those details. | `witness-angel-cryptolib/docs/selected_protocols.rst:28-32` |
