# H010: A position-graph transition model closes the gap H009 found

Status: STAGE 1 TESTED — offline, through the real production code; Stage 2 (live wiring) not built
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
