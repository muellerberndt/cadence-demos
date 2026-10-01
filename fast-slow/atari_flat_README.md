# Flat Freeway bootstrap

This bounded Cadence 0.60 candidate smoke learns Freeway's existing constant-UP
teacher, then plays complete native ALE episodes. It tests quick acquisition and
qualified execution of a routine. Constant UP needs no visual strategy, so this
is not evidence of learned perception, reward learning, or recursive advantage.
The website server, JavaScript engine and original checkpoints are unchanged.

The public layout has one input-only column: three action patches, 843 inputs
and 2,532 parameters. Inputs are current RGB pixels pooled to 21×20 luminance,
their difference from the preceding observation, and the last executed action.
Only training rows determine normalization. No code path reads RAM. Every patch
uses the common settlement and admission law; the collector supplies no direct
policy readout or unqualified action fallback.

Two teacher episodes supply 512 rows each. All three model seeds see the same
shuffled 64 batches of 16 actual executed-action witnesses. A separate 512-row
episode measures unclamped action agreement before and after training. Native
evaluation uses three further environment seeds, the frozen learned parameters,
one qualified query followed by one serial emulator step, and complete action,
observation-hash, reward and termination records. Matched constant-UP and NOOP
episodes are retained. Native trials stop on refusal; truncation or a step cap
cannot count as a completed game.

The [frozen protocol](evidence/20261001/atari-flat-bootstrap/protocol.json) fixes
all seeds, row order, budgets and gates before collection. Each arm allows 120
seconds for acquisition and held-out queries, 600 seconds for native play and a
900-second outer process cap. At most three single-threaded workers run. The
gates require all 64 admissions, qualified required calls, at least 95% held-out
agreement, and three completed positive-score games reaching at least 80% of
the matching teacher's score. Wall time and 15 Hz deadline misses are reported
separately from accuracy.

The [independent verification](evidence/20261001/atari-flat-bootstrap/verification.json)
passed all three seeds. Acquisition took 10.71–10.83 seconds per brain; all 192
admissions were accepted. Held-out agreement rose from 29.69–32.23% to 100%.
Each learned brain scored 26, 27 and 23 on the three native seeds, matching the
teacher; NOOP scored zero. All nine learned episodes ended naturally, with no
refusal or truncation. Native observation-to-dispatch p95 was 7.18–7.24 ms,
including receipt-writing overhead; none of the 18,258 learned decisions missed
the 66.7 ms budget. These measurements are from the recorded CPU host and are
not a browser performance claim.

Verification exactly re-executed all 21,522 recorded numerical calls, including
the 192 admissions, and all 18,258 learned body transitions. It also replayed
the collection and six baseline games, checked every result field and parameter
hash, matched saved checkpoints, and recalculated gates, work and latency.
An earlier collector attempt used a string where the event API requires an
integer. It stopped before learning; its source and failed receipts are retained,
and its 1,536 returned newborn queries were independently replayed. The corrected
attempt changed that integration call and receipt encoding, not seeds, exposure,
learning law or gates.

Run on the remote host holding ALE, its bundled Freeway ROM, and the pinned
Cadence candidate. Full ledgers and datasets stay on AWS; only small receipts
belong in the checkout.

```sh
export PYTHONPATH=/path/to/frozen-cadence/src
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
python atari_flat_bootstrap.py freeze /path/to/new-run
python atari_flat_bootstrap.py launch /path/to/new-run
python verify_atari_flat_bootstrap.py --root /path/to/new-run --out /path/to/verification.json
python -m pytest -q test_atari_flat_bootstrap.py test_verify_atari_flat_bootstrap.py
```

The two attempts and verifiers are preserved in the
[verified archive receipt](evidence/20261001/atari-flat-bootstrap/cadence-060-flat-atari-archive-receipt.json).
No successful seed was selected for reporting, and no Atari website migration
or Cadence release qualification follows from this routine-only smoke.
