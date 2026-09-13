"""Unit tests for the router in `agent/navigation.py`.

All coordinates here are *displacement space* — relative to wherever the
attempt began — which is the space the move and obstacle maps are keyed
in. Converting an absolute board pixel into it is the caller's job
(`MoveModel.to_relative`), and keeping that conversion out of here is
deliberate: navigation must not choose its own targets.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

from arcengine import GameAction  # noqa: E402

import navigation  # noqa: E402

UP, DOWN = GameAction.ACTION1, GameAction.ACTION2
LEFT, RIGHT = GameAction.ACTION3, GameAction.ACTION4

STRIDE_5 = {UP: (0, -5), DOWN: (0, 5), LEFT: (-5, 0), RIGHT: (5, 0)}


def nothing_blocked(position, action) -> bool:
    return False


def walk(start, path, moves=STRIDE_5):
    """Replay a path to see where it actually lands."""
    pos = start
    for action in path:
        dx, dy = moves[action]
        pos = (pos[0] + dx, pos[1] + dy)
    return pos


# ── plan ────────────────────────────────────────────────────────────────

def test_plan_reaches_an_exactly_reachable_target():
    path = navigation.plan((0, 0), (10, 10), STRIDE_5, nothing_blocked)
    assert path is not None
    assert walk((0, 0), path) == (10, 10)
    assert len(path) == 4, "should not wander: 2 across + 2 down"


def test_plan_routes_around_a_position_keyed_obstacle():
    """RIGHT blocked *at the origin only* must not disable RIGHT anywhere
    else — that is the whole point of keying obstacles by position."""
    def blocked(position, action):
        return position == (0, 0) and action is RIGHT

    path = navigation.plan((0, 0), (10, 0), STRIDE_5, blocked)
    assert path is not None
    assert path[0] is not RIGHT
    assert walk((0, 0), path) == (10, 0), "detour still arrives"


def test_plan_settles_for_the_closest_reachable_node():
    """An off-lattice target can never be hit exactly with a 5px stride.
    Best effort beats refusing to move."""
    path = navigation.plan((0, 0), (13, 13), STRIDE_5, nothing_blocked)
    assert path is not None
    landed = walk((0, 0), path)
    assert landed == (15, 15), "closest lattice point by Chebyshev distance"
    assert navigation.chebyshev(landed, (13, 13)) < navigation.chebyshev(
        (0, 0), (13, 13)
    ), "must actually get closer than standing still"


def test_plan_returns_none_without_a_move_map():
    assert navigation.plan((0, 0), (10, 10), {}, nothing_blocked) is None


def test_plan_returns_none_when_already_there():
    assert navigation.plan((5, 5), (5, 5), STRIDE_5, nothing_blocked) is None


def test_plan_returns_none_when_fully_walled_in():
    """No reachable node improves on standing still -> no plan, no crash."""
    assert navigation.plan(
        (0, 0), (10, 10), STRIDE_5, lambda position, action: True
    ) is None


# ── Route bookkeeping ───────────────────────────────────────────────────

def test_route_detects_drift_after_an_unexpected_outcome():
    route = navigation.Route()
    route.set([RIGHT, RIGHT], (99, 99))
    assert route.has_drifted((0, 0)) is False, "nothing taken yet"

    route.next_action((0, 0), STRIDE_5)          # expects to land at (5, 0)
    assert route.has_drifted((5, 0)) is False    # it did
    assert route.has_drifted((0, 0)) is True     # it didn't — obstacle


def test_route_survives_a_blocked_interleaved_action():
    """If some other action fired and was blocked, we are still where the
    plan left us, so the plan must remain valid rather than be discarded."""
    route = navigation.Route()
    route.set([RIGHT, RIGHT], (99, 99))
    route.next_action((0, 0), STRIDE_5)
    assert route.has_drifted((5, 0)) is False
    assert len(route) == 1


def test_route_clear_resets_everything():
    route = navigation.Route()
    route.set([RIGHT], (9, 9))
    route.next_action((0, 0), STRIDE_5)
    route.clear()
    assert not route and route.target is None and route.expected_position is None
