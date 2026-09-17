# H016: does the H007 conditional rule survive a direct causal test?

Status: TESTED 2026-09-17 — **OUTCOME B: the specific H007 causal rule is FALSIFIED.** 19 jointly-met presses across 8 usable seeds: residual fell 5, flat 10, **rose 4**. The verifier's own verdicts were 4 falsified / 3 expired / 1 live — **zero supported**. Joint satisfaction IS reachable once budget allows travel (6 of 8 usable seeds), so H015's premise was right about what was blocking execution — and the proposition being executed does not hold. Scope of the falsification, stated precisely: the rule `(adjacent:-x of the block) AND (state K0 on the strip) -> ACTION5 -> residual falls`. **NOT** cd82's mechanic, which remains undiscovered.
Research question: RQ2 (predictive world modelling) / RQ3 (active testing)
Date opened: 2026-09-17
Origin: four gates of infrastructure (H010 routing, H011 click coverage,
H015 budget economy) were built to make ONE proposition executable on cd82,
and each returned "mechanism proven, consumer unmoved". The proposition had
been jointly satisfied and actually tested exactly once — H007 Day 4, seed 2,
three met presses — and the residual did not move ("falsified: residual 5
held under three met presses"). Every gate since made it easier to execute
without re-asking whether it was true.

## Claim

If the oracle is given enough budget that travel is affordable, the
hypothesised action produces the predicted residual transition under the
jointly-satisfied condition.

## Mechanism / measurement

The unit is not "did we clear level 1". It is, per press, with the condition
jointly satisfied:

    dR = R_before - R_after

`scripts/h016_oracle_rule_test.py` injects the H007 two-condition bet with
`budget=120` instead of 8, records every press paired with whether the
condition was met at that step, and reports dR per met press.

## Prediction / falsifier

- Supported: the residual falls on a majority of jointly-met presses and
  never rises.
- Falsified: it does not fall on most of them, and/or rises on some.
- A single large fall is explicitly **not** support: the residual is a
  part-size difference that other events can move. A verdict needs >= 8
  jointly-met presses; below that the script states none.

## Result (2026-09-17)

12 seeds at `H007_INJECT_AFTER=150`, `budget=120`, 400 steps. 4 aborted on
the oracle's own pre-existing entity guard (entity 10 not live at
injection) — not a result. 8 usable.

| | |
|---|---|
| usable seeds | 8 |
| reached joint satisfaction at least once | **6 of 8** |
| never reached it (seeds 1, 11) | 2 of 8 |
| jointly-met presses | **19** |
| residual FELL | 5 |
| residual FLAT | 10 |
| residual **ROSE** | **4** |
| verifier verdicts | 4 falsified, 3 expired, 1 live, **0 supported** |

Per-seed detail is in the script's output; seed 9 is representative —
`50 -> 25` (dR +25), `25 -> 40` (dR **-15**), `40 -> 25` (+15), `25 -> 25`
(0). The residual moves in **both directions** under the satisfied
condition. That is not a lever.

**Two findings, not one.**

1. **Outcome B, the main result.** The specific rule is falsified. The
   condition can be satisfied and the predicted transition does not follow.
2. **A side of Outcome C.** 2 of 8 usable seeds never achieved adjacency at
   all, one of them (seed 11) while moving over **19 distinct positions**.
   For those, target computation or geometric reachability is still suspect
   — gate 1's reading B, unresolved and now narrowed to specific seeds.

## What this falsifies, and what it does not

Falsified: `(adjacent:-x, state K0) -> ACTION5 -> residual reduction`.

NOT falsified, and still open: what cd82's actual mechanic is. One failed
conditional action leaves the underlying rule undiscovered. Nothing here
says the swatch is irrelevant, that ACTION5 does nothing, or that the
architecture is wrong.

## Why this matters beyond cd82

It retroactively reinterprets three results. H010 fixed routing, H011
changed exploration, H015 improved budget economy; none produced skill —
**because the thing they were making executable was probably wrong.** The
research loop had become substrate-oriented: we optimised the conditions
under which a hypothesis could be tested without establishing that the
hypothesis deserved testing.

Hence the rule adopted with this result (`docs/plan.md`): **no
infrastructure follow-up until the mechanism it enables has passed a direct
causal test.** Mechanism first, infrastructure second.

## Status log

- 2026-09-17 opened, built and run. Outcome B. `scripts/h016_oracle_rule_test.py`.
  The verdict logic was tightened mid-run: a first pass declared "supported"
  off a single dR=+35 on one seed, which is exactly the over-claim this
  hypothesis exists to prevent. It now requires >= 8 jointly-met presses and
  a majority-fall with no rises before stating support.
