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

## START HERE (handoff, 2026-09-15 evening) — the latent-state week

**State.** `main` at `04fdfbb` pushed (H005 Stage 3, README, full sweep
0.1431). Uncommitted: this section, `scripts/alias_probe.py`,
`research/hypotheses/H006`–`H008` (+ README rows), the 09-15
review, one `history.md` entry. 261 tests green. Nothing runs in the
background. `ARC_PROPOSER` / `ARC_LLM_PROPOSER` still OFF by default.

**What changed the plan.** Reviewer C's fourth pass
(`docs/expert-reviews/reviewer_c_09_15_2026.md` — long; the gold is §3,
§5–8, §16 and the second note's §4–6, §12–13) makes one structural claim:
the layers describe *observations* well and *hidden state* not at all.
cd82's "which swatch is selected" is a persistent fact set by an earlier
action and held, not a relation over the current frame — and H005 Stage 3
proved exactly that by finding adjacency the wrong proxy. Its bottleneck
ranking: 1 no latent state, 2 hypotheses can't name a state variable,
3 information-seeking not first-class, 4 one-step transition model,
5 goal tied to visible residuals … 10 routing. **Stop routing work.**
Measured before adopting (`scripts/alias_probe.py`; `history.md`
2026-09-15 "Perceptual aliasing"): identical (frame, action) contexts
diverge on **0% of repeats in 12 games and 44–84% in 10** — and the 0%
set is exactly the set the agent can play. The premise holds where it
matters. Whether the divergence is *state* or *noise* is H006's question; the
probe cannot tell.

**Three things the review said not to do, adopted.** No LSTM / LMU / JEPA
this week — build the interface one would plug into. No semantic variable
names (`selected_color`, `mode`) — a variable is `Z<n>` with a domain, a
value and evidence, described after the fact. No new perception
primitive, no more LLM score sweeps.

**One rule added** (the temporal form of the governing principle, review
second note §6): *don't retain history unless it changes the predictive
distribution over future observations.* A latent variable is admitted only
if it splits an aliased context's outcomes.

**The week — three separately-falsifiable claims, one file each, so a
result can be cited by number: H006 *is there state?* (Days 1–3), H007
*can a hypothesis name it?* (Day 4), H008 *does it predict?* (Days 5, 7).
Split rather than bundled because each can fail while the others pass.
Each day has a deliverable and a gate; a failed gate changes the next
day, it does not skip it.**

1. **Look, then define (no `agent/` change).** `alias_probe.py --dump`
   for cd82, m0r0, sk48, g50t; for each aliased context replay the two
   outcomes through the recap (`SEED=`, `STEPS=`) and say what differed.
   Classify per game: *state* (something earlier separates the outcomes —
   an action count, a prior click, which entity last changed) vs
   *stochastic* (nothing does). Deliverable: a 10-row table in H006.
   Then the definition, docstring first: `LatentVariable` = id, domain,
   value | None, set_by, evidence — and `admit()` as the only way in.
   Gate: if every aliased game reads stochastic, Day 3's history-derived
   generator is dropped; the visible-persistent kind (Day 4) is built
   regardless, because cd82 needs it either way.
   **Done 2026-09-15.** 89% of the aliasing is quantised resource meters
   (sub-cell counter = actions since reset, exact on 5 games); cd82 has
   *no* mechanic aliasing; the hidden-state remainder is 72 contexts on
   su15 / sk48 / g50t / sc25 at ~2 visits each. Gate: history-derived
   family stays; Day 3 narrows to the 72 and needs a targeted non-LLM
   sweep of those four games for repeats. Table in H006.
2. **Trajectory reconstruction, offline.** `probe_relations.replay`
   already runs regions → tracker → relations from recordings; extend it
   to run belief and the predictor too, emitting S_t (live entities with
   roles, residual vector, stamina, displacement) per step. Two reads:
   (i) re-key the aliased contexts by S_t instead of pixels — how much
   does the existing vocabulary already resolve? (entity ids and
   displacement carry attempt history the pixels don't); (ii) H003's
   one-step forecast scored on the aliased contexts specifically — the
   baseline row of the predictive-sufficiency table. Deliverable:
   `scripts/latent_probe.py`, one table per game.
   **Done 2026-09-15.** Built as a tap on the real agent (not a rerun):
   action stream identical to the play_local recording of the same seed.
   S_t leaves 162 of 1,252 pixel-aliased contexts aliased with identical
   agent state; forecast accuracy on aliased contexts ~ all steps.
3. **Candidate variables as splitters.** Two generators over the Day-2
   trajectories, no agent change. (a) *visible-persistent*: an entity
   whose descriptor takes ≥ 2 values, changes only under some actions
   (Belief.effects selective) and holds otherwise; value = its descriptor
   key (`kinds.py`'s equal-descriptor view). (b) *history-derived*: a
   small enumerated family — last action that changed E; count of A since
   level start mod 2..4; E ever vanished; steps since E changed. Score
   each as a splitter: does its value partition every aliased context's
   outcomes? Rank by contexts resolved. Deliverable: per game, the best
   candidate and the fraction resolved. Gate (H006 P1): cd82 ≥ 50% by
   one variable → it is state, and Day 4 knows which kind. H006 closes
   here, either way.
   **Done 2026-09-15.** `scripts/latent_splitter.py`. `Z1 = actions since
   reset` confirmed with repeats, above null, zero contradictions on six
   meter games (cd82 82/0, dc22 325/0, ...). Mechanic remainder (sk48,
   sc25, su15, g50t residue): nothing above null. H006: holds for the
   meter class, undetermined for the rest — verdict in H006. Day 4 (H007)
   proceeds unchanged; H008 takes the counter as its one certain gain.
4. **The first consumer: a `state` condition kind — H007** (the 09-14
   handoff's item 1, reframed). `precondition` gains `("state", member, value)`:
   met when `member`'s current descriptor key equals `value`.
   `_condition_met` checks it; when unmet, `_hypothesis_action` satisfies
   it by *acting*, not moving — the action Belief.effects says sets that
   entity, None if unknown (the bet expires unmet: correct). Enumerator:
   tally `by_action_given` under the state condition as adjacency/side
   are tallied, so a state-conditioned lever can form with no oracle.
   Then H005 Stage 4 = the cd82 oracle with (adjacent:-x, template) AND
   (state, swatch, marked), seeds 1–3, against Stage 3; then the
   enumerator alone — does the lever form? Gate (H007 P1): jointly met on
   ≥ 3 of 8 steps (Stage 3: 0–1).
   **Done 2026-09-15.** Kind, setter memory (keyed by resulting state)
   and acting route built, 264 tests, default stream unchanged. Oracle
   seeds 1–3: state restored in one step on all three; jointly met 3/8
   on seed 2 (falsified: wrong colour named — the verifier working), 0/8
   on seeds 1, 3 because the *walk* to the block's −x side has no path
   (orbit hops vs a displacement planner). Correction: H001/H005 put the
   adjacency on the template, whose −x side is off screen. Enumerator
   tally not built: the state never varies under exploration (6 strip
   clicks / 4,000 steps) — week 2's information-gain item.
5. **Multi-step prediction — H008.** `Predictor.rollout(S, [a1..ak])` in the
   vocabulary — apply the forecast's entity effects and residual
   directions to an imagined S, forecast again. No pixels, no simulator.
   Score k = 1, 3, 10 offline on the Day-2 harness, per game, with and
   without the state condition in the tallies. This is the review's
   predictive-sufficiency table and the metric between "representation
   valid" and "score". Deliverable: k-step rows in `prediction` in sweep
   summaries; the brief's PREDICTED shows k=3. Gate (H008 P1): up on the
   aliased games, flat on the 0% controls.
   **Done 2026-09-15.** Live rollout scoring shipped (`Predictor.
   horizon`, every sweep summary); offline scorer verified exact against
   a live sweep. Controls flat (P1's negative half, met); 5 of 10 aliased
   games gain 2-7 points at k=10 from Z1, 4 gain nothing (a per-seed vs
   H006's pooled admission gap, not a contradiction). k=10 cleanly
   separates games with a learned move map (57-90%) from those without
   (14-66%); cd82 mid-table, matching H009.
6. **The planner factorial on cd82 — H009** (added 2026-09-15 evening
   from a reviewer proposal the user relayed, after Day 4 showed the
   *walk* is what fails). Separate representation, transition model and
   search: E0 is the bucket's motion a function of (position, action)?
   E1 learned moves + oracle target + `navigation.plan`; E2 the empirical
   position graph + oracle target + BFS. Readings: A (all fine, the gap
   is goal selection), B (the model class — one offset per action — is
   insufficient), C (position is not the state). Offline over the cd82
   traces; live only if ambiguous. `research/hypotheses/H009_planner_factorial.md`.
   The original item 6 here (the level boundary reading state) had no
   claim to test yet and moved to the week 2 list below, unbuilt.
   **Done 2026-09-15, reading B.** E0: 8 orbit positions, motion 32/32
   deterministic in (position, action), not in the action alone. E2: a
   −x target reachable from every position in ≤ 3. E1: the learned map
   is four 11-cell axis moves; 0 of 1,244 plans honoured at the first
   step (59% would arrive if followed blindly, but the router drops
   each after one mismatch). The transition model's *class* is the
   defect; fix = a position-graph model for the CONTROL thing, week 2.
7. **Ladder, and the decision (H008 P3).** A: current. B: + H007 (state
   condition kind, enumerator + routing). C: + state-conditioned tallies
   in the predictor. Touched set cd82, m0r0, sk48, g50t, cn04 + controls sp80,
   ls20, ar25; n=10 seed-paired, 400 steps. Read in order: k-step
   accuracy; aliased contexts resolved; unmet-rate and hypothesis
   outcomes; L1 reach; score last. Gate for week 2: k-step accuracy up on
   the aliased games with the controls flat.
   **Skipped, 2026-09-15 night, by user direction.** H009 found the
   actual cd82 bottleneck is the transition model's *class*, which
   neither arm of this ladder varies — running it would mostly measure
   noise around a defect it doesn't touch. Superseded by going straight
   to H009's own fix (H010, below) instead.

**Explicitly parked this week** (the 09-14 handoff's items 2–6): tracing
ar25 seeds 3/9/10; the matched-seed sweep of the self-referential fix;
why routing fails on self-referential targets; the prompt-side "moves
alike" fix; the event-sourcing rewrite. All routing / LLM polish — rank
6–10 on the review's list. The recap UI redesign
(`docs/expert-reviews/UI_instruction.md`) is shelved until the latent
layer exists — see Shelved ideas.

**Week 2, started early 2026-09-15 night** (Day 7's ladder skipped —
see below — in favour of H009's own finding, per user direction).
**H010, Stage 1 done:** `agent/control.py PositionModel` + `agent/
navigation.py plan_graph`, 12 new tests (278 total), validated offline
through the real code against H009's own cd82 data — edges match
exactly, reachability matches (<=3 actions), and replaying H009's 1,779
real decisions: honoured at the first step 1,779/1,779 (`plan`: 0/1,244).
**Stage 2 (live wiring — `.observe()` in `_learn_from`, `_route_to`/
`_route_for` preferring `plan_graph`) is the next concrete step**; it
needs a regression design first, since `plan_graph` deliberately does
not extrapolate to unobserved positions the way `plan`'s offset model
does — a real behavioural difference on sparsely-covered games, not
just an improvement, so a parity sweep across the games with an
existing move map (sp80, ls20, ar25, m0r0, dc22, …) comes before it
ships. Full detail in `research/hypotheses/H010_position_graph_model.md`.

Originally-scoped week 2 candidates, still open: planning through the
model — depth 2–4 rollout ranking, the "local transition simulator" from
On hold, now with a state to simulate. Information gain as a utility term
beside progress, with weights that shift with epistemic state (H004's
discriminating press, generalised). The LLM schema gains a latent-variable
slot — the review's "latent-state scientist" (§11), which H002 cannot be
until the slot exists. A learned residual memory `h_t` only if the
explicit state's k-step accuracy plateaus with unexplained aliasing left
(review second note §10–11, Level B). **The level boundary reads state**
(original Day-6 item, no claim to test yet): `BoundarySupervisor.on_advance`
records, beside the falling residuals, every variable's value at the
advance and its last change in the window — "what state transition
preceded success" (review §8). Consumer: the proposer's ranking prior,
weighted like `mattered`, never a rule. Free on the recordings first
(which values held at each recorded advance?), live second. A **pooled,
cross-seed Z1 admission** for `latent_rollout.py` (H008's own finding:
wa30/sc25/sk48/su15 gained nothing under a per-seed-only admission
despite wa30 being H006-confirmed at the pooled level).

**H011 opened and Stage 1 run, 2026-09-15 night** (the information-
directed exploration item, started early per user direction after H009
closed): `scripts/h011_click_novelty.py` replays cd82's 322 real
ACTION6 decisions and asks whether a novelty-aware re-ranking would
reach the swatch strip far more than the real 1.6%. Result: expected
160.1 of 322 (32x) under uniform draw from whatever is tied for fewest
real clicks; the strip is never absent and holds ~50% of that tied set
when present. The gap is entirely `ClickTargeting.pick()`'s tier
ordering (narrower salience tiers almost never run dry), not a missing
signal or a structural disadvantage. Full detail in
`research/hypotheses/H011_information_directed_targeting.md`. Stage 2
(blending novelty into `pick()`'s live ranking) is next, pending
direction on the exact mechanism — a change to `agent/attention.py`,
not the router and not new representation.

**H011 Stage 2 built and swept live, 2026-09-15 night**
(`agent/attention.py`, `agent/constants.py CLICK_NOVELTY_WEIGHT`, per
user direction to blend salience and novelty as a weighted score, not
a hard override). Live sweep on cd82 (seeds 1-5, weights 0/0.5/1/2/4):
strip clicks 1.6% -> 42-52% at EVERY weight, including 0 -- the fix is
almost entirely structural (ending the hard tier cutoff), not the
novelty term itself, which is documented plainly rather than
overclaimed. Measured trade-off: the hottest 8x8 region's click share
fell from ~20% to 14-18%. Weight set to 1.0 (least arbitrary given flat
sensitivity, not a tuned optimum). 8 new tests, 286 total pass. Not
done: a broader multi-game regression sweep and any score read. Full
detail in `research/hypotheses/H011_information_directed_targeting.md`.

**A second reviewer (`docs/expert-reviews/reviewer_g_09_16_2026.md`)
converged independently on the same two gaps**, then revised cleanly
once shown H007 and H011 Stage 2 already existed (its first pass
proposed both as new work — traced to the same stale-header bug fixed
below, not a flaw in its reasoning). The two-pass exchange settled on
one sequence, folded in here:

1. **Immediate, in flight**: finish and read the whole-sweep n=30
   seed-paired parity check on H011 Stage 2 (baseline arm done 30/30,
   clean — mean 0.0286, median 0.0162, matching the historical noise
   floor; treatment arm running 2026-09-16). **Hard gate, both
   reviewers' words**: revert or soften the tier-structure change if
   level-1 clears drop by more than 1 per 30 sweeps on games that
   previously cleared, or if the median score falls materially.
2. **H012 opened** (`research/hypotheses/H012_movement_novelty.md`):
   the movement-side symmetric counterpart to H011 — score frontier-
   tier actions by `PositionModel`/`MoveModel` sighting counts, not a
   visited/unvisited bit. Given its own number rather than "H011 Stage
   2b": a separately falsifiable claim, same split logic as H006/H007/
   H008. Predicts orbit coverage on cd82 reaches >= 9/10 of H009's
   seeds by decision 150 (was 8/10). Explicitly does NOT claim to
   unblock H007 P2 — that depends on click coverage (H011, already
   live), not movement coverage; a corrected reading of the second
   review's first pass, which had pinned that prediction to the wrong
   mechanism. Flag-gated (`ARC_MOVEMENT_NOVELTY`) per both reviewers'
   operating rule — the gap H011 Stage 2 left uncorrected. Waits on
   H011's own parity gate first.
3. **Re-test H007 P2 standalone**, decoupled from H012 and runnable as
   soon as H011 clears its gate: rerun the enumerator on cd82 (10
   seeds, 400 steps) and ask whether a state-conditioned lever for the
   paint action now forms, given the click-coverage change alone. If
   not, the residual gap is in tally/lever-formation logic, a smaller
   follow-up than assumed.
4. **H010 Stage 2**, once H011 (and H012, if it ships) are parity-clean:
   wire `PositionModel.observe` into `_learn_from`; prefer `plan_graph`
   over `plan` when it has edges from the current position, falling
   back otherwise. Same regression design and hard gate as above,
   n>=30 on sp80/ls20/ar25/m0r0/dc22. Success criterion (both
   reviewers): the "path found but immediately dropped" failure H009
   documented disappears, and the H007 two-condition oracle's joint-
   satisfaction rate rises on the seeds that were walk-blocked.
5. **Phase 4 (new, not yet built)**: gate a hypothesis's live action
   budget on a short internal residual rollout (H008's predictor,
   extended a few steps) showing the residual is expected to fall
   before any live action is spent — the minimal "plan through the
   model" step, staying inside residual language. Implement only after
   H010 Stage 2 is wired, so the internal model actually has
   position-dependent transitions to roll out.
6. **Only then reopen the proposer** (H002, a richer enumerator):
   giving it more power while exploration and the transition model are
   still incomplete mainly amplifies existing failure modes, per both
   reviewers.

**Operating rules, adopted from the exchange**: one live behavioural
change at a time, behind a flag (H011 Stage 2 is the one exception,
built before this rule was adopted — not retrofitted, since it is
already mid-parity-check); n>=30 seed-paired parity with the explicit
"> 1 level-1 clear per 30 sweeps" regression bar on games that already
work; offline/oracle/counterfactual first whenever a claim is
representational or about ranking, live only once the mechanism is
proven; the README table is the single source of truth for hypothesis
status, headers kept in sync with it (see `research/hypotheses/
README.md`'s own note, added 2026-09-16 after exactly this drifted and
produced the first review pass's staleness).

**Standing rules, unchanged, plus one new one (2026-09-15 night):**
never gate a commit on `make test | tail -N` or any piped test command —
the pipeline's exit status is the last command's, not the test run's,
and a real failure (H010's `plan_graph` determinism bug, caught this way
after the commit had already landed) can slip through silently. Run
`make test` (or `pytest`) unpiped, or check `${PIPESTATUS[0]}`.
Commit/push only when asked, per batch.
Never edit `agent/` while a sweep runs. Same seeds for both arms. Test on
the touched set, not the full sweep. Retention: latest 5 summaries, a
matched pair kept together.

## Handoff, 2026-09-14 night (superseded — see START HERE above; its items 2–6 are parked there)

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
smallest achievable two-sided p at this n is 0.0625).

**Extended to n=10 (seeds 6-10, both arms) — doubling the sample did not
resolve it, and the way it didn't is the actual finding.** Mean held at
2.0x (0.0523 -> 0.1061), but **median barely moved (0.0413 -> 0.0448)**,
6 wins / 2 losses / 2 ties, sign-test p=0.125 (improved) but Wilcoxon
signed-rank (weights by magnitude) p=**0.193** — *less* significant than
the sign test, because the wins are mostly small while the two losses
(seeds 4, 10) are moderate; the mean is carried almost entirely by two
standout runs (seeds 5, 7: +0.32, +0.15). A real, uniform effect should
sharpen both tests together as n grows; this sharpened neither cleanly —
the signature of a couple of good outlier runs on top of a flat typical
case, not a shift in the typical case. **Decided not to chase this
further via larger n**: marginal information per 40-minute sweep is low,
and there is a more informative next experiment that needs no new sweeps
at all. All 20 sweep summaries (10 baseline + 10 llm) kept together in
`results/sweeps/` (see the amended retention rule above). Full tables in
`research/hypotheses/H002_llm_hypothesis_proposer.md`.

**The replay-ablation harness: built and Stage 1 passed.**
`scripts/replay_ablation.py` — small, reuses `ScriptedClient` (already
existed) and `LLMProposer.trace` (previous entry) rather than adding new
machinery. Stage 1 (does replaying the exact recorded replies, offline,
reach the same outcome as the original live run?): **5 of 5 exact matches**
across ar25 (seeds 1, 3, 5) and cd82 (two seeds), 3-4 calls each. The
pipeline is genuinely deterministic once the model's output is fixed.
Bundled in the same pass: `Proposer.log` now tags each closed hypothesis
with `source`, saved as `hypothesis_log` in every sweep summary — needed
to check bottleneck #4 (exploration/action-budget, below) per-source, not
yet analysed since none of the existing twenty summaries carry it (only
live from this point forward). 251 tests.

**Generation-quality fix: shipped, matched-seed tested — correct, not a
score win.** Traced one real call (ar25) and found the actual failure
mode: all 5 accepted hypotheses claimed an unconditional lever for a pair
the brief's own RELATIONS section had just said had none — fabricated
groundedness, not malformed JSON. `parse_hypotheses` now rejects an
unconditional claim without a real lever, the same bar the enumerator
already holds itself to; a stated precondition stays exempt.

Then ran the fix through the same matched-seed comparison (games/seeds
1-10/200 steps unchanged, only the code differs from the existing pre-fix
LLM arm): mean score baseline 0.0523, pre-fix llm 0.1061, **fixed llm
0.0817 — down, not up**. Fixed vs. pre-fix directly: 2 wins / 5 losses /
3 ties, sign p=0.156 (not significant, leans negative). Mechanism totals
confirm the fix fired at scale, exactly as intended: 131 `no
unconditional lever` rejections, valid-schema rate 47.1% -> 19.4%.

**Not reverting** — the fix is correct on its own terms regardless of
score (an unconditional claim contradicting stated evidence should not
be accepted), and the score effect isn't significant either direction.
But it undercuts the simple story that removing fabricated content
should help: a plausible reading is that even a hypothesis with a
fabricated "why" still names a real `(action, relation, pair)` target,
falsified cheaply if wrong (budget 8), and some of those "wrong
justification, plausible target" bets may have functioned as exploration
diversity via the untested-LLM priority tiebreak in `select_experiment`
— rejecting more than half of them may have cost some of that diversity
along with the noise. 254 tests. All thirty sweep summaries (baseline,
pre-fix llm, fixed llm — 10 seeds each) kept together in
`results/sweeps/`, the matched-pair retention exception now covering a
three-way comparison.

**Resolved: softened to tag-not-reject.** `parse_hypotheses` no longer
drops an unconditional claim with no lever; it tags it
`source="llm_ungrounded"` and keeps it live. The whole mechanism is that
one string — `select_experiment`'s untested-LLM priority tiebreak checks
`source == "llm"` exactly, so an ungrounded bet stops jumping the queue
but stays selectable through the ordinary flow, and
`closed_by_source`/`evicted_by_source` separate its outcomes from
grounded ones for free. Verified for free again (same recorded ar25
reply, no new LLM calls): all 5 previously-rejected hypotheses now
accepted and tagged. 255 tests.

**Matched-seed swept — four arms, zero significant differences.**
Baseline/pre-fix/strict-reject/soft, all at seeds 1-10/200 steps: mean
0.0523 / 0.1061 / 0.0817 / 0.0761; soft has the highest median (0.0704)
of all four but its max falls back to baseline's ceiling (0.2276),
losing the 0.5487 outlier both LLM arms hit on seed 5. Every pairwise
comparison (sign test and Wilcoxon) is not significant; soft vs. strict
is the closest to an exact coin flip in the whole investigation
(p=0.94/0.81). **Four n=10 sweeps on this axis now, no signal on any of
them — recommending a pause on more score sweeps here.** The suggestive
(not proven) pattern: softening traded an occasional big win for
broader, smaller, more consistent gains.

**Both pivots done, same session, no new sweeps.** Bottleneck #4: the
enumerator's conditional bets never waste a step on an unmet precondition
(0.0% across ~800 closed bets, both arms); the LLM's do (39-47%). Traced
to a specific, clean cause: **12 of 17 LLM conditional hypotheses name a
precondition `member` that is one of the relation's own two entities**
(e.g. `distance(2,4)` conditioned on being adjacent to `#2` itself) rather
than a genuine third entity. Split by this: self-referential preconditions
burn **50.9%** of their budget on unmet routing; proper third-entity ones
burn **0.0%**, matching the enumerator exactly — the largest, cleanest
effect size in the whole H002 thread, well past anything the score
comparisons showed.

Stage 2 of the replay-ablation: hand-authored an oracle hypothesis for
cd82 (H001's "adjacent side -x" finding, real entity ids from a recorded
brief) and replayed it against three seeds — expired (7/8 steps unmet) on
one, falsified (tested properly, residual never moved) on another, never
closed (pool wiped first) on the third. `cd82` reached level 1 in zero of
the ~30 real runs recorded this session; the oracle still failed on 2 of
3 seeds tested. A negative result and the most conclusive one in this
thread: direct causal confirmation that cd82's two-factor rule (side x
selected paint colour) cannot be solved by a schema that expresses only
the first factor, independent of who proposes the hypothesis.

**Self-referential-precondition fix: shipped, verified for free, not yet
matched-seed swept.** Same shape and same reasoning as the lever-
grounding fix: `parse_hypotheses` tags (does not reject) a precondition
whose `member` is one of the relation's own two entities as
`source="llm_selfref"`, which drops out of `select_experiment`'s
untested-LLM priority the same way `llm_ungrounded` does. Verified
against the exact recorded run that found the problem (soft-arm ar25
seed 4, no new LLM calls): both mistagged hypotheses now correctly
tagged. One still expired 8-of-8 unmet — **the fix removes the
crowding-out, not the underlying routing failure**; why routing fails so
badly when the precondition's target coincides with the tested relation's
own entity remains open. Also fixed: the test suite's own baseline
`GOOD` fixture turned out to have a self-referential precondition,
undetected until this check existed. 257 tests.

**A third reviewer-C pass** (`docs/expert-reviews/reviewer_c_09_14_2026c.md`)
landed after the above. Its central new content is the ablation ladder
A/B/C/D (§14): case D, replaying the exact hypotheses a real run
generated against a deterministic agent, is a cleaner generation-vs-
integration separation than the four live matched-seed sweeps above,
which confound the two (a filtered hypothesis changes the pool, which
changes the trajectory, which changes what the next *live* call even
sees). Run the same session it landed, no new sweeps: `replay_ablation.
replay()` gained `drop_sources` (strips hypotheses by tagged source after
parsing, generation untouched); `scripts/replay_ablation_grounded.py`
replayed all 50 (game, seed) cells from the soft arm twice — identically,
then with `llm_ungrounded`/`llm_selfref` dropped. Result: 44/50 cells
unchanged, effect almost entirely on `ar25` (mean 0.0761 -> 0.0470 over
all 50, wins 2/losses 4/ties 44, p=0.6875 — not significant at n=6, but
same direction as the strict-reject sweep, now without that sweep's
resampling confound). Full table and inference in `docs/history.md`
(2026-09-15, "A third reviewer-C pass, and Case D actually run") and
`research/hypotheses/H002_llm_hypothesis_proposer.md`.

**H005 opened** (`research/hypotheses/H005_compositional_preconditions.md`)
after a reframing of the Case-D result was narrowed down to the one piece
with a direct measured gap behind it (the cd82 oracle proved the
precondition schema can't express a two-factor rule) rather than the two
pieces already tried once each under other names (`H003`'s predictor,
`H004`'s rival hypotheses). **Stage 1 done**: `precondition` now accepts
either its existing single-pair shape or a tuple of pairs (conjunctive),
via `hypothesis.conditions_of()`/`describe_conditions()`; enumerator and
LLM parser untouched; `_precondition_met` conjoins a new
`_condition_met`; routing goes to the first unmet condition in order.
261/261 tests pass (257 pre-existing unchanged, 4 new covering the
conjunction). Full detail in `docs/history.md` (2026-09-15, "H005:
conjunctive preconditions, Stage 1 built and green") and the H005 doc.

**H005 Stage 3 — done, same session.** `scripts/h005_cd82_oracle.py`
injected a hand-built two-condition oracle directly (no LLM, no parser)
into a live cd82 game on seeds 1-3: `H001`'s exact first condition
(adjacent, side −x, to the template) plus a second — adjacency to one
swatch entity — as the cheapest live test of the conjunction, not a
claim that it correctly encodes "the swatch is selected". Mechanism
confirmed: the conjunction gated correctly (seeds 2, 3 each found exactly
one step where both conditions held, scored as real evidence; every
other step correctly filed as precondition-unmet), and the two-condition
precondition survived logging intact. The anticipated gap confirmed too:
the conjunction was almost never jointly satisfiable, because the
template and the swatch sit in different screen regions — direct
evidence "adjacent to the swatch" is the wrong proxy for "the swatch is
selected," which is a persistent state, not a spatial fact. Seed 1
reached level 1 (cd82's first this session) but not attributably to the
oracle (it expired unmet there too) — read as early-trajectory
perturbation, the same sensitivity documented all session on the LLM
side, not a result. Full table and detail in `docs/history.md`
(2026-09-15, "H005 Stage 3: the cd82 oracle, two conditions, live") and
the H005 doc.

**Order for the next session.**
1. **A second condition kind for H005** — the concrete next step Stage 3
   points at: a persistent entity-state check ("is `#S`'s current
   descriptor equal to its 'selected' appearance", answerable the same
   falsifiable way `kinds.py`'s equal-descriptor view already works)
   rather than another adjacency. Smaller, more specific follow-up than
   a bigger sweep of what Stage 1 already built — and the representation
   piece cd82 actually needs, per Stage 3's own result.
2. **Trace `ar25` seeds 3, 9, 10 directly** — the Case-D result says the
   dropped hypotheses' *targets* carry real value on this game
   specifically, but not *which* one or *why*. Read those three traces to
   turn "the target carries value" from an inference into a mechanism,
   the same way the self-referential finding was traced rather than left
   as an aggregate percentage. Free — no new LLM calls, same recorded data.
3. **Matched-seed sweep the self-referential fix** — same discipline as
   every other fix this session: a mechanism verified for free is not
   the same claim as a score effect, and the lever-grounding fix's own
   result (mechanism correct, score flat-to-negative) is the reason not
   to assume this one is different without checking.
4. **Investigate why routing fails on a self-referential target** — the
   deeper mechanical question the tag doesn't answer. Is the approach
   pixel/offset genuinely unstable when the routing target is also one
   of the two entities the tested action is acting on (a moving-target
   problem), or is there an actual bug in `_route_to`/`_precondition_met`
   worth fixing directly? Needs tracing one real case step by step.
5. **A complementary prompt-side fix**: explain "moves under every action
   alike" in the schema/instructions explicitly, to reduce how often the
   model makes lever claims like this in the first place. Needs live
   model calls to verify (unlike everything above, which was free).
6. Deferred (per the review's own sequencing, unchanged): the full
   event-sourcing rewrite of `recap.py`/logging beyond the LLM-trace piece
   already done; LLM call-purpose framing (model-discovery vs.
   hypothesis-discrimination vs. experiment-selection prompts);
   call-budget-by-information-gain.

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
- **Recap UI as one cognition story** (`docs/expert-reviews/UI_instruction.md`,
  2026-09-15) — a left-to-right see → infer → believe → predict → decide →
  happen → update layout replacing the 3-column dashboard. Shelved until
  the latent-state layer (`H006`–`H008`) exists: the panel it would centre on
  (belief → prediction → update) is the thing being built, and a UI
  redesigned around the old belief would be redone.
