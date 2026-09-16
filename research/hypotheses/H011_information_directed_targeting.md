# H011: A novelty term in target selection reaches under-explored cells the salience heuristic misses

Status: TESTED (Stage 1 offline + Stage 2 live) — the click blend is built (`agent/attention.py`) and swept live on cd82: strip clicks 1.6% -> 42-52% at every weight tried. The effect is almost entirely structural (ending the hard tier cutoff), not the novelty term's weight, and comes with a measured, real trade-off (the hottest-region click share fell from ~20% to 14-18%). Movement-side novelty (the frontier tier in `_select`) is not yet built. Uncommitted as of 2026-09-16: a matched-seed (n=30) whole-sweep parity check is running before this is finalized.
Research question: RQ3 (active testing)
Date opened: 2026-09-15
Origin: two independent findings from this week point at the same gap.
H007 (Day 4) measured that cd82's swatch strip is clicked 4 of 322 times
(1.2%) because `ClickTargeting.pick()` ranks by visual salience, not by
how uncharacterized a cell's outcome is. H009's closing experiment found
one seed in ten never visits one of cd82's 8 orbit positions in 400
steps, for the same underlying reason at the movement layer: nothing in
`_select`'s tiers scores an action by how little is known about its
outcome from here, only by whether it has ever been visited at all
(`novel`/frontier) or by accumulated reward (`_weighted_choice`). The
review's fourth pass named this directly (§7): information-seeking
actions are not first-class, only useful-action selection is.

## Claim

A term scoring a candidate (click target, or movement action) by how
little evidence exists about its outcome — not by whether it is
currently salient, and not merely by whether it has ever been tried —
would select cd82's swatch strip, and seed 4's missing orbit position,
materially more often than the current salience/visited-once heuristics
do, using only evidence the agent already keeps.

What this is not: no new representation (the term reads existing
counts — `ClickTargeting._tries`, `Belief.acted`, `PositionModel`/
`MoveModel.visited` — it adds no new state); no router change (Stage 1
is pure re-ranking of `pick()`'s candidates, offline); no LLM.

## Mechanism

```
novelty(cell)     1 / (1 + tries_so_far[cell])       -- click targeting
                  0 for a background cell (nothing to click)
info_rank(cells)  sorted by novelty, ties broken however pick() already does

Stage 1 (this doc): OFFLINE counterfactual re-ranking, holding every
recorded frame and every REAL click fixed (the same limitation H006's
splitter and H009's per-decision replays already accept — this measures
whether the targeting MECHANISM is biased, board-state by board-state,
not a full alternate trajectory, which no offline replay can produce
once actions diverge).

Stage 2 (not this doc): novelty as an explicit term inside
ClickTargeting.pick() (a new tier, or a blend with salience), and the
equivalent for movement actions in _select (scoring `novel` candidates
by PositionModel/MoveModel sighting counts instead of a bare
visited/unvisited bit). Live, with a score-last read.
```

## Prediction

- P1. Re-ranking cd82's 322 real ACTION6 decisions by novelty (fewest
  real clicks on that cell so far), holding the recorded frames fixed:
  the swatch strip is the top-ranked candidate on far more than 1.2% of
  those decisions.
- P2. The strip is not disadvantaged by novelty ranking for a structural
  reason (too few cells, always background-classified, never legal) —
  if it is, that is a different, more specific finding than "salience
  crowds it out."
- P3. (weaker) The same reframing, applied to seed 4's movement
  decisions, shows position (17,32) would have been reached earlier
  under a sightings-based action score than it was under the
  visited-once frontier bit.

## Falsifier

- The strip ranks low even under pure novelty (e.g., it is background-
  classified, or its cells are absorbed into a larger region so its
  distinct coordinates rarely appear as separate candidates): the
  bottleneck is perceptual, not a targeting-policy choice, and Stage 2
  would not help.
- Novelty-reranking picks the strip on a similar fraction of decisions
  as the real policy already does: no opportunity here, contradicting
  the reading of the 4/322 number as a targeting bias.

## Experiment

Stage 1 (this pass): `scripts/h011_click_novelty.py` replays
`recordings/latent/seed*/cd82.jsonl`, reconstructing real per-cell click
counts as they stood at each of the 322 recorded ACTION6 decisions, and
asks whether a pure novelty rule would have picked a strip cell there.
No live agent, no game engine, no new data.

## Metrics

Fraction of the 322 real decisions where novelty ranks a strip cell
first (or within the top-K); the strip's own novelty rank distribution;
same question for other under-visited non-background regions, as a
sanity check that this isn't strip-specific overfitting.

## Status log

