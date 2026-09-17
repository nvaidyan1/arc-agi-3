"""Every tunable in the agent, grouped by the layer it belongs to.

Kept in one place deliberately. These numbers are the agent's entire
configuration surface, and most of them were set by measurement rather
than taste — the comment on each says what measurement, so that changing
one is a decision made against evidence rather than a guess. Where a
value was chosen to match another value (rather than tuned on its own),
that is stated too, because tuning it in isolation would break the
relationship it was picked for.

Layer order matches docs/plan.md's representation stack:
pixel > change > object > thing I control > thing I affect > environment,
plus attention and navigation on top.
"""
from __future__ import annotations

import os

# ── Action selection ────────────────────────────────────────────────────
# Chance of ignoring the change-rate weighting and picking a legal action
# uniformly at random, so under-tried actions keep getting sampled.
EXPLORATION_EPSILON = 0.25

# ── Change layer ────────────────────────────────────────────────────────
# How many past steps' diffed cells to keep as "recently active" targets.
RECENT_DIFF_STEPS = 5

# H011: how much weight a click target's novelty (1 / (1 + times tried))
# carries against its salience tier (1 / (1 + tier index), so tier 0 is
# 1.0, tier 1 is 0.5, ...) in ClickTargeting.pick(). A live sweep on cd82
# (docs/history.md 2026-09-15, "H011 Stage 2") found this value nearly
# irrelevant in isolation, over {0, 0.5, 1, 2, 4}: strip clicks moved
# from 1.6% (the old hard-tier cutoff) to 42-52% at EVERY weight tested,
# including 0. The fix is almost entirely the move from "the top
# non-empty tier wins outright" to "every live candidate gets summed
# weight, drawn proportionally" — a tier with hundreds of cells now
# carries real total mass even at low per-cell salience, regardless of
# novelty. 1.0 (equal footing between one tier step and full novelty) is
# kept as the least arbitrary choice given that near-flat sensitivity,
# not because it measurably outperformed the others. The sweep also
# found a real, modest trade-off: clicks in the single most-active 8x8
# region fell from ~20% to 14-18% of all clicks — some of the
# concentration that made the old design's "interest always wins" rule
# correct in the first place is traded away by removing the hard cutoff.
CLICK_NOVELTY_WEIGHT = 1.0

# ── Thing I control ─────────────────────────────────────────────────────
# Evidence needed before calling an action's effect a consistent "move":
# this many sightings of the same offset, and that share of all sightings.
# Deliberately conservative — on m0r0 ACTION1 splits 15/13 between two
# offsets and this correctly refuses to learn it.
MIN_MOVE_OBSERVATIONS = 3
MOVE_MAJORITY = 0.6

# H010: the position-graph transition model's admit rule (agent/control.py
# PositionModel). Deliberately a lower bar than MOVE_MAJORITY's — this is
# not "a clear majority", it is H006's admit rule: a (position, action)
# pair is trusted only once it has been seen enough times to say the
# outcome is the SAME every time, never merely the most common one. 2 is
# the threshold this project's own H006/H009 analysis used throughout
# 2026-09-15 to call a transition deterministic.
MIN_POSITION_OBSERVATIONS = 2

# Smallest shape worth calling a rotation. Below this a fit means little:
# a single cell can be "rotated" to anywhere about some pivot, so it would
# be a free explanation for any change. Set from the measured size
# distribution rather than taste — across 8 games the rotations that occur
# are 3, 18, 43 and 108 cells, with nothing at 1 or 2, and raising this to
# 4 would discard all 57 of wa30's real rotations.
MIN_ROTATION_CELLS = 3

# Smallest change worth calling a deformation-tolerant "shift". Centroid
# motion is weaker evidence than an exact offset, so the region has to be
# substantial before an average position means anything; cd82's object is
# 70+ cells and lp85's noise is far below this.
MIN_SHIFT_CELLS = 8

