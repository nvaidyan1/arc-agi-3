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

from constants import MIN_MOVE_OBSERVATIONS, MOVE_MAJORITY

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
