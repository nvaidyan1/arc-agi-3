# History

Notable findings — successes and failures both — as terse structured
entries: **hypothesis / motivation / observation / inference**, plus
context where it's load-bearing. Doubles as planning context for later
sessions, and feeds an eventual writeup where the ARC Prize Paper Prize
and Solution Writeup criteria explicitly reward transparency. Keep the
unflattering samples; a log of only what worked is worse than none.

Entries are append-only apart from restructuring passes. Built with
Claude Code throughout; direction, strategy calls, and all commits and
submissions are the user's.

---

## 2026-09-13 — Setup

**Context.** Python 3.12 + venv + framework clone + project-local Kaggle
token. `origin` → `nvaidyan1/arc-agi-3`, arcprize starter kept as
`upstream`. Standing rules set by the user: no autonomous commits or
pushes, and Kaggle submissions (5/day cap) are user-only.

## 2026-09-13 — Environment facts

**Motivation.** Ground truth on the action/observation space before
designing anything.

**Observation** (read from `arcengine`/`arc_agi`, not assumed): 8 actions
— `RESET`, `ACTION1-5`/`ACTION7` simple, `ACTION6` complex with `x,y` in
0-63. Frames are lists of 64×64 layers, values 0-15. `GameState` has
exactly 4 values. Each frame reports `available_actions`, and games expose
only a *subset* (ls20 `[1,2,3,4]`, vc33 `[6]`).

**Inference.** Acting outside `available_actions` is pure waste — became
the first agent change (affordance filtering).

## 2026-09-13 — Council review of a proposed 4-layer architecture

**Hypothesis reviewed.** Object extractor (connected components) → world
model → A*/planner → verification harness, with an LLM fallback for
transition-rule synthesis.

**Motivation.** Distil a large design into the single most economic next
step rather than build it wholesale.

**Observation.** Three independent review passes (feasibility, ROI,
generalization-fit), each blind to the others. Feasibility found two
factual errors: `GameAction.UNDO` doesn't exist, and `scipy` isn't
installed or transitively available. Generalization-fit rated
connected-component objects, a single "controllable agent" assumption,
and convex-hull frontier probing all RISKY; LLM rule-synthesis
CONDITIONAL (acceptable only as a per-episode hypothesis, never cached
across games).

**Inference.** Each RISKY item bakes in a representational assumption
(objects are colour blobs / there is one avatar / space is navigable)
that a hidden game can violate — and when violated it produces a *wrong
ontology* corrupting every layer above it, which is worse than being
merely unhelpful. Deferred; picked a cell-level diff signal instead. Full
list in `plan.md` "On hold".

## 2026-09-13 — Frame-diff signal, and a framework gap

**Hypothesis.** Keeping *which* cells changed (not just whether any did)
gives enough signal to target the click action usefully.

**Observation.** Works — click targeting converged from scattershot to a
few live regions within ~2 steps on vc33. Separately:
`FrameData.action_input` is **never populated** locally
(`_convert_raw_frame_data()` omits it), so "which action produced this
frame" cannot be read back from the frame.

**Inference.** The agent must track its own last action/click. The same
gap makes the framework's built-in `record=True` recorder near-useless
for debugging (logs raw frames, not decisions) — wrote per-step JSON
logging into `play_local.py` instead.

## 2026-09-13 — Go-Explore trajectory replay: built and reverted

**Hypothesis.** Remember the longest-surviving attempt's action sequence,
replay it after RESET to return to that frontier, then explore onward.

**Observation.** Attempts plateaued at a fixed per-game length (ls20 130,
dc22 128, m0r0 151, sc25 57, vc33 50) across up to 15 resets, never
improving. Engine source: `lose()` fires on *resource exhaustion* (vc33
step budget, ls20 lives counter), and `GAME_OVER` routes to
`level_reset()` — not `full_reset()` — which **preserves `_score` /
`levels_completed` and keeps the current level**.

**Inference.** Premise invalid. The engine already checkpoints level
progress, so there is no frontier to return to; and a saved trajectory is
by construction a *losing* run, so replaying it spends the new attempt's
finite budget to arrive back at a losing position. Net-harmful, not
merely redundant. Reverted.

**Kept.** `levels_completed` is the only true progress signal;
per-attempt budget is the binding constraint.

## 2026-09-13 — Layered reward signal

