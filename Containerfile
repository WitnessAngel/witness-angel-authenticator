# Containerfile - reproducible 16 KB-capable Android build toolchain for the
# Witness Angel Authenticator (Kivy/KivyMD + buildozer + python-for-android).
#
# Captures kivy/python-for-android#3165 (comment 4323324137):
#   buildozer master + p4a develop + Python 3.14 + API 36 + NDK r29
# -> 16 KB page-size aligned arm64-v8a libraries.
#
# Build the image (run from repo root, with the Podman CLI):
#   PODMAN="/c/Users/chamb/AppData/Local/Programs/Podman/podman.exe"
#   "$PODMAN" build -t wa-authenticator-build:16kb -f Containerfile .
#
# Run a build (mounts project for output + named volume for caches):
#   "$PODMAN" run --rm -it \
#     -v "/p/Workspace/WitnessAngel/witness-angel-authenticator:/kivy_app_build" \
#     -v "wa_build_home:/root" \
#     wa-authenticator-build:16kb \
#     bash -lc "cd /kivy_app_build && source /opt/venv_p4a_develop/bin/activate && buildozer -v android debug"
#
# Pin reproducibility by replacing the tag below with the digest from the reference:
#   FROM docker.io/library/ubuntu@sha256:c4a8d5503dfb2a3eb8ab5f807da5bc69a85730fb49b5cfca2330194ebcc41c7b
FROM docker.io/library/ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# --- apt build dependencies (task 3.2 + 3.5) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        git zip unzip openjdk-17-jdk python3-pip python3-virtualenv \
        autoconf libtool libtool-bin libltdl-dev pkg-config zlib1g-dev \
        libncurses5-dev libncursesw5-dev libtinfo6 cmake libffi-dev libssl-dev \
        automake autopoint gettext \
        build-essential libgl1-mesa-dev \
        software-properties-common curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
# NOTE: libltdl-dev provides the LT_SYS_SYMBOL_USCORE m4 macro that the p4a
# libffi recipe's autoreconf needs (the reference apt list omitted it).

# --- Rust toolchain (task 3.3) ---
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# --- Python 3.14 via deadsnakes (task 3.4) ---
RUN add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
        python3.14 python3.14-venv python3.14-dev && \
    rm -rf /var/lib/apt/lists/*

# --- venv + buildozer master + helpers (tasks 4.1-4.3) ---
# venv lives in the image (not the mounted project) for full reproducibility;
# the .buildozer cache still lands in the mounted project dir + /root volume.
RUN python3.14 -m venv /opt/venv_p4a_develop && \
    /opt/venv_p4a_develop/bin/pip install --upgrade pip && \
    /opt/venv_p4a_develop/bin/pip install "git+https://github.com/kivy/buildozer" && \
    /opt/venv_p4a_develop/bin/pip install legacy-cgi setuptools "cython==3.0.12"
# NOTE: cython 3.0.12 (max allowed by p4a develop's kivy recipe) generates Python
# 3.14-compatible C. The reference's cython==0.29.34 is too old and breaks kivy's
# graphics .c on 3.14 (_PyUnicode_FastCopyCharacters / "too few arguments").

WORKDIR /kivy_app_build
ENV VIRTUAL_ENV=/opt/venv_p4a_develop
ENV PATH="/opt/venv_p4a_develop/bin:${PATH}"

# Default: build the debug APK. Override the command for release (`buildozer android release`).
CMD ["bash", "-lc", "buildozer -v android debug"]
