"""What appears worth investigating — explicitly NOT what the goal is.

That distinction is the most important thing in this module, and it is
load-bearing rather than pedantic. An `InterestMap` entry means *change
happened here that I did not cause myself*. It does **not** mean *the
win condition is here*. We have measured what happens when those get
conflated: routing toward accumulated interest made completions more
reliable and the score **worse** (mean 0.0511 -> 0.0164), because the
score is quadratic in speed and interest marks where things happened,
not where the goal is. See docs/history.md, 2026-09-13.

So this module answers "where should I look next?" and leaves "is that
the goal?" unanswered — which is what lets attention discover goals,
side effects, objects and useful regions without having to decide in
advance which one it found.

Literature: incentive salience (Berridge & Robinson, 1998) — a location
acquires "wanting" through association with reward, separately from
whether it is itself rewarding; salience map (Itti & Koch, 1998);
habituation (Thompson & Spencer, 1966).
"""
from __future__ import annotations

import random
from collections import deque

from constants import (
    INTEREST_DECAY,
    INTEREST_PRUNE_FLOOR,
    INTEREST_TOP_K,
    RECENT_DIFF_STEPS,
)


class InterestMap:
    """Per-pixel accumulated "wanting", decaying over time.

    Justified by measurement before it was built: these sites cluster
    tightly rather than spreading uniformly (Clark-Evans R 0.39-0.52
    against 1.0 for spatially random), and on the games we score 8-29
    cells out of 4096 carry half the mass. A map of them therefore
    carries real information — had they been diffuse, it would not.

    Persists across RESET within a level (same layout, so a spot that
    mattered last attempt plausibly matters this one) and is cleared on
    level change.
    """

    def __init__(self) -> None:
        self._weights: dict[tuple[int, int], float] = {}

    def __bool__(self) -> bool:
        return bool(self._weights)

    def __len__(self) -> int:
        return len(self._weights)

    @property
    def peak(self) -> float:
        """Strongest accumulated evidence anywhere, or 0.0 if empty."""
        return max(self._weights.values(), default=0.0)

    def bump(self, cells, weight: float) -> None:
        """Add salience at `cells`."""
        for cell in cells:
            self._weights[cell] = self._weights.get(cell, 0.0) + weight

    def decay(self) -> None:
        """Age the map by one step; drop entries once negligible.

        Called once per real step rather than once per bump, so hotspots
        fade with time regardless of how many signals fired that step.
        Pruning keeps the top-K scan cheap.
        """
        dead = []
        for cell, value in self._weights.items():
            value *= INTEREST_DECAY
            if value < INTEREST_PRUNE_FLOOR:
                dead.append(cell)
            else:
                self._weights[cell] = value
        for cell in dead:
            del self._weights[cell]

    def top_cells(self, k: int = INTEREST_TOP_K) -> list[tuple[int, int]]:
        """The best-known cells, highest salience first. Empty if none."""
        if not self._weights:
            return []
        ranked = sorted(self._weights.items(), key=lambda kv: kv[1], reverse=True)
        return [cell for cell, _ in ranked[:k]]

    def top_cells_with_weight(
        self, k: int = 120
    ) -> list[tuple[tuple[int, int], float]]:
        """Like `top_cells`, but keeps the weight — for rendering a heatmap.

        `k` defaults far above `INTEREST_TOP_K` (which is sized for
        `_pick_coordinate`'s decision, not for a picture): a debugging view
        wants enough of the map to show its shape, not just the winning
        cell. Capped rather than unbounded so a dense map still produces a
        small, comparable-across-steps payload.
        """
        if not self._weights:
            return []
        ranked = sorted(self._weights.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:k]

    def clear(self) -> None:
        self._weights.clear()