# How much one axis must dominate before a shift is squared up to it. A
# deforming shape drags its centroid sideways as it travels: cd82 reports
# (-1,-11) then (1,-11), which `MoveModel` sees as two different offsets,
# splitting the majority to 56% and refusing to learn anything. Measured
# on the dominant axis those steps agree 100%. cd82's ratio is 11:1, so 3
# is well clear of the noise while leaving a true diagonal alone.
SHIFT_AXIS_RATIO = 3

# When True, an action whose effect no exact lens explains falls back to
# `perception.detect_shift`, which tolerates a changing shape.
#
# **Default ON as of the n=100 A/B** — the first change in this project to
# earn a default by measurement. It alters behaviour on only 4 of 25 games
# (ar25, cd82, cn04, tr87), so the 25-game aggregate dilutes it ~6x and is
# a poor instrument; the pre-specified test is the affected games alone.
#
#   whole 25-game score    median 0.0106 -> 0.0190    p = 0.044
#   the 4 affected games   median 0.0000 -> 0.0898    p < 0.0001
#   cd82 clearing level 1      19/100 -> 40/100       p = 0.0017
#   the 21 games it cannot touch                      p = 0.73   (nothing)
#
# Zero-scoring sweeps fell 13/100 -> 6/100, games reaching level 1 rose
# 1.50 -> 2.01 per sweep, and the ON arm produced this project's first
# level 2 in any recorded sweep (1 in 100 -- noted, not claimed).
#
# Still overridable by the environment, so an arm can be re-run without
# editing the tree mid-experiment, which is exactly how a comparison gets
# silently corrupted.
USE_SHIFT_FALLBACK = os.environ.get("ARC_SHIFT_FALLBACK", "1") == "1"

# ── Entities (grouping and following things) ────────────────────────────
# `RegionTracker` matches a region to its previous self by overlap. An
# object that moves further than its own width never overlaps itself, so
# it would get a fresh identity every step and no belief could ever
# accumulate — on ls20 that left 70 of 83 entities permanently UNASSIGNED.
#
# The fallback matches by centroid proximity instead, and the threshold is
# measured rather than chosen. Across four games the genuine
# non-overlapping reappearances sit at distance 3, 4 and 5 (each game's own
# move stride: ls20 286 of 294 at exactly 5, sp80 85 of 89 at 4, wa30 all
# at 3-4), and the nearest thing that is NOT the same object is at 10.
# Eight sits in the empty gap.
REGION_MATCH_DISTANCE = 8
# And it must be about the same size: a region half the size of its
# candidate is a different thing however close it sits.
REGION_MATCH_SIZE_TOLERANCE = 0.3

# How recently a region must have been on screen for a same-shape match to
# revive its identity. A RESET teleports every object back to its start
# within a single frame -- neither overlap nor proximity can follow that,
# so the tracker minted fresh ids and threw away the beliefs attached to
# the old ones, including the action-to-entity mapping. Measured: a
# post-reset frame mints ids at ~20x the ordinary rate. Kept tight because
# a region gone for a long time and matched on shape alone is more likely
# a look-alike than a survivor.
SHAPE_REVIVE_WINDOW = 3
# A region that was on screen last frame and now sits where the move we
# just made would have put it is the same region, however far that is.
# The offset comes from the caller's own move map, so nothing here fixes a
# stride; this is only how far the centroid may deviate from the expected
# landing. Non-zero because a shape that turns as it moves re-rasterises
# (cd82's bucket: 73 cells above the block, 84 beside it) and its centroid
# drifts a cell or two. Measured on cd82 seed 8: proximity at 8 lost the
# bucket on every 11-15 cell hop and minted a fresh id each time, leaving
# the old one behind as a remembered ghost that kept its beliefs.
REGION_MOTION_TOLERANCE = 2

