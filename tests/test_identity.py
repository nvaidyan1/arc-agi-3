"""Identity that survives the game's own stride, and beliefs that know
whether their entity is on screen.

Found on cd82: the bucket hops 11-15 cells around the block, proximity
matching reaches 8, so every hop minted a new id and left the old one
behind as a remembered ghost. The belief layer was fed the tracker's
*memory* rather than its *current frame*, so ghosts kept accumulating
observations, kept their roles, and the router was routing the bucket
toward its own ghost.

Two fixes, tested separately:
  * the tracker follows a region that lands where the caller's own move
    map said it would (explained motion) — and refuses the same hop when
    nothing explains it;
  * a belief observes only while its entity is live, records one VANISHED
    when it goes, and is excluded from role queries while it is gone.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import belief  # noqa: E402
import entities  # noqa: E402


def _blob(x0, y0, n=3, colour=7):
    return (colour, frozenset((x0 + i, y0) for i in range(n)))


def _tilted(x0, y0, colour=7):
    """A different rasterisation of roughly the same-sized thing."""
    return (colour, frozenset({(x0, y0), (x0 + 1, y0 + 1), (x0 + 2, y0 + 2), (x0 + 1, y0)}))


# ── explained motion ────────────────────────────────────────────────────

def test_a_hop_the_move_map_predicts_keeps_its_identity():
    # Far beyond the proximity bound, so only the explanation can carry it.
    t = entities.RegionTracker()
    rid = next(iter(t.update([_blob(0, 0)])))
    got = t.update([_blob(20, 0)], expected_offset=(20, 0))
    assert rid in got


# The hopping object below re-rasterises as it moves (as cd82's bucket
# does), so the shape-revive pass -- which follows an IDENTICAL shape
# anywhere within a few frames, the reset-teleport case -- cannot carry
# it. That isolates explained motion as the only evidence in play.

def test_the_same_hop_unexplained_is_a_different_object():
    t = entities.RegionTracker()
    rid = next(iter(t.update([_blob(0, 0)])))
    got = t.update([_tilted(20, 0)])
    assert rid not in got


def test_a_hop_in_the_wrong_direction_is_not_explained():
    t = entities.RegionTracker()
    rid = next(iter(t.update([_blob(0, 0)])))
    got = t.update([_tilted(20, 0)], expected_offset=(0, 20))
    assert rid not in got


def test_explained_motion_still_requires_the_same_colour():
    t = entities.RegionTracker()
    rid = next(iter(t.update([_blob(0, 0, colour=7)])))
    got = t.update([_blob(20, 0, colour=3)], expected_offset=(20, 0))
    assert rid not in got


def test_explained_motion_tolerates_re_rasterisation():
    # A shape that turns as it moves lands a cell off its predicted
    # centroid and a cell different in size; that is the same thing.
    t = entities.RegionTracker()
    rid = next(iter(t.update([_blob(0, 0)])))
    got = t.update([_tilted(20, 0)], expected_offset=(20, 0))
    assert rid in got


def test_explained_motion_only_follows_what_was_on_screen():
    # A remembered ghost was not moved by the move we just made.
    t = entities.RegionTracker()
    rid = next(iter(t.update([_blob(0, 0)])))
    t.update([])                     # gone
    got = t.update([_tilted(20, 0)], expected_offset=(20, 0))
    assert rid not in got


def test_live_is_exactly_what_is_on_screen():
    t = entities.RegionTracker()
    a = next(iter(t.update([_blob(0, 0)])))
    t.update([_blob(30, 30, colour=2)])
    assert a not in t.live and a in t._tracked      # remembered, not live
    assert len(t.live) == 1


# ── beliefs and liveness ────────────────────────────────────────────────

def _frame(*regions):
    return {i: r for i, r in enumerate(regions)}


def test_an_entity_that_leaves_is_observed_once_as_vanished_then_left_alone():
    w = belief.WorldBelief()
    cells = frozenset({(0, 0), (1, 0)})
    w.update({1: (7, cells)}, "ACTION1", [])
    w.update({}, "ACTION2", list(cells))            # it went
    b = w._beliefs[1]
    assert b.live is False
    assert b.kinds["ACTION2"] == {belief.VANISHED: 1}
    n = b.observations
    for _ in range(5):
        w.update({}, "ACTION3", [])
    assert b.observations == n, "a thing that is not there cannot be observed"


def test_a_ghost_is_not_returned_by_role_queries():
    b = belief.Belief(1, 7)
    for _ in range(10):
        b.observe("ACTION5", belief.GREW)
    for act in ("ACTION1", "ACTION2"):
        for _ in range(10):
            b.observe(act, None)
    assert b.role == belief.AFFECT
    w = belief.WorldBelief(); w._beliefs[1] = b
    assert w.by_role(belief.AFFECT) == [b]
    b.live = False
    assert w.by_role(belief.AFFECT) == []
    assert w.by_role(belief.AFFECT, live_only=False) == [b]


def test_an_entity_that_returns_is_live_again():
    w = belief.WorldBelief()
    cells = frozenset({(0, 0), (1, 0)})
    w.update({1: (7, cells)}, "ACTION1", [])
    w.update({}, "ACTION1", list(cells))
    w.update({1: (7, cells)}, "ACTION1", list(cells))
    assert w._beliefs[1].live is True


def test_a_held_role_is_never_described_blank():
    # Win AFFECT cleanly, then let the winning action's lift sag into the
    # hysteresis band: the role is held, `drivers` is empty, and the
    # description must still name the action.
    b = belief.Belief(1, 7)
    for _ in range(10):
        b.observe("ACTION5", belief.GREW)
    for act in ("ACTION1", "ACTION2"):
        for _ in range(10):
            b.observe(act, None)
    assert b.role == belief.AFFECT
    # Dilute ACTION5 until its lift sits between (SELECTIVITY - HYSTERESIS)
    # and SELECTIVITY.
    from constants import BELIEF_HYSTERESIS, BELIEF_SELECTIVITY
    while b.selectivity[1] >= BELIEF_SELECTIVITY:
        b.observe("ACTION5", None)
    assert b.selectivity[1] >= BELIEF_SELECTIVITY - BELIEF_HYSTERESIS
    assert b.role == belief.AFFECT
    assert "ACTION5" in b.describe()


# ── identity across a reset ─────────────────────────────────────────────

def test_a_reset_returns_an_object_to_its_home_identity():
    # It starts at home, hops far and re-rasterises (so no shape pass can
    # carry it back), dies, and RESET puts it home again facing the way it
    # first did. Told about the reset, the tracker gives it its old id.
    t = entities.RegionTracker()
    rid = next(iter(t.update([_blob(0, 0)])))              # home
    t.update([_tilted(20, 0)], expected_offset=(20, 0))    # moved
    t.expect_home()
    got = t.update([_blob(0, 0)])
    assert rid in got and len(got) == 1


def test_without_being_told_the_same_frame_is_a_new_object():
    t = entities.RegionTracker()
    rid = next(iter(t.update([_blob(0, 0)])))
    t.update([_tilted(20, 0)], expected_offset=(20, 0))
    for _ in range(entities.SHAPE_REVIVE_WINDOW + 1):
        t.update([_tilted(20, 0)])
    got = t.update([_blob(0, 0)])
    assert rid not in got


def test_home_is_the_level_start_not_the_first_frame_ever():
    t = entities.RegionTracker()
    t.update([_blob(0, 0)])
    t.clear()                                               # new level
    rid = next(iter(t.update([_blob(30, 30)])))             # this level's home
    t.update([_tilted(30, 50)], expected_offset=(0, 20))
    t.expect_home()
    got = t.update([_blob(30, 30)])
    assert rid in got
