# Plan

## Governing principle

> **No semantic slots without evidence.**
>
> Every perceptual or semantic interpretation must be produced by a
> falsifiable test and may return `None`. General structure may constrain
> *how hypotheses are represented and tested*, but must not constrain
> *which entities, goals, roles, or game types exist*.

Adopted 2026-09-13 after a design exchange that proposed a fixed
`WorldState` schema (`agent`/`target`/`obstacle`/`resource`/`hazard`) and
a fixed pixel taxonomy, then retracted both. The distinction that
survived: a **semantic** ontology encodes what games *are* and quietly
answers questions the agent hasn't earned; a **relational** one
(entity/attribute/relation/event/transition/hypothesis) only supplies
vocabulary for describing what *happens*. The first pigeonholes, the
second doesn't.

This is not a new direction — it is the pattern every surviving component
already follows. `_detect_translation` doesn't assert games contain moving
things, it asks whether *this* change is a translation and returns `None`
otherwise. `stamina_colour` doesn't assert games have resource bars, it
tests for a sawtooth. `acts_locally` stays `None` until evidence exists.
**`None` is a first-class outcome**, and that is the defence against
building an agent that is excellent at the games we happened to look at.

Corollary for review: game *type* is an output, never an architectural
input. No `if maze: use_bfs()`. BFS is what the router does *because* a
move map and obstacle map were discovered — not because anything
recognised a maze.

---

Living checklist — check items off as they're done, add new ones as they
come up. Don't delete completed items (they're the record of what's
built); don't rewrite history here beyond fixing errors — narrative of
*why* decisions were made belongs in `history.md`. See `glossary.md` for
the naming convention used for feature names below.

## Environment & repo

- [x] Python 3.12 venv, framework clone, Kaggle token, `make verify-local`
      passing.
- [x] Repo pushed to `origin` (`github.com/nvaidyan1/arc-agi-3`), original
      starter kept as `upstream`.
- [x] Kaggle username set in `notebooks/kernel-metadata.json`.

## Agent strategy (`agent/my_agent.py`)

**Where the score stands (2026-09-13, after measuring the noise floor).**
30 sweeps at one unchanged commit: mean 0.0307, **median 0.0131**, sd
0.0490, range 0.0–0.194, 3/30 zero. Severely right-skewed — the top sweep
is 6.3x the mean. **Every configuration ever recorded in `history.md` is
statistically consistent with this one**, including the "pre-router
baseline" (0.0630 at n=5, p=0.08 — a 1-in-12 fluctuation picked post-hoc
as the max of ~6 configs). Nothing in this project has ever been measured,
in either direction. A sweep costs **29 seconds**; the measurement tax we
deferred work around was never real.

**Standard from here: n>=30 per arm, compare medians.** At n=30 a rank
test has 80% power to detect a 3x change and 51% for 2x; at n=3–14 (what
every past comparison used) it cannot see a 3x change reliably.
Scoring, **re-read from `arc_agi/scorecard.py` 2026-09-13** and partly
refuting what this section said before. Per level:
`((baseline_actions / actions_taken) ** 2) * 100` on completion, 0.0
otherwise, capped at 115. But an environment's score is the
**level-index-weighted average over every level in the game**,
`sum(score_i * i) / sum(i)`, the denominator including levels never
reached. vc33 and ls20 have 7 levels, so level 1 is worth **1/28** of the
environment.

Two consequences, both measured against the real scorer (see
`history.md`, same date):

  * **Depth dominates speed.** On vc33, reaching level 2 *at our current
    185-action pace* scores 0.0727 — as much as becoming 4x faster at
    level 1 (0.0827). Level 3 at that pace (0.6788) beats an 8x speedup
    (0.3308) twofold. "Closing the 10–50x speed gap is the whole
    remaining problem" was **wrong**: it reads one term of a two-term
    objective, and the other term has never been measured because the
    agent has cleared level 2 approximately never.
  * **`actions_taken` is a cumulative delta**, not a per-attempt count
    (`_calculate_score`, ~line 476: `actions_at_level - prev_actions`),
    and the agent's counter never resets. Actions spent failing *within*
    a level are charged to that level, so truncate-and-retry buys
    nothing. Refuted before being built.

