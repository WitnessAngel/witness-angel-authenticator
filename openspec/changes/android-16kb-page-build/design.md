## Context

Google Play mandates 16 KB page-size support for 64-bit native code in apps targeting Android 15+ (enforced from 2025-11-01). The Authenticator is a Kivy/KivyMD app packaged with buildozer + python-for-android (p4a). The reference recipe — [p4a#3165 comment 4323324137](https://github.com/kivy/python-for-android/issues/3165#issuecomment-4323324137) — confirms that **buildozer master + p4a `develop` + Python 3.14 + API 36 + NDK r29** produces 16 KB-aligned `arm64-v8a` libraries, and was validated in a Docker `ubuntu:noble` container.

Constraints specific to this project:
- **Host is Windows 11**; the build toolchain (NDK, autotools, p4a) only runs on Linux → must build in a Linux container.
- The user requires **Podman**, not Docker. Podman is **not yet installed** on this host.
- `buildozer.spec` already has `p4a.branch = develop`; it needs `android.api 35→36` and a new `android.ndk = 29`.
- Disk: the reference build consumes ~12 GB total (≈5 GB `.buildozer`, ≈6 GB `/root` home, ≈1.4 GB image/libs). Must verify free space.
- App requirements pin `pycryptodome==3.20.0`, `kivy==2.3.0`, a kivymd zip, and many pure-Python deps — these must still resolve under Python 3.14.

## Goals / Non-Goals

**Goals:**
- A reproducible, Docker-free build that yields a **16 KB-aligned `arm64-v8a`** Authenticator artifact (`.aab` for release, `.apk` for testing).
- Podman runs the same `ubuntu:24.04` (noble) image used in the reference, so results are reproducible across machines.
- An explicit, scripted **alignment verification** gate before submission.
- Persistent caches so re-builds are fast (bind-mounted `.buildozer` and `/root`).

**Non-Goals:**
- No change to app logic (`main.py`, `waauthenticator`, Python deps stay as-is).
- No iOS work (the separate `TODO FIX custom location not remembered on ios` file is out of scope).
- Not chasing 16 KB alignment for 32-bit `armeabi-v7a` (exempt; Play only requires 64-bit).
- Not migrating to GitHub Actions / cloud CI (local Podman only, per request).

## Decisions

### D1: Podman on Windows via a WSL2-backed `podman machine`
Podman on Windows runs a lightweight Linux VM. Plan: install Podman (winget `RedHat.Podman` or Podman Desktop), then `podman machine init` + `podman machine start`. All `podman` commands from Git Bash then target that VM.
- **Why over Docker**: explicit user requirement; Podman is rootless/daemonless and the OCI image (`ubuntu:24.04`) is identical, so the reference steps transfer 1:1 (`docker` → `podman`).
- **Alternative considered**: WSL2 Ubuntu directly (no container). Rejected — less reproducible, pollutes the host WSL distro, harder to share.

### D2: Pull the pinned Ubuntu noble image
Use `podman pull docker.io/library/ubuntu:24.04` (reference used the `noble-20260410` tag / digest `sha256:c4a8d5503dfb...`). Pin by digest when reproducibility matters.
- **Why**: matches the validated environment exactly.

### D3: Bind-mount strategy for Windows
Mount the project and a persistent home into the container:
```bash
podman run -it --name build_kivy \
  -v "/p/Workspace/WitnessAngel/witness-angel-authenticator:/kivy_app_build" \
  -v "wa_build_home:/root" \
  ubuntu:24.04 bash
```
- Use a **named volume** (`wa_build_home`) for `/root` instead of a host path — avoids Windows↔WSL path-translation and permission friction, and keeps the ~6 GB cache inside the VM.
- The project itself is bind-mounted so the produced `bin/*.aab` lands directly on the Windows filesystem.
- **Alternative**: bind-mount a Windows host dir for `/root` (as the reference did with `$HOME/ubuntu_build_root_home`). Rejected on Windows due to slow 9p/virtiofs I/O and root-owned-file permission issues; named volume is faster and cleaner.

### D4: In-container toolchain provisioning (ordered)
Following the reference, in the running container as root:
1. `apt update && apt install -y git zip unzip openjdk-17-jdk python3-pip python3-virtualenv autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo6 cmake libffi-dev libssl-dev automake autopoint gettext`
2. Rust: `curl https://sh.rustup.rs -sSf | sh` then `source "$HOME/.cargo/env"`
3. Python 3.14 via deadsnakes PPA: `apt install software-properties-common`, `add-apt-repository ppa:deadsnakes/ppa`, `apt update`, `apt install python3.14 python3.14-venv python3.14-dev`
4. `build-essential libgl1-mesa-dev` (OpenGL headers for kivy)
5. venv on the mounted volume: `python3.14 -m venv venv_p4a_develop && source venv_p4a_develop/bin/activate`
6. `pip install git+https://github.com/kivy/buildozer` then `pip install legacy-cgi setuptools cython==0.29.34`
- **Why a venv inside the mounted project dir**: keeps the interpreter/tooling out of system Python and persists across container restarts.
- **Why pin cython 0.29.34**: p4a recipes expect the legacy Cython API; matches the reference.

### D5: buildozer.spec edits (minimal, surgical)
- `android.api = 35` → `android.api = 36`
- uncomment/add `android.ndk = 29`
- keep `p4a.branch = develop`
- leave `android.archs = armeabi-v7a,arm64-v8a,x86,x86_64` as-is (arm64-v8a is what the 16 KB gate checks). Optionally trim to `arm64-v8a` for faster builds during iteration.
- **Note**: existing `requirements` already use `pycryptodome==3.20.0` (newer than the p4a_hacks.diff's 3.9.9), so the local `p4a_hacks.diff` (debug logging + old pin) is **not** applied — it predates this approach.

### D6: Verification gate
After build, extract the artifact and run the reference `readelf` loop over `lib/*/*.so`, failing if any `arm64-v8a/*.so` shows `0x1000` LOAD alignment. Capture this as a small script (`scripts/check_16kb_alignment.sh`) runnable in the container or any Linux/WSL shell.

### D7: Capture the runbook as scripts + docs
Produce: (a) a `Containerfile` (optional, for a non-interactive image), (b) a step-by-step runbook in the repo, (c) the verification script. Interactive flow is primary; the Containerfile is a convenience for full reproducibility.

## Risks / Trade-offs

- **Moving branches** (buildozer master, p4a develop) → builds may break without notice. **Mitigation**: record the exact resolved commits (`buildozer --version`, p4a commit) after a green build; pin via `p4a.commit` / a buildozer commit hash.
- **Python 3.14 dep compatibility** (pycryptodome 3.20, kivymd zip, jsonschema, etc. compiling/installing under 3.14) → install or recipe failures. **Mitigation**: build incrementally; if a recipe fails, pin a known-good recipe version or fall back to API/NDK-compatible alternatives.
- **Windows ↔ Podman bind-mount I/O & permissions** → slow builds or root-owned files on the host. **Mitigation**: named volume for caches (D3); only the final artifact crosses to the host.
- **Disk exhaustion (~12 GB)** inside the podman machine VM. **Mitigation**: pre-check free space; `podman machine` disk size may need raising (`podman machine set --disk-size`).
- **NDK r29 / API 36 download size & SDK licenses** → first build is long and needs license acceptance. **Mitigation**: let buildozer auto-accept (`-v`), keep the SDK in the persistent volume.
- **`x86`/`x86_64` archs** add build time with no Play benefit. **Trade-off**: keep for emulator testing, or drop during iteration.

## Migration Plan

1. Install Podman on Windows; start `podman machine`. (Reversible: `podman machine stop`/uninstall.)
2. Edit `buildozer.spec` (api 36, ndk 29) on a branch.
3. Run the container, provision toolchain, build debug `.apk` first (fast feedback) for `arm64-v8a` only.
4. Run the alignment verification gate; iterate on any failing recipe.
5. Build the release `.aab` with all required archs once debug passes.
6. **Rollback**: revert `buildozer.spec`; the change is build-only, so no runtime rollback is needed. The previous 4 KB build remains valid for non-Play-15+ distribution.

## Open Questions

- Should `android.archs` be trimmed to `arm64-v8a,x86_64` (drop 32-bit) given Play's 64-bit-only future, or kept for legacy devices?
- Do we want a fully non-interactive `Containerfile` + single build script now, or keep the interactive runbook until the first green build pins versions?
- Should the resolved buildozer/p4a commits be pinned in `buildozer.spec` immediately after the first successful 16 KB build?
