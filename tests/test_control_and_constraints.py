"""Unit tests for `agent/control.py` and `agent/constraints.py`.

The recurring theme: each layer must **refuse to conclude** when the
evidence is ambiguous. A move map that learns m0r0's coin-flip action, or
a meter detector that calls dc22's fill-progress a budget, would be worse
than one that stays silent — it would feed confident nonsense to every
layer above. So the refusals are tested as carefully as the successes.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

from arcengine import GameAction  # noqa: E402

from constraints import MeterDetector, ObstacleMap  # noqa: E402
from control import MoveModel  # noqa: E402

UP, DOWN = GameAction.ACTION1, GameAction.ACTION2
LEFT, RIGHT = GameAction.ACTION3, GameAction.ACTION4


# ── MoveModel ───────────────────────────────────────────────────────────

def test_move_model_learns_a_consistent_action():
    m = MoveModel()
    for i in range(3):
        m.observe_translation(RIGHT, (5, 0), 4, (i * 5, 0))
    assert m.learned_moves == {RIGHT: (5, 0)}


def test_move_model_refuses_an_ambiguous_action():
    """m0r0's ACTION1 splits 15 one way and 13 the other. Returning
    nothing is the correct answer, not a gap."""
    m = MoveModel()
    for i in range(15):
        m.observe_translation(UP, (0, -5), 4, (0, 100 - i))
    for i in range(13):
        m.observe_translation(UP, (0, 5), 4, (0, i))
    assert UP not in m.learned_moves


def test_move_model_needs_enough_sightings():
    m = MoveModel()
    for i in range(2):  # below MIN_MOVE_OBSERVATIONS
        m.observe_translation(RIGHT, (5, 0), 4, (i * 5, 0))
    assert m.learned_moves == {}


def test_anchor_is_rederived_not_accumulated():
    """Absolute position comes from the observed pre-move anchor each
    time, so it cannot silently drift away from ground truth."""
    m = MoveModel()
    m.observe_translation(RIGHT, (5, 0), 4, (10, 10))
    assert m.anchor == (15, 10)
    # A later observation reports where the shape *actually* was.
    m.observe_translation(RIGHT, (5, 0), 4, (40, 10))
    assert m.anchor == (45, 10), "ground truth wins over the running tally"


def test_to_relative_bridges_pixel_and_displacement_space():
    m = MoveModel()
    m.observe_translation(RIGHT, (5, 0), 4, (10, 10))
    # Started at board (10,10) with displacement (0,0); now at (15,10)
    # with displacement (5,0). So origin is (10,10).
    assert m.origin_anchor() == (10, 10)
    assert m.to_relative((25, 10)) == (15, 0)


def test_to_relative_is_none_before_any_translation():
    assert MoveModel().to_relative((25, 10)) is None


def test_reset_position_keeps_game_knowledge():
    m = MoveModel()
    for i in range(3):
        m.observe_translation(RIGHT, (5, 0), 4, (i * 5, 0))
    m.reset_position()
    assert m.learned_moves == {RIGHT: (5, 0)}, "what an action does survives"
    assert m.displacement == (0, 0) and m.anchor is None, "position does not"
    assert m.controlled_size == 4, "shape size is a property of the game"


# ── ObstacleMap ─────────────────────────────────────────────────────────

def test_obstacle_is_position_keyed():
    o = ObstacleMap()
    o.observe((0, 0), RIGHT, occurred=False)
    assert o.is_blocked((0, 0), RIGHT) is True
    assert o.is_blocked((5, 0), RIGHT) is False, "a wall is somewhere, not everywhere"


def test_obstacle_ignores_successful_moves():
    o = ObstacleMap()
    o.observe((0, 0), RIGHT, occurred=True)
    assert o.is_blocked((0, 0), RIGHT) is False


def test_obstacle_clear_forgets_the_layout():
    o = ObstacleMap()
    o.observe((0, 0), RIGHT, occurred=False)
    o.clear()
    assert o.is_blocked((0, 0), RIGHT) is False


# ── MeterDetector ───────────────────────────────────────────────────────

def _sawtooth(meter: MeterDetector, colour: int, full: int, cycles: int = 2):
    """Deplete to zero and refill, the pattern a real budget makes."""
    for _ in range(cycles):
        for n in range(full, -1, -1):
            meter.update({colour: n, 0: 4096 - n})
        meter.update({colour: full, 0: 4096 - full})


def test_meter_detects_a_sawtooth():
    m = MeterDetector()
    _sawtooth(m, colour=7, full=40)
    assert m.meter_colour == 7


def test_meter_rejects_a_monotonic_drain():
    """dc22's fill-progress colour declines all run and never refills.
    Calling it a budget would have the agent conserving while winning."""
    m = MeterDetector()
    for n in range(400, -1, -1):
        m.update({7: n, 0: 4096 - n})
    assert m.meter_colour is None


def test_meter_rejects_something_too_small_to_be_a_bar():
    m = MeterDetector()
    _sawtooth(m, colour=7, full=3)  # below METER_MIN_SIZE
    assert m.meter_colour is None


def test_budget_fraction_tracks_depletion():
    m = MeterDetector()
    _sawtooth(m, colour=7, full=40)
    assert m.budget_fraction == 1.0
    m.update({7: 20, 0: 4076})
    assert 0.4 < m.budget_fraction < 0.6


def test_budget_fraction_is_none_without_a_meter():
    assert MeterDetector().budget_fraction is None
