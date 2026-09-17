# H007: A `state` condition kind — a two-factor rule becomes jointly satisfiable

Status: TESTED — the `state` condition kind is built and works: mechanism confirmed 3/3 seeds live on cd82 (state restored in one action every time). P1 (jointly met >= 3/8) met on 1 of 3 seeds; the other two are blocked by the walk (`navigation.plan`'s offset model), not by the state condition — see H009. P2 (the enumerator forms a state-conditioned lever) is blocked by an exploration gap, not a representation one — see H011. **P2 RE-TESTED 2026-09-17 AND NOT MET — but the original justification survives.** 10 seeds, 400 steps, cd82: 1,372 hypotheses formed, 309 adjacency-conditioned, **0 state-conditioned**. Cause is not the enumerator: H011 raised clicks into the strip ENTITY's bbox (21.5% -> 42.4%) but not onto the ~23 interactive swatch cells inside it (3.29% -> 3.36%), so the strip's state changed after 1 of 101 bbox clicks and there is still nothing varying to tally. `scripts/h007_p2_retest.py`.
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
- 2026-09-15 **Day 4 built and run.** `relations.state_key` (colour +
  shape token, position removed) and `STATE`; `Hypothesis.precondition`
  accepts `("state:<token>", member)` through `conditions_of` unchanged;
  `_condition_met` dispatches on the kind; `MyAgent._setters` — per
  entity, per state it has been seen to *enter*, the action that took it
  there with its click — recorded in `_learn_from` from
  `belief.last_effects` (keyed by the resulting state, not "what last
  changed it", because the last change may have taken the thing *away*
  from the state a bet needs); `_route_by_acting` looks that up when a
  state condition is unmet; the policy satisfies state conditions before
  walks (one action, no displacement). Enumerator, LLM schema and the
  predictor untouched. 264 tests (3 new). Default action stream
  byte-identical on cd82 and sp80 seed 1 (the memory is recording-only
  until a state condition exists).

  `scripts/h007_cd82_oracle.py`, seeds 1–3, injection at step 24 after
  three forced swatch clicks so the agent's *own* memory learns both
  transitions (nothing injected into `_setters`):

  | seed | strip tokens through the clicks | setters learned | acting route | jointly met / 8 | verdict |
  |---|---|---|---|---|---|
  | 1 | K0 → K1 → K0 → K1 | both (K1: click (37,4); K0: click (43,4)) | fired once, K0 restored in one step | 0 | expired: no path to the block's −x side for 6 of 7 steps, lever pressed unmet |
  | 2 | same | both | fired once | **3** | falsified: residual 5 held under three met presses |
  | 3 | same | both | fired once | 0 | expired, as seed 1 |

  **P1 met on 1 of 3 seeds, and the mechanism confirmed on 3 of 3.** The
  state condition read correctly (tokens flip deterministically), the
  transition memory learned both directions from observation, and the
  acting route restored the named state in one step every time. What
  kept seeds 1 and 3 from the joint test is the *walking* condition —
  `_route_to` found no path to the block's −x side (cd82's moves are
  orbit hops the displacement planner cannot express), a pre-existing
  router limit, not the state kind. **P3 supported in spirit**: the state
  condition cost one step per seed, adjacency seven.

  **Seed 2's falsification is the verifier working.** The oracle named
  the *initial* state K0 (colour 15 selected); seed 2's block stood at
  residual 5 and needed the other colour, so painting 15 could not lower
  it. The right bet there is `state:K1`; a proposer that reads which
  colour the block lacks would name it. Not a failure of the kind.

  **A correction to the record.** H001/H005's oracles conditioned
  adjacency on the *template* (#0), which sits at the board's left edge —
  its −x side is off screen, so that condition was near-impossible by
  geometry. H001's `adjacent:-x` lever was tallied relative to the pair's
  nearest non-control member, i.e. the **block** (#10). H005 Stage 3's
  0–1 of 8 was partly this, not only the swatch-adjacency proxy.

  **P2 (the enumerator forms a state-conditioned lever) — not built,
  and not reachable by tallies alone.** The agent clicked the strip 6
  times in 4,000 recorded steps, so the selection state never varies
  under its own exploration and no tally can contrast it. That is an
  exploration / information-gain problem (week 2), not a representation
  one; the tally extension waits for it.

- 2026-09-17 **P2 re-test formally queued as gate 2 of the 09-17 ladder.**
  Not a new finding — a correction. When H011 Stage 2 cleared its n=30
  parity gate on 2026-09-16, the precondition P2 was blocked on was
  removed, and the standalone re-test (item 3 of the 09-15 converged
  reviewer list) became runnable. It was never run, and the first draft of
  the 09-17 plan wrongly recorded it as folded forward; a colleague's
  independent read caught the omission. The test is unchanged from how it
  was specified: rerun the enumerator on cd82, 10 seeds, 400 steps, and
  ask only whether a state-conditioned lever for the paint action forms
  under the new click distribution. Read it on lever formation, condition
  grounding, third-entity relation discovery and route usability — **not**
  on aggregate score. What makes it worth running ahead of anything
  larger: H011 may have changed the *input distribution* to the existing
  learning machinery without changing the machinery. If the lever now
  forms, the chain coverage -> representation discovery -> lever formation
  is demonstrated end to end, which is stronger evidence for the
  architecture than any score movement. If it does not, the remaining gap
  is located in tally / lever-formation logic — smaller and better-placed
  than the alternative assumption that representation is at fault.

- 2026-09-17 **P2 re-test run (gate 2). Not met; the day-4 reasoning holds
  for a newly-identified reason.** Day 4 declined to build the enumerator's
  state-conditioned tally because "the state never varies under exploration
  (6 strip clicks / 4,000 steps)". H011 appeared to remove that blocker.
  It did not. 10 seeds x 400 steps with `ARC_PROPOSER=1`: **0 of 1,372
  hypotheses carried a `state:` precondition**, while 309 carried an
  adjacency one, so the enumerator is forming conditioned levers freely —
  just never over this kind. The strip's visible state changed after 1 of
  101 strip-bbox clicks; 8 of 10 seeds saw exactly one strip configuration
  all run. Classifying clicks by the colour under them: 93 of 101 landed on
  the strip's inert backing (colour '3'), 8 on an actual swatch. Measured
  the same way pre- and post-H011, swatch coverage is 3.29% -> 3.36% — flat.
  **P2 is therefore still blocked by an exploration gap, exactly as this
  file said, but the gap is finer-grained than "the strip is rarely
  clicked": it is that the strip entity is 94% inert backing, and novelty
  drawn uniformly over non-background cells lands there.** No change to the
  `state` condition kind is implied — it works (mechanism 3/3 under oracle
  injection). Evidence: `scripts/h007_p2_retest.py`.