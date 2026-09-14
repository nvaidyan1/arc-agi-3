"""What limits or conditions my actions.

Two constraints, discovered rather than declared:

  * `ObstacleMap`   — spatial. Where a known move fails to happen.
  * `StaminaDetector` — resource. A rendered quantity that depletes and refills.

They sit together because they answer one question — *what stops me, or
runs out on me?* — not because they are the same mechanism.

Deliberately **not** named `environment.py`: `docs/plan.md` already uses
"environment" for a different layer of the representation stack (changes
that happen independently of action), and reusing the word here would
assert a correspondence that isn't true. "Environment" also invites
becoming a dumping ground for anything that isn't the agent, whereas
"constraint" has a real boundary.

Neither class asserts that games *have* walls or stamina. Both stay
silent until evidence arrives, and both are wrong on some games in ways
that are documented rather than hidden.
"""
from __future__ import annotations

import logging

from arcengine import GameAction

from constants import (
    BLOCKED_MIN_OBSERVATIONS,
    STAMINA_DECLINE_RATIO,
    STAMINA_MIN_ATTEMPTS,
    STAMINA_MIN_SIZE,
    STAMINA_MUST_EMPTY_TO,
    STAMINA_START_TOLERANCE,
)

logger = logging.getLogger(__name__)


class ObstacleMap:
    """Where a move we know how to make fails to happen.

    Keyed by `(position, action)` on purpose, and the shape of the
    resulting map is its own validation: a real obstacle blocks at
    specific places, whereas a wrong move-map fails everywhere. Measured:
    "mixed" outcomes per (position, action) are ~0 — these games are
    deterministic — and each action is blocked at only a minority of
    positions. That is an obstacle signature, not model error.

    Effect when wired in: wasted moves on ls20 fell 63% -> 21%, and
    coverage rose 27-56% on 4 of 5 games.
    """

    def __init__(self) -> None:
        self._blocked: dict[tuple[tuple[int, int], GameAction], int] = {}
        self._attempts: dict[tuple[tuple[int, int], GameAction], int] = {}

    def observe(
        self, position: tuple[int, int], action: GameAction, occurred: bool
    ) -> None:
        """Record whether a move with a known expected effect happened.

        `occurred=False` deliberately covers both "nothing changed" and
        "something changed but the shape didn't move" — measured at 16%
        and 44% of predicted moves respectively, and on ls20 the latter
        dominates (bump a wall, the shape stays put and a counter ticks).
        Treating only silence as blocked would miss most obstacles.
        """
        key = (position, action)
        self._attempts[key] = self._attempts.get(key, 0) + 1
        if not occurred:
            self._blocked[key] = self._blocked.get(key, 0) + 1

    def is_blocked(self, position: tuple[int, int], action: GameAction) -> bool:
        """Is this action known not to work from this position?

        One failed attempt is enough: these games are deterministic, so
        the same action from the same position gives the same result.
        Position-keyed, so a wrong entry costs us one spot rather than
        disabling an action everywhere.
        """
        return self._blocked.get((position, action), 0) >= BLOCKED_MIN_OBSERVATIONS

    def clear(self) -> None:
        """New level, new layout — the old map means nothing."""
        self._blocked.clear()
        self._attempts.clear()


