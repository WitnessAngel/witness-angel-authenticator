# Witness Angel Authenticator — Specification

Specification of the Witness Angel Authenticator application (v1.5), detailed enough to
reimplement it in another language or framework while staying interoperable with existing
authenticator folders, the Witness Angel gateway, and `wacryptolib`.

Derived from the code of three repositories (sources are cited as `path:line` relative to the
`WitnessAngel/` workspace root):

- `witness-angel-authenticator` — app shell (`waauthenticator/`, `main.py`, build files)
- `witness-angel-components` — screens, widgets, platform helpers (`src/wacomponents/`)
- `witness-angel-cryptolib` — keystore, crypto, JSON-RPC client (`src/wacryptolib/`)

## Documents

| File | Content | Read it if you implement… |
|------|---------|---------------------------|
| [01-architecture-and-platform.md](01-architecture-and-platform.md) | Purpose, actors, lifecycle, config file, per-OS storage paths, permissions, build/release. Part A = requirements, Part B = current Kivy/buildozer implementation details. | the app skeleton, packaging |
| [02-ux-and-screens.md](02-ux-and-screens.md) | The 5 screens, navigation, exact EN/FR labels, validation messages, enabled states, dialogs, user journeys. | the UI |
| [03-business-logic.md](03-business-logic.md) | Domain concepts, state machines, creation, passphrase check, publication, revelation request processing, export/import/destroy, security assumptions. | the core logic |
| [04-data-and-protocols.md](04-data-and-protocols.md) | On-disk layout, metadata schema, Extended JSON, key formats (PEM / PKCS#8), RSA-OAEP chunking, gateway JSON-RPC methods. | storage, crypto, networking (byte-level interop) |

Suggested reading order: README → 01 §1 → 03 §1–3 → 02 → 04 → remaining sections.

## Glossary

| Term | Meaning |
|------|---------|
| **Authenticator** | A keystore (folder with metadata + keypairs) held by a *key guardian*; its private keys are protected by the guardian's passphrase. Also the name of this app. |
| **Key guardian** (trustee) | Person owning an authenticator, who accepts or rejects revelation requests. |
| **Cryptainer** | Encrypted container produced by Witness Angel recorders; its symmetric keys are encrypted with authenticators' public keys. |
| **Claimant / requestor** | Party wanting to decrypt cryptainers; sends a *revelation request* via the gateway. |
| **Revelation request** | Request, relayed by the gateway, asking the guardian to decrypt one or more symmetric keys and re-encrypt them for the requestor. |
| **Gateway** | Witness Angel web registry (JSON-RPC) where authenticators are published and revelation requests exchanged. Default URL: `https://api.witnessangel.com/gateway/jsonrpc/`. |
| **Publication** | One-time upload of an authenticator's public metadata and public keys to the gateway. |
| **Keystore secret** | Random secret stored in the authenticator metadata, used to authenticate the guardian to the gateway. |

## Conventions

- 01 Part A lists requirements a reimplementation must keep; 01 Part B and the other files
  describe current behaviour, which is the reference unless flagged as an open issue.
- Each document ends with an **Open issues & observations** section listing bugs,
  inconsistencies and security concerns found in the current code. A reimplementation should
  keep the behaviour on the wire and on disk unchanged, but need not reproduce those bugs.
