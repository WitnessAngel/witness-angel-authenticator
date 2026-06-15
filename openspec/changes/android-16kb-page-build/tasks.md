## 1. Host setup (Windows + Podman)

> Use the Podman CLI by absolute path (not on PATH). Define once per shell:
> `PODMAN="/c/Users/chamb/AppData/Local/Programs/Podman/podman.exe"`

- [x] 1.1 Verify Podman is ready: `"$PODMAN" --version` (5.8.2) and `"$PODMAN" machine list` shows `podman-machine-default` running (fallback: `"$PODMAN" machine start`)
- [x] 1.2 Verify free disk inside the VM (machine disk is 100 GiB): `"$PODMAN" machine ssh df -h`
- [x] 1.3 Pull the Ubuntu image: `"$PODMAN" pull docker.io/library/ubuntu:24.04` (pin digest `sha256:c4a8d5503dfb...` for exact reproducibility)
- [x] 1.4 Create the persistent cache volume: `"$PODMAN" volume create wa_build_home`

## 2. buildozer.spec changes

- [x] 2.1 Set `android.api = 36` (was 35)
- [x] 2.2 Add/uncomment `android.ndk = 29`
- [x] 2.3 Confirm `p4a.branch = develop` and `android.archs` includes `arm64-v8a`
- [x] 2.4 (Optional, for fast iteration) temporarily narrow `android.archs = arm64-v8a`
- [x] 2.5 Commit the spec change on a dedicated branch

## 3. Launch and provision the build container

- [x] 3.1 Start container: `"$PODMAN" run -it --name build_kivy -v "/p/Workspace/WitnessAngel/witness-angel-authenticator:/kivy_app_build" -v "wa_build_home:/root" ubuntu:24.04 bash`
- [x] 3.2 Install apt build deps: `apt update && apt install -y git zip unzip openjdk-17-jdk python3-pip python3-virtualenv autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo6 cmake libffi-dev libssl-dev automake autopoint gettext`
- [x] 3.3 Install Rust: `curl https://sh.rustup.rs -sSf | sh` (standard install) then `source "$HOME/.cargo/env"`
- [x] 3.4 Install Python 3.14 via deadsnakes: `apt install -y software-properties-common && add-apt-repository -y ppa:deadsnakes/ppa && apt update && apt install -y python3.14 python3.14-venv python3.14-dev`
- [x] 3.5 Install OpenGL/build headers: `apt install -y build-essential libgl1-mesa-dev`

## 4. Build environment (venv + buildozer)

- [x] 4.1 `cd /kivy_app_build` and create venv: `python3.14 -m venv venv_p4a_develop && source venv_p4a_develop/bin/activate`
- [x] 4.2 Install buildozer master: `pip install git+https://github.com/kivy/buildozer`
- [x] 4.3 Install helpers: `pip install legacy-cgi setuptools cython==0.29.34`
- [x] 4.4 Confirm `buildozer --version` and record the resolved buildozer/p4a commit for later pinning

## 5. Build the app

- [x] 5.1 Run a debug build (arm64-v8a only for fast feedback): `buildozer -v android debug`
- [x] 5.2 Resolve any recipe/dependency failure under Python 3.14 (pin recipe versions or deps as needed); re-run until green
- [x] 5.3 Confirm the artifact is written under `bin/`
- [ ] 5.4 Restore full `android.archs` and run the release build: `buildozer -v android release` (produces the `.aab`)

## 6. Verify 16 KB alignment

- [x] 6.1 Add `scripts/check_16kb_alignment.sh` implementing the `readelf -lW` loop over `lib/*/*.so`
- [x] 6.2 Extract the artifact (`7z x` / `unzip`) and run the script
- [x] 6.3 Assert NO `arm64-v8a/*.so` reports `0x1000` LOAD alignment (32-bit `armeabi-v7a` may stay 4 KB)
- [x] 6.4 Record/fail the gate accordingly

## 7. Reproducibility & documentation

- [x] 7.1 Pin the resolved buildozer commit and `p4a.commit` in `buildozer.spec` after the first green 16 KB build
- [x] 7.2 Write the runbook (host setup → container → provision → build → verify → extract artifact) into the repo (e.g. `scripts/README_android_16kb_build.md`)
- [x] 7.3 (Optional) Author a non-interactive `Containerfile` capturing steps 3–4 for one-command reproducible builds
- [x] 7.4 Note that the legacy `p4a_hacks.diff` (debug logging + pycryptodome 3.9.9 pin) is NOT used by this pipeline
