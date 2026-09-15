"""The enumerating proposer and the verification loop.

A hypothesis is a bet that a residual some action has been seen to drive
is worth driving to 0. What is pinned here is how it dies: held at 0,
falsified when it rises twice or stalls past patience, expired at budget —
and that the enumerator refuses pairs with no lever, illegal levers, click
levers, undecidable residuals and cooled-down keys.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import hypothesis  # noqa: E402
import relations  # noqa: E402
from constants import HYPOTHESIS_BUDGET, HYPOTHESIS_PATIENCE  # noqa: E402


def rec(residual, **levers):
    """A PairRecord with a residual and per-action DOWN/UP/FLAT tallies."""
    r = relations.PairRecord(); r.residual = residual
    for act, (d, u, f) in levers.items():
        r.by_action[act] = {relations.DOWN: d, relations.UP: u, relations.FLAT: f}
    return r


class Engine:
    def __init__(self, **records):
        self.records = {eval(k): v for k, v in records.items()}


LEGAL = {"ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6"}


# ── the enumerator ──────────────────────────────────────────────────────

def test_picks_the_clearest_lever():
    e = Engine(**{
        '("distance", 1, 2)': rec(20, ACTION3=(8, 0, 2), ACTION4=(0, 8, 2), ACTION1=(1, 1, 8)),
        '("distance", 1, 3)': rec(30, ACTION3=(5, 0, 5), ACTION4=(2, 2, 6), ACTION1=(1, 1, 8)),
    })
    h = hypothesis.Proposer().propose(e, live={1, 2, 3}, legal=LEGAL, step=0)
    assert h.key == ("distance", 1, 2) and h.action == "ACTION3" and h.start == 20


def test_refuses_pairs_that_move_under_every_action_alike():
    e = Engine(**{'("containment", 1, 2)': rec(30, ACTION1=(9, 0, 1), ACTION2=(9, 0, 1), ACTION3=(9, 0, 1))})
    assert hypothesis.Proposer().propose(e, live={1, 2}, legal=LEGAL, step=0) is None


def test_refuses_illegal_levers_click_levers_and_ghost_pairs():
    e = Engine(**{
        '("distance", 1, 2)': rec(20, ACTION7=(8, 0, 2), ACTION1=(0, 8, 2)),   # lever not legal
        '("distance", 1, 3)': rec(20, ACTION6=(8, 0, 2), ACTION1=(0, 8, 2)),   # click lever
        '("distance", 1, 4)': rec(20, ACTION3=(8, 0, 2), ACTION1=(0, 8, 2)),   # #4 not live
    })
    assert hypothesis.Proposer().propose(e, live={1, 2, 3}, legal=LEGAL, step=0) is None


def test_close_logs_which_source_the_closed_bet_came_from():
    # Second review, 2026-09-14, bottleneck #4 ("exploration policy"): the
    # unmet/spent breakdown needs to be splittable by source, which
    # `closed_by_source` (status counts only) cannot do -- the log itself
    # has to carry it.
    p = hypothesis.Proposer()
    h = make(10); h.source = "llm"
    h.status = hypothesis.FALSIFIED
    p.close(h, step=1)
    assert p.log[-1][-1] == "llm"
    assert p.log[-1][:9] == (h.key, h.action, h.start, h.current, h.status, h.spent, h.unmet,
                             h.precondition, h.exclusive)


def test_a_cooled_key_is_not_proposed_again_until_the_cooldown_ends():
    e = Engine(**{'("distance", 1, 2)': rec(20, ACTION3=(8, 0, 2), ACTION4=(0, 8, 2))})
    p = hypothesis.Proposer()
    h = p.propose(e, live={1, 2}, legal=LEGAL, step=0)
    h.status = hypothesis.FALSIFIED; p.close(h, step=10)
    assert p.propose(e, live={1, 2}, legal=LEGAL, step=11) is None
    assert p.propose(e, live={1, 2}, legal=LEGAL, step=10 + 1000) is not None


# ── verification ────────────────────────────────────────────────────────

def make(start=10):
    return hypothesis.Hypothesis(key=("distance", 1, 2), action="ACTION3", lift=0.6, start=start)


def test_held_when_the_residual_reaches_zero():
    h = make(3)
    assert h.observe(2) == hypothesis.LIVE
    assert h.observe(0) == hypothesis.HELD


def test_falsified_when_it_rises_twice_running():
    h = make(10)
    assert h.observe(11) == hypothesis.LIVE
    assert h.observe(12) == hypothesis.FALSIFIED


def test_falsified_when_it_stalls_for_patience_steps():
    # PATIENCE presses of the lever with no fall is the falsification.
    h = make(10)
    for _ in range(HYPOTHESIS_PATIENCE - 1):
        assert h.observe(10) == hypothesis.LIVE
    assert h.observe(10) == hypothesis.FALSIFIED


def test_expires_at_budget_while_still_falling():
    h = make(100)
    v = 100
    for _ in range(HYPOTHESIS_BUDGET - 1):
        v -= 1; assert h.observe(v) == hypothesis.LIVE
    assert h.observe(v - 1) == hypothesis.EXPIRED


def test_an_undecidable_step_costs_budget_but_is_not_evidence():
    h = make(10)
    h.observe(None); h.observe(None)
    assert h.status == hypothesis.LIVE and h.spent == 2
    assert h.observe(9) == hypothesis.LIVE


# ── the exploration floor ───────────────────────────────────────────────

def _agent_with(tries, won=None, legal=("ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6")):
    import my_agent, supervisor
    from arcengine import GameAction
    a = object.__new__(my_agent.MyAgent)
    a._level_tries = dict(tries)
    a.supervisor = supervisor.BoundarySupervisor(); a.supervisor.won = dict(won or {})
    a._last_click = None; a._last_action = None
    return a, [GameAction[n] for n in legal]


def test_an_untried_action_is_not_probed_on_its_own():
    # Measured and reverted: a blanket floor did not recover cd82 and cost
    # the navigational games. Only winning moves are probed.
    a, cands = _agent_with({"ACTION1": 9, "ACTION2": 9, "ACTION3": 9, "ACTION4": 9, "ACTION5": 0})
    assert a._probe_action(cands) is None


def test_a_winning_move_stops_being_probed_once_tried_enough():
    from constants import HYPOTHESIS_PROBE_TRIES
    a, cands = _agent_with({"ACTION5": HYPOTHESIS_PROBE_TRIES}, won={"ACTION5": 1})
    assert a._probe_action(cands) is None


def test_a_click_is_never_a_bare_probe():
    a, cands = _agent_with({"ACTION1": 9}, legal=("ACTION1", "ACTION6"))
    assert a._probe_action(cands) is None


def test_a_winning_move_from_an_earlier_level_is_probed_first():
    a, cands = _agent_with({}, won={"ACTION5": 1})
    assert a._probe_action(cands).name == "ACTION5"


# ── preconditions and the outcome taxonomy (H001) ───────────────────────

def test_an_unmet_precondition_costs_budget_but_is_not_evidence():
    h = make(10); h.precondition = ("adjacent:-x", 2)
    for _ in range(HYPOTHESIS_PATIENCE + 1):
        assert h.observe(10, met=False) == hypothesis.LIVE       # would have falsified if counted
    assert h.unmet == HYPOTHESIS_PATIENCE + 1
    assert h.observe(9, met=True) == hypothesis.LIVE
    assert h.outcomes[-1] == hypothesis.SUPPORTED


def test_expiry_spent_on_the_precondition_cools_briefly():
    from constants import HYPOTHESIS_COOLDOWN
    p = hypothesis.Proposer()
    h = make(10); h.precondition = ("adjacent:-x", 2)
    for _ in range(HYPOTHESIS_BUDGET):
        h.observe(10, met=False)
    assert h.status == hypothesis.EXPIRED
    p.close(h, step=100)
    assert p._cooldown[h.key] == 100 + HYPOTHESIS_COOLDOWN // 4


def test_the_proposer_bets_on_a_conditional_lever_with_its_precondition():
    rec = relations.PairRecord(); rec.residual = 30
    def tally(cond, act, d, u, f):
        rec.by_action_given.setdefault(cond, {})[act] = {relations.DOWN: d, relations.UP: u, relations.FLAT: f}
        t = rec.by_action.setdefault(act, {relations.DOWN: 0, relations.UP: 0, relations.FLAT: 0})
        t[relations.DOWN] += d; t[relations.UP] += u; t[relations.FLAT] += f
    tally("apart:-y", "ACTION5", 0, 0, 30); tally("adjacent:-y", "ACTION5", 6, 0, 2)
    for a in ("ACTION1", "ACTION2"):
        tally("apart:-y", a, 0, 0, 10); tally("adjacent:-y", a, 0, 0, 4)
    e = Engine(); e.records[("part_size_diff", 1, 2)] = rec
    h = hypothesis.Proposer().propose(e, live={1, 2}, legal=LEGAL, step=0, control={1})
    assert h is not None and h.action == "ACTION5"
    assert h.precondition == ("adjacent:-y", 2)
    assert "when adjacent on side -y of #2" in h.describe()
