# H008: State in the tallies raises k-step predictive sufficiency, and only where state exists

Status: OPENED — not built
Research question: RQ2 (predictive world modelling)
Date opened: 2026-09-15
Origin: `H003` (one-step forecast in the vocabulary; its largest error is
state-dependent), reviewer C fourth pass second note §12–13 (multi-step
prediction and the predictive-sufficiency table as the metric between
"representation valid" and "score"). Third of three claims
(H006 → H007 → H008); needs H007's state-conditioned tallies to exist.

## Claim

A rollout of the existing forecast in the vocabulary — apply predicted
entity effects and residual directions to an imagined state, forecast
again — measures how much of the future the state carries. Adding the
state condition to the tallies raises that accuracy at k = 3 and 10 on
the aliased games and leaves the 0%-aliased games unchanged; if it
rises everywhere alike, the gain is a tally artefact, not state.

## Mechanism

```
Predictor.rollout(S, [a1..ak])   no pixels, no simulator: forecast(S, a1) -> S'
                                 by applying entity effects and residual directions,
                                 then forecast(S', a2) ...; abstain propagates
score                            accuracy and coverage at k = 1, 3, 10, per game,
                                 per layer, with and without ("state", Z, v) tallies
consumers                        `prediction` in sweep summaries gains k-step rows;
                                 the brief's PREDICTED shows k=3
supervisor (Day 6, no claim yet) on_advance records every variable's value and last
                                 change in the window; a week-2 hypothesis if it
                                 earns a prior
```

## Prediction

1. k=3 accuracy on the aliased games rises >= 10 points with
   state-conditioned tallies; the 0%-aliased games move < 3 points.
2. k=10 accuracy is above chance on the navigational games without any
   change (the move map is a real transition model) and near chance on
   the aliased games without state — the table separates the two
   families before any score does.
3. (Day 7 ladder, weakest, not required) L1 reach on cd82 / m0r0 / sk48
   rises under arm C; score is read last.

## Falsifier

- k-step accuracy rises on the controls as much as on the aliased games:
  artefact.
- State-conditioned tallies do not move k=3 on cd82 even though H007's
  condition is met and its lever formed: the state is real and
  conditionable but the rollout's vocabulary cannot carry its consequence
  (a positional or arrangement effect) — H003's own finding again, and an
  argument for position as the next primitive over more state.

## Experiment

Day 5 offline on the Day-2 harness, per game, both tally settings. Day 7
ladder: A current / B + H007 / C + state tallies in the predictor; touched
set cd82, m0r0, sk48, g50t, cn04 plus controls sp80, ls20, ar25; n=10
seed-paired, 400 steps. Read in order: k-step accuracy; aliased contexts
resolved; unmet-rate and outcomes; L1 reach; score last.

## Metrics

Accuracy and coverage at k = 1, 3, 10 per game and layer, both settings;
the ladder's per-arm table.

## Status log

- 2026-09-15 opened.
