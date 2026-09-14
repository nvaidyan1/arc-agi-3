"""Unit tests for the falsifiable lenses in `agent/perception.py`.

This layer is stateless and deterministic — given two grids the right
answer is checkable by hand — which is why it is the layer worth testing
properly. Two things are asserted throughout:

  1. The positive case: the lens finds the explanation when it is there.
  2. **The None case**: the lens reports *nothing* when its explanation
     doesn't fit, rather than forcing an answer. That is the governing
     principle (docs/plan.md) and it is what stops a game we have never
     seen from being force-fit into the shape of the 25 we have, so it
     is tested at least as carefully as the positive case.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import perception  # noqa: E402


class Frame:
    """Minimal FrameData stand-in: these lenses only ever read `.frame`."""

    def __init__(self, grid: list[list[int]]) -> None:
        self.frame = [grid]


def grid(fill: int = 0, cells: dict | None = None, size: int = 12) -> list[list[int]]:
    g = [[fill] * size for _ in range(size)]
    for (x, y), v in (cells or {}).items():
        g[y][x] = v
    return g


def shape_at(x0: int, y0: int, colour: int, w: int = 2, h: int = 2) -> dict:
    return {(x0 + dx, y0 + dy): colour for dx in range(w) for dy in range(h)}


# ── diff_cells ──────────────────────────────────────────────────────────

def test_diff_cells_finds_changed_positions():
    a = Frame(grid(0, {(3, 4): 7}))
    b = Frame(grid(0, {(3, 4): 9}))
    assert perception.diff_cells(a, b) == [(3, 4)]


def test_diff_cells_empty_when_identical():
    a = Frame(grid(0, {(3, 4): 7}))
    assert perception.diff_cells(a, Frame(grid(0, {(3, 4): 7}))) == []


def test_diff_cells_survives_empty_frames():
    class Empty:
        frame: list = []

    assert perception.diff_cells(Empty(), Empty()) == []


# ── detect_translation ──────────────────────────────────────────────────

def test_detect_translation_finds_offset_size_and_anchor():
    a = Frame(grid(0, shape_at(2, 2, 5)))
    b = Frame(grid(0, shape_at(5, 2, 5)))
    result = perception.detect_translation(a, b)
    assert result is not None
    colour, size, offset, anchor = result
    assert (colour, size, offset, anchor) == (5, 4, (3, 0), (2, 2))


def test_detect_translation_anchor_enables_absolute_position():
    """The anchor + offset must land on where the shape actually went —
    this is what the router depends on to convert pixel targets."""
    a = Frame(grid(0, shape_at(2, 2, 5)))
    b = Frame(grid(0, shape_at(5, 4, 5)))
    _, _, offset, anchor = perception.detect_translation(a, b)
    assert (anchor[0] + offset[0], anchor[1] + offset[1]) == (5, 4)


def test_detect_translation_returns_none_for_a_recolour():
    """A shape changing colour in place is not a translation."""
    a = Frame(grid(0, shape_at(2, 2, 5)))
    b = Frame(grid(0, shape_at(2, 2, 6)))
    assert perception.detect_translation(a, b) is None


def test_detect_translation_returns_none_when_shape_deforms():
    """Losing a cell mid-move means no single offset explains the diff."""
    a = Frame(grid(0, shape_at(2, 2, 5)))
    partial = shape_at(5, 2, 5)
    partial.pop((6, 3))
    assert perception.detect_translation(a, Frame(grid(0, partial))) is None


def test_detect_translation_returns_none_on_unrelated_churn():
    a = Frame(grid(0, {(1, 1): 3, (9, 9): 4}))
    b = Frame(grid(0, {(1, 1): 8, (9, 9): 2}))
    assert perception.detect_translation(a, b) is None


# ── expected_move_occurred ──────────────────────────────────────────────

def test_expected_move_occurred_is_true_for_the_right_offset():
    a = Frame(grid(0, shape_at(2, 2, 5)))
    b = Frame(grid(0, shape_at(4, 2, 5)))
    assert perception.expected_move_occurred(a, b, (2, 0)) is True


def test_expected_move_occurred_is_false_for_the_wrong_offset():
    a = Frame(grid(0, shape_at(2, 2, 5)))
    b = Frame(grid(0, shape_at(4, 2, 5)))
    assert perception.expected_move_occurred(a, b, (0, 2)) is False


def test_detect_translation_ignores_change_in_other_colours():
    """Correspondence is per colour, so unrelated churn elsewhere does
    NOT defeat the strict test. Documenting this because it is easy to
    assume otherwise."""
    a = Frame(grid(0, {**shape_at(2, 2, 5), (10, 10): 1}))
    b = Frame(grid(0, {**shape_at(4, 2, 5), (10, 10): 2}))
    assert perception.detect_translation(a, b) is not None


def test_expected_move_occurred_tolerates_extra_change():
    """Weaker than detect_translation on purpose. One stray cell of the
    *moving shape's own colour* breaks the strict set-match, and each
    such case would otherwise be recorded as a false obstacle (measured
    ~4% of real moves). This test must still see the move."""
    a = Frame(grid(0, shape_at(2, 2, 5)))
    b = Frame(grid(0, {**shape_at(4, 2, 5), (10, 10): 5}))
    assert perception.detect_translation(a, b) is None  # strict test fails
    assert perception.expected_move_occurred(a, b, (2, 0)) is True  # this doesn't


# ── classify_change ─────────────────────────────────────────────────────

def test_classify_change_recolour_between_foreground_colours():
    a = Frame(grid(0, shape_at(2, 2, 3)))
    b = Frame(grid(0, shape_at(2, 2, 7)))
    recolours, cardinality, lost = perception.classify_change(a, b, background=0)
    assert recolours == {(3, 7): 4}
    assert cardinality == {} and lost == set()


def test_classify_change_appearance_is_positive_cardinality():
    a = Frame(grid(0))
    b = Frame(grid(0, shape_at(2, 2, 4)))
    recolours, cardinality, lost = perception.classify_change(a, b, background=0)
    assert cardinality == {4: 4} and recolours == {} and lost == set()


def test_classify_change_disappearance_reports_where():
    a = Frame(grid(0, shape_at(2, 2, 4)))
    b = Frame(grid(0))
    _, cardinality, lost = perception.classify_change(a, b, background=0)
    assert cardinality == {4: -4}
    assert lost == set(shape_at(2, 2, 4))


def test_classify_change_background_is_not_assumed_to_be_zero():
    """Regression guard: the canvas is whatever the caller says it is."""
    a = Frame(grid(9, {(1, 1): 0}))
    b = Frame(grid(9))
    _, cardinality, _ = perception.classify_change(a, b, background=9)
    assert cardinality == {0: -1}


def test_classify_change_respects_a_moving_background():
    """dc22 disagrees on 37.4% of steps between per-frame argmax and the
    level's initial canvas. Same pixels, different category."""
    prev = Frame(grid(9, shape_at(0, 0, 8, w=10, h=10)))  # 8 now dominant
    new = Frame(grid(9, {**shape_at(0, 0, 8, w=10, h=10), (11, 11): 8}))
    _, told, _ = perception.classify_change(prev, new, background=9)
    _, argmax, _ = perception.classify_change(prev, new)  # derives its own
    assert told == {8: 1}, "canvas remembered: content appeared"
    assert argmax != told, "per-frame argmax reaches a different verdict"


