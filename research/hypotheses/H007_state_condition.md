# H007: A `state` condition kind — a two-factor rule becomes jointly satisfiable

Status: OPENED — not built; the 09-14 handoff's item 1 reframed
Research question: RQ3 (active testing)
Date opened: 2026-09-15
Origin: `H001` falsifier 2 (cd82's second factor is *another entity's
state*), `H005` Stage 3 (an adjacency conjunction was jointly met on 0–1
of 8 steps because "adjacent to the swatch" is the wrong proxy for
"selected"), reviewer C fourth pass §6 ("what a hypothesis is allowed to
talk about"). Second of three claims (H006 → H007 → H008); depends on
H006 only for *which* variable kind cd82 needs, and is built for the
visible-persistent kind regardless of H006's result.

## Claim

`Hypothesis.precondition` can carry a condition of a second **kind** —
a persistent fact about another entity, not the controlled thing's
position — and once it can, the complete cd82 rule (side × selected
swatch) is expressible, jointly satisfiable within a bet's budget, and
routable: an unmet state condition is satisfied by *acting* on the
entity, not by moving next to it.

## Mechanism

```
precondition     ("state", member, value) -- met when member's current descriptor
                 key == value (kinds.py's equal-descriptor view); conjoins with
                 adjacency/side through H005's conditions_of() unchanged
_condition_met   dispatches on the condition kind
routing          unmet state condition -> the action Belief.effects says sets that
                 entity; None if none known, and the bet expires unmet (correct)
enumerator       PairRecord.by_action_given tallied under the state condition as it
                 is under adjacency/side, so a state-conditioned lever can form
                 with no oracle
LLM schema       untouched this week (week-2 candidate)
```

## Prediction

1. The cd82 oracle with (adjacent:-x, template) AND (state, swatch,
   marked) is jointly met on >= 3 of 8 steps on seeds 1–3, against
   0–1 of 8 for H005 Stage 3's adjacency pair on the same seeds.
2. With the oracle removed, the enumerator forms a state-conditioned
   lever for ACTION5 on cd82 within a level (the lift it could not see
   under adjacency alone).
3. The precondition-unmet rate of state-conditioned bets is at or below
   the enumerator's adjacency-conditioned rate (0.0% across ~800 bets),
   because acting to set a state is one step, not a route.

## Falsifier

- The two-condition oracle is still jointly met on < 2 of 8 steps: the
  swatch's "marked" descriptor is not the state, or the setting action
  is not learnable from Belief.effects — H006's Day-3 ranking says which.
- Jointly met, and the residual still does not move under ACTION5: a
  third factor, or the goal is arrangement (not a residual) — relocates
  the bottleneck to the goal model, not the condition schema.
- The state-conditioned lever forms on the 0%-aliased games where no
  state exists: the tally is picking up noise.

## Experiment

Day 4. `scripts/h005_cd82_oracle.py` extended to the state condition,
seeds 1–3, side by side with the Stage 3 numbers; then the enumerator
alone on cd82, 10 seeds, 400 steps, reading the hypothesis log for a
state-conditioned lever. Unit tests for the dispatch and the acting
route, same harness H005 Stage 1 added.

## Metrics

Jointly-met steps per oracle; state-conditioned levers formed per game;
precondition-unmet rate by condition kind; hypothesis outcomes.

## Status log

- 2026-09-15 opened.