Human level-1 baselines: vc33 7 actions, ls20 22, sp80 39, dc22 59; full
per-level vectors now land in every sweep summary. We take ~400.

- [x] **Affordance filtering** — only try actions `latest_frame.available_actions`
      reports as legal.
- [x] **Contingency detection** — epsilon-greedy bandit over "does this
      action change the frame," Laplace-smoothed.
- [x] **Salience map + habituation** — target recently-changed cells for
      the coordinate-click action, avoid grid regions that absorb clicks
      with zero effect.
- [x] **Layered reward signal** — frame-change (dense) kept as-is and
      *added to*, not replaced by, level-ups (sparse, `levels_completed`,
      the thing actually scored, weighted 20x). Level-up credit
      deliberately persists across RESETs while frame-change stats stay
      per-attempt: level-ups are too rare to forget, and which action
      makes progress is a property of the game, not of one attempt.
      Verified with synthetic frames (real play has never produced a
      level-up, so the path would otherwise be untested): credit lands on
      the right action, survives RESET, and shifts selection to ~74%
      (the other ~26% being the epsilon floor).
- [x] **Contingency awareness, first layer** — per-cell click memory
      (prefer unclicked, skip cells that did nothing) plus a learned
      `acts_locally` signature: does clicking change the cell you touched,
      or something elsewhere? Measured across three games: ft09 local
      (38 cells per click), vc33/tn36 remote (1-2 cells). The signature now
      *changes behavior* — when clicks act at a distance, targeting
      recently-changed cells is a category error (they're the effect, not
      the cause), so the policy covers new ground instead. Click repeat
      waste fell from ~50% to 1-3%. No score change.

### Representation roadmap

The layers the user asked for — pixel > object > thing I control > thing
I affect — defined by **contingency, not appearance**, so nothing assumes
2D space, avatars, or navigability. See `history.md` (2026-09-13,
contingency awareness) for the full framing and `glossary.md` for terms.

- [x] **pixel** — raw grid
- [x] **change** — `_diff_cells`
- [x] **click contingency** — `acts_locally`, per-cell effect memory
- [x] **object** — `_detect_translation` tests whether a frame change is
      one colored shape displaced by a single offset. Not
      connected-components, no colored-blob assumption: it *tests* for a
      translation and reports nothing when there isn't one. Fires on
      **14 of 25 games** — strong evidence that the 2D object reading is
      real for much of this set, and it was derived rather than imposed.
      Silent on vc33/ft09/tn36, which is the graceful-failure property
      working rather than a gap.
- [x] **thing I control** — `learned_moves`: per action, the movement
      offset it reliably causes (needs 3+ sightings and a 60% majority).
      On ls20 it recovers a complete, noise-free directional map
      (ACTION1-4 → up/down/left/right at a 5px stride, 122/122
      consistent). Correctly *refuses* to learn genuinely ambiguous
      actions (m0r0 ACTION1: 15x one way, 13x the other).
- [x] **settled-frame reading** — `frame` is animation sub-frames within
      one action, not spatial layers; all signals now read `frame[-1]`
      (the settled state) rather than `frame[0]` (mid-animation).
- [x] **recolour + cardinality change types** (`_classify_change`) —
      translation covers only 31% of real transitions; recolour-in-place
      is 53% and cardinality-change 16%. Both now have a lens.
      Discriminator is the background ("the canvas"): a change *touching*
      it creates or destroys content (cardinality), a change *between two
      non-background colours* relabels something already there
      (recolour) — the same rule that fixed the vanish false-positive.
      **Recording-only: deliberately not wired into action selection.**
      The router taught us that adding a signal and changing decision
      logic in one pass makes a regression impossible to attribute.
      - Background must be the level's *initial* mode, not a per-frame
        argmax: measured across 25 games, 24 are stable but **dc22
        disagrees on 37.4% of steps** (its fill mechanic eventually
        outvotes the canvas). Fixed; changed dc22's classification
        exactly as predicted (recolour 38%→19%, cardinality 23%→0%).
      - Our taxonomy is deliberately **narrower** than the manual study's.
        ft09 toggles two foreground colours (9→8 468 cells, 8→9 432, over
        a stable background of 5); the study called that cardinality
        because per-colour totals move, we call it recolour because
        nothing was created or destroyed.
      - Census percentages are **not comparable** to the manual 31/53/16:
        ours count "category present in this step" (non-exclusive, sums
        past 100%), the study assigned one dominant category per
        transition. Also noisy run-to-run since trajectories differ.
