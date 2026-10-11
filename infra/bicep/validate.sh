#!/usr/bin/env bash
# Static validation of every Bicep template and parameter file. No subscription needed.
# Fails on any error or warning. Used by `make bicep-lint` and the CI workflow.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BICEP=${BICEP:-$(command -v bicep || echo "$HOME/.local/bin/bicep")}
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

echo "bicep: $("$BICEP" --version)"
status=0

check() {
  # $1 = subcommand (build | build-params), $2 = file
  local log="$OUT/$(basename "$2").log"
  if "$BICEP" "$1" "$2" --outdir "$OUT" >"$log" 2>&1; then
    if grep -qiE 'warning|error' "$log"; then
      echo "WARN  $2"; cat "$log"; status=1
    else
      echo "OK    $2"
    fi
  else
    echo "FAIL  $2"; cat "$log"; status=1
  fi
}

for f in "$HERE"/main.bicep "$HERE"/rg.bicep "$HERE"/modules/*.bicep; do
  check build "$f"
done

for f in "$HERE"/params/*.bicepparam; do
  check build-params "$f"
done

# Lint reports diagnostics without producing output; treat any diagnostic as failure.
for f in "$HERE"/main.bicep "$HERE"/rg.bicep; do
  log="$OUT/lint-$(basename "$f").log"
  if "$BICEP" lint "$f" >"$log" 2>&1 && ! grep -qiE 'warning|error' "$log"; then
    echo "LINT  $f ok"
  else
    echo "LINT  $f reported diagnostics"; cat "$log"; status=1
  fi
done

if [ "$status" -eq 0 ]; then
  echo "Bicep validation passed: $(ls "$HERE"/modules/*.bicep | wc -l) modules, $(ls "$HERE"/params/*.bicepparam | wc -l) parameter files"
else
  echo "Bicep validation FAILED"
fi
exit "$status"
