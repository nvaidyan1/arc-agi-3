"""Your ARC-AGI-3 agent. This is the *only* file you should normally edit.

`scripts/build_notebook.py` splices the contents of this file into the
Kaggle submission notebook, so your local dev loop and your Kaggle
submission stay in lock-step:

    [edit my_agent.py] → [make play-local] → [make submit]

Governing principle — NO SEMANTIC SLOTS WITHOUT EVIDENCE:

    Every perceptual or semantic interpretation must be produced by a
    falsifiable test and may return None. General structure may constrain
    *how* hypotheses are represented and tested, but must not constrain
    *which* entities, goals, roles, or game types exist.

Concretely, every detector below is a *lens*: it asks whether some
specific explanation fits this change and reports nothing when it
doesn't. `_detect_translation` does not assert that games contain moving
objects; `meter_colour` does not assert that games have resource bars;
`acts_locally` stays None until there is evidence either way. **None is a
first-class outcome** — it is what keeps a game we have never seen from
being force-fit into the shape of the 25 we have. Game *type* is an
output, never an input: the router runs BFS because a move map and an
obstacle map were discovered, not because anything recognised a maze.
See docs/plan.md "Governing principle" for the full rationale.

Strategy: game-agnostic exploration. No per-game special-casing — the goal
is a policy that behaves reasonably on games it has never seen, which is
what the competition actually scores. Ideas, all driven only by what the
game itself reports each frame (see README.md "Game mechanics reference"):

  1. Only ever try actions the game currently reports as legal
     (`latest_frame.available_actions`) instead of guessing across all 7 —
     e.g. ls20 only exposes ACTION1-4, so trying ACTION5-7 there is wasted
     budget.
  2. Two layered reward signals per action, both feeding one weight:
     - *dense*: how often the action changes the frame at all. Fires most
       steps, so the policy keeps learning even while nothing is scored.
     - *sparse*: how often the action completed a level
       (`levels_completed`, which is what the competition actually
       scores). Weighted to dominate whenever it has ever fired, and
       deliberately remembered across RESETs — it's far too rare to
       afford forgetting, and which action makes progress is a property
       of the game rather than of one attempt.
     Epsilon-greedy on top, so under-tried actions still get sampled.
  3. Frame-diff signal: instead of collapsing "did the frame change" to a
     boolean, keep *which cells* changed. The one action with a payload
     (ACTION6, a grid click) targets cells that were recently part of a
     diff — "click near where things are happening" — falling back to
     cells that merely differ from the frame's most common color, and
     finally to a uniform random cell. Per-cell click memory on top:
     never-clicked cells are preferred, and cells that absorbed a click
     with no effect are skipped (habituation).
  4. The beginning of a *learned representation*, derived rather than
     assumed: per click we record whether the change landed on the cell
     we touched or somewhere else (`acts_locally`). Sampling three games
     showed a clean split — ft09 changes the clicked cell (and exactly
     38 cells each time), while vc33/tn36 never touch it and change 1-2
     cells elsewhere. Nothing here assumes the grid is a 2D space or
     that anything in it is an object; that structure is meant to emerge
     from correlated change, not be imposed. See docs/plan.md.
Go-Explore-style trajectory replay was built and then removed here — see
docs/plan.md "Tried and reverted." Short version: the engine already
checkpoints level progress across GAME_OVER (it calls `level_reset()`,
which preserves `_score`), and death is budget/lives exhaustion, so
replaying a failed trajectory only burns the new attempt's budget to
arrive back at a losing position.

Contract (enforced by the ARC-AGI-3-Agents framework):
  - Subclass `agents.agent.Agent`.
  - Class must be named `MyAgent` (the notebook's __init__.py registers it).
  - Implement `is_done(frames, latest_frame) -> bool`.
  - Implement `choose_action(frames, latest_frame) -> GameAction`.
"""
from __future__ import annotations

import logging
import random
import time
from collections import deque
from typing import Any

from arcengine import FrameData, GameAction, GameState

# When run inside the ARC-AGI-3-Agents framework (locally or on Kaggle)
# the `agents` package is on sys.path, so this import resolves.
from agents.agent import Agent

logger = logging.getLogger(__name__)

# Chance of ignoring the change-rate weighting and picking a legal action
# uniformly at random, so under-tried actions keep getting sampled.
EXPLORATION_EPSILON = 0.25

# How many past steps' diffed cells to keep as "recently active" targets.
RECENT_DIFF_STEPS = 5

# Evidence needed before calling an action's effect a consistent "move":
# this many sightings of the same offset, and that share of all sightings.
MIN_MOVE_OBSERVATIONS = 3
MOVE_MAJORITY = 0.6

# One failed attempt is enough to call a move blocked: these games are
# deterministic, so the same action from the same position gives the same
# result. Keyed by position, so if the move-map itself is wrong the damage
# is confined to that spot rather than disabling the action everywhere.
BLOCKED_MIN_OBSERVATIONS = 1

# A colour is treated as a rendered resource meter only if it shows the
# sawtooth: it falls during an attempt and returns to the same starting
# value on RESET. Decline alone is not enough — dc22 has a colour that
# moves monotonically all run because the player is filling the board in,
# which is progress, not budget.
METER_MIN_ATTEMPTS = 1
METER_DECLINE_RATIO = 5.0
METER_START_TOLERANCE = 0.05
# Guards against two false positives seen in testing: a 3-cell colour
# oscillating (too small to be a meter), and a large background that
# depletes as the board fills and refills on reset (it never empties,
# whereas a real budget runs down to near zero before death).
METER_MIN_SIZE = 8
METER_MUST_EMPTY_TO = 0.25

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
# Floor for "a whole object", used when no move map exists to compare
# against. Below this, drops are churn: ka59 shows 244 one-cell drops.
MIN_VANISH_CELLS = 8

# Incentive salience (region-of-interest) map: locations gain "wanting" by
# association with change that wasn't us or the budget meter, weighted
# higher for better evidence (mere residual < vanish < an actual
# level-up), and decaying so stale hotspots fade. Berridge & Robinson,
# "What is the role of dopamine in reward: hedonic impact, reward
# learning, or incentive salience?", 1998. Screened 2026-09-13 (see
# docs/history.md): sites cluster tightly (Clark-Evans R 0.39-0.52,
# 1.0=random) rather than spreading uniformly, so a map of them is more
# informative than "somewhere on the board".
INTEREST_DECAY = 0.98
INTEREST_PRUNE_FLOOR = 0.05
INTEREST_RESIDUAL_WEIGHT = 1.0
INTEREST_VANISH_WEIGHT = 4.0
INTEREST_LEVEL_UP_WEIGHT = 15.0
# How many of the best-known cells to offer as click targets.
INTEREST_TOP_K = 5

