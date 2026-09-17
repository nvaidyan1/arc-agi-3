# H012: Sighting-count novelty in the frontier tier raises orbit coverage

Status: OPENED — not built; CONDITIONAL, not next. Resequenced 2026-09-17 to gate 3 of the `docs/plan.md` START HERE ladder: two cheaper discriminating tests (gate 1, H010 Stage 3's exact-failure diagnosis; gate 2, the H007 P2 re-test under H011) now stand ahead of it, and this hypothesis proceeds only if one of them shows movement coverage to be the limiting factor. Primary success criterion upgraded from orbit coverage to joint-condition satisfaction — see P0.
Research question: RQ3 (active testing)
Date opened: 2026-09-16
Origin: the movement-side symmetric counterpart to H011 (click novelty),
proposed independently by two reviewers converging on the same gap.
H009's closing experiment found one seed in ten never completes cd82's
8-position orbit in 400 steps (7 of 8 positions, 9 of 32 edges) because
`_select`'s `novel`/frontier tier only asks whether a displacement has
ever been visited — a bare bit, not how well-characterized it is — and
sits behind `strong_route`, so it is not always reached. H007's own
status log names the same gap as the reason its enumerator cannot form
a state-conditioned lever (P2, still blocked). Split from H011 rather
than folded into it as "Stage 2b": a separately falsifiable claim, same
reasoning that split H006/H007/H008 apart — this can succeed or fail on
its own regardless of the click-side result.

## Claim

Scoring candidate movement actions by how many times the exact
`(position, action)` pair has been observed — via `PositionModel.edges`
where it exists, `MoveModel`'s per-offset counts otherwise — rather than
a visited/unvisited bit on the resulting displacement, raises orbit
coverage on cd82 (and any other game whose motion is position-dependent)
without regressing games whose current move-based frontier tier already
works.

What this is not: no new representation (reads `PositionModel`/
`MoveModel` state that already exists); not the router (`navigation.py`
is untouched); no LLM.

## Mechanism

```
_select's frontier tier today:
    novel = [a for a in candidates if a in moves
             and (position + moves[a]) not in self.moves.visited]
    -- a bare bit: has this DISPLACEMENT ever been reached, regardless
       of how many times, or from how many different positions/actions

H012:
    score(a) = 1 / (1 + sightings of (position, a))
        sightings from PositionModel.edges' backing counts where a
        position-graph edge exists for (position, a); from
        MoveModel's per-action total tries otherwise (the offset model
        has no per-position count to fall back on -- this is the
        expected, graceful degrade on games H010 never touches)
    weighted draw over candidates in the frontier tier, same shape as
    H011's blend: salience (still-in-frontier-tier) + novelty term,
    not a replacement of the tier structure entirely
```

Flag-gated per both reviewers' operating rule: `ARC_MOVEMENT_NOVELTY`,
default off, so a live A/B needs no tree edit to switch arms — the
gap H011 Stage 2 left uncorrected (built unconditionally, no flag).

## Prediction

- P0 (**primary, added 2026-09-17**). Joint satisfaction of the
  two-condition cd82 oracle rises on the seeds that gate 1 shows to be
  coverage-blocked. This, not orbit coverage, is the criterion this
  hypothesis is judged on. The reason for the upgrade: H010 Stage 2
  proved a navigation mechanism and moved no joint-satisfaction rate,
  which is exactly the failure mode of measuring the mechanism instead
  of the thing the mechanism was for. Orbit coverage (P1) is now the
  *mechanism* check; P0 is the *consumer* check, and P1 passing while
  P0 fails is a negative result for this hypothesis, not a partial win.
- P1. On the ten seeds used for H009's live-episode closing experiment,
  the previously-missing orbit position on cd82 appears in >= 9 of 10
  seeds by decision 150 (H009's own bar: 8/10 at that checkpoint
  without this change).
- P2. A whole-sweep, n>=30, seed-paired parity check on games with an
  existing clean move map (sp80, ls20, ar25, m0r0, dc22) loses no more
  than 1 level-1 clear per 30 sweeps relative to pre-H012 — the same
  bar both reviewers converged on for H010 Stage 2, applied here first
  since this is the smaller, earlier change.
- P3 (explicitly NOT this hypothesis's claim — see Origin). Whether
  H007's enumerator can now form a state-conditioned lever depends on
  CLICK coverage (H011, already live), not movement coverage: the
  swatch strip is reached by ACTION6, which this tier does not touch.
  Re-testing H007 P2 is its own check, decoupled from H012, and can run
  as soon as H011 Stage 2 clears its own parity gate — it does not need
  to wait for this hypothesis.
  **Update 2026-09-17: H011 cleared that gate on 2026-09-16 and the P2
  re-test was still never run** — it was mistakenly recorded as folded
  forward in the first 09-17 plan draft. It is now gate 2 of the ladder,
  ahead of this hypothesis and at equal priority with gate 1. This
  paragraph's decoupling claim was correct and is unchanged; what was
  wrong was the assumption that the decoupled check had happened.

## Falsifier

- Coverage does not rise (orbit completion stays at 8/10 or worse by
  decision 150): the bottleneck is elsewhere in the tier ordering (e.g.
  `strong_route` claiming the decision before frontier is ever reached),
  not the bare-bit vs sighting-count distinction.
- The n>=30 parity check regresses by more than 1 level-1 clear per 30
  sweeps on the move-map games: the same concentration trade-off H011
  found on the click side has a movement-side analogue, and this needs
  softening (a blend weight, not a full replacement) before it ships.

## Experiment

Offline first: replay `recordings/latent/seed*/cd82.jsonl` (already
have `_z1`-style per-step position/action data from H009/H010's own
scripts) and ask, at each real movement decision, whether a
sighting-count re-ranking would have reached the missing position
sooner — the same counterfactual-re-ranking method H011 Stage 1 used,
before any live code. Then live, behind `ARC_MOVEMENT_NOVELTY=1`: the
ten H009-seed live-episode replay (P1), then the n>=30 parity sweep
(P2).

## Metrics

Joint-condition satisfaction rate on the coverage-blocked seeds (P0, the
primary read); orbit-position coverage by decision checkpoint (P1,
matching H009's closing table); n>=30 parity: level-1 clears per game,
whole-sweep median score, sign test.

**The standing metrics apply here and are not optional** (`docs/plan.md`
START HERE, 2026-09-17). Report the **level-2 funnel** — L1 completions,
L2 entries, L2 completions, actions-to-L2/L3 — above the aggregate. And
report the **exploration-cost set**, because this is the movement-side
analogue of exactly the trade-off H011 measured on the click side (the
hottest 8x8 region's share fell 20% -> 14-18%): coverage, concentration,
novelty, **useful-transition yield**, level progression, actions-to-level.
Useful-transition yield is the one that connects this hypothesis to the
thesis — not "how many new positions did we touch?" but "how many
exploratory actions produced information that subsequently entered a
predictive model, a hypothesis, or a skill?" A coverage rise with no
yield rise is a negative result.

## Status log

- 2026-09-16 opened, per both reviewers' converged sequencing. Not
  built; waiting on H011 Stage 2's own n=30 parity result first (the
  explicit, agreed gate before any further live behavioural change).
- 2026-09-17 **resequenced to conditional, and its success criterion
  upgraded**, after a third read (a colleague's note against reviewer C's
  fifth pass, then C against the note). Two changes. (i) This is no longer
  "the next behavioural change": gates 1 and 2 of the new ladder are
  cheaper, are both diagnostics on data largely already held, and either
  can establish or remove the mandate for it. H012 proceeds if gate 1
  finds the required edge absent at the oracle's critical step, or if
  gate 2 shows coverage still preventing state-conditioned evidence from
  accumulating. (ii) P0 supersedes P1 as the criterion: measure joint-
  condition satisfaction, not orbit coverage. Both changes come from the
  same lesson in H010 Stage 2 — a mechanism can be proven while the thing
  it was built for does not move. Still not built; nothing here is
  invalidated, only reordered and re-pointed at the consumer.
