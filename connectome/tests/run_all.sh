#!/bin/sh
# Every check of the demo: the browser brain against the library, the two-half brain, the
# spiking port against the Python model, the body, the closed loop.
set -e
cd "$(dirname "$0")/.."
# Check node's status before shortening successful output. In a POSIX shell, a
# `node ... | tail -1` pipeline otherwise hides a failing test behind tail's exit code.
summary() {
  if output=$(node "$1"); then
    printf '%s\n' "$output" | tail -1
  else
    result=$?
    printf '%s\n' "$output"
    return "$result"
  fi
}
node tests/parity.mjs
node tests/twin.mjs
node tests/spiking_parity.mjs
node tests/evidence.mjs
node tests/learning_parity.mjs
node tests/learning_contract.mjs
node tests/lesson_life_contract.mjs
node tests/learning_probe.mjs
node tests/learning_view.mjs
node tests/learning_shuffle.mjs
# The old learning_life assay inferred a hold from lesson samples and required
# instability. The release assay tests frozen learned weights independently.
node tests/learning_release.mjs
node tests/learning_reteach.mjs
summary tests/body.mjs
summary tests/life.mjs
summary tests/larva.mjs
summary tests/larva_brain.mjs
summary tests/larva_life.mjs
echo "all demo checks passed"
