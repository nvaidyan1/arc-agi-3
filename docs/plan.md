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

Two further rules, added 2026-09-14 after an external review
(`reviewer_c_09_14_2026.MD`) named what the project had already been living
by for a day:

> **No representation without a consumer.** A layer nothing reads cannot
> move the score, and three recording-only layers proved it. Build the
> consumer, or the layer waits.
>
> **No hypothesis without a falsifier.** Every bet the agent makes names
> the observation that would kill it, and the verifier reports *which*
> way it died — wrong, precondition unmet, inconclusive — not a boolean.

And one softening of the first rule, from the same review: **priors may
generate hypotheses, never conclusions.** "Similar things may behave
alike" is allowed to propose; only evidence may promote.

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

## Built: the entity and belief layers

| module | question |
|---|---|
| `perception.connected_regions` | what things are on the board? |
| `entities.RegionTracker` | which of them is the same thing as last frame? |
| `belief.WorldBelief` | what is each of them *to me*? |

Roles are **relational, not semantic** — CONTROL / AFFECT / CONTEXT /
ENVIRONMENT / UNASSIGNED each describe how an entity's behaviour correlates
with our own actions, never what it is in a game. Grouping and following are
representation, which the governing principle permits; the roles stay
falsifiable and UNASSIGNED is a real answer.

- [x] **entity-scoped stamina** — meter detection 16/25 -> **25/25**, zero
      losses; cd82's bar contamination of "thing I affect" 100% -> 22%.
      Score effect measured at n=30 per arm: **p = 0.82, none**. Expected:
      nothing acts on stamina yet.
- [x] **belief layer** — a role per entity, read from the contrast
      *between* actions: `responsiveness` (baseline rate across all
      actions) against `selectivity` (how far one action stands out).
      That subtraction is the whole mechanism — cd82's stamina bar changes
      on 52-66% of steps *whatever* is pressed, and before it that common
      signal sat in every action's profile and drowned the one effect that
      was action-specific. Recording-only.
- [x] **how, not just that.** A role names the *kind* of effect, in a
      vocabulary defined purely by what happened to a set of cells:
      MOVED (centroid shifted), TURNED (size and centroid held, cells
      changed), GREW / SHRANK, APPEARED / VANISHED. Live:
      `wa30 #0 CONTROL — ACTION2 turned it +37%`,
      `cd82 #13 CONTEXT — shrank whatever I press (55% of steps)`.
      Note wa30's rotation is identified here by centroid-preservation
      alone, independently of `detect_rotation` — two routes agreeing.
- [x] **bordered objects are one thing.** Same-colour grouping necessarily
      splits a frame from its fill: wa30's first frame had three objects
      each a 12-cell 4x4 frame around a 4-cell 2x2 core, drawn as six
      entities. `perception.merge_enclosed` folds a region whose every
      outside neighbour belongs to one other region into it — enclosure is
      geometry, not a guess. 12 non-canvas regions -> 8. Merely *touching*
      still does not merge.
- [ ] **`RECOLOURED` is missing from the kind vocabulary.** A recolour
      presents as one entity shrinking while another grows in the same
      place, so cd82's ACTION5 — whose whole effect is turning colour 0
      into 15 across 400 cells, exclusively — reads as "no stable effect
      learned yet". Inferable the same way as the rest (two entities,
      overlapping cells, opposite size changes, same step) and not yet
      built. This is a gap in the vocabulary, not caution about bias.
- [ ] **roles still flicker.** With hysteresis and a 20-observation bar,
      cd82's readout still changes on 16% of steps and 11 of 17 entities
      gain a role, lose it and regain it. wa30 is stable (2%). The
      evidence genuinely wobbles near the threshold; the panel reports it
      faithfully rather than smoothing it.
- [ ] `sp80` assigns no CONTROL despite having two controllable objects.
- [x] **CONTROL by determinism** (2026-09-14). The rate contrast could not
      see a thing driven by several buttons at equal rates — every d-pad.
      CONTROL now also fires when >= 2 actions each do one fixed, *different*
      thing to an entity (`Belief.controllers`); motion is read from
      bounding-box extent, not size. cd82's bucket and ls20's sprite both
      read `control 100%` with a four-way map. See `history.md` 2026-09-14.

