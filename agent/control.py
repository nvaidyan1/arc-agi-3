"""The "thing I control" layer: what my actions do, and where I am.

Built entirely from contingency — which action reliably causes which
displacement — rather than from appearance. Nothing here assumes there
*is* a controllable avatar: on a game with no movement no offsets are
ever observed, `learned_moves` stays empty, and every consumer degrades
to its no-move-map path. That is the intended outcome, not a gap: the
move map is silent on 9 of 25 games.

Two kinds of state live here, and the difference matters:

  * **Properties of the game** (`_offsets`, `controlled_size`) persist
    across RESET. What an action does is not a fact about one attempt.
  * **Position within an attempt** (`displacement`, `anchor`, `visited`)
    resets, because the level restarts from its own origin.

Literature: contingency awareness (Bellemare, Veness & Bowling, AAAI
2012) — learning which parts of an observation are under the agent's own
control by detecting what covaries with its actions.
"""
from __future__ import annotations

import logging

from arcengine import GameAction

from constants import MIN_MOVE_OBSERVATIONS, MIN_POSITION_OBSERVATIONS, MOVE_MAJORITY

logger = logging.getLogger(__name__)


class MoveModel:
    """Per action, the displacement it reliably causes — and where we are."""

    def __init__(self) -> None:
        # Property of the game: persists across attempts.
        self._offsets: dict[GameAction, dict[tuple[int, int], int]] = {}
        self._announced: set[GameAction] = set()
        self.controlled_size = 0
        self.reset_position()

    def reset_position(self) -> None:
        """New attempt or new level: the position frame of reference is gone.

        `displacement` is relative to wherever this attempt started;
        `anchor` is the same point in absolute board pixels, and stays
        None until a translation is actually observed. The pair is what
        lets the router convert an absolute pixel target into this
        relative space — see `origin_anchor`.
        """
        self.displacement: tuple[int, int] = (0, 0)
        self.anchor: tuple[int, int] | None = None
        self.visited: set[tuple[int, int]] = {(0, 0)}

    @property
    def learned_moves(self) -> dict[GameAction, tuple[int, int]]:
        """Actions whose effect is a consistent translation, and by what.

        Requires several observations and a clear majority, so a one-off
        coincidence isn't mistaken for control. On ls20 this recovers a
        complete, noise-free directional map (ACTION1-4 -> up/down/left/
        right at a 5px stride, 122/122 consistent). It correctly *refuses*
        genuinely ambiguous actions: m0r0's ACTION1 splits 15 one way and
        13 the other, and returning nothing is the right answer there.
        """
        learned = {}
        for action, offsets in self._offsets.items():
            if not offsets:
                continue
            best, count = max(offsets.items(), key=lambda kv: kv[1])
            total = sum(offsets.values())
            if count >= MIN_MOVE_OBSERVATIONS and count / total >= MOVE_MAJORITY:
                learned[action] = best
        return learned

    def observe_translation(
        self,
        action: GameAction,
        offset: tuple[int, int],
        size: int,
        pre_move_anchor: tuple[int, int],
        game_id: str = "",
    ) -> None:
        """Record that `action` displaced a `size`-cell shape by `offset`."""
        self.controlled_size = max(self.controlled_size, size)
        offsets = self._offsets.setdefault(action, {})
        offsets[offset] = offsets.get(offset, 0) + 1
        self.displacement = (
            self.displacement[0] + offset[0],
            self.displacement[1] + offset[1],
        )
        self.visited.add(self.displacement)
        # Absolute position is re-derived from ground truth every time
        # rather than purely accumulated, so it cannot silently drift.
        self.anchor = (
            pre_move_anchor[0] + offset[0],
            pre_move_anchor[1] + offset[1],
        )
        if action in self.learned_moves and action not in self._announced:
            self._announced.add(action)
            logger.info(
                "LEARNED on %s: %s moves a %d-cell shape by %s",
                game_id, action.name, size, offset,
            )

    def origin_anchor(self) -> tuple[int, int] | None:
        """Board position where `displacement` was (0, 0), or None.

        `displacement` and `anchor` advance by identical offsets from
        different origins, so subtracting one from the other recovers the
        shared origin. This is the bridge between the absolute pixel space
        the interest map is keyed in and the relative space the move and
        obstacle maps are keyed in.
        """
        if self.anchor is None:
            return None
        return (
            self.anchor[0] - self.displacement[0],
            self.anchor[1] - self.displacement[1],
        )

    def to_relative(self, pixel: tuple[int, int]) -> tuple[int, int] | None:
        """Re-express an absolute board pixel in displacement space."""
        origin = self.origin_anchor()
        if origin is None:
            return None
        return (pixel[0] - origin[0], pixel[1] - origin[1])


class PositionModel:
    """`(position, action) -> position'`, in displacement space, learned
    empirically — the position-KEYED generalisation of `MoveModel.
    learned_moves`, which holds one offset per action regardless of where
    it is taken.

    H009 (`docs/history.md`, `research/hypotheses/H009_planner_factorial.md`,
    2026-09-15) found this distinction is not academic: on cd82 the
    controlled thing's motion is a deterministic function of (position,
    action) across ten seeds — every context seen twice has one successor
    — but NOT a function of the action alone (each action has 5 distinct
    observed deltas, because the bucket orbits the block rather than
    translating). `MoveModel`'s offset model cannot express that, and
    traced live it is honoured at the first step of 0 of 1,244 plans.

    The admit rule is H006's, not `MoveModel`'s majority-vote one
    (`learned_moves`, `MOVE_MAJORITY`): a transition is trusted only once
    every sighting of it agreed, never merely most of them. A position
    that has been seen to move two different ways under the same action
    is a fact the model must NOT paper over with a majority — that is
    exactly the ambiguity `learned_moves` already refuses for m0r0's
    ACTION1 (15 one way, 13 the other), generalised to be position-aware.

    Persists across RESET like `MoveModel._offsets` — the orbit is a
    property of the game, not of one attempt — and is cleared on a new
    level, same as `MoveModel.reset_position` clears `displacement`
    itself: positions from the previous level's frame of reference are
    not comparable.
    """

    def __init__(self) -> None:
        self._table: dict[tuple[tuple[int, int], GameAction], dict[tuple[int, int], int]] = {}

    def observe(
        self,
        position: tuple[int, int],
        action: GameAction,
        next_position: tuple[int, int],
    ) -> None:
        counts = self._table.setdefault((position, action), {})
        counts[next_position] = counts.get(next_position, 0) + 1

    @property
    def edges(self) -> dict[tuple[tuple[int, int], GameAction], tuple[int, int]]:
        """Admitted transitions: seen `MIN_POSITION_OBSERVATIONS` times or
        more, and every sighting the SAME successor — deterministic, not
        majority. A `(position, action)` pair that has ever disagreed with
        itself is excluded, not resolved by a vote: an ambiguous edge is
        a fact worth having (H009's E0 checked for exactly this and found
        none on cd82), and voting it away would hide a real failure mode
        this model exists to avoid.
        """
        out = {}
        for key, counts in self._table.items():
            if sum(counts.values()) >= MIN_POSITION_OBSERVATIONS and len(counts) == 1:
                out[key] = next(iter(counts))
        return out

    def clear(self) -> None:
        """New level: positions from the old frame of reference mean
        nothing in the new one."""
        self._table.clear()
