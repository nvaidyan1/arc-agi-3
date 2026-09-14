"""Unit tests for the entity layer: grouping pixels, and following a group.

This layer exists because an aggregate destroyed a real signal. cd82's
stamina bar drains 64 cells to zero — perfectly — but 100 static cells
elsewhere share its colour, so the whole-board colour total only falls
164 -> 100 = 61% and the "must actually empty" test rejected it. Measured
per region the same bar reads 0% and passes.

As everywhere in this codebase the refusals matter as much as the
successes: grouping must not merge things that are merely adjacent in
colour space, and tracking must not hand one thing another's identity.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import entities  # noqa: E402
import perception  # noqa: E402


class Frame:
    def __init__(self, grid):
        self.frame = [grid]


def grid(cells=None, fill=0, size=8):
    g = [[fill] * size for _ in range(size)]
    for (x, y), v in (cells or {}).items():
        g[y][x] = v
    return g


# ── connected_regions ───────────────────────────────────────────────────

def test_separates_two_blobs_of_the_same_colour():
    # THE case this layer was built for: same colour, different objects.
    # Counting colour totals would report one number for both.
    g = grid({(1, 1): 5, (2, 1): 5, (6, 6): 5, (6, 7): 5})
    found = perception.connected_regions(Frame(g), min_size=2)
    fives = [cells for colour, cells in found if colour == 5]
    assert len(fives) == 2, "two separate blobs must not be merged"
    assert {len(c) for c in fives} == {2}


def test_diagonal_touch_is_not_connected():
    # Four-connectivity. Diagonal neighbours are a different object until
    # something shows otherwise.
    g = grid({(1, 1): 5, (2, 2): 5})
    fives = [c for col, c in perception.connected_regions(Frame(g), 1) if col == 5]
    assert len(fives) == 2


def test_min_size_filters_small_regions():
    g = grid({(1, 1): 5, (2, 1): 5, (2, 2): 5, (6, 6): 5})
    fives = [c for col, c in perception.connected_regions(Frame(g), min_size=3)
             if col == 5]
    assert len(fives) == 1 and len(fives[0]) == 3


def test_background_is_a_region_like_any_other():
    # No special case for the canvas -- it is grouped the same way, and
    # whether it means anything is somebody else's question.
    found = perception.connected_regions(Frame(grid()), min_size=1)
    assert len(found) == 1 and len(found[0][1]) == 64


def test_empty_frame_yields_nothing():
    empty = Frame([])
    empty.frame = []
    assert perception.connected_regions(empty) == []


# ── RegionTracker ───────────────────────────────────────────────────────

def _bar(length, y=7, colour=4):
    return (colour, frozenset((x, y) for x in range(length)))


def test_a_shrinking_region_keeps_its_identity():
    # A draining bar changes size every frame. Identity must come from
    # overlap, not from shape or size, or the series breaks every tick.
    t = entities.RegionTracker()
    first = t.update([_bar(8)])
    rid = next(iter(first))
    for n in (7, 6, 5):
        got = t.update([_bar(n)])
        assert rid in got, "the bar must stay the same region as it drains"
        assert len(got[rid][1]) == n


def test_a_region_that_vanishes_and_returns_is_recognised():
    # The case that made cd82's meter undetectable: a bar empties
    # completely, and if its id dies with it the refill looks like a brand
    # new object, so the sawtooth never closes.
    t = entities.RegionTracker()
    rid = next(iter(t.update([_bar(8)])))
    assert t.update([]) == {}, "nothing is present while it is empty"
    back = t.update([_bar(8)])
    assert rid in back, "a refilled bar must be the same region again"


def test_two_regions_do_not_swap_identities():
    t = entities.RegionTracker()
    a = (4, frozenset({(0, 0), (1, 0)}))
    b = (4, frozenset({(6, 6), (7, 6)}))
    first = t.update([a, b])
    ids = {cells: rid for rid, (_c, cells) in first.items()}
    second = t.update([a, b])
    for rid, (_c, cells) in second.items():
        assert ids[cells] == rid


def test_a_region_that_changes_colour_is_a_different_thing():
    # Letting colours merge would quietly recreate the aggregate this
    # layer exists to escape.
    t = entities.RegionTracker()
    rid = next(iter(t.update([(4, frozenset({(0, 0), (1, 0)}))])))
    got = t.update([(9, frozenset({(0, 0), (1, 0)}))])
    assert rid not in got


def test_clear_drops_every_identity():
    t = entities.RegionTracker()
    rid = next(iter(t.update([_bar(8)])))
    t.clear()
    assert rid not in t.update([_bar(8)])


# ── proximity fallback ──────────────────────────────────────────────────
# Overlap cannot follow a thing that moves further than its own width, and
# most moving objects do: a stride tends to exceed a sprite. Without this,
# ls20's entities were reborn every step and no belief could accumulate.

def _blob(x0, y0, n=3, colour=7):
    return (colour, frozenset((x0 + i, y0) for i in range(n)))


def test_an_object_that_jumps_clear_of_itself_keeps_its_identity():
    # ls20's stride is 5 and its sprite is smaller, so successive
    # positions share no cells at all.
    t = entities.RegionTracker()
    rid = next(iter(t.update([_blob(0, 0)])))
    got = t.update([_blob(5, 0)])
    assert rid in got, "a 5-cell jump is the same object on ls20"


def test_a_jump_too_far_is_a_different_object():
    # Measured: genuine reappearances sit at distance 3-5, and the nearest
    # thing that is NOT the same object is at 10.
    t = entities.RegionTracker()
    rid = next(iter(t.update([_blob(0, 0)])))
    got = t.update([_blob(40, 0)])
    assert rid not in got


def test_proximity_will_not_match_a_very_different_size():
    # Close by is not enough; a region a quarter the size is another thing.
    # Positioned so the two do NOT overlap, because the overlap pass has
    # no size guard on purpose — a draining bar changes size drastically
    # and must keep its identity, so only the proximity path checks size.
    t = entities.RegionTracker()
    rid = next(iter(t.update([_blob(0, 0, n=12)])))      # centroid x=5.5
    got = t.update([_blob(12, 0, n=3)])                  # centroid x=13
    assert not (frozenset((i, 0) for i in range(12))
                & frozenset((12 + i, 0) for i in range(3))), "must not overlap"
    assert rid not in got


def test_overlap_still_wins_over_proximity():
    # Overlap is the stronger evidence and must be tried first, or a
    # passing neighbour could steal a stationary object's identity.
    t = entities.RegionTracker()
    first = t.update([_blob(0, 0), _blob(20, 0)])
    ids = {cells: rid for rid, (_c, cells) in first.items()}
    second = t.update([_blob(1, 0), _blob(20, 0)])
    for rid, (_c, cells) in second.items():
        if cells == _blob(20, 0)[1]:
            assert rid == ids[cells], "the stationary one keeps its id"


def test_two_neighbours_do_not_swap_identities():
    t = entities.RegionTracker()
    a, b = _blob(0, 0), _blob(12, 0)
    first = t.update([a, b])
    ids = {cells: rid for rid, (_c, cells) in first.items()}
    # Both step 3 to the right — near each other, but each is nearer its own.
    second = t.update([_blob(3, 0), _blob(15, 0)])
    by_id = {rid: cells for rid, (_c, cells) in second.items()}
    assert by_id[ids[a[1]]] == _blob(3, 0)[1]
    assert by_id[ids[b[1]]] == _blob(15, 0)[1]
