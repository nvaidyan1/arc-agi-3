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
     finally to a uniform random cell. Coarse grid regions that have been
     clicked repeatedly with zero effect are avoided ("dead" regions),
     the same Laplace-smoothed pattern used for the per-action stats.
     See docs/plan.md for why a full object/connected-component model
     (considered and deliberately deferred) isn't used for this instead.
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

# Coarse grid bucket size for click "dead region" tracking: 64/8 -> an 8x8
# grid of regions, coarse enough that a handful of clicks is enough signal.
REGION_SIZE = 8

# A region needs at least this many tried clicks, with zero of them causing
# any diff, before it's treated as dead and avoided.
DEAD_REGION_MIN_TRIES = 3

# How many past steps' diffed cells to keep as "recently active" targets.
RECENT_DIFF_STEPS = 5

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
        self._reset_exploration_state()

    def _reset_exploration_state(self) -> None:
        # (tries, frame-changes) per action, reset on every RESET since a
        # fresh level can behave differently from the one before it.
        self._action_tries: dict[GameAction, int] = {}
        self._action_changes: dict[GameAction, int] = {}
        # Same idea, keyed by coarse click region, for ACTION6 only.
        self._region_tries: dict[tuple[int, int], int] = {}
        self._region_changes: dict[tuple[int, int], int] = {}
        # Rolling window of recent diffed-cell lists, newest last.
        self._recent_diffs: deque[list[tuple[int, int]]] = deque(
            maxlen=RECENT_DIFF_STEPS
        )
        # What we chose last call, so next call can credit/blame it against
        # the resulting frame (see note in choose_action on why this can't
        # be read back from the frame itself).
        self._last_action: GameAction | None = None
        self._last_click: tuple[int, int] | None = None

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
        if len(frames) >= 2 and self._last_action is not None:
            prev_frame = frames[-2]
            diff_cells = self._diff_cells(prev_frame, latest_frame)

            self._action_tries[self._last_action] = (
                self._action_tries.get(self._last_action, 0) + 1
            )
            if diff_cells:
                self._action_changes[self._last_action] = (
                    self._action_changes.get(self._last_action, 0) + 1
                )
                self._recent_diffs.append(diff_cells)

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
                cx, cy = self._last_click
                region = (cx // REGION_SIZE, cy // REGION_SIZE)
                self._region_tries[region] = self._region_tries.get(region, 0) + 1
                if diff_cells:
                    self._region_changes[region] = (
                        self._region_changes.get(region, 0) + 1
                    )

        if random.random() < EXPLORATION_EPSILON:
            action = random.choice(candidate_actions)
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
            action.reasoning = {"why": why}
            self._last_click = (x, y)
        else:
            tries = self._action_tries.get(action, 0)
            changes = self._action_changes.get(action, 0)
            level_ups = self._action_level_ups.get(action, 0)
            action.reasoning = (
                f"exploration: {action.name} tried={tries} "
                f"changed={changes} level_ups={level_ups}"
            )
            self._last_click = None
        self._last_action = action
        return action

    @staticmethod
    def _diff_cells(
        prev_frame: FrameData, latest_frame: FrameData
    ) -> list[tuple[int, int]]:
        """(x, y) cells that differ between two frames' first layer.

        Only layer 0 is compared — same simplification `_pick_coordinate`
        already made when picking click targets.
        """
        if not prev_frame.frame or not latest_frame.frame:
            return []
        prev_grid, latest_grid = prev_frame.frame[0], latest_frame.frame[0]
        return [
            (x, y)
            for y, (prev_row, latest_row) in enumerate(zip(prev_grid, latest_grid))
            for x, (prev_val, latest_val) in enumerate(zip(prev_row, latest_row))
            if prev_val != latest_val
        ]

    def _region_is_dead(self, x: int, y: int) -> bool:
        region = (x // REGION_SIZE, y // REGION_SIZE)
        tries = self._region_tries.get(region, 0)
        changes = self._region_changes.get(region, 0)
        return tries >= DEAD_REGION_MIN_TRIES and changes == 0

    def _pick_coordinate(self, latest_frame: FrameData) -> tuple[int, int, str]:
        """Pick a click target and say why, most to least preferred:

        1. A cell that was part of a recent diff (something is happening
           there) and also differs from the current background color.
        2. Any recently-diffed cell.
        3. Any cell that differs from the frame's most common color.
        4. A uniform random cell.

        Regions that have absorbed several clicks with zero effect are
        filtered out of 1-3 (falling back to a live region if everything
        is dead) — a game-agnostic stand-in for "stop poking dead space."
        """
        if not latest_frame.frame:
            return random.randint(0, 63), random.randint(0, 63), "no frame yet"

        grid = latest_frame.frame[0]
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

        ranked: list[tuple[list[tuple[int, int]], str]] = [
            (
                [c for c in recent_active if c in color_salient],
                "recently active + non-background cell",
            ),
            (recent_active, "recently active cell"),
            (list(color_salient), "non-background cell"),
        ]
        for candidates, why in ranked:
            live = [c for c in candidates if not self._region_is_dead(*c)]
            if live:
                return (*random.choice(live), why)
            # Either no candidates at this tier, or all of them sit in a
            # dead region — either way, fall through to the next (weaker)
            # tier rather than clicking a known-inert spot.

        return random.randint(0, 63), random.randint(0, 63), "random fallback"
