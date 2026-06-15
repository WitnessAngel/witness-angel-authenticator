#!/usr/bin/env bash
#
# sync_android_subpackages.sh - vendor the wacryptolib + wacomponents packages into
# the project root so the Android build (source.dir = .) bundles them into the APK/AAB.
#
# WHY: on desktop these packages are pip-installed (or symlinked). The Android build
# instead picks them up as plain source dirs at the project root. They are NOT part of
# this repo (they live in sibling Git checkouts) and are git-ignored here. A symlink
# would dangle inside the Podman build container (only this project dir is bind-mounted,
# not its siblings), so we COPY the real sources in.
#
# Run from the repo root before building for Android:
#   bash scripts/sync_android_subpackages.sh
#
# Override the sibling checkout locations if yours differ:
#   CRYPTOLIB_SRC=/path/to/witness-angel-cryptolib/src \
#   COMPONENTS_SRC=/path/to/witness-angel-components/src \
#   bash scripts/sync_android_subpackages.sh

set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

CRYPTOLIB_SRC="${CRYPTOLIB_SRC:-../witness-angel-cryptolib/src}"
COMPONENTS_SRC="${COMPONENTS_SRC:-../witness-angel-components/src}"

copy_pkg() {
  local name="$1" src_root="$2"
  local src="${src_root}/${name}"
  if [[ ! -f "${src}/__init__.py" ]]; then
    echo "error: ${name} not found at ${src} (set CRYPTOLIB_SRC / COMPONENTS_SRC)" >&2
    exit 1
  fi
  echo "Vendoring ${name} <- ${src}"
  rm -rf "./${name}"
  mkdir -p "./${name}"
  # copy package contents; drop caches/compiled junk that needn't ship
  cp -r "${src}/." "./${name}/"
  find "./${name}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "./${name}" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
  echo "  -> $(find "./${name}" -name '*.py' | wc -l) .py files"
}

copy_pkg wacryptolib  "$CRYPTOLIB_SRC"
copy_pkg wacomponents "$COMPONENTS_SRC"

echo "Done. wacryptolib/ and wacomponents/ are populated for the Android build."
