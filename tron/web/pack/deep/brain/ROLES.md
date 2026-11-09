# Neuron roles: Mako Deep

Brain file `deep-c2.npz`. 7928 settled positions from 25 games (seeds 9100000+: against voronoi from both seats, against voronoi20, against itself). Written by `scripts/introspect.py`.

A neuron fires above the midpoint of its own 5th-95th percentile range. Its role is the thresholded event whose presence best matches its firing (phi), or a number it tracks (Pearson r) when that fits clearly better; kept at |phi| or |r| >= 0.3, else mixed. Causal check: on positions where the event holds, the brain is forked and the move read with the neuron silenced (bias -30, held at its floor) and driven (bias +30, held at 1). A role is supported when a clamp changes the move on at least 15% of those positions, at least 3 times the rate for random neurons of the same layer on positions where they fire, and on at least 5 positions; or when it shifts the motor vote the same way on at least 80% of at least 10 positions, by at least 3 times the null's mean shift. A verdict needs a null of at least 20 trials. Groups are judged against as many random neurons with similar firing rates.

Replay check: 6131 replayed moves, 0 different from the first pass; the unclamped fork read a different move than the brain on 0 tested positions.

## L1 (module_0, 256 neurons)

164 with a role at |phi| or |r| >= 0.3; 0 supported by the causal check (of 20 tested); 92 mixed; 0 barely move. Null: one random neuron, silenced or driven, flips the move on 3.3% of random positions and shifts the largest motor vote by 0.0446 on average (788 trials).

Groups (every neuron of the layer with that role, clamped together; null: as many random neurons on random positions):

| role | neurons | causal effect | null flips |
|---|---|---|---|
| fires when there is a long run open to the right | 40 | driving them makes the brain turn right more often (10% -> 100% of these positions) (n=40) | 25% |
| fires when there is a long run open to the left | 28 | driving them makes the brain ride straight on less often (78% -> 0% of these positions) (n=40) | 25% |
| fires when the left is blocked | 24 | driving them: no clear effect (move flips on 8%, largest vote shift +0.063) (n=40), not clear | 12% |
| fires when the right is blocked | 14 | silencing them: no clear effect (move flips on 2%, largest vote shift -0.050) (n=40), not clear | 5% |
| fires when the riders are walled apart | 12 | driving them: no clear effect (move flips on 12%, largest vote shift -0.068) (n=40), not clear | 10% |
| fires when the opponent is off to the right | 6 | driving them: no clear effect (move flips on 10%, largest vote shift +0.085) (n=40), not clear | 8% |
| fires when a wall is within two cells ahead | 5 | silencing them makes the brain ride straight on more often (20% -> 42% of these positions) (n=40) | 30% |
| fires when the opponent is in front | 4 | silencing them tilts the vote away from riding straight on (motor -0.044, the same way on 95% of these positions; the move flips on 2%) (n=40) | 2% |

Correlated but not supported (untested, or no clear effect of the clamps):

- L1.69: rises near the arena's walls (r = -0.65); tested n=40: move changed 0% silenced, 0% driven
- L1.49: fires when the right is blocked, and when the opponent is off to the right (phi = +0.65; fires on 93% of positions with the event, 23% without); tested n=40: move changed 0% silenced, 0% driven
- L1.50: fires when the right is blocked, and when it rides along the arena's edge (phi = +0.63; fires on 91% of positions with the event, 24% without); tested n=40: move changed 2% silenced, 0% driven
- L1.196: fires when the left is blocked, and when it rides along the arena's edge (phi = +0.62; fires on 95% of positions with the event, 31% without); tested n=40: move changed 0% silenced, 0% driven
- L1.21: fires when the left is blocked, and when it rides along the arena's edge (phi = +0.62; fires on 86% of positions with the event, 23% without); tested n=40: move changed 0% silenced, 0% driven
- L1.227: fires when the right is blocked, and when the opponent is off to the right (phi = +0.62; fires on 99% of positions with the event, 33% without); tested n=40: move changed 0% silenced, 0% driven
- L1.188: fires when the right is blocked, and when the riders are walled apart (phi = +0.58; fires on 95% of positions with the event, 33% without); tested n=40: move changed 0% silenced, 0% driven
- L1.219: fires when the right is blocked, and when the riders are walled apart (phi = +0.58; fires on 97% of positions with the event, 35% without); tested n=40: move changed 0% silenced, 0% driven
- L1.105: tracks the distance to the nearest wall (r = +0.57); tested n=40: move changed 0% silenced, 0% driven
- L1.130: fires when the left is blocked (phi = +0.56; fires on 76% of positions with the event, 19% without); tested n=40: move changed 2% silenced, 0% driven
- L1.157: tracks the distance to the nearest wall (r = +0.56); tested n=40: move changed 0% silenced, 0% driven
- L1.236: fires when the right is blocked, and when the riders are walled apart (phi = +0.56; fires on 96% of positions with the event, 36% without); tested n=40: move changed 2% silenced, 0% driven
- and 152 more

