#!/bin/bash
# Fetch the freely distributable Doom shareware IWAD (v1.9) and verify it.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p wads
if [ -f wads/doom1.wad ]; then echo "wads/doom1.wad already present"; exit 0; fi
curl -sL -o wads/doom1.wad \
  https://github.com/Akbar30Bill/DOOM_wads/raw/master/doom1.wad
echo "f0cefca49926d00903cf57551d901abe  wads/doom1.wad" | md5sum -c - 2>/dev/null \
  || [ "$(md5 -q wads/doom1.wad 2>/dev/null)" = "f0cefca49926d00903cf57551d901abe" ]
echo "doom1.wad verified (md5 f0cefca49926d00903cf57551d901abe)"
