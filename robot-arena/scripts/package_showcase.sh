#!/bin/sh
# Zip the Showcase League page for upload (Lovable or any static host): the app folder without
# node_modules and dist. Usage: scripts/package_showcase.sh [out.zip]
set -e
cd "$(dirname "$0")/.."
OUT=${1:-$HOME/Downloads/cadence-showcase-league.zip}
rm -f "$OUT"
(cd showcase-app && zip -qr "$OUT" . -x "node_modules/*" -x "dist/*" -x ".DS_Store")
echo "$OUT ($(du -h "$OUT" | cut -f1))"
