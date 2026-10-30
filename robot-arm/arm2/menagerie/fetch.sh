#!/bin/sh
# Fetches MuJoCo Menagerie's franka_emika_panda at the pinned commit into
# arm2/menagerie/franka_emika_panda/ and checks the files against those the arm was trained with.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
COMMIT=f3b6013629c7b94f8ee93fd977b161fa8350f9bc
OUT="$HERE/franka_emika_panda"
if command -v sha256sum >/dev/null 2>&1; then SHA="sha256sum"; else SHA="shasum -a 256"; fi
digest() { $SHA "$1" | cut -d' ' -f1; }
if [ ! -f "$OUT/panda.xml" ]; then
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT
  git clone -q --filter=blob:none --no-checkout https://github.com/google-deepmind/mujoco_menagerie.git "$TMP/m"
  git -C "$TMP/m" sparse-checkout set franka_emika_panda
  git -C "$TMP/m" checkout -q "$COMMIT"
  mkdir -p "$OUT/assets"
  for f in panda.xml hand.xml scene.xml LICENSE README.md CHANGELOG.md; do cp "$TMP/m/franka_emika_panda/$f" "$OUT/$f"; done
  cp "$TMP/m/franka_emika_panda/assets/"* "$OUT/assets/"
fi
ok=1
[ "$(digest "$OUT/panda.xml")" = 96ad67da03710f17f798c9478fd9e9efdf24a3bf8359f05e456dd9fb158ea273 ] || { echo "panda.xml differs"; ok=0; }
[ "$(digest "$OUT/hand.xml")" = d2a6539d0fd7c55c75c14f11c78f04505ee33f31d93e6112e3ad7120e5ee786a ] || { echo "hand.xml differs"; ok=0; }
assets=$(cd "$OUT/assets" && $SHA * | $SHA | cut -d' ' -f1)
[ "$assets" = c6f2a4dca4ab6d8a55e612d894d6047aec34df9e539fa4dd4a2c653b5713e8fe ] || { echo "assets differ"; ok=0; }
[ $ok = 1 ] && echo "franka_emika_panda at $COMMIT: checked" || { echo "the fetched model does not match; delete $OUT and run again"; exit 1; }
