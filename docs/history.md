# History

A dated log of what's been done and why, including how AI assistance was
used at each step. Kept honestly, not retroactively cleaned up — the ARC
Prize Foundation's Paper Prize track and the Grand Prize's "Solution
Writeup" criteria reward transparent, genuine methodological contribution
over an unexplained leaderboard number, so however AI is used in building
this, it should show up here plainly.

Entries are append-only; append a new one per work session, don't edit old
entries except to fix factual errors.

---

## 2026-09-13 — Environment setup and repo bootstrap

Worked with Claude Code (Sonnet 5) to go from a fresh clone to a working
local dev loop. Claude: installed Python 3.12 via Homebrew (missing on this
machine), ran `make setup` (venv, deps, framework clone), created the
project-local `.kaggle/access_token` file from a token the user provided
directly in chat, and verified `make verify-local` passes. Claude also
renamed the original `origin` remote to `upstream` and added a new `origin`
pointing at a GitHub repo the user created and asked to be used
(`github.com/nvaidyan1/arc-agi-3`), then pushed. The user set explicit
ground rules up front: never run `make submit` / touch Kaggle submissions
autonomously (5-per-day budget, user-only), and never commit without being
asked.

## 2026-09-13 — Game mechanics orientation

User asked introductory questions about the action/observation space
(action count, grid size, pixel depth) after watching the random-baseline
agent play. Claude answered by reading the actual `arcengine`/`arc_agi`
source (not guessing or relying on prior knowledge) via a research
sub-agent, confirming: 8 actions (`RESET`, `ACTION1`-`5`, `ACTION7` simple,
`ACTION6` complex with `x,y` in `0-63`), 64×64 frames, values 0-15 (16-color
palette), and the 4-value `GameState` enum. This was folded into
`README.md` under "Game mechanics reference" (an earlier draft lived in a
separate `docs/game-mechanics.md`, moved into the README per the user's
call that a separate file would go stale before submission).

## 2026-09-13 — First non-random agent strategy

