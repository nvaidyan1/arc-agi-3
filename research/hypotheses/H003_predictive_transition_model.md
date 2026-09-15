# H003: A predictive transition model from the evidence already held

Status: TESTED — predictions 1 and 3 met, 2 not as stated (the error localises to geometry, not the paint rule)
Research question: RQ2 (predictive world modelling)
Date opened: 2026-09-14
Origin: reviewer C §12 and §32 steps 3–4, second note "Experiments 1–4":
build a predictive model and competing hypotheses *before* attaching a
language model. `docs/plan.md` START HERE, item 1.

## Claim

The per-action tallies the agent already keeps — `Belief.effects[action]`
(what each action did to each entity, with how reliably) and
`PairRecord.by_action[_given]` (which way each residual moved under each
action, per precondition) — are enough to **predict the next frame at the
level of the vocabulary**: for every live entity, the effect the action
will have; for every pair, the direction its residual will move. Scoring
those predictions every step gives a world-model metric that sits between
"the representation is valid" (the probe's (i)–(iii')) and "the agent
scores" (the sweep): **prediction error per layer**. Where the error is
high and confident, the vocabulary is missing a factor — and that is the
signal a rival hypothesis (H004) or a proposer (H002) should be pointed at.

## Mechanism

```
before the action is learned from (the pre-action state is still held):
  Predictor.forecast(belief, engine, action)
      entity  rid  -> (expected effect | unchanged, confidence)   from Belief.acted/effects
      pair    key  -> (down | up | flat, confidence, condition)   from by_action_given[cond]
                                                                  when it has enough tries,
                                                                  else by_action, else abstain
after belief.update / relations.update:
  Predictor.score(forecast, belief.last_effects, engine.records)
      hit / miss / undecidable / abstained, Brier, per layer, per action, per relation
      surprises: the most confident misses, kept for the brief
```

Abstain is a first-class outcome: fewer than PREDICT_MIN_TRIES (4) tries
of the action on that entity or pair, and nothing is predicted. Coverage
(predicted / possible) is reported beside accuracy so a model that
abstains its way to 100% is visible as such. No simulator, no rollout: a
forecast is one step, and it is compared to what happened, never to a
counterfactual.

Consumers (rule: no representation without a consumer):
  1. the brief's PREDICTED section — accuracy and coverage per layer on
     this level, and the last confident surprises — read by the recap now
     and by the LLM proposer when one is attached;
  2. the sweep summary — per-game prediction error, so the metric is
     durable and comparable across arms;
  3. H004 — rival hypotheses are proposed where the pair layer's
     conditional and unconditional tallies disagree.

## Prediction

1. On the navigational games (sp80, ls20, m0r0, ar25) the entity layer
   reaches >= 70% accuracy on the CONTROL thing within the first level
   at coverage >= 50%: a d-pad is deterministic and the tallies say so.
2. On cd82 the pair layer's confident misses concentrate on ACTION5 and
   `part_size_diff(template content, block)` — the two-factor rule shows
   up as *error*, localised, before anything names it.
3. Accuracy under the conditional tally is higher than under the
   unconditional one on the pairs where both are available (the
   precondition carries information), and the difference is largest on
   cd82.

## Falsifier

- Entity-layer accuracy on CONTROL things stays below 50% at coverage
  >= 50% on the navigational games: the effect vocabulary (kind +
  direction) does not describe what the d-pad does, and the belief layer
  has been earning roles from noise.
- Confident misses are spread evenly over actions and pairs on cd82:
  the error carries no localisation, and H004 has nothing to aim at.
- The conditional tally predicts *worse* than the unconditional one
  where both exist: the precondition vocabulary is adding noise.

## Experiment

E-H003-1: touched set (cd82, sp80, m0r0, ar25, ls20, cn04, tr87, sk48),
n=10 seeds, 400 steps, default flags. Read per-game accuracy and
coverage per layer from the sweep summaries; read the surprise lists on
cd82 by eye. No behavioural change is expected or measured — the policy
does not read the forecast.

## Metrics

per layer (entity / pair): accuracy among predicted, coverage, Brier;
per action and per relation for the pair layer; the top confident
misses per game.

## Status log

- 2026-09-14 opened.
- 2026-09-14 built (`agent/predictor.py`, PREDICTED in the brief,
  `observed[game].prediction` in sweep summaries). Action stream
  byte-identical to HEAD at default flags (cd82, sp80, seed 3). The
  headline pair accuracy is trivial — 99% of 43,000 forecasts on sp80 are
  "flat" on pairs nothing moves — so movement precision/recall and an
  (action × relation) error table over non-trivial forecasts were added.
- 2026-09-14 E-H003-1 (touched 8 × 10 seeds × 400 steps, default flags):

  | game | L1 | entity acc / cov | chg prec / rec | pair chg prec / rec | cond / uncond |
  |---|---|---|---|---|---|
  | sp80 | 7/10 | 97 / 89 | 92 / 95 | 91 / 92 | 99 / 98 |
  | ls20 | 2/10 | 89 / 95 | 82 / 83 | 84 / 73 | 95 / 94 |
  | ar25 | 4/10 | 84 / 87 | 79 / 80 | 76 / 70 | 93 / 91 |
  | cd82 | 7/10 | 93 / 90 | 77 / 85 | 69 / 73 | 96 / 93 |
  | cn04 | 2/10 | 74 / 86 | 69 / 60 | 48 / 35 | 91 / 90 |
  | m0r0 | 0/10 | 71 / 93 | 61 / 55 | 52 / 40 | 91 / 91 |
  | sk48 | 0/10 | 87 / 93 | 64 / 58 | 60 / 46 | 95 / 95 |
  | tr87 | 1/10 | 96 / 96 | 49 / 45 | 49 / 44 | 99 / 98 |

  Prediction 1 met. Prediction 3 weakly met: +1 to +3 points, largest on
  cd82. Prediction 2 **not met as stated**: the misses localise, but to
  `containment` / `distance` under the movement actions on every game
  (cd82: ACTION1–4 × containment, 7–10k wrong each), not to ACTION5.
  ACTION5's own cells on cd82 are wrong 62–98% (distance 94% of 1,102,
  count_diff 98% of 795, part_size_diff 63% of 1,050) but are outnumbered
  ten to one. A direction tally cannot forecast a residual that depends on
  *where* the controlled thing is; the world model's largest missing factor
  is position, not the two-factor paint rule.
