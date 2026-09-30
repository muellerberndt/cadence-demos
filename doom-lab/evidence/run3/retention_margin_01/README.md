# Cached navigation retention and target-margin comparison

Lower intrinsic target margin recovered one navigation development success,
but every candidate lost existing Basic successes. **Nothing was deployed.**
More Basic bootstrap replay alone did not solve retention in this fixture.

| Old replay | Intrinsic margin | Basic wins | Basic mean return | Navigation wins | Navigation mean return | Squared parameter displacement |
| --- | --- | --- | --- | --- | --- | --- |
| Initial `ad9` | — | 8/8 | −29.125 | 0/4 | −.210000 | 0 |
| Uniform control | .8 | 4/8 | −215.375 | 0/4 | −.210000 | .260430 |
| Uniform | .08 | 6/8 | −117.875 | 1/4 | +.089625 | .134047 |
| Six Basic / one doors / one navigation | .8 | 5/8 | −189.375 | 0/4 | −.210000 | .201951 |
| Six Basic / one doors / one navigation | .08 | 5/8 | −189.375 | 1/4 | +.089625 | .102564 |

The 116.14-second campaign reused the exact 32 autonomous navigation contexts
and already verified native/novelty branch witnesses from
`../navigation_novelty_01/`. All four batch plans and sources were frozen before
training. The uniform/.8 control reproduced both original admission row lists
and checkpoint hashes, ending in `f7b691`, before variants started; its twelve
new native episode traces also matched the original experiment exactly.

Every arm used two accepted public `Brain.observe_batch(..., source="estimate")`
repairs with sixteen examples each, plus five unadmitted pending examples.
The twenty outputs remain settled Cadence policy patches; there is no new
optimizer, teacher, actor override or fallback. The system's bounded states,
input boundaries, residual readback, native records and feedback repairs are
unchanged. The sample coordinates and native reward vectors are immutable.

The stratified gene deliberately gives all eight old slots to bootstrap
retention: six Basic, one doors and one navigation. Its twelve Basic
presentations replace the uniform sampler's one; it also replaces the control's
later native replay mixture. This tests retained capacity as well as task
coverage, and is not a source-mixture-matched comparison. The .08 target gene
scales newly created intrinsic preference vectors to one tenth their original
magnitude; if an example later replays it keeps that scaled vector. Original
bootstrap labels and original full-margin utility witnesses remain unchanged.

All 48 episodes completed, all 8,887 action queries qualified, and no fallback
acted. The independent verifier checks frozen source/plan hashes, target
arithmetic, task quotas, public admissions, snapshot hashes, all native action
buttons, per-tic reward sums, total 35,502 native tics, and exact control trace
parity. `verification.json` records the result. All four candidates are partial
two-repair lifetimes, and each additionally fails Basic retention; the existing
four-repair promotion requirement was not relaxed.

The uniform/.08 candidate is
`ed7e277b09c6514f296b17544855403049cf49f4a691ee3d22395614c99627b2`.
It is useful diagnostic evidence, not a deployable replacement: it loses
Basic seeds 1220000004 and 1220000005. Its single navigation win is repeated
development evidence from four seeds, not fresh confirmation or general
navigation competence.

The next interpretation is narrower than “use more replay”: old bootstrap
teacher targets do not exactly describe the competent current actor. The
initial `ad9` already disagrees with 9/36 old Basic teacher actions on those
training inputs. Likewise, reducing absolute target magnitude is not a trust
region around the actor's current scores; it can still pull those scores
toward zero. A separately frozen comparison could preserve the current actor's
own qualified scores on retained actual contexts and blend a small preference
change around its current scores. That is a candidate target-orchestration
gene, not a proven remedy. Native goal-credit and longer-horizon evidence must
remain a separate requirement; novelty success alone cannot authorize promotion.

Reproduction source: `../../retention_margin_campaign.py`. Guard tests:
`../../test_retention_margin_campaign.py` (three tests passed locally and on
AWS; original two-batch input JSON parity was also verified before launch).
Independent verifier: `verify.py`, run read-only on the AWS CPU host. Full
plans, models, traces and logs remain in
`/home/ec2-user/doom-v3-20260929/runs/retention_margin_01/` (75 files,
9,360,754 bytes after the verifier was attached), with frozen code under
`code/retention_margin_01/`. The 900-second process-group supervisor exited
normally; no additional cloud resource was provisioned.
