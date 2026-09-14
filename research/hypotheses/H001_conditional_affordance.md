# H001: Conditional affordances — a lever given a precondition

Status: TESTED — prediction not met on cd82 (falsifier 2); gains elsewhere held
Research question: RQ2 (predictive world modelling) / RQ3 (active testing)
Date opened: 2026-09-14
Origin: cd82 diagnosis (`history.md` 2026-09-14, "the floor fails, the
diagnosis holds") and reviewer C, §9–10 and §32 step 2.

## Claim

Some actions have no unconditional effect and a decisive conditional one.
Representing an action's effect on a residual **given a precondition on
another residual** — first: the controlled thing being adjacent to a member
of the pair — lets the proposer find levers that the unconditional contrast
cannot see, and lets the verifier tell *"the precondition was not met"*
apart from *"the hypothesis is wrong"*.

## Mechanism

```
PairRecord.by_action_given[condition][action]  -> {down, up, flat}
condition = "adjacent" | "apart"   (distance(CONTROL thing, nearest member) <= d, before the action)

conditional lever(rel, pair) =
    (action, condition) whose DOWN rate under the condition exceeds both
    the same action's rate under the other condition and the median of
    the other actions under this condition, by >= LEVER_MIN_LIFT

Hypothesis(key, action, precondition=(member, d))
verifier -> SUPPORTED | FALSIFIED | PRECONDITION_UNMET | INCONCLUSIVE | HELD | EXPIRED
    a step under an unmet precondition costs budget but is not evidence;
    the router's first step goes to satisfying the precondition.
```

## Prediction

On cd82 (the paint action lands only when the bucket is at the block):
the brief will show `part_size_diff(template, block): ACTION5 drives it
down when adjacent`, the proposer will bet on it with a precondition, and
sweeps reaching level 1 under `ARC_PROPOSER=1` will return from 2–3 / 30
toward the base rate of 16 / 30 without sp80 (25 / 30) or m0r0 (9 / 30)
falling.

## Falsifier

- The conditional lever never appears on cd82 in 30 seeds (the condition
  chosen is the wrong one, or the effect is not conditional on adjacency).
- It appears but cd82 does not recover (the lever is not the bottleneck;
  arrangement is — see `shape_diff`).
- cd82 recovers but sp80 or m0r0 lose more than the seed-paired noise.

## Experiment

E-7a: base vs `ARC_PROPOSER=1`, games cd82, sp80, m0r0 (+ ls20, ar25,
cn04, tr87, sk48 as the rest of the touched set), n=30 seed-paired,
medians, permutation; per-game level-1 reach is the primary reading.

## Metrics

- per-game sweeps reaching L1 (primary)
- touched-8 median score
- verifier outcome counts per game: SUPPORTED / FALSIFIED /
  PRECONDITION_UNMET — the last one is the new information

## Status log

- 2026-09-14 opened; blanket exploration floor measured and reverted first.
- 2026-09-14 built. Adjacency alone never varied on cd82 (every orbit
  position touches the block); **side** added to the condition, and a
  conditional lever formed at once: `ACTION5 | adjacent:-x, +0.30`.
  Unmodelled factor found: the selected paint colour (another entity's
  state). E-7a launched.
- 2026-09-14 E-7a: cd82 16 -> 2 of 30 (unchanged), sp80 16 -> 25, ar25
  9 -> 15, m0r0 0 -> 6; touched-8 median 0.040 -> 0.110, p = 0.20.
  Falsifier 2 met: the conditional lever formed and cd82 did not recover.
  Reading: the rule is two-factor (side x selected colour) and the level
  needs arrangement, not proportion. Next candidate condition: the state
  of another entity (which swatch is marked) — or hand the two-factor rule
  to a proposer that can state it.
