# H015: A bet that cannot reach its precondition should not spend on its lever

Status: PARITY GATE PASSED 2026-09-17, NOT PROMOTED. n=30 seed-paired, 60 clean sweeps, zero failures: mechanism confirmed at scale (`unreachable` 0 -> 235, `expired` -236, near 1:1), parity held (worst game -1, at the bar not past it), and **no effect on depth or score** (L2 clears 0 -> 0; median 0.0521 -> 0.0538, 12W/9L/9T, p=0.66). The gate does exactly what it claims and buys nothing measurable, because the defect it exposed is what actually kills the bets. Flag stays DEFAULT OFF — a change with no measured benefit does not earn a default. Exposed a second, larger budget defect that is deliberately left unfixed — see "What this exposed".
Research question: RQ4 (planning) / RQ3 (active testing)
Date opened: 2026-09-17
Origin: gate 1 (`H010` Stage 3). The cd82 two-condition oracle expired unmet
on every run measured, `spent=8/8`, `unmet=8`, `jointly_met=0`, with the
controlled thing frozen in place and the target 10-48 units away. The cause
was not coverage and not the state condition: `_hypothesis_action` computes
which preconditions are unmet, tries to route to the first, and when
`_plan_route` finds no path in either transition model the branch falls
through to the lever anyway ("Falls back to the lever when no path").

This is the minimal form of the ladder's gate 4 — "do not spend live budget
on a hypothesis the model says will not work". It needs no predictor: the
information is on the line above the fall-through.

## Claim

When a bet's precondition is unmet and no route to it exists, pressing the
lever spends an action that cannot test anything. Declining that decision,
and retiring the bet after a run of such decisions, converts wasted presses
into movement without changing how a bet that *is* testable dies.

## Mechanism

`Hypothesis.stall()` counts a declined decision — nothing appended to
`history`, nothing filed in `outcomes`, so no evidence about the residual is
invented. `HYPOTHESIS_STALL` (6) consecutive stalls retire the bet as
`UNREACHABLE`, a status distinct from `EXPIRED`: "never tested" and "tested,
inconclusive" are different facts and the proposer should not read them
alike. `reached()` resets the run whenever a route reappears. An
`UNREACHABLE` bet takes the same short cooldown as an unmet-heavy expiry —
its key is not discredited, it was simply not reachable this time.
`_hypothesis_action` returns `None` on a declined decision, so the tiers
below use the action instead.

## Prediction

- P1 (mechanism). On the cd82 oracle, lever presses taken with the
  precondition known false fall to 0, and the actions go to routing instead.
  **Met, seed 1 at injection 154: ACTION5-with-precondition-false 6 -> 0;
  routing moves 1 -> 7; distinct positions visited while live 2 -> 6.**
- P2 (consumer). Joint satisfaction of the two-condition oracle rises.
  **NOT met — and the reason is instructive; see below.**
- P3 (parity). n>=30 seed-paired whole-sweep parity: no regression beyond
  the standing "> 1 level-1 clear per 30 sweeps" bar on games that already
  work, read after the level-2 funnel. **NOT RUN.**

## Falsifier

- Wasted presses do not fall, or the freed actions do not go to routing:
  the fall-through was not what was consuming the budget.
- The parity sweep regresses past the bar: declining to press costs more
  than it saves, and the bet should spend rather than stall.

## What this exposed (and why it is deliberately not fixed here)

With the gate on, seed 1 still expires at `spent=8/8`. The presses are gone,
but **the routing steps themselves charge the budget**: `_learn_from`
observes the live bet on every decision whose tier is `hypothesis`,
including pure precondition-chasing moves, filing each as
`PRECONDITION_UNMET`. Measured, gate on: 8 budget-charging steps = 0 lever
presses + 7 routing moves + 1 click.

So the deeper defect is that **`HYPOTHESIS_BUDGET` prices travel as though it
were testing.** A target 10+ units away cannot be reached inside 8, so the
bet dies before it is ever tested, however good the router is.

This is not a bug — it is the council's "price every test in actions" applied
to a step that is not a test. Changing it is a real design decision with its
own risks (bets living far longer, monopolising the action stream), so it
gets its own hypothesis and its own gate rather than being folded in here
under the same flag. **One live behavioural change at a time.**

## Experiment

Offline/oracle first, done: `scripts/h010_stage3_diagnosis.py` with
`ARC_BUDGET_GATE=0/1`, seeds 1 and 3, `H007_INJECT_AFTER=150`. Then the
n>=30 seed-paired whole-sweep parity check before the flag's default flips.
Note the gate is only reachable under `ARC_PROPOSER=1`, which is off in the
submission, so it has no bearing on the leaderboard either way until both
flags flip.

