# Plan

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
- [ ] **thing I affect** — cluster that changes conditionally/indirectly.
      Partially visible already (`acts_locally`, and vc33 occasionally
      learning that a click displaces something by (-4,0)), but not yet
      separated from "thing I control" as its own concept.
- [ ] **environment** — changes independent of action, or never changes

- [ ] **Budget awareness** — death is resource exhaustion, so the finite
      per-attempt budget is the binding constraint and the policy is
      currently blind to it. Not yet started.
- [ ] **First level-up** — nothing has ever completed a level, so the
      sparse signal above is inert until something does. This is the real
      blocker on a non-zero score; the layered reward is the scaffolding
      that makes any first success compound rather than be forgotten.

## Tooling

- [x] `RENDER=terminal` / `RENDER=human` / `RENDER=terminal-fast` in
      `scripts/play_local.py` / `Makefile`.
- [x] Per-step JSON logging (`recordings/<run-timestamp>/<game_id>.jsonl`),
      on by default in `play_local.py`.

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
- [ ] **Local transition simulator + A\* search** — premature: nothing to
      simulate or search over without object identity or a goal signal
      first.
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
