"""Unit tests for connecting belief to the router.

Two things are tested, and they are kept apart on purpose because they
are separable changes behind separate flags (see `constants.py`):

  * **the target** — `_belief_target` picks the strongest AFFECT entity
    and refuses the canvas, ourselves, CONTEXT, ENVIRONMENT and anything
    without a position. The refusals matter more than the pick: a router
    aimed at the stamina bar or the middle of the screen is worse than no
    router at all.
  * **the gate** — `_level_proven` is scoped to one layout and dies with
    it, while the cross-level counters `_weighted_choice` reads are left
    exactly as they were.

Also pins the `Belief.certainty` arity bug found while reading the layer:
it raised `TypeError` for every CONTEXT entity and nothing had ever
called it on one.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import belief  # noqa: E402
import my_agent  # noqa: E402
from control import MoveModel  # noqa: E402


def feed(b, action, changed, times=1, kind=belief.GREW):
    for _ in range(times):
        b.observe(action, kind if changed else None)


def affect(rid, colour, cells, hits=9, driver="ACTION5"):
    """An entity one action clearly acts on, positioned at `cells`."""
    b = belief.Belief(rid, colour)
    feed(b, driver, True, times=hits)
    feed(b, driver, False, times=10 - hits)
    for act in ("ACTION1", "ACTION2"):
        feed(b, act, False, times=10)
    b.last_cells = frozenset(cells)
    assert b.role == belief.AFFECT
    return b


def context(rid, colour, cells):
    """The stamina bar: busy under every action, selective under none."""
    b = belief.Belief(rid, colour)
    for act in ("ACTION1", "ACTION2", "ACTION3"):
        feed(b, act, True, times=7, kind=belief.SHRANK)
        feed(b, act, False, times=3)
    b.last_cells = frozenset(cells)
    assert b.role == belief.CONTEXT
    return b


def bare_agent(anchor=(10, 10), background=0, beliefs=()):
    """A MyAgent with only what `_belief_target` reads.

    The framework constructor needs a live environment, and the policy
    under test touches exactly three attributes, so build those and no
    more. `anchor` is where the controlled thing is on the board; None
    means no move map has formed and there is no displacement space.
    """
    agent = object.__new__(my_agent.MyAgent)
    agent.moves = MoveModel()
    agent.moves.anchor = anchor
    agent._background = background
    agent.belief = belief.WorldBelief()
    for b in beliefs:
        agent.belief._beliefs[b.region_id] = b
    return agent


# ── Belief.centroid ─────────────────────────────────────────────────────

def test_centroid_is_the_rounded_mean_of_last_cells():
    b = belief.Belief(1, 3)
    b.last_cells = frozenset({(0, 0), (0, 2), (2, 0), (2, 2)})
    assert b.centroid == (1, 1)


def test_centroid_is_none_with_no_cells():
    assert belief.Belief(1, 3).centroid is None


# ── the arity bug ───────────────────────────────────────────────────────

def test_certainty_of_a_context_entity_does_not_raise():
    b = context(1, 4, [(0, 0)])
    c = b.certainty
    assert 0.0 <= c <= 1.0
    # 70% responsiveness over 30 observations against a 35% bar is not a
    # close call, so the confidence should read as such.
    assert c > 0.99


# ── the target: what it picks ───────────────────────────────────────────

def test_picks_the_affect_entity_with_the_largest_lift():
    weak = affect(1, 7, [(40, 40)], hits=6)    # +60% over baseline
    strong = affect(2, 8, [(20, 20)], hits=10)  # +100%
    agent = bare_agent(beliefs=[weak, strong])
    assert agent._belief_target() == (20, 20)


def test_returns_none_when_nothing_has_earned_affect():
    thin = belief.Belief(1, 7)
    feed(thin, "ACTION5", True, times=2)
    thin.last_cells = frozenset({(20, 20)})
    assert thin.role == belief.UNASSIGNED
    assert bare_agent(beliefs=[thin])._belief_target() is None


# ── the target: what it refuses ─────────────────────────────────────────

def test_refuses_the_canvas():
    # The background is a tracked region too, usually the largest one; its
    # centroid is the middle of the screen and means nothing.
    canvas = affect(1, 0, [(30, 30)])
    assert bare_agent(background=0, beliefs=[canvas])._belief_target() is None


def test_refuses_context():
    # Travelling to the stamina bar is the clearest category error there is.
    bar = context(1, 4, [(60, 5)])
    assert bare_agent(beliefs=[bar])._belief_target() is None


def test_refuses_where_we_already_are():
    here = affect(1, 7, [(10, 10)])
    assert bare_agent(anchor=(10, 10), beliefs=[here])._belief_target() is None


def test_refuses_an_entity_with_no_position():
    gone = affect(1, 7, [])
    assert bare_agent(beliefs=[gone])._belief_target() is None


def test_refuses_to_target_anything_without_a_move_map():
    # No anchor means no controlled thing, so no displacement space to plan
    # in. This is the 9-of-25 case and must be a clean None, not a crash.
    target = affect(1, 7, [(20, 20)])
    assert bare_agent(anchor=None, beliefs=[target])._belief_target() is None


# ── the gate ────────────────────────────────────────────────────────────

def test_level_proven_dies_with_the_level_but_action_credit_does_not():
    agent = object.__new__(my_agent.MyAgent)
    # Only the state `_reset_level` touches.
    from attention import ClickTargeting, InterestMap
    from constraints import ObstacleMap
    import entities
    import navigation
    agent.obstacles = ObstacleMap()
    agent.interest = InterestMap()
    agent.regions = entities.RegionTracker()
    agent.belief = belief.WorldBelief()
    agent.moves = MoveModel()
    agent.route = navigation.Route()
    agent.clicks = ClickTargeting()
    agent._interaction_sites = {}
    agent._background = 0

    from arcengine import GameAction
    agent._action_level_ups = {GameAction.ACTION5: 1}
    agent._action_vanishes = {GameAction.ACTION3: 4}
    agent._level_proven = 5

    agent._reset_level()

    assert agent._level_proven == 0
    # The cross-level counters feed `_weighted_choice`, where persistence
    # is load-bearing; the gate change must not have touched them.
    assert agent._action_level_ups == {GameAction.ACTION5: 1}
    assert agent._action_vanishes == {GameAction.ACTION3: 4}
