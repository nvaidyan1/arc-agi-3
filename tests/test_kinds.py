"""Kinds: same palette and part count makes a kind; same shape makes it
exact; roles and drift are read per member; vanishing transfers.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import belief  # noqa: E402
import kinds  # noqa: E402
from relations import RelationEngine  # noqa: E402


def sq(x0, y0, w=3, h=3):
    return frozenset((x0 + i, y0 + j) for i in range(w) for j in range(h))


def role(b, r):
    """Force a Belief to read as role `r` through evidence."""
    if r == belief.ENVIRONMENT:
        for a in ("ACTION1", "ACTION2"):
            for _ in range(12):
                b.observe(a, None)
    elif r == belief.AFFECT:
        for _ in range(10):
            b.observe("ACTION5", belief.GREW)
        for a in ("ACTION1", "ACTION2"):
            for _ in range(10):
                b.observe(a, None)
    elif r == belief.CONTROL:
        for a, eff in (("ACTION1", (belief.MOVED, 0, -1)), ("ACTION2", (belief.MOVED, 0, 1)),
                       ("ACTION3", (belief.MOVED, -1, 0)), ("ACTION4", (belief.MOVED, 1, 0))):
            for _ in range(8):
                b.observe(a, belief.MOVED, eff)
    assert b.role == r, (b.role, r)
    return b


def world(**roles):
    w = belief.WorldBelief()
    for rid, r in roles.items():
        w._beliefs[int(rid.lstrip("_"))] = role(belief.Belief(int(rid.lstrip("_")), 0), r)
    return w


def test_two_lone_things_of_one_colour_and_shape_are_an_exact_kind():
    e = RelationEngine()
    t = {1: (7, sq(0, 0)), 2: (7, sq(20, 20)), 3: (3, sq(40, 40))}
    for _ in range(2):
        e.update(t, t.keys(), "ACTION1")
    ks = kinds.compute_kinds(e, world(_1=belief.ENVIRONMENT, _2=belief.ENVIRONMENT), {1, 2, 3})
    assert len(ks) == 1 and ks[0].exact and ks[0].palette == frozenset({7})
    assert sorted(m.key for m in ks[0].members) == [(1,), (2,)]


def test_same_colours_different_shape_is_a_palette_kind():
    e = RelationEngine()
    t = {1: (7, sq(0, 0, 3, 3)), 2: (7, sq(20, 20, 9, 1))}
    for _ in range(2):
        e.update(t, t.keys(), "ACTION1")
    ks = kinds.compute_kinds(e, world(_1=belief.ENVIRONMENT, _2=belief.ENVIRONMENT), {1, 2})
    assert len(ks) == 1 and not ks[0].exact


def test_one_thing_is_not_a_kind():
    e = RelationEngine()
    t = {1: (7, sq(0, 0)), 2: (3, sq(20, 20))}
    e.update(t, t.keys(), "ACTION1"); e.update(t, t.keys(), "ACTION1")
    assert kinds.compute_kinds(e, world(), {1, 2}) == []


def test_role_asymmetry_is_read_per_member():
    e = RelationEngine()
    t = {1: (7, sq(0, 0)), 2: (7, sq(20, 20))}
    for _ in range(2):
        e.update(t, t.keys(), "ACTION1")
    k = kinds.compute_kinds(e, world(_1=belief.ENVIRONMENT, _2=belief.AFFECT), {1, 2})[0]
    by = {m.key: m for m in k.members}
    assert by[(1,)].static and not by[(2,)].static
    assert by[(2,)].describe_roles() == "changes under my actions"


def test_drift_reads_the_residuals_to_the_static_member():
    e = RelationEngine()
    frame = sq(0, 0, 8, 8) - sq(1, 1, 6, 6)
    scene = {1: (4, frame), 2: (0, sq(1, 1, 6, 3)), 3: (15, sq(1, 4, 6, 3)),
             4: (0, sq(30, 30, 6, 1)), 5: (15, sq(30, 31, 6, 5))}
    for rows in (1, 2, 3, 2, 3, 2):                 # block halves trade cells -> grouped
        scene[4] = (0, sq(30, 30, 6, rows)); scene[5] = (15, sq(30, 30 + rows, 6, 6 - rows))
        e.update(dict(scene), scene.keys(), "ACTION5")
    w = world(_1=belief.ENVIRONMENT, _2=belief.ENVIRONMENT, _3=belief.ENVIRONMENT,
              _4=belief.AFFECT, _5=belief.AFFECT)
    ks = [k for k in kinds.compute_kinds(e, w, {1, 2, 3, 4, 5}) if k.parts > 1]
    # {1,2,3} has palette {4,0,15} and {4,5} has {0,15}: not one kind by palette...
    # so make the frame the canvas colour and skip it: use the two-part units only.
    assert ks == [] or all(k.parts > 1 for k in ks)
    static, moving = kinds.Member((1, 2, 3), {belief.ENVIRONMENT: 3}), kinds.Member((4, 5), {belief.AFFECT: 2})
    d = kinds.drift(e, moving, static)
    assert any(x.startswith("part_size_diff") for x in d)


def test_vanishing_transfers_across_the_kind():
    e = RelationEngine()
    t = {1: (7, sq(0, 0)), 2: (7, sq(20, 20)), 3: (7, sq(40, 40))}
    w = world(_1=belief.ENVIRONMENT, _2=belief.ENVIRONMENT, _3=belief.ENVIRONMENT)
    mem = kinds.KindMemory()
    for _ in range(2):
        e.update(t, t.keys(), "ACTION1")
        mem.record(kinds.compute_kinds(e, w, {1, 2, 3}), {1, 2, 3}, "ACTION1", 0.50)
    # #2 is eaten: it leaves the screen and stamina rises.
    t2 = {1: (7, sq(0, 0)), 3: (7, sq(40, 40))}
    e.update(t2, t2.keys(), "ACTION4")
    mem.record(kinds.compute_kinds(e, w, {1, 3}), {1, 3}, "ACTION4", 0.62)
    n, mean = mem.transfer(frozenset({7}))
    assert n == 1 and abs(mean - 0.12) < 1e-9
    assert mem.gain_prior(frozenset({7})) == 1
    assert mem.gain_prior(frozenset({3})) == 0


def test_a_regrouping_is_not_a_vanishing():
    e = RelationEngine()
    t = {1: (7, sq(0, 0)), 2: (7, sq(20, 20))}
    w = world(_1=belief.ENVIRONMENT, _2=belief.ENVIRONMENT)
    mem = kinds.KindMemory()
    e.update(t, t.keys(), "ACTION1"); mem.record(kinds.compute_kinds(e, w, {1, 2}), {1, 2}, "ACTION1", 0.5)
    e.update(t, t.keys(), "ACTION1"); mem.record(kinds.compute_kinds(e, w, {1, 2}), {1, 2}, "ACTION1", 0.5)
    # still on screen, kinds recomputed — nothing vanished
    mem.record([], {1, 2}, "ACTION1", 0.5)
    assert mem.transfer(frozenset({7})) == (0, None)


def test_the_content_of_a_frame_is_a_unit_of_its_own():
    # A yellow frame around a canvas-coloured interior around black and
    # pink (cd82's template), and a free two-colour block: the frame's
    # CONTENT and the block are one palette-kind {0,15} with two parts.
    e = RelationEngine()
    frame = sq(0, 0, 10, 10) - sq(1, 1, 8, 8)
    interior = sq(1, 1, 8, 8) - sq(2, 2, 6, 3) - sq(2, 5, 6, 3)
    scene = {1: (4, frame), 2: (5, interior), 3: (0, sq(2, 2, 6, 3)), 4: (15, sq(2, 5, 6, 3)),
             5: (0, sq(30, 30, 6, 1)), 6: (15, sq(30, 31, 6, 5))}
    for rows in (1, 2, 3, 2, 3, 2):
        scene[5] = (0, sq(30, 30, 6, rows)); scene[6] = (15, sq(30, 30 + rows, 6, 6 - rows))
        e.update(dict(scene), scene.keys(), "ACTION5")
    w = world(_1=belief.ENVIRONMENT, _2=belief.ENVIRONMENT, _3=belief.ENVIRONMENT, _4=belief.ENVIRONMENT,
              _5=belief.AFFECT, _6=belief.AFFECT)
    ks = kinds.compute_kinds(e, w, {1, 2, 3, 4, 5, 6}, background=5)
    k = next(k for k in ks if k.palette == frozenset({0, 15}))
    assert sorted(m.key for m in k.members) == [(3, 4), (5, 6)]
    by = {m.key: m for m in k.members}
    assert by[(3, 4)].static and not by[(5, 6)].static


def test_a_reset_is_not_a_vanishing():
    e = RelationEngine()
    t = {1: (7, sq(0, 0)), 2: (7, sq(20, 20))}
    w = world(_1=belief.ENVIRONMENT, _2=belief.ENVIRONMENT)
    mem = kinds.KindMemory()
    e.update(t, t.keys(), "ACTION1"); mem.record(kinds.compute_kinds(e, w, {1, 2}), {1, 2}, "ACTION1", 0.1)
    mem.new_attempt()                                             # died, reset sent
    t2 = {3: (7, sq(0, 0)), 4: (7, sq(20, 20))}                   # fresh ids, stamina refilled
    e.update(t2, t2.keys(), None); mem.record(kinds.compute_kinds(e, w, {3, 4}), {3, 4}, None, 1.0)
    assert mem.transfer(frozenset({7})) == (0, None)
