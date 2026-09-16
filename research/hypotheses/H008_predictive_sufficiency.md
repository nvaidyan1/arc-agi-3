# H008: State in the tallies raises k-step predictive sufficiency, and only where state exists

Status: TESTED — the predictor scores its own k=1/3/10 rollouts live now. Z1 (H006) gains 2-7 points of k=10 accuracy on 5 of 10 aliased games, 0 on the three 0%-aliased controls, exactly as predicted; games with a real move map separate cleanly from those without at k=10, and cd82 sits mid-table, foreshadowing H009.
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
- 2026-09-15 **Day 5 built and run.** The predictor now scores its own
  entity rollouts live: `predictor.HORIZONS = (1, 3, 10)`,
  `Ledger.horizon`, in every sweep summary and one line in the brief.
  `scripts/latent_rollout.py` recomputes the identical number offline
  from the S_t traces (verified exact against a live sweep, su15 seed 1:
  1414/452/0/20, 1172/604/12/40, 909/612/28/50 both ways) and adds the
  arm the agent cannot run yet — the same tallies plus H006's admitted
  variable, `Z1 = actions since reset`, admitted **per entity** only
  when that entity's whole history in the trace is a function of Z1
  (every Z1 value seen ≥ 2 times saw one effect, ≥ 3 such values). 266
  tests (2 new), default action stream unchanged (cd82, sp80, seed 1).

  Ten seeds, thirteen games, accuracy among forecasts made:

  | game | k=1 | k=3 | k=10 | +Z1 k=10 | Δk=10 |
  |---|---|---|---|---|---|
  | sp80 | 97% | 94% | 90% | 90% | 0 |
  | ls20 | 89% | 81% | 72% | 72% | 0 |
  | cd82 | 93% | 85% | 79% | 82% | +3 |
  | dc22 | 88% | 80% | 77% | 79% | +2 |
  | ar25 | 84% | 73% | 57% | 57% | 0 |
  | ka59 | 84% | 68% | 61% | 66% | +5 |
  | su15 | 84% | 76% | 66% | 66% | 0 |
  | sc25 | 83% | 64% | 55% | 55% | 0 |
  | wa30 | 84% | 62% | 54% | 54% | 0 |
  | sk48 | 87% | 73% | 61% | 61% | 0 |
  | cn04 | 74% | 56% | 38% | 45% | +7 |
  | m0r0 | 71% | 43% | 28% | 35% | +7 |
  | g50t | 70% | 42% | 14% | 20% | +6 |

  **P1 (aliased games rise, controls flat) — partially met.** The three
  0%-aliased controls (sp80, ls20, ar25) move 0 points, exactly as
  predicted. Of the ten aliased games, five gain 5–7 points at k=10
  (g50t, m0r0, cn04, ka59) or 2–3 (cd82, dc22); **five gain nothing**
  (wa30, sc25, sk48, su15) despite wa30 being one of H006's six
  cross-attempt-confirmed meter games. Reconciled: H006's splitter
  admits a variable **per game**, pooled across all ten seeds, on the
  pixel-context level; this scorer admits **per entity, within one
  seed's trace only** (no pooling, by design — no cross-seed leakage).
  wa30's meter entity evidently does not clear `MIN_FUNCTION_POINTS`
  (3 distinct Z1 values at ≥ 2 sightings) within a single 400-step trace
  though it does across ten pooled traces. Not a contradiction of H006;
  a smaller information budget in this scorer. A pooled-across-seeds
  admission is the natural next version, not built this week.

  **P2 (k=10 separates the games with a real move map) — met, more
  clearly than "navigational vs rest."** sp80/ls20/ar25/cd82/dc22 (all
  have a `learned_moves` map, per `control.py`) hold 57–90% at k=10;
  every game without one falls to 14–66%. cd82 sitting mid-table (79%,
  not 90%+) matches H009's finding directly: its map exists but the
  true dynamics are position-dependent, so the tallies alone still miss
  a fifth of 10-step rollouts — the same gap H009 traced to source.

  **The one certain H006 gain, quantified.** cd82, ka59, m0r0, cn04,
  g50t: +2 to +7 points at k=10 from one history-derived variable,
  free, no new perception, no score claim. Matches H006's prediction
  exactly ("one certain, small H008 gain... should not expect more").
