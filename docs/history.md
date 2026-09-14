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

## 2026-09-13 — Region-of-interest screening: the substrate exists, is clustered, and is switched off where it matters most

**Hypothesis.** Incentive salience (attend to places where something
happened that was neither us nor the budget) is only worth building if
those places actually *cluster*. If they are diffuse, a map of them
carries no more information than "somewhere on the board".

**Motivation.** The agent answers "what do I control" and "what resists
me" but nothing answers "where should I go / what should I make". Framing
correction from the user, which changed the design: a region of interest
is not always a *destination*. In a copy/mirror task (replicate the heart
on the left onto the right) the region on the left is a *specification*,
not a place to travel to, and the obstacle map contributes nothing. So
ROI serves two families and the router is the optional half, not the
mandatory one. Confirmed in code: `_blocked_moves` is gated on
`learned_moves`, so the 9 games where no move map forms already get
nothing from the obstacle layer.

**Method.** Subclassed `MyAgent` and overrode `_residual_cells` and
`_track_meter` to keep the *positions* they already compute and discard.
25 games x 400 actions. Clark-Evans nearest-neighbour index R (observed
mean NN distance / expected under complete spatial randomness; R<1
clustered, 1 random) plus half-mass (distinct cells carrying 50% of hits).

**Observation 1 — clustered, strongly.** R < 1 on every game with data.
Navigational family (move map forms, n=16) mean R = 0.52; constructive
family (no move map, n=9) mean R = 0.39; vanish sites R ~ 0.45. The games
we actually score on are extreme: **ls20 29 cells, sp80 28, sk48 8**
carry half the residual mass, out of 4096. Not universal — re86 0.94,
cn04 0.90, bp35 0.96 are indistinguishable from random. 18 of 21 clustered.

**Observation 2 — the substrate is structurally disabled on exactly the
family the user described.** `_residual_cells` is gated on
`observed_offset is not None`: it must know its own movement before it
can compute "not me". On **ft09, sb26, cd82, tn36 the residual layer
fires on 0.0% of steps** — not rarely, never, across 400 actions. Family
rates: navigational 30.9% of steps and a median 176 distinct cells;
constructive 7.2% and a median 13. With no movement there is no self to
subtract, so the whole ROI machinery cannot run in the copy/match family.

**Observation 3 — template/workspace separation is real and large.**
Share of static non-background cells lying *outside* the bounding box of
everything that ever changed: constructive family mean **52%** (su15,
sb26, cd82 at 100%); navigational mean 27% but with **sp80 at 93%**,
tr87 66%, ls20 64%, dc22 60%. Constructive games average 926 static vs
332 dynamic cells — mostly immutable structure around a small workspace.
The agent never attends to the static part. Caveat: "static" means "never
changed during our episode", which partly reflects our own coverage;
trustworthy for the click games, where `_pick_coordinate` samples
board-wide, weaker for the movement games.

**Observation 4 (unplanned) — a documented figure was wrong.** The
council entry above records the vanish detector as firing on "0-1.5% of
steps". True where it was measured (ls20 2.3%, dc22 0.8%, ka59 0.8%) but
not in general: **ft09 78.6%, s5i5 46.7%, cd82 44.5%, cn04 28.0%, bp35
13.5%**. This probe requires a matching colour-drop, so those are lower
bounds. On those games `VANISH_WEIGHT = 8.0` is being applied to ordinary
churn rather than to a rare sub-goal. The original claim generalised from
an unrepresentative subset — the same sampling error as the earlier
retractions, in a new place.

**Inference.** Build the incentive-salience map; the clustering justifies
it. But the gate must change, and the reason is clean: the
`observed_offset is not None` condition exists because residual-as-a-
*reward* would double-count frame-change if "me" were not subtracted. A
*map* does not double-count anything. So the gate is correct for the
reward term and wrong for the spatial term — keep it on one, drop it on
the other, and the constructive family gets an ROI map for the first
time. Fix or scope `VANISH_WEIGHT` first; layering attention on top of a
signal that fires 78% of the time would inherit the noise.

## 2026-09-13 — Incentive-salience map built; vanish detector's false-positive fixed

**Hypothesis.** Two fixes motivated by the screening above. (1) The vanish
detector's documented rate (0-1.5%) was wrong in general (up to 78.6%) —
it was missing a discriminator: a colour dropping because something else
*recoloured into it* is not a deletion, only a drop the *background*
absorbs is. (2) The residual-cells map should be split from the
residual-cells reward: keep the `observed_offset is not None` gate on the
reward (needed to avoid double-counting frame-change), drop it on the
map (a map cannot double-count anything, and the gate was making the
map read exactly 0.0% on the constructive family — ft09/sb26/cd82/tn36).

**Motivation.** User: cues in the environment matter independent of
whether we can walk to them; a copy/mirror task's "region of interest" is
a specification (what to reproduce), not a destination, and the current
obstacle-detector "does not really help" there. Confirmed in code before
building anything: `_blocked_moves` requires `learned_moves`, so it
already contributes nothing on those 9 games — the gap was real, not
hypothetical.

**Built.**
1. `_track_meter`'s vanish loop now also requires the drop be absorbed by
   the background (`background_gain = counts[bg] - previous[bg]`,
   `pending_vanish = min(total_drop, background_gain)`), so a same-step
   recolour between two non-background colours no longer counts.
2. `_residual_cells` is now called unconditionally in `choose_action`
   (previously `[] if observed_offset is None`). The existing
   `_action_interactions` / `INTERACTION_WEIGHT` reward path stays gated
   on `observed_offset is not None`, unchanged.
3. New `_interest: dict[(x,y), float]` (incentive salience — Berridge &
   Robinson 1998). Bumped at residual cells every step (weight 1),
   further at the same cells when `_pending_vanish` fires (weight 4,
   approximate — see code comment on why exact vanish positions aren't
   isolated), and at `residual or diff_cells` on a level-up (weight 15,
   falling back to the raw diff so a level-up reached by pure movement
   with no separate residual still gets credit). Decays 0.98/step,
   pruned below 0.05, cleared on level change like the obstacle map.
4. Wired into `_pick_coordinate` as the new top-priority tier
   (`_top_interest_cells`, top 5 by value) — the only path available to
   the constructive family, since ACTION6 is the sole coordinate action.
   Movement games get the map built but not yet consumed (needs the
   router — separate, larger, not part of this change).

**Observation.** Re-ran `scripts/roi_probe.py` (moved from a scratch
script to make this reproducible) on ft09 alone: residual firing rate
**0.0% -> 95.1%** of steps post-fix, 19 cells carrying half the mass,
Clark-Evans R=0.31 (clustered). Traced a full play-local run's per-step
log: interest evidence appears by step 16 ("learned region of interest
(unclicked)"); by step ~390 selection has narrowed to
"learned region of interest (revisit)" almost exclusively — the map is
sticky once it finds a productive spot, since ft09's clicks never
habituate (every click there changes 38 cells, so `_cell_is_spent` never
trips). `EXPLORATION_EPSILON` still forces 25% uniform-random coverage
regardless. One 25-game smoke sweep at 400 actions after both changes:
0.0316, inside the existing 0.0006-0.1496 range (single run, not a
replication — recorded as a sanity check, not evidence of a shift).

Separately, verified the vanish fix directly against the production code
(tapping `_pending_vanish` itself, not the probe's independent
re-derivation): **ft09 78.6% -> 0.0%, s5i5 46.7% -> 0.5%** — both now
inside the originally-claimed range. **cd82 44.5% -> 21.9%**: improved,
not fixed. Read as a second, distinct false-positive family, same shape
as the budget-meter's known one (dc22's fill-progress colour): cd82's
core mechanic plausibly *is* frequent recolour-to-background
(consumption/fill), which the new discriminator cannot tell apart from a
real deletion since both are, correctly, "absorbed by the background".
Not chased further — one-game residual, flagged in `plan.md`.