def test_classify_change_skips_cells_another_lens_explained():
    a = Frame(grid(0, {(2, 2): 3}))
    b = Frame(grid(0, {(3, 2): 3}))
    assert perception.classify_change(a, b, explained={(2, 2), (3, 2)}) is None


def test_classify_change_returns_none_when_nothing_changed():
    a = Frame(grid(0, {(1, 1): 5}))
    assert perception.classify_change(a, Frame(grid(0, {(1, 1): 5}))) is None


# ── residual_cells ──────────────────────────────────────────────────────

def test_residual_subtracts_our_own_movement():
    a = Frame(grid(0, shape_at(2, 2, 5)))
    b = Frame(grid(0, shape_at(4, 2, 5)))
    changed = perception.diff_cells(a, b)
    assert perception.residual_cells(a, b, changed, (2, 0), None) == []


def test_residual_keeps_what_movement_does_not_explain():
    a = Frame(grid(0, {**shape_at(2, 2, 5), (10, 10): 1}))
    b = Frame(grid(0, {**shape_at(4, 2, 5), (10, 10): 2}))
    changed = perception.diff_cells(a, b)
    assert perception.residual_cells(a, b, changed, (2, 0), None) == [(10, 10)]


def test_residual_subtracts_the_budget_meter():
    """Meter depletion recolours cells *away* from the meter colour, so
    both sides of the change must be checked, not just the new value."""
    a = Frame(grid(0, {(1, 1): 11}))
    b = Frame(grid(0, {(1, 1): 3}))
    changed = perception.diff_cells(a, b)
    assert perception.residual_cells(a, b, changed, None, 11) == []


