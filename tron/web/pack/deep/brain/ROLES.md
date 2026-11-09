# Neuron roles: Mako Deep

Brain file `deep-g3.npz`. 8074 settled positions from 25 games (seeds 9100000+: against voronoi from both seats, against voronoi20, against itself). Written by `scripts/introspect.py`.

A neuron fires above the midpoint of its own 5th-95th percentile range. Its role is the thresholded event whose presence best matches its firing (phi), or a number it tracks (Pearson r) when that fits clearly better; kept at |phi| or |r| >= 0.3, else mixed. Causal check: on positions where the event holds, the brain is forked and the move read with the neuron silenced (bias -30, held at its floor) and driven (bias +30, held at 1). A role is supported when a clamp changes the move on at least 15% of those positions, at least 3 times the rate for random neurons of the same layer on positions where they fire, and on at least 5 positions; or when it shifts the motor vote the same way on at least 80% of at least 10 positions, by at least 3 times the null's mean shift. A verdict needs a null of at least 20 trials. Groups are judged against as many random neurons with similar firing rates.

Replay check: 6348 replayed moves, 0 different from the first pass; the unclamped fork read a different move than the brain on 0 tested positions.

## L1 (module_0, 256 neurons)

158 with a role at |phi| or |r| >= 0.3; 0 supported by the causal check (of 20 tested); 98 mixed; 0 barely move. Null: one random neuron, silenced or driven, flips the move on 4.8% of random positions and shifts the largest motor vote by 0.0477 on average (800 trials).

Groups (every neuron of the layer with that role, clamped together; null: as many random neurons on random positions):

| role | neurons | causal effect | null flips |
|---|---|---|---|
| fires when there is a long run open to the right | 42 | driving them makes the brain turn right more often (10% -> 100% of these positions) (n=40) | 22% |
| fires when there is a long run open to the left | 26 | driving them makes the brain ride straight on less often (78% -> 0% of these positions) (n=40) | 20% |
| fires when the left is blocked | 23 | driving them: no clear effect (move flips on 8%, largest vote shift +0.070) (n=40), not clear | 8% |
| fires when the riders are walled apart | 14 | silencing them: no clear effect (move flips on 10%, largest vote shift +0.067) (n=40), not clear | 2% |
| fires when the right is blocked | 11 | silencing them: no clear effect (move flips on 2%, largest vote shift -0.029) (n=40), not clear | 10% |
| fires when a wall is within two cells ahead | 5 | silencing them makes the brain ride straight on more often (18% -> 40% of these positions) (n=40) | 10% |
| fires when the opponent is off to the right | 5 | driving them: no clear effect (move flips on 8%, largest vote shift +0.033) (n=40), not clear | 8% |
| fires when the opponent is off to the left | 4 | driving them makes the brain turn left less often (25% -> 12% of these positions) (n=40) | 5% |

Correlated but not supported (untested, or no clear effect of the clamps):

- L1.69: rises near the arena's walls (r = -0.65); tested n=40: move changed 2% silenced, 0% driven
- L1.21: fires when the left is blocked, and when it rides along the arena's edge (phi = +0.64; fires on 87% of positions with the event, 22% without); tested n=40: move changed 0% silenced, 0% driven
- L1.196: fires when the left is blocked, and when the riders are walled apart (phi = +0.62; fires on 95% of positions with the event, 31% without); tested n=40: move changed 0% silenced, 0% driven
- L1.49: fires when the right is blocked, and when the opponent is off to the right (phi = +0.62; fires on 90% of positions with the event, 23% without); tested n=40: move changed 0% silenced, 0% driven
- L1.227: fires when the right is blocked, and when the riders are walled apart (phi = +0.60; fires on 99% of positions with the event, 33% without); tested n=40: move changed 0% silenced, 0% driven
- L1.50: fires when the right is blocked, and when it rides along the arena's edge (phi = +0.60; fires on 90% of positions with the event, 24% without); tested n=40: move changed 5% silenced, 0% driven
- L1.93: fires when the riders are walled apart, and when it rides along the arena's edge (phi = +0.58; fires on 87% of positions with the event, 25% without); tested n=40: move changed 0% silenced, 2% driven
- L1.90: fires when the left is blocked, and when the opponent owns most of the free board (phi = +0.58; fires on 91% of positions with the event, 32% without); tested n=40: move changed 0% silenced, 0% driven
- L1.219: fires when the right is blocked, and when the riders are walled apart (phi = +0.57; fires on 97% of positions with the event, 34% without); tested n=40: move changed 0% silenced, 0% driven
- L1.105: tracks the distance to the nearest wall (r = +0.57); tested n=40: move changed 0% silenced, 0% driven
- L1.201: fires when the left is blocked, and when the teacher would ride straight on (phi = +0.56; fires on 94% of positions with the event, 37% without); tested n=40: move changed 0% silenced, 0% driven
- L1.236: fires when the right is blocked, and when the riders are walled apart (phi = +0.56; fires on 96% of positions with the event, 34% without); tested n=40: move changed 5% silenced, 0% driven
- and 146 more

