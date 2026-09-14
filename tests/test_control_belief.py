"""CONTROL read from determinism: what happens is fixed by which action.

The rate contrast finds "one button drives this". It cannot find a thing
driven by several buttons at equal rates — every d-pad — because no
button stands out. Measured on cd82: the controller read AFFECT, then
CONTEXT ("shrank whatever I press"). The signature of control is that the
EFFECT is a function of the ACTION: ACTION3 always left, ACTION4 always
right.

As everywhere, the refusals are pinned: equal rates with random effects
are not control, and one deterministic button is left to the rate path.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import belief  # noqa: E402

LEFT, RIGHT, UP, DOWN = (belief.MOVED, -1, 0), (belief.MOVED, 1, 0), (belief.MOVED, 0, -1), (belief.MOVED, 0, 1)


def dpad(b, per_action=8, misses=2):
    """Four buttons, each moving it one fixed way, each missing sometimes."""
    for act, eff in (("ACTION1", UP), ("ACTION2", DOWN), ("ACTION3", LEFT), ("ACTION4", RIGHT)):
        for _ in range(per_action):
            b.observe(act, belief.MOVED, eff)
        for _ in range(misses):
            b.observe(act, None)


def test_a_thing_every_button_moves_a_different_way_is_control():
    b = belief.Belief(1, 2)
    dpad(b)
    # No rate contrast at all: every action has the same hit rate.
    assert b.selectivity[1] < 0.01
    assert b.role == belief.CONTROL
    assert "ACTION3" in b.describe() and "-x" in b.describe()
    assert b.strength >= 0.8


def test_equal_rates_with_random_effects_are_not_control():
    # Same hit rates, but the direction is a coin flip: this thing changes
    # when I press things, but nothing about WHICH thing I press fixes
    # what happens. That is CONTEXT, not control.
    rng = random.Random(3)
    b = belief.Belief(1, 2)
    for act in ("ACTION1", "ACTION2", "ACTION3", "ACTION4"):
        for _ in range(8):
            b.observe(act, belief.MOVED, rng.choice([LEFT, RIGHT, UP, DOWN]))
        for _ in range(2):
            b.observe(act, None)
    assert b.controllers == []
    assert b.role != belief.CONTROL


def test_two_buttons_with_the_same_effect_are_not_a_dpad():
    # Two deterministic actions that do the identical thing carry no
    # information about which was pressed; determinism alone is not it.
    b = belief.Belief(1, 2)
    for act in ("ACTION1", "ACTION2"):
        for _ in range(8):
            b.observe(act, belief.GREW, (belief.GREW,))
        for _ in range(2):
            b.observe(act, None)
    for _ in range(10):
        b.observe("ACTION3", None)
    assert b.controllers == []


def test_one_deterministic_button_is_left_to_the_rate_path():
    b = belief.Belief(1, 2)
    for _ in range(10):
        b.observe("ACTION5", belief.GREW, (belief.GREW,))
    for act in ("ACTION1", "ACTION2"):
        for _ in range(10):
            b.observe(act, None)
    assert b.controllers == []
    assert b.role == belief.AFFECT           # exactly as before


def test_determinism_needs_evidence():
    b = belief.Belief(1, 2)
    for act, eff in (("ACTION3", LEFT), ("ACTION4", RIGHT)):
        for _ in range(2):                    # below the floor
            b.observe(act, belief.MOVED, eff)
    assert b.determinism("ACTION3") == (None, 0.0)
    assert b.controllers == []


# ── the effect vocabulary ───────────────────────────────────────────────

def _cells(x0, y0, w, h):
    return frozenset((x0 + i, y0 + j) for i in range(w) for j in range(h))


def _step(b, cells, hit=True):
    kind, effect = belief._kind(b, cells, hit, first_seen=False)
    b.last_cells, b.last_size = cells, len(cells)
    return kind, effect


def test_a_pure_translation_is_moved_with_a_direction():
    b = belief.Belief(1, 2)
    b.last_cells, b.last_size = _cells(0, 0, 3, 3), 9
    assert _step(b, _cells(5, 0, 3, 3)) == (belief.MOVED, (belief.MOVED, 1, 0))


def test_a_hop_that_re_rasterises_is_still_moved():
    # 9 cells become 10 as the thing lands at a new angle 11 cells away.
    b = belief.Belief(1, 2)
    b.last_cells, b.last_size = _cells(0, 0, 3, 3), 9
    kind, effect = _step(b, _cells(11, 0, 5, 2))
    assert kind == belief.MOVED and effect[1] == 1


def test_a_size_change_in_place_is_growth_not_motion():
    b = belief.Belief(1, 2)
    b.last_cells, b.last_size = _cells(0, 0, 3, 3), 9
    assert _step(b, _cells(0, 0, 3, 4))[0] == belief.GREW


def test_growth_that_extends_one_edge_is_growth_though_the_centroid_drifts():
    # The near edge stays put; only the far edge advances. Not motion.
    b = belief.Belief(1, 2)
    b.last_cells, b.last_size = _cells(0, 0, 3, 3), 9
    assert _step(b, _cells(0, 0, 6, 3))[0] == belief.GREW


def test_a_whole_extent_that_shifts_is_motion_even_if_the_size_changed():
    # Both edges advance: the thing went somewhere, and happens to have
    # re-rasterised larger on landing.
    b = belief.Belief(1, 2)
    b.last_cells, b.last_size = _cells(0, 0, 3, 3), 9
    kind, effect = _step(b, _cells(4, 0, 6, 3))
    assert kind == belief.MOVED and effect == (belief.MOVED, 1, 0)


def test_a_rotation_in_place_is_turned():
    b = belief.Belief(1, 2)
    b.last_cells, b.last_size = frozenset({(0, 1), (1, 1), (2, 1)}), 3
    assert _step(b, frozenset({(1, 0), (1, 1), (1, 2)})) == (belief.TURNED, (belief.TURNED,))
