"""Which regions are *the same region* from one frame to the next.

`perception.connected_regions` groups pixels; it has no memory, so the
grouping it returns for frame N carries no relationship to frame N-1. This
module supplies that relationship, and only that: it hands each region a
stable id and follows it while it persists.

Why a whole layer for it. Every question we have struggled with this week
turned out to be a question about a *thing over time* asked in a
vocabulary that had no things in it:

  * cd82's stamina bar drains 64 cells to 0 — perfectly — but 100 static
    cells elsewhere share its colour, so the whole-board colour total only
    falls 164 -> 100 and the sawtooth test rejects it at 61%. The same bar
    tracked as a region reads 0% and passes.
  * cd82's controllable object deforms by up to 14 cells as it moves, so
    every lens that demands an identical shape refuses it. Tracked as a
    region it is obviously one object, in one place, moving.
  * sp80 and dc22 each have two controllable objects whose motions are
    summed into a single position, because the move map is keyed by action
    and the colour is discarded.

Deliberately NOT an ontology. A tracked region is an unlabelled candidate:
nothing here says which one is the player, the goal, or a hazard. Grouping
and following are representation, which the governing principle permits;
assigning roles is interpretation, which stays evidence-gated elsewhere
and is still free to conclude nothing.

Matching is by **overlap**, not by shape or size, precisely because the
things worth following change shape — a draining bar, a walking sprite, a
rotating bucket. A region matches the previous region it shares the most
cells with, which survives shrinking from either end, deformation, and
recolouring of part of the whole.
"""
from __future__ import annotations

from constants import REGION_MATCH_DISTANCE, REGION_MATCH_SIZE_TOLERANCE


def _centroid(cells) -> tuple[float, float]:
    n = len(cells)
    return (sum(c[0] for c in cells) / n, sum(c[1] for c in cells) / n)


class RegionTracker:
    """Assigns each contiguous region an id that persists across frames.

    Ids are opaque ints. They mean "this is the thing you were looking at
    last frame" and nothing else — no ordering, no seniority, no claim
    about importance.
    """

    def __init__(self) -> None:
        self._next_id = 0
        # id -> (colour, cells) as of the last frame it was SEEN in, kept
        # after it disappears. That memory is load-bearing rather than
        # tidy-minded: a stamina bar empties to nothing and then refills,
        # and if its id died with it the refill would look like a brand
        # new object, so the sawtooth would never close and the meter
        # would never be recognised. Bounded in practice — only regions
        # above the caller's `min_size` are ever passed in.
        self._tracked: dict[int, tuple[int, frozenset[tuple[int, int]]]] = {}

    def update(
        self, regions: list[tuple[int, frozenset[tuple[int, int]]]]
    ) -> dict[int, tuple[int, frozenset[tuple[int, int]]]]:
        """Match this frame's regions to the previous frame's.

        Returns `{region_id: (colour, cells)}` for this frame only. A
        region that has vanished is dropped from the return value but its
        id is not reused, so a caller holding a series keyed by id will
        see it stop rather than see it silently become something else.

        Greedy by overlap size, largest first. A region matches only a
        previous region of the **same colour**: a shape that changes
        colour entirely is a different thing for our purposes, and letting
        colours merge would quietly recreate the aggregate this layer
        exists to escape.
        """
        candidates = []
        for colour, cells in regions:
            for old_id, (old_colour, old_cells) in self._tracked.items():
                if old_colour != colour:
                    continue
                overlap = len(cells & old_cells)
                if overlap:
                    candidates.append((overlap, old_id, colour, cells))

        # Largest overlaps win, so a big region keeps its identity when a
        # small one happens to straddle the same pixels.
        candidates.sort(key=lambda c: -c[0])
        assigned: dict[int, tuple[int, frozenset]] = {}
        used_old: set[int] = set()
        used_new: set[frozenset] = set()
        for _overlap, old_id, colour, cells in candidates:
            if old_id in used_old or cells in used_new:
                continue
            assigned[old_id] = (colour, cells)
            used_old.add(old_id)
            used_new.add(cells)

        # Second pass: proximity. Overlap is the stronger evidence and is
        # always tried first, but it cannot follow a thing that moves
        # further than its own width — and that is most moving objects,
        # since a stride tends to exceed a sprite. Without this, ls20's
        # entities were reborn every step and no belief could form.
        leftovers = [(c, cells) for c, cells in regions if cells not in used_new]
        if leftovers:
            candidates = []
            for colour, cells in leftovers:
                cx, cy = _centroid(cells)
                for old_id, (old_colour, old_cells) in self._tracked.items():
                    if old_id in used_old or old_colour != colour:
                        continue
                    if abs(len(cells) - len(old_cells)) > (
                            REGION_MATCH_SIZE_TOLERANCE
                            * max(len(cells), len(old_cells))):
                        continue
                    ox, oy = _centroid(old_cells)
                    distance = max(abs(cx - ox), abs(cy - oy))
                    if distance <= REGION_MATCH_DISTANCE:
                        candidates.append((distance, old_id, colour, cells))
            # Nearest first, so the closest pairing wins when two regions
            # of one colour sit within range of each other.
            candidates.sort(key=lambda c: c[0])
            for _distance, old_id, colour, cells in candidates:
                if old_id in used_old or cells in used_new:
                    continue
                assigned[old_id] = (colour, cells)
                used_old.add(old_id)
                used_new.add(cells)

        for colour, cells in regions:
            if cells in used_new:
                continue
            assigned[self._next_id] = (colour, cells)
            used_new.add(cells)
            self._next_id += 1

        # Remember where everything was, including what is no longer on
        # screen, so a region that comes back can be recognised as itself.
        # Only what is present right now is returned.
        self._tracked.update(assigned)
        return assigned

    def clear(self) -> None:
        """New level: the layout is gone, so no id survives it."""
        self._tracked.clear()