## Metrics

Lever presses taken with the precondition false; routing moves; distinct
positions visited while a bet is live; `UNREACHABLE` vs `EXPIRED` counts in
the hypothesis log; then the level-2 funnel and the exploration-cost set
(coverage, concentration, novelty, useful-transition yield), and aggregate
score last.

## Status log

- 2026-09-17 opened and built. `agent/constants.py` (`HYPOTHESIS_STALL`,
  `USE_BUDGET_GATE`), `agent/hypothesis.py` (`UNREACHABLE`, `stalled`,
  `stall()`, `reached()`, cooldown), `agent/my_agent.py` (the decline, and
  `UNREACHABLE` reaching the LLM's died-since-call counter). 5 new tests,
  301 total, green with the flag both off and on. P1 met, P2 not met, P3
  not run. The P2 failure is the finding, not a disappointment: it localises
  the remaining defect precisely, one level below where gate 1 left it.
- 2026-09-17 (night) **n>=30 parity sweep launched, running.** Seeds 601-630,
  both arms, whole 25-game sweep, 400 steps, `ARC_PROPOSER=1` on both (the
  gate is unreachable without it), `--no-log`. Seed-paired: each seed runs
  `ARC_BUDGET_GATE=0` then `=1` back to back.
  Two operational notes. The sweep summary's `config` records `max_steps`
  only, so it **cannot** distinguish the arms — both run the same code and
  differ only by the env flag. A manifest (`h015_manifest.jsonl`, one line
  per run: seed, arm, rc, seconds, summary path) is written as each run
  finishes, so the arms stay separable and a crash mid-run still leaves the
  completed runs analysable. This is the gap that made H011's own two arms
  indistinguishable from their summaries after the fact.
  The tree is frozen for the duration: no `agent/` edits while it runs.
  Read the result on the **level-2 funnel first** (L1 completions, L2
  entries, L2 completions, actions-to-L2/L3), then the exploration-cost set,
  then `UNREACHABLE` vs `EXPIRED` counts in the hypothesis logs, and the
  aggregate score last.

- 2026-09-17 **n=30 parity sweep done: 60 runs, 5.0 h, zero failures, zero
  missing summaries, all 30 seeds paired.** Read in the standing order.

  **1. Level-2 funnel (read first).** L1 clears 99 -> 97 across 750
  game-sweeps; **L2 clears 0 -> 0**; L3 0 -> 0; mean actions-to-L2
  182.9 -> 177.9. The -2 on L1 is a balanced shuffle, not a loss:
  per-seed 5W/7L/18T, p=0.77, and per-game it is cd82 +2, cn04 -2,
  sp80 -1, ar25 -1. **Level 2 remains untouched, which is the headline:
  this change does not move depth.**

  **2. Status mix — the mechanism, confirmed at scale.** `unreachable`
  0 -> 235 with `expired` 5109 -> 4873 (-236). Near 1:1: 235 bets that
  would have burned their budget being unroutable now retire without
  spending it. `falsified` -59, `live` -327, `held` -47.

  **3. Parity.** sp80 24 -> 23, ar25 8 -> 7, ls20/m0r0/dc22 flat. Worst
  case -1, at the pre-agreed "> 1 per 30 sweeps" bar rather than past it
  — the same boundary reading H010 Stage 2 got on sp80.

  **4. Aggregate score (last).** median 0.0521 -> 0.0538, mean
  0.0881 -> 0.0908, sign test 12W/9L/9T, p = 0.66. Not significant.

  **Verdict: the gate passes and is not promoted.** P1 met at scale, P3
  met, P2 still not met. It reclaims 235 wasted budgets and converts none
  of them into depth, exactly as predicted once the routing-charges-budget
  defect was found: stopping the waste does not help while a bet still
  dies travelling. Keeping it OFF costs nothing (it is unreachable without
  `ARC_PROPOSER` anyway) and keeps one variable out of the next
  comparison. Promote it only if the budget-pricing fix lands and the two
  together move the funnel.

  **A limitation of this sweep, stated rather than buried.** It was run
  `--no-log` to avoid ~3 GB of per-step recordings, and the summaries carry
  no click coordinates — so the **exploration-cost set adopted the same day
  (concentration, novelty, useful-transition yield) could not be computed
  from it at all.** The nearest available proxy, the predictor's own
  accuracy, is identical between arms (entity 0.8893 vs 0.8898, pair 0.9564
  vs 0.9565 over 750 game-sweeps each), which is consistent with "the freed
  actions did not produce better model information" but does not measure
  the adopted metric. Any future sweep meant to read those metrics needs
  logs on, or the summary needs to carry the counters.