User chose, from four options Claude proposed (generic exploration
heuristic / per-game hardcoding / model-based-learning / minimal
non-zero-score patch), the **generic exploration heuristic** direction —
explicitly to match the competition's stated generalization goal rather
than overfitting to the ~25 locally-visible games. Claude implemented it in
`agent/my_agent.py`:
- filter candidate actions to `latest_frame.available_actions` (discovered
  mid-implementation that games declare a legal-action subset, e.g. `ls20`
  → `[1,2,3,4]`, `vc33` → `[6]` — this wasn't known going in),
- an epsilon-greedy bandit over "does this action change the frame",
- salience-based coordinate picking for the complex click action.

Verified locally: ran against all 25 games with `make play-local
--max-steps 30`, no exceptions, `ls20` confirmed to only ever pick from
`ACTION1`-`4` as expected. Score remains 0.0 (expected — exploration alone
doesn't solve levels). Not committed yet; user reviews and commits
explicitly.

Also added `RENDER=terminal` / `RENDER=human` / `RENDER=terminal-fast`
support to `scripts/play_local.py` and the `Makefile` — the underlying
`arc_agi` package already shipped these renderers but the local script only
exposed one of them.

## 2026-09-13 — Council review of a brainstormed architecture, then frame-diff + logging

User brought a substantial brainstormed 4-layer architecture (Object
Extractor / Perception → Epistemic World Model → Planner/Search Arbiter →
Verification Harness — connected-component object segmentation, a
"Controllable_Agent" tracker, convex-hull frontier probing, A* search over
an inferred simulator, LLM-based transition-rule synthesis as fallback)
and asked for it to be checked and distilled into "the economic next
action — a single small step in a vector that attains max increase in
accuracy," rather than implemented wholesale.

Claude ran three independent review passes in parallel (as background
sub-agents, each given only the proposal and repo context, not each
other's output) before synthesizing a recommendation:
1. **Technical feasibility** — checked the proposal's concrete claims
   against the actual installed packages and framework source. Found two
   factual errors (`GameAction.UNDO` doesn't exist — 8 real members:
   `RESET`, `ACTION1`-`7`; `scipy` isn't installed or transitively
   available) and confirmed no object-tracking state existed yet in
   `agent/my_agent.py` to extend.
2. **ROI/incrementalism** — ranked which single piece would most plausibly
   help with least effort/risk given the agent is still exploration-only
   at 0.0 score. Flagged full object extraction and the search/synthesis
   layer as premature, and recommended a minimal cell-level diff signal
   instead (see below).
3. **Generalization-fit** — evaluated purely on "does this transfer to
   hidden games the competition actually scores on, or does it overfit to
   assumptions about the ~25 visible games." Rated connected-component
   objects, a single controllable-agent assumption, and convex-hull
   frontier probing all RISKY (each bakes in a representational
   assumption — contiguous-color objects, one avatar, 2D navigability —
   that a hidden game could simply not have, in which case the technique
   doesn't just underperform, it actively misleads downstream logic).
   Rated LLM-synthesized transition rules CONDITIONAL: fine only as a
   per-episode, verified/discarded hypothesis, never cached or reused
   across games (that crosses into the per-game memorization the
   competition's stated eval philosophy is explicitly designed against).

Full reasoning and the "on hold" list (nothing rejected permanently, just
sequenced behind having an actual object/goal signal) is in `plan.md`.

Chosen next action, implemented in `agent/my_agent.py`: a **frame-diff
signal** — track which `(x, y)` cells changed between frames (not just a
boolean), use recently-changed cells to target the coordinate-click
action ahead of the previous "non-background color" heuristic, and track
a per-region (8x8 coarse buckets) dead-click counter so regions that
absorb clicks with zero effect get avoided. No new dependencies, no
object model, no per-game logic. While implementing, found and fixed a
real bug in the initial draft: `FrameData.action_input` — which the plan
assumed could be read to recover "what action produced this frame" — is
never actually populated by the local framework's
`_convert_raw_frame_data()` (always left at its default, `RESET`/empty
data); switched to the agent tracking its own last action/click as
instance state instead. Verified via a traced run against `vc33`
(ACTION6-only game): click targeting visibly converges from
"non-background cell" to "recently active + non-background cell" within
2 steps, and clusters into a handful of live regions. Full 25-game sweep
still passes with no exceptions; score remains 0.0 as expected (this is
an exploration-quality improvement, not a solving capability).

Also added per-step JSON logging to `scripts/play_local.py`
(`recordings/<run-timestamp>/<game_id>.jsonl`, one line per step with
action/reasoning/prev-diff-count), on by default, after the user noted
that watching `RENDER=terminal` live is impractical for actual debugging.
Deliberately did not use the framework's built-in `record=True` option —
discovered it has the same `action_input`-never-populated gap, so it logs
raw frames but not which action was taken or why, which is the part
actually needed for debugging agent decisions.

## 2026-09-13 — Naming convention, checklist plan, and a Go-Explore build that was reverted

Three process changes at the user's request: (a) name features after
existing cognitive-science/ML/RL concepts rather than ad-hoc descriptions,
so the work stays legible as history grows and is easier to describe to
others — established `glossary.md` and retroactively named what already
existed (affordance / contingency detection / salience map / habituation /
epsilon-greedy); (b) restructured `plan.md` into a checklist; (c) the user
raised, and deliberately shelved, a deeper idea of restructuring variables
into a cognition-mapped namespace (`memory.last_action`), judging it a net
loss against plain readable Python — recorded in `plan.md` under "Shelved
ideas" rather than acted on.

The user also asked that "compact symbolic modeling" — converting raw
observations into a compact domain-specific symbolic state representation
and planning over that rather than over raw pixels — inform the planning
philosophy going forward. Treated as directionally useful (and see below:
the session's own findings independently point the same way).

Then: implemented Go-Explore trajectory replay (remember the
longest-surviving attempt's action sequence, replay it after a RESET to
return to that frontier, then explore onward), tested it, and **reverted
it the same session**. The sequence of findings:
1. First test showed replay reproducing the previous attempt's death
   exactly — the saved trajectory ended *with* the fatal action, so
   deterministic replay deterministically re-died. Fixed by trimming the
   last action.
2. Retest showed attempts plateauing at exactly 130 actions on ls20 over
   15 resets, never improving. Checked four more games: same pattern at
   different fixed values (vc33 50, sc25 57, dc22 128, m0r0 151).
3. That pattern prompted reading the engine and game sources rather than
   assuming skill-limited deaths. Found that `lose()` is triggered by
   *resource exhaustion* (vc33: `current_steps` budget; ls20: a lives
   counter), and — decisively — that `GAME_OVER` routes to
   `level_reset()`, not `full_reset()`, which **preserves `_score` /
   `levels_completed` and keeps the current level**.

So the engine already checkpoints level progress for free (no frontier to
return to), and since a saved trajectory is by construction a losing run,
replaying it spends the new attempt's entire finite budget to arrive back
at a losing position — net-harmful, not merely redundant. Removed it.
Kept: the finding that `levels_completed` is the only real progress signal
and per-attempt budget is the binding constraint, which reframes the next
step and points toward representing state compactly enough to make
budget-aware, state-dependent decisions, rather than the current
state-agnostic per-action statistics.

Noting the reversal plainly because a log that only records things that
worked would misrepresent how the work actually went.

## 2026-09-13 — Layered reward signal (frame-change + level-ups)

Following the Go-Explore reversal, the obvious correction was to make the
policy aware of `levels_completed` — the signal that actually matches the
competition score. The user pushed back on framing it as a replacement:
frame-change is a good signal and shouldn't be removed. That was right,
and it's why the implementation layers rather than swaps. Frame-change is
the *dense* signal (fires most steps, so the policy keeps learning during
the long stretches where nothing is being scored); level-ups are *sparse*
but weighted 20x so they dominate whenever they fire.

One deliberate asymmetry: level-up credit persists across RESETs while
frame-change stats stay per-attempt. Level-ups are far too rare to afford
forgetting, and which action makes progress is a property of the game
rather than of a single attempt — whereas frame-change stats can go stale
when a fresh level behaves differently.

Testing note worth recording: no run has ever produced a level-up, so this
entire code path would have shipped untested if verified only by playing.
Tested it instead with synthetic `FrameData` — confirming credit lands on
the correct action, is logged loudly rather than buried, survives a RESET
while frame-change stats correctly wipe, and shifts selection to ~74% for
the rewarded action (the residual ~26% matching the epsilon-greedy floor).
Full 25-game sweep then re-run clean; score still 0.0.

Honest status: this change is *inert* until something completes a level
for the first time. It is scaffolding, not a score improvement — it makes
a first success compound instead of being forgotten, but does not by
itself make that success more likely. Recorded plainly rather than
presented as progress.

## 2026-09-13 — Contingency awareness as the representation layer

The user asked a representation-side question the memory-side work had
been sidestepping: do we have any mechanism to distinguish
pixel > object > the thing I control > the thing I affect? Explicitly
*without* importing a 3D/spatial connotation that would pigeonhole every
task.

Honest answer at the time: no. We had pixels and change-detection, and we
were discarding the rest — `_recent_diffs` kept a 5-step window, flattened
into an undifferentiated bag of cells, with no record of which action
caused which diff. Per action, everything collapsed to one scalar.

The framing adopted: **define each layer by contingency, not by
appearance.** This matters because the earlier generalization review
rejected connected-component objects as RISKY — but it rejected the
*visual* definition ("object = contiguous same-colored blob"), not the
concept. A statistical definition carries no spatial commitment:
- **object** = cells that reliably change together (Gestalt *common
  fate* — grouping by shared change, not shared appearance)
- **thing I control** = a cluster whose change is immediate and reliably
  contingent on the action chosen
- **thing I affect** = a cluster that changes conditionally/indirectly
- **environment** = changes independent of action, or never changes

This fails gracefully in a way the blob-ontology does not: if nothing
turns out contingent, you learn "nothing here is directly controllable,"
which is true information rather than a corrupted ontology poisoning
every downstream layer.

The user made an important correction worth recording: having actually
*played* two of the games, they have direct evidence that for a subset of
games the 2D object-movement analogy is not merely useful but necessary,
and that the emergent analogy of object must eventually be brought about.
Agreed, with the sequencing being the point — spatial structure as a
*derived destination* rather than an assumed prior. For spatially
organized games, cells that change together will turn out to be
contiguous and to translate coherently; the 2D reading then emerges from
data, available where it's real without being imposed where it isn't.

First concrete step, measured before being coded. Instrumented ACTION6
across three games:
- **ft09**: 94 local / 0 remote, diff size exactly 38 every time → click
  paints a 38-cell object at the cursor
- **vc33**: 0 local / 117 remote, diff 1-2 cells
- **tn36**: 0 local / 118 remote, diff exactly 1 every time

Three completely different click semantics, derived with zero
game-specific code. The measurement also exposed waste: ~50% of clicks
were exact repeats of already-clicked cells, against a finite budget; and
the 8x8 region habituation was over-generalizing (blacklisting 64 cells
after 3 duds could rule out the one productive cell in a block).

Changes: replaced coarse region habituation with per-cell click memory
(prefer never-clicked cells, skip cells that absorbed a click with no
effect), and recorded the local/remote signature as `acts_locally`,
persisted across RESETs since it describes the game rather than the
attempt.

Then the representation did its first real work. Per-cell memory alone
barely helped vc33/tn36 (53%->45%, 52%->48%) because every click there
produces *some* effect, so habituation never fires, and the
"recently-active" tier is a couple of cells that are all already clicked.
`acts_locally=False` explains why that heuristic was wrong there: when
clicking changes something *elsewhere*, the cells that changed are the
effect, not the cause, so aiming at them is a category error. Made
targeting conditional on the signature — cover new ground when clicks act
at a distance. Repeat rate then fell to 1% / 3% / 0%.

Status: this is a real efficiency win (budget no longer burned on
duplicate clicks) but **not** a score win — still 0.0, no level completed
anywhere. One honest tradeoff: vc33's total cells-changed dropped (~150
to 23) under broader coverage, so "less repetition" is not automatically
"more effect" there. Recorded rather than glossed.

## 2026-09-13 — Object and control layers, derived from translation detection

Next feature off the representation roadmap: the object layer. Design
choice that paid off — rather than grouping co-changing cells generically,
test the stronger and more specific hypothesis that a frame change is
*one coloured shape displaced by a single offset*. That yields two
roadmap layers at once: an object (the shape) and, when the displacement
correlates with an action, the thing we control plus what that action
does to it. Crucially it is a *test*, not an assumption: when the change
isn't a translation, `_detect_translation` returns None and nothing
downstream is polluted.

Results, all derived from pixels with no game-specific code:
- **ls20**: a complete, noise-free directional map — ACTION1 (0,-5),
  ACTION2 (0,+5), ACTION3 (-5,0), ACTION4 (+5,0), 122 observations with
  zero disagreement. The 5px stride also reveals the game's logical cell
  size.
- **Fires on 14 of 25 games.** That is direct evidence for the user's
  earlier point (made from having actually played the games) that the 2D
  object-movement analogy is necessary for a substantial subset — and it
  arrived as an emergent finding rather than a prior.
- **Silent on vc33 / ft09 / tn36** — the graceful-failure property
  working as intended, not a gap. ft09's 38-cell change is a recolour,
  not a move.
- **Refuses to learn ambiguous actions**: m0r0 ACTION1 was 15x (0,5) vs
  13x (0,-5), and the majority rule correctly declined rather than
  inventing a mapping. Likely a context-dependent action that a
  state-agnostic model cannot pin down — which is itself informative.

Then made the representation behavioural rather than merely
observational: accumulate the controlled shape's displacement from
observed translations, and prefer actions predicted to land it somewhere
this attempt hasn't been. This is count-based exploration over a *derived
symbolic state* (position) instead of over raw frames — the compact
symbolic modelling idea, reached bottom-up.

**A retraction worth recording.** One vc33 run returned
`levels_completed=1` — the first non-zero progress all session — and it
was nearly reported as a win. Re-running vc33 six times gave 0/6. It was
a fluke, not a result, and the `ACTION6 -> (-4,0)` mapping that
accompanied it was itself only learned in 1 of 6 runs. Score remains 0.0
everywhere. Recording this because the temptation to report the lucky run
was real, and a log that captures only the flattering sample is worse
than useless for a writeup.

Known caveat, untuned: MIN_MOVE_OBSERVATIONS=3 is low enough that short
runs can lock in a premature mapping (at 40 steps, dc22 learned both
ACTION3 and ACTION4 as (2,0), which is likely under-sampling rather than
truth). Fine while this is diagnostic; needs raising before anything
plans on it.

Status: the representation layers are real and reproducible; the
behavioural use of them is principled but **unproven** — it has not been
shown to improve score.
