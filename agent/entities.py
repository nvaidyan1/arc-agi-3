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

from constants import (  # noqa: F401  (SHAPE_REVIVE_WINDOW re-exported for tests)
    REGION_MATCH_DISTANCE,
    REGION_MATCH_SIZE_TOLERANCE,
    REGION_MOTION_TOLERANCE,
    SHAPE_REVIVE_WINDOW,
)


def _centroid(cells) -> tuple[float, float]:
    n = len(cells)
    return (sum(c[0] for c in cells) / n, sum(c[1] for c in cells) / n)


def _shape(cells) -> frozenset[tuple[int, int]]:
    """The region's form, independent of where it sits.

    Cells re-expressed relative to the region's own top-left, so the same
    object in two places has the same shape. This is what lets a thing be
    recognised after it teleports.
    """
    x0 = min(c[0] for c in cells)
    y0 = min(c[1] for c in cells)
    return frozenset((x - x0, y - y0) for x, y in cells)


class RegionTracker:
    """Assigns each contiguous region an id that persists across frames.

    Ids are opaque ints. They mean "this is the thing you were looking at
    last frame" and nothing else — no ordering, no seniority, no claim
    about importance.
    """

    def __init__(self) -> None:
        self._next_id = 0
        self._step = 0
        # When each id was last actually on screen. Shape matching is only
        # allowed to revive something that vanished MOMENTS ago: a reset
        # teleports an object within a single frame, whereas a region that
        # has been gone for a hundred steps and is now matched by shape
        # alone is far more likely a different thing that happens to look
        # the same. Without this bound the pass will capture look-alikes.
        self._last_seen: dict[int, int] = {}
        # id -> (colour, cells) as of the last frame it was SEEN in, kept
        # after it disappears. That memory is load-bearing rather than
        # tidy-minded: a stamina bar empties to nothing and then refills,
        # and if its id died with it the refill would look like a brand
        # new object, so the sawtooth would never close and the meter
        # would never be recognised. Bounded in practice — only regions
        # above the caller's `min_size` are ever passed in.
        self._tracked: dict[int, tuple[int, frozenset[tuple[int, int]]]] = {}
        # The ids actually on screen in the most recent frame. `_tracked`
        # deliberately remembers what has gone; this is what is here now,
        # and it is the set every consumer that reasons about *things I
        # can see* should read. Measured before it existed: on cd82 the
        # belief layer was scoring ghosts — remembered positions of an
        # object that had since moved on — and the router was routing the
        # object toward its own ghost.
        self.live: set[int] = set()
        # The layout as it stood at the start of the current attempt —
        # what the level restores on RESET. Kept so that a reset can be
        # *told* rather than deduced: the shape-revive pass below can only
        # recognise a teleported object whose form is identical, and an
        # object that faces a different way at home than it did when it
        # died (cd82's bucket) is not. Measured before this: a post-reset
        # frame minted ids at ~20x the ordinary rate, and every belief on
        # the old ids was orphaned.
        self._home: dict[int, tuple[int, frozenset[tuple[int, int]]]] | None = None
        self._expect_home = False

    def expect_home(self) -> None:
        """The caller has just sent RESET: the next frame is the layout as
        it was at the start of the attempt, so match against that first."""
        self._expect_home = True

    def update(
        self,
        regions: list[tuple[int, frozenset[tuple[int, int]]]],
        expected_offset: tuple[int, int] | None = None,
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

        `expected_offset` is what the caller's own move map says the action
        just taken does — the displacement it has learned to expect. When
        given, a region that was on screen last frame and now sits that far
        away is matched however large the hop, which is the only evidence
        that can follow an object whose stride exceeds the proximity bound.
        """
        self._step += 1
        was_live = set(self.live)
        assigned: dict[int, tuple[int, frozenset]] = {}
        used_old: set[int] = set()
        used_new: set[frozenset] = set()

        # Zeroth pass, only on the frame after a RESET: the level has put
        # everything back where the attempt began, so a region that
        # overlaps a remembered home region of its colour IS that region.
        # This is the caller telling us what happened rather than us
        # guessing from shapes, and it is what carries an object's beliefs
        # across a death.
        if self._expect_home and self._home:
            candidates = []
            for colour, cells in regions:
                for home_id, (home_colour, home_cells) in self._home.items():
                    if home_colour != colour:
                        continue
                    overlap = len(cells & home_cells)
                    if overlap:
                        candidates.append((overlap, home_id, colour, cells))
            candidates.sort(key=lambda c: -c[0])
            for _overlap, home_id, colour, cells in candidates:
                if home_id in used_old or cells in used_new:
                    continue
                assigned[home_id] = (colour, cells)
                used_old.add(home_id)
                used_new.add(cells)

        candidates = []
        for colour, cells in regions:
            if cells in used_new:
                continue
            for old_id, (old_colour, old_cells) in self._tracked.items():
                if old_id in used_old:
                    continue
                if old_colour != colour:
                    continue
                overlap = len(cells & old_cells)
                if overlap:
                    candidates.append((overlap, old_id, colour, cells))

        # Largest overlaps win, so a big region keeps its identity when a
        # small one happens to straddle the same pixels.
        candidates.sort(key=lambda c: -c[0])
        for _overlap, old_id, colour, cells in candidates:
            if old_id in used_old or cells in used_new:
                continue
            assigned[old_id] = (colour, cells)
            used_old.add(old_id)
            used_new.add(cells)

        # Second pass: explained motion. If we just did the thing that
        # moves something by `expected_offset`, then a region that was on
        # screen last frame and has reappeared exactly that far away is
        # that region. Stronger evidence than proximity — it is a
        # prediction confirmed rather than a nearest-neighbour guess — and
        # the only pass that scales with the game's own stride instead of
        # a constant of ours. Size is still required to be similar, within
        # the tolerance a deforming mover has already earned.
        leftovers = [(c, cells) for c, cells in regions if cells not in used_new]
        if leftovers and expected_offset is not None:
            dx, dy = expected_offset
            candidates = []
            for colour, cells in leftovers:
                cx, cy = _centroid(cells)
                for old_id, (old_colour, old_cells) in self._tracked.items():
                    if (old_id in used_old or old_colour != colour
                            or old_id not in was_live):
                        continue
                    if abs(len(cells) - len(old_cells)) > (
                            REGION_MATCH_SIZE_TOLERANCE
                            * max(len(cells), len(old_cells))):
                        continue
                    ox, oy = _centroid(old_cells)
                    miss = max(abs(cx - (ox + dx)), abs(cy - (oy + dy)))
                    if miss <= REGION_MOTION_TOLERANCE:
                        candidates.append((miss, old_id, colour, cells))
            candidates.sort(key=lambda c: c[0])
            for _miss, old_id, colour, cells in candidates:
                if old_id in used_old or cells in used_new:
                    continue
                assigned[old_id] = (colour, cells)
                used_old.add(old_id)
                used_new.add(cells)

        # Third pass: proximity. Overlap is the stronger evidence and is
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

        # Fourth pass: same shape, same colour, somewhere else entirely.
        # A RESET teleports every object back to its start, so neither
        # overlap nor proximity can follow it and the tracker mints a
        # fresh id -- discarding every belief attached to the old one,
        # including the action-to-entity mapping it had learned. Measured:
        # a post-reset frame mints ids at ~20x the ordinary rate (cd82
        # 1.7 per frame against 0.08).
        #
        # Matching on form is what survives a teleport. Where several
        # remembered regions share a shape -- wa30 has three identical
        # 4x4 frames -- the nearest wins, which pairs them correctly when
        # they all return to the positions they were remembered at.
        leftovers = [(c, cells) for c, cells in regions if cells not in used_new]
        if leftovers:
            candidates = []
            for colour, cells in leftovers:
                form = _shape(cells)
                cx, cy = _centroid(cells)
                for old_id, (old_colour, old_cells) in self._tracked.items():
                    if old_id in used_old or old_colour != colour:
                        continue
                    if _shape(old_cells) != form:
                        continue
                    if self._step - self._last_seen.get(old_id, 0) > SHAPE_REVIVE_WINDOW:
                        continue
                    ox, oy = _centroid(old_cells)
                    candidates.append((max(abs(cx - ox), abs(cy - oy)),
                                       old_id, colour, cells))
            candidates.sort(key=lambda c: c[0])
            for _d, old_id, colour, cells in candidates:
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
        for rid in assigned:
            self._last_seen[rid] = self._step
        self.live = set(assigned)
        # The first frame after a clear is the level's start; the first
        # after a reset is the same layout restored. Either way, this is
        # what the next reset will return us to.
        if self._home is None or self._expect_home:
            self._home = dict(assigned)
            self._expect_home = False
        return assigned

    def clear(self) -> None:
        """New level: the layout is gone, so no id survives it."""
        self._tracked.clear()
        self._last_seen.clear()
        self.live.clear()
        self._home = None
        self._expect_home = False
