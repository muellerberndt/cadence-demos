# Cadence demo guidance

Read this repository's `README.md` and the affected demo's README first. Follow
the current Cadence README/AGENTS and
[world-model guide](https://github.com/muellerberndt/cadence/blob/main/docs/world-model.md)
when designing a new brain or explaining the intended operating model.

- The target is a continuing equilibrium world-model brain, with bounded
  reciprocal patches, local state and ports, readback, records and the common
  local repair law. Use `Brain.compose` as the primary integrated entry. Deep
  System 1 is the foundation; optional System 2 returns recursive feedback in
  the same settlement. These are functional roles, not biological guarantees.
- Bootstrap reusable knowledge. Normal behavior reads durable knowledge and
  retains useful context; witnessed mismatches or failures can admit repair.
  Do not teach users to recreate a brain, reset its memory or force a label
  update for every new input as the general Cadence recipe.
- Declare each memory's writes, reads, capacity, retention and reset boundary.
  Identify actual observations, executed actions, corrections and pending
  transactions so delay, retry and save/load preserve the correct event and
  exactly-once custody. Private forecasts do not become witnessed experience.
- Preserve the identity of existing demos. Population-solver examples and
  `RecordPatchNet` have their own equations and historical evidence; their
  success does not certify the integrated common brain. Existing code that
  updates every transition or uses specialized readouts must be described
  honestly, rather than renamed as demand-driven equilibrium cognition.
- Independent-input classifiers, fresh-start models, always-repair schedules,
  memory ablations, MLPs and transformers can be declared controls. Match
  information and experience where claiming superiority. Disclose application
  controllers, thresholds and architecture as controls or candidate genes.
- Measure held-out behavior, acquired knowledge, correction benefit and
  retention alongside full resource costs. Separate bootstrap from ordinary
  continuation, memory and witnessed repair. Charge refused/private/replayed
  work. Low recurring cost is a target. Low residual is neither world truth
  nor physical energy; `pass`/`WIN` labels certify only their declared tests,
  not a guaranteed performance advantage or general human competence.
- Documentation edits must not rewrite frozen protocols, trained models,
  source-bound receipts, parity fixtures or historical runtime identities.
  New evidence requires a new source-bound run. Running a published example
  or finding a guidance gap does not authorize a long campaign or cloud spend.
