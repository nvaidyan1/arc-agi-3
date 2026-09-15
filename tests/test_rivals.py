"""Competing transition hypotheses (H004): a general rule and an exclusive
conditional rule about the same action, proposed together, pressed where
their forecasts differ, so that one step falsifies one of them.

Pinned: an exclusive bet treats a fall under its unmet precondition as a
strike and a hold as support; a non-exclusive one still files unmet steps
as no evidence; the enumerator builds the rival of either kind; the
selector prefers an action whose live bets diverge right now; closing a
rival records which of the pair died first.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import hypothesis  # noqa: E402
import proposer_llm as pl  # noqa: E402
import relations  # noqa: E402
from constants import HYPOTHESIS_PATIENCE  # noqa: E402

KEY = ("part_size_diff", 1, 2)
LEGAL = {"ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5"}


def general(start=30):
    return hypothesis.Hypothesis(key=KEY, action="ACTION5", lift=0.3, start=start)


def specific(start=30, exclusive=True):
    return hypothesis.Hypothesis(key=KEY, action="ACTION5", lift=0.3, start=start,
                                 precondition=("adjacent:-x", 2), exclusive=exclusive)


def rec(residual, unconditional=None, given=None):
    """A PairRecord with an unconditional tally and per-condition tallies."""
    r = relations.PairRecord(); r.residual = residual
    if unconditional:
        d, u, f = unconditional
        r.by_action["ACTION5"] = {relations.DOWN: d, relations.UP: u, relations.FLAT: f}
        r.by_action["ACTION1"] = {relations.DOWN: 0, relations.UP: 0, relations.FLAT: 8}
    for cond, (d, u, f) in (given or {}).items():
        r.by_action_given[cond] = {
            "ACTION5": {relations.DOWN: d, relations.UP: u, relations.FLAT: f},
            "ACTION1": {relations.DOWN: 0, relations.UP: 0, relations.FLAT: 6}}
    return r


# ── the exclusive reading ───────────────────────────────────────────────

def test_an_exclusive_bet_is_struck_by_a_fall_it_said_could_not_happen():
    s = specific(30)
    assert s.observe(25, met=False) == hypothesis.LIVE
    assert s.outcomes[-1] == hypothesis.AGAINST and s.strikes == 1
    assert s.observe(20, met=False) == hypothesis.FALSIFIED


def test_an_exclusive_bet_is_supported_when_the_residual_holds_without_its_precondition():
    s = specific(30)
    s.observe(30, met=False); s.observe(31, met=False)
    assert s.outcomes == [hypothesis.SUPPORTED, hypothesis.SUPPORTED] and s.status == hypothesis.LIVE


def test_unmet_holds_do_not_count_toward_patience_for_an_exclusive_bet():
    # PATIENCE unmet steps with no fall say nothing about the positive claim.
    s = specific(30)
    for _ in range(HYPOTHESIS_PATIENCE + 1):
        assert s.observe(30, met=False) == hypothesis.LIVE
    # Met steps do: the same number with no fall falsifies as before.
    s = specific(30)
    for _ in range(HYPOTHESIS_PATIENCE - 1):
        assert s.observe(30, met=True) == hypothesis.LIVE
    assert s.observe(30, met=True) == hypothesis.FALSIFIED


def test_a_non_exclusive_bet_still_files_unmet_steps_as_no_evidence():
    s = specific(30, exclusive=False)
    assert s.observe(25, met=False) == hypothesis.LIVE
    assert s.outcomes == [hypothesis.UNMET] and s.strikes == 0


def test_forecasts_differ_only_when_the_precondition_is_unmet():
    g, s, weak = general(), specific(), specific(exclusive=False)
    assert g.forecast(met=True) == g.forecast(met=False) == relations.DOWN
    assert s.forecast(met=True) == relations.DOWN and s.forecast(met=False) == hypothesis.NOT_DOWN
    assert weak.forecast(met=False) is None


# ── rivals from the enumerator ──────────────────────────────────────────

def test_a_conditional_bet_gets_a_general_rival_and_becomes_exclusive():
    p = hypothesis.Proposer()
    s = specific()
    g = p.rival(s, rec(30, unconditional=(2, 2, 6), given={"adjacent:-x": (4, 0, 0)}), control={9})
    assert g is not None and g.precondition is None and g.action == "ACTION5" and g.key == KEY
    assert s.exclusive and s.rival is g and g.rival is s
    assert p.rivals == 1


def test_an_unconditional_bet_gets_an_exclusive_rival_where_one_condition_stands_out():
    p = hypothesis.Proposer()
    g = general()
    r = rec(30, unconditional=(6, 2, 8), given={"adjacent:-x": (5, 0, 1), "apart:+y": (1, 2, 7)})
    s = p.rival(g, r, control={1})
    assert s is not None and s.exclusive and s.precondition == ("adjacent:-x", 2)
    assert g.rival is s


def test_no_rival_when_no_condition_differs_from_the_whole():
    p = hypothesis.Proposer()
    g = general()
    r = rec(30, unconditional=(6, 2, 8), given={"adjacent:-x": (3, 1, 4), "apart:+y": (3, 1, 4)})
    assert p.rival(g, r, control={1}) is None and g.rival is None and p.rivals == 0


def test_closing_a_rival_records_which_died_first():
    p = hypothesis.Proposer()
    s = specific(); g = p.rival(s, rec(30, unconditional=(2, 2, 6), given={"adjacent:-x": (4, 0, 0)}), control={9})
    g.status = hypothesis.FALSIFIED
    p.close(g, step=5)
    assert p.rival_outcomes == {"general_died_first": 1}
    s.status = hypothesis.FALSIFIED
    p.close(s, step=9)
    assert p.rival_outcomes == {"general_died_first": 1}      # the second death is not "first"


# ── the selector ────────────────────────────────────────────────────────

def test_selector_prefers_the_action_whose_bets_diverge_now():
    g, s = general(), specific()
    g.rival, s.rival = s, g
    lone = hypothesis.Hypothesis(key=("distance", 3, 4), action="ACTION1", lift=0.9, start=9, confidence=0.9)
    pool = [lone, g, s]
    # Precondition unmet: G says down, S says not down — one press decides.
    chosen = pl.select_experiment(pool, LEGAL, met=lambda h: False)
    assert chosen is g
    assert pl.diverges(pool, "ACTION5", met=lambda h: False)
    # Precondition met: both say down — no divergence, and the pair still
    # outranks the lone bet because one press tests two bets (as before).
    chosen = pl.select_experiment(pool, LEGAL, met=lambda h: True)
    assert chosen in (g, s)
    assert not pl.diverges(pool, "ACTION5", met=lambda h: True)


def test_the_bet_acted_under_is_the_ready_one_so_the_press_happens_now():
    g, s = general(), specific()
    g.rival, s.rival = s, g
    assert pl.select_experiment([s, g], LEGAL, met=lambda h: False) is g
