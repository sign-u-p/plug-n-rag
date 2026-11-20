#!/bin/sh
# Checks the whole marketplace: the catalog, then every plugin under plugins/.
# Usage: tools/check.sh [--schnell]   (--schnell skips tests that need the real local model)
set -u
cd "$(dirname "$0")/.." || exit 1
FAST=0
[ "${1:-}" = "--schnell" ] && FAST=1
fail=0
step() { printf '\n== %s\n' "$1"; }

step "Marketplace (.claude-plugin/marketplace.json)"
claude plugin validate . || fail=1

for dir in plugins/*/; do
  name=$(basename "$dir")
  step "Plugin $name: validate"
  claude plugin validate "$dir" || fail=1
  if [ -f "$dir/pyproject.toml" ] && [ -d "$dir/tests" ]; then
    step "Plugin $name: Python-Tests"
    if [ "$FAST" -eq 1 ]; then
      (cd "$dir" && env -u UV_NATIVE_TLS uv run --all-extras pytest -q -m "not model") || fail=1
    else
      (cd "$dir" && env -u UV_NATIVE_TLS uv run --all-extras pytest -q) || fail=1
    fi
  fi
  if find "$dir" -path "$dir/node_modules" -prune -o \( -name '*.test.ts' -o -name '*.test.tsx' \) -print | grep -q .; then
    step "Plugin $name: Mod-Tests"
    claude plugin test "$dir" || fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  printf '\nFEHLER: mindestens eine Prüfung ist fehlgeschlagen.\n'
  exit 1
fi
printf '\nAlles grün.\n'
