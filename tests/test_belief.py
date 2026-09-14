"""Unit tests for the belief layer: what each entity is to the agent.

The layer exists because the agent held a pile of correlations and never
reduced them. cd82's stamina bar changes on 52-66% of steps *whatever* is
pressed, and that common signal sat in every action's profile, drowning the
one effect that is action-specific. Roles are read from the CONTRAST
between actions, so the common part cancels.

As everywhere here, the refusals are tested as carefully as the
conclusions: an entity with thin evidence must stay UNASSIGNED, and a
recolour must not be described as movement.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import belief  # noqa: E402


def feed(b, action, changed, displaced=False, times=1, kind=None):
    """`changed=False` means nothing happened; otherwise a kind is recorded.

    Defaults to GREW so a test that only cares about "did it change" gets a
    non-motion kind, which is the AFFECT side of the split.
    """
    for _ in range(times):
        b.observe(action, (kind or (belief.MOVED if displaced else belief.GREW))
                  if changed else None)


# ── role assignment ─────────────────────────────────────────────────────

def test_an_entity_that_changes_whatever_i_press_is_context():
    # The stamina bar. High responsiveness, no action stands out.
    b = belief.Belief(1, 4)
    for act in ("ACTION1", "ACTION2", "ACTION3"):
        feed(b, act, True, times=7)
        feed(b, act, False, times=3)
    assert b.role == belief.CONTEXT
    assert "whatever I press" in b.describe()


def test_an_entity_driven_by_one_action_is_not_context():
    # Same total activity as above, but concentrated. Contrast is what
    # separates "this is mine to act through" from "this is the weather".
    b = belief.Belief(2, 15)
    feed(b, "ACTION5", True, times=9); feed(b, "ACTION5", False, times=1)
    for act in ("ACTION1", "ACTION2"):
        feed(b, act, False, times=10)
    assert b.role == belief.AFFECT
    assert b.selectivity[0] == "ACTION5"


def test_motion_is_what_separates_control_from_affect():
    # Identical evidence except for HOW the entity changed. Control is
    # motion under my hand; anything else I merely act upon.
    def make(kind):
        b = belief.Belief(3, 7)
        feed(b, "ACTION1", True, kind=kind, times=9)
        feed(b, "ACTION1", False, times=1)
        feed(b, "ACTION2", False, times=10)
        return b
    assert make(belief.GREW).role == belief.AFFECT
    assert make(belief.MOVED).role == belief.CONTROL
    assert make(belief.TURNED).role == belief.CONTROL, "turning is motion too"


def test_the_description_says_HOW_not_just_that():
    # "ACTION5 affects #12" and "ACTION5 grows #12" are different amounts
    # of understanding, and the second costs nothing extra to record.
    b = belief.Belief(3, 7)
    feed(b, "ACTION1", True, kind=belief.SHRANK, times=9)
    feed(b, "ACTION1", False, times=1)
    feed(b, "ACTION2", False, times=10)
    assert "shrank" in b.describe()
    assert b.kind_for("ACTION1") == belief.SHRANK


def test_an_entity_that_never_changes_is_environment():
    b = belief.Belief(4, 3)
    for act in ("ACTION1", "ACTION2"):
        feed(b, act, False, times=10)
    assert b.role == belief.ENVIRONMENT


# ── the refusals ────────────────────────────────────────────────────────

def test_thin_evidence_stays_unassigned():
    # UNASSIGNED is a first-class outcome, exactly as `learned_moves`
    # refuses m0r0's 15/13 split rather than picking a winner.
    b = belief.Belief(5, 9)
    feed(b, "ACTION1", True, times=2)
    feed(b, "ACTION2", True, times=2)
    assert b.role == belief.UNASSIGNED


def test_one_action_alone_is_not_a_contrast():
    # A rate with nothing to compare against says nothing. Plenty of
    # observations, but all of one action.
    b = belief.Belief(6, 9)
    feed(b, "ACTION1", True, times=40)
    assert b.role == belief.UNASSIGNED


def test_a_role_changes_when_the_evidence_does():
    # Roles are mutable: recomputed from current evidence, never stamped.
    b = belief.Belief(7, 5)
    feed(b, "ACTION1", True, displaced=True, times=9)
    feed(b, "ACTION1", False, times=1)
    feed(b, "ACTION2", False, times=10)
    assert b.role == belief.CONTROL
    # It stops responding to ACTION1; the evidence now looks uniform.
    feed(b, "ACTION1", False, times=60)
    feed(b, "ACTION2", False, times=60)
    assert b.role != belief.CONTROL


# ── WorldBelief ─────────────────────────────────────────────────────────

def _cells(*xy):
    return frozenset(xy)


def test_a_change_at_the_edge_counts_for_that_entity():
    # The bug that made the cd82 meter unreadable: a drained cell has just
    # STOPPED being the meter colour, so it is absent from the current
    # region and testing only against that missed it — the meter read 7%
    # responsive where it is really 77%.
    w = belief.WorldBelief()
    full = _cells((0, 0), (1, 0), (2, 0))
    w.update({1: (4, full)}, "ACTION1", [])
    shrunk = _cells((0, 0), (1, 0))
    w.update({1: (4, shrunk)}, "ACTION1", [(2, 0)])   # the cell that drained
    assert w._beliefs[1].changed.get("ACTION1") == 1


def test_appearing_is_not_moving():
    # Without a first-sighting guard an entity that appears counts as
    # displaced, and a recolour gets described as "I move this" — a claim
    # about the world, and the wrong one.
    w = belief.WorldBelief()
    w.update({1: (15, _cells((5, 5), (6, 5)))}, "ACTION5", [(5, 5), (6, 5)])
    assert w._beliefs[1].kind_for("ACTION5") == belief.APPEARED


def test_reset_steps_are_not_evidence():
    w = belief.WorldBelief()
    w.update({1: (4, _cells((0, 0)))}, "RESET", [(0, 0)])
    assert w._beliefs == {}


def test_clear_drops_every_belief():
    w = belief.WorldBelief()
    w.update({1: (4, _cells((0, 0)))}, "ACTION1", [(0, 0)])
    w.clear()
    assert w.summary() == []
