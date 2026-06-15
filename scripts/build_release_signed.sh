#!/usr/bin/env bash
#
# build_release_signed.sh - build a SIGNED, 16 KB-aligned release .aab via Podman.
#
# Signing uses python-for-android's P4A_RELEASE_* environment variables. Secrets are
# handled safely:
#   - passwords are PROMPTED interactively (read -s), never passed on the command line,
#     never echoed, never written to disk, never committed;
#   - they are exported into this shell and forwarded to the container with `-e NAME`
#     (value-less), so they do NOT appear in `podman` args / process list;
#   - the keystore stays on the host and is reached through the existing project bind
#     mount (it is git-ignored via *.keystore).
#
# MUST be run interactively (it prompts). From Git Bash, e.g.:
#   bash scripts/build_release_signed.sh
# In a Claude Code session, prefix with `!` so it runs in your terminal:
#   ! bash scripts/build_release_signed.sh
#
# Override defaults via env: PODMAN, IMAGE, PROJECT_WIN, KEYSTORE_FILE, P4A_RELEASE_KEYALIAS

set -euo pipefail

PODMAN="${PODMAN:-/c/Users/chamb/AppData/Local/Programs/Podman/podman.exe}"
IMAGE="${IMAGE:-wa-authenticator-build:16kb}"
PROJECT_WIN="${PROJECT_WIN:-P:\\Workspace\\WitnessAngel\\witness-angel-authenticator}"
KEYSTORE_FILE="${KEYSTORE_FILE:-witnessangel_android.keystore}"   # relative to project root

# --- collect signing inputs (alias is not secret; passwords are prompted hidden) ---
if [[ -z "${P4A_RELEASE_KEYALIAS:-}" ]]; then
  read -rp "Keystore alias: " P4A_RELEASE_KEYALIAS
fi
read -rsp "Keystore (store) password: " P4A_RELEASE_KEYSTORE_PASSWD; echo
read -rsp "Key password [blank = same as store]: " P4A_RELEASE_KEYALIAS_PASSWD; echo
P4A_RELEASE_KEYALIAS_PASSWD="${P4A_RELEASE_KEYALIAS_PASSWD:-$P4A_RELEASE_KEYSTORE_PASSWD}"

if [[ -z "$P4A_RELEASE_KEYALIAS" || -z "$P4A_RELEASE_KEYSTORE_PASSWD" ]]; then
  echo "error: alias and store password are required" >&2
  exit 1
fi

# keystore path AS SEEN INSIDE the container (project is bind-mounted at /kivy_app_build)
export P4A_RELEASE_KEYSTORE="/kivy_app_build/${KEYSTORE_FILE}"
export P4A_RELEASE_KEYALIAS P4A_RELEASE_KEYSTORE_PASSWD P4A_RELEASE_KEYALIAS_PASSWD

echo "Building signed release .aab (alias: ${P4A_RELEASE_KEYALIAS}, keystore: ${KEYSTORE_FILE}) ..."

# -e NAME (no =value) forwards the exported value without exposing it in the arg list.
MSYS_NO_PATHCONV=1 "$PODMAN" run --rm --name wa_release_build \
  -v "${PROJECT_WIN}:/kivy_app_build" \
  -v 'wa_build_home:/root' \
  -e P4A_RELEASE_KEYSTORE \
  -e P4A_RELEASE_KEYALIAS \
  -e P4A_RELEASE_KEYSTORE_PASSWD \
  -e P4A_RELEASE_KEYALIAS_PASSWD \
  "$IMAGE" \
  bash -lc 'cd /kivy_app_build && source /opt/venv_p4a_develop/bin/activate && buildozer -v android release'

# scrub secrets from this shell
unset P4A_RELEASE_KEYSTORE_PASSWD P4A_RELEASE_KEYALIAS_PASSWD

echo "Done. Signed artifact in bin/ . Verify 16 KB alignment:"
echo "  MSYS_NO_PATHCONV=1 \"\$PODMAN\" run --rm -v '${PROJECT_WIN}:/kivy_app_build' ${IMAGE} \\"
echo "    bash -lc 'cd /kivy_app_build && bash scripts/check_16kb_alignment.sh bin/*.aab'"