def test_residual_without_a_move_map_is_the_whole_diff():
    """With offset=None there is no self to subtract — correct for games
    with no controllable movement, and the reason the map must not be
    gated on having a move map."""
    a = Frame(grid(0, {(5, 5): 1, (6, 6): 2}))
    b = Frame(grid(0, {(5, 5): 3, (6, 6): 4}))
    changed = perception.diff_cells(a, b)
    assert perception.residual_cells(a, b, changed, None, None) == changed


# ── detect_rotation ─────────────────────────────────────────────────────
# The lens that exists because `detect_translation` was the *only* rigid
# motion we tested for. It gets as far as "this colour lost as many cells
# as it gained" and then discards anything a single offset can't explain —
# so an object turning under the agent's own actions produced no evidence
# at all. Measured on wa30: 57 of 57 such events are exact rotations.

# An L, and its image under (x, y) -> (10 - y, x). Chosen so the two do
# not overlap: only *changed* cells reach the detector, so an overlapping
# turn presents as a smaller set (see the partial-overlap test below).
_L = {(2, 2), (2, 3), (2, 4), (3, 4)}
_L_CW = {(8, 2), (7, 2), (6, 2), (6, 3)}
_L_CCW = {(2, 8), (3, 8), (4, 8), (4, 7)}


def _frames(before, after, colour=7):
    return (Frame(grid(cells={c: colour for c in before})),
            Frame(grid(cells={c: colour for c in after})))


def test_detect_rotation_finds_a_quarter_turn_clockwise():
    found = perception.detect_rotation(*_frames(_L, _L_CW))
    assert found is not None
    colour, cells, kind, pivot = found
    assert (colour, cells, kind) == (7, 4, "rot90cw")
    # Pivot is doubled so a turn about a cell corner stays exact; (10, 10)
    # is the point (5, 5), which this rotation does indeed hold fixed.
    assert pivot == (10, 10)


def test_detect_rotation_distinguishes_the_two_directions():
    # Naming the direction is the point — a detector that called every
    # quarter turn "clockwise" would be worse than useless to a caller
    # trying to learn which action turns which way.
    assert perception.detect_rotation(*_frames(_L, _L_CW))[2] == "rot90cw"
    assert perception.detect_rotation(*_frames(_L, _L_CCW))[2] == "rot90ccw"


def test_detect_rotation_recovers_a_turn_from_partial_overlap():
    # Only cells that CHANGED reach the detector, so a shape rotating onto
    # part of itself presents a *smaller* set than the shape really is.
    # The constants are solved from whatever subset changed, so the answer
    # stays exact — this is the case that occurs in real play, and it is
    # also why a small shape can rotate and still be refused by the size
    # floor: the floor applies to the changed cells, not the object.
    before = {(4, 2), (4, 3), (4, 4), (4, 5), (5, 5)}   # bar with a foot
    after = {(8 - y, x) for x, y in before}             # quarter turn cw
    assert after & before, "this test is pointless without overlap"
    found = perception.detect_rotation(*_frames(before, after))
    assert found is not None
    colour, cells, kind, _pivot = found
    assert kind == "rot90cw"
    assert cells == 4, "one cell sat still, so only four are visible"


def test_detect_rotation_returns_none_for_a_translation():
    # A pure slide must be left to the translation lens: it composes into
    # a position, which a rotation does not.
    assert perception.detect_rotation(
        *_frames(_L, {(x + 5, y) for x, y in _L})) is None


def test_detect_rotation_returns_none_when_the_shape_deforms():
    # Same cell count, not a rigid motion. The exact set-equality check is
    # what refuses this, and it is the whole guarantee.
    assert perception.detect_rotation(
        *_frames(_L, {(8, 8), (9, 2), (1, 6), (0, 0)})) is None