# Router: BFS over displacement space toward the best interest cell, using
# `learned_moves` as edges and `_blocked_moves` as removed edges. This is
# what makes the interest map (above) actually actionable on the movement
# games, rather than only steering ACTION6 clicks. Bounded rather than
# exhaustive: displacement magnitude is naturally capped by the 64x64
# board, but capping node expansion keeps a worst case bounded and cheap
# regardless. If the exact target cell isn't reachable (e.g. it doesn't
# sit on the move map's stride lattice), settles for the closest reachable
# node found within the cap rather than refusing to move at all — the
# same graceful-degrade-to-best-effort stance as the rest of this file.
ROUTE_MAX_NODES = 4000


def _chebyshev(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Chessboard distance — matches grid movement better than Euclidean,
    since a diagonal-capable move set shouldn't be penalised for it."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class MyAgent(Agent):
    """Explores by favoring actions/regions that visibly change the frame."""

    # Upper bound on actions per game. The framework's default was 80, but
    # that is a demo guard against infinite loops, NOT a competition rule —
    # no server- or gateway-side cap exists anywhere, and the framework's
    # own Playback class uses 1,000,000. At 80, ls20 (42 actions per life)
    # gets under two attempts, and measured completions were pure noise
    # (1 run of 2 produced any). At 400 both replicate runs produced
    # completions on 2 games. Raised deliberately; see docs/history.md.
    MAX_ACTIONS = 400

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Seed per game_id so replays from the same game are reproducible but
        # different games explore independently.
        seed = int(time.time() * 1_000_000) + hash(self.game_id) % 1_000_000
        random.seed(seed)
        # Level-ups are the sparse, high-value signal — deliberately NOT
        # reset per attempt, unlike everything in _reset_exploration_state.
        # Which action makes progress is a property of the game, not of one
        # attempt, and level-ups are far too rare to afford forgetting.
        self._action_level_ups: dict[GameAction, int] = {}
        # Contingency signature of the click action: does clicking change
        # the cell you clicked, or something elsewhere? Measured, never
        # assumed — the three games sampled so far split cleanly into
        # "acts locally" and "acts at a distance", and that's a property
        # of the game, so it persists across attempts like level-ups do.
        self._click_local = 0
        self._click_remote = 0
        # Per action, how often each movement offset was observed. This is
        # the "thing I control" layer: if one action reliably translates
        # the same shape by the same offset, that shape is what we move
        # and that offset is what the action does. Persists across RESETs
        # (a property of the game, not of one attempt).
        self._action_offsets: dict[GameAction, dict[tuple[int, int], int]] = {}
        self._announced_moves: set[GameAction] = set()
        # "Thing I affect": times an action changed something beyond our own
        # movement, and the positions where that happened. Persists across
        # RESETs — where the world reacts is a property of the level.
        self._action_interactions: dict[GameAction, int] = {}
        self._interaction_sites: dict[tuple[int, int], int] = {}
        # Change-type census (see `_classify_change`). Recorded but NOT
        # yet wired into action selection — the router taught us that
        # adding a new signal and changing decision logic in the same
        # pass makes a regression impossible to attribute. Validate the
        # lens against the known 31/53/16 baseline first, then decide
        # whether any of it deserves to influence behaviour.
        self._recolour_counts: dict[tuple[int, int], int] = {}
        self._cardinality_counts: dict[int, int] = {}
        # The empty canvas for this level, captured once from the first
        # frame seen rather than re-derived per frame.
        self._background: int | None = None
        self._change_steps = 0
        self._translation_steps = 0
        self._recolour_steps = 0
        self._cardinality_steps = 0
        # Sub-goal progress: whole objects disappearing. Persists across
        # RESETs like the other rare, high-value signals.
        self._action_vanishes: dict[GameAction, int] = {}
        self._controlled_size = 0
        self._pending_vanish = 0
        # Where a known move failed to happen, keyed by (position, action):
        # the environment layer — things that resist us. Survives RESET
        # (the level restarts from the same origin, so displacements stay
        # comparable) but is cleared on level change, since a new level is
        # a new layout. Position-keyed on purpose: a real obstacle blocks
        # at specific places, whereas a wrong move-map fails everywhere —
        # so the shape of this map is also its own validation.
        self._blocked_moves: dict[tuple[tuple[int, int], GameAction], int] = {}
        self._move_attempts: dict[tuple[tuple[int, int], GameAction], int] = {}
        self._map_level = 0
        # Incentive salience: per-pixel "wanting" accumulated from change
        # that wasn't us or the meter (see INTEREST_* above). Persists
        # across RESET within a level — same layout, so a spot that
        # mattered last attempt plausibly matters this one — cleared on
        # level change alongside the obstacle map, since a new level is a
        # new layout.
        self._interest: dict[tuple[int, int], float] = {}
        # Resource-meter detection. Per colour: the value it starts each
        # attempt at, and how often it fell vs rose. Spans attempts by
        # necessity — the sawtooth is only visible across a RESET.
        self._meter_starts: dict[int, list[int]] = {}
        self._meter_down: dict[int, int] = {}
        self._meter_up: dict[int, int] = {}
        self._colour_counts: dict[int, int] = {}
        self._meter_peak: dict[int, int] = {}
        self._meter_min: dict[int, int] = {}
        self._announced_meter = False
        self._reset_exploration_state()

    @property
    def meter_colour(self) -> int | None:
        """The colour that behaves like a depleting budget, if any.

        Requires the sawtooth: consistently falls during an attempt *and*
        returns to the same starting value on RESET.
        """
        best, best_start = None, 0
        for colour, starts in self._meter_starts.items():
            if len(starts) < METER_MIN_ATTEMPTS:
                continue
            down, up = self._meter_down.get(colour, 0), self._meter_up.get(colour, 0)
            if down < METER_DECLINE_RATIO * max(up, 1):
                continue
            mean_start = sum(starts) / len(starts)
            if mean_start < METER_MIN_SIZE:
                continue
            # Must actually run down, not merely fluctuate.
            if self._meter_min.get(colour, mean_start) > METER_MUST_EMPTY_TO * mean_start:
                continue
            spread = (max(starts) - min(starts)) / mean_start
            if spread > METER_START_TOLERANCE:
                continue
            # Prefer the largest such meter — finer resolution.
            if mean_start > best_start:
                best, best_start = colour, mean_start
        return best

    @property
    def budget_fraction(self) -> float | None:
        """How much of the attempt's budget is left, 0-1, or None."""
        colour = self.meter_colour
        if colour is None:
            return None
        starts = self._meter_starts[colour]
        full = sum(starts) / len(starts)
        return max(0.0, min(1.0, self._colour_counts.get(colour, 0) / full))
        self._reset_exploration_state()

    @property
    def learned_moves(self) -> dict[GameAction, tuple[int, int]]:
        """Actions whose effect is a consistent translation, and by what.

        Requires several observations and a clear majority, so a one-off
        coincidence doesn't get mistaken for control.
        """
        learned = {}
        for action, offsets in self._action_offsets.items():
            if not offsets:
                continue
            best, count = max(offsets.items(), key=lambda kv: kv[1])
            total = sum(offsets.values())
            if count >= MIN_MOVE_OBSERVATIONS and count / total >= MOVE_MAJORITY:
                learned[action] = best
        return learned

    @property
    def acts_locally(self) -> bool | None:
        """Whether clicking tends to change the clicked cell itself.

        None until there's evidence either way. This is the first piece of
        a learned representation of *what kind of thing the click is* —
        derived from contingency, with no assumption that the grid is a
        2D space or that anything in it is an object.
        """
        if not (self._click_local or self._click_remote):
            return None
        return self._click_local > self._click_remote

    def _reset_exploration_state(self) -> None:
        # (tries, frame-changes) per action, reset on every RESET since a
        # fresh level can behave differently from the one before it.
        self._action_tries: dict[GameAction, int] = {}
        self._action_changes: dict[GameAction, int] = {}
        # Per-cell click memory, for ACTION6. Deliberately per-cell rather
        # than per-coarse-region: measurement showed ~50% of clicks were
        # exact repeats of already-clicked cells, and that blacklisting a
        # whole 8x8 block after a few duds can rule out the one productive
        # cell inside it.
        self._click_tries: dict[tuple[int, int], int] = {}
        self._click_effect: dict[tuple[int, int], int] = {}
        # Rolling window of recent diffed-cell lists, newest last.
        self._recent_diffs: deque[list[tuple[int, int]]] = deque(
            maxlen=RECENT_DIFF_STEPS
        )
        # What we chose last call, so next call can credit/blame it against
        # the resulting frame (see note in choose_action on why this can't
        # be read back from the frame itself).
        self._last_action: GameAction | None = None
        self._last_click: tuple[int, int] | None = None
        # Set on the first frame of a fresh attempt, so colour counts seen
        # then are recorded as that attempt's starting values.
        self._attempt_started = False
        # Where the controlled shape has got to, relative to where this
        # attempt started, accumulated from observed translations — a
        # compact symbolic state derived from the learned move map. Reset
        # per attempt because the level restarts from its own origin.
        self._displacement = (0, 0)
        self._visited_displacements: set[tuple[int, int]] = {(0, 0)}
        # Absolute board position of the controlled shape (None until the
        # first translation is observed this attempt). Same offsets as
        # `_displacement`, different origin — this is what lets the router
        # compare against `_interest`, which is keyed in absolute pixels.
        self._anchor: tuple[int, int] | None = None
        # Queued actions toward the current router target, the target
        # itself (for reasoning/logging), and the displacement the plan
        # expects to be at right now — if reality doesn't match (a step
        # hit an obstacle the plan didn't know about), the remaining
        # actions were computed for positions we never reached, so the
        # plan is dropped rather than followed off course.
        self._route_plan: list[GameAction] = []
        self._route_target: tuple[int, int] | None = None
        self._route_expected_position: tuple[int, int] | None = None

    @property
    def name(self) -> str:
        return f"{super().name}.{self.MAX_ACTIONS}"

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        # Stop once we win. Don't stop on GAME_OVER — we want to RESET and retry.
        return latest_frame.state is GameState.WIN

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        # First call or after a death → reset the level.
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            self._reset_exploration_state()
            self._attempt_started = True
            return GameAction.RESET

        # Only consider actions the game currently says are legal.
        if latest_frame.available_actions:
            candidate_actions = [
                a
                for a in (
                    GameAction.from_id(i) for i in latest_frame.available_actions
                )
                if a is not GameAction.RESET
            ]
        else:
            candidate_actions = [a for a in GameAction if a is not GameAction.RESET]

        # Credit/blame the action *we* took last call: which cells actually
        # changed, if any (empty list == no-op). NOTE: we track this
        # ourselves rather than reading `latest_frame.action_input` — the
        # local framework's `_convert_raw_frame_data()` never populates
        # that field, it's always left at its default (RESET, no data).
        self._track_meter(latest_frame)

        # A new level is a new layout, so the obstacle map and our position
        # origin no longer mean anything.
        if latest_frame.levels_completed != self._map_level:
            self._map_level = latest_frame.levels_completed
            self._blocked_moves.clear()
            self._move_attempts.clear()
            self._interest.clear()
            self._displacement = (0, 0)
            self._visited_displacements = {(0, 0)}
            self._anchor = None
            self._route_plan = []
            self._route_target = None
            self._route_expected_position = None
            self._background = None  # new level, new canvas

        if len(frames) >= 2 and self._last_action is not None:
            prev_frame = frames[-2]
            self._decay_interest()
            diff_cells = self._diff_cells(prev_frame, latest_frame)
            moved = None
            # Position the last action was taken *from* — captured before
            # a successful move updates _displacement below.
            origin = self._displacement

            self._action_tries[self._last_action] = (
                self._action_tries.get(self._last_action, 0) + 1
            )
            if diff_cells:
                self._action_changes[self._last_action] = (
                    self._action_changes.get(self._last_action, 0) + 1
                )
                self._recent_diffs.append(diff_cells)

                # Object layer: was that change one shape translating? If
                # so, attribute the movement to the action that caused it.
                moved = self._detect_translation(prev_frame, latest_frame)
                if moved is not None:
                    _color, _size, offset, pre_move_anchor = moved
                    self._controlled_size = max(self._controlled_size, _size)
                    offsets = self._action_offsets.setdefault(self._last_action, {})
                    offsets[offset] = offsets.get(offset, 0) + 1
                    self._displacement = (
                        self._displacement[0] + offset[0],
                        self._displacement[1] + offset[1],
                    )
                    self._visited_displacements.add(self._displacement)
                    # Absolute board position of the controlled shape,
                    # re-derived from ground truth every time (rather than
                    # purely accumulated) so it can't silently drift: the
                    # router needs this to translate an `_interest` pixel
                    # target into the same relative-displacement space
                    # `learned_moves`/`_blocked_moves` already use.
                    self._anchor = (
                        pre_move_anchor[0] + offset[0],
                        pre_move_anchor[1] + offset[1],
                    )
                    if (
                        self._last_action in self.learned_moves
                        and self._last_action not in self._announced_moves
                    ):
                        self._announced_moves.add(self._last_action)
                        logger.info(
                            "LEARNED on %s: %s moves a %d-cell shape by %s",
                            self.game_id,
                            self._last_action.name,
                            _size,
                            offset,
                        )

            # "Thing I affect": whatever changed that our own movement and
            # the budget meter do not explain.
            # Fall back to what this action is *known* to do when the
            # strict whole-diff test fails — otherwise our own movement
            # goes unexplained and every step looks like an interaction.
            observed_offset = (
                moved[2] if moved else self.learned_moves.get(self._last_action)
            )
            # Computed unconditionally: with no known self (observed_offset
            # is None) there is nothing to subtract, so this *is* the whole
            # diff minus the meter — exactly right for a game with no
            # controllable movement, where every change is "other than
            # self" by construction. Gating this behind a move map, as
            # before, left the region-of-interest map structurally blind
            # on exactly the copy/match family: measured 0.0% on
            # ft09/sb26/cd82/tn36 (docs/history.md, 2026-09-13).
            residual = self._residual_cells(
                prev_frame, latest_frame, diff_cells, observed_offset
            )
            # The *reward* term stays gated on knowing our own movement —
            # crediting "changed something" before subtracting self would
            # double-count ordinary frame-change on games with a move map.
            if residual and observed_offset is not None:
                self._action_interactions[self._last_action] = (
                    self._action_interactions.get(self._last_action, 0) + 1
                )
                self._interaction_sites[origin] = (
                    self._interaction_sites.get(origin, 0) + 1
                )
            if residual:
                self._bump_interest(residual, INTEREST_RESIDUAL_WEIGHT)

            # Change-type census. `diff_cells - residual` is exactly the
            # cells another lens already accounted for (our own movement,
            # and the budget meter ticking), so subtracting it keeps the
            # meter's steady drain from swamping the cardinality count
            # and stops two lenses claiming the same pixels.
            self._pending_vanish = 0
            vanish_cells: set[tuple[int, int]] = set()
            if diff_cells:
                self._change_steps += 1
                if moved is not None:
                    self._translation_steps += 1
                classified = self._classify_change(
                    prev_frame,
                    latest_frame,
                    set(diff_cells) - set(residual),
                    self._background,
                )
                if classified is not None:
                    recolours, cardinality, lost_cells = classified
                    if recolours:
                        self._recolour_steps += 1
                        for key, count in recolours.items():
                            self._recolour_counts[key] = (
                                self._recolour_counts.get(key, 0) + count
                            )
                    if cardinality:
                        self._cardinality_steps += 1
                        for colour, delta in cardinality.items():
                            self._cardinality_counts[colour] = (
                                self._cardinality_counts.get(colour, 0) + delta
                            )
                    # Sub-goal signal, now derived per cell rather than
                    # from whole-board histograms. A colour is only
                    # treated as having *vanished* if it lost more than a
                    # whole object's worth in one step: below that it is
                    # churn (ka59 produces 244 one-cell drops). Our own
                    # shape sliding over something can no longer be
                    # mistaken for a deletion — that lands in `recolours`
                    # (content over content), not here.
                    floor = max(self._controlled_size, MIN_VANISH_CELLS)
                    vanished = sum(
                        -delta
                        for delta in cardinality.values()
                        if delta < 0 and -delta > floor
                    )
                    if vanished:
                        self._pending_vanish = vanished
                        vanish_cells = lost_cells

            if self._pending_vanish:
                self._action_vanishes[self._last_action] = (
                    self._action_vanishes.get(self._last_action, 0) + 1
                )
                # Bump exactly where content was destroyed, not across
                # every residual cell — the old signal had no positions to
                # offer, so it had to smear the credit.
                self._bump_interest(sorted(vanish_cells), INTEREST_VANISH_WEIGHT)

            # Environment layer: an action with a known effect that failed
            # to produce it. Deliberately covers both "nothing changed"
            # and "something changed but the shape didn't move" —
            # measured at 16% and 44% of predicted moves, and on ls20 the
            # latter dominates (bump a wall, the shape stays put and a
            # counter ticks), so treating only silence as blocked would
            # miss most of it. Checked outside the `if diff_cells` branch
            # for exactly that reason.
            expected = self.learned_moves.get(self._last_action)
            if expected is not None:
                key = (origin, self._last_action)
                self._move_attempts[key] = self._move_attempts.get(key, 0) + 1
                if not self._expected_move_occurred(
                    prev_frame, latest_frame, expected
                ):
                    self._blocked_moves[key] = self._blocked_moves.get(key, 0) + 1

            # The signal that actually matches what's scored: did that
            # action complete a level? Rare enough that we surface it
            # loudly rather than letting it vanish into the stats.
            if latest_frame.levels_completed > prev_frame.levels_completed:
                self._action_level_ups[self._last_action] = (
                    self._action_level_ups.get(self._last_action, 0) + 1
                )
                logger.info(
                    "LEVEL UP on %s via %s -> levels_completed=%d",
                    self.game_id,
                    self._last_action.name,
                    latest_frame.levels_completed,
                )
                # Strongest possible credit, at whatever changed — falling
                # back to the raw diff (rather than residual) covers a
                # level-up reached by pure movement, where residual can be
                # empty because the whole change is explained as self.
                self._bump_interest(residual or diff_cells, INTEREST_LEVEL_UP_WEIGHT)

            if self._last_action is GameAction.ACTION6 and self._last_click is not None:
                self._click_tries[self._last_click] = (
                    self._click_tries.get(self._last_click, 0) + 1
                )
                if diff_cells:
                    self._click_effect[self._last_click] = self._click_effect.get(
                        self._last_click, 0
                    ) + len(diff_cells)
                    # Did we change what we touched, or something else?
                    if self._last_click in set(diff_cells):
                        self._click_local += 1
                    else:
                        self._click_remote += 1

        # Once we know what each action does to the shape we control, we
        # can explore *its position space* rather than wander: prefer a
        # move that lands somewhere this attempt hasn't been. Only applies
        # where a move map was actually learned, so non-spatial games are
        # unaffected.
        moves = self.learned_moves
        # Don't spend budget walking into something we've already learned
        # resists us here. Only drop blocked actions while alternatives
        # remain, so we never end up with nothing to pick.
        unblocked = [a for a in candidate_actions if not self._is_blocked(a)]
        if unblocked:
            candidate_actions = unblocked

        novel_moves = [
            a
            for a in candidate_actions
            if a in moves
            and (
                self._displacement[0] + moves[a][0],
                self._displacement[1] + moves[a][1],
            )
            not in self._visited_displacements
        ]

        # Router vs frontier: these now *compete* rather than the router
        # sitting permanently beneath the frontier. Measured reason: under
        # strict frontier-first ordering the router fired on only 3.0% of
        # steps across 25 games, because `_visited_displacements` resets
        # every attempt so the frontier almost never runs dry and the
        # router tier was rarely reached at all (docs/history.md,
        # 2026-09-13). A signal nothing can act on cannot move the score.
        #
        # The router wins when its target is *well evidenced* — the best
        # interest cell carrying at least a sub-goal's worth of weight
        # (INTEREST_VANISH_WEIGHT) rather than a single residual bump.
        # That threshold is deliberately one of the existing weights
        # rather than a new tuned constant: "something meaningful happened
        # there", not "something changed there". Below that bar the
        # frontier still wins, so ordinary exploration is unaffected.
        #
        # The `proven_action_exists` gate below is untouched and still
        # outranks all of this: once an action has actually earned a
        # level-up or vanish, the reward-weighted branch must win, which
        # is what fixed the earlier regression where an unconditional
        # router preempted the only channel that ever produced a
        # completion.
        if self._route_plan and (
            self._route_plan[0] not in candidate_actions
            or self._displacement != self._route_expected_position
        ):
            # Either the next planned action is no longer legal, or a
            # prior step didn't land where the plan assumed (a newly
            # discovered obstacle) — either way the rest of the plan was
            # computed for positions we never reached.
            self._route_plan = []
        # Route only while we have no proven-valuable action yet. Once
        # something has ever earned a level-up or vanish credit, that
        # signal must win the weighted branch below every time — those are
        # the only channels that have ever produced a real completion, and
        # an unconditional router was measured crowding them out entirely
        # (a regression: every one of 25 games scored 0, including sp80,
        # which completed in 4 of 5 runs before this gate existed).
        # Vanishes stay in this gate, and the reason is counter-intuitive
        # enough to be worth recording. Dropping them (keeping only
        # level-ups) was tried and measured: router engagement rose
        # 3.6% -> 5.8% and completions got *more reliable* (7/8 sweeps
        # non-zero vs 5/9) — yet mean score fell 0.0511 -> 0.0164 and the
        # max fell 0.1485 -> 0.0639. Scoring is
        # `(baseline/actions)**2 * 100`, so completing more often but
        # slower loses badly: for sp80 a 4x speed difference is a 16x
        # score difference. Routing walks toward the *interest map*, which
        # marks where things happened, not where the goal is — so more of
        # it buys reliability at the cost of the speed the score actually
        # pays for. See docs/history.md, 2026-09-13.
        proven_action_exists = bool(
            self._action_level_ups or self._action_vanishes
        )
        if proven_action_exists and self._route_plan:
            self._route_plan = []  # evidence arrived mid-plan; stop routing
        # Plan whenever we have no plan — no longer conditional on the
        # frontier being exhausted, which is what starved this entirely.
        if not self._route_plan and not proven_action_exists:
            self._route_plan = self._plan_route() or []
            if self._route_plan:
                self._route_target = self._top_interest_cells[0]

        # Is the target worth preferring over covering new ground?
        strong_route = bool(
            self._route_plan
            and self._interest
            and max(self._interest.values()) >= INTEREST_VANISH_WEIGHT
        )

        # Note neither the epsilon nor the frontier branch clears the plan
        # any more. If they move us off it, the drift check at the top of
        # the next call notices `_displacement` isn't where the plan
        # expected and drops it then — and if their move was blocked, we
        # are still where the plan expected and it correctly survives.
        if random.random() < EXPLORATION_EPSILON:
            action = random.choice(candidate_actions)
        elif strong_route:
            action = self._route_plan.pop(0)
            self._route_expected_position = (
                self._displacement[0] + moves[action][0],
                self._displacement[1] + moves[action][1],
            )
            action.reasoning = (
                f"router: {action.name} to well-evidenced interest cell "
                f"{self._route_target} (weight "
                f"{max(self._interest.values()):.1f}), "
                f"{len(self._route_plan)} steps left"
            )
            self._last_click = None
            self._last_action = action
            return action
        elif novel_moves:
            action = random.choice(novel_moves)
            action.reasoning = (
                f"frontier: {action.name} moves {moves[action]} to unvisited "
                f"displacement from {self._displacement}"
            )
            self._last_click = None
            self._last_action = action
            return action
        elif self._route_plan:
            action = self._route_plan.pop(0)
            self._route_expected_position = (
                self._displacement[0] + moves[action][0],
                self._displacement[1] + moves[action][1],
            )
            action.reasoning = (
                f"router: {action.name} heading to interest cell "
                f"{self._route_target}, {len(self._route_plan)} steps left"
            )
            self._last_click = None
            self._last_action = action
            return action
        else:
            # Laplace-smoothed value per action, combining both signals:
            # frame changes (dense — fires most steps, keeps the policy
            # learning when nothing is being scored) plus level-ups
            # (sparse, but the only thing that matches the actual score,
            # so weighted to dominate whenever it has ever fired).
            weights = [
                (
                    self._action_changes.get(a, 0)
                    + INTERACTION_WEIGHT * self._action_interactions.get(a, 0)
                    + VANISH_WEIGHT * self._action_vanishes.get(a, 0)
                    + LEVEL_UP_WEIGHT * self._action_level_ups.get(a, 0)
                    + 1
                )
                / (self._action_tries.get(a, 0) + 2)
                for a in candidate_actions
            ]
            action = random.choices(candidate_actions, weights=weights, k=1)[0]

        if action.is_complex():
            # ACTION6 takes (x, y) coordinates on a 64×64 grid.
            x, y, why = self._pick_coordinate(latest_frame)
            action.set_data({"x": x, "y": y})
            action.reasoning = {
                "why": why,
                # Learned, not assumed: does clicking change what you
                # touched, or something elsewhere? None until known.
                "acts_locally": self.acts_locally,
                "clicked_cells": len(self._click_tries),
            }
            self._last_click = (x, y)
        else:
            tries = self._action_tries.get(action, 0)
            changes = self._action_changes.get(action, 0)
            level_ups = self._action_level_ups.get(action, 0)
            budget = self.budget_fraction
            action.reasoning = (
                f"exploration: {action.name} tried={tries} "
                f"changed={changes} level_ups={level_ups}"
                + (f" budget={budget:.2f}" if budget is not None else "")
            )
            self._last_click = None
        self._last_action = action
        return action

    @staticmethod
    def _expected_move_occurred(
        prev_frame: FrameData, latest_frame: FrameData, offset: tuple[int, int]
    ) -> bool:
        """Did *any* coloured component shift by exactly `offset`?

        Deliberately weaker than `_detect_translation`, which demands the
        entire diff be that one translation. Measured: the strict test
        misses ~4% of real moves (because something else changed in the
        same step), and every one of those would otherwise be recorded as
        a false obstacle.
        """
        if not prev_frame.frame or not latest_frame.frame:
            return False
        dx, dy = offset
        lost, gained = MyAgent._lost_and_gained(prev_frame, latest_frame)
        for color, source in lost.items():
            target = gained.get(color)
            if target and any((x + dx, y + dy) in target for x, y in source):
                return True
        return False

    def _track_meter(self, latest_frame: FrameData) -> None:
        """Update per-colour cell counts and the rise/fall tallies."""
        if not latest_frame.frame:
            return
        counts: dict[int, int] = {}
        for row in latest_frame.frame[-1]:
            for value in row:
                counts[value] = counts.get(value, 0) + 1

        # The canvas, fixed at what it was before we started changing
        # things. Deliberately not re-derived per frame — see the note in
        # `_classify_change` on ft09, where a per-frame argmax background
        # silently flips once painted content outgrows the canvas.
        if self._background is None and counts:
            self._background = max(counts, key=counts.get)

        # Look for the sawtooth in the series itself rather than keying off
        # our own RESET: ls20 refills its meter internally (per life), with
        # no GAME_OVER, so refills tied to RESET would never be seen.
        for colour in set(counts) | set(self._colour_counts):
            n = counts.get(colour, 0)
            previous = self._colour_counts.get(colour)
            if previous is None:
                continue
            peak = self._meter_peak.get(colour, previous)
            self._meter_peak[colour] = max(peak, n)
            self._meter_min[colour] = min(self._meter_min.get(colour, n), n)
            if n < previous:
                self._meter_down[colour] = self._meter_down.get(colour, 0) + 1
            elif n > previous:
                # A jump back up to near the observed peak is a refill —
                # the second half of the sawtooth. Anything smaller is
                # ordinary gameplay noise.
                if peak and (n - previous) >= 0.5 * peak:
                    self._meter_starts.setdefault(colour, []).append(n)
                else:
                    self._meter_up[colour] = self._meter_up.get(colour, 0) + 1

        # The sub-goal (vanish) signal used to be computed here from
        # whole-board colour histograms. It now comes from
        # `_classify_change`'s per-cell cardinality loss instead — see
        # `choose_action`. Histograms could only say "colour C has fewer
        # cells than last step", which conflates a deleted object with our
        # own shape sliding over one, and cannot say *where* it happened.

        # Keep zeros rather than dropping absent colours: a meter that
        # empties disappears from the histogram, and forgetting it here
        # would make the refill that follows look like a first sighting.
        self._colour_counts = {
            colour: counts.get(colour, 0)
            for colour in set(counts) | set(self._colour_counts)
        }

        if not self._announced_meter and self.meter_colour is not None:
            self._announced_meter = True
            colour = self.meter_colour
            logger.info(
                "METER on %s: colour %d starts at ~%d each attempt and depletes",
                self.game_id,
                colour,
                sum(self._meter_starts[colour]) / len(self._meter_starts[colour]),
            )

    def _residual_cells(
        self,
        prev_frame: FrameData,
        latest_frame: FrameData,
        diff_cells: list[tuple[int, int]],
        offset: tuple[int, int] | None,
    ) -> list[tuple[int, int]]:
        """Changed cells NOT explained by our own shape moving.

        The "thing I affect" layer: subtract self (the translation we
        caused) and the budget meter (which ticks on its own schedule),
        and whatever is left is something else we acted upon. Nothing
        here assumes what that something is.
        """
        if not diff_cells:
            return []
        explained: set[tuple[int, int]] = set()
        if offset is not None and prev_frame.frame and latest_frame.frame:
            dx, dy = offset
            lost, gained = self._lost_and_gained(prev_frame, latest_frame)
            for colour, source in lost.items():
                target = gained.get(colour)
                if not target:
                    continue
                moved = {p for p in source if (p[0] + dx, p[1] + dy) in target}
                if moved:
                    explained |= moved
                    explained |= {(x + dx, y + dy) for x, y in moved}

        meter = self.meter_colour
        residual = []
        for cell in diff_cells:
            if cell in explained:
                continue
            if meter is not None and prev_frame.frame and latest_frame.frame:
                x, y = cell
                # Depletion recolours meter cells *away* from the meter
                # colour, so check both sides of the change, not just the
                # new value.
                if meter in (prev_frame.frame[-1][y][x], latest_frame.frame[-1][y][x]):
                    continue  # the budget ticking down, not something we hit
            residual.append(cell)
        return residual

    def _bump_interest(self, cells: list[tuple[int, int]], weight: float) -> None:
        """Add incentive salience at `cells`. See INTEREST_* above."""
        for cell in cells:
            self._interest[cell] = self._interest.get(cell, 0.0) + weight

    def _decay_interest(self) -> None:
        """Age the interest map by one step; drop entries once negligible.

        Called once per real step (not per bump) so hotspots fade with
        time regardless of how many signals fired that step, and so the
        map stays bounded (at most 4096 cells on a 64x64 grid either way,
        but pruning keeps lookups and the top-K scan cheap).
        """
        dead = []
        for cell, value in self._interest.items():
            value *= INTEREST_DECAY
            if value < INTEREST_PRUNE_FLOOR:
                dead.append(cell)
            else:
                self._interest[cell] = value
        for cell in dead:
            del self._interest[cell]

    @property
    def _top_interest_cells(self) -> list[tuple[int, int]]:
        """The best-known cells, highest salience first. Empty if none."""
        if not self._interest:
            return []
        ranked = sorted(self._interest.items(), key=lambda kv: kv[1], reverse=True)
        return [cell for cell, _ in ranked[:INTEREST_TOP_K]]

    def _is_blocked(self, action: GameAction) -> bool:
        """Is this action known not to work from where we currently are?"""
        return self._blocked_at(self._displacement, action)

    def _blocked_at(self, position: tuple[int, int], action: GameAction) -> bool:
        """Is this action known not to work from an arbitrary position?

        Same rule as `_is_blocked`, parameterised — the router needs to
        ask this about positions it hasn't reached yet while planning.
        """
        return (
            self._blocked_moves.get((position, action), 0)
            >= BLOCKED_MIN_OBSERVATIONS
        )

    def _plan_route(self) -> list[GameAction] | None:
        """BFS toward the best-known region of interest, in move-map space.

        Returns a list of actions from the current `_displacement` toward
        (or as close as reachable to) the pixel target, or None if there
        is no target, no move map, or no known board position yet.

        Bridges two coordinate systems that share the same offsets but
        different origins: `_interest` is keyed in absolute board pixels,
        while `learned_moves`/`_blocked_moves` are keyed relative to this
        attempt's start. `_anchor - _displacement` recovers that shared
        origin (the board position where `_displacement` was (0, 0)),
        letting the pixel target be re-expressed in displacement space.
        """
        moves = self.learned_moves
        if self._anchor is None or not moves or not self._interest:
            return None

        target_pixel = self._top_interest_cells[0]
        origin_anchor = (
            self._anchor[0] - self._displacement[0],
            self._anchor[1] - self._displacement[1],
        )
        target = (
            target_pixel[0] - origin_anchor[0],
            target_pixel[1] - origin_anchor[1],
        )

        start = self._displacement
        if start == target:
            return None  # already there; nothing to route

        # BFS, since edges are unweighted (every action costs one step).
        # Tracks the best (closest-to-target) node seen in case the exact
        # target sits off the reachable lattice.
        frontier = deque([start])
        came_from: dict[tuple[int, int], tuple[tuple[int, int], GameAction]] = {}
        visited = {start}
        best, best_dist = start, _chebyshev(start, target)
        expanded = 0

        while frontier and expanded < ROUTE_MAX_NODES:
            node = frontier.popleft()
            expanded += 1
            if node == target:
                best = node
                break
            for action, offset in moves.items():
                nxt = (node[0] + offset[0], node[1] + offset[1])
                if nxt in visited or self._blocked_at(node, action):
                    continue
                visited.add(nxt)
                came_from[nxt] = (node, action)
                frontier.append(nxt)
                dist = _chebyshev(nxt, target)
                if dist < best_dist:
                    best, best_dist = nxt, dist

        if best == start:
            return None  # nothing reachable got any closer

        path: list[GameAction] = []
        node = best
        while node in came_from:
            node, action = came_from[node]
            path.append(action)
        path.reverse()
        return path

    @staticmethod
    def _classify_change(
        prev_frame: FrameData,
        latest_frame: FrameData,
        explained: set[tuple[int, int]] | None = None,
        background: int | None = None,
    ) -> tuple[
        dict[tuple[int, int], int], dict[int, int], set[tuple[int, int]]
    ] | None:
        """Name the change types translation doesn't cover.

        Returns `(recolours, cardinality, lost_cells)`, or None if there's
        nothing to classify:
          `recolours`   {(from_colour, to_colour): cell_count} — a thing
                        at a fixed position changed identity.
          `cardinality` {colour: signed_delta} — content appeared
                        (positive) or disappeared (negative) relative to
                        the empty canvas.
          `lost_cells`  the positions where content became canvas. This
                        is the sub-goal signal, and unlike the whole-board
                        histogram it replaces, it says *where* — so the
                        salience bump can land on the cells that actually
                        emptied rather than on every residual cell.

        Motivation: classifying 533 transitions across 8 games found
        translation is only **31%** of what games actually do —
        recolour-in-place is **53%** (vc33 97%) and cardinality-change
        **16%** (ft09 98%), with the three together covering 99%. Only
        translation had a lens; this adds the other two, so ~69% of
        transitions stop being anonymous diff cells.

        The discriminator is the background colour, which is exactly the
        rule the vanish-detector fix already relies on (docs/history.md,
        2026-09-13): a change *touching the background* creates or
        destroys content, while a change *between two non-background
        colours* merely relabels something that was already there and is
        still there.

        `background` is passed in rather than derived per frame, and that
        matters more than it looks: deriving it as "the most common colour
        right now" makes the classification flip when content grows enough
        to outvote the canvas. Measured across all 25 games — 24 are
        stable, but **dc22 disagrees on 37.4% of steps** (argmax
        oscillating between colours 3 and 4), which is exactly the game
        whose mechanic is filling the board in, so the fill eventually
        outvotes the canvas. The caller supplies the level's *initial*
        mode instead (see `self._background`): the canvas as it was
        before we touched it. Falls back to per-frame argmax only when
        the caller has none yet.

        Note the taxonomy this implements is deliberately *narrower* than
        the manual 533-transition study's. ft09 toggles two foreground
        colours back and forth (9->8 468 cells, 8->9 432 cells, over a
        stable background of 5); the study counted that as
        cardinality-change because per-colour totals move, this counts it
        as recolour because nothing was created or destroyed. Same
        distinction that fixed the vanish false-positive.

        Like every other lens here this is a *test*, not an assertion: a
        game whose changes are entirely translations yields empty dicts
        rather than a forced classification, and `explained` lets the
        caller subtract cells another lens already accounted for so the
        same pixels aren't claimed twice.
        """
        if not prev_frame.frame or not latest_frame.frame:
            return None
        prev_grid, latest_grid = prev_frame.frame[-1], latest_frame.frame[-1]

        if background is None:
            counts: dict[int, int] = {}
            for row in latest_grid:
                for value in row:
                    counts[value] = counts.get(value, 0) + 1
            if not counts:
                return None
            background = max(counts, key=counts.get)

        explained = explained or set()
        recolours: dict[tuple[int, int], int] = {}
        cardinality: dict[int, int] = {}
        lost_cells: set[tuple[int, int]] = set()
        for y, (prev_row, latest_row) in enumerate(zip(prev_grid, latest_grid)):
            for x, (prev_val, latest_val) in enumerate(zip(prev_row, latest_row)):
                if prev_val == latest_val or (x, y) in explained:
                    continue
                if prev_val == background:
                    # Canvas -> content: something came into existence.
                    cardinality[latest_val] = cardinality.get(latest_val, 0) + 1
                elif latest_val == background:
                    # Content -> canvas: something ceased to exist.
                    cardinality[prev_val] = cardinality.get(prev_val, 0) - 1
                    lost_cells.add((x, y))
                else:
                    key = (prev_val, latest_val)
                    recolours[key] = recolours.get(key, 0) + 1

        if not recolours and not cardinality:
            return None
        return recolours, cardinality, lost_cells

    @staticmethod
    def _lost_and_gained(
        prev_frame: FrameData, latest_frame: FrameData
    ) -> tuple[dict[int, set[tuple[int, int]]], dict[int, set[tuple[int, int]]]]:
        """Per colour, the cells that stopped being it and started being it.

        The shared substrate under every correspondence question we ask:
        translation, blocked-move confirmation, residual, and recolour /
        cardinality classification all start from exactly this. Extracted
        because four copies of the same nested loop is four places for a
        fix to have to land.

        Note both dicts are keyed by *colour at that side of the change*:
        a cell that went 3 -> 7 appears in `lost[3]` and `gained[7]`, so a
        colour can appear in one, the other, or both.
        """
        lost: dict[int, set[tuple[int, int]]] = {}
        gained: dict[int, set[tuple[int, int]]] = {}
        if not prev_frame.frame or not latest_frame.frame:
            return lost, gained
        for y, (prev_row, latest_row) in enumerate(
            zip(prev_frame.frame[-1], latest_frame.frame[-1])
        ):
            for x, (prev_val, latest_val) in enumerate(zip(prev_row, latest_row)):
                if prev_val != latest_val:
                    lost.setdefault(prev_val, set()).add((x, y))
                    gained.setdefault(latest_val, set()).add((x, y))
        return lost, gained

    @staticmethod
    def _detect_translation(
        prev_frame: FrameData, latest_frame: FrameData
    ) -> tuple[int, int, tuple[int, int], tuple[int, int]] | None:
        """Is this frame-to-frame change one colored shape *moving*?

        Returns (color, cell_count, (dx, dy), anchor) if the entire set of
        cells that lost colour C is exactly the set that gained colour C,
        displaced by a single consistent offset — otherwise None. `anchor`
        is the shape's pre-move reference cell (its lexicographically
        smallest cell), which is what lets the caller reconstruct an
        absolute board position from a chain of relative offsets — see
        `self._anchor` in `choose_action`.

        This is the object layer, derived rather than assumed (Gestalt
        common fate: things that change together are one thing). Note it
        makes no prior commitment to 2D space or to anything being an
        object: it *tests* whether a translation explains the change, and
        reports nothing when it doesn't, so a non-spatial game simply
        yields no detections instead of a wrong ontology.
        """
        if not prev_frame.frame or not latest_frame.frame:
            return None

        lost, gained = MyAgent._lost_and_gained(prev_frame, latest_frame)

        for color, source in lost.items():
            target = gained.get(color)
            if not target or len(target) != len(source):
                continue
            # Anchor on each set's lexicographically smallest cell to get
            # the single candidate offset, then require an exact match.
            (sx, sy), (tx, ty) = min(source), min(target)
            offset = (tx - sx, ty - sy)
            if {(x + offset[0], y + offset[1]) for x, y in source} == target:
                return color, len(source), offset, (sx, sy)
        return None

    @staticmethod
    def _diff_cells(
        prev_frame: FrameData, latest_frame: FrameData
    ) -> list[tuple[int, int]]:
        """(x, y) cells that differ between two frames' settled state.

        `FrameData.frame` is NOT a stack of spatial layers — it's the
        animation sub-frames produced *within* one action (the engine
        loops step()+render until the action completes). So `frame[-1]`
        is the settled state the action produced and `frame[0]` is
        mid-animation. Measured: only ~10% of steps animate at all, but
        on a heavily animated game (tu93, 61% of steps) reading frame[0]
        drops move-map consistency to 21-29% versus 43-64% for frame[-1],
        because it compares windows offset by a partial action.
        """
        if not prev_frame.frame or not latest_frame.frame:
            return []
        prev_grid, latest_grid = prev_frame.frame[-1], latest_frame.frame[-1]
        return [
            (x, y)
            for y, (prev_row, latest_row) in enumerate(zip(prev_grid, latest_grid))
            for x, (prev_val, latest_val) in enumerate(zip(prev_row, latest_row))
            if prev_val != latest_val
        ]

    def _cell_is_spent(self, cell: tuple[int, int]) -> bool:
        """Clicked before and never did anything — habituated, skip it."""
        return (
            self._click_tries.get(cell, 0) > 0
            and self._click_effect.get(cell, 0) == 0
        )

    def _pick_coordinate(self, latest_frame: FrameData) -> tuple[int, int, str]:
        """Pick a click target and say why, most to least preferred:

        0. A learned region of interest (`_top_interest_cells`) — places
           incentive salience has accumulated across this level's
           attempts (residual change, sub-goal vanishes, level-ups).
           Empty until evidence exists, so this changes nothing early on.
        1. A cell that was part of a recent diff (something is happening
           there) and also differs from the current background color.
        2. Any recently-diffed cell.
        3. Any cell that differs from the frame's most common color.
        4. A uniform random cell.

        Within a tier, cells that have already absorbed a click with no
        effect are dropped entirely (habituation), and never-clicked cells
        are preferred over ones already tried — measurement showed ~half
        of all clicks were exact repeats, which is pure waste against a
        finite per-attempt budget.
        """
        if not latest_frame.frame:
            return random.randint(0, 63), random.randint(0, 63), "no frame yet"

        grid = latest_frame.frame[-1]
        counts: dict[int, int] = {}
        for row in grid:
            for value in row:
                counts[value] = counts.get(value, 0) + 1
        background = max(counts, key=counts.get)

        color_salient = {
            (x, y)
            for y, row in enumerate(grid)
            for x, value in enumerate(row)
            if value != background
        }
        recent_active = [cell for diff in self._recent_diffs for cell in diff]

        # Learned region of interest goes first regardless of the
        # acts_locally split below: it is not about whether clicking
        # affects what's under the cursor, it's about which locations have
        # a track record of mattering (see INTEREST_* / _bump_interest).
        ranked: list[tuple[list[tuple[int, int]], str]] = [
            (self._top_interest_cells, "learned region of interest"),
        ]
        if self.acts_locally is False:
            # Clicking here changes something *elsewhere*, so the cells
            # that changed are the effect, not the cause — aiming at them
            # is a category error. Cover new ground instead. (First place
            # the learned contingency signature changes what we do.)
            ranked += [
                (list(color_salient), "non-background cell (acts at a distance)"),
                (recent_active, "recently active cell"),
            ]
        else:
            ranked += [
                (
                    [c for c in recent_active if c in color_salient],
                    "recently active + non-background cell",
                ),
                (recent_active, "recently active cell"),
                (list(color_salient), "non-background cell"),
            ]
        for candidates, why in ranked:
            live = [c for c in candidates if not self._cell_is_spent(c)]
            if not live:
                continue
            # Prefer cells we've never clicked before; only fall back to
            # re-clicking productive ones once the fresh ones run out.
            fresh = [c for c in live if c not in self._click_tries]
            if fresh:
                return (*random.choice(fresh), f"{why} (unclicked)")
            return (*random.choice(live), f"{why} (revisit)")

        return random.randint(0, 63), random.randint(0, 63), "random fallback"
