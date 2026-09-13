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