**Inference.** The map is real, populated, clustered, and now reaches the
one game family it was built for. It is not yet expected to move the
score: it improves *where* the click game family looks, not *how it gets
there* in the movement family, which is where our actual completions
come from (sp80, ls20, lp85). The router (`plan.md`, "planning toward a
target") is what would let this pay off on those games.

## 2026-09-13 — Router built; caught and fixed a real regression before it shipped

**Hypothesis.** The interest map is inert without something that acts on
it in the movement family — build a router (BFS over displacement space,
`learned_moves` as edges, `_blocked_moves` as removed edges) that plans a
multi-step path to the best `_interest` cell and executes it.

**Motivation.** User, closing the loop on the prior session's work: "the
map can only be used if we react upon it to complete the levels." Router
was the acknowledged missing half from the region-of-interest screening.

**Built.** `self._anchor`: absolute board position of the controlled
shape, re-derived from ground truth on every translation (not purely
accumulated, so it can't silently drift) — needed because `_interest` is
keyed in absolute pixels while `learned_moves`/`_blocked_moves` are keyed
relative to the attempt's start; `_anchor - _displacement` recovers the
shared origin to translate between the two. `_plan_route()`: bounded BFS
(cap 4000 node expansions — cheap given the board's natural size) from
the current displacement toward the target, falling back to the closest
reachable node (Chebyshev distance) if the exact target isn't on the move
map's stride lattice, rather than refusing to move. Plan execution
inserted as a new tier in `choose_action`, validated online: dropped if
the next queued action becomes illegal, or if `_displacement` doesn't
match what the plan expected (a previously-unknown obstacle was just
discovered, so the rest of the plan was computed for positions never
reached). Verified offline first (6 synthetic unit tests: direct path,
detour around a position-keyed obstacle, best-effort on an off-lattice
target, and the three "no signal yet" None cases) before trusting it on
live games.

**Observation — a real regression, caught before commit.** First live
placement put the router directly below the frontier (`novel_moves`)
tier and above the reward-weighted fallback, reasoning that it only
"replaces the weakest option." That reasoning was wrong: the fallback
branch is not weak, it is the *only* channel carrying `LEVEL_UP_WEIGHT`
(20x) and `VANISH_WEIGHT` (8x) — the sole mechanism that had ever produced
a real completion. The router has something to say almost as soon as
`_interest` is non-empty (fast — often within a few dozen steps) and
`novel_moves` empties out with normal use, so it was preempting that
fallback branch on ~30% of steps on ls20 in isolation. First full 25-game
sweep post-integration: **every single game scored levels=0**, including
sp80, which completed 4 of 5 runs before this change — replicated on a
second full sweep, also all-zero. Not a hypothesis at that point; a
measured, reproduced blackout.

**Fix.** Gate router use on `not (self._action_level_ups or
self._action_vanishes)` — route only while nothing has ever earned real
credit; the moment any action proves itself, that evidence must win the
weighted branch every time, and an in-progress plan is abandoned the
instant it does. This is not a tuning knob, it's a priority *inversion*
fix: directed search toward a correlational cue should never outrank a
causally-confirmed action.

**Re-verification, replicated.** sp80 alone, 15 runs post-fix: 9/15
complete (60%), against the flat-zero result immediately before the fix
and a documented 4/5 (80%) baseline from before the router existed at
all — noisy but recovered, not still broken. Three full 25-game sweeps
post-fix: 0.0110, 0.0, 0.0072 (mean ~0.0061) against the five-sweep
pre-router baseline of 0.0006-0.1496 (mean ~0.063). The blackout is
clearly gone (multiple non-zero sweeps, sp80/lp85/cn04 completing
again), but this post-fix mean sits noticeably below the pre-router one
on only 3 samples against 5, and this exact quantity has already shown a
250x span (0.0006 to 0.1496) across its own baseline — not enough to
call a further, smaller regression either way. Left open rather than
either claimed fixed or flagged as still-broken.

**Inference.** The router is built, individually unit-tested, and no
longer catastrophically regresses score. Its *net* effect on score is
still genuinely unmeasured — would need several more replicated sweeps
to separate from this environment's inherent variance, and that's a
reasonable next check before or shortly after committing, not a reason
to hold the commit.

## 2026-09-13 — Architecture review: the ontology question, and a principle

**Hypothesis reviewed.** An 18-point critique argued the agent is "still
somewhat event-driven and heuristic" and should maintain an explicit
latent world model: a `WorldState` schema (objects/relations/environment
with `walls`, `targets`, `resources`, `hazards`, `inventory`, `timer`), a
fixed pixel taxonomy (agent/target/obstacle/effect/resource/decoration),
cross-game action priors, Bayesian confidence over the hard thresholds,
causal graphs from intervention, and a hypothesis ledger driving
information-gain action selection.

**Motivation.** Enough of it was right that it deserved a real triage
rather than either wholesale adoption or reflexive defence.

**Observation — triage.** Seven items (generalised correspondence,
conditional effects, Bayesian confidence, state-space frontier, causal
graph, reversibility, invariants) were low-risk extensions of what
exists. Three were not: the fixed `WorldState` schema and the fixed pixel
taxonomy reintroduce precisely what the earlier council review rejected —
an *imposed* ontology, where a hidden game either leaves slots empty or
gets force-fit into them. The cross-game action prior ("ACTION1 usually
means left") is refuted by our own data: m0r0's ACTION1 splits 15/13 with
no majority, and the hidden eval set has no reason to share our 25 games'
control conventions.

**Observation — the exchange converged.** The schema and taxonomy were
retracted, and the distinction that came out of it is sharper than the
original proposal: **semantic** ontology (agent/target/obstacle) encodes
what games *are*; **relational** ontology
(entity/attribute/relation/event/transition/hypothesis) only supplies
vocabulary for what *happens*. The first pigeonholes; the second doesn't.

**Inference.** Adopted as a governing principle, now at the top of both
`plan.md` and `my_agent.py`: *no semantic slots without evidence — every
interpretation comes from a falsifiable test and may return `None`.*
Worth being clear that this is not a new direction but a *name* for the
one pattern that has survived contact with real games here: translation
detection returning None, the meter requiring a sawtooth, `acts_locally`
staying None until evidence. Corollary: game type is an output, never an
architectural input — no `if maze: use_bfs()`; BFS runs because a move
map and obstacle map were discovered.

**Also inferred.** The council was *not* convened. It exists to arbitrate
disagreement about risk, and the disagreement dissolved in conversation —
the three high-risk items were withdrawn by the proposer. Convening it
anyway would have been process for its own sake.

## 2026-09-13 — Correspondence lens: recolour-in-place and cardinality-change

**Hypothesis.** Translation explains only 31% of transitions (533
classified across 8 games); recolour-in-place is 53% and
cardinality-change 16%. Give the other two a lens and ~69% of transitions
stop being anonymous diff cells.

**Motivation.** Longest-standing open item on the checklist, and the
cheapest of the triage's "build" row — purely additive, no new ontology.

**Built.** `_classify_change` returns `(recolours, cardinality)` or None.
Discriminator is the background: a change *touching* it creates or
destroys content (cardinality, signed), a change between two
non-background colours relabels something already present (recolour) —
the same rule that fixed the vanish false-positive. Also extracted
`_lost_and_gained`, which four call sites were duplicating. Wired in
**recording-only**: the router taught us that a new signal plus a
decision-logic change in one pass makes a regression unattributable.

**Observation 1 — a correction, found by measuring.** The first version
derived background per frame as `max(counts)`. I asserted in the
docstring that this mis-filed ft09, whose clicks paint 38 cells a time.
That was wrong, and inspecting real frames showed why: ft09's background
is a stable colour 5, and its changes are 9→8 (468 cells) and 8→9 (432)
— two *foreground* colours toggling, which is recolour-in-place under any
sensible reading. The manual study's "cardinality" label is the looser
one (per-colour totals do move). The false claim was removed from the
code rather than left to harden.

**Observation 2 — the fix was right, on a different game.** Measuring
where per-frame argmax actually disagrees with the level's initial mode:
24 of 25 games stable, but **dc22 disagrees on 37.4% of steps**, argmax
oscillating between colours 3 and 4. That is precisely the game whose
mechanic is filling the board in, so the fill outvotes the canvas.
Background is now the level's initial mode; dc22's classification moved
exactly as predicted (recolour 38%→19%, cardinality 23%→0%).

**Observation 3 — the predicted payoff did not arrive.** The checklist
claimed cardinality "likely also renders the step/lives counters, so
detecting it may give budget-awareness". It does not. It finds **drains**
— monotonic, never returning (dc22's fill, cd82's consumption) — not
**budgets**, which refill each attempt. Only 2 of 25 games showed a large
drain `meter_colour` missed, and cd82's is the already-known consumption
mechanic. The meter detector is *correct* to reject them: the refill test
is the entire distinction, and the two imply opposite behaviour (a budget
near zero means conserve, a drain near zero means you are nearly done).

**Inference.** Two of three change categories now have lenses, and the
census runs clean across 25 games. But the signal is currently **inert** —
nothing consumes it — and the census percentages are *not* comparable to
the manual 31/53/16 (ours count "category present in this step",
non-exclusive, summing past 100%; the study assigned one dominant
category per transition). The open question is whether category should
differentiate interest weight — a cardinality loss resembles sub-goal
progress, a foreground toggle may be a mere indicator — which is the
natural next consumer and a behaviour change to make on its own.

**Regression.** Two full sweeps after the refactor: 0.0136 and 0.0569
(the latter the best since the router landed), sp80 4/6 on spot-check.
The `_lost_and_gained` extraction was separately verified equivalent to
the inline loops on 200 random grids.

## 2026-09-13 — Vanish signal rebuilt on cardinality: better signal, no score change

**Hypothesis.** Replace the whole-board-histogram vanish detector with
`_classify_change`'s per-cell cardinality loss. Predicted chain: a more
precise sub-goal signal trips the router's gate less spuriously, so the
router (our only directed-behaviour mechanism) stays available longer,
so completions get faster.

**Built.** `_pending_vanish` now comes from per-cell content->canvas
transitions rather than colour histograms, and `_classify_change` returns
`lost_cells` so the salience bump lands on the cells that actually
emptied instead of smearing across every residual cell. Self-occlusion is
now structurally impossible rather than threshold-guarded: our own shape
sliding over something is content-over-content, which lands in
`recolours`, not in cardinality. The `max(_controlled_size,
MIN_VANISH_CELLS)` floor is kept, and is exactly sized so our own
vacated trail can never clear it.

**Observation 1 — signal quality improved, and is now measured
everywhere.** Vanish fires on **2.1% of steps overall**, back in line
with the 0-1.5% the detector was originally documented at.

**Observation 2 — two games stay high, and the detector is right.**
cd82 **22.2%** (was 21.9%, essentially unchanged) and bp35 **22.7%**.
The per-cell rebuild did not move them because there is nothing to fix:
those games genuinely destroy content on a fifth of all steps. An earlier
entry assumed cd82's rate was detector noise — that assumption was wrong,
and this is what refutes it.

**Observation 3 — the predicted chain broke at step two.** Router
engagement is **3.0% of steps overall**, concentrated almost entirely in
ls20 (35.4%) and tu93 (24.4%); most games are flat 0%. Making the gate
more accurate did not make the router run more, because the gate was
never the binding constraint.

**Observation 4 — no score change.** Four sweeps: 0.0, 0.0396, 0.0023,
0.0 (mean ~0.0105) against ~0.0061 for the three before it. Both sit
inside a metric that has ranged 0.0 to 0.1496 across its own baseline.
No effect detectable at this sample size.

**Inference.** The signal got better and the score did not, which
localises the bottleneck rather than being a dead end. The router is
nearly vestigial *by construction*: it sits below the frontier tier, and
`_visited_displacements` resets every attempt, so the frontier almost
never runs dry and the router tier is rarely reached at all. On top of
that ~9 games never form a move map, so routing is structurally
impossible there. The limiting factor on directed behaviour is the
router's **placement**, not the quality of the signal gating it — which
is a different fix from the one just made, and the next thing to test.

## 2026-09-13 — Router competes with frontier: score recovers, hypothesis still refuted

**Hypothesis.** The router fires on only 3.0% of steps because it sits
permanently *below* the frontier tier, which rarely runs dry. Let it
compete — win when its target is well evidenced — and directed behaviour
should increase, and completions get faster.

**Built.** Plan creation no longer gated on the frontier being exhausted.
A `strong_route` wins over the frontier when the best interest cell
carries at least `INTEREST_VANISH_WEIGHT` — deliberately an existing
weight, not a new tuned constant: "something meaningful happened there",
not "something changed there". Below that bar the frontier still wins.
The `proven_action_exists` gate is untouched and still outranks
everything, preserving the earlier regression fix. Neither the epsilon
nor frontier branch clears the plan any more — the drift check handles
invalidation, and correctly *keeps* the plan when their move was blocked.

**Observation 1 — the stated mechanism barely moved.** Router engagement
went **3.0% -> 3.6%** of steps. It spread across more games (cn04
0.2->11.2%, g50t 0->8.2%, sc25 0->5.5%, tr87 0->2.5%) but the aggregate
is essentially unchanged. Placement was *not* the binding constraint.
The real ones, in order: 9 of 25 games never form a move map so routing
is structurally impossible (frontier is 0% there too); any vanish or
level-up permanently disables routing via `proven_action_exists`; and
`strong_route` needs accumulated interest >= 4.0, which is rare.

**Observation 2 — score recovered anyway.** Nine sweeps: 0.1316, 0,
0.0183, 0.0244, 0.1485, 0, 0, 0.1369, 0 — mean **0.0511**, 5/9 non-zero,
three sweeps at 0.13-0.15.

| config | mean | max | non-zero |
|---|---|---|---|
| pre-router baseline (n=5) | 0.0630 | 0.1496 | 5/5 |
| router, strict order (n=3) | 0.0061 | 0.0110 | 2/3 |
| + vanish rework, strict (n=4) | 0.0105 | 0.0396 | 2/4 |
| + router competes (n=9) | 0.0511 | 0.1485 | 5/9 |

**Inference, and it is unflattering.** Against the config immediately
before it, this is ~5x better. Against the **pre-router baseline** — the
honest reference point — it is *not* an improvement: nominally lower mean
(0.0511 vs 0.0630) and clearly worse consistency (5/9 vs 5/5 non-zero),
with comparable maxima. So the whole line of work since that baseline
(interest map, router, correspondence lens, vanish rework) has recovered
from a regression it introduced rather than produced a net gain.

Also important: the score recovery **cannot be attributed to the stated
mechanism**, because router engagement moved only 0.6pp. Something else
in the change, or noise, is responsible. Claiming the causal story here
would repeat the ft09 error from earlier today.

**What this actually establishes.** We have not tested "directed
navigation as a strategy" — we have tested directed navigation on 3.6% of
decisions. The interesting question is no longer placement but whether
the router can become the *primary* mode where a move map exists, which
means confronting the two real constraints: `proven_action_exists`
disabling it outright, and the 9 games where no move map ever forms.

## 2026-09-13 — Scoping the routing gate: the speed/reliability trade, and why routing loses it

**Hypothesis.** `proven_action_exists` blocks routing on *any* level-up
or vanish, ever, globally, permanently. Vanishes fire on 22% of steps on
cd82/bp35, so a single one kills directed navigation for a whole run —
disproportionate for what is only a *proxy* for sub-goal progress.
Scoping the gate to level-ups alone should free the router where it is
being vetoed on weak evidence.

**Observation 1 — the mechanism worked exactly as predicted.** Router
engagement **3.6% -> 5.8%** overall, with the gains precisely on the
high-vanish games that had been vetoed: re86 0 -> **43.1%**, cn04 11.2 ->
**38.7%**, bp35 0 -> **9.7%**. Unchanged at 0% on the nine games that
never form a move map, as expected.

**Observation 2 — completions got more reliable.** 7 of 8 sweeps
non-zero, against 5 of 9 before.

**Observation 3 — and the score got worse.** Mean **0.0511 -> 0.0164**,
max **0.1485 -> 0.0639**.

| config | mean | max | non-zero | router% |
|---|---|---|---|---|
| pre-router baseline (n=5) | 0.0630 | 0.1496 | 5/5 | n/a |
| router competes, vanish gates (n=9) | 0.0511 | 0.1485 | 5/9 | 3.6% |
| vanish dropped from gate (n=8) | 0.0164 | 0.0639 | 7/8 | 5.8% |

**Inference — the most useful negative result so far.** The relationship
across all three configs is monotonic: *more routing buys reliability and
costs score*. That is not a contradiction, it is the scoring function
working as designed. Score is `(baseline_actions/actions_taken)**2 * 100`,
so for sp80 (baseline 39) a completion in 100 actions scores 15.2 and one
in 400 scores 0.95 — **a 4x speed difference is a 16x score difference**.
A mechanism that completes more often but more slowly is actively
harmful.

And the reason routing is slow is now plain: the interest map marks
**where things happened**, not **where the goal is**. Walking deliberately
to a correlational hotspot spends real actions on a destination with no
established link to the win condition, while the high scores in every
config came from *stumbling onto the goal early*. Directed navigation
toward a non-goal is worse than undirected search that might get lucky.

**Action.** Reverted — vanishes stay in the gate. Recorded rather than
silently dropped, because the finding is worth more than the change: it
says the bottleneck was never routing *capacity*, and adding more of it
without a real goal signal will keep making the score worse. The
pre-router baseline (0.0630) remains the best-measured configuration.

## 2026-09-13 — Reorganised into layers; packaging made provable; a latent crash found

**Motivation.** 1,328 lines in one file, and navigating it had become the
bottleneck on doing anything else. Deferred previously because splitting
was judged UNSAFE — `build_notebook.py` shipped exactly one file, and a
bad import would pass every local check and fail only during the Kaggle
rerun, costing one of five daily submissions.

**Hypothesis.** The layer stack we already documented is a real
decomposition, so the code can mirror it without inventing structure; and
the deployment risk is removable rather than inherent.

**Built.** Seven modules, each answering one question: `perception` (what
happened), `control` (what can I make happen), `constraints` (what limits
it), `attention` (what's worth investigating), `navigation` (how to get
there), `constants`, and `my_agent` (what to do next). Names are
deliberately **epistemic rather than semantic** — `objects.py`/`goals.py`
would smuggle in an ontology the governing principle forbids.

Two boundaries defended on purpose:
  * `perception` returns evidence, never decisions — it can say something
    happened, not what it means.
  * `navigation` takes a target, never chooses one. The pre-refactor
    router reached into the interest map for its own destination, which
    quietly made navigation the privileged paradigm: routing happened
    because it *could*, not because the situation called for it.

**Packaging, now proven rather than hoped.** The notebook emits one
`%%writefile` cell per module; a `sys.path` bootstrap makes sibling
imports resolve both locally (loaded standalone by `play_local.py`) and
on Kaggle (imported as `agents.templates.my_agent`) — neither plain
absolute nor relative imports work in both contexts.
`scripts/verify_packaging.py` rebuilds the rerun layout **from the
notebook's own bytes**, rewrites `agents/__init__.py` as the notebook
does, and imports MyAgent in a clean subprocess. It is a prerequisite of
`make submit`. An attached-dataset layout was considered and rejected:
two artifacts to keep in sync (drift runs stale code *silently*) and no
way to verify locally, since `/kaggle/input` paths don't exist here.

**Observation — a latent crash, surfaced by the move.** Two games raised
`KeyError(ACTION4)`. Cause: `learned_moves` is recomputed every step, so
an action whose offsets stop meeting the majority threshold silently
*drops out* of the map — and a queued route still holding that action
then failed its offset lookup. Pre-existing; the restructure only made it
frequent enough to see. Fixed by invalidating a route whose next action
is no longer a known move.

**Observation — behavioural parity.** After the fix: 0 errors across 25
games, move maps form on **16/25 (exactly matching pre-refactor)**,
vanish 2.3% vs 2.1%, router 3.3% vs 3.6%. Score across 14 sweeps: mean
0.0268, max 0.0958, **13/14 non-zero** against pre-refactor 0.0511 / 5-of-9.
The means overlap heavily given this metric's documented 0.0-0.15 range
within a single configuration, and consistency is better; the structural
measurements are what actually certify the refactor, not the score.

**Also built.** 47 unit tests (`make test`), the first in the repo. They
assert the **refusals** as carefully as the successes — translation
returning None on a recolour, the move map declining m0r0's 15/13
coin-flip, the meter rejecting dc22's monotonic fill — because a layer
that concludes confidently from ambiguous evidence is worse than one that
stays silent. One test failure was the *test* being wrong, and it
corrected an inherited docstring: `detect_translation` is defeated by a
stray cell of the **moving shape's own colour**, not by unrelated change
elsewhere, since correspondence is per colour.

**Inference.** No behaviour was intended to change and none measurably
did. The value is that the next experiment is cheap to write, the layer
boundaries make "where does this belong?" answerable, and a packaging
mistake can no longer cost a submission.

## 2026-09-13 — Council on the goal problem; durable sweep summaries; the scorer re-read, and the speed premise refuted

**Council brief.** Five independent advisors (contrarian, first-principles,
expansionist, outsider, executor), then an anonymised peer-review round, on:
what is the next most economic experiment, given that more routing and more
perception both cost score. Convergent findings: the measurement channel is
narrower than the effect sizes; realizable score lives in the first ~100
actions; and the no-semantic-slots principle has never been *priced* against
the scoring function. All five reviewers independently ranked the executor's
answer strongest — fix the instrument before buying more sweeps.

A reviewer also flagged the load-bearing assumption nobody had checked:
is `actions_taken` per-level or cumulative? That turned out to be the whole
entry.

**Observation 1 — the record was gone.** ~50 sweeps have been run. `recordings/`
is gitignored and only **four runs** survive; exactly **one** is a full 25-game
sweep. Every configuration comparison in the tables above was made against
numbers that no longer exist. Across all 29 surviving logs there are **three**
level completions, at actions **175, 185, 342**.

**Observation 2 — truncate-and-retry is dead.** `arc_agi/scorecard.py`
`_calculate_score` (~line 476) computes `level_actions = actions_at_level -
prev_actions`: a level's cost is the cumulative counter at its completion minus
the counter at the previous completion. `agents/agent.py:87` never resets that
counter — not on RESET, not on level change. So actions spent failing *within*
a level are charged to that level. Six 60-action attempts charge level 1 with
360. The council's convergent "short budget, retry often" recommendation is
refuted before it was built. The three surviving completions agree: none
arrived under 120 actions, so a 40/60/80/120 cap would have scored zero on
every completion this project has ever recorded.

**Observation 3 — the scorer is a level-index-weighted average, over *all*
levels.** `EnvironmentScoreCalculator.to_score` computes
`sum(level_score_i * i) / sum(i)`, where the denominator runs over every level
in the game including ones never reached. vc33 and ls20 have **7 levels** each
(full baseline vectors are now visible in the summaries: vc33
`[7,18,44,61,131,34,152]`, ls20 `[22,123,73,84,96,192,186]` — previously only
the level-1 figure was recorded). Weights 1..7 sum to 28, so level 1 is worth
**1/28 of the environment**. Per-level score is capped at 115, not 100.

**Inference — the speed premise was wrong, and it has been steering everything.**
Measured directly against the real scorer, on vc33:

| | score |
|---|---|
| L1 in 185 actions (our best ever) | 0.0051 |
| L1 in 46 actions (**4x faster**) | 0.0827 |
| L1 in 23 actions (**8x faster**) | 0.3308 |
| L1 in 7 actions (human parity, **26x faster**) | 3.5714 |
| L1-L2, each still at 185 actions | 0.0727 |
| L1-L3, each still at 185 actions | 0.6788 |
| L1-L4, each still at 185 actions | 2.2320 |

Reaching level 2 *at our current sluggish pace* is worth as much as becoming
4x faster at level 1. Reaching level 3 beats an 8x speedup by 2x. Reaching
level 4 approaches human-parity-on-level-1. `plan.md` has said since the budget
ladder that "closing that 10-50x [speed gap] is the whole remaining problem";
that reads only one term of a two-term objective. **Depth dominates speed**,
and depth is the term never measured, because the agent has cleared level 2
approximately never.

This also re-reads the router result. "More routing buys reliability and costs
score" was inferred from a metric in which only level-1 speed could move.
Reliability — completing more often — is the *precondition* for depth. The
finding stands as measured but its interpretation was too strong.

**Built.** `scripts/sweep_summary.py` + wiring in `play_local.py`: every sweep
now writes `results/sweeps/<run-id>.json` — committed, a few KB — carrying the
scorer's per-level actions/scores/baselines, the action index of each
completion, and a git fingerprint so a score is attributable to the code that
produced it. Level tracking is deliberately independent of `--log`: the JSONL
is a debugging convenience, the completion index is the result.
`scripts/backfill_summaries.py` recovered the four surviving runs (marked
`"backfilled": true`, no scorer half — it is gone). 14 unit tests, asserting
the degradation paths as carefully as the successes, since a summariser that
can throw would take a 25-game sweep down with it. `make clean` deliberately
spares `results/`.

**Status.** No agent behaviour changed; this entry is instrument work and a
re-reading. The next experiment is now a different question than the one the
council was asked: not "how do we find the goal" but "what stops us reaching
level 2", which is measurable for the first time.

## 2026-09-13 — Variance floor measured (n=30); every past configuration comparison dissolves; budget buys breadth, not depth

**Motivation.** With summaries in place, the two questions that had been
deferred as too expensive were finally cheap. A 25-game sweep at 400 actions
takes **29 seconds**. The "measurement tax" this project has organised itself
around since the budget ladder — deferring experiments, reasoning from n=3 —
was never real.

### Variance floor

**Hypothesis.** Configuration comparisons made at n=3-14 are underpowered.

**Observation.** 30 sweeps at one unchanged commit:

| n | mean | median | sd | min | max | zeros |
|---|---|---|---|---|---|---|
| 30 | 0.0307 | 0.0131 | 0.0490 | 0.0000 | 0.1940 | 3/30 |

Severely right-skewed: the top sweep is **6.3x the mean**, and one sp80 run
cleared level 1 in **9 actions** against a human baseline of 39. Score is
manufactured by rare lucky completions, so the mean is the wrong statistic.

Bootstrapped 95% interval for the reported mean, configuration unchanged:

| k sweeps | interval | width |
|---|---|---|
| 3 | 0.0030-0.0970 | 32x |
| 5 | 0.0054-0.0850 | 16x |
| 8 | 0.0079-0.0693 | 9x |
| 14 | 0.0109-0.0599 | 6x |

**Inference — every configuration in this document is consistent with the
current unchanged code.** Probability that k sweeps of *this* config report at
least the claimed figure: pre-router baseline 0.0630 at n=5 → **p=0.08**;
router-competes 0.0511 at n=9 → 0.12; vanish-dropped 0.0164 at n=8 → 0.76;
post-refactor 0.0268 at n=14 → 0.58. The "pre-router baseline is the best
configuration ever measured" claim was a 1-in-12 fluctuation selected
post-hoc as the maximum across ~6 configurations — the standard way to
manufacture a false best. The monotonic "more routing buys reliability and
costs score" result rests on three numbers that are one distribution.

This does not mean the router helps. It means **nothing here has ever been
measured**, in either direction.

**Power, for future work** (rank test, P(detect)):

| improvement | n=10 | n=30 | n=50 | n=100 |
|---|---|---|---|---|
| +50% | 0.13 | 0.26 | 0.39 | 0.68 |
| 2x | 0.21 | 0.51 | 0.75 | 0.95 |
| 3x | 0.35 | **0.80** | 0.95 | 1.00 |

Standard from here: **n>=30 per arm, compare medians, 15 minutes.**

### Budget ladder, graded on depth

**Hypothesis.** Depth dominates score, and 400 actions is below the human cost
of finishing most games (median 638, and a perfect human finishes only 8/25
within 400). So more budget should buy depth.

**Observation.**

| cap | n | mean | median | games reaching L1 | games reaching **L2** | median completion |
|---|---|---|---|---|---|---|
| 400 | 30 | 0.0307 | 0.0131 | 1.63 | 1 (in 750 game-runs) | 173 |
| 800 | 6 | 0.0466 | 0.0125 | 2.33 | **0** | 320 |
| 1600 | 6 | 0.0111 | 0.0091 | 3.83 | **0** | 726 |

**Inference — budget buys breadth, not depth.** Games clearing level 1 rises
cleanly 1.63 → 2.33 → 3.83, and level 2 stays at zero. Score does not rise,
because the extra completions are slow ones and score is quadratic in speed
*within* a level. The 1600-action experiment from the budget-ladder entry was
right to be run and was abandoned on the wrong grounds; the number that
mattered (depth) was never recorded. Across **every sweep on record, one
game-run has ever reached level 2** (tu93, once).

### What actually stops level 2

**Hypothesis 1 (refuted).** Completing level 1 poisons the policy: level-up
credit persists across the boundary at weight 20 and permanently flips the
`proven` gate that disables routing. **Refuted** — measured on the recorded
completions, the action distribution does not collapse afterwards (sp80 stays
spread across all four actions, frame-change stays 100%). The credit is
divided by try-count, so by action ~185 a +20 bonus is well diluted.

**Hypothesis 2 (partly confirmed, and the useful part is where it fails).**
Death is resource exhaustion, so the binding constraint may be the
*per-attempt* budget inside a level, not the total cap. sp80 at cap 1600,
logged: cleared level 1 at action 109, then made **33 attempts at level 2 and
died on all of them**, median **45 actions per attempt** — against a human
baseline of **58**. Only 1 of 33 attempts survived long enough to match human
optimal play. On sp80, level 2 is not stumble-able even in principle.

But it does not generalise, and that is the finding:

| game | level 2: actions per attempt | human needs | attempts cleared |
|---|---|---|---|
| sp80 | 45 (median) | 58 | 0/33 — budget below human optimal |
| cn04 | 81 | 54 | 0/1 |
| **cd82** | **100** | **8** | **0/15 — 12x the needed budget, still fails** |

**Inference — two distinct failure modes, and cd82 isolates the interesting
one.** On sp80 the per-attempt resource is below what the level costs a human,
so no policy without near-human efficiency can clear it. On cd82 the agent has
**twelve times** the budget it needs and still fails every attempt, which
budget cannot explain. That makes **cd82 level 2 the clean testbed for goal
identification**: ample budget, short human solution, 0/15. Any real goal
signal should move it, and a null there cannot be blamed on the action cap.

Level 1 has been winnable by stumbling (small space, per-attempt budget close
to the human baseline — one run cleared it in 9 actions). Level 2 is not.
The original council question was right, but not for the stated reason: the
goal signal matters not because it improves reliability, but because from
level 2 onward there is no stumble budget to fall back on.

**Built.** `scripts/analyse_sweeps.py` — groups summaries by (sha, dirty, cap,
game count) and reports score spread, depth, and completion timing. Fixed a
latent defect in `play_local.py`: second-granularity run ids collide when
sweeps run concurrently, silently overwriting a summary; the pid now
disambiguates.

## 2026-09-13 — Stale cross-level state fixed; runs made replayable; a step-through view of the agent's reasoning

**Motivation.** The level-2 investigation needs to inspect single runs, and
three things made that impossible: knowledge from level 1 leaking into level 2,
runs that could never be repeated, and decisions that left no trace of why they
were made.

**Observation 1 — two coordinate-keyed structures survived a level change.**
`_reset_level` is documented as "a new level is a new layout, so position-keyed
knowledge dies" and missed the two largest such structures: the per-cell click
memory (`clicks._tries` / `._effect`), which was wiped only on death and so
corrupted the first attempt of every level, and `_interaction_sites`, which was
never cleared at all for the whole run. Fixed. What survives now is exactly
what is keyed by *action* rather than *place* — the move map and the
`acts_locally` signature, both properties of the controller, which the game
does not rebuild between levels. `clicks.reset_attempt()` is the right call
rather than a fresh object precisely because it keeps `acts_locally`.

These are unlikely to be *the* reason level 2 fails — cd82 fails 15/15 with
twelve times the budget it needs, which stale coordinates do not explain — but
they would corrupt any deep-dive on a single game.

**Observation 2 — no run could ever be replayed, despite a comment saying
otherwise.** The seed was
`int(time.time()*1e6) + hash(self.game_id) % 1e6`, commented "so replays of one
game are reproducible". False twice over: wall-clock time, and `hash()` of a
str is salted per process (measured: `hash('ls20')` gave 12004 / 128729 /
134629 in three runs). So the sp80 run that cleared level 1 in **9 actions**
can never be watched. Now the seed is explicit, drawn from `SystemRandom` when
not given, always recorded in the sweep summary, and offset per game by a
stable SHA-256 digest so games still explore independently while one number
reproduces a whole sweep. Verified: same seed → byte-identical action sequence;
different seed → divergence.

**Observation 3 — two of five decision branches left no trace.** Only the
frontier branch and the click path set `reasoning`; an epsilon coin-flip (25%
of actions) and a deliberate weighted choice both surfaced as a bare
`ACTION3`. A suspicious run could not be diagnosed even with a perfect viewer,
because you could not tell whether the agent decided or flipped a coin. Every
branch now records its tier, its candidates and its weights. Recording only,
and **no RNG call was added**, so the action stream is unchanged.

**Built — `scripts/recap.py` + `recap_template.html`.** Runs the agent
in-process, snapshots the **live layer objects** at every decision (not a log —
so it shows what the agent held, not what someone remembered to serialise), and
writes a self-contained page stepped through one keypress at a time: the frame
with the click target marked, every perception, per-action evidence, and the
decision with weight bars. Jump keys for level-up / death / vanish / blocked /
non-epsilon. `make recap GAME=cd82 SEED=4242`. Pages are ~1.5MB and gitignored:
they are fully regenerable from (sha, game, seed), so the seed is the record
and the page is a view.

**First finding from it.** On cd82, 301 steps: **229 weighted, 70 epsilon, 0
frontier, 0 route.** cd82 never forms a move map, so the frontier and router
branches are structurally dead there — the entire agent on that game is a
weighted bandit plus 23% noise. Worth knowing before the cd82 deep-dive: there
is currently no channel through which a goal signal could act on that game
except `_pick_coordinate`, which the interest map already feeds.

**Also — naming.** "Budget" was carrying three unrelated meanings: our
self-imposed `MAX_ACTIONS`, the game's per-attempt resource, and the human
`baseline_actions` yardstick. The middle one is now `stamina_*`
(`StaminaDetector`, `stamina_colour`, `stamina_fraction`, `STAMINA_*`).
**`stamina` rather than `lives`**: in ls20/dc22 it is literally a lives
counter, but in vc33 it is a step budget, so `lives` would assert discrete
retries the evidence does not support — the governing principle forbids exactly
that. `MAX_ACTIONS` keeps its name because the framework's `Agent.main()` reads
that attribute. 61 tests pass; `make verify-packaging` still green.

## 2026-09-13 — Rotation, multi-object conflation, per-action signatures; and an aggregate that hides a perfect signal

**Motivation.** A session of questions about what the agent can and cannot
see, each one checked rather than argued. Every finding below is recording-only:
`_select` is byte-identical throughout, verified at the end.

### Translation was the only rigid motion we ever tested for

**Observation.** `detect_translation` gets as far as "this colour lost exactly
as many cells as it gained" — a rigid-motion signature — then discards the
event if no single *offset* explains it. A rotation dies exactly there.
Measured across 25 games: **285 balanced-but-not-translated events, of which
77 are exact rotations**. On wa30, **57 of 57** — a quarter of its change
steps, seen as nothing at all.

**Built.** `perception.detect_rotation`: solves each transform's two constants
in closed form from the coordinate sums, then verifies by exact set equality.
No search, no fitting, returns None freely. Three decisions made from
measurement rather than taste:
  * `MIN_ROTATION_CELLS = 3` — the measured size distribution is 3, 18, 43,
    108 with nothing at 1 or 2; a threshold of 4 would discard all 57 of
    wa30's rotations.
  * **Reflections implemented, measured, and removed** — zero occurrences
    across 25 games, so they are absent rather than carried untested.
  * Tried only *after* translation: a centrally-symmetric shape sliding
    sideways satisfies both, and the offset is the one that composes into a
    position.

Live: wa30 ACTION1/3/4 all turn clockwise (25/15/17), cn04 ACTION5 turns
(31 cw, 1 ccw). 9 unit tests, asserting the refusals.

### Two controllable objects, merged into one

**Observation.** `detect_translation` identifies *which colour* moved and
`MoveModel` then throws it away, keeping only the offset. So the agent cannot
tell "I moved" from "a second controllable thing moved":

| game | ACTION1 | ACTION2 | ACTION3 | ACTION4 |
|---|---|---|---|---|
| sp80 | colour **12** (0,4) | colour **9** (0,4) | colour **12** (20,0) | colour **9** (20,0) |
| dc22 | colour **2** (0,2) | colour **14** (0,2) | colour **2** (2,0) | colour **14** (2,0) |
| ls20 | colour 12 | colour 12 | colour 12 | colour 12 |

sp80 and dc22 have **two independent objects**; ACTION1/3 drive one and
ACTION2/4 the other. Their motions are summed into one `displacement`, which
is then the key for `visited`, for `_blocked`, and for the router's BFS. ls20
is single-avatar, which is why everything looked correct there. Recorded, not
yet fixed — keying the move map by `(action, colour)` is a behaviour change.

### An action's *kind* of effect is invisible

**Observation.** `_action_changes` is a yes/no, and the colour census is
global rather than per action. So on cd82, ACTION1-4 produce identical
5↔15 / 2↔5 churn while **ACTION5 alone turns colour 0 into 15 across 400
cells and nothing else ever does** — and that exclusivity scores the same as
a one-pixel counter tick. ACTION5 was tried 27 times against ACTION3's 96.
Surfaced in the recap (viewer-side, so the shipped path pays nothing).

### The finding that matters most: an aggregate hiding a perfect signal

**Hypothesis (user).** cd82's stamina bar is not being recognised, and its
ticking is mis-filed as action-caused change.

**Observation — half confirmed.** The bar changes on 77% of steps and **192 of
192 of those land in "thing I affect"**, wholly unfiltered, because
`residual_cells` only filters cells matching a *detected* stamina colour and
cd82's is `None`. Attention is therefore polluted on three steps in four.
**Half refuted:** masking the bar row and re-running both motion lenses gives
**0 detections before and 0 after** — the real size mismatches are ±13/±14
cells, genuine deformation, not a one-cell bar tick.

**Inference — why the bar is invisible, exactly:**

| colour 4 measured as | start | min | min/start | verdict |
|---|---|---|---|---|
| whole-board total (what we do) | 164 | 100 | **61%** | FAILS `STAMINA_MUST_EMPTY_TO` |
| the bar region alone | 64 | 0 | **0%** | passes cleanly |

**100 static colour-4 cells elsewhere on the board** act as a floor. A bar
that empties *completely* is unrecoverable because unrelated pixels happen to
share its colour. This is the concrete case for grouping pixels into
entities, and it is not an analogy: the signal is perfect at the region level
and absent at the aggregate level.

Related, on cd82's control: colour 15 steps (16,23) → (26,25) → (38,23) under
ACTION4 and back under ACTION3, deforming as it goes, so every rigid lens
refuses it. A centroid test that tolerates deformation recovers **100%
consistency across 179 observations** — ACTION1 up, ACTION2 down, ACTION3
left, ACTION4 right, stride 11 — on a game where we currently detect nothing.
It does not hallucinate elsewhere: sb26 and tn36 correctly return nothing,
lp85 is noisy at 29%.

### A bug of our own making, and what it cost

Three recording dicts were put in `_reset_attempt` instead of `__init__`, so
**every death threw the evidence away**. wa30's rotation count read 7 instead
of 57. Action-keyed facts are game properties; the codebase already says so
and the code did not follow it. Fixed.

### Behaviour parity, properly measured for the first time

30 sweeps before, 30 after, same cap and game count:

| | before `88e0399b` | after `1409ea0e` |
|---|---|---|
| mean | 0.0307 | 0.0479 |
| median | 0.0131 | 0.0085 |
| sd | 0.0490 | 0.0701 |

Permutation test on the median: **p = 0.50**. No detectable difference, which
is the intended result. Note the means differ by 56% while the medians differ
by 0.0045 at p=0.50 — a clean demonstration that the mean was always the
wrong statistic here. Cost: 15 minutes.

## 2026-09-13 — Entities, and a belief layer that composes the lenses

**Motivation.** A session of adding lenses had moved the score zero, and the
diagnosis was not "we need more lenses". Per-action evidence was a flat
count — tries, changes, vanishes — with no baseline and no contrast, so
cd82's stamina tick (52-66% of steps *whatever* is pressed) sat in every
action's profile and drowned the one effect that is action-specific.

**Observation — the case for entities, with a number.** cd82's stamina bar
drains 64 cells to **0**, perfectly. It was never detected, because 100
static cells elsewhere share its colour, so the whole-board colour total
only falls 164 -> 100 = 61% and the "must actually empty" test rejects it.
The same bar measured as a region reads **0%** and passes. A signal flawless
at the region level was unrecoverable at the aggregate level.

**Built — `perception.connected_regions` + `entities.RegionTracker`.**
Grouping is representation, not ontology: it proposes that some pixels may
be one thing and says nothing about what. Pure Python flood fill; `scipy` is
not installed and is not worth a dependency for twenty lines. Meter
detection went **16/25 -> 25/25 games with zero losses**, and cd82's bar
contamination of "thing I affect" fell from **192/192 (100%) to 22%**.

Three bugs found by checking rather than reasoning, each measured:
  * The tracker must **remember vanished regions**, or a bar that empties
    gets a new id on refill and the sawtooth never closes.
  * The tiebreak had to move from *largest* to **drain persistence**. cd82
    has a fill-progress region that also sawtooths; the real bar declines
    on 57% of steps and fill-progress on 3%. Size picked the wrong one, and
    reading fill progress as a budget would have the agent conserving
    precisely when it is winning.
  * Overlap matching cannot follow a thing that moves further than its own
    width. Measured across four games, genuine non-overlapping
    reappearances sit at distance 3-5 (each game's own stride: ls20 286 of
    294 at exactly 5) and the nearest *different* object at 10, so a
    proximity fallback at **8** sits in the empty gap. ls20 went from **83
    region ids to 19** and from 70 entities permanently UNASSIGNED to
    beliefs that form.

**Built — `belief.py`.** Roles read from the contrast *between* actions:
`responsiveness` (baseline rate across all actions) and `selectivity` (how
far one action stands out). High responsiveness with no selectivity is
CONTEXT — which is exactly what the stamina bar is, so it falls out instead
of contaminating everything. Roles are **relational, not semantic**: each is
a statement about how an entity's behaviour correlates with our own actions,
and there is no PLAYER, GOAL or ENEMY here. UNASSIGNED is a first-class
outcome and roles are recomputed from current evidence every time.

Live, it says what a session of argument had been asking for:
```
cd82   #36 AFFECT   acted on by ACTION5 +27%
       #40 CONTEXT  changes whatever I press (69% of steps)   <- the bar
wa30   #0  CONTROL  I move this with ACTION2 +39%, ACTION4 +31%
```
Notably, on cd82 *without* the shift fallback it also finds
`#15 CONTROL I move this with ACTION3 +32%, ACTION4 +24%` — the game's real
left/right control, recovered from region-level contrast alone, which no
perception lens could see.

Two further bugs, both of the same family as the stamina one:
  * **Stale cells.** A draining cell has *left* its region, so testing
    against current cells missed it: the cd82 meter read **7% responsive
    where it is really 77%** and stayed UNASSIGNED.
  * **Appearing counted as moving**, so a recolour was described as "I move
    this" — a claim about the world, and the wrong one.
  * **False precision.** wa30 reported five entities as ACTION2's; ACTION2
    is genuinely highest (0.93) but ACTION4 is 0.84 against a 0.53
    baseline. Several buttons really do drive one thing, so every action
    above threshold is now named rather than only the winner.

**Status.** 102 tests (from 61 at session start), packaging verified.
`belief` is recording-only: nothing reads it to decide. That is deliberate
— naming the consumer before wiring one is the lesson of three
recording-only layers that moved the score zero.

## 2026-09-13 — The A/B lands; belief learns to say *how*; identity survives a reset

**The A/B, n=100 per arm.** `detect_shift` (deformation-tolerant motion)
**default ON — the first change here to earn a default by measurement**:

| test | OFF | ON | p |
|---|---|---|---|
| the 4 games it changes (pre-specified) | 0.0000 | 0.0898 | **< 0.0001** |
| cd82 clearing level 1 (predicted from mechanism) | 19/100 | 40/100 | **0.0017** |
| whole 25-game score | 0.0106 | 0.0190 | 0.044 |
| the 21 games it cannot touch (sanity) | — | — | 0.73 |

Zeros 13/100 -> 6/100, level-1 games 1.50 -> 2.01 per sweep, and the ON arm
produced **one level 2**, the first in any recorded sweep. n=1: noted, not
claimed.

**A lesson about instruments, worth more than the result.** The flag alters
behaviour on only **4 of 25 games** — verified by comparing action streams,
which are byte-identical on the other 21. A 25-game aggregate therefore
dilutes the effect ~6x, which is why the whole-sweep test reads a marginal
p = 0.044 while the pre-specified subset reads p < 0.0001. Before this, a
per-game table had been over-read: lp85's +33% was the largest number in it
and lies on a game the flag **cannot touch** — pure sampling noise. Check
which games a change can even reach before reading per-game differences.

**Belief now says how, not just that.** Roles carry a kind — MOVED, TURNED,
GREW, SHRANK, APPEARED, VANISHED — each defined only by what happened to a
set of cells. wa30's rotating object reads TURNED by centroid-preservation,
arriving at the same conclusion `detect_rotation` does by a different
route. cd82's bar reads "shrank whatever I press", which is stamina's
meaning derived rather than assumed.

Asked why the Controls panel still said "drives" rather than the kind, the
honest answer was that it was an oversight and not a principle: the belief
object knew the kind and the panel built its own string and discarded it.
Two bugs sat behind one symptom — the kind was never passed, and actions
were shown from the move map *or* belief and never both, so the moment four
actions learned offsets on cd82 the fifth vanished from the panel entirely.

**Identity survives a reset (mostly).** A reset teleports every object home;
neither overlap nor proximity can follow that, so fresh ids were minted and
**every belief attached to the old ones was discarded, the learned
action-to-entity mapping included**. Measured: post-reset frames mint ids at
~20x the ordinary rate (cd82 1.7 per frame against 0.08). A third matching
pass — same colour, same shape, reappearing within 3 frames — recovers it
(cd82 42 -> 35 ids, ls20 19 -> 12). The window is tight on purpose: a
same-shaped thing reappearing *moments* later is plausibly the same thing,
one reappearing a hundred steps later is plausibly a look-alike. That
tension surfaced as a failing test rather than as a guess, and both
behaviours are now pinned.

**Three GUI findings that were really engineering findings.**
  * The `environment` mask was not merely redundant — **94% of its cells
    were off-board** on wa30, at coordinates from -193 to 221 on a 64x64
    grid, silently clipped by the canvas. Obstacles live in relative
    displacement space, and where the move map is wrong the conversion is
    meaningless. Removed as a mask; the *ratio* stays in Perceptions,
    where it is a live check on whether that space is sane at all.
  * `interest` and `affect` cover **100% of the same cells** on wa30 and
    ls20 — interest is bumped *at* the residual cells, so it is affect
    accumulated over time. Kept both; they answer different questions
    per-step, but it is the same territory.
  * The entity mask painted every region one blue with opacity by id, so
    neighbouring ids were indistinguishable and two objects read as one.
    One hue per entity now.

**On the difference between certainty and strength.** A one-sided test that
a role's defining inequality holds was built, measured, and found to read
**100% for every entity** — past a few hundred observations nearly any real
effect is significant, so it discriminates nothing on screen. It now gates
whether a role is claimed at all (below 95%, UNASSIGNED), while what is
*shown* is how dependable the relation is: `wa30 #0 100%` (ACTION2 moves it
every time) against `cd82 #36 27%` (ACTION5 affects it sometimes). Correct
and useless is still useless.

## 2026-09-13 — What a level-2 failure looks like; connecting belief to the router

**Motivation.** The plan named level 2 as the open problem and cd82 as the
testbed (ample budget, human clears it in 8, reproducible zero), and said to
decide what a depth-shaped belief consumer looks like *before* building one.
Nobody had looked at what the agent actually does on a level 2.

**Observation — cd82 level 2, 8 seeds.** 5 of 8 clear level 1 (at actions
109-211) and then spend the remaining ~290 actions on level 2 without
clearing it. Per-tier breakdown of one such run (seed 8):

| level | bandit | frontier | router | interest |
|---|---|---|---|---|
| 1 (109 steps) | 65% | 6% | **22%** | 5% |
| 2 (292 steps) | **74%** | 16% | **0%** | 10% |

Two `GAME_OVER`s in 292 level-2 actions. It is not dying; it is alive and
taking near-uniform bandit actions with a median 200-cell diff each. Not a
budget problem and not a death problem: no goal and no planner running.

**Inference — the router is structurally dead from level 2 on.** The gate
`proven = bool(_action_level_ups or _action_vanishes)` latches for the whole
run, and those counters deliberately persist. Clearing level 1 therefore
switches off the only planning machinery in the agent, permanently. The gate
was added for a measured reason (an ungated router scored 0.0 on two full
sweeps), but "once anything ever worked, never plan again" is a blunter rule
than the harm it guards against required.

**Built — two flags, both default OFF, separately measurable.**
  * `ARC_BELIEF_TARGET`: the router's destination becomes the strongest
    AFFECT entity (the thing some action has been *shown* to act on),
    falling back to the hottest interest cell when no role has been earned.
    Refuses the canvas, CONTROL entities, CONTEXT (the stamina bar), the
    cell we already occupy, and anything with no position. Target selection
    is policy and lives in `my_agent.py`; `belief` gained only a descriptive
    `centroid`; `navigation` is untouched.
  * `ARC_ROUTE_PER_LEVEL`: the gate reads a per-level vanish counter instead
    of the run-wide one. `_weighted_choice` still reads the cross-level
    counters — that is the channel the original regression ran through and
    it is deliberately unchanged.
  Default path verified byte-identical on cd82 seed 8 (401 actions).

**Bug found by probing, not reasoning: the per-level gate latched on the
first step of every level 2.** `_reset_level` runs before `_learn_from` in
`choose_action`, so the level-up that *ended* level 1 was credited to level
2's counter, and the router was shut before level 2 had been played at all
(probe: `gate latches at 231`, level 2 starts at 231). A level-up is
evidence about a layout that no longer exists; it now does not touch the
per-level counter at all. After the fix the gate never latched on cd82 seed
8's level 2 and the router took **88 of 171** level-2 actions (was 0).

**A second latent bug, found by reading.** `Belief.certainty` passed four
arguments to a three-argument function and raised `TypeError` for every
CONTEXT entity. Nothing had ever called it on one. Fixed and pinned.

**Observation — what belief routing does on cd82 (seed 42, level 1).**
207 of 401 actions are router steps, in **100 separate routes of median
length 2**, to the same entity at ~(32,38). It arrives, has nothing to do
on arrival (the route is exhausted, `plan` returns None for start==target,
a bandit/frontier action moves it away), and re-routes back. Half the
level's actions are spent shuttling. Belief says "ACTION5 acts on this",
unconditionally on position — it does not say that *being there* matters,
and the consumer as built has no arrival behaviour because no evidence
justifies one. This is the honest shape of the gap: the layer knows which
action acts on which thing, and nothing yet measures whether *where* matters.

**Reachability, checked before reading any per-game number.** At seed 42
the belief target changes the action stream on **11 of 25** games (ar25,
cd82, cn04, g50t, ka59, ls20, m0r0, sc25, sk48, tr87, wa30) — the games
where a move map forms and an AFFECT role is earned. The gate changes **0 of
25** at that seed: it can only bite after a level-1 clear, and the only game
that cleared (sp80) has no move map. Both flags together ≡ belief alone
there.

**Measurement (n=30 per arm, seed-paired, 25 games, medians, permutation
test).** 4 arms x 30 sweeps x 25 games, seed-paired:

| arm | median | mean | zeros | L1/sweep | L2 total |
|---|---|---|---|---|---|
| base | 0.0145 | 0.0384 | 2 | 2.00 | 0 |
| per-level gate | 0.0145 | 0.0384 | 2 | 2.00 | 0 |
| belief target | 0.0196 | 0.0375 | 3 | 1.93 | 2 |
| both | 0.0123 | 0.0332 | 4 | 1.73 | 0 |

The gate alone is **exactly inert** — identical to base on all 30 seeds:
even ungated, the router finds no plan on level 2. Belief vs base: median
+0.005, p = 0.60; the two level-2s (both ar25) are the only ones in 120
sweeps, p = 0.49, noted not claimed. Both: p = 0.63.

**This A/B is contaminated and must be re-run on a frozen tree.** The
agent was edited while it ran (the identity and control work below), and
every sweep is a fresh process importing from disk: 15/30 base, 20/30
gate, 14/30 belief and 11/30 both sweeps ran on an edited tree. Seed
pairing and interleaving spread the contamination across arms rather than
confounding one, but the number measures a moving target. Recorded here as
a procedural failure — `constants.py` already says an arm must never be
re-run against an edited tree, and this is the same mistake one level up.

What survives the contamination is mechanistic and was confirmed directly:
with the target the consumer had (see below, it was the bucket's own
ghost on cd82) belief-routing could not help, and the gate had nothing to
route toward.

## 2026-09-14 — The gap between the belief we have and one that could carry a hypothesis

**Motivation.** The user's framing, on cd82: a bucket orbits a central
block, painting it to match a template top-left; the belief layer should be
rich enough that a hypothesis generator (an LLM, or a search) could
*propose* "match the template" from a few probing moves and then test it.
Explicitly not a cd82 feature request — the requirement is an emergent
state/belief space that says None where it has no evidence.

**Observation — the full belief state on cd82 seed 8, step 150.** Every
row individually defensible, the whole nearly useless:

  * **Identity fragments at the game's stride.** The bucket occupies 8
    ring positions at r = 12-16 around (32,38) (100 steps at "above", 76
    at "upper-right", ...). Each hop is 11-15 cells; the proximity bound is
    8 (measured on games with stride 3-5). Fresh id per hop; the old id
    lingered as a remembered ghost that **kept accumulating observations
    and holding a role**, because `belief.update` was fed the tracker's
    memory (`_tracked`) rather than its current frame. The router's
    "belief target" was the bucket's own ghost.
  * **The controller reads AFFECT, then CONTEXT.** All four movement
    actions move the bucket at equal rates, so no action stands out by
    rate; and it re-rasterises at each angle so its kind was GREW/SHRANK,
    never MOVED. By level 2: "shrank whatever I press (56%)" — the
    controller classified as weather.
  * **No composites.** Bucket = frame + fill (open on one side, so
    `merge_enclosed` rightly declines); block = pink + black; template =
    black + pink in a frame. Seven entities, no part-of structure.
  * **Vocabulary gaps.** #11 grows exactly where #12 shrinks under
    ACTION5 — one RECOLOURED event described as two unrelated size
    changes. The bucket's constant distance to the block is computed by
    nothing.
  * **No binary relations.** Block and template share a palette and a
    two-part structure; swatch count equals template colour count; one
    swatch is marked. Invisible: no predicate takes two entities.

**Inference — what a sufficient representation contains** (all
relational, none game-specific): objects with parts, identity by explained
motion; per-object invariant descriptors (palette, part count, outline
signature); binary relations over all live pairs (`same_palette`,
`similar_shape`, `contains`, `adjacent`, `constant_distance`,
`count_match`, `distinguished`); control as action->effect determinism;
an event log in that vocabulary; hypotheses as *checkable predicates* with
a progress measure, verified against the next frames, per episode only.
Build order agreed with the user: identity -> control -> composites (by
co-motion, enclosure, or cell exchange — never adjacency alone) ->
relations + events -> hypothesis interface. Each step measured for which
games it touches and for its refusals before any score is read.

### Built — step 1: identity

  * **Explained motion** (`RegionTracker.update(..., expected_offset)`):
    a region on screen last frame that now sits where the caller's own
    move map says the action just taken would put it is that region,
    however far. Second pass, ahead of proximity. Centroid may miss by
    `REGION_MOTION_TOLERANCE = 2` (re-rasterisation). Size within the
    existing deformation tolerance. Only follows what was live last frame.
  * **Live vs remembered** (`RegionTracker.live`, `Belief.live`): belief
    observes only the current frame; an entity that leaves is observed
    once as VANISHED and then not at all; `by_role` is live-only by
    default. Recap panel dims ghosts and paints only live entities.
  * **Reset is told, not deduced** (`expect_home`, `_home`): the first
    frame after `clear()` is the level's home layout; `_reset_attempt`
    tells the tracker a RESET was sent, and the next frame is matched
    against home by overlap before any other pass. Post-reset minting
    **cd82 1.7/frame -> 0.00**, ls20 0.00, wa30 0.00 (ordinary 0.01-0.06).
    The shape-revive pass stays for what it was built for.
  * Fixed on the way: `_tracked_live` seeded 13 phantom beliefs at cd82's
    level-2 boundary (`_observe_frame` runs before `_reset_level`);
    `Belief.certainty` raised TypeError on every CONTEXT entity (4 args
    to a 3-arg function, never called); `describe()` returned blank for a
    role held under hysteresis.

Measured: cd82's bucket holds **one id for all 147 steps** of the dump
(was 3). Total ids minted across 25 games 582 -> 584 — minting is
dominated by resets and level changes, not hops, so the aggregate did not
move even though the bucket's identity did. Like-for-like CONTROL counts
(ghosts included) after >= before on the four games where the live-only
count fell (re86 16 vs 5, cn04 11 vs 2, sc25 4 vs 3, ar25 12 vs 2).

### Built — step 2: control by determinism

`Belief.effects` tallies (kind, direction) per action; `determinism(a)`
is the fraction of a's changes carrying its modal effect;
`controllers` is every action deterministic at >= 0.8 with >= 4 changes,
*provided their effects differ* — two buttons doing the same thing carry
no information about which was pressed. CONTROL when `controllers` is
non-empty, ahead of the rate contrast, which is kept for the one-button
case. Motion is read from **bounding-box extent**: both edges shift =
MOVED (whatever the size did), one edge = GREW/SHRANK, neither = TURNED.
No tolerance constant.

Live: cd82 bucket frame and fill `control 100% — ACTION4 +x, ACTION1 -y,
ACTION3 -x, ACTION2 +y`; belief target is now **the block (32,39)**, the
thing ACTION5 acts on, for the first time. ls20 sprite (two parts)
`control 100%` with the same map. Refusals pinned: equal rates with random
directions, two same-effect buttons, one deterministic button (left to the
rate path), below-floor evidence. 140 tests.

**Status.** Default action stream has changed (tracker feeds stamina,
residual and interest), so the identity work needs its own parity/A/B on a
frozen tree before it can be said to have earned anything at the score.
Nothing above is wired to a decision beyond the existing flagged consumer.

## 2026-09-14 — Council on the next step; two agreed builds overruled

**Motivation.** Before building step 3 of the representation roadmap
(composites with parts), pressure-test the whole direction: five independent
advisors, anonymised peer review, chairman synthesis. Full record in
`council_2026-09-14_belief.md`.

**Observation.** Unanimous: relations before composites; relations return a
residual `int | None` (0 holds, None undecidable — never False for unknown);
the residual *is* the progress measure; cut the semantic names; probe before
build. Overruled from our plan: **composites are never built** (a partition
has no falsifier — the Outsider's line), and `distinguished` is salience with
no test. Upheld against us: the relation set was cd82 read backwards; fix by
deriving it from a second game and shipping the intersection. Rejected from
the Contrarian: "no score moved after steps 1-2, so stop" — an agent that
cannot represent the goal cannot move the score, so a flat score is the
predicted observation. What every advisor missed and the reviewers named:
actuation (`action -> delta residual`), the level-boundary diff as free
per-episode supervision, that every probe was passive, and that nobody
designed the serialisation the LLM would read.

**Inference.** Order is now: `relations.py` (six residuals, offline, no
policy change) -> `probe_relations.py` with three exit criteria, the binding
one being *>=50% of level advances preceded by a monotone-decreasing
residual* -> event log + `action -> delta residual` -> boundary diff as
supervisor -> enumerator, serialisation-first, then LLM. Frames added to the
per-step recordings so the probe can replay offline; they were not recorded
before.

## 2026-09-14 — Relations as residuals; the probe gate, run

**Built.** `agent/relations.py`: seven relations over every pair of known
entities, each a residual `int | None` (0 holds, None undecidable — ghost,
first sighting, history too short). `palette_diff`, `shape_diff` (0 or
None, no threshold), `containment`, `distance`, `distance_drift`,
`count_diff`, and `cell_exchange` as grouping evidence. Per (relation, pair)
a tally of how each action moved the residual — the actuation bridge the
council found missing. No grids aligned, nothing ranked by goal-likeness,
no composites stored. Frames now recorded in the per-step JSONL (64 hex rows,
~4.6 KB/step, gitignored) so `scripts/probe_relations.py` replays the whole
perception stack offline. 152 tests.

**Observation — the probe, 4 sweeps x 25 games, 11 level advances.**

| criterion | result | need |
|---|---|---|
| (i) games with a moving residual | 25/25 | >= 15 |
| (ii) games with an action-selective lever | 18/25 | >= 3 |
| (iii) literal: a residual collapsing to 0 into the advance | 4/11 = 36% | >= 50% |
| (iii') a falling residual some action selectively drives | **6/11 = 55%** | >= 50% |

Two corrections to the literal (iii), both forced by the data rather than
chosen: **the solved frame is never observed** — the winning action yields
the *next level's* first frame, so the last frame in the window is one move
before the goal and a residual whose final step is that move cannot read 0;
and **drains pass "monotone"** — cd82's stamina containment fell into every
advance because time passes. Three of the four literal hits were artefacts
(`distance_drift` reading 0 because things stopped; a 64 -> 0 identity
discontinuity). (iii') requires the residual to be falling *and* to have an
action that moves it more than the others do — the same contrast that keeps
the stamina bar out of every belief.

**Inference.** The gate passes, narrowly, on 11 advances, and says exactly
what the flat-entity vocabulary can and cannot express:

  * Every lever into an advance is `distance` or `containment` — the
    navigational family. ar25 (2/2), cn04 (1/1), ls20 (1/1), cd82 (2/4) hit;
    **sp80 (0/3) has no falling coordinate at all**.
  * **`palette_diff` and `shape_diff` never moved on any game.** Over
    single-colour flat entities a palette is one colour and `palette_diff`
    is 0 or 2 forever; the block-matches-template coordinate on cd82 is not
    expressible until a *view* groups the block's parts. The council said
    composites fall out for free from persisting `cell_exchange` /
    `containment`; this is the measurement that says the free view is now
    the binding constraint, and it stays a view, never a node.
  * The None queue is dominated by ghosts (re86: 4930 of 5405 pairs).

Next per the verdict: step 5 (event log + `action -> delta residual` in the
agent), then the level-boundary diff, with the grouping *view* added to the
relation layer so `palette_diff` can move. More advances are needed to make
(iii') a measurement rather than a reading: 11 is the whole sample.

## 2026-09-14 — The brief, the grouping view, and what two games' briefs say

**Built.** `agent/brief.py` — the text a hypothesis proposer would be sent
(THINGS / GROUPS / CONTROL / RELATIONS / FALLING / OPEN / RECENT, ~45
lines), composed live by the agent and shown verbatim in a new recap card.
`RelationEngine.groups()` — the council's "composite for free": union-find
over pairs whose `containment == 0` or `cell_exchange > 0` has persisted 3
steps, recomputed every call, never stored; `palette_diff` / `shape_diff`
between groups. `PairRecord.lever()` — the action that moves a residual
*more than the others do*, Belief's selectivity contrast lifted to a pair.
161 tests.

**Observation — reading the brief as a proposer would, three times.**
First draft on cd82: all ten RELATIONS rows and six of eight RECENT events
were the canvas (`containment(static, canvas) = 3192`; "canvas lost 35
cells that the bucket gained" on every move). The canvas is now excluded
from relation pairs at the engine. Second draft: `containment(*, stamina
bar)` filled FALLING because the bar drains under everything. FALLING now
requires a lever. Third draft, sp80: the **canvas had earned CONTROL** —
it grows under one action and shrinks under another, deterministically,
which is the d-pad signature applied to the substrate — and was named as
what the d-pad moves. Excluded from CONTROL.

**Observation — the grouping view on cd82, unprompted, at step 60:**
`{#0,#1,#5,#6}` the template (interior, frame, black, pink);
`{#2,#3,#4}` the strip with its swatches; `{#8,#9}` the bucket, frame and
fill; `{#11,#12}` the block's two halves. Every object the opening
screenshot named, from persistence of two relations, with no node stored.

**Inference — what the two briefs say, and what they cannot.**
  * cd82: `palette_diff(template-group, block-group) = 2`, constant — the
    block already has the template's two colours; the goal is their
    *arrangement*. In this vocabulary that is `shape_diff(template-black,
    block-black) -> 0`: an equality with no gradient, which is exactly
    where "never align two grids" leaves it. The cd82 probe with group
    residuals confirms: no group residual is a lever or collapses into any
    advance.
  * sp80: CONTROL says "moves *something*" — the move map has offsets but
    **no entity is CONTROL**; every relation "moves under every action
    alike" (a timer, `{#0,#7}`, one bar grouped from cell exchange);
    FALLING: nothing. The honest brief for a game where the agent does not
    know what it controls, and the second-game derivation the council
    asked for: sp80's controllable objects are not entities at all
    (the plan's "sp80 assigns no CONTROL" item, now located).

## 2026-09-14 — The second game finds a perception bug: solitary objects were the canvas

**Motivation.** The council required the relation set to survive a second
game's dump. sp80's brief said `CONTROL: moves *something*` — the move map
had offsets, no entity was CONTROL, every relation "moved under every
action alike", FALLING was empty.

**Observation.** sp80's controllable object is an 80-cell bar of colour 9
that touches nothing but canvas. `merge_enclosed` folds a region "wholly
surrounded by one other region" into that region — built for a fill inside
a frame — and the canvas satisfies that for anything floating alone on it.
The bar was absorbed into the canvas on every frame. Every other object on
sp80 survived only because it happened to touch a second region (the
U-shapes touch the floor; the top piece touches the timer). `regions total
8, tracked live 8`, and the bar in neither.

**Built.** `merge_enclosed(regions, background=...)` never absorbs into
the background colour (or, unknown, the largest region). Three tests.
After: sp80 `#4 colour 9 80 cells CONTROL — ACTION1 -y, ACTION2 +y,
ACTION3 -x, ACTION4 +x`, and FALLING carries `distance(#4, #5)` /
`distance(#4, #6)` — the bar approaching the two 80-cell U-shapes, driven
by ACTION2 and ACTION4 respectively. The brief went from "I do not know
what I control" to a full d-pad and two candidate destinations, from one
perception fix and no new vocabulary.

**Inference.** This changes the region list on every game with a solitary
object, hence the tracker, stamina, residual and interest — the default
action stream moves. It is the third default-path change today without a
parity measurement (identity, control, this); the debt is real and listed.
The council's "derive from a second game" rule paid for itself on the first
try, and not in the way expected: the vocabulary held, the perception
under it did not.

**The probe, re-run with the merge fix (same 4 sweeps, 11 advances).**

| criterion | before fix | after fix |
|---|---|---|
| (i) games with a moving residual | 25/25 | 25/25 |
| (ii) games with an action-selective lever | 18/25 | 18/25 |
| (iii) literal collapse to 0 | 4/11 = 36% | 6/11 = 55% |
| (iii') falling residual some action drives | 6/11 = 55% | **9/11 = 82%** |

sp80 went from 0/3 advances with any falling coordinate to **3/3** — the
whole gain — once its controller existed as an entity. cd82 still 2/4:
its two misses are the advances where the winning move was a paint action
and the relation set has no coordinate for arrangement. Same sample of 11;
the number is a reading, not a measurement, but the direction is the one
the fix predicted.

## 2026-09-14 — Deciding when the brief is rich enough

**Motivation.** The user's question: with primitives, beliefs, relations
and a brief built and nothing wired to the controller, what is the cut-off
for moving to hypothesis generation? "How do you know there is enough
info?"

**Inference.** Sufficiency is not judgeable from inside the vocabulary;
it is a test. (a) Recall at the boundary: does the brief 3-8 steps before
a level advance contain the coordinate that turned out to matter? The
answer separates a selection gap (in the engine, not in the text) from a
vocabulary gap (not in the engine) from no gap. (b) An oracle read of five
cold briefs. Bars set low and explicit — majority recall, 2 of 5 — because
the point is to start the loop, not to perfect the layer: from then on new
primitives come from hypotheses that failed because they were
*inexpressible*, each surviving a second game. Score expectation stated by
the user and agreed: none until something consumes the brief. Added to
`plan.md` as 5b.

## 2026-09-14 — Parity: today's perception changes moved no default action

**Motivation.** Three default-path changes shipped without measurement
(identity, control by determinism, `merge_enclosed` not folding into the
canvas). The user asked for the current score; the honest answer was that
the current commit had never been scored.

**Observation.** 30 sweeps x 25 games at `54173e7`, seeds 1-30, frozen
tree, against the seed-paired A/B base arm at `5855c9d`:

| | reference | current |
|---|---|---|
| median | 0.0145 | 0.0145 |
| mean | 0.0384 | 0.0384 |
| zero sweeps | 2 | 2 |
| games reaching L1 / sweep | 2.00 | 2.00 |
| level-2 clears | 0 | 0 |

Permutation p = 1.000, and every seed-paired sweep that could be compared
(10 of 10) has **byte-identical** per-game outcomes: levels, action counts,
completion indices. The identity, control and merge changes altered the
entities, beliefs and relations the agent *holds* and not one action it
*took* — the policy still reads none of them. Expected (stated by the user
beforehand), and it retires the parity debt for all three at once. The
reference arm's own contamination is moot for the same reason.

**Inference.** The score is 0.0145 median at the current commit, unchanged
since `5855c9d`; it will stay there until something consumes the brief.

## 2026-09-14 — Cut-off test (a): recall of the goal coordinate in the brief

**Built.** `scripts/probe_brief_recall.py`: replays the full perception
stack from recordings, composes the brief as it stood 3-8 steps before
each level advance, and asks whether the coordinate that fell into the
advance under a lever was in the text — FALLING, RELATIONS, engine-only, or
absent.

**Observation — 11 advances x 6 leads.**

| where the coordinate was | rows | advances (best lead) |
|---|---|---|
| FALLING (named as a candidate) | 2 (3%) | — |
| RELATIONS (present, findable) | 36 (56%) | 7 |
| engine only (crowded out of the text) | 4 (6%) | 0 |
| absent (no such coordinate) | 22 (34%) | 4 |

**7/11 advances had it in the text — the bar (a majority) is cleared.**
Zero selection gaps: whenever the engine had the coordinate, the brief
carried it. All four vocabulary gaps are cd82's paint advances, the
arrangement goal already known to be inexpressible without alignment.
FALLING almost never named it (2 rows): its 5-step window and "down twice"
bar are too tight; RELATIONS is where a proposer would find it.

**Correction to the relation probe.** This probe skips the canvas as the
agent does; the earlier one did not. cd82's "levers" in that run were all
`distance(*, #7)` with #7 the canvas — the bucket moving relative to the
board's centroid, not toward anything. With the canvas excluded cd82 has
no lever coordinate at any of its four advances; the 82% is re-measured
below.

**Inference.** The brief is rich enough to hand over, by the test we set:
the goal was findable in the text for every advance whose goal the
vocabulary can express at all. Next: (b) the oracle read, then (c) the
proposer. FALLING to be loosened or dropped in favour of a proposer that
reads RELATIONS itself.

## 2026-09-14 — Cut-off test (b): five cold reads of the brief

**Method.** Five briefs from games not yet examined (ar25, cn04, tu93,
vc33, ka59), each at ~step 240, handed to a fresh model that saw nothing
else — "state the goal as a checkable condition, the coordinate to watch,
the first three moves, and what is missing" — then scored against the
games' first frames, which the readers never saw.

**Observation.** cn04: `distance(cyan tile, cyan tile) -> 0` — the
docking condition, **hit**. tu93: "reach the far corner tile", walls at
half-offsets — **hit**, low confidence. ka59: "put #5 where its twin #6
sits in the mirrored room", as `shape_diff` of the two assemblies — a
checkable, plausible **hit**. ar25: "shrink #17" — **miss**; its fallback,
colour/shape matching, was the right family. vc33: **miss**, and it
planned ACTION1-3 on a click-only game. **3 of 5; the bar was 2.**

Every reader asked for the same five things, none of them vocabulary:
available actions; click coordinates in RECENT; blocked moves; an extent
per thing (with `shape_diff` equality-only, every shape row read "not
decidable"); and no stale ids in GROUPS rows. All except blocked moves
fixed the same hour. Every reader also asked for a score or level signal
— the level-boundary diff, step 6.

**Inference.** The brief carries enough for a cold reader to state a
checkable goal on a majority of games. The failures are the informative
ones: ar25's reader chose the one entity with a "shrinks under ACTION5"
belief over the shape relation because shape said nothing — the
equality-only rule is right for *goals* and wrong for *description*, and
extents fix that without aligning anything. Proceed to (c).

**Relation probe, corrected (canvas excluded as the agent does):** (i)
25/25, (ii) 18/25, (iii) literal 6/11, **(iii') 7/11 = 64%** — passes,
down from the 82% that counted `distance(*, canvas)` as levers on cd82.
cd82 now contributes 0/4: none of its advances has a lever coordinate in
this vocabulary, consistent with (a).

## 2026-09-14 — (c) The first consumer: hypotheses that must earn their keep

**Built.** `agent/hypothesis.py`. A hypothesis is `residual(rel, a, b) -> 0`
with the action that has been seen to drive it (the lever), a budget of 8
actions, and three deaths: *held* at 0, *falsified* when the residual rises
twice running or does not fall in 3 presses, *expired* at budget while still
falling. Falsified and expired keys cool down for 40 steps. The enumerator
proposes the live pair with the clearest legal lever, excluding pairs with a
CONTEXT member (belief's judgement, reused) and click levers (no coordinate
to click). A `distance` hypothesis is a destination: the router plans from
the controlled thing to the other member and the first step is taken,
verified on the residual as before. New `hypothesis` tier in `_select`,
below epsilon, behind `ARC_PROPOSER` (default OFF). The brief gained a
HYPOTHESIS section (what is being tested, the last three outcomes). 173
tests. Default stream untouched with the flag off.

**Observation — first live run, three games, seed 8.** The tier takes
60-70% of steps. sp80: `distance(#4, U-shape) 26 -> 22 -> 18 -> 14` under
ACTION2 — the loop doing what it is for. cd82: before the CONTEXT
exclusion it bet on `containment(stamina bar, block)` with a +30% lever
earned on four presses; 18 falsified, 3 expired, and level 1 — which the
bandit had reached by stumbling onto ACTION5 — not reached. tu93: 19
falsified in a row, most at "3, 3, 3": a lever that does not move the
residual from where the thing now stands, i.e. a wall, which the lever
tally cannot see. **A/B launched: base vs proposer, n=30, frozen tree.**

**Inference, ahead of the number.** This is the first policy change fed
by the brief, and the honest expectation is that it can lose: it displaces
the bandit that has been finding level-ups by accident, and it aims at
whatever moves, not at what matters — the level-boundary diff (step 6) is
what would tell it which residuals have ever mattered. The measurement is
the point; the vocabulary grows from what this loop falsifies.

Constraint surfaced for the LLM proposer: no `anthropic` SDK or key in
this environment, and the competition notebook has no internet. The LLM is
a development-time proposer for growing the vocabulary; the competition
path is the enumerator, or a local model. Interface is the same
`Hypothesis` either way.

## 2026-09-14 — A/B: the first brief consumer, base vs proposer (n=30 per arm)

**Pre-specified test: whole 25-game score, medians, permutation.**

| arm | median | mean | zero sweeps | L1 games/sweep | L2 |
|---|---|---|---|---|---|
| base | 0.0145 | 0.0384 | 2 | 2.00 | 0 |
| proposer (`ARC_PROPOSER=1`) | **0.0420** | 0.0588 | 0 | 2.27 | 0 |

Median +0.0275, **p = 0.082**. Not significant at 0.05; the first change
since the shift fallback to move the median at all, and in the direction
that the earlier three recording-only layers did not.

**Reach check first, as the protocol says.** The flag changes level reach
on 8 of 25 games; the untouched 17 score identically in both arms (median
0.0000 / mean 0.0009 in each, p = 1.0) — the flag genuinely does not touch
them. On the 8 it touches: median 0.040 -> 0.131, p = 0.063.

**Exploratory, post hoc — not confirmatory.** The 8 split cleanly:
  * gainers sp80 16->25, m0r0 **0->9**, ar25 9->13, cn04 3->5, sk48 0->1
    — games where the level is cleared by *reaching* something. Subset
    median 0.019 -> 0.198, p = 0.004.
  * losers cd82 **16->4**, ls20 5->1, tr87 1->0 — cd82's level is cleared
    by a paint action (ACTION5) that the bandit found by stumbling and the
    proposer now displaces with movement hypotheses. Subset median
    0.050 -> 0.000, p = 0.001.
Both p-values were selected after seeing the data and mean nothing on their
own; the split is the finding, not the numbers. m0r0 reaching level 1 at
all — never once in 60+ base sweeps — is the single most informative row.

**Inference.** The consumer works exactly as far as its vocabulary does:
`distance -> 0` is a navigational goal, and it wins on navigational games
and loses on the one game whose winning move is not a movement. The cd82
loss is the cost of aiming at whatever moves; the level-boundary diff (step
6) is the mechanism that would have told it, after one clear, that
ACTION5 was the lever that mattered there. Not promoted to default: p =
0.08 on the pre-specified test, and the cd82 regression is real. Next:
step 6, then re-run this A/B.

## 2026-09-14 — The matching family gets its two counting residuals

**Motivation.** The user's question: does anything in the belief hint that
cd82's block and template are correlated in their colours? Partly —
`palette_diff(template-group, block-group) = 2`, muddied by the frame and
interior folded into the template's group; `shape_diff` is the endpoint
with no gradient. The council's rule for a new primitive was met twice
(cd82's four absent advances in (a); the A/B loss), with two candidate
second games from the cold reads (ar25, ka59).

**Built, over the grouping view only, counting only, no alignment.**
`palette_missing(A, B)` = colours of A that B lacks (directional):
block -> template reads **0** on cd82 — "everything the block is made of,
the template has". `part_size_diff(A, B)` = over shared colours, the summed
difference in cells per colour: a *proportion* residual with a gradient, so
the paint action can become its lever. Arrangement stays `shape_diff = 0`.
Group records gained **continuity**: a group whose member is reborn under
a new id inherits the record of the earlier group with the same colours
sharing at least half its members — the tracker's overlap rule applied to
composites. The proposer now bets on group residuals too.

**Second-game check.** `part_size_diff` moves on cd82, ar25 **and** ka59
(all three recordings), so it ships. ka59's brief now reads
`palette_diff = shape_diff = part_size_diff = 0` between its two rooms —
the cold reader's mirror hypothesis, confirmed by the structure. On cd82's
recorded advances the new residual is present but not yet a *lever*: the
bandit pressed ACTION5 too rarely in those runs for a rate contrast to
form. The proposer, live, still spends its cd82 budget on bucket-related
`part_size_diff` noise (bucket re-rasterisation changes its part sizes).

**Next primitive, from the user's snake example, not built:** *kinds* —
things with identical descriptors are the same kind, and what one did
(ate, drained, scored) is evidence about the others. A view over equal
shape and palette, with beliefs transferring across it. Listed as 4d.

## 2026-09-14 — Step 6: the level-boundary diff as supervisor

**Built.** `agent/supervisor.py`. Keeps the last 8 residual vectors; at a
level advance — read *before* the level's records are cleared — finds the
residuals that were falling into it under a lever (the relation probe's
(iii') test, live) and records them **typed by colour**, since ids die
with the level and colours do not: "part_size_diff between a {0,15} thing
and a {0,4,5,15} thing fell into the advance", plus the winning move. A
death clears the window (the frames before it were not a run-up). The
proposer ranks a candidate whose type has mattered first, then one whose
lever has won, then by lever strength — weights, never rules, because
goals may change per level. The brief gained MATTERED, including the count
of advances with *no* expressible coordinate, so the vocabulary's blind
spots are counted rather than hidden. Per episode only. 183 tests.

## 2026-09-14 — 4e: kinds — same stuff, different roles, drift, transfer

**Motivation.** The user's question: two objects share a colour
combination, one changes under our actions and the other stays constant —
can the belief say "similar but evolved", "similar but one is controllable"?
Both halves existed as monads (roles per entity; palette/shape residuals
between groups) and nothing joined them.

**Built.** `agent/kinds.py`, a view over the grouping view. A kind is two or
more units with the same palette and part count; *exact* when their
outlines match. Units are groups, lone things, and — new in the relation
engine — the **content of a framed group**: the members a frame's bounding
box encloses, minus canvas-coloured filler. Each member carries the roles
belief gave its parts; a member that changes is described by its residuals
to the static member (drift) with the lever that moves them. `KindMemory`
records, per palette, members that vanished and how stamina moved when they
did, and the proposer adds a weight for distance hypotheses toward the
remaining members of a kind whose members vanished with stamina rising —
the snake reading. Units nested in one another are never compared; a reset
is neither a vanishing nor a stamina change (measured first: tu93 read "4
of this kind have vanished, stamina +98%" — four deaths).

**Observation.** cd82 at step 100:
`kind {0,15}x2 x2 (exact): {#5,#6} static · {#10,#12} changes under my
actions — drifted from the static one: part_size_diff 30, shape_diff 0`.
That is the sentence asked for, from evidence, with nothing called a
template. ka59: `kind {1,4,14}x3 x2: {#1,#5,#8} holds the CONTROL thing —
drifted part_size_diff 27 (ACTION3 drives it down) · {#3,#4,#6} static`.
tu93: the maze tiles read as two exact kinds of 32 and 18. cn04: no kinds
— its cyan squares are absorbed into one big group by containment, which
is the grouping view being too eager on that board and is noted.

**Not yet exercised live:** the transfer half. No game in the recorded set
has a kind whose members vanish with a stamina change; it holds on the
unit test and waits for a game that has it. 193 tests. Built on the
`next-step` worktree branch while the proposer A/B ran on a frozen main.

## 2026-09-14 — Exploration inside the proposer: the floor fails, the diagnosis holds

**Hypothesis.** cd82 loses under the proposer because its paint action is
never pressed enough to earn a lever; a floor of 4 presses per legal
action per level, winning moves first, would let it.

**Observation — 8 touched games x 30 seeds, base vs proposer+floor.**
cd82 16 -> **3** (A/B #2: 2 — unchanged), sp80 25 -> **15**, m0r0 9 -> **6**,
cn04 3 -> 9, ar25 9 -> 10, ls20 5 -> 1. Median +0.004, p = 0.74. Reverted
to probing only *winning moves from earlier levels*.

**Diagnosis, from one traced run.** ACTION5 was pressed 76 times; **8
presses painted anything**. Painting lands only when the bucket stands at
the right angle to the block — the effect is **conditional on position**,
and the lever contrast (rate under this action vs the others) cannot see
an effect that fires on 1 press in 10. When it did paint, the kind drift
went 30 -> 60 -> 80: the wrong colour onto the wrong half, so the few
"drive it down" bets were honestly falsified. The bandit clears cd82 with
8-21 paint presses because its random walk samples (position, action)
pairs the movement hypotheses never visit.

**Inference.** The missing structure is the one the user named earlier and
§8 of the architecture lists: **conditional effects** — a lever *given*
another residual's value ("ACTION5 moves part_size_diff(template, block)
when distance(bucket, block) <= d"). General: eat-when-touching,
push-when-adjacent, paint-when-aligned. That, not more presses, is what
would let the enumerator find cd82's move; it is also the first primitive
the LLM proposer would need to be able to *say*. Next.

## 2026-09-14 — 7a: conditional levers, preconditions, and what cd82's paint is conditional on

**Built (H001, `research/hypotheses/H001_conditional_affordance.md`).**
`PairRecord.by_action_given[condition][action]`: the movement tallies split
by a precondition read from the frame *before* the action —
`adjacent:-x`, `apart:+y`, …: whether the controlled thing touched the
nearest non-control member of the pair, and on which side.
`conditional_lever()`: an action that moves the residual under one
condition more than it does under the others *and* more than the other
actions do under that condition. `Hypothesis.precondition`; the verifier
now reports per-step `supported / against / precondition_unmet /
inconclusive`, and a step under an unmet precondition costs budget but is
not evidence; the router carries the controlled thing to the required side
first. The brief says "ACTION5 drives it down when the controlled thing is
adjacent on side -x". 205 tests.

**Observation — three readings of the same record on cd82, seed 8.**
  1. Adjacency alone: *every* orbit position of the bucket touches the
     block's bounding box, so the condition never varied and no contrast
     could form. The paint press on `part_size_diff(template content,
     block)` read `down 3, up 8, flat 87`.
  2. The residual reached **0 at step 320 — proportions matched — and the
     level did not clear**, then rose again. Arrangement, as predicted.
  3. By side: from `-x`, ACTION5 `down 2, up 1, flat 3`; from `+x`
     `0, 2, 6`; from `+y` `0, 2, 0`; from `-y` `1, 2, 20`. A conditional
     lever forms: `ACTION5 | adjacent:-x, +0.30`. The mix within a side
     is the factor still unmodelled — the *selected paint colour*, which is
     the state of a strip entity the swatch click changes.

**Inference.** The condition vocabulary now has two general members
(adjacency, side), both from the reviewer's list, and the first fired
nowhere while the second fired at once — which is the argument for adding
conditions one at a time against a game that needs them. cd82's full rule
is two-factor (side × selected colour); the second factor is "the state of
another entity", the next generalisation. E-7a (touched 8 games × 30
seeds) launched to see what side alone buys.

**E-7a (touched 8 games x 30 seeds, base vs proposer with conditional
levers).** Median 0.040 -> 0.110, p = 0.20. Per game reaching L1: sp80
16 -> 25, ar25 9 -> **15** (A/B #2: 10), m0r0 0 -> 6, cn04 3 -> 5, sk48
0 -> 1; **cd82 16 -> 2 — unchanged**; ls20 5 -> 0, tr87 1 -> 0.

**Inference.** H001's second falsifier is met: the conditional lever
appears on cd82 and cd82 does not recover. The lever was not the
bottleneck. cd82's rule is two-factor — side × selected paint colour — and
the second factor is the *state of another entity* (which swatch is
marked), which no condition in the vocabulary reads; and even with the
proportions matched (residual 0 at step 320 of the traced run) the level
needs the *arrangement*, which has no gradient by design. Three attempts
at cd82 through the enumerator (exploration floor, adjacency, side) have
each moved the diagnosis and not the number. The navigational games keep
their gains and ar25 improved again. Decision left to the user: a third
condition (another entity's state), or accept cd82 as the open case the
enumerator cannot express and move to the LLM proposer, which can *state*
a two-factor rule from a brief that now shows side-conditional levers and
the swatch strip as a thing ACTION6 turns.
