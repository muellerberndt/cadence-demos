# Neuron roles: Mako

Brain file `brain.npz`. 7738 settled positions from 25 games (seeds 9100000+: against voronoi from both seats, against voronoi20, against itself). Written by `scripts/introspect.py`.

A neuron fires above the midpoint of its own 5th-95th percentile range. Its role is the thresholded event whose presence best matches its firing (phi), or a number it tracks (Pearson r) when that fits clearly better; kept at |phi| or |r| >= 0.3, else mixed. Causal check: on positions where the event holds, the brain is forked and the move read with the neuron silenced (bias -30, held at its floor) and driven (bias +30, held at 1). A role is supported when a clamp changes the move on at least 15% of those positions, at least 3 times the rate for random neurons of the same layer on positions where they fire, and on at least 5 positions; or when it shifts the motor vote the same way on at least 80% of at least 10 positions, by at least 3 times the null's mean shift. A verdict needs a null of at least 20 trials. Groups are judged against as many random neurons with similar firing rates.

Replay check: 6087 replayed moves, 0 different from the first pass; the unclamped fork read a different move than the brain on 0 tested positions.

## L1 (association, 256 neurons)

162 with a role at |phi| or |r| >= 0.3; 0 supported by the causal check (of 20 tested); 94 mixed; 0 barely move. Null: one random neuron, silenced or driven, flips the move on 5.4% of random positions and shifts the largest motor vote by 0.1282 on average (800 trials).

Groups (every neuron of the layer with that role, clamped together; null: as many random neurons on random positions):

| role | neurons | causal effect | null flips |
|---|---|---|---|
| fires when there is a long run open to the right | 46 | driving them makes the brain turn right more often (12% -> 100% of these positions) (n=40), not clear | 72% |
| fires when there is a long run open to the left | 23 | silencing them makes the brain turn left less often (20% -> 5% of these positions) (n=40) | 78% |
| fires when the left is blocked | 19 | silencing them makes the brain turn left more often (0% -> 10% of these positions) (n=40), not clear | 2% |
| fires when the riders are walled apart | 16 | driving them: no clear effect (move flips on 0%, largest vote shift -0.269) (n=40), not clear | 15% |
| fires when the right is blocked | 11 | silencing them: no clear effect (move flips on 0%, largest vote shift -0.158) (n=40), not clear | 8% |
| fires when the opponent is off to the left | 9 | driving them makes the brain ride straight on more often (75% -> 100% of these positions) (n=40) | 2% |
| fires when a wall is within two cells ahead | 5 | silencing them makes the brain ride straight on more often (25% -> 57% of these positions) (n=40) | 40% |
| fires when the opponent is off to the right | 5 | driving them: no clear effect (move flips on 8%, largest vote shift -0.183) (n=40), not clear | 10% |

Correlated but not supported (untested, or no clear effect of the clamps):

- L1.50: fires when the right is blocked, and when it rides along the arena's edge (phi = +0.65; fires on 84% of positions with the event, 16% without); tested n=40: move changed 5% silenced, 0% driven
- L1.69: rises near the arena's walls (r = -0.64); tested n=40: move changed 0% silenced, 2% driven
- L1.49: fires when the right is blocked, and when the opponent is off to the right (phi = +0.63; fires on 90% of positions with the event, 23% without); tested n=40: move changed 0% silenced, 0% driven
- L1.21: fires when the left is blocked, and when it rides along the arena's edge (phi = +0.61; fires on 86% of positions with the event, 22% without); tested n=40: move changed 0% silenced, 0% driven
- L1.227: fires when the right is blocked, and when the opponent is off to the right (phi = +0.60; fires on 99% of positions with the event, 34% without); tested n=40: move changed 0% silenced, 0% driven
- L1.196: fires when the left is blocked, and when the riders are walled apart (phi = +0.60; fires on 95% of positions with the event, 31% without); tested n=40: move changed 0% silenced, 0% driven
- L1.111: fires when the riders are walled apart, and when it rides along the arena's edge (phi = +0.58; fires on 63% of positions with the event, 9% without); tested n=40: move changed 0% silenced, 5% driven
- L1.236: fires when the right is blocked, and when the riders are walled apart (phi = +0.56; fires on 95% of positions with the event, 35% without); tested n=40: move changed 0% silenced, 0% driven
- L1.144: fires when the right is blocked, and when the opponent owns most of the free board (phi = +0.56; fires on 75% of positions with the event, 17% without); tested n=40: move changed 5% silenced, 0% driven
- L1.93: fires when the riders are walled apart, and when it rides along the arena's edge (phi = +0.56; fires on 84% of positions with the event, 26% without); tested n=40: move changed 0% silenced, 0% driven
- L1.23: tracks the distance to the nearest wall (r = +0.56); tested n=40: move changed 0% silenced, 0% driven
- L1.219: fires when the right is blocked, and when the riders are walled apart (phi = +0.55; fires on 96% of positions with the event, 37% without); tested n=40: move changed 0% silenced, 0% driven
- and 150 more

Mixed (94): no single feature reaches |phi| or |r| 0.3; their best matches are apart (13), left_blocked (12), opp_right_side (11), big_territory (10).

## motor (motor, 3 neurons)

The three motor neurons are the moves (left, straight, right); the move is read from them.

0 with a role at |phi| or |r| >= 0.3; 0 supported by the causal check (of 0 tested); 0 mixed; 0 barely move.
