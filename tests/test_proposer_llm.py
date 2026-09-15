"""The language-model proposer's interface, without a language model.

Everything the model returns is checked against what the agent knows; what
survives becomes an ordinary Hypothesis. The client is scripted here — the
reviewer's staging: prove the machinery first, attach the model second.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import hypothesis  # noqa: E402
import proposer_llm as pl  # noqa: E402
import relations  # noqa: E402


class Engine:
    def __init__(self, **records):
        self.records = {eval(k): v for k, v in records.items()}
        self.group_records = {}

    def record(self, key):
        return self.records.get(key) or self.group_records.get(key)


def rec(residual):
    r = relations.PairRecord(); r.residual = residual; return r


ENGINE = Engine(**{'("distance", 1, 2)': rec(12), '("part_size_diff", 3, 4)': rec(30),
                   '("distance", 1, 5)': rec(0)})
LIVE = {1, 2, 3, 4, 5}
LEGAL = {"ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6"}


def reply(*items):
    return json.dumps({"hypotheses": list(items)})


GOOD = {"relation": "part_size_diff", "a": 3, "b": 4, "action": "ACTION5",
        "precondition": {"adjacency": "adjacent", "side": "-x", "member": 4},
        "predicted": "down", "falsifier": "part_size_diff(3,4) does not fall after 3 adjacent presses",
        "confidence": 0.7, "why": "painting changes proportions"}


# ── parsing and validation ──────────────────────────────────────────────

def test_a_well_formed_hypothesis_becomes_a_hypothesis():
    hyps, rejects = pl.parse_hypotheses(reply(GOOD), ENGINE, LIVE, LEGAL, control={1})
    assert not rejects and len(hyps) == 1
    h = hyps[0]
    assert h.key == ("part_size_diff", 3, 4) and h.action == "ACTION5"
    assert h.precondition == ("adjacent:-x", 4)
    assert h.source == "llm" and h.confidence == 0.7 and h.start == 30
    assert "adjacent presses" in h.falsifier


def test_rejections_name_their_reason():
    bad = [
        dict(GOOD, relation="wins_level"),                       # unknown relation
        dict(GOOD, a=99),                                        # not on screen
        dict(GOOD, action="ACTION6"),                            # bare click
        dict(GOOD, action="ACTION7"),                            # not legal now
        dict(GOOD, falsifier=""),                                # no falsifier
        dict(GOOD, predicted="rotates"),                         # not checkable
        dict(GOOD, precondition={"adjacency": "near", "member": 4}),
        dict(GOOD, precondition={"adjacency": "adjacent", "member": 1}),   # member is the control thing
        {"relation": "distance", "a": 1, "b": 5, "action": "ACTION1", "predicted": "down",
         "falsifier": "does not fall in three", "confidence": 0.5},        # already holds
    ]
    hyps, rejects = pl.parse_hypotheses(reply(*bad), ENGINE, LIVE, LEGAL, control={1})
    assert hyps == []
    reasons = [r.reason for r in rejects]
    assert reasons == ["unknown relation", "entity not on screen", "action not legal (or a bare click)",
                       "action not legal (or a bare click)", "no falsifier",
                       "prediction not checkable (down|zero)", "precondition vocabulary",
                       "precondition member not on screen or is the controlled thing", "already holds"]


def test_json_inside_prose_and_a_bare_list_both_parse():
    prose = "Sure! Here you go:\n" + reply(GOOD) + "\nHope that helps."
    assert len(pl.parse_hypotheses(prose, ENGINE, LIVE, LEGAL)[0]) == 1
    assert len(pl.parse_hypotheses(json.dumps([GOOD]), ENGINE, LIVE, LEGAL)[0]) == 1
    hyps, rejects = pl.parse_hypotheses("no json here", ENGINE, LIVE, LEGAL)
    assert hyps == [] and rejects[0].reason == "unparseable"


def test_entity_ids_written_the_way_the_brief_displays_them_still_parse():
    # Measured live (E-H002-1, 2026-09-14): a 4B model echoes the brief's
    # own "#5" notation back rather than the bare int the schema asks for
    # -- the single largest rejection category, not hallucinated ids.
    for a in ("#3", "3", 3):
        hyps, rejects = pl.parse_hypotheses(reply(dict(GOOD, a=a)), ENGINE, LIVE, LEGAL, control={1})
        assert not rejects and hyps[0].key == ("part_size_diff", 3, 4)
    # A group id list in the same mixed notation.
    e = Engine(); e.group_records[("part_size_diff", (3, 5), 4)] = rec(30)
    hyps, rejects = pl.parse_hypotheses(reply(dict(GOOD, a=["#3", "5"])), e, {1, 3, 4, 5}, LEGAL, control={1})
    assert not rejects and hyps[0].key == ("part_size_diff", (3, 5), 4)


def test_a_non_numeric_or_missing_id_is_still_rejected():
    for bad_a in ("#nine", "abc", None):
        hyps, rejects = pl.parse_hypotheses(reply(dict(GOOD, a=bad_a)), ENGINE, LIVE, LEGAL, control={1})
        assert hyps == [] and rejects[0].reason == "entity not on screen"


def test_a_group_pair_is_addressed_by_id_lists():
    e = Engine(); e.group_records[("part_size_diff", (5, 6), (10, 12))] = rec(30)
    item = dict(GOOD, a=[5, 6], b=[12, 10], precondition=None)
    hyps, rejects = pl.parse_hypotheses(reply(item), e, {5, 6, 10, 12}, LEGAL)
    assert not rejects and hyps[0].key == ("part_size_diff", (5, 6), (10, 12))


# ── the proposer and its call policy ────────────────────────────────────

def test_scripted_client_end_to_end_with_stats():
    client = pl.ScriptedClient([reply(GOOD, dict(GOOD, relation="nope"))])
    p = pl.LLMProposer(client, max_calls_per_level=2, min_step=0)
    hyps = p.propose("BRIEF", ENGINE, LIVE, LEGAL, control={1}, level_step=5)
    assert len(hyps) == 1
    assert p.stats["calls"] == 1 and p.stats["returned"] == 2 and p.stats["valid"] == 1
    assert p.stats["rejects"] == {"unknown relation": 1}
    assert "=== BRIEF ===" in client.prompts[0] and "ACTION5" in client.prompts[0]


def test_call_policy_first_at_min_step_then_only_after_falsifications():
    p = pl.LLMProposer(pl.ScriptedClient(["{}"]), max_calls_per_level=3, min_step=20, after_falsified=4)
    assert not p.should_call(10, pool_empty=True)          # brief too thin yet
    assert p.should_call(20, pool_empty=False)             # first call of the level
    p.propose("b", ENGINE, LIVE, LEGAL, control=set(), level_step=20)
    assert not p.should_call(21, pool_empty=True)          # nothing falsified since
    p.falsified_since_call = 4
    assert not p.should_call(22, pool_empty=False)         # pool still has bets
    assert p.should_call(22, pool_empty=True)
    p.calls_this_level = 3
    assert not p.should_call(30, pool_empty=True)          # capped
    p.new_level()
    assert p.should_call(20, pool_empty=True)


# ── experiment selection ────────────────────────────────────────────────

def mk(key, action, conf, pre=None, source="enumerator", spent=0):
    h = hypothesis.Hypothesis(key=key, action=action, lift=conf, start=10, confidence=conf,
                              precondition=pre, source=source)
    h.history = [10] * spent   # `spent` reads len(history)
    return h


def test_selects_the_action_that_tests_the_most_live_hypotheses():
    pool = [mk(("distance", 1, 2), "ACTION3", 0.9),
            mk(("distance", 1, 3), "ACTION4", 0.6),
            mk(("containment", 2, 3), "ACTION4", 0.5)]
    chosen = pl.select_experiment(pool, LEGAL, met=lambda h: True)
    assert chosen.action == "ACTION4"                      # two bets share it; one step tests both


def test_a_bet_whose_precondition_holds_beats_one_whose_does_not():
    pool = [mk(("distance", 1, 2), "ACTION3", 0.9, pre=("adjacent:-x", 2)),
            mk(("distance", 1, 3), "ACTION4", 0.4)]
    chosen = pl.select_experiment(pool, LEGAL, met=lambda h: False)
    assert chosen.action == "ACTION4"


def test_an_untested_llm_bet_wins_a_tie_against_an_enumerator_bet():
    # Measured live (E-H002-1, 2026-09-14): without this tiebreak, valid
    # LLM hypotheses mostly never got a turn -- cd82 generated 12, only 2
    # were ever closed, because the enumerator refills the pool on every
    # decision while the LLM is called at most 3 times a level, and
    # nothing broke a tie on readiness/confidence in its favour.
    pool = [mk(("distance", 1, 2), "ACTION3", 0.8, source="enumerator"),
            mk(("distance", 1, 3), "ACTION3", 0.8, source="llm")]
    chosen = pl.select_experiment(pool, LEGAL, met=lambda h: True)
    assert chosen.source == "llm"
    # Only while untested -- once it has spent a step, an equally-confident
    # enumerator bet is not perpetually starved by it either.
    pool[1].history = [10]
    chosen = pl.select_experiment(pool, LEGAL, met=lambda h: True)
    assert chosen.source == "enumerator"
    # Scoped to a tie on the structural criteria (ready / discriminates /
    # batch size) -- it does not override a bet that genuinely tests MORE
    # live hypotheses at once, which stays the higher-order criterion.
    # (Confidence itself is not a safe tiebreak here: the enumerator's
    # "confidence" is its measured lift, the model's is self-reported --
    # different scales, not comparable, which is the other reason this
    # sits ahead of it rather than blended into it.)
    pool = [mk(("distance", 1, 2), "ACTION3", 0.9, source="enumerator"),
            mk(("containment", 4, 5), "ACTION3", 0.9, source="enumerator"),
            mk(("distance", 1, 3), "ACTION4", 0.1, source="llm")]
    chosen = pl.select_experiment(pool, LEGAL, met=lambda h: True)
    assert chosen.action == "ACTION3"          # tests two bets in one press


def test_illegal_or_dead_bets_are_never_selected():
    dead = mk(("distance", 1, 2), "ACTION3", 0.9); dead.status = hypothesis.FALSIFIED
    pool = [dead, mk(("distance", 1, 3), "ACTION7", 0.9)]
    assert pl.select_experiment(pool, {"ACTION1", "ACTION3"}, met=lambda h: True) is None


def test_a_failing_client_counts_toward_the_cap_and_returns_nothing():
    class Dead:
        def complete(self, prompt):
            raise ConnectionRefusedError("nobody home")
    p = pl.LLMProposer(Dead(), max_calls_per_level=2, min_step=0)
    assert p.propose("b", ENGINE, LIVE, LEGAL, control=set(), level_step=1) == []
    assert p.propose("b", ENGINE, LIVE, LEGAL, control=set(), level_step=2) == []
    assert p.stats["errors"] == 2 and "nobody home" in p.stats["last_error"]
    assert not p.should_call(3, pool_empty=True)           # capped, despite failing
