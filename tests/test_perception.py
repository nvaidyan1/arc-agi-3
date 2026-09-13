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
