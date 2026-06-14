# Android 16 KB page-size build runbook (Authenticator)

Build a Google-Play-compliant **16 KB page-size aligned** Authenticator artifact using
**Podman** (Docker-free) on this Windows host.

Recipe source: [kivy/python-for-android#3165 (comment 4323324137)](https://github.com/kivy/python-for-android/issues/3165#issuecomment-4323324137).
The fix is: **buildozer master + p4a `develop` + Python 3.14 + `android.api = 36` + `android.ndk = 29`**,
which makes the `arm64-v8a` `.so` files 16 KB aligned. 32-bit `armeabi-v7a` stays 4 KB (exempt — Play
only requires it on 64-bit devices).

`buildozer.spec` is already set: `android.api = 36`, `android.ndk = 29`, `p4a.branch = develop`,
`android.archs` includes `arm64-v8a`.

> **Note on `p4a_hacks.diff`:** the repo's `p4a_hacks.diff` is legacy (debug logging + a
> `pycryptodome==3.9.9` pin). It is **NOT used** by this pipeline — `requirements` already pins
> `pycryptodome==3.20.0` and p4a `develop` handles the alignment. Do not apply it.

---

## 0. Conventions

The Podman CLI is **not on PATH**; call it by absolute path. Define once per Git Bash shell:

```bash
PODMAN="/c/Users/chamb/AppData/Local/Programs/Podman/podman.exe"
```

Disk: a full build needs ~12 GB. The `podman-machine-default` VM has a 100 GiB disk (≈955 GB free), so capacity is fine.

> **CRITICAL - `P:` is a removable drive.** The WSL podman machine does not auto-mount
> removable drives, so the project on `P:` is invisible by default (`/mnt/p` is an empty stub)
> and **`podman build -f Containerfile .` fails** (`archive/tar: missed writing 99 bytes`).
> Two consequences, both handled below:
> 1. **Build the image via stdin** (no directory context) - the Containerfile has no `COPY`.
> 2. **Persist a drvfs mount of `P:`** so bind mounts work (one-time, done):
>    ```bash
>    MSYS_NO_PATHCONV=1 "$PODMAN" machine ssh \
>      "grep -q '/mnt/p drvfs' /etc/fstab || echo 'P: /mnt/p drvfs metadata,uid=1000,gid=1000,umask=022 0 0' | sudo tee -a /etc/fstab; sudo mount /mnt/p"
>    ```
>    WSL re-runs `/etc/fstab` on each machine boot, so `P:` re-mounts automatically (it must be
>    connected at boot).
> 3. **Always run `podman` with `MSYS_NO_PATHCONV=1` and a Windows-style `-v` source**
>    (`'P:\...:/dest'`); the `/p/...:/dest` form gets mangled by Git Bash.

---

## 1. Host setup (one-time, mostly done)

```bash
"$PODMAN" --version                       # podman version 5.8.2
"$PODMAN" machine list                    # podman-machine-default must be running...
"$PODMAN" machine start                   # ...else start it
MSYS_NO_PATHCONV=1 "$PODMAN" machine ssh "df -h /"   # confirm free space
"$PODMAN" pull docker.io/library/ubuntu:24.04        # base image
"$PODMAN" volume create wa_build_home                # persistent cache for /root
```

---

## 2. Build - choose ONE path

### Path A: reproducible image (recommended)

Uses the repo `Containerfile` (toolchain baked in: apt deps, Rust, Python 3.14, buildozer master, cython 0.29.34).

```bash
cd /p/Workspace/WitnessAngel/witness-angel-authenticator

# build the toolchain image via stdin - NO directory context (works around the P: drive)
"$PODMAN" build -t wa-authenticator-build:16kb - < Containerfile      # ~10-15 min, already done

# debug APK (fast feedback; first p4a build downloads SDK/NDK r29 - long & needs disk)
MSYS_NO_PATHCONV=1 "$PODMAN" run --rm -it \
  -v 'P:\Workspace\WitnessAngel\witness-angel-authenticator:/kivy_app_build' \
  -v 'wa_build_home:/root' \
  wa-authenticator-build:16kb \
  bash -lc "cd /kivy_app_build && source /opt/venv_p4a_develop/bin/activate && buildozer -v android debug"

# release AAB (per android.release_artifact = aab)
MSYS_NO_PATHCONV=1 "$PODMAN" run --rm -it \
  -v 'P:\Workspace\WitnessAngel\witness-angel-authenticator:/kivy_app_build' \
  -v 'wa_build_home:/root' \
  wa-authenticator-build:16kb \
  bash -lc "cd /kivy_app_build && source /opt/venv_p4a_develop/bin/activate && buildozer -v android release"
```

### Path B: interactive container (matches the reference comment)

```bash
MSYS_NO_PATHCONV=1 "$PODMAN" run -it --name build_kivy \
  -v 'P:\Workspace\WitnessAngel\witness-angel-authenticator:/kivy_app_build' \
  -v 'wa_build_home:/root' \
  ubuntu:24.04 bash
```

Then **inside the container** (all as root):

```bash
apt update
apt install -y git zip unzip openjdk-17-jdk python3-pip python3-virtualenv \
  autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev \
  libtinfo6 cmake libffi-dev libssl-dev automake autopoint gettext

curl https://sh.rustup.rs -sSf | sh        # standard install
source "$HOME/.cargo/env"

apt install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt update
apt install -y python3.14 python3.14-venv python3.14-dev
apt install -y build-essential libgl1-mesa-dev

cd /kivy_app_build
python3.14 -m venv venv_p4a_develop
source venv_p4a_develop/bin/activate
pip install git+https://github.com/kivy/buildozer
pip install legacy-cgi setuptools cython==0.29.34
buildozer --version                        # record the resolved version for pinning

buildozer -v android debug                 # then later: buildozer -v android release
```

---

## 3. Verify 16 KB alignment

From any Linux/WSL shell or inside the container (needs `readelf` + `unzip`):

```bash
./scripts/check_16kb_alignment.sh bin/<your_artifact>.apk     # or .aab
```

Pass = every `arm64-v8a` / `x86_64` `.so` is `>= 0x4000` aligned. The script exits non-zero if any
64-bit lib is still `0x1000` (4 KB). 32-bit libs are reported `[skip]`.

Manual equivalent (the reference one-liner) from the extracted `lib/` dir:

```bash
find -type f -iname "*.so" | while read ii; do echo -n "$ii"; \
  readelf -lW "$ii" | grep -q "0x1000" && echo " --> found 4Kb aligned .so ..." || echo " --> ok"; done
```

---

## 4. Pin for reproducibility (after first green build)

- Record `buildozer --version` and the resolved p4a `develop` commit.
- Set `p4a.commit = <hash>` in `buildozer.spec` (and pin the buildozer commit in the `Containerfile`)
  so future builds are deterministic.
- Optionally pin the base image by digest in the `Containerfile`
  (`ubuntu@sha256:c4a8d5503dfb...`).

---

## Tips

- For faster iteration, temporarily set `android.archs = arm64-v8a` in `buildozer.spec`
  (the only arch the 16 KB gate checks), then restore the full list for release.
- First build downloads the Android SDK + NDK r29 (large). Caches live in the mounted project
  `.buildozer/` and the `wa_build_home` volume, so subsequent builds are much faster.
- The final `.aab`/`.apk` lands in `bin/` on the Windows filesystem (project is bind-mounted).
