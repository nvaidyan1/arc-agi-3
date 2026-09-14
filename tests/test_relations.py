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


# ── the grouping view ───────────────────────────────────────────────────

def frame_fill(x0, y0):
    """A 5x5 frame of colour 2 around a 3x3 fill of colour 15 — an open
    bucket would not be enclosed, but its fill sits inside its bbox."""
    outer = sq(x0, y0, 5, 5) - sq(x0 + 1, y0 + 1, 3, 3) - {(x0 + 2, y0)}  # open at the top
    return {1: (2, outer), 2: (15, sq(x0 + 1, y0 + 1, 3, 3))}


def test_a_fill_inside_a_frame_groups_once_it_has_persisted():
    e = RelationEngine()
    for _ in range(2):
        step(e, frame_fill(10, 10))
    assert e.groups() == []                       # containment held 1 step so far
    for _ in range(3):
        step(e, frame_fill(10, 10))
    assert e.groups() == [frozenset({1, 2})]


def test_a_thing_passing_through_a_box_does_not_group():
    e = RelationEngine()
    big, small = (7, sq(0, 0, 10, 10)), (3, sq(20, 0))
    step(e, {1: big, 2: small}); step(e, {1: big, 2: small})
    step(e, {1: big, 2: (3, sq(3, 3))})          # inside for one step
    step(e, {1: big, 2: (3, sq(20, 0))})
    step(e, {1: big, 2: (3, sq(20, 0))})
    assert e.groups() == []


def test_regions_that_keep_trading_cells_group():
    # A recolour mechanic: part of 1 becomes 2, step after step.
    e = RelationEngine()
    w = 6
    for k in range(6):
        step(e, {1: (7, sq(0, 0, w - k, 4) if w - k > 0 else frozenset({(0, 0)})),
                 2: (3, sq(w - k, 0, k + 1, 4))}, action="ACTION5")
    assert e.groups() == [frozenset({1, 2})]


def test_group_palette_diff_is_over_the_union_of_colours():
    e = RelationEngine()
    def scene():
        d = frame_fill(10, 10)                   # group {1,2}: colours {2,15}
        d[3] = (15, sq(40, 40))                  # a lone pink thing
        d[4] = (9, sq(50, 50))                   # a lone other thing
        return d
    for _ in range(5):
        step(e, scene())
    snap = e.snapshot()
    assert snap[("palette_diff", (1, 2), (3,))] == 1      # {2,15} ^ {15} = {2}
    assert snap[("palette_diff", (1, 2), (4,))] == 3      # {2,15} ^ {9}
    assert ("palette_diff", (3,), (4,)) not in snap        # singleton pairs stay ordinary


def test_groups_are_a_view_and_dissolve_when_the_evidence_stops():
    e = RelationEngine()
    for _ in range(5):
        step(e, frame_fill(10, 10))
    assert e.groups()
    # The fill leaves the frame and stays out.
    d = frame_fill(10, 10); d[2] = (15, sq(40, 40))
    for _ in range(2):
        step(e, d)
    assert e.groups() == []


# ── levers ──────────────────────────────────────────────────────────────

def _tally(**kw):
    rec = relations.PairRecord()
    for act, (d, u, f) in kw.items():
        rec.by_action[act] = {relations.DOWN: d, relations.UP: u, relations.FLAT: f}
    return rec


def test_a_residual_every_action_moves_alike_has_no_lever():
    # The timer bar: falls on 9 of 10 steps whatever is pressed.
    rec = _tally(ACTION1=(9, 0, 1), ACTION2=(9, 0, 1), ACTION3=(9, 0, 1), ACTION4=(9, 0, 1))
    assert rec.movers(relations.DOWN)                    # it certainly moves
    assert rec.lever(relations.DOWN) is None             # but nothing drives it


def test_the_action_that_stands_out_is_the_lever():
    rec = _tally(ACTION1=(8, 0, 2), ACTION2=(1, 2, 7), ACTION3=(0, 8, 2), ACTION4=(1, 1, 8))
    act, lift = rec.lever(relations.DOWN)
    assert act == "ACTION1" and lift > 0.5
    assert rec.lever(relations.UP)[0] == "ACTION3"


def test_a_lever_needs_tries():
    rec = _tally(ACTION1=(2, 0, 0), ACTION2=(0, 0, 10))
    assert rec.lever(relations.DOWN) is None             # 2 tries is a coincidence