class ClickTargeting:
    """Where to aim the one action that takes coordinates.

    Holds the per-cell click memory and the learned locality signature.
    Both are evidence about the click action, kept here rather than in
    `control` because they answer "where should I aim?" rather than
    "what does my action do?".
    """

    def __init__(self) -> None:
        # Property of the game: does clicking change the cell you touched?
        self._local = 0
        self._remote = 0
        self.reset_attempt()

    def reset_attempt(self) -> None:
        self._tries: dict[tuple[int, int], int] = {}
        self._effect: dict[tuple[int, int], int] = {}
        self._recent: deque[list[tuple[int, int]]] = deque(maxlen=RECENT_DIFF_STEPS)

    @property
    def acts_locally(self) -> bool | None:
        """Does clicking tend to change the clicked cell itself?

        None until there's evidence either way. Measured across three
        games, the split is clean: ft09 changes the cell you touch (and
        exactly 38 cells each time), while vc33/tn36 never touch it and
        change 1-2 cells elsewhere. This *changes behaviour*: when clicks
        act at a distance, the changed cells are the effect, not the
        cause, so aiming at them is a category error. Click repeat waste
        fell from ~50% to 1-3% once this was respected.
        """
        if not (self._local or self._remote):
            return None
        return self._local > self._remote

    def observe_click(
        self, cell: tuple[int, int], changed: list[tuple[int, int]]
    ) -> None:
        self._tries[cell] = self._tries.get(cell, 0) + 1
        if changed:
            self._effect[cell] = self._effect.get(cell, 0) + len(changed)
            if cell in set(changed):
                self._local += 1
            else:
                self._remote += 1

    def observe_change(self, changed: list[tuple[int, int]]) -> None:
        if changed:
            self._recent.append(changed)

    def _is_spent(self, cell: tuple[int, int]) -> bool:
        """Clicked before and never did anything — habituated, skip it."""
        return self._tries.get(cell, 0) > 0 and self._effect.get(cell, 0) == 0

    def pick(
        self, grid: list[list[int]], interest: InterestMap
    ) -> tuple[int, int, str]:
        """Pick a click target and say why, most to least preferred:

        0. A learned region of interest — where salience has accumulated.
        1. A recently-changed cell that also differs from the background.
        2. Any recently-changed cell.
        3. Any non-background cell.
        4. A uniform random cell.

        Within a tier, cells that already absorbed a click with no effect
        are dropped (habituation), and never-clicked cells are preferred
        over ones already tried — measurement showed ~half of all clicks
        were exact repeats, which is pure waste against a finite budget.
        """
        if not grid:
            return random.randint(0, 63), random.randint(0, 63), "no frame yet"

        counts: dict[int, int] = {}
        for row in grid:
            for value in row:
                counts[value] = counts.get(value, 0) + 1
        background = max(counts, key=counts.get)

        salient = {
            (x, y)
            for y, row in enumerate(grid)
            for x, value in enumerate(row)
            if value != background
        }
        recent = [cell for diff in self._recent for cell in diff]

        # Interest leads regardless of the locality split below: it is
        # not about whether clicking affects what's under the cursor, but
        # about which locations have a track record of mattering.
        ranked: list[tuple[list[tuple[int, int]], str]] = [
            (interest.top_cells(), "learned region of interest"),
        ]
        if self.acts_locally is False:
            # Clicking changes something *elsewhere*, so the changed cells
            # are the effect, not the cause — aiming at them is a category
            # error. Cover new ground instead.
            ranked += [
                (list(salient), "non-background cell (acts at a distance)"),
                (recent, "recently active cell"),
            ]
        else:
            ranked += [
                ([c for c in recent if c in salient],
                 "recently active + non-background cell"),
                (recent, "recently active cell"),
                (list(salient), "non-background cell"),
            ]

        for candidates, why in ranked:
            live = [c for c in candidates if not self._is_spent(c)]
            if not live:
                continue
            fresh = [c for c in live if c not in self._tries]
            if fresh:
                return (*random.choice(fresh), f"{why} (unclicked)")
            return (*random.choice(live), f"{why} (revisit)")

        return random.randint(0, 63), random.randint(0, 63), "random fallback"