# ── Belief (what each entity is to me) ──────────────────────────────────
# Roles are read from CONTRAST between actions, not from how busy an entity
# is. Thresholds set from measurement on cd82, where the two extremes sit
# side by side: the stamina bar changes on 52-66% of steps whatever is
# pressed (pure baseline, no selectivity), while ACTION5's target region
# changes almost only under ACTION5 (+41% over baseline).
#
# Evidence bars first, in the same spirit as MIN_MOVE_OBSERVATIONS: an
# entity seen a handful of times has no role, and a role read from one
# action is not a contrast at all.
BELIEF_MIN_OBSERVATIONS = 20
BELIEF_MIN_ACTIONS = 2
# How far one action must stand out before the entity is called that
# action's. Comfortably under the +41% that a real exclusive effect
# produces, and far above the +/-4% spread seen among the uniform ones.
BELIEF_SELECTIVITY = 0.20
# Above this, an entity that shows no selectivity is reporting on the world
# rather than responding to me — a meter, a timer, an animation. Set below
# the bar's measured 52-66% so it is caught, and above the 14-25% churn of
# ordinary scenery.
BELIEF_CONTEXT_BASELINE = 0.35
# A role must also be statistically convincing, not merely large. This is
# what stops a rarely-tried action looking decisive on a handful of tries.
# Note it saturates: with a few hundred observations almost any real effect
# clears it, which is why the UI shows `strength` (how dependable the
# relation is) rather than this.
BELIEF_MIN_CERTAINTY = 0.95
# How much easier it is to KEEP a role than to win one. Without this an
# entity hovering at the threshold flickers: measured on cd82, 12 of 17
# entities gained a role, lost it and regained it -- one seven times --
# and the readout changed on 19% of steps. Small enough that a role which
# genuinely stops holding still drops.
BELIEF_HYSTERESIS = 0.05
# CONTROL by determinism. The rate contrast above finds "one button drives
# this"; it cannot find a thing driven by *several* buttons at equal rates,
# which is every d-pad. Measured on cd82: the bucket responds to ACTION1-4
# about equally, so no action stands out, and the controller read as
# AFFECT with thin evidence and CONTEXT ("shrank whatever I press") with
# more. What distinguishes control is not how often a thing changes under
# an action but that WHAT happens is fixed by WHICH action: ACTION3 always
# takes it left, ACTION4 always right. An action is deterministic for an
# entity when this fraction of the changes it causes carry the same
# effect, and an entity is CONTROL when at least two actions are
# deterministic for it with different effects. Two, not one: a single
# deterministic action is already covered by the rate contrast, and one
# button that always does one thing to a thing is AFFECT unless that thing
# is motion.
BELIEF_DETERMINISM = 0.8
BELIEF_DETERMINISM_MIN_CHANGES = 4

# ── Connecting belief to action ─────────────────────────────────────────
# Two flags, both default OFF so the tree's default behaviour stays
# byte-identical to the ~43 sweeps already on record at this commit.
# They are separate because they are separable: the target changes where
# the router aims (level 1 included), the gate changes *when* it is
# allowed to aim at all (level 2 onward only). Shipping them as one knob
# would repeat the router's original mistake of adding a signal and
# changing decision logic in a single pass, which made its regression
# unattributable.
#
# TARGET. The router's destination is currently the hottest *interest*
# cell — where change has recently happened. Measured, that is not where
# the goal is, and routing to it cost score (mean 0.0511 -> 0.0164).
# Belief offers a different kind of destination: an entity some action has
# been *shown* to act on. "Bring the thing I move to the thing ACTION5
# does something to" is a claim about an action's demonstrated effect, not
# about a location's recency.
USE_BELIEF_TARGET = os.environ.get("ARC_BELIEF_TARGET", "0") == "1"

# GATE. `proven` — has any action ever produced a level-up or a vanish —
# currently latches for the whole run, so clearing level 1 permanently
# disables the router. Measured on cd82 seed 8: the router takes 22% of
# level-1 actions and 0% of level-2's 292, which are 74% bandit instead.
# The gate's stated intent was "route only while nothing has proven itself
# *yet*", and a level-up is an achievement about a layout the game has
# just replaced. Scoping it per level restores that intent: the per-level
# counter holds this level's vanishes only (a level-up is what ended the
# previous layout, so it is evidence about nothing we can still act on),
# and `_weighted_choice` is untouched, keeping its full cross-level
# level-up credit — that is the channel the original regression ran
# through, and it is deliberately left alone.
USE_PER_LEVEL_ROUTE_GATE = os.environ.get("ARC_ROUTE_PER_LEVEL", "0") == "1"