- [ ] **budget-awareness from cardinality — NOT confirmed.** The stated
      hope was that cardinality would reveal step/lives counters. It
      finds **drains**, not **budgets**: a drain falls monotonically and
      never returns (dc22 fill-progress, cd82 consumption), a budget
      *refills* each attempt. Only 2 of 25 games (lp85, cd82) showed a
      large drain the meter missed, and cd82's is the known consumption
      mechanic. `stamina_colour` is right to reject them — the refill test
      is the whole distinction. Superseded unless a refilling counter
      turns up that the sawtooth misses.
- [ ] **translation as a *component*** — `_detect_translation` still
      requires the whole diff to be one displacement (measured cost: 4%).
      `_expected_move_occurred` already does the component test for
      blocked-move detection; generalising it would let the three change
      types coexist. Low priority given the measured 4%.
- [x] **what changes when a move is blocked** — answered: both, by game.
      ls20/dc22 render a resource meter (fixed row, fixed transition,
      y-spread 0.0); wa30 shows interactions instead. Led to the meter
      detector below.
- [x] **stamina awareness** (renamed from "budget", see below) —
      `stamina_colour` / `stamina_fraction` detect a
      rendered budget via its sawtooth (declines, then refills to a
      recurring max). Correctly rejects dc22's fill-progress colour, which
      declines but never refills. Fires on ~9 of 25 games. ls20: 84 units
      at 2/action = 42 actions per attempt.
- [x] **action cap raised 80 -> 400** — self-imposed, no external cap
      exists. Reproducibly yields completions (2 of 2 replicates at 400)
      where 80 gave noise. Does NOT raise score: completions at ~400
      actions score ~0 against human baselines of 7-59.
- [x] **sub-goal (vanish) signal** — a whole object disappearing, the
      only visible proxy for intra-level progress. Online discriminator:
      drops larger than `_controlled_size` cannot be self-occlusion.
      Correctly ignores ka59's 244 one-cell churn drops. Weight 8. No
      score change.
