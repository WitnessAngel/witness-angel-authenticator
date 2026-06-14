## 1. Host setup (Windows + Podman)

- [ ] 1.1 Verify free disk ≥ ~20 GB on the drive backing the podman machine VM
- [ ] 1.2 Install Podman on Windows (`winget install RedHat.Podman` or Podman Desktop); confirm `podman --version`
- [ ] 1.3 `podman machine init` then `podman machine start`; if needed raise disk size: `podman machine set --disk-size 60`
- [ ] 1.4 Pull the Ubuntu image: `podman pull docker.io/library/ubuntu:24.04` (pin digest `sha256:c4a8d5503dfb...` for exact reproducibility)
- [ ] 1.5 Create the persistent cache volume: `podman volume create wa_build_home`

## 2. buildozer.spec changes

- [ ] 2.1 Set `android.api = 36` (was 35)
- [ ] 2.2 Add/uncomment `android.ndk = 29`
- [ ] 2.3 Confirm `p4a.branch = develop` and `android.archs` includes `arm64-v8a`
- [ ] 2.4 (Optional, for fast iteration) temporarily narrow `android.archs = arm64-v8a`
- [ ] 2.5 Commit the spec change on a dedicated branch

## 3. Launch and provision the build container

- [ ] 3.1 Start container: `podman run -it --name build_kivy -v "/p/Workspace/WitnessAngel/witness-angel-authenticator:/kivy_app_build" -v "wa_build_home:/root" ubuntu:24.04 bash`
- [ ] 3.2 Install apt build deps: `apt update && apt install -y git zip unzip openjdk-17-jdk python3-pip python3-virtualenv autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo6 cmake libffi-dev libssl-dev automake autopoint gettext`
- [ ] 3.3 Install Rust: `curl https://sh.rustup.rs -sSf | sh` (standard install) then `source "$HOME/.cargo/env"`
- [ ] 3.4 Install Python 3.14 via deadsnakes: `apt install -y software-properties-common && add-apt-repository -y ppa:deadsnakes/ppa && apt update && apt install -y python3.14 python3.14-venv python3.14-dev`
- [ ] 3.5 Install OpenGL/build headers: `apt install -y build-essential libgl1-mesa-dev`

## 4. Build environment (venv + buildozer)

- [ ] 4.1 `cd /kivy_app_build` and create venv: `python3.14 -m venv venv_p4a_develop && source venv_p4a_develop/bin/activate`
- [ ] 4.2 Install buildozer master: `pip install git+https://github.com/kivy/buildozer`
- [ ] 4.3 Install helpers: `pip install legacy-cgi setuptools cython==0.29.34`
- [ ] 4.4 Confirm `buildozer --version` and record the resolved buildozer/p4a commit for later pinning

## 5. Build the app

- [ ] 5.1 Run a debug build (arm64-v8a only for fast feedback): `buildozer -v android debug`
- [ ] 5.2 Resolve any recipe/dependency failure under Python 3.14 (pin recipe versions or deps as needed); re-run until green
- [ ] 5.3 Confirm the artifact is written under `bin/`
- [ ] 5.4 Restore full `android.archs` and run the release build: `buildozer -v android release` (produces the `.aab`)

## 6. Verify 16 KB alignment

- [ ] 6.1 Add `scripts/check_16kb_alignment.sh` implementing the `readelf -lW` loop over `lib/*/*.so`
- [ ] 6.2 Extract the artifact (`7z x` / `unzip`) and run the script
- [ ] 6.3 Assert NO `arm64-v8a/*.so` reports `0x1000` LOAD alignment (32-bit `armeabi-v7a` may stay 4 KB)
- [ ] 6.4 Record/fail the gate accordingly

## 7. Reproducibility & documentation

- [ ] 7.1 Pin the resolved buildozer commit and `p4a.commit` in `buildozer.spec` after the first green 16 KB build
- [ ] 7.2 Write the runbook (host setup → container → provision → build → verify → extract artifact) into the repo (e.g. `scripts/README_android_16kb_build.md`)
- [ ] 7.3 (Optional) Author a non-interactive `Containerfile` capturing steps 3–4 for one-command reproducible builds
- [ ] 7.4 Note that the legacy `p4a_hacks.diff` (debug logging + pycryptodome 3.9.9 pin) is NOT used by this pipeline