Mixed (92): no single feature reaches |phi| or |r| 0.3; their best matches are opp_right_side (13), apart (12), left_blocked (10), big_territory (9).

## L2 (module_1, 128 neurons)

91 with a role at |phi| or |r| >= 0.3; 8 supported by the causal check (of 20 tested); 37 mixed; 0 barely move. Null: one random neuron, silenced or driven, flips the move on 1.6% of random positions and shifts the largest motor vote by 0.0318 on average (800 trials).

| neuron | role | evidence | causal effect |
|---|---|---|---|
| L2.76 | fires when the left is blocked | phi = +0.66; fires on 99% of positions with the event, 32% without | silencing it tilts the vote away from riding straight on (motor -0.037, the same way on 100% of these positions; the move flips on 0%) (n=40) |
| L2.36 | rises as the right closes in | r = -0.64 | silencing it tilts the vote away from riding straight on (motor -0.042, the same way on 100% of these positions; the move flips on 0%) (n=40) |
| L2.113 | fires when the left is blocked | phi = +0.60; fires on 96% of positions with the event, 34% without | silencing it tilts the vote away from riding straight on (motor -0.040, the same way on 100% of these positions; the move flips on 0%) (n=40) |
| L2.26 | rises as the left closes in | r = -0.59 | silencing it tilts the vote away from riding straight on (motor -0.068, the same way on 100% of these positions; the move flips on 0%) (n=40) |
| L2.107 | fires when the right is blocked, and when the left is open | phi = +0.53; fires on 98% of positions with the event, 41% without | silencing it tilts the vote away from turning left (motor -0.044, the same way on 100% of these positions; the move flips on 0%) (n=40) |
| L2.4 | tracks the room to the right | r = +0.47 | silencing it makes the brain turn right less often (92% -> 80% of these positions) (n=40) |
| L2.61 | tracks the room to the left | r = +0.46 | silencing it tilts the vote away from turning left (motor -0.120, the same way on 100% of these positions; the move flips on 10%) (n=40) |
| L2.40 | tracks the room to the right | r = +0.46 | silencing it makes the brain turn right less often (75% -> 55% of these positions) (n=40) |

Groups (every neuron of the layer with that role, clamped together; null: as many random neurons on random positions):

| role | neurons | causal effect | null flips |
|---|---|---|---|
| fires when the right is open | 19 | driving them makes the brain turn right more often (10% -> 80% of these positions) (n=40) | 10% |
| fires when the left is open | 15 | driving them makes the brain turn left more often (15% -> 80% of these positions) (n=40) | 15% |
| fires when there is a long run open to the left | 13 | driving them: no clear effect (move flips on 8%, largest vote shift -0.127) (n=40), not clear | 25% |
| fires when a wall is within two cells ahead | 9 | driving them makes the brain ride straight on less often (20% -> 0% of these positions) (n=40) | 2% |
| fires when there is a long run open to the right | 4 | driving them: no clear effect (move flips on 8%, largest vote shift +0.178) (n=40), not clear | 12% |
| fires when the riders still share a room | 4 | driving them makes the brain ride straight on more often (75% -> 88% of these positions) (n=40) | 0% |
| fires when the way ahead is open | 3 | silencing them makes the brain ride straight on less often (75% -> 0% of these positions) (n=40) | 5% |
| fires when the right is blocked | 3 | silencing them tilts the vote away from riding straight on (motor -0.071, the same way on 100% of these positions; the move flips on 0%) (n=40) | 0% |

Correlated but not supported (untested, or no clear effect of the clamps):