## START HERE (handoff, 2026-09-14 night)

**State.** `main` at `1eeca67` is pushed (two commits: H003+H004+H002 with
242 tests; the recap GUI 3-column redesign). `ARC_PROPOSER` and
`ARC_LLM_PROPOSER` are still OFF by default — nothing here changed the
default score. Ollama + `gemma3:4b` are installed and working locally
(`qwen3.5:4b` is unusable — a thinking model whose reasoning never
terminates in bounded time on this build; confirmed independently by the
user hanging on a plain "hi"). Nothing runs in the background.

**3a/3b done, per the previous handoff's order.** H003 (`agent/predictor.py`):
one-step forecast from the tallies already held, scored against what
happens. Finding: the world model's largest gap is state-dependent
geometry (containment/distance error concentrates under movement actions),
not another semantic condition — **position is the next primitive**, not
more vocabulary. H004 (`agent/hypothesis.py` rival/forecast/exclusive):
mechanism fires and is measurably active; net effect against E-7a was
mixed, not a clean win — not promoted, kept behind `ARC_PROPOSER`.

**H002: attached, then fixed twice, then swept at n=5.** E-H002-1 (5
games, 1 seed) found the dominant rejection was a format mismatch, not
hallucination — the model echoes the brief's own `"#5"` notation instead
of a bare int. Fixed (lenient id parsing, a worked prompt example, a
pool-priority tiebreak so valid LLM bets actually get tested instead of
losing to the enumerator's bets for pool slots, eviction accounting to
make that measurable). Seed-paired single-seed rerun: valid-schema rate
27%→39%. **E-H002-2** (5 games × 5 seeds × 200 steps, `gemma3:4b`, the
fixed code): valid-schema rate **55.9%** (146/261) — confirms the fixes
generalise across seeds, not a lucky single run. 57 calls total (2.28/run).
Of 146 valid: 1 `held`, 78 `falsified`, 19 `expired`, 11 live at cutoff.
LLM hit rate (held/(held+falsified)) 1.3% vs the enumerator's own 2.6% in
the *same* sweep — lower, but same order of magnitude on a falsification-
heavy system where most bets of either source die; not evidence the
model's hypotheses are dramatically worse. Gameplay: 3/25 runs reached
level 1+ (cd82 0/5, cn04 1/5, tu93 0/5, ka59 0/5, ar25 2/5) — **but there
is no matched non-LLM baseline at these same seeds/games/steps**, so this
cannot yet answer whether the LLM moves the score. Full numbers in
`research/hypotheses/H002_llm_hypothesis_proposer.md`.

**A second reviewer-C pass** (`docs/expert-reviews/reviewer_c_09_14_2026b.md`)
landed after E-H002-2 was scoped. Its central claim is correct and already
independently flagged before reading it: **`recap.py`'s re-run-from-seed
approach stops being a replay once a stochastic LLM is in the loop — it
is a rerun, and should not be read as ground truth for an LLM-enabled run.**
Agreed and actionable; pushed back on the proposed full event-sourcing
rewrite (`agent.export_step()`, a Tier 1-5 architecture, `recap.py` reading
a saved trace instead of re-running) as bigger than justified before
E-H002-2 has told us the LLM proposer is worth the continued investment —
the review's own recommended sequencing agrees (logging rework comes
*after* analysis, not before). Also flagged: the "paired experiment" framing
assumed a baseline that doesn't exist yet.

