"""The level-boundary diff: which residuals were falling into an advance
under a lever, typed by colour so the knowledge survives the level.

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
import supervisor  # noqa: E402


class Engine:
    def __init__(self, **records):
        self.records = {eval(k): v for k, v in records.items()}
        self.group_records = {}

    def record(self, key):
        return self.records.get(key) or self.group_records.get(key)


def rec(residual, **levers):
    r = relations.PairRecord(); r.residual = residual
    for act, (d, u, f) in levers.items():
        r.by_action[act] = {relations.DOWN: d, relations.UP: u, relations.FLAT: f}
    return r


COLOUR = {1: 9, 2: 3, 3: 4}.get


def test_a_falling_levered_residual_is_recorded_by_colour():
    e = Engine(**{'("distance", 1, 2)': rec(2, ACTION4=(8, 0, 2), ACTION3=(0, 8, 2))})
    s = supervisor.BoundarySupervisor()
    for v in (10, 8, 6, 4, 2):
        s.observe({("distance", 1, 2): v})
    found = s.on_advance(e, COLOUR, "ACTION4")
    assert found == [("distance", frozenset({3}), frozenset({9}))]
    assert s.mattered[("distance", frozenset({3}), frozenset({9}))] == 1
    assert s.won == {"ACTION4": 1}
    assert s.unexplained == 0


def test_a_drain_with_no_lever_is_not_recorded():
    e = Engine(**{'("containment", 1, 3)': rec(20, ACTION1=(9, 0, 1), ACTION2=(9, 0, 1), ACTION3=(9, 0, 1))})
    s = supervisor.BoundarySupervisor()
    for v in (30, 28, 26, 24, 22):
        s.observe({("containment", 1, 3): v})
    assert s.on_advance(e, COLOUR, "ACTION5") == []
    assert s.unexplained == 1                      # written down, not papered over


def test_a_residual_that_was_not_falling_is_not_recorded():
    e = Engine(**{'("distance", 1, 2)': rec(10, ACTION4=(8, 0, 2), ACTION3=(0, 8, 2))})
    s = supervisor.BoundarySupervisor()
    for v in (10, 10, 12, 10, 10):
        s.observe({("distance", 1, 2): v})
    assert s.on_advance(e, COLOUR, "ACTION4") == []


def test_the_proposer_prefers_a_type_that_has_mattered():
    # Two equally good levers; only one has a type that fell into an advance.
    e = Engine(**{
        '("distance", 1, 2)': rec(20, ACTION3=(8, 0, 2), ACTION4=(0, 8, 2)),   # colours {9},{3}
        '("distance", 1, 3)': rec(20, ACTION3=(8, 0, 2), ACTION4=(0, 8, 2)),   # colours {9},{4}
    })
    s = supervisor.BoundarySupervisor()
    s.mattered[("distance", frozenset({4}), frozenset({9}))] = 1
    typer = lambda key: supervisor.type_of(key, COLOUR)  # noqa: E731
    h = hypothesis.Proposer().propose(e, live={1, 2, 3}, legal={"ACTION3", "ACTION4"}, step=0,
                                      prior=s.prior, typer=typer)
    assert h.key == ("distance", 1, 3)


def test_the_proposer_prefers_a_lever_that_has_won():
    e = Engine(**{
        '("distance", 1, 2)': rec(20, ACTION3=(8, 0, 2), ACTION4=(0, 8, 2)),
        '("distance", 1, 3)': rec(20, ACTION5=(8, 0, 2), ACTION4=(0, 8, 2)),
    })
    s = supervisor.BoundarySupervisor(); s.won["ACTION5"] = 1
    h = hypothesis.Proposer().propose(e, live={1, 2, 3}, legal={"ACTION3", "ACTION4", "ACTION5"},
                                      step=0, won=s.won)
    assert h.action == "ACTION5"


def test_describe_reads_as_a_brief_section():
    s = supervisor.BoundarySupervisor()
    assert s.describe() == []
    s.advances = 2; s.unexplained = 1
    s.mattered[("part_size_diff", frozenset({0, 15}), frozenset({0, 4, 5, 15}))] = 1
    s.won["ACTION5"] = 2
    text = "\n".join(s.describe())
    assert "MATTERED" in text and "part_size_diff" in text and "ACTION5 x2" in text
    assert "1 with no expressible coordinate" in text