def test_detect_rotation_refuses_shapes_below_the_size_floor():
    # Two cells can be rotated onto almost anything, so a fit there
    # explains nothing. MIN_ROTATION_CELLS is 3, set from the measured
    # size distribution rather than taste.
    before = {(2, 2), (2, 3)}
    after = {(10 - y, x) for x, y in before}
    assert perception.detect_rotation(*_frames(before, after)) is None


def test_detect_rotation_returns_none_on_an_unchanged_frame():
    g = grid(cells={c: 7 for c in _L})
    assert perception.detect_rotation(Frame(g), Frame(g)) is None


def test_detect_rotation_survives_empty_frames():
    empty = Frame([])
    empty.frame = []
    assert perception.detect_rotation(empty, empty) is None


# ── detect_shift ────────────────────────────────────────────────────────
# The deformation-tolerant lens. Every exact lens demands the shape be
# identical before and after, which is too strict for anything that
# animates: cd82's controllable object changes by up to 14 cells as it
# moves, so translation and rotation both refuse it and the game ends up
# with no move map at all.

def _blob(x0, y0, w, h):
    return {(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h)}


def test_detect_shift_reports_motion_despite_a_changed_shape():
    before = _blob(2, 2, 4, 3)            # 12 cells
    after = _blob(8, 2, 3, 4)             # 12 cells, different shape
    found = perception.detect_shift(*_frames(before, after), background=0)
    assert found is not None
    colour, cells, (dx, dy), _anchor = found
    assert colour == 7 and dx > 0 and dy == 0


def test_detect_shift_refuses_when_the_masses_differ_too_much():
    # Without this guard, a colour consumed on one side of the board and
    # created on the other would read as an object travelling.
    before = _blob(2, 2, 4, 3)            # 12 cells
    after = _blob(9, 2, 1, 3)             # 3 cells — not the same thing
    assert perception.detect_shift(*_frames(before, after), background=0) is None


def test_detect_shift_refuses_tiny_changes():
    # Centroid motion is weaker evidence than an exact offset, so a few
    # cells drifting must not be promoted to "an object moved".
    before = {(2, 2), (3, 2)}
    after = {(9, 2), (10, 2)}
    assert perception.detect_shift(*_frames(before, after), background=0) is None


def test_detect_shift_is_silent_when_nothing_moved():
    g = grid(cells={c: 7 for c in _blob(2, 2, 4, 3)})
    assert perception.detect_shift(Frame(g), Frame(g), background=0) is None


def test_detect_shift_picks_the_largest_mover_deterministically():
    # Two colours move at once; dict ordering must not decide which one
    # the caller learns about.
    before = {c: 7 for c in _blob(2, 2, 4, 3)}
    before.update({c: 5 for c in _blob(2, 40, 6, 4)})
    after = {c: 7 for c in _blob(9, 2, 4, 3)}
    after.update({c: 5 for c in _blob(9, 40, 6, 4)})
    found = perception.detect_shift(Frame(grid(cells=before, size=50)),
                                    Frame(grid(cells=after, size=50)),
                                    background=0)
    assert found is not None and found[0] == 5, "24 cells beats 12"


def test_detect_shift_survives_empty_frames():
    empty = Frame([])
    empty.frame = []
    assert perception.detect_shift(empty, empty, background=0) is None


def test_detect_shift_ignores_the_background():
    # The regression that made this parameter mandatory. One object moves
    # right; the canvas loses cells where it arrived and gains them where
    # it left, so the canvas "moves" LEFT and is the larger candidate.
    # Without the guard the move map learns a reversed offset for every
    # action on every game.
    before = {c: 7 for c in _blob(2, 2, 4, 3)}
    after = {c: 7 for c in _blob(9, 2, 4, 3)}
    unguarded = perception.detect_shift(Frame(grid(cells=before, size=20)),
                                        Frame(grid(cells=after, size=20)))
    guarded = perception.detect_shift(Frame(grid(cells=before, size=20)),
                                      Frame(grid(cells=after, size=20)),
                                      background=0)
    assert guarded is not None and guarded[0] == 7 and guarded[2][0] > 0
    if unguarded is not None and unguarded[0] == 0:
        assert unguarded[2][0] < 0, "the canvas really does read backwards"
