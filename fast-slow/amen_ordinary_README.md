# Ordinary Amen settlement diagnostics

These experiments examine why a hidden ordinary layer makes Amen preparation expensive, then test two private numerical solvers against exactly the same first-batch energy. They do not establish musical acquisition, recovery, recursive advantage or a deployable model. No candidate endpoint was inserted into a `Brain` checkpoint or counted as a public admission.

The frozen input is the first uniform 32-row batch for seed 1103 from the startup curriculum. The ordinary graph has 585 input samples, 64 hidden patches and 71 output patches: 47,870 parameters, with input/state contacts and no residual contacts. Output witnesses, private row states, parameter anchors, box bounds and tolerance remain the same. The mean residual and state-prior energies scale by 1/32; the parameter anchor occurs once. Whole-graph qualification uses each row's unaveraged state gradient.

## Verified observations

The first 115-second probes at widths 64 and 256 both timed out during their first admission. Those failed attempts remain in the archive. The two subsequent width-64 calls, plain and profiled, both qualified with identical complete results and final snapshots. The plain public admission took 121.057 seconds. Profiling attributed 112.956 of 128.276 seconds to tensor energy/gradient evaluation; reference checks took 4.753 seconds. There was no reference refinement sweep or restart.

| Method | Solve seconds | Whole candidate case seconds | Accepted steps | Energy/gradient evaluations | Additional Jv/Jᵀ products | Reference stationarity |
|---|---:|---:|---:|---:|---:|---:|
| Native tensor public admission | 121.057 | 122.064 including setup/query | 5,161 | 11,958 including qualification | 0 | 8.421e-7 |
| Diagonal GN preconditioner with spectral step | 12.576 | 16.877 including equation checks | 3,195 | 7,515 during solving | 0 | 8.918e-7 |
| Matrix-free GN with fixed 32-step CG limit | 17.255 | 21.561 including equation checks | 439 | 647 during solving | 14,048 of each | 9.853e-7 |

All three reference energies are approximately 2.174179645. The candidates use NumPy float64 dense blocks with one OpenBLAS thread; the native baseline uses the existing sparse Torch float64 path with four threads. These times combine kernel and iteration changes and are not a method-only or matched-compute speed claim. GN uses fewer outer steps but more operator work and took longer than the diagonal candidate. Each candidate had an independent 600-second cap.

Both candidate methods initially saved their numerical endpoints but failed when a NumPy boolean reached JSON serialization. That entire failed attempt is retained. A receipt-only conversion fix was frozen separately and both methods repeated. The original and repeated endpoint bytes and complete iteration ledgers match exactly. Original endpoints independently qualify, but their complete wall-time receipts were lost and are not reconstructed.

Eight pure founder queries also compare a free future head with the same actual target clamped. On four fixed rows, the hidden-state RMS shift was 0.05238–0.06161; hidden residual RMS changed from 0.000364–0.000536 to 0.05237–0.06161. This is ordinary coupled backreaction under a teaching boundary. It is neither historical forecast surprise nor proof of the cause of poor free musical generation.

## Custody and reproduction

- [Native runtime verification](evidence/20261001/amen-ordinary-runtime/verification.json) contains exact plain/profile parity, public admission cursors, independent reference energy/projected-gradient checks and the earlier censored calls.
- [Candidate protocol](evidence/20261001/amen-solvers/protocol.json) binds the complete selected inputs/clamps, initial and baseline snapshots, original data/source hashes, both fixed methods and the failed first attempt.
- [Candidate verification](evidence/20261001/amen-solvers/verification.json) independently requalifies original and repeated endpoints against the frozen scalar engine, original anchors and exact actual clamps. It does not replay the numerical learning trajectories.
- [Original failed execution](evidence/20261001/amen-solvers/failed-attempt/execution.json) retains both serialization failures.
- The complete source, arrays, ledgers and archives remain on the catalogued Amen AWS EBS volume. Compact archive receipts identify exact hashes and members. Existing archives and run directories must not be overwritten.

The collector commands used on the existing immutable ordinary root were:

```sh
PYTHONPATH=core/src:collector-v2:collector OPENBLAS_NUM_THREADS=1 \
  /home/ec2-user/venv/bin/python collector-v2/amen_solver_candidates.py \
  freeze "$ORDINARY_ROOT" --out "$ORDINARY_ROOT/acceleration-v2"
PYTHONPATH=core/src:collector-v2:collector OPENBLAS_NUM_THREADS=1 \
  /home/ec2-user/venv/bin/python collector-v2/amen_solver_candidates.py \
  launch "$ORDINARY_ROOT" --out "$ORDINARY_ROOT/acceleration-v2"
PYTHONPATH=core/src:collector-v2:collector OPENBLAS_NUM_THREADS=1 \
  /home/ec2-user/venv/bin/python collector-v2/verify_amen_solver_candidates.py \
  "$ORDINARY_ROOT" --out "$ORDINARY_ROOT/acceleration-v2"
```

Here `ORDINARY_ROOT` was `/home/ec2-user/cadence-060-ordinary-amen-20261001`. These commands create receipts exclusively; repeat work needs a fresh output directory and a fresh source-bound protocol. The original source version is included in the archive because the maintained collector now contains the receipt fix.

Focused tests cover scalar-reference derivatives, Jv/Jᵀ adjoints, finite differences at interior and active-bound points, explicit Jacobian column norms, batch scaling, parameter anchors, true clamps, source mutation, refused unsupported contacts, JSON scalar custody and no public mutation. The next integration prerequisite is an experimental engine using the existing public `observe_batch` admission/rollback path, with unchanged reference qualification and full custody tests. This evidence alone does not authorize a default solver change.