**Three "before the next churn" items done, same session, before the order
below was acted on.** All bounded, low-risk, cheap — done rather than
deferred once the user pushed back on sequencing them after the baseline
arm: (a) durable per-LLM-call I/O capture — `LLMProposer.trace` /
`export_trace()`, exact prompt + raw reply + accepted/rejected + trigger +
latency + model + a new `PROMPT_VERSION`, wired into `play_local.py`'s
sweep summary as `llm_stats`/`llm_trace` so it's captured automatically
in the durable committed format going forward; (b) `recap.py`'s docstring
now states the rerun-vs-replay distinction explicitly; (c) the metadata-
freeze problem resolved structurally, not by convention: route sweeps
through `play_local.py` itself (which already captures git sha/flags/
seed/config via `sweep_summary.py`) instead of ad hoc scripts. 245 tests.
Smoke-tested end to end against `gemma3:4b` on cd82 — trace fields
confirmed correct in a real committed sweep summary.

**Matched baseline arm: done.** Same 5 games, same seeds 1-5, same
200-step cap, `ARC_PROPOSER=1` without the LLM, via `play_local.py`
directly (4m10s wall — confirms LLM latency was E-H002-2's entire cost,
not game simulation). Paired against E-H002-2 on `levels_completed`: 20
of 25 seed×game cells identical; 3/25 vs 2/25 reaching level 1+ — no
signal, indistinguishable from noise. But `eh002_2.py` never queried the
scorecard, so this compared the wrong variable.

**The LLM arm re-run through `play_local.py` (same seeds/games/steps) to
get `aggregate_score` for both arms — first real score-level comparison,
and it looks different from the levels-completed read:**

| seed | baseline score | llm score | diff |
|---|---|---|---|
| 1 | 0.0000 | 0.0497 | +0.0497 |
| 2 | 0.0000 | 0.0427 | +0.0427 |
| 3 | 0.0000 | 0.0214 | +0.0214 |
| 4 | 0.0462 | 0.0000 | -0.0462 |
| 5 | 0.2276 | 0.5487 | +0.3212 |

Mean: baseline 0.0547 -> **llm 0.1325 (2.4x)**. LLM arm wins 4 of 5 seeds
paired. Exact sign-permutation p=0.25 (n=5, not significant — the
smallest achievable two-sided p at this n is 0.0625). Not one outlier:
dropping the largest-gain seed (5) still leaves 3 of the remaining 4
positive, mean diff +0.017. **Not a claim the LLM proposer helps the
score — a reason to find out with a larger n that didn't exist before
this sweep.** Both arms' 10 sweep summaries kept together in
`results/sweeps/` (see the amended retention rule above). Full tables in
`research/hypotheses/H002_llm_hypothesis_proposer.md`.

**Order for the next session.**
1. **A larger-n score-comparison sweep** (both arms, same seeds extended
   past 5, through `play_local.py`) — the only way to move p below 0.25.
   n=10 or n=15 per arm is the next reasonable step; estimate wall time
   from this session's ~8.5 min/seed for the LLM arm before committing to
   a number.
2. **The replay-ablation experiment** (second review §14) is buildable now
   — real LLM traces exist (from E-H002-2 and this comparison) and can be
   replayed offline against a deterministic agent to separate generation
   quality from integration quality. Worth doing regardless of (1)'s
   outcome, now that it's cheap.