- [x] **FIX: vanish false-positive from same-step recolouring.** Was
      mis-measured as "0-1.5% of steps" (only held on the games it was
      sampled from); really up to 78.6% (ft09). Missing discriminator: a
      drop absorbed by *another non-background colour* is a recolour, not
      a deletion — only a drop the *background* absorbs is real.
      `_track_meter` now requires `pending_vanish = min(total_drop,
      background_gain)`. Verified directly against the fixed production
      code (not the probe's independent re-derivation): **ft09 78.6% ->
      0.0%, s5i5 46.7% -> 0.5%**, both now inside the originally-claimed
      range. **cd82 44.5% -> 21.9%** — improved but still elevated;
      plausibly a game whose core mechanic *is* frequent
      recolour-to-background (a consumption/fill mechanic, not a
      sub-goal), the same shape of false positive already known for the
      budget-meter detector (dc22's fill-progress colour). Not chased
      further now — flagged, one-game residual, not blocking.
- [x] **planning toward a target — router built** (`_plan_route`,
      `_anchor`, `_route_plan`/`_route_target`/`_route_expected_position`
      in `agent/my_agent.py`). Bounded BFS over displacement space,
      `learned_moves` as edges, `_blocked_moves` as removed edges, target
      = best `_interest` cell; falls back to the closest reachable node
      (Chebyshev) if the exact target isn't on the move map's stride
      lattice. Validated offline first (6 synthetic unit tests) before
      live games. Online self-correction: an in-progress plan is dropped
      if the next step becomes illegal or `_displacement` doesn't match
      what the plan expected (a newly-discovered obstacle).
      **Caught and fixed a real regression before it shipped**: the
      router's first placement (below frontier, above the reward-weighted
      fallback) preempted the *only* channel that has ever produced a
      real completion (`LEVEL_UP_WEIGHT`/`VANISH_WEIGHT`). Measured: two
      full 25-game sweeps scored **0.0 on every single game**, including
      sp80 (4/5 baseline before the router existed). Fixed by gating
      router use on `not (self._action_level_ups or
      self._action_vanishes)` — route only while nothing has proven
      itself yet; an in-progress route is abandoned the moment something
      does. Re-verified: sp80 alone recovered to 9/15 (60%) post-fix from
      a flat 0/25 immediately before it.
      **Open**: net score effect vs. no router is not yet established —
      3 post-fix sweeps (0.0110, 0.0, 0.0072, mean ~0.0061) sit below the
      5-sweep pre-router baseline (mean ~0.063), but that baseline itself
      spans 0.0006-0.1496 (250x), so 3 vs 5 samples cannot separate a real
      effect from this environment's known variance. Needs more
      replicates, not a blocking concern for the router's correctness.
- [ ] **use of the budget signal** — deliberately NOT wired to behaviour:
      measured cost per action is flat (ls20 1.94-2.00 for every action),
      so cost-aware selection gains nothing. Needs a goal to be useful —
      knowing time is short only helps if there is something to rush
      toward.
- [ ] **THE OPEN PROBLEM: level 2.** Across every sweep on record, exactly
      **one** game-run has reached level 2 (tu93, once). Budget is not the
      cause: a ladder at 400/800/1600 raises games clearing level 1
      cleanly (1.63 → 2.33 → 3.83 per sweep) and leaves level 2 at zero.
      Two distinct failure modes, measured per-attempt (`history.md`,
      same date):
      - **sp80** — 33 attempts at level 2, all fatal, median **45 actions
        per attempt against a human baseline of 58**. The per-attempt
        resource is below what the level costs a human, so no policy
        short of near-human efficiency can clear it.
      - **cd82** — **100 actions per attempt against a human baseline of
        8**, and still 0/15. Twelve times the needed budget. Budget
        cannot explain this one.

      **cd82 level 2 is therefore the clean testbed for goal
      identification**: ample budget, short human solution, reproducible
      zero. A real goal signal should move it, and a null there cannot be
      blamed on the action cap. Level 1 has been winnable by stumbling
      (one sp80 run cleared it in 9 actions vs a human 39); from level 2
      on there is no stumble budget. That, not reliability, is why the
      goal signal matters.
- [x] **thing I affect** — residual change after subtracting our own
      movement and the meter. Gated on having a move map, since with no
      known "self" the residual is just "anything changed" and
      double-counts frame-change. 26-57% on games with a move map, ~0%
      without. Third reward tier (weight 3) between frame-change and
      level-up. No score change.
- [x] **code organisation** — was 1,328 lines in one file, now seven
      modules mirroring the layer stack, each answering one question:

      | module | question |
      |---|---|
      | `perception.py` | what happened? |
      | `control.py` | what can I make happen? |
      | `constraints.py` | what limits what I can make happen? |
      | `attention.py` | what appears worth investigating? |
      | `navigation.py` | how do I get there with what I've learned? |
      | `my_agent.py` | given all that, what should I do next? |
      | `constants.py` | every tunable, grouped by layer |

      Names are **epistemic, not semantic** — `control`/`constraints`/
      `attention` are functional roles, not claims about what games
      contain. `objects.py`/`goals.py`/`enemies.py` would smuggle in an
      ontology; these don't. Review test for anything added later: does
      the name describe an observable relationship, or an interpretation?

      Two boundaries are load-bearing and should be defended:
      - **`perception` returns evidence, never decisions.** It can say
        something happened; it cannot say what it means. No `is_goal()`.
      - **`navigation` takes a target, never picks one.** An earlier
        draft had the router reach into the interest map to choose its
        own destination, which quietly made navigation the privileged
        paradigm — routing happened because it *could*, not because the
        situation called for it. Policy lives in `my_agent.py` alone.

      Synthesis stays in `my_agent.py` until there is enough accumulated
      model-learning logic to justify extracting a hypothesis layer.
      Don't create a module because you can imagine one; create it when
      the code shows there is one.

      **Shipping is now proven rather than hoped.** `build_notebook.py`
      emits one `%%writefile` cell per module and copies them all into
      the framework's `templates/`; a `sys.path` bootstrap in
      `my_agent.py` makes sibling imports resolve both locally (loaded
      standalone by `play_local.py`) and on Kaggle (imported as
      `agents.templates.my_agent`) — neither plain absolute nor relative
      imports work in both. `make verify-packaging` reconstructs the
      rerun layout from the *notebook's own bytes* and imports MyAgent
      through it in a clean interpreter, so a packaging mistake fails
      here instead of after spending one of 5 daily submissions. Wired
      into `make submit` as a prerequisite.

      An attached-Kaggle-dataset layout was considered and rejected: it
      needs two artifacts kept in sync (silent stale-code runs when they
      drift) and can't be verified locally at all, since `/kaggle/input`
      paths don't exist here.
- [x] **tests** — 47 unit tests across perception, navigation, control
      and constraints (`make test`, no game engine needed). They assert
      the *refusals* as carefully as the successes: that translation
      detection returns None on a recolour, that the move map refuses
      m0r0's 15/13 coin-flip action, that the meter rejects dc22's
      monotonic fill. A layer that concludes confidently from ambiguous
      evidence is worse than one that stays silent.
      Caught a latent crash during the refactor: `learned_moves` is
      recomputed every step, so an action can drop out of it when new
      observations break its majority — a queued route still referencing
      it then raised `KeyError` (seen live on sc25 and wa30). Pre-existing;
      the restructure only made it surface.
- [x] **environment / blocked-move detection** — a learned move that
      fails = something resists us, keyed by (position, action). Built
      *before* robustness after measuring the strictness flaw at only 4%.
      Validated by determinism: "mixed" outcomes per (position, action)
      are ~0, and each action is blocked at a minority of positions —
      obstacle signature, not model error. Cuts wasted moves (ls20
      63%→21%) and raises coverage (+27-56% on 4 of 5 games). No score
      change.
- [x] **thing I affect** *(duplicate — superseded by the residual-cells
      item above, which is this concept built)*. Kept as the record of
      where the idea started: `acts_locally`, and vc33 occasionally
      learning that a click displaces something by (-4,0).
- [ ] **environment** — changes independent of action, or never changes.
      Not built; nothing so far has needed a true world-vs-self split
      beyond what blocked-move detection already gives.
- [x] **region of interest / attention (map + click wiring)** —
      Every layer above answers *what do I control* and *what resists me*;
      none answers *where should I go* or *what should I make*. Two uses,
      not one: a **destination** in the navigational family, and a
      **specification** in the constructive/matching family (mirror the
      heart on the left onto the right — the left region is not a place
      to travel to, and the obstacle map is irrelevant there).
      Substrate already exists and is thrown away: `_residual_cells`
      computes "changed, explained by neither self nor the budget meter"
      every step, but only its **count** survives (as a reward weight) —
      the **positions** are discarded. `_interaction_sites` keys on *our
      own displacement*, not on where the change landed.
      Screened 2026-09-13 (25 games x 400 actions, see `history.md`):
      - sites **cluster** — Clark-Evans R 0.52 navigational / 0.39
        constructive (1.0 = random); ls20 29 cells, sp80 28, sk48 8 carry
        half the mass out of 4096. Random on re86/cn04/bp35 only.
      - the layer is **structurally off** where it is needed most:
        `observed_offset is not None` requires knowing our own movement,
        so ft09/sb26/cd82/tn36 produce residual on **0.0%** of steps.
        Resolution: that gate is right for the *reward* term (without it
        residual double-counts frame-change) and wrong for a *map*, which
        double-counts nothing. Keep the gate on one, drop it on the other.
      - **template/workspace separation is real**: static non-background
        cells lying outside the ever-changed bounding box average 52% in
        the constructive family (su15/sb26/cd82 = 100%) and include
        **sp80 at 93%**. Caveat: "static" = unchanged *during our
        episode*, so it partly reflects our own coverage. Not yet acted
        on — no consumer distinguishes template from workspace.

      **Built** (`_interest`, `_bump_interest`, `_decay_interest`,
      `_top_interest_cells`, `INTEREST_*`): bumped at residual cells
      (ungated — see fix above), extra at vanish sites, most at level-up
      sites; decays 0.98/step; wired into `_pick_coordinate` as the top
      tier. Verified end-to-end on ft09: evidence by step 16, dominating
      selection by step ~390. Only reaches ACTION6 (the constructive
      family) — movement games get the map but nothing yet consumes it,
      that is the router item below. One 25-game smoke sweep post-change:
      0.0316, inside the existing 0.0006-0.1496 range (not a replication).

- [x] **Reliable level-ups** — was: two spontaneous level-ups (vc33, sp80),
      each non-reproducible on retest (0/6 and 0/8). Resolved by the budget
      raise, though only on a minority of games: 5 of 5 sweeps at 400 now
      score non-zero and sp80 completes in 4 of 5 runs, while most of the
      25 still complete nothing. Levels are now reliably *reachable*; the
      open problem moved from hit-rate to **speed**.

## Naming: three things were all called "budget"

Renamed 2026-09-13 after the word turned out to be carrying three
unrelated meanings, which made the docs actively misleading:

| thing | name | whose rule |
|---|---|---|
| total moves we allow per game, across all levels | `MAX_ACTIONS` | **ours** — self-imposed |
| the per-attempt resource that kills you at zero | `stamina_*` | **the game's** |
| human moves for a level, used only for scoring | `baseline_actions` | **the yardstick** |

`stamina` rather than `lives`: what the detector measures is a quantity
that drains during an attempt and refills when it restarts. In ls20 and
dc22 that is literally a lives counter; in vc33 it is a step budget, and
"lives" would assert discrete retries the evidence doesn't support —
exactly the kind of semantic slot the governing principle forbids.
`MAX_ACTIONS` keeps its name because the framework's `Agent.main()` loop
reads that exact attribute.

## Tooling

- [x] `RENDER=terminal` / `RENDER=human` / `RENDER=terminal-fast` in
      `scripts/play_local.py` / `Makefile`.
- [x] Per-step JSON logging (`recordings/<run-timestamp>/<game_id>.jsonl`),
      on by default in `play_local.py`. Bulky and gitignored — a debugging
      convenience, not the record.
- [x] **Durable sweep summaries** (`scripts/sweep_summary.py`,
      `results/sweeps/<run-id>.json`, committed). Carries the scorer's
      per-level actions/scores/baselines, the action index of every
      completion, and a git fingerprint, so a score is attributable to the
      code that produced it. Built because ~50 sweeps had been run and
      **one** survived on disk — every comparison in the tables above was
      against numbers that no longer exist. Level tracking is independent
      of `--log` on purpose: the completion index is the result, not a
      debugging aid. `make backfill-summaries` recovered the four
      surviving runs (marked `backfilled`, scorer half unrecoverable).
      `make clean` spares `results/`.
- [ ] **Variance floor still unmeasured.** The summaries make it cheap to
      compute for the first time — run N sweeps at one unchanged commit
      and read the spread. Until that number exists, no configuration
      comparison in this document is defensible.

## Docs

- [x] Game mechanics reference folded into `README.md`.
- [x] `history.md` established as an append-only, honest log of AI
      involvement (Paper Prize / Solution Writeup transparency angle).
- [x] `glossary.md` established — name features after existing
      cognitive-science/ML terms rather than ad-hoc descriptions.

## Submissions

- [ ] First `make submit` (0 of 5 daily submissions used so far). Always
      user-run, never autonomous.

---

## On hold (and why)

A brainstormed 4-layer architecture (Perception/Object-Extractor →
Epistemic World Model → Planner/Search Arbiter → Verification Harness)
was reviewed by three independent passes (technical feasibility,
ROI/incrementalism, generalization-fit — see `history.md`, 2026-09-13)
before choosing what to build next. Outcome, nothing rejected forever,
just sequenced behind having an actual object/goal signal:

- [ ] **Connected-component object extraction** (`scipy.ndimage.label`,
      segmenting same-colored regions into objects) — RISKY for
      generalization: assumes "object" = "contiguous same-colored blob,"
      which a hidden game could simply not use (texture, single pixels,
      non-contiguous motifs), corrupting everything built on top. Also:
      `scipy` isn't installed.
- [ ] **Single "Controllable_Agent" tracker** — RISKY: assumes exactly
      one persistent, controllable avatar exists, which ARC-AGI-3's
      abstract action set is deliberately designed to allow games to not
      have.
- [ ] **Convex-hull frontier probing** — RISKY: assumes a 2D navigable
      map; many ARC-style puzzles are symbolic/transformational with no
      spatial "unreachable area" concept.
- [ ] **Local transition simulator + A\* search** — was deferred as
      premature: "nothing to simulate or search over without object
      identity or a goal signal first." **That condition is now met** —
      object identity (`_detect_translation`), a move map
      (`learned_moves`), an obstacle map (`_blocked_moves`) and a
      displacement-space cognitive map (`_visited_displacements`) all
      exist. The remaining missing piece is the goal signal, which is
      what the *region of interest* item is for. Unblocked, not built.
- [ ] **Local coding-LLM fallback for transition-rule synthesis**
      (Qwen-Coder/Gemma) — CONDITIONAL, not rejected: fine only as a
      per-episode hypothesis, verified/discarded within that game, never
      cached or reused across games (that crosses into per-game
      memorization, which the competition's stated eval philosophy is
      explicitly designed against). No local LLM infra exists yet either
      way.
- Factual corrections surfaced during review: `GameAction.UNDO` doesn't
  exist (8 real members: `RESET`, `ACTION1`-`7`); `scipy` isn't installed
  or transitively available.

## Tried and reverted

- **Go-Explore trajectory replay** (Ecoffet et al., 2021) — built,
  tested, reverted the same session. The premise was "remember the
  best attempt's action sequence, replay it to return to that frontier,
  then explore onward." Two facts from the engine source killed it:
  1. On `GAME_OVER` the engine calls `level_reset()`, not `full_reset()`
     — which preserves `_score` (i.e. `levels_completed`) and keeps you
     on the current level. **Level progress is already checkpointed for
     free**, so there is no frontier to return to.
  2. Death is *resource exhaustion*, not a fatal move (vc33: step budget
     `current_steps` hits zero; ls20: a lives counter decrements to
     zero). So a saved trajectory is by definition a *losing* run, and
     replaying it spends the fresh attempt's entire finite budget to
     arrive back at a losing position.
  Together that makes replay **net-harmful**, not merely useless.
  Empirically: attempts plateaued at a fixed per-game length (ls20 130,
  dc22 128, m0r0 151, sc25 57, vc33 50) across up to 15 resets, with
  zero levels completed — consistent with a fixed budget, not with
  skill-limited deaths.
  Worth keeping from the exercise: the discovery that `levels_completed`
  is the only real progress signal, and that per-attempt budget is the
  binding constraint. That reframes the next step (see checklist).

## Shelved ideas

- **Cognition-mapped variable namespace** (e.g. `memory.last_action`
  instead of `self._last_action`) — raised, deliberately not adopted: it
  would trade plain, readable Python for a metaphor that isn't load-
  bearing. Could revisit if a genuine need for it shows up later.
