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


# ── conjunctive preconditions (H005) ─────────────────────────────────────
# Every proposer above still builds one bare (cond, member) pair -- neither
# changed. `conditions_of`/`describe_conditions` are the normalization that
# lets a hand-built hypothesis (research/hypotheses/H005) carry SEVERAL
# such pairs, conjunctively, without every existing reader needing to know
# which shape it's looking at.

def test_conditions_of_normalizes_every_precondition_shape():
    assert hypothesis.conditions_of(None) == ()
    assert hypothesis.conditions_of(()) == ()
    assert hypothesis.conditions_of(("adjacent:-x", 2)) == (("adjacent:-x", 2),)
    multi = (("adjacent:-x", 2), ("adjacent:+y", 5))
    assert hypothesis.conditions_of(multi) == multi


def test_describe_conditions_joins_several_with_and():
    multi = (("adjacent:-x", 2), ("adjacent:+y", 5))
    assert (hypothesis.describe_conditions(multi)
            == " when adjacent on side -x of #2 and adjacent on side +y of #5")
    assert hypothesis.describe_conditions(multi, exclusive=True).startswith(" only when")
    assert hypothesis.describe_conditions(None) == ""
    assert hypothesis.describe_conditions(()) == ""


def test_describe_carries_a_conjunctive_precondition():
    h = make(10)
    h.precondition = (("adjacent:-x", 2), ("adjacent:+y", 5))
    assert "adjacent on side -x of #2 and adjacent on side +y of #5" in h.describe()


def test_a_conjunctive_precondition_requires_every_condition_met():
    """`_precondition_met` (agent/my_agent.py) ANDs over `conditions_of` --
    the mechanism this session's H005 doc calls the smallest extension
    that carries a two-factor rule end to end. #2 is adjacent to the
    controlled thing throughout; #5 starts far away, so the conjunction
    must read False even though one of its two conditions already holds,
    then True once both do."""
    import my_agent
    from types import SimpleNamespace
    a = object.__new__(my_agent.MyAgent)
    a.regions = SimpleNamespace(live={1, 2, 5}, _tracked={
        1: (3, [(0, 0)]),       # the controlled thing
        2: (1, [(1, 0)]),       # adjacent throughout
        5: (2, [(100, 100)]),   # far, moved adjacent below
    })
    a._control_ids = lambda: {1}
    h = make(10)
    h.precondition = (("adjacent", 2), ("adjacent", 5))
    assert a._condition_met("adjacent", 2) is True
    assert a._condition_met("adjacent", 5) is False
    assert a._precondition_met(h) is False
    a.regions._tracked[5] = (2, [(0, 1)])
    assert a._condition_met("adjacent", 5) is True
    assert a._precondition_met(h) is True


# ── the state condition kind (H007) ──────────────────────────────────────

def test_describe_renders_a_state_condition():
    h = make(10)
    h.precondition = (("adjacent:-x", 2), ("state:a1b2c3d4", 7))
    assert "adjacent on side -x of #2 and #7 in state a1b2c3d4" in h.describe()


def test_a_state_condition_reads_the_members_current_appearance():
    """`state:<token>` is met exactly when the member's colour+shape token
    (relations.state_key) equals the one the hypothesis names — position
    does not matter, shape does. H005 Stage 3 found adjacency the wrong
    proxy for cd82's "which swatch is selected"; this is the condition
    kind that can carry it."""
    import my_agent, relations
    from types import SimpleNamespace
    marker_left = [(0, 0), (1, 0), (2, 0), (0, 1)]
    marker_right = [(0, 0), (1, 0), (2, 0), (2, 1)]
    a = object.__new__(my_agent.MyAgent)
    a.regions = SimpleNamespace(live={1, 7}, _tracked={1: (3, [(0, 0)]), 7: (5, marker_left)})
    a._control_ids = lambda: {1}
    want = relations.state_key(5, marker_left)
    assert a._condition_met(f"state:{want}", 7) is True
    a.regions._tracked[7] = (5, [(x + 10, y + 10) for x, y in marker_left])   # moved, same shape
    assert a._condition_met(f"state:{want}", 7) is True
    a.regions._tracked[7] = (5, marker_right)                                 # changed in place
    assert a._condition_met(f"state:{want}", 7) is False
    a.regions.live = {1}                                                       # off screen
    assert a._condition_met(f"state:{want}", 7) is False


def test_an_unmet_state_condition_is_satisfied_by_acting_not_walking():
    """The router for a state condition is the action that has put that
    entity into the named state before, with its click coordinates when
    it was a click. Keyed by the RESULTING state, not "what last changed
    it": the last change may have taken the thing away from the state the
    bet needs. Nothing known for that state, or the action illegal now,
    and the bet proceeds unmet."""
    import my_agent
    from arcengine import GameAction
    a = object.__new__(my_agent.MyAgent)
    a._setters = {}
    a._last_click = None
    legal = [GameAction.ACTION1, GameAction.ACTION5, GameAction.ACTION6]
    assert a._route_by_acting(7, "k0", legal) == (None, "")           # nothing has set #7
    a._setters[7] = {"k1": ("ACTION5", None)}
    assert a._route_by_acting(7, "k0", legal) == (None, "")           # k1 is known, k0 is not
    step, note = a._route_by_acting(7, "k1", legal)
    assert step is GameAction.ACTION5 and "#7" in note
    a._setters[7]["k0"] = ("ACTION6", (43, 4))
    a._setters[7]["k1"] = ("ACTION6", (37, 4))
    step, _ = a._route_by_acting(7, "k0", legal)
    assert step is GameAction.ACTION6
    assert step.action_data.x == 43 and step.action_data.y == 4
    assert a._last_click == (43, 4)
    a._setters[7]["k0"] = ("ACTION6", None)                             # a click with no coordinate
    assert a._route_by_acting(7, "k0", legal) == (None, "")
    a._setters[7]["k0"] = ("ACTION3", None)                             # not legal now
    assert a._route_by_acting(7, "k0", legal) == (None, "")