**Hypothesis.** Weight actions by `levels_completed` (what's scored),
*added to* rather than replacing frame-change — the user's correction,
since the dense signal is what keeps the policy learning during the long
stretches where nothing is scored.

**Observation.** No run has ever produced a level-up, so the path was
untestable by play. Verified with synthetic `FrameData`: credit lands on
the right action, survives RESET while per-attempt stats wipe, and shifts
selection to ~74% (residual ~26% = the epsilon floor).

**Inference.** Correct but **inert** until a first level completion
exists. Scaffolding that makes a first success compound — not itself a
score improvement.

## 2026-09-13 — Contingency awareness as the representation layer

**Motivation.** User asked whether we can distinguish
pixel > object > thing I control > thing I affect, explicitly *without*
importing a 3D/spatial connotation that would pigeonhole every task.
Answer at the time: no — we had pixels and change, and discarded the rest.

**Hypothesis.** Define each layer by **contingency, not appearance**.
(This rescues the object concept the council rejected: what was rejected
was the *visual* definition — colour blobs — not the idea.) Object =
cells that change together (Gestalt common fate); controlled = change
immediately contingent on action; affected = conditional/indirect;
environment = independent of action.

**Observation.** Instrumented `ACTION6` across three games — three
distinct click semantics, zero game-specific code: ft09 94 local/0 remote,
diff exactly 38 every time (paints at the cursor); vc33 0 local/117
remote, 1-2 cells; tn36 0 local/118 remote, exactly 1. Also ~50% of clicks
were exact repeats, and 8×8 region habituation over-generalized
(blacklisting 64 cells after 3 duds).

**Inference.** Replaced region habituation with per-cell click memory.
More significantly, `acts_locally=False` exposed a category error: when
clicks change something *elsewhere*, the changed cells are the effect, not
the cause, so targeting them is wrong. Targeting is now conditional on the
signature — repeat waste fell from ~50% to 1-3%.

**Context.** User noted, from having actually *played* the games, that the
2D object-movement analogy is necessary for a subset of them. Agreed, with
sequencing as the point: spatial structure as a *derived destination*, not
an assumed prior.

## 2026-09-13 — Object and control layers via translation detection

**Hypothesis.** Test the specific question "is this change one coloured
shape displaced by a single offset?" — stronger than generic co-change
grouping, and yields two layers at once (the object, plus the action→effect
map when displacement correlates with an action). Critically a *test*: it
returns nothing when it doesn't hold.

**Observation.** ls20: a complete noise-free directional map —
`ACTION1(0,-5) ACTION2(0,+5) ACTION3(-5,0) ACTION4(+5,0)`, 122
observations, zero disagreement; the 5px stride also reveals the game's
logical cell size. Fires on **14 of 25 games**. Silent on vc33/ft09/tn36.
Correctly *declined* to learn m0r0's ACTION1 (15× one way, 13× the other).

**Inference.** The 2D object reading is real for most of this set and was
*derived* rather than imposed; silence on the rest is the graceful-failure
property working, not a gap. Refusal on ambiguous actions suggests some
are context-dependent — which a state-agnostic model cannot represent.

**Retraction.** One vc33 run returned `levels_completed=1`, the first
non-zero progress all session, and was nearly reported as a win.
Re-running vc33 six times: **0/6**. A fluke; the accompanying
`ACTION6 → (-4,0)` mapping appeared in only 1 of 6 runs. Score remains 0.0
everywhere.

**Caveat, untuned.** `MIN_MOVE_OBSERVATIONS = 3` is low enough that short
runs lock in premature mappings (at 40 steps dc22 "learned" both ACTION3
and ACTION4 as `(2,0)`). Acceptable while diagnostic; must rise before
anything plans on it.

**Status.** Representation layers reproducible; their behavioural use
(exploring the controlled shape's derived position space) is principled
but **unproven** — no demonstrated score effect.

## 2026-09-13 — Change-space audit, and the sub-frame question settled

**Hypothesis.** Before building prediction-error detection on top of
translation, check whether the change vocabulary covers what games do.

**Observation.** Classifying 533 transitions across 8 games: three
categories explain 99%, but translation — the only one implemented — is
just **31%**. Recolour-in-place is **53%** (vc33 97%), cardinality-change
(grow/appear/vanish) **16%** (ft09 98%). `available_actions` never
changed in any run, so it carries no signal.

**Inference.** We model roughly a third of what happens. Recolour and
cardinality are the missing categories; cardinality likely also renders
the step/lives counters, so reading it could yield budget-awareness.

---

**Sub-frame question (raised as a blocker, now settled).**
`FrameData.frame` is *not* spatial layers: `base_game.py` loops
`step()` + render until an action completes, so it is the animation
sub-frames of that action. `frame[-1]` is the settled state, `frame[0]`
mid-animation. All signals had been comparing `frame[0]` to `frame[0]`.

*Method error worth recording.* The first comparison (36% vs 25%
translations) was run as two **separate agent runs** with different random
trajectories, and the difference attributed to the index. Invalid: a
paired test on identical frames shows **86% of steps (694/808) have
`frame[0]` identical to `frame[-1]`** — only 9.5% of steps animate at
all — so most of that gap was run-to-run variance.

*Decisive evidence.* On tu93, which animates on 61/101 steps, move-map
consistency is **21-29% with `frame[0]` versus 43-64% with `frame[-1]`**,
and only `frame[-1]` yields a coherent map (8px orthogonal stride). On
barely-animated ls20 both recover the same clean map.

**Inference.** `frame[-1]` is correct — semantically (it is the state the
action produced) and empirically (better where animation exists, neutral
where it doesn't). Switched all three read sites.

**Retraction (second of the session).** The post-fix sweep reported
aggregate 0.19 with a level-up on sp80. sp80 re-run 8 times: **0/8**.
Three further full sweeps: 0.0, 0.0, 0.0. The 0.19 was entirely that one
fluke. No score improvement from this change.

**Inference worth keeping.** Two spontaneous level-ups have now occurred
(vc33, sp80) across many runs. Levels are evidently *reachable* by chance,
just at a very low rate — the problem is hit-rate, not reachability.

**Design note.** `_detect_translation` requires the *entire* diff to be
one shape's displacement. Finding a translation *component* instead would
be more robust and is likely a precondition for recolour and cardinality
detection to coexist with it.

## 2026-09-13 — Blocked-move detection (the environment layer)

**Hypothesis.** An action with a learned move that fails to produce it
means something resists us there. Keyed by (position, action), that yields
an obstacle map — and the map's *shape* validates itself: real obstacles
fail at specific positions, a wrong move-map fails roughly uniformly.

**Motivation.** Ordering question — harden `_detect_translation` first, or
build this first? Settled with data rather than preference: across 731
predicted-move steps, the strictness flaw (whole-diff test missing a real
move because something else changed too) accounts for only **4%**, i.e.
6% of "blocked" verdicts would be false. Tolerable, so robustness was
*not* the blocker and this went first. Same measurement showed the
definition of blocked had to be "expected translation didn't occur"
(16% silent + 44% something-changed-but-no-move), not "nothing changed" —
on ls20 the silent case is 0/120, so silence-only would have missed all
of it.

**Observation.** Determinism check: "mixed" outcomes for the same
(position, action) are near-zero — ls20 2/114, dc22 2/173, ka59/wa30/
sk48/g50t exactly 0 — and each action is blocked at a *minority* of
positions (ls20 ACTION1 at 7 of 30). Effect of avoiding known blocks,
averaged over 4 runs per condition:

| game | blocked-move rate | distinct positions |
|---|---|---|
| ls20 | 62.9% → 20.7% | 8.2 → 12.8 (+55%) |
| ka59 | 43.4% → 21.2% | 22.2 → 34.8 (+56%) |
| wa30 | 58.8% → 31.9% | 61.0 → 86.2 (+41%) |
| sk48 | 33.0% → 17.7% | 72.8 → 92.5 (+27%) |
| dc22 | 35.7% → 27.2% | 16.0 → 16.0 (0%) |

**Inference.** The determinism plus position-specificity says these are
real obstacles, not model error — the validation the map was designed to
provide. Avoiding them is a large, consistent efficiency win on the axis
that matters, since death is resource exhaustion. Residual ~20% blocked
rate is the unavoidable cost of discovering each wall once.

**But: three full sweeps after the change give 0.0, 0.0, 0.0.** Better
exploration efficiency did not convert into a single level completion.
Stated plainly to avoid a third false positive: the mechanism works, the
score did not move.

**Lead for next.** The 44% bucket — blocked moves that nonetheless change
something — is unexamined. Whatever changes when we fail to move is either
the step/lives counter (→ budget awareness) or an interaction with the
thing we bumped into (→ the "thing I affect" layer). Both are wanted, and
the data is already being collected.

## 2026-09-13 — What changes on a blocked move: it's a rendered budget meter

**Hypothesis.** The 44% of failed moves that still change something is
either an interaction with whatever we bumped, or a HUD counter.
Discriminator: a counter changes in a *fixed screen location* regardless
of where we are; an interaction tracks our position.

**Observation.** On ls20 every blocked-move diff is exactly 2 cells, always
the transition colour 11→3, with centroid y-spread **0.0** while our own
position varies in y by 7.7 — same row every time, advancing along x.
dc22 the same (1 cell, `0→3`, y-spread 0.0). wa30 is the opposite: only
3/40 recolour-like, transitions `14→0` and `0→14` in equal numbers — an
interaction, not a meter. Reading colour 11's count over time on ls20
gives a clean sawtooth: `84 82 80 … 2 0 0` then back to 84.

**Inference.** Both of the user's candidates are right, for different
games. ls20/dc22-style games render a resource meter; wa30-style changes
are interactions. ls20's budget is 84 units at 2/action = 42 actions per
attempt, and a blocked move costs the same 2 — so blocked moves aren't
merely wasted, they're *paid for*, which raises the value of the obstacle
map built in the previous step.

**Built.** A meter detector keyed on the sawtooth: a colour that declines
steadily and jumps back to a recurring maximum. Deliberately not "declines
monotonically" — dc22 has a colour that moves all run because the player
is filling the board, which is progress, not budget, and it is correctly
rejected (it never refills).

**Three bugs found by testing, each a wrong assumption:**
1. Refills were keyed to *our* RESET. ls20 refills internally per life
   with no GAME_OVER, so no start value was ever recorded. Fixed by
   detecting the jump in the series itself.
2. A colour at count 0 vanishes from the histogram, so the refill that
   followed looked like a first sighting and was skipped. Fixed by
   retaining zeros.
3. Two false positives at scale: a 3-cell colour oscillating, and a large
   background that depletes as the board fills. Added a minimum size and
   a requirement that a real budget actually empties (min ≤ 25% of full).

Also lowered the evidence bar from two refills to one: two needs ~250
actions, but `MAX_ACTIONS` is 80, so the meter would never have been found
under realistic conditions. At 80 steps it now correctly finds ls20 (84),
vc33 (64), ft09 (64) and rejects dc22/bp35. Fires on ~9 of 25 games,
stable across runs.

**Negative result worth keeping.** Measured cost per action against the
meter: ls20 is 1.94-2.00 for *every* action (spread 0.02); vc33/ft09 have
only one action type. The budget is a flat step counter, so cost-aware
action selection — the obvious use — would gain essentially nothing. Not
built. The corollary matters: since every step costs the same, efficiency
can only come from making steps *better*, never cheaper.

**Status.** Meter exposed as a diagnostic (`budget_fraction`, surfaced in
reasoning/logs), not driving behaviour, because the data says the natural
behavioural use is worthless. Sweeps: 0.047 then 0.0 — the former is
another one-off sp80 level-up of the kind retracted twice already, not an
improvement.

## 2026-09-13 — "Thing I affect": residual change after subtracting self

**Hypothesis.** Subtract what our own movement explains (and the budget
meter, which ticks on its own), and whatever change is left is something
else we acted upon — the "thing I affect" layer, with no assumption about
what that something is.

**Observation / two bugs, both mine.** First pass reported ls20 as 118/120
steps being "interactions", which is absurd for a plain movement game.
Causes: (1) it used `_detect_translation`, which fails on ~69% of steps
because it demands the *whole* diff be one translation — so our own
movement went unexplained and every step looked like an interaction;
fixed by falling back to the offset `learned_moves` already knows for that
action. (2) The meter exclusion tested only the new cell value, but
depletion recolours cells *away* from the meter colour (11→3), so
depleting cells slipped through; fixed by testing both sides.

**Second, more interesting flaw.** Even fixed, tn36 sat at 97% and ft09 at
77% — non-discriminating. Reason is conceptual, not incidental: on games
with no move map there is no "self" to subtract, so residual ≡ any change,
which silently double-counts the existing frame-change signal. Gated the
layer on having a move map, which is the correct statement of the idea —
**"thing I affect" is only definable once "thing I control" is known.**

**Result.** Games with a move map: 26-57% interaction rate (ls20 26%,
wa30 40%, dc22 44%, ka59 57%, cn04 55%) — discriminating rather than
constant. Games without (vc33, ft09, tn36): ~0%, correctly silent. Wired
in as a third reward tier at weight 3, between frame-change (1) and
level-up (20): affecting the world is better evidence of progress than
merely moving, but it is not the score.

**Status.** Two sweeps after the change: 0.0, 0.0. No score movement.

**Context — Kaggle packaging constraint (checked, not acted on).**
`build_notebook.py` reads *only* `agent/my_agent.py` and ships it via one
`%%writefile` + one `cp`. Worse, the agent executes only under
`KAGGLE_IS_COMPETITION_RERUN`, so Phase A "Save & Run All" never imports
it. Splitting into modules today would therefore pass `make play-local`,
pass `make submit`, report `complete` — and fail only in Phase B, after
spending one of five daily submissions. Two viable routes if we refactor:
ship each file with its own `%%writefile`+`cp` (testable locally by
replicating the framework's `templates/` import path), or have the builder
inline the modules into one file at build time (submission path stays
byte-identical). Not attempted without explicit approval.

## 2026-09-13 — Council on the goal problem; action cap raised; sub-goal (vanish) signal

**Council brief.** Three independent reviews (signal inventory grounded in
engine source; sparse-reward strategy; a skeptic told to attack the
premise). Two convened findings reframed the question before they even
reported: `MAX_ACTIONS=80` is self-imposed (framework demo guard; no
server/gateway cap exists anywhere; Playback uses 1,000,000), and scoring
is `((baseline/actions_taken)**2)*100` when completed, **0.0** when not,
counted **per level** (`scorecard.py:481`).

**Skeptic's verdict.** Do not build a goal; we are budget-starved and
cannot conclude "no goal" when the sample size for "ever reached one" is
statistically zero. Correct on the facts.

**Experiment (budget ladder, and a harness bug).** First run was void:
`play_local.py` did `min(MAX_ACTIONS, --max-steps)`, so the flag could
only *lower* the budget and all three "budget" runs silently executed at
80. Fixed to assign. Corrected ladder:

| budget | repA | repB |
|---|---|---|
| 80 | 0 games, **0.0** | 0 games, **0.0** |
| 400 | 2 games, 0.0048 | 1 game, **0.0444** |
| 1600 | 6 games, 0.0061 | 4 games, 0.0114 |

**Correction worth recording.** The first (unreplicated) ladder showed 80
scoring 0.190, and an inference was drawn from it that score moves
*against* budget. Replication refutes that: 80 scores exactly 0.0 in both
replicates, and the 0.190 was itself a single fluke completion. Raising
the cap moves us from reliably-zero to reliably-nonzero. Conclusion drawn
from one run of a stochastic process — the same error retracted twice
earlier today.

**Inference.** More budget buys completions and real (if tiny) score, so
we were genuinely budget-starved. But magnitudes stay ~0.004-0.044 against
a per-level maximum of 100, and the human baselines explain why:
vc33 level 1 takes a human **7 actions**, ls20 22, sp80 39, dc22 59
(found in `environment_files/*/metadata.json`; note the live API redacts
`baseline_actions`, so this is for offline evaluation only — using it in
the agent would be per-game memorisation and unavailable on hidden games).
Stumbling in at ~400 actions scores `(7/400)^2*100 = 0.03`. Note repB at
400: ONE completing game scored 0.044, more than SIX completing games at
1600 (0.0061) — one fast completion is worth many slow ones. So the
efficiency work the skeptic called "decoration" is in fact the dominant
term, quadratically, once completions exist.

**Signal inventory — the useful part.** No API field reports partial
progress (confirmed absent). But sub-goal completion *mutates pixels*:
ls20 deletes matched sprites, vc33 hides them. Win conditions across all
24 games reduce to two shapes — coordinate/pixel equality ("reach or match
a position") or a flag tested in `step()`. Also `win_levels` == total level
count, known from frame 0, so `levels_completed/win_levels` is free coarse
progress.

**Built.** (1) `MAX_ACTIONS` 80 -> 400. (2) A vanish detector: a whole
object disappearing, as the visible proxy for sub-goal progress, weighted
8 (above interaction 3, below level-up 20). Discriminator is online and
needs no lookahead — occlusion by our own shape can hide at most
`_controlled_size` cells, so a larger drop cannot be self-occlusion.
Validated: fires 0-1.5% of steps, and correctly returns **zero** on ka59,
whose 244 one-cell drops are churn rather than deletions.

**Status: no score improvement.** Two sweeps at 400: one produced 2
completions (0.0023), the other none (0.0). Completions remain flukish and
slow. The vanish signal has the same bootstrap problem as level-ups — real
but too rare (0-1.5%) to shape behaviour.

**Sharpened next step.** The gap is now quantified: we need level 1 in
~7-59 actions; undirected search takes ~400. That is 10-50x, which reward
shaping alone will not close — it needs planning toward a target. The
council originally deferred A*/pathfinding as premature "with no object
identity or goal signal to search over". Those prerequisites now exist
(object, move map, obstacle map, and win conditions that are mostly
"reach a position"), so the condition they set for revisiting it is met.
