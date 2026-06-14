## Why

Since **November 1st, 2025**, Google Play requires every new app and update targeting Android 15+ to support **16 KB memory page sizes** on 64-bit devices. The current Authenticator build (Python 3.11/3.12 toolchain, `android.api = 35`, default NDK) produces 4 KB-aligned `.so` files for `arm64-v8a` and would be rejected by the Play Store. We need a reproducible build pipeline that yields a 16 KB-aligned release artifact.

Per [python-for-android#3165 (comment 4323324137)](https://github.com/kivy/python-for-android/issues/3165#issuecomment-4323324137), the fix is now official: build with **buildozer master** + **p4a `develop` branch** + **Python 3.14** + **`android.api = 36`** + **`android.ndk = 29`**. This change captures that pipeline, adapted to run in a **Podman** (rootless, Docker-free) Ubuntu 24.04 container on this Windows host.

## What Changes

- **Build environment**: Document and script a reproducible **Podman** workflow on Windows that runs an **Ubuntu 24.04 (`noble`)** container — replacing any ad-hoc local/Docker build. (Podman is not currently installed on this host; install is part of the change.)
- **Toolchain upgrade**: Inside the container, install **Python 3.14** (deadsnakes PPA), **Rust** (for cryptography-adjacent recipes), JDK 17, and **buildozer master** (`git+https://github.com/kivy/buildozer`).
- **`buildozer.spec` updates**:
  - `android.api = 35` → **`36`**
  - add **`android.ndk = 29`**
  - keep `p4a.branch = develop` (already set)
  - confirm `android.archs` includes `arm64-v8a` (the only arch with a 16 KB mandate; 32-bit `armeabi-v7a` is exempt and may stay 4 KB).
- **Verification step**: Add a `readelf`-based check that confirms `arm64-v8a` `.so` files are **no longer 4 KB-aligned** (no `0x1000` LOAD alignment) before submission.
- **Documentation**: A repeatable build runbook (host setup → container → build → verify → extract `.aab`/`.apk`).

## Capabilities

### New Capabilities
- `android-16kb-build`: Reproducible Podman-based Ubuntu 24.04 build pipeline that produces a 16 KB page-size-aligned Android release artifact for the Authenticator app, plus the alignment verification procedure.

### Modified Capabilities
<!-- None: no existing specs in openspec/specs/. -->

## Impact

- **Files**: `buildozer.spec` (api/ndk), new build runbook/script under `scripts/`; optionally a `Containerfile` for Podman.
- **Toolchain**: Python 3.14, buildozer master, p4a `develop`, NDK r29, Android API 36; Podman on Windows host.
- **Build sizes** (per the reference comment): `<project>/.buildozer` ≈ 5 GB, container `/root` home ≈ 6 GB, image/`/usr` ≈ 1.4 GB — disk capacity must be checked.
- **Risk**: `develop`/master are moving branches; pin commits where possible. Recipes (`pycryptodome==3.20.0`, kivy 2.3.0, kivymd) must still build against Python 3.14 / NDK r29.
- **No app source changes**: `main.py` and Python deps are unchanged; this is a build/packaging change only.
