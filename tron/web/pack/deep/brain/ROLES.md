# Neuron roles: Mako Deep

Brain file `brain.npz`. 8322 settled positions from 25 games (seeds 9100000+: against voronoi from both seats, against voronoi20, against itself). Written by `scripts/introspect.py`.

A neuron fires above the midpoint of its own 5th-95th percentile range. Its role is the thresholded event whose presence best matches its firing (phi), or a number it tracks (Pearson r) when that fits clearly better; kept at |phi| or |r| >= 0.3, else mixed. Causal check: on positions where the event holds, the brain is forked and the move read with the neuron silenced (bias -30, held at its floor) and driven (bias +30, held at 1). A role is supported when a clamp changes the move on at least 15% of those positions, at least 3 times the rate for random neurons of the same layer on positions where they fire, and on at least 5 positions; or when it shifts the motor vote the same way on at least 80% of at least 10 positions, by at least 3 times the null's mean shift. A verdict needs a null of at least 20 trials. Groups are judged against as many random neurons with similar firing rates.

Replay check: 6492 replayed moves, 0 different from the first pass; the unclamped fork read a different move than the brain on 0 tested positions.

## L1 (module_0, 256 neurons)

160 with a role at |phi| or |r| >= 0.3; 0 supported by the causal check (of 20 tested); 96 mixed; 0 barely move. Null: one random neuron, silenced or driven, flips the move on 4.2% of random positions and shifts the largest motor vote by 0.0497 on average (794 trials).

Groups (every neuron of the layer with that role, clamped together; null: as many random neurons on random positions):

| role | neurons | causal effect | null flips |
|---|---|---|---|
| fires when there is a long run open to the right | 43 | driving them makes the brain turn right more often (10% -> 100% of these positions) (n=40) | 22% |
| fires when there is a long run open to the left | 31 | driving them makes the brain ride straight on less often (82% -> 2% of these positions) (n=40), not clear | 52% |
| fires when the left is blocked | 20 | driving them: no clear effect (move flips on 2%, largest vote shift +0.014) (n=40), not clear | 10% |
| fires when the right is blocked | 14 | silencing them: no clear effect (move flips on 5%, largest vote shift -0.031) (n=40), not clear | 15% |
| fires when the riders are walled apart | 13 | driving them makes the brain turn left more often (8% -> 40% of these positions) (n=40) | 8% |
| fires when the opponent is off to the left | 7 | driving them makes the brain turn left less often (20% -> 0% of these positions) (n=40) | 2% |
| fires when a wall is within two cells ahead | 5 | silencing them makes the brain ride straight on more often (22% -> 55% of these positions) (n=40) | 20% |
| fires when the opponent is off to the right | 3 | driving them: no clear effect (move flips on 5%, largest vote shift -0.048) (n=40), not clear | 0% |

Correlated but not supported (untested, or no clear effect of the clamps):

- L1.49: fires when the right is blocked, and when the opponent is off to the right (phi = +0.64; fires on 92% of positions with the event, 23% without); tested n=40: move changed 2% silenced, 0% driven
- L1.50: fires when the right is blocked, and when the opponent owns most of the free board (phi = +0.62; fires on 87% of positions with the event, 21% without); tested n=40: move changed 2% silenced, 2% driven
- L1.196: fires when the left is blocked, and when the riders are walled apart (phi = +0.62; fires on 95% of positions with the event, 31% without); tested n=40: move changed 0% silenced, 0% driven
- L1.69: rises near the arena's walls (r = -0.62); tested n=40: move changed 2% silenced, 0% driven
- L1.21: fires when the left is blocked, and when it rides along the arena's edge (phi = +0.60; fires on 86% of positions with the event, 24% without); tested n=40: move changed 0% silenced, 0% driven
- L1.236: fires when the right is blocked, and when the riders are walled apart (phi = +0.59; fires on 96% of positions with the event, 32% without); tested n=40: move changed 2% silenced, 0% driven
- L1.227: fires when the right is blocked, and when the riders are walled apart (phi = +0.59; fires on 98% of positions with the event, 35% without); tested n=40: move changed 2% silenced, 0% driven
- L1.90: fires when the left is blocked (phi = +0.56; fires on 91% of positions with the event, 34% without); tested n=40: move changed 0% silenced, 0% driven
- L1.219: fires when the right is blocked, and when the riders are walled apart (phi = +0.56; fires on 96% of positions with the event, 35% without); tested n=40: move changed 0% silenced, 0% driven
- L1.111: fires when the riders are walled apart, and when the right is blocked (phi = +0.55; fires on 68% of positions with the event, 13% without); tested n=40: move changed 0% silenced, 2% driven
- L1.201: fires when the left is blocked (phi = +0.55; fires on 93% of positions with the event, 37% without); tested n=40: move changed 2% silenced, 0% driven
- L1.93: fires when the riders are walled apart, and when it rides along the arena's edge (phi = +0.55; fires on 84% of positions with the event, 27% without); tested n=40: move changed 0% silenced, 0% driven
- and 148 more

