#!/usr/bin/env bash
# Both training routes at a size that finishes in minutes, from tron/ (writes runs/smoke/...).
# Checks that every stage runs end to end on the installed cadence-net; it raises no strong brain.
#   bash scripts/smoke.sh [flat|deep|all]
set -euo pipefail
cd "$(dirname "$0")/.."
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1
export TRON_MAX_PAIRS=4                      # every reading at most 4 mirror pairs
export TRON_CORPUS=runs/r3/corpus3.jsonl
PY="${PY:-python}"
FLAT=web/pack/flat/brain/brain.npz          # the shipped flat brain: the deep route's donor
WHAT="${1:-all}"
step() { echo "== $1 $(date +%T)"; }

step data
[ -e runs/r3/turnset.npz ] || $PY -W ignore scripts/prepare.py --games 64 --scenario-games 30 --turn-games 3 --workers 4

if [ "$WHAT" != deep ]; then
  R=runs/smoke/flat
  step "1 genetic search"
  $PY -W ignore scripts/ga3.py --out $R/ga --pop 4 --gens 1 --games 1 --finalists 1 --val-games 1 --scale 0.05 \
      --workers 4 --elite 1 --fix sense=field
  step "2 school"
  $PY -W ignore scripts/phaseb.py --arm instruct --genome $R/ga/summary.json --rank 0 --seed 23 --out $R/school \
      --rows 8 --watch 40 --stage2 40 --stage3 40 --every 40 --games 1 --workers 2 --backend cpu \
      --scenarios runs/r3/scenarios.json
  S=$(ls $R/school/brain-m*.npz | sort -t m -k3 -n | tail -1)
  step "3 expert iteration from $S"
  $PY -W ignore scripts/phasec.py --arm exit --start "$S" --sense field --seed 32 --rows 8 --workers 2 --backend cpu \
      --gate-voronoi --moments 60 --gen 30 --every 30 --pairs 2 --gate-pairs 2 --voronoi-pairs 4 --out $R/exit
  E=$(ls $R/exit/brain-m*.npz | sort -t m -k3 -n | tail -1)
  step "4 selection from $E"
  $PY -W ignore scripts/select_exit.py --start "$E" --out $R/selection --children 2 --depth 3 --moments 20 --rows 8 \
      --gate-pairs 2 --finalists 1 --gens 1 --workers 4 --check-pairs 4
  step "5 self-play from the shipped flat brain"
  $PY -W ignore scripts/select_exit.py --start $FLAT --out $R/selfplay --children 2 --eta-divs 12,18 --priors 8 --depth 3 \
      --moments 20 --rows 8 --base-eta 0.0009 --gens 1 --workers 4 --sprt --batch 2 --cap 4 --survivors 2 \
      --selfplay --anchors bot:voronoi,bot:voronoi3 --anchor-share 0.5 --softs "" --crit-w 2.5 --exploiter \
      --train-half --selves 2 --check-pairs 4 --read-pairs 2
fi

if [ "$WHAT" != flat ]; then
  R=runs/smoke/deep
  step "1 function-preserving growth of the flat brain"
  $PY -W ignore scripts/net2net.py --donor $FLAT --out $R/n2n --layouts deep3n --eps 0.2
  step "3 skip halved, the deep pathway distilled"
  $PY -W ignore scripts/skip_scale.py $R/n2n/skip-eps0.2-layoutdeep3n.npz 0.5 $R/n2n/stage1-start.npz
  $PY -W ignore scripts/deep_raise.py --init load --start $R/n2n/stage1-start.npz --mako $FLAT --teacher mako \
      --l1-rate 0 --skip-rate 0 --eta 0.0009 --moments 40 --every 20 --rows 8 --eval-workers 2 --backend cpu --out $R/stage1
  step "4 the next annealing stage starts"
  $PY -W ignore scripts/skip_scale.py $R/stage1/final.npz 0.5 $R/n2n/stage2-start.npz
  step "the deep pathway's share"
  $PY -W ignore scripts/deep_ablation.py $R/n2n/stage2-start.npz
fi
step done
