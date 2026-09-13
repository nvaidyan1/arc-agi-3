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

# ── Action selection ────────────────────────────────────────────────────
# Chance of ignoring the change-rate weighting and picking a legal action
# uniformly at random, so under-tried actions keep getting sampled.
EXPLORATION_EPSILON = 0.25

# ── Change layer ────────────────────────────────────────────────────────
# How many past steps' diffed cells to keep as "recently active" targets.
RECENT_DIFF_STEPS = 5

# ── Thing I control ─────────────────────────────────────────────────────
# Evidence needed before calling an action's effect a consistent "move":
# this many sightings of the same offset, and that share of all sightings.
# Deliberately conservative — on m0r0 ACTION1 splits 15/13 between two
# offsets and this correctly refuses to learn it.
MIN_MOVE_OBSERVATIONS = 3
MOVE_MAJORITY = 0.6

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