Mixed (96): no single feature reaches |phi| or |r| 0.3; their best matches are left_blocked (14), apart (12), opp_right_side (12), opp_left_side (10).

## L2 (module_1, 128 neurons)

88 with a role at |phi| or |r| >= 0.3; 6 supported by the causal check (of 20 tested); 40 mixed; 0 barely move. Null: one random neuron, silenced or driven, flips the move on 2.5% of random positions and shifts the largest motor vote by 0.0429 on average (800 trials).

| neuron | role | evidence | causal effect |
|---|---|---|---|
| L2.36 | rises as the right closes in | r = -0.61 | silencing it tilts the vote away from riding straight on (motor -0.050, the same way on 100% of these positions; the move flips on 0%) (n=40) |
| L2.26 | rises as the left closes in | r = -0.59 | silencing it tilts the vote away from riding straight on (motor -0.063, the same way on 100% of these positions; the move flips on 0%) (n=40) |
| L2.113 | fires when the left is blocked | phi = +0.54; fires on 94% of positions with the event, 39% without | silencing it tilts the vote away from riding straight on (motor -0.042, the same way on 100% of these positions; the move flips on 0%) (n=40) |
| L2.107 | fires when the right is blocked, and when the left is open | phi = +0.50; fires on 97% of positions with the event, 44% without | silencing it tilts the vote away from turning left (motor -0.063, the same way on 100% of these positions; the move flips on 2%) (n=40) |
| L2.108 | fires when a wall is within two cells ahead | phi = +0.48; fires on 51% of positions with the event, 6% without | driving it makes the brain ride straight on less often (22% -> 8% of these positions) (n=40) |
| L2.50 | fires when the way ahead is open | phi = -0.46; fires on 35% of positions with the event, 88% without | driving it makes the brain ride straight on more often (75% -> 98% of these positions) (n=40) |

Groups (every neuron of the layer with that role, clamped together; null: as many random neurons on random positions):

| role | neurons | causal effect | null flips |
|---|---|---|---|
| fires when the right is open | 19 | driving them makes the brain turn right more often (10% -> 68% of these positions) (n=40), not clear | 22% |
| fires when the left is open | 15 | driving them makes the brain turn left more often (15% -> 75% of these positions) (n=40) | 10% |
| fires when there is a long run open to the left | 11 | driving them: no clear effect (move flips on 2%, largest vote shift +0.151) (n=40), not clear | 68% |
| fires when a wall is within two cells ahead | 10 | silencing them makes the brain ride straight on more often (22% -> 52% of these positions) (n=40) | 18% |
| fires when the riders still share a room | 6 | driving them: no clear effect (move flips on 10%, largest vote shift -0.173) (n=40), not clear | 2% |
| fires when not: the opponent owns most of the free board | 3 | driving them: no clear effect (move flips on 10%, largest vote shift -0.100) (n=40), not clear | 0% |
| fires when the way ahead is open | 3 | silencing them makes the brain ride straight on less often (75% -> 12% of these positions) (n=40) | 2% |
| fires when the right is blocked | 3 | silencing them tilts the vote away from riding straight on (motor -0.082, the same way on 100% of these positions; the move flips on 0%) (n=40) | 0% |

Correlated but not supported (untested, or no clear effect of the clamps):

