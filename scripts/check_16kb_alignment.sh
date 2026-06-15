#!/usr/bin/env bash
#
# check_16kb_alignment.sh - verify Android native libs are 16 KB page-size aligned.
#
# Google Play requires 16 KB page-size support for 64-bit (arm64-v8a, x86_64)
# native code in apps targeting Android 15+. A compliant .so has its ELF LOAD
# segments aligned to >= 0x4000 (16 KB). A 4 KB-aligned lib shows 0x1000 and is
# REJECTED. 32-bit archs (armeabi-v7a, x86) are exempt and may stay 0x1000.
#
# Usage:
#   ./check_16kb_alignment.sh path/to/app.apk          # or .aab
#   ./check_16kb_alignment.sh path/to/extracted_dir    # dir containing lib/<arch>/*.so
#
# Requires: readelf (binutils), unzip. Run on Linux / WSL / inside the build container.
# Exit code: 0 = all 64-bit libs OK, 1 = at least one 64-bit lib is 4 KB-aligned.

set -euo pipefail

MIN_ALIGN=16384            # 0x4000
ARCH64_RE='(arm64-v8a|x86_64)'

target="${1:-}"
if [[ -z "$target" ]]; then
  echo "usage: $0 <app.apk|app.aab|extracted_dir>" >&2
  exit 2
fi

workdir=""
cleanup() { [[ -n "$workdir" && -d "$workdir" ]] && rm -rf "$workdir"; }
trap cleanup EXIT

if [[ -f "$target" ]]; then
  workdir="$(mktemp -d)"
  echo "Extracting $target ..."
  unzip -q -o "$target" -d "$workdir"
  root="$workdir"
elif [[ -d "$target" ]]; then
  root="$target"
else
  echo "error: '$target' is neither a file nor a directory" >&2
  exit 2
fi

fail=0
checked=0

# Find every .so under a lib/<arch>/ path.
while IFS= read -r so; do
  arch="$(basename "$(dirname "$so")")"
  # Skip non-ELF files: p4a ships libpybundle.so, a renamed Python data blob (not a
  # real shared library), in lib/<arch>/ so Android extracts it. It has no ELF header.
  if ! readelf -h "$so" >/dev/null 2>&1; then
    printf '  [skip] %-12s %-28s (not an ELF - data blob, e.g. libpybundle.so)\n' "$arch" "$(basename "$so")"
    continue
  fi
  # Smallest LOAD-segment alignment in this ELF (last column of readelf -lW LOAD lines).
  # Parse hex with bash arithmetic ($((0x..))) so we don't need gawk's strtonum (mawk lacks it).
  min=0
  while IFS= read -r tok; do
    [[ "$tok" =~ ^0x[0-9a-fA-F]+$ ]] || continue
    v=$(( tok ))
    if [[ "$min" -eq 0 || "$v" -lt "$min" ]]; then min="$v"; fi
  done < <(readelf -lW "$so" 2>/dev/null | awk '/LOAD/ {print $NF}')

  if [[ "$arch" =~ $ARCH64_RE ]]; then
    checked=$((checked+1))
    if [[ -z "$min" || "$min" -lt "$MIN_ALIGN" ]]; then
      printf '  [FAIL] %-12s %-28s align=0x%x (need >= 0x4000)\n' "$arch" "$(basename "$so")" "${min:-0}"
      fail=1
    else
      printf '  [ ok ] %-12s %-28s align=0x%x\n' "$arch" "$(basename "$so")" "$min"
    fi
  else
    printf '  [skip] %-12s %-28s align=0x%x (32-bit exempt)\n' "$arch" "$(basename "$so")" "${min:-0}"
  fi
done < <(find "$root" -type f -path '*/lib/*' -iname '*.so' | sort)

echo "---"
if [[ "$checked" -eq 0 ]]; then
  echo "warning: no 64-bit (arm64-v8a/x86_64) .so found under lib/ - nothing verified" >&2
  exit 2
fi
if [[ "$fail" -ne 0 ]]; then
  echo "RESULT: FAILED - one or more 64-bit libs are 4 KB-aligned. Rebuild with NDK r29 + p4a develop."
  exit 1
fi
echo "RESULT: PASS - all $checked 64-bit lib(s) are >= 16 KB aligned."