Mixed (98): no single feature reaches |phi| or |r| 0.3; their best matches are left_blocked (13), opp_right_side (11), apart (11), open_left (10).

## L2 (module_1, 128 neurons)

86 with a role at |phi| or |r| >= 0.3; 10 supported by the causal check (of 20 tested); 42 mixed; 0 barely move. Null: one random neuron, silenced or driven, flips the move on 0.8% of random positions and shifts the largest motor vote by 0.0229 on average (795 trials).

| neuron | role | evidence | causal effect |
|---|---|---|---|
| L2.36 | rises as the right closes in | r = -0.63 | silencing it tilts the vote away from riding straight on (motor -0.064, the same way on 100% of these positions; the move flips on 5%) (n=40) |
| L2.76 | fires when the left is blocked, and when the riders are walled apart | phi = +0.62; fires on 99% of positions with the event, 36% without | silencing it tilts the vote away from riding straight on (motor -0.038, the same way on 100% of these positions; the move flips on 0%) (n=40) |
| L2.26 | rises as the left closes in | r = -0.59 | silencing it tilts the vote away from riding straight on (motor -0.061, the same way on 100% of these positions; the move flips on 0%) (n=40) |
| L2.113 | fires when the left is blocked | phi = +0.56; fires on 96% of positions with the event, 39% without | silencing it tilts the vote away from riding straight on (motor -0.041, the same way on 100% of these positions; the move flips on 0%) (n=40) |
| L2.107 | fires when the right is blocked, and when the left is open | phi = +0.49; fires on 98% of positions with the event, 45% without | silencing it tilts the vote away from riding straight on (motor -0.046, the same way on 100% of these positions; the move flips on 2%) (n=40) |
| L2.34 | rises near the arena's walls | r = -0.49 | silencing it tilts the vote away from riding straight on (motor -0.024, the same way on 98% of these positions; the move flips on 2%) (n=40) |
| L2.52 | tracks the room to the right | r = +0.49 | silencing it tilts the vote away from turning right (motor -0.022, the same way on 100% of these positions; the move flips on 2%) (n=40) |
| L2.75 | fires when a wall is within two cells ahead | phi = +0.48; fires on 56% of positions with the event, 7% without | silencing it tilts the vote away from turning right (motor -0.032, the same way on 100% of these positions; the move flips on 5%) (n=40) |
| L2.4 | tracks the room to the right | r = +0.47 | silencing it tilts the vote away from turning right (motor -0.105, the same way on 98% of these positions; the move flips on 10%) (n=40) |
| L2.61 | tracks the room to the left | r = +0.46 | silencing it makes the brain turn left less often (85% -> 72% of these positions) (n=40) |

Groups (every neuron of the layer with that role, clamped together; null: as many random neurons on random positions):

| role | neurons | causal effect | null flips |
|---|---|---|---|
| fires when the right is open | 15 | driving them makes the brain turn right more often (10% -> 65% of these positions) (n=40), not clear | 22% |
| fires when the left is open | 14 | driving them makes the brain turn left more often (15% -> 82% of these positions) (n=40) | 20% |
| fires when there is a long run open to the left | 12 | driving them makes the brain turn left more often (18% -> 28% of these positions) (n=40), not clear | 15% |
| fires when a wall is within two cells ahead | 10 | silencing them tilts the vote towards riding straight on (motor +0.163, the same way on 100% of these positions; the move flips on 5%) (n=40) | 8% |
| fires when the riders still share a room | 7 | driving them makes the brain ride straight on more often (75% -> 90% of these positions) (n=40) | 2% |
| fires when the way ahead is open | 3 | silencing them makes the brain ride straight on less often (75% -> 0% of these positions) (n=40) | 8% |
| fires when the right is blocked | 3 | silencing them tilts the vote away from riding straight on (motor -0.095, the same way on 100% of these positions; the move flips on 5%) (n=40) | 8% |
| fires when there is a long run open to the right | 3 | driving them: no clear effect (move flips on 0%, largest vote shift +0.086) (n=40), not clear | 8% |

Correlated but not supported (untested, or no clear effect of the clamps):