- L2.114: fires when the right is open (phi = -0.68; fires on 1% of positions with the event, 75% without); tested n=40: move changed 0% silenced, 0% driven
- L2.76: fires when the left is blocked, and when the riders are walled apart (phi = +0.61; fires on 98% of positions with the event, 35% without); tested n=40: move changed 0% silenced, 0% driven
- L2.103: fires when the right is open, and when the opponent is off to the left (phi = -0.56; fires on 1% of positions with the event, 61% without); tested n=40: move changed 0% silenced, 0% driven
- L2.60: fires when the right is open, and when the riders still share a room (phi = -0.56; fires on 6% of positions with the event, 66% without); tested n=40: move changed 0% silenced, 0% driven
- L2.84: fires when the left is open, and when the riders still share a room (phi = -0.55; fires on 6% of positions with the event, 62% without); tested n=40: move changed 0% silenced, 0% driven
- L2.19: fires when the right is open (phi = -0.52; fires on 13% of positions with the event, 70% without); tested n=40: move changed 0% silenced, 0% driven
- L2.75: fires when a wall is within two cells ahead (phi = +0.51; fires on 56% of positions with the event, 6% without); tested n=40: move changed 2% silenced, 8% driven
- L2.90: fires when the right is open (phi = -0.51; fires on 3% of positions with the event, 56% without); tested n=40: move changed 0% silenced, 0% driven
- L2.10: fires when the left is open (phi = -0.47; fires on 17% of positions with the event, 65% without); tested n=40: move changed 0% silenced, 0% driven
- L2.52: tracks the room to the right (r = +0.47); tested n=40: move changed 5% silenced, 0% driven
- L2.120: fires when the riders still share a room, and when the way ahead is open (phi = -0.46; fires on 23% of positions with the event, 71% without); tested n=40: move changed 0% silenced, 0% driven
- L2.57: fires when the left is open (phi = -0.46; fires on 15% of positions with the event, 62% without); tested n=40: move changed 0% silenced, 0% driven
- and 70 more

Mixed (40): no single feature reaches |phi| or |r| 0.3; their best matches are right_blocked (8), left_blocked (6), open_left (5), wall_ahead (5).

## L3 (association, 32 neurons)

32 with a role at |phi| or |r| >= 0.3; 2 supported by the causal check (of 20 tested); 0 mixed; 0 barely move. Null: one random neuron, silenced or driven, flips the move on 3.9% of random positions and shifts the largest motor vote by 0.1160 on average (800 trials).

| neuron | role | evidence | causal effect |
|---|---|---|---|
| L3.10 | fires when a wall is within two cells ahead | phi = +0.48; fires on 60% of positions with the event, 9% without | driving it makes the brain ride straight on less often (22% -> 2% of these positions) (n=40) |
| L3.28 | tracks the room to the left | r = +0.42 | silencing it makes the brain turn left less often (90% -> 68% of these positions) (n=40) |

Groups (every neuron of the layer with that role, clamped together; null: as many random neurons on random positions):

| role | neurons | causal effect | null flips |
|---|---|---|---|
| fires when a wall is within two cells ahead | 10 | driving them makes the brain ride into walls where it never did (0% -> 12% of these positions) (n=40) | 18% |
| fires when the way ahead is open | 10 | silencing them makes the brain ride straight on less often (75% -> 0% of these positions) (n=40) | 48% |

Correlated but not supported (untested, or no clear effect of the clamps):

- L3.20: rises as the left closes in (r = -0.57); tested n=40: move changed 0% silenced, 2% driven
- L3.9: tracks the room to the right (r = +0.56); tested n=40: move changed 0% silenced, 8% driven
- L3.1: rises as the left closes in (r = -0.56); tested n=40: move changed 0% silenced, 0% driven
- L3.22: rises as the left closes in (r = -0.55); tested n=40: move changed 0% silenced, 2% driven
- L3.12: rises as the right closes in (r = -0.55); tested n=40: move changed 0% silenced, 0% driven
- L3.21: rises as the right closes in (r = -0.54); tested n=40: move changed 0% silenced, 0% driven
- L3.23: rises as the right closes in (r = -0.53); tested n=40: move changed 0% silenced, 0% driven
- L3.27: fires when a wall is within two cells ahead (phi = +0.48; fires on 63% of positions with the event, 10% without); tested n=40: move changed 2% silenced, 8% driven
- L3.2: fires when a wall is within two cells ahead (phi = +0.47; fires on 63% of positions with the event, 10% without); tested n=40: move changed 8% silenced, 10% driven
- L3.31: fires when a wall is within two cells ahead (phi = +0.47; fires on 61% of positions with the event, 10% without); tested n=40: move changed 0% silenced, 2% driven
- L3.16: fires when the way ahead is open (phi = -0.46; fires on 37% of positions with the event, 89% without); tested n=40: move changed 0% silenced, 5% driven
- L3.26: fires when the way ahead is open (phi = -0.46; fires on 36% of positions with the event, 88% without); tested n=40: move changed 0% silenced, 5% driven
- and 18 more

## motor (motor, 3 neurons)

The three motor neurons are the moves (left, straight, right); the move is read from them.

0 with a role at |phi| or |r| >= 0.3; 0 supported by the causal check (of 0 tested); 0 mixed; 0 barely move.
