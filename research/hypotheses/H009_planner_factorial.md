# H009: cd82's walk fails in the planner's model class, not in the representation or the search

Status: OPENED — not run
Research question: RQ2 (predictive world modelling) / RQ4 (planning)
Date opened: 2026-09-15
Origin: user-relayed reviewer proposal (2026-09-15 evening), on top of
`H007` Day 4's result — the state condition was satisfied in one step on
every seed, and what kept the joint test from happening was `_route_to`
finding no path to the block's −x side on 6 of 7 steps. Before changing
representation, planner or exploration together, separate them.

## Claim

On cd82 the controlled thing's motion is a deterministic function of
(its position, the action) — the state the tracker already holds is
sufficient — but not of the action alone, which is the only model class
the router's planner has (`learned_moves`: one displacement per action,
BFS in displacement space). So: a search over the *empirical position
graph* finds the walk to the −x side of the block wherever one exists;
the current planner either returns no path or a path that the true
dynamics do not honour. The defect is the transition model's class, not
the search and not the representation.

## Mechanism (the factorial)

```
T_learned   learned_moves as the agent forms them (one offset per action)
T_oracle    the empirical table  (pos_t, action) -> pos_{t+1}  from the traces
target      the set of controlled-thing positions that satisfy
            adjacent:-x of the block (bbox_gap <= 1, side_of == -x)
planner     navigation.plan (BFS over offsets)  |  BFS over T_oracle

E0  is T_oracle a function?      determinism of (pos, action) -> pos'   [C if not]
E1  T_learned + target + navigation.plan     path found? honoured by T_oracle?
E2  T_oracle  + target + BFS                 path found?  length?
E3  T_learned + target + BFS over T_oracle-validated steps   (does the search
    algorithm matter once the model is right?)
```

Read as the reviewer set it out:

| E2 | E1 | reading |
|---|---|---|
| path | path, honoured | A: representation, condition, transition, planning all fine; the gap is above — goal / action selection |
| path | none, or not honoured | B: the transition model class is insufficient (position-dependent moves need a position graph) |
| none | — | C: position is not the state that decides motion; something else does (E0 says what) |

## Prediction

1. E0: (pos, action) → pos' is deterministic on cd82 across all ten
   seeds (every (pos, action) seen ≥ 2 times has one successor), and
   pos' − pos is *not* a function of the action alone.
2. E2: from ≥ 90% of visited positions a path to a −x-adjacent position
   exists in T_oracle, length ≤ 6.
3. E1: `navigation.plan` returns no path, or a path T_oracle does not
   honour, from ≥ 50% of those same positions — reading B.

## Falsifier

- E0 non-deterministic: position is not sufficient (reading C); then
  ask whether Z1 or the strip state restores determinism before
  anything else.
- E1 finds honoured paths from most positions: the planner is fine, and
  H007's 6-of-7 "no path" was something else (a target computation
  bug, an obstacle-map artefact) — reading A, and a bug hunt.
- E2 finds no path: the −x side is unreachable by the bucket's orbit —
  the condition itself is wrong, and H001's tally must be re-read.

## Experiment

Offline first, over `recordings/latent/seed*/cd82.jsonl` (the tap
records the CONTROL thing's bbox, the block's bbox, and — after the
Day-5 retrace — `learned_moves` and `displacement`): E0 and E2 need only
the traces; E1 replays `navigation.plan` with the recorded move map at
each step and validates the returned path through T_oracle. Live only if
the offline read is ambiguous.

## Metrics

E0 determinism (successors per (pos, action)); E2 reachability and path
length; E1 path-found rate, honoured rate, first divergence step.

## Status log

- 2026-09-15 opened.
- 2026-09-15 **Run, offline + one cd82 tap, ten seeds. Reading B.**
  `scripts/h009_planner.py`; E0/E2 from the S_t traces (level 0 only).

  **E0 — position is sufficient.** The bucket occupies 8 orbit positions
  (bbox top-left) at level 0; 32 of 32 (position, action) contexts seen
  ≥ 2 times have exactly one successor across ten seeds (with the canvas
  entity — sometimes flagged CONTROL — excluded; with it in, 78%). The
  displacement is *not* a function of the action alone: each action has
  5 distinct deltas (ACTION3: (−8,5) ×293, (−11,−3) ×147, (0,0), …).
  P1 met.

  **E2 — the walk exists.** −x-adjacent positions: (14,21), (14,40),
  (17,32). Through the empirical graph a target is reachable from every
  one of 1,779 off-target decisions, in ≤ 3 actions (e.g. (33,40):
  ACTION3, ACTION3; (38,32): ACTION1, ACTION3, ACTION3). P2 met.

  **E1 — the agent's planner, at every decision of ten real runs.**
  The learned move map is `{ACTION1: (0,−11), ACTION2: (0,11),
  ACTION3: (−11,0), ACTION4: (11,0)}` — four axis translations of 11,
  because `_detect_translation` reads a rigid 11-cell shift somewhere
  in the diff while the bucket's bbox actually hops diagonally and
  re-rasterises. Of 1,779 decisions: a path returned on 1,244 (70%);
  none on 535 (`plan` None 352, block not live 150, no anchor 27, no
  moves 6). **0 of 1,244 paths are honoured at their first step** (the
  offset never matches the true successor). Followed blindly through
  the true dynamics anyway, 728 of 1,244 (59%) end at a target and 792
  (64%) pass through one — the lattice happens to point the right way.
  But the live router drops a plan the moment the displacement fails
  to match its expectation, which is *every* plan after one step, so
  live the agent re-plans from scratch each step and never strings the
  two or three hops together. Planned lengths 1–11 (52 plans of 11)
  against a true diameter of 3. P3 met.

  **Verdict: B.** Representation (position) sufficient; condition
  expressible (H007); search fine (BFS finds the walk in the right
  graph); the **transition model's class** — one offset per action in a
  displacement lattice — cannot represent an orbit whose hop depends on
  where you stand. That is H003's "state-dependent geometry" finding,
  now with a direct causal test behind it and a concrete fix: a
  position-graph transition model for the CONTROL thing (`(pos, action)
  -> pos'`, admitted where deterministic — the same admit rule as
  H006's), which `navigation.plan` can search unchanged. Not built this
  week; it is the first item on week 2's list, above information gain.