# ── the matching family: palette_missing and part_size_diff ─────────────

def template_and_block(black_rows):
    """A framed template (yellow frame 4, black 0 on top, pink 15 below) and
    a free-standing two-colour block whose top `black_rows` rows are black."""
    frame = sq(0, 0, 8, 8) - sq(1, 1, 6, 6)
    t_black, t_pink = sq(1, 1, 6, 3), sq(1, 4, 6, 3)
    b_black = sq(30, 30, 6, black_rows) if black_rows else frozenset()
    b_pink = sq(30, 30 + black_rows, 6, 6 - black_rows)
    d = {1: (4, frame), 2: (0, t_black), 3: (15, t_pink), 5: (15, b_pink)}
    if b_black:
        d[4] = (0, b_black)
    return d


def paint(e, rows_sequence):
    """Step through black_rows values; each change trades cells between the
    block's halves, which is what groups them (adjacency alone never does)."""
    for rows in rows_sequence:
        step(e, template_and_block(rows), action="ACTION5")


def test_palette_missing_says_the_block_is_made_only_of_template_colours():
    e = RelationEngine()
    paint(e, (1, 2, 3, 2, 3))                                     # four exchanges: grouped
    snap = e.snapshot()
    assert snap[("palette_missing", (4, 5), (1, 2, 3))] == 0     # block -> template: nothing missing
    assert snap[("palette_missing", (1, 2, 3), (4, 5))] == 1     # template -> block: the frame colour


def test_part_size_diff_falls_as_the_proportions_are_painted_toward_the_template():
    e = RelationEngine()
    paint(e, (1, 2, 3, 2, 3, 2))                                  # well past the grouping bar
    values = []
    for rows in (1, 2, 3):                                        # painting black downward
        step(e, template_and_block(rows), action="ACTION5")
        values.append(e.snapshot().get(("part_size_diff", (1, 2, 3), (4, 5))))
    # template: black 18, pink 18. block rows=1: black 6 / pink 30 -> |18-6|+|18-30| = 24;
    # rows=2: 12/24 -> 12; rows=3: 18/18 -> 0.
    assert values == [24, 12, 0]
    rec = e.group_records[("part_size_diff", (1, 2, 3), (4, 5))]
    assert rec.by_action["ACTION5"][relations.DOWN] >= 2


def test_part_size_diff_is_none_with_no_shared_colour():
    e = RelationEngine()
    d = template_and_block(1); d[6] = (9, sq(50, 50, 4, 4)); d[7] = (11, sq(50, 55, 4, 2))
    for _ in range(5):
        step(e, d)
    # {6,7} never groups (not enclosed, no exchange); as a singleton each has no shared colour.
    assert e.snapshot()[("part_size_diff", (1, 2, 3), (6,))] is None


def test_a_group_whose_part_is_reborn_keeps_its_record():
    # The block's pink half gets a new id after each paint (as cd82's does);
    # the template-vs-block record must carry on and the paint action must
    # accumulate its lever on it.
    e = RelationEngine()
    # Exchange evidence accrues per direction, so the halves group on the
    # fifth step; two more paint steps give the record one DOWN before the
    # rebirth we are about to test.
    paint(e, (1, 2, 3, 2, 3, 2, 3, 2))
    before = e.group_records[("part_size_diff", (1, 2, 3), (4, 5))].by_action["ACTION5"][relations.DOWN]
    assert before >= 1
    # Pink half reborn as #9; it keeps trading cells with the black half
    # as painting continues, so the pair re-groups — and must inherit.
    for rows in (3, 2, 3, 2, 3):
        d = template_and_block(rows); d[9] = d.pop(5)
        step(e, d, action="ACTION5")
    keys = [k for k in e.group_records
            if k[0] == "part_size_diff" and k[1] == (1, 2, 3) and len(k[2]) > 1]
    assert keys == [("part_size_diff", (1, 2, 3), (4, 5))], keys  # one group record, the old one
    rec = e.group_records[keys[0]]
    assert rec.by_action["ACTION5"][relations.DOWN] > before        # the lever kept accumulating
    assert e.record(("part_size_diff", (1, 2, 3), (4, 9))) is rec  # new members resolve to it
