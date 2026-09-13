"""Your ARC-AGI-3 agent. This is the *only* file you should normally edit.

`scripts/build_notebook.py` splices the contents of this file into the
Kaggle submission notebook, so your local dev loop and your Kaggle
submission stay in lock-step:

    [edit my_agent.py] → [make play-local] → [make submit]

Strategy: game-agnostic exploration. No per-game special-casing — the goal
is a policy that behaves reasonably on games it has never seen, which is
what the competition actually scores. Two ideas, both driven only by what
the game itself reports each frame (see docs/game-mechanics.md):

  1. Only ever try actions the game currently reports as legal
     (`latest_frame.available_actions`) instead of guessing across all 7 —
     e.g. ls20 only exposes ACTION1-4, so trying ACTION5-7 there is wasted
     budget.
  2. Track, per action, how often it actually changes the frame vs. does
     nothing, and bias future picks toward actions that do something
     (epsilon-greedy so under-tried actions still get sampled). For the
     one action with a payload (ACTION6, a grid click), click a cell whose
     color differs from the frame's most common color — a proxy for
     "click the thing that looks different" with no game-specific meaning
     attached.

Contract (enforced by the ARC-AGI-3-Agents framework):
  - Subclass `agents.agent.Agent`.
  - Class must be named `MyAgent` (the notebook's __init__.py registers it).
  - Implement `is_done(frames, latest_frame) -> bool`.
  - Implement `choose_action(frames, latest_frame) -> GameAction`.
"""
from __future__ import annotations

import random
import time
from typing import Any

from arcengine import FrameData, GameAction, GameState

# When run inside the ARC-AGI-3-Agents framework (locally or on Kaggle)
# the `agents` package is on sys.path, so this import resolves.
from agents.agent import Agent

# Chance of ignoring the change-rate weighting and picking a legal action
# uniformly at random, so under-tried actions keep getting sampled.
EXPLORATION_EPSILON = 0.25


class MyAgent(Agent):
    """Explores by favoring actions that visibly change the frame."""

    # Upper bound on actions per game; the framework also enforces global limits.
    MAX_ACTIONS = 80

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Seed per game_id so replays from the same game are reproducible but
        # different games explore independently.
        seed = int(time.time() * 1_000_000) + hash(self.game_id) % 1_000_000
        random.seed(seed)
        self._reset_exploration_state()

    def _reset_exploration_state(self) -> None:
        # (tries, frame-changes) per action, reset on every RESET since a
        # fresh level can behave differently from the one before it.
        self._action_tries: dict[GameAction, int] = {}
        self._action_changes: dict[GameAction, int] = {}

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

        # Credit/blame the action that produced the current frame: did the
        # frame actually change, or was it a no-op?
        last_action = latest_frame.action_input.id
        if len(frames) >= 2 and last_action is not GameAction.RESET:
            changed = latest_frame.frame != frames[-2].frame
            self._action_tries[last_action] = self._action_tries.get(last_action, 0) + 1
            if changed:
                self._action_changes[last_action] = (
                    self._action_changes.get(last_action, 0) + 1
                )

        if random.random() < EXPLORATION_EPSILON:
            action = random.choice(candidate_actions)
        else:
            # Laplace-smoothed change-rate: untried actions default to 1/2
            # (competitive with anything else), proven-inert actions decay.
            weights = [
                (self._action_changes.get(a, 0) + 1)
                / (self._action_tries.get(a, 0) + 2)
                for a in candidate_actions
            ]
            action = random.choices(candidate_actions, weights=weights, k=1)[0]

        if action.is_complex():
            # ACTION6 takes (x, y) coordinates on a 64×64 grid.
            x, y = self._pick_salient_coordinate(latest_frame)
            action.set_data({"x": x, "y": y})
            action.reasoning = {"why": "click on salient (non-background) cell"}
        else:
            tries = self._action_tries.get(action, 0)
            changes = self._action_changes.get(action, 0)
            action.reasoning = (
                f"exploration: {action.name} tried={tries} changed={changes}"
            )
        return action

    @staticmethod
    def _pick_salient_coordinate(latest_frame: FrameData) -> tuple[int, int]:
        """Pick a grid cell whose color differs from the most common one.

        Game-agnostic stand-in for "click on the thing that looks
        interesting" — no assumption about what any color means.
        """
        if not latest_frame.frame:
            return random.randint(0, 63), random.randint(0, 63)

        grid = latest_frame.frame[0]
        counts: dict[int, int] = {}
        for row in grid:
            for value in row:
                counts[value] = counts.get(value, 0) + 1
        background = max(counts, key=counts.get)

        salient = [
            (x, y)
            for y, row in enumerate(grid)
            for x, value in enumerate(row)
            if value != background
        ]
        if not salient:
            return random.randint(0, 63), random.randint(0, 63)
        return random.choice(salient)