- L2.114: fires when the right is open, and when it is away from the edges (phi = -0.65; fires on 1% of positions with the event, 73% without); tested n=40: move changed 0% silenced, 0% driven
- L2.84: fires when the left is open, and when the riders still share a room (phi = -0.54; fires on 5% of positions with the event, 58% without); tested n=40: move changed 0% silenced, 0% driven
- L2.60: fires when the right is open, and when the riders still share a room (phi = -0.53; fires on 6% of positions with the event, 64% without); tested n=40: move changed 0% silenced, 0% driven
- L2.57: fires when the left is open (phi = -0.52; fires on 12% of positions with the event, 65% without); tested n=40: move changed 0% silenced, 0% driven
- L2.19: fires when the right is open (phi = -0.49; fires on 15% of positions with the event, 69% without); tested n=40: move changed 2% silenced, 0% driven
- L2.90: fires when the right is open (phi = -0.48; fires on 4% of positions with the event, 56% without); tested n=40: move changed 0% silenced, 0% driven
- L2.10: fires when the left is open (phi = -0.47; fires on 15% of positions with the event, 64% without); tested n=40: move changed 0% silenced, 0% driven
- L2.42: fires when the left is open (phi = -0.47; fires on 16% of positions with the event, 65% without); tested n=40: move changed 0% silenced, 0% driven
- L2.120: fires when the riders still share a room, and when the way ahead is open (phi = -0.47; fires on 24% of positions with the event, 73% without); tested n=40: move changed 0% silenced, 2% driven
- L2.80: fires when the left is open, and when the teacher would turn (phi = -0.47; fires on 3% of positions with the event, 48% without); tested n=40: move changed 2% silenced, 0% driven
- L2.87: fires when there is a long run open to the left (phi = +0.46; fires on 49% of positions with the event, 7% without); not tested
- L2.98: tracks the room to the left (r = +0.46); not tested
- and 64 more

Mixed (42): no single feature reaches |phi| or |r| 0.3; their best matches are right_blocked (9), left_blocked (8), open_left (5), opp_left_side (5).

## L3 (association, 32 neurons)

32 with a role at |phi| or |r| >= 0.3; 2 supported by the causal check (of 20 tested); 0 mixed; 0 barely move. Null: one random neuron, silenced or driven, flips the move on 4.1% of random positions and shifts the largest motor vote by 0.1048 on average (800 trials).

| neuron | role | evidence | causal effect |
|---|---|---|---|
| L3.18 | tracks the room to the left | r = +0.44 | silencing it makes the brain turn left less often (92% -> 72% of these positions) (n=40) |
| L3.28 | tracks the room to the left | r = +0.44 | silencing it makes the brain turn left less often (90% -> 68% of these positions) (n=40) |

Groups (every neuron of the layer with that role, clamped together; null: as many random neurons on random positions):

| role | neurons | causal effect | null flips |
|---|---|---|---|
| fires when the way ahead is open | 11 | silencing them makes the brain ride straight on less often (75% -> 0% of these positions) (n=40) | 12% |
| fires when a wall is within two cells ahead | 10 | silencing them makes the brain turn right less often (50% -> 0% of these positions) (n=40) | 40% |

Correlated but not supported (untested, or no clear effect of the clamps):

- L3.9: tracks the room to the right (r = +0.57); tested n=40: move changed 0% silenced, 5% driven
- L3.20: rises as the left closes in (r = -0.57); tested n=40: move changed 0% silenced, 0% driven
- L3.12: rises as the right closes in (r = -0.57); tested n=40: move changed 0% silenced, 0% driven
- L3.1: rises as the left closes in (r = -0.57); tested n=40: move changed 0% silenced, 0% driven
- L3.22: rises as the left closes in (r = -0.55); tested n=40: move changed 2% silenced, 0% driven
- L3.23: rises as the right closes in (r = -0.55); tested n=40: move changed 0% silenced, 0% driven
- L3.21: rises as the right closes in (r = -0.54); tested n=40: move changed 0% silenced, 0% driven
- L3.11: rises as the right closes in (r = -0.47); tested n=40: move changed 0% silenced, 0% driven
- L3.27: fires when a wall is within two cells ahead (phi = +0.45; fires on 61% of positions with the event, 10% without); tested n=40: move changed 2% silenced, 0% driven
- L3.31: fires when a wall is within two cells ahead (phi = +0.45; fires on 62% of positions with the event, 10% without); tested n=40: move changed 0% silenced, 0% driven
- L3.3: fires when the way ahead is open (phi = -0.45; fires on 33% of positions with the event, 87% without); tested n=40: move changed 0% silenced, 8% driven
- L3.10: fires when a wall is within two cells ahead (phi = +0.45; fires on 60% of positions with the event, 10% without); tested n=40: move changed 5% silenced, 12% driven
- and 18 more

## motor (motor, 3 neurons)

The three motor neurons are the moves (left, straight, right); the move is read from them.

0 with a role at |phi| or |r| >= 0.3; 0 supported by the causal check (of 0 tested); 0 mixed; 0 barely move.
