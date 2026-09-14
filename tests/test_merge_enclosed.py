"""`merge_enclosed` folds a fill into its frame — and never into the canvas.

Found on sp80: the controllable bar touched nothing but background, so
"wholly surrounded by one other region" held and it was absorbed into the
canvas. The move map learned its offsets; no entity was ever CONTROL.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import perception  # noqa: E402


def box(x0, y0, w, h):
    return frozenset((x0 + i, y0 + j) for i in range(w) for j in range(h))


def scene():
    canvas_cells = box(0, 0, 20, 20)
    frame = box(2, 2, 5, 5) - box(3, 3, 3, 3)      # a frame...
    fill = box(3, 3, 3, 3)                         # ...around a fill
    lone = box(12, 12, 4, 2)                       # a solitary bar on the canvas
    canvas = canvas_cells - frame - fill - lone
    return [(12, canvas), (2, frame), (15, fill), (9, lone)]


def test_a_fill_is_folded_into_its_frame():
    merged = perception.merge_enclosed(scene(), background=12)
    colours = {c for c, _ in merged}
    assert 15 not in colours                       # the fill is gone into the frame
    frame = next(cells for c, cells in merged if c == 2)
    assert box(3, 3, 3, 3) <= frame


def test_a_solitary_object_is_not_folded_into_the_canvas():
    merged = perception.merge_enclosed(scene(), background=12)
    assert any(c == 9 and cells == box(12, 12, 4, 2) for c, cells in merged)


def test_without_a_known_background_the_largest_region_is_the_canvas():
    merged = perception.merge_enclosed(scene())
    assert any(c == 9 for c, _ in merged)
    assert not any(c == 15 for c, _ in merged)