3. Deferred (per the review's own sequencing, unchanged): the full
   event-sourcing rewrite of `recap.py`/logging beyond the LLM-trace piece
   already done; LLM call-purpose framing (model-discovery vs.
   hypothesis-discrimination vs. experiment-selection prompts);
   call-budget-by-information-gain. Revisit once (1) is decisive either way.

**Open case, unchanged.** cd82: paint effect is two-factor (side × selected
paint colour) and the level needs *arrangement*, which has no gradient by
rule. Still the LLM proposer's test case; still not solved by it — no
hypothesis across E-H002-1 or E-H002-2 has named a precondition on another
entity's state, because the precondition schema has no slot for it
(`{adjacency, side, member}` only). A representation-language ceiling, not
yet evidence about the model's reasoning either way.

**Standing rules that bit this session.** Commit/push only when asked, per
batch — and re-read the file before writing the commit message if it
changed on disk since you last touched it (caught one wrong message before
pushing this session). Never edit `agent/` while a sweep runs. A "before
vs after" comparison needs the same seeds captured for *both* arms, not
assumed. **Retention: latest 5 sweep summaries — except a matched-pair
comparison keeps both arms together even past 5.** (Amended 2026-09-14:
the baseline-vs-LLM score comparison needs both sides' files reproducible
from the committed record; 10 are currently kept for exactly this reason.
Prune a pair only once its comparison is superseded by a larger-n rerun,
not on a file-count schedule.) Test on the games a change touches, not the
full sweep, when the touched set is known. Ollama serves one request at a
time (`OLLAMA_NUM_PARALLEL=1`) — running multiple game processes
concurrently does not parallelise LLM-proposer sweeps, only non-LLM ones.

## NEXT: relations as residuals, gated by a probe (council verdict 2026-09-14)

Reframed twice on 2026-09-14. First after dumping cd82's full belief and
finding monads that could carry no hypothesis; then after a five-advisor
council overruled two of the items that came out of that
(`council_2026-09-14_belief.md` is the full record). Standing rules from the
verdict, in force for everything below:

  * A relation returns a **residual** `int | None`: 0 means it holds, None
    means undecidable (ghost, appeared this step, history too short,
    descriptor undefined). **Unknown is None, never False.**
  * The residual **is** the progress measure. No separate progress function.
  * **Never align two grids.** Residuals are set-cardinality and counting
    only; cellwise comparison after alignment is template-matching, encoded.
  * No thresholds: a similarity threshold is a prior. `shape_diff` is 0 on
    equality and None otherwise. No rotation/scale-normalised signatures.
  * **Composites are never built.** A partition has no falsifier. Where a
    grouping is wanted it is a *view* over a persisting relation
    (`cell_exchange`, `containment`), recomputed, never stored as a node.
  * The relation set must survive derivation from a **second game's dump**;
    anything only cd82 produces is a prior wearing a generic name.

- [x] **1. identity** — explained motion, live vs remembered, reset told to
      the tracker. Post-reset minting cd82 1.7/frame -> 0.
- [x] **2. control by determinism** — see the item above.
- [x] ~~**3. composites with parts**~~ — **deleted by the council, not
      deferred.** Co-motion, enclosure and cell exchange survive as
      relations over flat entities.
- [x] **3. `relations.py`** — offline, no policy change. Descriptors
      `(colour(s), cells, bbox, shape)`, no normalisation. Six residuals over
      all live pairs, ghosts included: `palette_diff` (|symmetric
      difference|), `cell_exchange` (cells A lost this step that B gained —
      grouping evidence, not a goal), `shape_diff` (0 if equal else None),
      `containment` (cells of B outside A's bbox), `distance` /
      `distance_drift` (None until 2 frames), `count_diff` (over colour
      classes). Plus the actuation bridge the council found missing:
      `action -> delta residual` tallies per (relation, pair), the same
      structure Belief keeps per entity. No ranking by "looks like a goal".
- [x] **4. `probe_relations.py`** — replay recordings through the engine.
      **Run 2026-09-14 (4 sweeps, 11 advances): (i) 25/25, (ii) 18/25,
      (iii) literal 36%, (iii') 55% — passes; after the merge_enclosed fix
      (iii') 82%; corrected to **64%** once the probe skipped the canvas as the agent does — cd82's levers were `distance(*, canvas)`. sp80 0/3 -> 3/3 stands.** Literal (iii) is
      unmeasurable by construction (the solved frame is never shown), so
      the gate is (iii'): falling AND action-selectively driven. Every hit
      is `distance`/`containment`; `palette_diff` and `shape_diff` never
      moved on any game — over flat entities they cannot. sp80 0/3.
      See `history.md`, same date.
      Per game: (i) pairs whose residual ever changes, (ii) changes
      attributable to an action, (iii) residuals monotone-decreasing over
      the 8 frames into a level advance, plus the pairs stuck at None (the
      first intervention queue). **Exit, all three:** >=15/25 games with a
      moving residual; >=3 games with >=1 action-attributable change per
      episode; **>=50% of level advances preceded by a monotone-decreasing
      residual.** (iii) is the gate. If it fails, the relation layer is
      decoration and the fallback is novelty certification over first-visit
      frame hashes — a different build.
- [x] **4b. grouping as a view** — built; cd82 groups template, strip,
      bucket and block halves unprompted. The exit criterion was wrong:
      `palette_diff(block, template)` reads 2 and *cannot* fall, because
      the block already has the template's colours and the goal is their
      arrangement — expressible only as `shape_diff -> 0`, no gradient.
      Recorded, not worked around (`history.md` 2026-09-14).
- [x] **4c. sp80: the controlled objects are not entities** — found and fixed: `merge_enclosed` absorbed any solitary object into the canvas. sp80 now reads a full d-pad on `#4`. Original note: The move map
      learns (0,4)/(20,0) but no tracked region is CONTROL, so the brief
      says "moves something". Find why (size filter? colour shared with the
      canvas? merged by `merge_enclosed`?) — this is the second game's
      derivation the council required before the relation set is trusted.
- [x] ~~**4b'.**~~ (merged into 4b above) `relations.groups()`: union-find over
      pairs whose `cell_exchange` or `containment == 0` has persisted k
      frames, recomputed each step, never stored; `palette_diff` /
      `count_diff` / `shape_diff` computed over the view as well as over
      flat entities. Forced by the probe: `palette_diff` cannot move over
      single-colour entities, so the matching family is invisible to the
      layer until this exists. Exit: `palette_diff(block-view, template-view)`
      on cd82 reads 2 and falls under paint actions.
- [x] **4d. the matching family's residuals** — `palette_missing` and
      `part_size_diff` over the grouping view, counting only; group-record
      continuity across member rebirth. Moves on cd82, ar25, ka59.
- [x] **4e. kinds as a view** — `agent/kinds.py`; KINDS section in the brief; transfer weight in the proposer. cd82: template content and block read as one exact kind, one static, one drifting by part_size_diff 30. Transfer half not yet seen live. Original note: — things with identical shape and palette
      are one kind; what one instance did (drained stamina, vanished,
      scored) is evidence about the rest. The user's snake example: eat
      one food, expect the same of its lookalikes. A view over equal
      descriptors with belief transfer; None until two instances exist.
- [x] **5. the brief** (supersedes "event log") — `agent/brief.py`, shown
      live in the recap's Brief card: THINGS / GROUPS / CONTROL / RELATIONS
      (levers, or "moves under every action alike") / FALLING (only with a
      lever) / OPEN / RECENT. The serialisation was designed before the
      proposer, as the council asked, and reading it found three faults
      the panels had hidden (canvas as relatum, drains as levers, canvas as
      CONTROL). The original exit — `palette_diff 2 -> 1` on cd82 — was
      impossible, see 4b.
- [ ] **5b. the cut-off: is the brief rich enough to hand over?** Decided
      2026-09-14: "rich enough" is not a property of the vocabulary (every
      vocabulary looks incomplete from inside) but a test the brief passes
      or fails. Two tests, both runnable before any LLM exists:
      - [x] **(a) recall at the boundary — 7/11 advances in the text, 0 selection gaps, 4 vocabulary gaps (all cd82 paint advances). Bar cleared.** `scripts/probe_brief_recall.py`:
            for each recorded level advance, take the brief 3-8 steps
            *before* it and ask whether the coordinate that fell into the
            advance under a lever (the probe's (iii') key) is in the text —
            in FALLING, in RELATIONS, in the engine only, or nowhere. The
            three outcomes name three different gaps: selection, nothing,
            vocabulary. Bar: a majority in the text.
      - [x] **(b) the oracle read — 3 of 5 (cn04, tu93, ka59 hit; ar25, vc33 miss). Bar cleared.** Five briefs from games not yet looked
            at, read cold with "state the goal and the first three moves",
            against what the game wants. Bar: >= 2 of 5.
      - [ ] **brief revision from the cold reads** — [x] available actions,
            [x] click coordinates in RECENT, [x] extent w x h per thing,
            [x] no stale ids in GROUPS rows, [ ] blocked moves from the
            obstacle map (tu93's reader: "which presses were blocked").
      - [x] **(c) the enumerating proposer + verification loop** —
            `agent/hypothesis.py`, `ARC_PROPOSER` default OFF. **A/B n=30:
            median 0.0145 -> 0.0420, p = 0.082 (pre-specified, whole
            sweep); untouched 17 games identical; touched 8 split into
            navigational gainers (m0r0 0 -> 9 sweeps reaching L1) and
            cd82 losing 16 -> 4 because movement hypotheses displace the
            paint action.** Not promoted; re-run after step 6. Next for it: the
            level-boundary diff to tell it which residuals ever mattered;
            walls (a lever that does not move the residual from here should
            consult the obstacle map before being falsified); the LLM
            proposer behind the same `Hypothesis` type — development-time
            only, since the competition notebook has no internet and no
            `anthropic` SDK is installed here.
      - [~] **(c') the LLM proposer** — interface, schema validation, call policy, hypothesis pool and experiment selector built and tested with a scripted client (H002); no model attached yet — needs Ollama (~4B model) or a remote endpoint. Brief in, `Hypothesis` out.
            **Offline path on Kaggle, verified 2026-09-14 from the official
            template and entrants' notebooks:** no internet at evaluation;
            weights come from **Kaggle Models attached to the notebook**
            (`kernel-metadata.json` `model_sources`, mounted at
            `/kaggle/input/models/<owner>/<model>/transformers/<variant>/1`),
            served by **vLLM installed from offline wheels** (a wheels
            dataset, or the competition's `arc_agi_3_wheels`) as a local
            OpenAI-compatible server on `127.0.0.1:8000/v1`, called with the
            `openai` client. Models in use: official template
            `danielhanchen/gpt-oss-120b` (RTX Pro 6000; "runs slowly");
            entrants `google/gemma-4` `gemma-4-31b-it` and Qwen 3.x 27B FP8;
            smaller attachable options `qwen-lm/qwen-3-5` (4B), `qwen2.5-coder`
            (0.5-32B), `metaresearch/llama-3.2` (1B/3B), `google/gemma-3`.
            Time is the binding limit (`GAME_TIME_LIMIT_S`, "scorecard not
            produced in time"), so the proposer must be called rarely —
            at level start, on a falsified streak — not per step. Local
            mimic: run vLLM (or Ollama) with the same model and point the
            proposer at the same base URL; the agent code is identical. — brief in; a goal
            predicate over relation keys, a progress coordinate and a few
            actions out; verified by residual movement within k frames;
            every test priced in actions; per-episode, nothing cached.
            The vocabulary then grows from *falsified* hypotheses — a
            primitive is added only when a real failure was inexpressible,
            and survives a second game — rather than from anticipation.
      Reasoning: build the layers in parallel with the consumer rather than
      mastering one spot at a time; the consumer's failures are the only
      principled source of new primitives.
- [x] **6. level-boundary diff as supervisor** — `agent/supervisor.py`, wired into the proposer's ranking and the brief (MATTERED). Re-run of the proposer A/B pending. — snapshot the residual
      vector at t-1 and t of every level advance; only residuals that
      collapsed at >=2 independent boundaries are admissible hypothesis
      targets. A hypothesis is admissible only if its residual is finite
      and strictly decreased at least once in the last 5 steps under our own
      action. Goals may change per level; nothing may assume otherwise.
- [ ] **7. enumerator, serialisation-first, then LLM** — design the text
      the proposer reads before writing the proposer. Proposal space is
      pairs x relations x (targets, for ACTION6), gated by reachability;
      every hypothesis test costs actions from the depth-weighted budget and
      must be priced.
- [x] **exploration floor inside the proposer — measured and reverted.**
      Pressing every legal action 4x per level: cd82 16 -> 3, sp80 25 -> 15,
      m0r0 9 -> 6 (8 touched games x 30 seeds). The paint action's effect is
      *conditional on position* (76 presses, 8 paints), which no count of
      presses reveals. Kept: probing winning moves from earlier levels.
- [x] **7a. conditional levers** — built (adjacency + side, preconditions, outcome taxonomy, routing to the side). E-7a: cd82 unchanged (16 -> 2), gains held/rose elsewhere (ar25 9 -> 15). cd82's rule is two-factor (side x selected colour) plus arrangement; open. Original note: — a lever *given* another residual's
      value: per (relation, pair, action), tally movement split by a
      condition such as `distance(CONTROL thing, member) <= d` (nearest
      first). Says "ACTION5 drives part_size_diff(template, block) down
      when the bucket is adjacent" — eat-when-touching, push-when-adjacent,
      paint-when-aligned. Hypotheses then carry a precondition the router
      can satisfy first. Exit: cd82's paint lever appears in the brief with
      its condition; cd82 recovers on 30 seeds without costing sp80/m0r0.
- [ ] **rename `stamina` -> `sawtooth_region`** and strip the
      refill-on-reset semantics from its description: the council's one
      finding against existing code — a slot whose test was written first
      and called evidence.
- [ ] **re-run the belief-routing A/B on a frozen tree.** The 2026-09-14
      run was contaminated by edits to `agent/` while it ran. Its one robust
      reading: the per-level gate is exactly inert, and the target it routed
      to on cd82 was the controlled object's own ghost.
- [x] **parity for the identity, control and merge work** — 30 seed-paired sweeps at `54173e7`: byte-identical outcomes, p = 1.000. No default action changed. Original note: It changes the default action
      stream and has not earned a default by measurement. The council's
      caution applies: a representation change is not expected to move the
      score until something consumes it, so the instrument here is parity
      (no regression), not improvement.

### Superseded: connect beliefs to action (2026-09-13 framing)

Everything below the belief layer is built, tested and inert. `belief`
reads nothing into any decision, and that is the single reason the score
has not moved: four recording-only layers were added and each moved it by
nothing, exactly as each was predicted to.

**The candidate consumer.** `_pick_coordinate` currently clicks the hottest
*interest* cell. Interest marks where change has happened — measured, that
is not where the goal is, and routing toward it cost score. Belief marks
what an action has been *shown* to do to a specific thing. On cd82 that is
`ACTION5 -> #12/#14`; on wa30 `ACTION2 turns #0`. Clicking or acting
through the entity a role points at is a different target from the hottest
cell, and it is the first one this project has had that is grounded in
evidence about an action rather than about a location.

**Aim it at depth, not breadth.** This is the important part. Every
mechanism added so far — router, interest map, shift fallback — bought more
level-1 completions and never a level 2. Breadth at level 1 is worth 1/21
of a game. A belief consumer aimed at "click better" is aimed where
everything else was aimed and will likely land where everything else
landed. Decide what a depth-shaped consumer looks like *before* building
one.

**Protocol** (the variance floor is known, so this is settled):
n >= 30 per arm, medians, permutation test, never means — a single lucky
sweep moves the mean 56% while the median holds (measured, p = 0.50).
~15 min per arm. If the change touches only a few games, **test those
games**: the shift fallback altered behaviour on 4 of 25, and the 25-game
aggregate diluted it ~6x into near-insignificance (p = 0.044) while the
affected-games test read p < 0.0001.

## Resolved: the agent is told about RESET (2026-09-14)

`_reset_attempt` now calls `RegionTracker.expect_home()`; the tracker keeps
the layout as it stood on the first frame after each `clear()` or reset and
matches the post-reset frame against it by overlap before any other pass.
Post-reset id minting: cd82 1.7/frame -> 0.00, ls20 0.00, wa30 0.00. The
shape-revive pass is kept for what it was built for. Original note follows.

## Was open: the agent has no model of RESET

The agent does not know that a reset restores the layout. It sees every
object vanish and new ones appear.

Measured: a post-reset frame mints region ids at **~20x** the ordinary rate
(cd82 1.7 per frame against 0.08; wa30 25x; ls20 17x). Each fresh id
discards the belief attached to the old one — **including the
action-to-entity mapping already learned** — so the agent repeatedly
forgets what it had worked out about a thing, then has to re-earn it.

Mitigated but not fixed. `RegionTracker` now has a third matching pass —
same colour, same shape, reappearing within `SHAPE_REVIVE_WINDOW` frames —
which recovers identity across a teleport by inference (cd82 42 -> 35 ids,
ls20 19 -> 12). The real fix is to *tell* the tracker a reset happened,
from `_reset_attempt`, rather than have it deduce this from shapes. That
also removes the one assumption the shape pass carries: that a same-shaped
thing reappearing moments later is the same thing, which is a guess, and
is why the window is kept to 3 frames.

Related and unbuilt: nothing models "an action caused a rotation" as a
*persistent fact about that action* in a form the router could plan with.
Rotations are counted per action and shown, but a rotation does not compose
into a position the way an offset does.

## Resolved: the deformation-tolerant tracker (A/B, n=100 per arm)

`perception.detect_shift` — a motion lens that tolerates a changing shape,
because every exact lens demands the shape be identical and cd82's object
deforms by up to 14 cells as it moves. **Default ON: the first change in
this project to earn a default by measurement.**

| test | OFF | ON | p |
|---|---|---|---|
| the 4 games it changes (pre-specified) | 0.0000 | 0.0898 | **< 0.0001** |
| cd82 clearing level 1 (mechanistic prediction) | 19/100 | 40/100 | **0.0017** |
| whole 25-game score | 0.0106 | 0.0190 | 0.044 |
| the 21 games it cannot touch (sanity) | — | — | 0.73 |

Zeros fell 13/100 -> 6/100; games reaching level 1 rose 1.50 -> 2.01 per
sweep. The ON arm produced **one level 2** — the first in any recorded
sweep here. n=1: noted, not claimed.

Two guards were needed and both were caught by tests before any sweep ran:
the **background is also a "mover"** (when an object goes right the canvas
loses cells where it arrived and gains them where it left, so the canvas
shifts *left* and is the larger candidate — unguarded this teaches a
reversed offset for every action on every game), and **weak evidence must
not contaminate strong** (the fallback is barred from any action an exact
lens has ever explained; without that, ar25's ACTION1 went from a clean
(0,3)x20 to (0,-5)x17 and fell out of the map).

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
- [x] **Sweep summary retention: the latest 5 are committed, the rest are
      pruned** (2026-09-14, user decision; was 10 — experiment tracking moves
      to `research/`, and ~410 files had accumulated before the first prune).
      The aggregate numbers every past comparison rests on live in
      `history.md`, which is the record; the JSON is the raw material for
      the *current* question only. `git log` still has every pruned file.
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
- [x] **Variance floor measured** (n=30 at one unchanged commit): mean
      0.0307, **median 0.0131**, sd 0.0490, range 0.0-0.194, top sweep 6.3x
      the mean. Heavy-tailed, so compare medians. A sweep costs ~30-55s,
      which is the whole reason any of the above became answerable.

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

- [x] **Connected-component object extraction — BUILT, and the RISKY
      verdict was too strong.** Now `perception.connected_regions`, pure
      Python, no `scipy`. The original objection conflated two failure
      modes: **coverage** failure (a game of non-contiguous motifs gets
      grouped too finely, so we detect *less* — graceful, and no worse
      than the nothing we had) and **ontology corruption** (asserting
      something false and building on it). Grouping risks only the first,
      because it proposes that some pixels may be one thing and says
      nothing about what. What the caution was really about is **role
      assignment**, which is where the risk genuinely lives and which
      stays evidence-gated in `belief.py`. Decided by measurement in the
      end: a signal that is perfect at the region level (cd82's bar,
      64 cells -> 0) was unrecoverable at the colour level (164 -> 100,
      61%, rejected).
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
