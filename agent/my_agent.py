"""Your ARC-AGI-3 agent. This is the *only* file you should normally edit.

`scripts/build_notebook.py` splices the contents of this file into the
Kaggle submission notebook, so your local dev loop and your Kaggle
submission stay in lock-step:

    [edit my_agent.py] → [make play-local] → [make submit]

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


class MyAgent(Agent):
    """Explores by favoring actions/regions that visibly change the frame."""

    # Upper bound on actions per game; the framework also enforces global limits.
    MAX_ACTIONS = 80

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
            self._displacement = (0, 0)
            self._visited_displacements = {(0, 0)}

        if len(frames) >= 2 and self._last_action is not None:
            prev_frame = frames[-2]
            diff_cells = self._diff_cells(prev_frame, latest_frame)
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
                    _color, _size, offset = moved
                    offsets = self._action_offsets.setdefault(self._last_action, {})
                    offsets[offset] = offsets.get(offset, 0) + 1
                    self._displacement = (
                        self._displacement[0] + offset[0],
                        self._displacement[1] + offset[1],
                    )
                    self._visited_displacements.add(self._displacement)
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

        if random.random() < EXPLORATION_EPSILON:
            action = random.choice(candidate_actions)
        elif novel_moves:
            action = random.choice(novel_moves)
            action.reasoning = (
                f"frontier: {action.name} moves {moves[action]} to unvisited "
                f"displacement from {self._displacement}"
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
        lost: dict[int, set[tuple[int, int]]] = {}
        gained: dict[int, set[tuple[int, int]]] = {}
        for y, (prev_row, latest_row) in enumerate(
            zip(prev_frame.frame[-1], latest_frame.frame[-1])
        ):
            for x, (prev_val, latest_val) in enumerate(zip(prev_row, latest_row)):
                if prev_val != latest_val:
                    lost.setdefault(prev_val, set()).add((x, y))
                    gained.setdefault(latest_val, set()).add((x, y))
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

    def _is_blocked(self, action: GameAction) -> bool:
        """Is this action known not to work from where we currently are?"""
        key = (self._displacement, action)
        return self._blocked_moves.get(key, 0) >= BLOCKED_MIN_OBSERVATIONS

    @staticmethod
    def _detect_translation(
        prev_frame: FrameData, latest_frame: FrameData
    ) -> tuple[int, int, tuple[int, int]] | None:
        """Is this frame-to-frame change one colored shape *moving*?

        Returns (color, cell_count, (dx, dy)) if the entire set of cells
        that lost colour C is exactly the set that gained colour C,
        displaced by a single consistent offset — otherwise None.

        This is the object layer, derived rather than assumed (Gestalt
        common fate: things that change together are one thing). Note it
        makes no prior commitment to 2D space or to anything being an
        object: it *tests* whether a translation explains the change, and
        reports nothing when it doesn't, so a non-spatial game simply
        yields no detections instead of a wrong ontology.
        """
        if not prev_frame.frame or not latest_frame.frame:
            return None

        lost: dict[int, set[tuple[int, int]]] = {}
        gained: dict[int, set[tuple[int, int]]] = {}
        for y, (prev_row, latest_row) in enumerate(
            zip(prev_frame.frame[-1], latest_frame.frame[-1])
        ):
            for x, (prev_val, latest_val) in enumerate(zip(prev_row, latest_row)):
                if prev_val != latest_val:
                    lost.setdefault(prev_val, set()).add((x, y))
                    gained.setdefault(latest_val, set()).add((x, y))

        for color, source in lost.items():
            target = gained.get(color)
            if not target or len(target) != len(source):
                continue
            # Anchor on each set's lexicographically smallest cell to get
            # the single candidate offset, then require an exact match.
            (sx, sy), (tx, ty) = min(source), min(target)
            offset = (tx - sx, ty - sy)
            if {(x + offset[0], y + offset[1]) for x, y in source} == target:
                return color, len(source), offset
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

        if self.acts_locally is False:
            # Clicking here changes something *elsewhere*, so the cells
            # that changed are the effect, not the cause — aiming at them
            # is a category error. Cover new ground instead. (First place
            # the learned contingency signature changes what we do.)
            ranked: list[tuple[list[tuple[int, int]], str]] = [
                (list(color_salient), "non-background cell (acts at a distance)"),
                (recent_active, "recently active cell"),
            ]
        else:
            ranked = [
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
