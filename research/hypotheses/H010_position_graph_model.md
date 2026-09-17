# H010: A position-graph transition model closes the gap H009 found

Status: STAGE 2 SHIPPED, MECHANISM PROVEN — LIVE OUTCOME UNRESOLVED. Persistence and crash-safety proven (unit tests + live trace + a corrected n=30 sweep with zero errors); named parity games hold (one, sp80, at the exact gate boundary, not past it); cd82 moved +1/30 level-1 clears. But the two-condition cd82 oracle this stage was meant to finally close still did not close end-to-end — see "Stage 2" below. Not marked TESTED/CLOSED because its own stated success criterion (H007's oracle joint-satisfaction rate) was not met.
Research question: RQ2 (predictive world modelling) / RQ4 (planning)
Date opened: 2026-09-15
Origin: `H009`'s reading B — cd82's controlled thing is a deterministic
function of (position, action), not of the action alone, and
`navigation.plan`'s offset model (`MoveModel.learned_moves`) is honoured
at the first step of 0 of 1,244 real plans. User-approved next step
(2026-09-15 night): build the model, validate offline against H009's own
cd82 graph, before touching the live router.

## Claim

A transition model keyed by `(position, action)` rather than by action
alone — admitted only where the transition has been seen to be
deterministic, H006's admit rule — represents cd82's orbit correctly,
and the existing BFS planner can search it with no change to its
algorithm, only to what edges it is given.

## Mechanism

```
PositionModel (agent/control.py)
    observe(position, action, next_position)
    edges -> {(position, action): next_position}
             admitted iff seen >= MIN_POSITION_OBSERVATIONS (2) times,
             every sighting the SAME successor (not a majority vote —
             an edge that ever disagreed with itself is excluded, not
             resolved by outvoting the disagreement)
    persists across RESET (a property of the game); clears on a new level

navigation.py
    _bfs(start, target, actions, successor, is_blocked)   the search both
        plan and plan_graph now share — extracted from plan() unchanged
    plan(start, target, moves, is_blocked)                 UNCHANGED
        signature and behaviour; internally now one line: builds an
        offset-based successor and calls _bfs
    plan_graph(start, target, edges, is_blocked)            NEW
        graph-based successor (edges.get((pos, action))); no
        extrapolation to an unobserved position — the deliberate
        opposite of plan's optimistic offset-everywhere assumption,
        which is exactly what made it confidently wrong on cd82
```

## Predictions (Stage 1)

- P1. `PositionModel.edges`, built from real `.observe()` calls over the
  cd82 traces, matches H009's own oracle graph.
- P2. `navigation.plan_graph` reaches a −x-adjacent target from every
  orbit position within the same bound H009's independent BFS found
  (≤ 3 actions).
- P3. Replaying H009's own 1,779 traced decisions through `plan_graph`
  instead of `plan`: paths found and honoured at the first step, at or
  near 100% — against `plan`'s 1,244/1,779 found, 0/1,244 honoured.

## Falsifier

- `PositionModel.edges` disagrees with H009's oracle graph (a bug in
  the admit rule, or a real difference in how the two were built).
- `plan_graph` cannot reach a target from a position H009's BFS could —
  a bug in `_bfs` or the extraction from `plan`.