- L2.114: fires when the right is open (phi = -0.69; fires on 2% of positions with the event, 76% without); tested n=40: move changed 0% silenced, 0% driven
- L2.84: fires when the left is open (phi = -0.55; fires on 5% of positions with the event, 60% without); tested n=40: move changed 0% silenced, 0% driven
- L2.60: fires when the right is open, and when the riders still share a room (phi = -0.53; fires on 6% of positions with the event, 63% without); tested n=40: move changed 0% silenced, 0% driven
- L2.57: fires when the left is open (phi = -0.52; fires on 11% of positions with the event, 65% without); tested n=40: move changed 0% silenced, 0% driven
- L2.19: fires when the right is open (phi = -0.52; fires on 15% of positions with the event, 71% without); tested n=40: move changed 0% silenced, 0% driven
- L2.103: fires when the right is open, and when the opponent is off to the left (phi = -0.51; fires on 0% of positions with the event, 53% without); tested n=40: move changed 0% silenced, 2% driven
- L2.90: fires when the right is open (phi = -0.49; fires on 4% of positions with the event, 57% without); tested n=40: move changed 0% silenced, 0% driven
- L2.52: tracks the room to the right (r = +0.49); tested n=40: move changed 0% silenced, 5% driven
- L2.75: fires when a wall is within two cells ahead (phi = +0.48; fires on 56% of positions with the event, 7% without); tested n=40: move changed 0% silenced, 0% driven
- L2.34: rises near the arena's walls (r = -0.48); tested n=40: move changed 0% silenced, 0% driven
- L2.80: fires when the left is open (phi = -0.47; fires on 3% of positions with the event, 48% without); tested n=40: move changed 0% silenced, 0% driven
- L2.42: fires when the left is open (phi = -0.47; fires on 16% of positions with the event, 64% without); tested n=40: move changed 0% silenced, 0% driven
- and 71 more

Mixed (37): no single feature reaches |phi| or |r| 0.3; their best matches are left_blocked (8), right_blocked (8), big_territory (7), open_left (3).

## L3 (association, 32 neurons)

32 with a role at |phi| or |r| >= 0.3; 4 supported by the causal check (of 20 tested); 0 mixed; 0 barely move. Null: one random neuron, silenced or driven, flips the move on 5.1% of random positions and shifts the largest motor vote by 0.1076 on average (800 trials).

| neuron | role | evidence | causal effect |
|---|---|---|---|
| L3.17 | tracks the room to the right | r = +0.45 | silencing it makes the brain turn right less often (95% -> 75% of these positions) (n=40) |
| L3.0 | tracks the room to the right | r = +0.45 | silencing it makes the brain turn right less often (88% -> 70% of these positions) (n=40) |
| L3.10 | fires when a wall is within two cells ahead | phi = +0.45; fires on 60% of positions with the event, 10% without | driving it makes the brain ride straight on less often (20% -> 5% of these positions) (n=40) |
| L3.28 | tracks the room to the left | r = +0.44 | silencing it makes the brain turn left less often (95% -> 70% of these positions) (n=40) |

Groups (every neuron of the layer with that role, clamped together; null: as many random neurons on random positions):

| role | neurons | causal effect | null flips |
|---|---|---|---|
| fires when the way ahead is open | 11 | silencing them makes the brain ride straight on less often (75% -> 0% of these positions) (n=40) | 5% |
| fires when a wall is within two cells ahead | 7 | silencing them makes the brain ride straight on more often (20% -> 40% of these positions) (n=40) | 18% |

Correlated but not supported (untested, or no clear effect of the clamps):

- L3.9: tracks the room to the right (r = +0.58); tested n=40: move changed 2% silenced, 10% driven
- L3.12: rises as the right closes in (r = -0.58); tested n=40: move changed 0% silenced, 0% driven
- L3.20: rises as the left closes in (r = -0.58); tested n=40: move changed 0% silenced, 0% driven
- L3.1: rises as the left closes in (r = -0.57); tested n=40: move changed 0% silenced, 0% driven
- L3.23: rises as the right closes in (r = -0.56); tested n=40: move changed 2% silenced, 0% driven
- L3.22: rises as the left closes in (r = -0.56); tested n=40: move changed 0% silenced, 0% driven
- L3.21: rises as the right closes in (r = -0.55); tested n=40: move changed 0% silenced, 0% driven
- L3.11: rises as the right closes in (r = -0.49); tested n=40: move changed 0% silenced, 0% driven
- L3.31: fires when a wall is within two cells ahead (phi = +0.45; fires on 62% of positions with the event, 10% without); tested n=40: move changed 0% silenced, 0% driven
- L3.27: fires when a wall is within two cells ahead (phi = +0.45; fires on 61% of positions with the event, 10% without); tested n=40: move changed 0% silenced, 0% driven
- L3.6: fires when there is a long run open to the left, and when there is a long run open to the right (phi = +0.45; fires on 58% of positions with the event, 11% without); tested n=40: move changed 0% silenced, 0% driven
- L3.2: fires when a wall is within two cells ahead (phi = +0.45; fires on 61% of positions with the event, 10% without); tested n=40: move changed 2% silenced, 2% driven
- and 16 more

## motor (motor, 3 neurons)

The three motor neurons are the moves (left, straight, right); the move is read from them.

0 with a role at |phi| or |r| >= 0.3; 0 supported by the causal check (of 0 tested); 0 mixed; 0 barely move.