class StaminaDetector:
    """A rendered per-attempt resource, identified by its sawtooth.

    Named *stamina* rather than *lives* on purpose. What is measured is a
    quantity that drains while an attempt runs and refills when it
    restarts; in ls20 and dc22 that is literally a lives counter, but in
    vc33 it is a step budget, and "lives" would assert discrete retries
    the evidence does not support. Nor "budget", which this project uses
    for the self-imposed `MAX_ACTIONS` cap — a different thing we choose,
    not a rule the game enforces. (`MAX_ACTIONS` itself cannot be renamed:
    the framework's `Agent.main()` loop reads that exact attribute.)

    Requires *both* halves: the colour must fall during an attempt **and**
    return to the same starting value afterwards. Decline alone is not
    enough, and that distinction is load-bearing rather than fussy —
    dc22 has a colour that declines monotonically all run because the
    player is filling the board in. Reading that as a budget would have
    the agent conserving precisely when it is winning.

    The distinction in one line: a **drain** falls and never returns and
    means *how much of the level is done*; **stamina** refills and means
    *how much is left before death*. Only the second is a constraint.

    Fires on ~9 of 25 games. On ls20: 84 units at 2/action = 42 actions
    per attempt.
    """

    def __init__(self) -> None:
        self._starts: dict[int, list[int]] = {}
        self._down: dict[int, int] = {}
        self._up: dict[int, int] = {}
        self._peak: dict[int, int] = {}
        self._min: dict[int, int] = {}
        self._counts: dict[int, int] = {}
        # Series are keyed by an opaque **series key**, not by colour.
        # With whole-board totals the key IS the colour (and the old
        # behaviour is unchanged); with tracked regions it is a region id,
        # and this map carries the colour back out for callers that still
        # think in colours. That distinction is the whole fix: cd82's bar
        # drains 64 -> 0 but shares its colour with 100 static cells, so
        # measured per colour it only falls 164 -> 100 = 61% and is
        # rejected, while measured per region it reads 0% and passes.
        self._key_colour: dict = {}
        self._key_cells: dict = {}
        # Every cell the region has ever covered. A draining bar's
        # front cell has just STOPPED being the meter colour, so it is
        # absent from the current region and a filter keyed on that
        # alone still leaks the tick through — measured at 65% of bar
        # changes on cd82. The full extent is what the meter occupies
        # when full, which is the right thing to subtract.
        self._key_extent: dict = {}
        self._steps = 0
        self._announced = False

    @property
    def counts(self) -> dict[int, int]:
        """Last seen per-colour cell counts."""
        return self._counts

    @property
    def _best_key(self):
        """The series key whose shape is a stamina sawtooth, if any."""
        best, best_start = None, 0
        for colour, starts in self._starts.items():
            if len(starts) < STAMINA_MIN_ATTEMPTS:
                continue
            down, up = self._down.get(colour, 0), self._up.get(colour, 0)
            if down < STAMINA_DECLINE_RATIO * max(up, 1):
                continue
            mean_start = sum(starts) / len(starts)
            if mean_start < STAMINA_MIN_SIZE:
                continue
            # Must actually run down, not merely fluctuate.
            if self._min.get(colour, mean_start) > STAMINA_MUST_EMPTY_TO * mean_start:
                continue
            spread = (max(starts) - min(starts)) / mean_start
            if spread > STAMINA_START_TOLERANCE:
                continue
            # Prefer the most PERSISTENT drain, not the largest one.
            # Stamina depletes whether or not you achieve anything; fill
            # progress advances only when you do, and both refill on a
            # restart so both show a sawtooth. Measured on cd82, where the
            # two sit side by side: the real bar declines on 57% of steps
            # and the fill-progress region on 3%, a 19x separation. Sizing
            # alone picked the wrong one (the fill region is larger), and
            # reading fill progress as a budget would have the agent
            # conserving precisely when it is winning.
            persistence = self._down.get(colour, 0) / max(self._steps, 1)
            if persistence > best_start:
                best, best_start = colour, persistence
        return best

    @property
    def stamina_colour(self) -> int | None:
        """The colour that behaves like depleting stamina, if any."""
        key = self._best_key
        if key is None:
            return None
        return self._key_colour.get(key, key)

    @property
    def stamina_region(self):
        """The tracked region id of the meter, when measured per region.

        Exact, not inferred. A caller that instead matched regions against
        `stamina_cells` would get the wrong one: that set is the meter's
        accumulated *extent*, and the canvas grows over cells the meter
        has vacated, so the canvas intersects it and wins on size.
        """
        return self._best_key if self._key_colour else None

    @property
    def stamina_cells(self) -> frozenset | None:
        """The cells of the stamina region, when tracked as a region.

        Lets a caller subtract *that bar* rather than every cell sharing
        its colour — which on a board where 100 unrelated cells are the
        same colour is the difference between filtering the meter and
        filtering a chunk of the play area.
        """
        key = self._best_key
        return None if key is None else self._key_extent.get(key)

    @property
    def stamina_fraction(self) -> float | None:
        """How much of the attempt's stamina is left, 0-1, or None.

        Deliberately not wired to behaviour: measured cost per action is
        flat (ls20 1.94-2.00 for every action), so cost-aware selection
        gains nothing. Knowing time is short only helps if there is
        something worth rushing toward.
        """
        key = self._best_key
        if key is None:
            return None
        starts = self._starts[key]
        full = sum(starts) / len(starts)
        return max(0.0, min(1.0, self._counts.get(key, 0) / full))

    def update(self, counts: dict, game_id: str = "",
               colours: dict | None = None, cells: dict | None = None) -> None:
        """Fold one frame's size series into the sawtooth evidence.

        `counts` maps a **series key** to a size. Pass colour->total for
        the old whole-board behaviour, or region_id->size with `colours`
        and `cells` alongside to measure per region. The sawtooth logic
        below is identical either way; only what is being counted changes.
        """
        self._steps += 1
        if colours:
            self._key_colour.update(colours)
        if cells:
            self._key_cells = dict(cells)
            for k, v in cells.items():
                self._key_extent[k] = self._key_extent.get(k, frozenset()) | v
        # Look for the sawtooth in the series itself rather than keying
        # off our own RESET: ls20 refills its meter internally (per life)
        # with no GAME_OVER, so refills tied to RESET would never be seen.
        for colour in set(counts) | set(self._counts):
            n = counts.get(colour, 0)
            previous = self._counts.get(colour)
            if previous is None:
                continue
            peak = self._peak.get(colour, previous)
            self._peak[colour] = max(peak, n)
            self._min[colour] = min(self._min.get(colour, n), n)
            if n < previous:
                self._down[colour] = self._down.get(colour, 0) + 1
            elif n > previous:
                # A jump back up to near the observed peak is a refill —
                # the second half of the sawtooth. Anything smaller is
                # ordinary gameplay noise.
                if peak and (n - previous) >= 0.5 * peak:
                    self._starts.setdefault(colour, []).append(n)
                else:
                    self._up[colour] = self._up.get(colour, 0) + 1

        # Keep zeros rather than dropping absent colours: a meter that
        # empties disappears from the histogram, and forgetting it here
        # would make the refill that follows look like a first sighting.
        self._counts = {
            colour: counts.get(colour, 0)
            for colour in set(counts) | set(self._counts)
        }

        key = self._best_key
        if not self._announced and key is not None:
            self._announced = True
            starts = self._starts[key]
            logger.info(
                "STAMINA on %s: colour %s, %d cells, starts at ~%d each "
                "attempt and depletes",
                game_id, self.stamina_colour,
                len(self._key_cells.get(key) or ()),
                sum(starts) / len(starts),
            )