- Replayed honoured rate stays well under 100% — position-keying alone
  is not sufficient (something else varies at fixed (position, action)
  after all, contradicting H009's E0).

## Experiment (Stage 1 — offline, no live agent)

`scripts/h010_position_model.py`: builds a `PositionModel` from
`recordings/latent/seed*/cd82.jsonl` through real `.observe()` calls;
prints its admitted edges; runs `plan_graph` from every recorded orbit
position to the nearest −x-adjacent target; replays every decision
`scripts/h009_planner.py trace` recorded (`recordings/latent_h009/`)
and asks whether `plan_graph`'s first step would have been honoured.

## Metrics

Edges admitted vs H009's oracle graph (exact match/mismatch); path
lengths per position; found-rate and honoured-rate over the 1,779
replayed decisions, against `plan`'s own numbers on the same set.

## Status log

- 2026-09-15 opened, Stage 1 built and run.

  **Built** (`agent/control.py`): `PositionModel` — `observe`, `edges`
  (H006's determinism admit rule, not `MoveModel`'s majority one),
  `clear`. `MIN_POSITION_OBSERVATIONS = 2` (`agent/constants.py`), the
  same threshold this project's own H006/H009 analysis used all session
  to call a transition deterministic.

  **Built** (`agent/navigation.py`): `plan`'s BFS body extracted into a
  shared `_bfs(start, target, actions, successor, is_blocked)`; `plan`'s
  public signature and behaviour are **byte-for-byte unchanged** — it now
  calls `_bfs` with an offset-based successor, one line different
  internally. `plan_graph(start, target, edges, is_blocked)` is new,
  same contract, graph-keyed successor, no extrapolation to unobserved
  positions.

  **Tested.** 12 new unit tests (7 `navigation`, 5 `control`): a
  position-dependent 3-cell orbit that no fixed-offset model could route
  (`plan_graph` chains it correctly); an edge that ever disagreed with
  itself is refused even with 20:1 support the other way (no majority
  vote); the admit-rule floor; per-position keying (the same action from
  two positions is two independent edges); a sanity check that `plan`
  and `plan_graph` agree exactly when fed the same action-only graph
  (confirms the shared `_bfs` did not silently change `plan`'s
  behaviour). **278/278 tests pass, all 266 pre-existing unchanged.**

  **Run** (`scripts/h010_position_model.py`), through the real classes,
  not a scratch copy:

  | check | result |
  |---|---|
  | P1: edges admitted | 32, matching H009's oracle graph exactly (same 8 positions, same successors) |
  | P2: reachability, `plan_graph` | every off-target position reaches a −x target in 1–3 actions (1×1, 2×2, 1×3) — H009's own bound, now reproduced through the real planner |
  | P3: 1,779 replayed decisions | path found **1,779/1,779** (100%, vs `plan`'s 1,244/1,779 = 70%); honoured at the first step **1,779/1,779** (100%, vs `plan`'s **0/1,244**) |

  One bug caught and fixed in the validation script itself before
  trusting P2's numbers: the first pass tried only one of the three
  target cells per position and kept whatever path that returned,
  understating the true shortest route (e.g. (33,21) read as a 4-step
  path via a wrong detour before the fix, 2 steps — matching H009's own
  table — after it). `plan_graph` and `_bfs` were never the source of
  the discrepancy; the script's "nearest of several targets" loop was.

  **Inference.** Stage 1 predictions P1–P3 all met, cleanly, with no
  ambiguity: the position-graph model represents cd82's orbit exactly,
  the shared planner finds the same walk H009's independent BFS found,
  and every one of H009's own real decisions would have been honoured
  had this model been asked instead of the offset one. This is the
  building block H009 called for, proven against H009's own data through
  the actual code that will run live — not yet running live. Stage 2
  (wiring `PositionModel.observe` into `_learn_from`, and making
  `_route_to`/`_route_for` prefer `plan_graph` over `plan` when it has
  edges) needs a regression design first: `plan_graph` deliberately does
  NOT extrapolate to unobserved positions the way `plan`'s offset model
  does, so on a game where motion is genuinely position-independent but
  coverage is sparse, preferring the graph could return a shorter
  partial route than the offset model's optimistic extrapolation would —
  a real behavioural difference, not obviously a regression, but one
  that needs a parity sweep across the games with an existing move map
  (sp80, ls20, ar25, m0r0, dc22, …) before it ships, not an assumption
  that "more precise" implies "no worse."
- 2026-09-15 **A real bug caught by test flakiness, fixed.** The
  `make test` chain that verified this Stage's commit used
  `make test 2>&1 | tail -1`, which masks a failure (the pipeline's exit
  status is `tail`'s, not `make`'s) — the commit landed before the
  flake was seen. Re-running ten times surfaced it: 1 in ~3-5 runs,
  `test_plan_and_plan_graph_agree_when_the_graph_is_action_only` failed
  with the two paths disagreeing. Root cause: `plan_graph`'s
  `actions = {a for (_pos, a) in edges}` is a bare set of `GameAction`
  members, whose hash is identity-based and **not stable across process
  runs** (measured directly: `hash(GameAction.ACTION2)` differs between
  two Python invocations). Set iteration order therefore varies run to
  run, and where several equally-short routes exist, `plan_graph` could
  pick a different one on two runs given byte-identical `edges` — a real
  determinism defect, not a test artifact, and one that would have
  broken the seed-reproducibility guarantee this project's replay
  harness depends on had it reached the live agent. Fixed:
  `sorted(..., key=lambda a: a.value)`. Verified stable over 30
  consecutive runs of the affected test and 10 of the full suite; H010's
  own offline validation (P1–P3) is bit-for-bit unchanged by the fix,
  as expected — it never depended on which of several equal-length
  routes was chosen. Lesson recorded for the standing rules: never gate
  a commit on `make test | tail -N`; the pipeline's exit code is the
  last command's, not `make`'s.

## Stage 2: wired live, two real bugs caught, and one claim that stays open

**What this stage set out to answer** (per both reviewers' converged
sequencing, `docs/plan.md` 2026-09-16): does wiring the proven Stage-1
model into the live router actually let cd82's two-condition oracle
(H007) close, and does it hold up under a real matched-seed sweep on the
games that already work.

**Built.** `PositionModel.observe()` feeds the graph from `_learn_from`
on every confirmed translation/shift, exactly as `MoveModel.
observe_translation` already does (same evidence, no new perception).
`_route_to`/`_route_for` prefer `plan_graph` over the offset model when
the graph has edges from the current position, falling back gracefully
otherwise (`_plan_route`). `PositionModel` persists across RESET and
clears on a new level, matching `MoveModel`'s own game-vs-attempt
distinction.

**Bug 1, found live: no persistence.** The first oracle retest showed
the router honouring a first step correctly (a real change — the old
offset model never did this, 0 of 1,244 in H009's own measurement) but
never completing a multi-step walk, because `_route_to` recomputed a
fresh path every decision with no memory of one already in progress. A
single interrupting action that never even moved the agent (an epsilon
click) was enough to erase all progress. **Fixed**: `Route.next_action`
generalised to accept the position-graph edges alongside the offset
model (preferring whichever has real evidence for the exact current
position); a new `self.precondition_route` (a persistent `Route`,
separate from the one `_maintain_route` already owns) is continued
across decisions unless the target changed or the position drifted from
what it expected. Verified via unit tests and a live trace where the
agent visibly chained multiple route steps and survived an interruption
that would have derailed the pre-fix code.

**Bug 2, found live, more serious: a crash.** Retesting the oracle at
this point still didn't close it (see below), so the work moved to the
real n=30 statistical test — where the first treatment run crashed on 5
of 30 seeds with a `KeyError`. Root cause: a stored route's next action
fell out of legality (or out of both models' coverage for the current
position) between decisions, and `Route.next_action` had no fallback for
that case. `_maintain_route` — the agent's other, pre-existing routing
system — already carried the exact defensive check this needed
(`actions[0] not in candidates or actions[0] not in moves or has_
drifted`); it was never replicated for the new persistent route. **The
whole first treatment run, including the 25 seeds that hadn't crashed,
was discarded as invalid** — it ran under code proven capable of
crashing, so none of its output could be trusted, successful-looking or
not. Fixed by mirroring that same three-part check before ever calling
`next_action`, plus hardening `next_action` itself to degrade instead of
raising if a caller ever fails to check first. Two regression tests
reproduce the exact crash; all five previously-crashed seeds verified
clean afterward; the full n=30 treatment sweep was rerun from scratch
against the fixed code.

**The corrected n=30 result** (seeds 501-530, 400 steps, `ARC_PROPOSER=1`
— the only condition under which any of this code is ever reached; it
is off by default in the actual submission, so this result has zero
bearing on the current leaderboard score either way):

| | baseline | treatment |
|---|---|---|
| aggregate_score mean (6 games) | 0.2096 | 0.2029 |
| aggregate_score median (6 games) | 0.1864 | 0.1727 |
| sign test (7W/10L/13T) | — | p = 0.63, not significant |
| ar25 / m0r0 / ls20 / dc22 L1+ | 10 / 10 / 1 / 0 | 10 / 10 / 1 / 0 (unchanged) |
| sp80 L1+ | 18/30 | 17/30 (−1, at the gate's exact edge) |
| **cd82 L1+ (the target game)** | 6/30 | 7/30 (+1) |

Gate read: the four named parity games besides sp80 are untouched;
sp80's drop of exactly 1 does not exceed the pre-agreed ">1" bar, though
it sits precisely on it rather than comfortably inside it. cd82 moved in
the predicted direction, modestly. The 6-game aggregate is flat to
slightly negative and not significant — expected, since only cd82 among
these six games is a plausible beneficiary of a position-dependent
transition model; the other five already have simple, uniform move maps
the old offset model already served well, so any real cd82-specific
effect is diluted by five games with nothing to gain.

**What Stage 2 proves, and what it does not — kept explicitly separate,
per council review (2026-09-17), which found the first draft of this
result was at risk of conflating them:**

- PROVEN: the position-graph model is honoured at the first step where
  the offset model never was; a persistent route survives a
  non-moving interruption where the old code always lost it; the
  wiring does not crash and does not measurably regress the four
  parity games with headroom, one game at the boundary; cd82 moved in
  the right direction.
- NOT PROVEN: the specific two-condition cd82 oracle that originally
  motivated this whole thread (H007 + H009 + H010 together) still did
  not close end-to-end after both bugs were fixed. Seeds 1 and 3 of
  the retest still expired unmet; the joint-satisfaction rate did not
  rise on the walk-blocked seeds H007 specifically named as this
  stage's success criterion. The reason is diagnosed as different from
  either bug fixed here — graph coverage incompleteness at the exact
  point in the episode the oracle needs it — but that diagnosis was
  not chased further this stage. **This is the one open thread from
  Stage 2**: whether it is a coverage problem H012 will incidentally
  fix, a genuine gap needing its own follow-up, or something else has
  not been determined.

**Decision: ship the infrastructure, do not close the hypothesis.** The
mechanism is real, tested, safe to merge (inert by default), and an
improvement over what existed. The oracle's continued failure means
H010's own originally-stated success criterion is not yet met, so this
stays open rather than being marked TESTED/CLOSED outright.