- 2026-09-15 opened.
- 2026-09-15 **Stage 1 run, corrected once before trusting it.**
  `scripts/h011_click_novelty.py` replays the 322 real ACTION6 decisions
  on cd82 across ten seeds' recorded frames. First metric tried ("is the
  strip ever tied for fewest real clicks") read 322/322 (100%) —
  immediately recognised as near-vacuous: with a median 833 non-
  background cells and only 322 total clicks, almost the whole board
  stays tied at zero clicks throughout, so nearly any rarely-visited
  region would pass that test. Replaced before reporting anything, with
  the one metric that actually says something: the EXPECTED number of
  strip clicks a uniform-random draw from the tied set would produce,
  weighted by that set's size at each decision.

  **Result.** Real policy: 5 of 322 clicks (1.6%) land in the strip's
  bbox. Under uniform draw from whatever is tied for fewest real clicks
  so far: expected **160.1** strip clicks over the same 322 decisions —
  **32x** the real rate. The strip's own median share of the tied set is
  0.496 — it is a solid, densely non-background bar, so it makes up
  roughly half of "still fresh" candidates on a typical decision, far
  more than its ~10% share of the board's area, yet a policy that always
  exhausts narrower salience tiers first (interest, recently-active,
  near-action-zone) before ever reaching the broad "any non-background
  cell" tier reaches it 32x less than a naive novelty tie-break would.

  **Inference (P1 met, decisively; P2 addressed).** The strip is not
  disadvantaged by any structural or perceptual property — it is
  visible as a normal non-background region on every single decision
  (0 of 322 absent) and would win roughly half of a fair coin-flip
  among still-fresh cells. The entire gap is the tier *ordering*:
  `ClickTargeting.pick()`'s narrower, salience-defined tiers almost
  never run dry, so the broad tier where novelty would actually compete
  fairly is close to unreachable in practice. Confirms the claim as
  precisely as this stage can: a novelty-aware re-ranking, not a new
  perceptual signal, is what closes this gap. Stage 2 (blending novelty
  into `pick()`'s ranking, live) is the natural next step, and is a
  change to `agent/attention.py`'s target-selection function — a
  decision-weighting change over existing evidence, not new
  representation and not the navigation router.

## Stage 2: live implementation and weight sweep

**Built** (`agent/attention.py` `ClickTargeting.pick()`; `agent/
constants.py` `CLICK_NOVELTY_WEIGHT`, per user direction to blend
novelty with salience as a weighted score rather than a hard override
or replacement). Every live (non-habituated) candidate across every
tier — not just the first non-empty one — now gets
`score = salience(cell) + CLICK_NOVELTY_WEIGHT * novelty(cell)`, with
`salience(cell) = 1 / (1 + its best tier's index)` and
`novelty(cell) = 1 / (1 + times clicked so far)`; the pick is a weighted
random draw over all of them. Habituation (a cell clicked before with
zero effect) is excluded before scoring, unchanged. The `acts_locally`
branch that drops the "recent AND non-background" tier when clicking
acts remotely is unchanged in structure. 8 new unit tests
(`tests/test_attention.py`), 286 total pass.

**Live weight sweep** (`scripts/h011_weight_sweep.py`, cd82, seeds 1–5,
400 steps, weights 0/0.5/1/2/4):

| weight | strip clicks | strip % | hottest 8×8 region % |
|---|---|---|---|
| 0.0 | 57/117 | 48.7% | 13.7% |
| 0.5 | 56/125 | 44.8% | 13.6% |
| 1.0 | 64/122 | 52.5% | 18.0% |
| 2.0 | 55/130 | 42.3% | 15.4% |
| 4.0 | 59/127 | 46.5% | 15.0% |

**A larger and more honest finding than expected.** Strip clicks moved
from the old 1.6% to 42–52% at *every* weight tested, including 0.0 —
pure salience, no novelty term at all. The fix is almost entirely
structural, not from novelty: replacing "the top non-empty tier wins
outright" with "every candidate gets summed weight, drawn
proportionally" means a tier with hundreds of cells (tier 3, "any
non-background") now carries real total probability mass even at a low
per-cell score, purely because there are so many of them — the strip
being roughly half the board's non-background area (Stage 1) means it
now wins close to half the time regardless of the specific novelty
weight. `CLICK_NOVELTY_WEIGHT`'s own effect, in isolation, is close to
flat over the tested range.

**The real trade-off, measured rather than assumed.** Clicks in the
single most-active 8×8 region fell from ~20% (the original, separately-
measured 63/322 concentration) to 14–18% here. Some of the concentration
that made "interest always wins outright" the right rule in the first
place is traded away by ending the hard cutoff — a modest, not
catastrophic, dilution, but a real one, and this project's own history
(`docs/history.md` 2026-09-13, "more routing made the score worse") is
reason enough not to wave it away.

**Weight chosen: 1.0** — the natural, least-arbitrary value (equal
footing between one salience tier-step and full novelty) given that
sensitivity to it is nearly flat on this data, not because it
measurably beat the alternatives. `constants.py` documents this
precisely, including the flat-sensitivity finding, so a future reader
does not mistake the choice for a tuned optimum.

**Not done:** a broader multi-game regression check (this touches every
game with a click action, not only cd82) and any score-level read —
consistent with "score is read last," and the concentration trade-off
above is a specific, named reason a live sweep across click-heavy games
should happen before this is trusted beyond cd82.
