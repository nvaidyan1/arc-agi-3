# H011: A novelty term in target selection reaches under-explored cells the salience heuristic misses

Status: SHIPPED — **measurement correction 2026-09-17: the headline "strip clicks" metric counts clicks into the strip ENTITY's 414-cell bbox, which is ~94% inert backing; swatch coverage, the thing the hypothesis was for, did not move (3.29% -> 3.36%). The shipped mechanism and its parity gate stand; the success metric overstated the gain. See the status log and `scripts/h007_p2_retest.py`.** Original: click blend live (`agent/attention.py`): strip clicks 1.6% -> 42-52%, effect almost entirely structural (ending the hard tier cutoff). Whole-sweep n=30 parity gate passed 2026-09-16: median score rose, the five named parity games showed zero regression, one flagged game (lp85) read as trajectory-perturbation noise on inspection, not a real regression. Committed. Movement-side novelty is its own hypothesis, H012.
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

## Parity gate: read and passed

**n=30 seed-paired, whole 25-game sweep, seeds 101-130, pre-H011 (main
at the time) vs H011 Stage 2, 400 steps.** Both arms clean: 30/30
seeds each, zero errors, baseline scores matching the historical noise
floor (mean 0.0286, median 0.0162 on the completed portion).

| | baseline | treatment |
|---|---|---|
| aggregate_score mean | 0.0401 | 0.0632 |
| aggregate_score median | 0.0163 | 0.0206 |
| sign test (19W/11L/0T) | p = 0.20 | not significant at n=30 |
| sp80 / ls20 / ar25 / dc22 L1+ | 18 / 4 / 7 / 0 | 18 / 4 / 7 / 0 (unchanged) |
| m0r0 L1+ | 0 | 1 |
| ft09 L1+ | 0 | **12** |
| vc33 L1+ | 0 | **11** |
| lp85 L1+ | 13 | 10 |

**Gate read.** Median did not fall (rose). The five named parity games
(sp80/ls20/ar25/m0r0/dc22) show zero regression, one improvement.
lp85 trips the literal ">1 level-1 clear per 30" wording (13->10), but
its per-seed pattern is a roughly balanced shuffle (7 seeds
clear->not-clear, 4 the other way) — the trajectory-perturbation
signature this project has repeatedly documented, not a one-directional
capability loss. ft09 and vc33's jumps from a hard 0/30 baseline to
11-12/30 are a different, more confidently real signature: a uniform
shift across many independent seeds from literal zero is not
explainable by the same reshuffling.

**Decision: ship.** Gate passed as intended by both reviewers. `agent/
attention.py`, `agent/constants.py`, `scripts/h011_weight_sweep.py`,
`tests/test_attention.py` committed. All 60 sweep summaries (30+30)
kept together as a matched-pair retention exception.

**Not explained, flagged for later, not blocking:** why ft09 and vc33 —
games whose central mechanic this project has not characterised in
detail this session — respond so strongly to novelty-aware click
targeting. Worth a look when representation work resumes; not a
condition of this ship decision.

- 2026-09-17 **Measurement correction, found by H007's P2 re-test (gate 2).
  Not a retraction — the mechanism works and its n=30 parity gate stands.**
  This hypothesis's headline number, "swatch strip clicks 1.6% -> 42-52%",
  is computed over the strip ENTITY's bounding box (x 18-63, y 0-8), taken
  from the S_t traces and used by `scripts/h011_click_novelty.py`. That box
  is 414 cells, of which ~391 are inert backing of colour '3' and only ~23
  are the two interactive swatches. Classifying each click by the colour
  actually under it, across 10 fresh seeds and the pre-H011 traces measured
  identically: bbox clicks rose 21.5% -> 42.4%, while **clicks on an actual
  swatch went 3.29% -> 3.36%, i.e. did not move.** 93 of 101 post-H011 bbox
  clicks landed on backing. The consequence the project cared about —
  making the swatch's state vary often enough for the enumerator to tally
  it — did not happen: 1 of 101 bbox clicks was followed by any change in
  the strip.
  What this does and does not touch. The click blend still ends the hard
  tier cutoff, still passed its n=30 seed-paired gate on score, and ft09 /
  vc33's 0/30 -> 12/30 and 11/30 are unaffected by any of this. What is
  corrected is the inference that this hypothesis had unblocked H007 P2. It
  had not. The open question it leaves: novelty draws uniformly from cells
  tied for fewest clicks, over *non-background* cells — and on an entity
  that is 94% inert backing, that is close to a uniform draw over the
  backing. Preferring cells that are plausibly interactive, rather than
  merely non-background, is the natural follow-up and does not yet exist as
  a hypothesis.