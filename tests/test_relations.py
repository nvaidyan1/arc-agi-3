"""Relations as residuals: `int` when decidable, `None` when not, never False.

The refusals matter more than the values. A pair with a ghost in it, a pair
seen for the first time this step, and a drift with one frame of history
must all be None — a None is a question the agent could act to decide, and
a False in its place is exactly the type error the council named.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import relations  # noqa: E402
from relations import RelationEngine  # noqa: E402


def sq(x0, y0, w=3, h=3):
    return frozenset((x0 + i, y0 + j) for i in range(w) for j in range(h))


def frame(**ents):
    """{id: (colour, cells)} from keyword args like _1=(7, cells)."""
    return {int(k.lstrip("_")): v for k, v in ents.items()}


def step(engine, tracked, action="ACTION1", live=None):
    return engine.update(tracked, live if live is not None else tracked.keys(), action)


# ── decidability ────────────────────────────────────────────────────────

def test_everything_is_none_on_the_first_sighting():
    e = RelationEngine()
    out = step(e, frame(_1=(7, sq(0, 0)), _2=(3, sq(10, 10))))
    assert out and all(v is None for v in out.values())


def test_a_pair_with_a_ghost_is_none():
    e = RelationEngine()
    t = frame(_1=(7, sq(0, 0)), _2=(3, sq(10, 10)))
    step(e, t)
    out = step(e, t, live={1})                 # 2 is remembered, not live
    assert out[("distance", 1, 2)] is None
    assert ("distance", 1, 2) in e.undecided()


def test_drift_needs_two_distances():
    e = RelationEngine()
    t = frame(_1=(7, sq(0, 0)), _2=(3, sq(10, 0)))
    step(e, t)
    out = step(e, t)
    assert out[("distance", 1, 2)] == 10
    assert out[("distance_drift", 1, 2)] is None
    out = step(e, frame(_1=(7, sq(2, 0)), _2=(3, sq(10, 0))))
    assert out[("distance", 1, 2)] == 8
    assert out[("distance_drift", 1, 2)] == 2


# ── the values ──────────────────────────────────────────────────────────

def test_palette_diff_counts_the_symmetric_difference():
    e = RelationEngine()
    t = frame(_1=(7, sq(0, 0)), _2=(3, sq(10, 10)), _3=(7, sq(20, 20)))
    step(e, t); out = step(e, t)
    assert out[("palette_diff", 1, 2)] == 2
    assert out[("palette_diff", 1, 3)] == 0


def test_shape_diff_is_zero_on_equality_and_none_otherwise():
    # Same cells up to translation: 0. Anything else: None, not a distance —
    # a similarity score would be a threshold, and a threshold is a prior.
    e = RelationEngine()
    t = frame(_1=(7, sq(0, 0)), _2=(3, sq(10, 10)), _3=(3, sq(20, 20, 3, 4)))
    step(e, t); out = step(e, t)
    assert out[("shape_diff", 1, 2)] == 0
    assert out[("shape_diff", 1, 3)] is None


def test_containment_counts_cells_outside_the_box_and_is_directional():
    e = RelationEngine()
    t = frame(_1=(7, sq(0, 0, 10, 10)), _2=(3, sq(2, 2)))
    step(e, t); out = step(e, t)
    assert out[("containment", 1, 2)] == 0        # 2 inside 1's box
    assert out[("containment", 2, 1)] == 100 - 9  # most of 1 is outside 2's box


def test_count_diff_compares_colour_classes_over_live_entities():
    e = RelationEngine()
    t = frame(_1=(7, sq(0, 0)), _2=(7, sq(10, 0)), _3=(7, sq(20, 0)), _4=(3, sq(30, 0)))
    step(e, t); out = step(e, t)
    assert out[("count_diff", 1, 4)] == 2         # three 7s, one 3
    assert out[("count_diff", 1, 2)] == 0


def test_cell_exchange_is_the_cells_one_lost_that_the_other_gained():
    # A recolour of part of a thing: region 1 shrinks exactly where 2 grows.
    e = RelationEngine()
    step(e, frame(_1=(7, sq(0, 0, 4, 4)), _2=(3, sq(4, 0, 2, 4))))
    step(e, frame(_1=(7, sq(0, 0, 4, 4)), _2=(3, sq(4, 0, 2, 4))))
    out = step(e, frame(_1=(7, sq(0, 0, 3, 4)), _2=(3, sq(3, 0, 3, 4))), action="ACTION5")
    assert out[("cell_exchange", 1, 2)] == 4
    assert out[("cell_exchange", 2, 1)] == 0
    assert "cell_exchange" in relations.EVIDENCE_ONLY


def test_never_aligns_two_grids():
    # Same palette, same size, different shapes: the only thing the layer
    # will say is "palette 0, shape undecidable". No cellwise similarity.
    e = RelationEngine()
    t = frame(_1=(7, sq(0, 0, 2, 6)), _2=(7, sq(20, 20, 3, 4)))
    step(e, t); out = step(e, t)
    assert out[("palette_diff", 1, 2)] == 0
    assert out[("shape_diff", 1, 2)] is None
    assert not any(k[0] in ("similar_shape", "overlap", "match") for k in out)


# ── actuation: action -> delta residual ─────────────────────────────────

def test_actions_are_credited_with_the_direction_they_moved_a_residual():
    e = RelationEngine()
    t = frame(_1=(7, sq(0, 0)), _2=(3, sq(20, 0)))
    step(e, t); step(e, t)
    step(e, frame(_1=(7, sq(5, 0)), _2=(3, sq(20, 0))), action="ACTION4")   # closer
    step(e, frame(_1=(7, sq(10, 0)), _2=(3, sq(20, 0))), action="ACTION4")  # closer
    step(e, frame(_1=(7, sq(5, 0)), _2=(3, sq(20, 0))), action="ACTION3")   # further
    rec = e.records[("distance", 1, 2)]
    assert rec.by_action["ACTION4"][relations.DOWN] == 2
    assert rec.by_action["ACTION3"][relations.UP] == 1
    assert rec.movers(relations.DOWN) == [("ACTION4", 2)]


def test_a_question_resolving_is_not_motion():
    # None -> value must not be credited to the action as a change.
    e = RelationEngine()
    t = frame(_1=(7, sq(0, 0)), _2=(3, sq(20, 0)))
    step(e, t, action="ACTION1")
    step(e, t, action="ACTION2")                   # first defined value
    rec = e.records[("distance", 1, 2)]
    assert rec.by_action == {}
    assert not rec.moved


def test_moved_lists_only_residuals_that_changed_this_step():
    e = RelationEngine()
    t = frame(_1=(7, sq(0, 0)), _2=(3, sq(20, 0)))
    step(e, t); step(e, t)
    step(e, frame(_1=(7, sq(5, 0)), _2=(3, sq(20, 0))), action="ACTION4")
    keys = {k for k, _p, _c in e.moved()}
    assert ("distance", 1, 2) in keys
    assert ("palette_diff", 1, 2) not in keys


def test_skipped_entities_take_part_in_nothing():
    # The canvas: live, tracked, and deliberately not a relatum.
    e = RelationEngine()
    t = frame(_1=(7, sq(0, 0)), _2=(3, sq(10, 0)), _9=(5, sq(0, 20, 30, 30)))
    e.update(t, t.keys(), "ACTION1", skip={9})
    out = e.update(t, t.keys(), "ACTION1", skip={9})
    assert not any(9 in k[1:] for k in out)
    assert out[("count_diff", 1, 2)] == 0          # the canvas is not counted either
