#!/bin/sh
# The Cadence Showcase League, end to end: a fresh league of the stock robots and two random
# baselines, the accelerated nursery with its controls, a run of ranked royales, the league page.
# Usage: scripts/showcase.sh [league-dir] [nursery-moments] [fights]
set -e
cd "$(dirname "$0")/.."
LEAGUE=${1:-league}; MOMENTS=${2:-60000}; FIGHTS=${3:-40}
PY=.venv/bin/python
if [ -e "$LEAGUE/league.json" ]; then echo "$LEAGUE exists; move it aside first"; exit 1; fi
$PY -m arena --league "$LEAGUE" init
$PY -m arena --league "$LEAGUE" nursery --moments "$MOMENTS" --workers 8 --controls --quiet
$PY -m arena --league "$LEAGUE" royale --fights "$FIGHTS" --size 6 --quiet
$PY -m arena --league "$LEAGUE" ladder
$PY -m arena --league "$LEAGUE" dashboard