# ── Hypotheses (the first consumer of the brief) ────────────────────────
# Default OFF: the loop is built and measured before it earns a default.
# When on, `_select` takes a new tier below epsilon: if a live hypothesis
# names a legal action, take it. Nothing else in the policy changes.
USE_PROPOSER = os.environ.get("ARC_PROPOSER", "0") == "1"
# Actions a hypothesis may spend before it expires unpaid; how many steps
# without a fall before it is falsified; how long a falsified or expired
# key waits before the enumerator may propose it again. The budget is the
# council's "price every test in actions": eight is under a fifth of a
# short attempt, and a residual that has not moved in three presses of the
# action that supposedly moves it is not being moved by it.
HYPOTHESIS_BUDGET = 8
HYPOTHESIS_PATIENCE = 3
HYPOTHESIS_COOLDOWN = 40
# How many times a WINNING move from an earlier level is tried on a new
# level before the proposer goes back to betting on residuals. Only
# winning moves: a blanket floor over every action was measured and lost
# (see `_probe_action`).
HYPOTHESIS_PROBE_TRIES = 4
# H010 Stage 3 / gate 4 (2026-09-17). `_hypothesis_action` computes which of
# a bet's preconditions are unmet, tries to route to the first one, and --
# when no route exists in either transition model -- falls through and
# presses the lever anyway, with the precondition known false. Each such
# press consumes budget, so a bet can reach EXPIRED having tested nothing:
# measured at 8/8 presses unmet on all four cd82 oracle runs of gate 1,
# frozen in place, target 10-48 units away.
#
# With the gate on, that decision is DECLINED instead: nothing is spent and
# the tiers below decide. A bet that cannot be routed to forever would then
# never expire (`spent` stops rising), so a declined decision is counted,
# and HYPOTHESIS_STALL of them in a row retire the bet as UNREACHABLE --
# a distinct verdict from EXPIRED, which means "tested and inconclusive".
#
# Set below HYPOTHESIS_BUDGET deliberately rather than tuned: a bet that
# cannot even be reached should free its slot sooner than one that is being
# tested. Behind a flag, default OFF, per the one-change-at-a-time rule.
HYPOTHESIS_STALL = 6
USE_BUDGET_GATE = os.environ.get("ARC_BUDGET_GATE", "0") == "1"
# The language-model proposer (agent/proposer_llm.py). Default OFF. It is a
# hypothesis generator behind the same `Hypothesis` type as the enumerator,
# called at most LLM_MAX_CALLS_PER_LEVEL times per level — never per step —
# against any OpenAI-compatible server: Ollama locally, vLLM on Kaggle.
USE_LLM_PROPOSER = os.environ.get("ARC_LLM_PROPOSER", "0") == "1"
LLM_BASE_URL = os.environ.get("ARC_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
LLM_MODEL = os.environ.get("ARC_LLM_MODEL", "qwen3.5:4b")
LLM_API_KEY = os.environ.get("ARC_LLM_API_KEY", "local")
LLM_MAX_CALLS_PER_LEVEL = 3
# How many live hypotheses the policy keeps in play at once: the enumerator's
# best plus whatever the model returned. One step can test several of them
# when they share an action (`select_experiment`).
HYPOTHESIS_POOL = 6

# ── Environment (what resists me) ───────────────────────────────────────
# One failed attempt is enough to call a move blocked: these games are
# deterministic, so the same action from the same position gives the same
# result. Keyed by position, so if the move-map itself is wrong the damage
# is confined to that spot rather than disabling the action everywhere.
BLOCKED_MIN_OBSERVATIONS = 1

# A colour is treated as a rendered resource meter only if it shows the
# sawtooth: it falls during an attempt and returns to the same starting
# value on RESET. Decline alone is not enough — dc22 has a colour that
# moves monotonically all run because the player is filling the board in,
# which is progress, not budget. That distinction is load-bearing: a
# budget near zero means conserve, a drain near zero means nearly done.
STAMINA_MIN_ATTEMPTS = 1
STAMINA_DECLINE_RATIO = 5.0
STAMINA_START_TOLERANCE = 0.05
# Guards against two false positives seen in testing: a 3-cell colour
# oscillating (too small to be a meter), and a large background that
# depletes as the board fills and refills on reset (it never empties,
# whereas a real budget runs down to near zero before death).
STAMINA_MIN_SIZE = 8
STAMINA_MUST_EMPTY_TO = 0.25

# ── Reward weighting ────────────────────────────────────────────────────
# How much a level-up outweighs a mere frame change when weighting actions.
# Frame change is the dense signal (fires most steps, teaches "this action
# does *something*"); a level-up is the sparse one that actually matches
# what the competition scores, so it dominates when it ever fires.
LEVEL_UP_WEIGHT = 20.0

# An interaction — changing something *other than* ourselves — sits between
# "the frame changed at all" and "a level completed". Affecting the world is
# better evidence of progress than merely moving, but it is not the score.
INTERACTION_WEIGHT = 3.0

# A whole object vanishing is the closest thing to visible sub-goal
# progress: no API field reports partial progress, but games delete or
# hide sprites when a sub-goal is met (ls20 removes matched targets, vc33
# hides them). Ranked above a mere interaction, below an actual level-up.
VANISH_WEIGHT = 8.0
# Floor for "a whole object". Below this, drops are churn: ka59 shows 244
# one-cell drops. Used as `max(controlled_size, MIN_VANISH_CELLS)`, which
# is what makes our own vacated trail unable to register as a deletion —
# the trail is at most `controlled_size` cells, so it can never clear the
# floor. Do not lower this below the largest plausible controlled shape.
MIN_VANISH_CELLS = 8

# ── Attention (incentive salience) ──────────────────────────────────────
# Locations gain "wanting" by association with change that wasn't us or
# the budget meter, weighted higher for better evidence (mere residual <
# vanish < an actual level-up), and decaying so stale hotspots fade.
# Berridge & Robinson, "What is the role of dopamine in reward: hedonic
# impact, reward learning, or incentive salience?", 1998.
#
# Justified by measurement (docs/history.md, 2026-09-13): these sites
# cluster tightly rather than spreading uniformly — Clark-Evans R
# 0.39-0.52 against 1.0 for spatially random — so a map of them carries
# real information. On the games we score, 8-29 cells out of 4096 carry
# half the mass.
INTEREST_DECAY = 0.98
INTEREST_PRUNE_FLOOR = 0.05
INTEREST_RESIDUAL_WEIGHT = 1.0
INTEREST_VANISH_WEIGHT = 4.0
INTEREST_LEVEL_UP_WEIGHT = 15.0
# How many of the best-known cells to offer as click targets.
INTEREST_TOP_K = 5

# ── Navigation ──────────────────────────────────────────────────────────
# Router: BFS over displacement space toward the best interest cell, using
# the learned move map as edges and the obstacle map as removed edges.
# Bounded rather than exhaustive: displacement magnitude is naturally
# capped by the 64x64 board, but capping node expansion keeps the worst
# case bounded and cheap regardless. If the exact target isn't reachable
# (e.g. it doesn't sit on the move map's stride lattice), the router
# settles for the closest reachable node rather than refusing to move —
# the same graceful-degrade stance as every lens.
#
# WARNING before increasing the router's influence: measured across three
# configurations, *more routing makes the score worse*. It buys completion
# reliability (5/9 -> 7/8 non-zero sweeps) and costs score (mean 0.0511 ->
# 0.0164), because scoring is quadratic in speed and the interest map
# marks where things happened, not where the goal is. See docs/history.md,
# 2026-09-13.
ROUTE_MAX_NODES = 4000
