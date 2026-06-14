## ADDED Requirements

### Requirement: Podman-based Ubuntu build environment

The build SHALL run inside a rootless **Podman** container based on **Ubuntu 24.04 (`noble`)** on the Windows host, without any dependency on Docker. The container SHALL bind-mount the project directory and a persistent build-home directory so that build caches survive container restarts.

#### Scenario: Podman is available on the Windows host
- **WHEN** the operator runs `podman --version` after host setup
- **THEN** Podman reports a version and a Linux machine (`podman machine`) is running, with no Docker Desktop / Docker engine required

#### Scenario: Build container launched with project mounted
- **WHEN** the operator starts the build container
- **THEN** an `ubuntu:24.04` (noble) container runs interactively with the project mounted at a build path and a persistent home volume mounted at `/root`

### Requirement: 16 KB-capable toolchain

The build environment SHALL install **Python 3.14**, **buildozer master** (`git+https://github.com/kivy/buildozer`), the **p4a `develop`** branch, **JDK 17**, **Rust (cargo)**, and the native build dependencies required by the Authenticator recipes.

#### Scenario: Toolchain versions verified
- **WHEN** the operator checks tool versions inside the container after setup
- **THEN** `python3.14` runs, `buildozer` is installed from the master branch, and `cargo` is on `PATH`

#### Scenario: p4a branch pinned to develop
- **WHEN** buildozer reads `buildozer.spec`
- **THEN** `p4a.branch = develop` is in effect (the branch that produces 16 KB-aligned output)

### Requirement: buildozer.spec targets Android API 36 and NDK r29

`buildozer.spec` SHALL set `android.api = 36` and `android.ndk = 29`, and `android.archs` SHALL include `arm64-v8a`.

#### Scenario: Spec values updated
- **WHEN** `buildozer.spec` is inspected
- **THEN** `android.api = 36`, `android.ndk = 29`, and `android.archs` contains `arm64-v8a`

### Requirement: Produce a release artifact

The pipeline SHALL build the Authenticator app and produce the configured release artifact (`.aab` per current `android.release_artifact = aab`, and/or a debug `.apk` for testing).

#### Scenario: Build completes
- **WHEN** the operator runs the buildozer build command in the container
- **THEN** buildozer exits successfully and writes the artifact under the project `bin/` directory

### Requirement: 16 KB alignment verification

After a build, the operator SHALL verify that every `arm64-v8a` native library (`.so`) inside the artifact is **not 4 KB-aligned** — i.e. its ELF `LOAD` segment alignment is not `0x1000`. 32-bit `armeabi-v7a` libraries are exempt and MAY remain 4 KB-aligned.

#### Scenario: arm64-v8a libraries are 16 KB-aligned
- **WHEN** the operator extracts the artifact and runs `readelf -lW` over each `arm64-v8a/*.so`
- **THEN** no `arm64-v8a` `.so` reports a `0x1000` LOAD alignment (all pass the alignment check)

#### Scenario: 32-bit libraries do not fail the gate
- **WHEN** `armeabi-v7a/*.so` files report `0x1000` alignment
- **THEN** the verification still passes, because the 16 KB requirement applies only to 64-bit devices
