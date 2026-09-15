"""The predictive transition model (H003): a forecast per entity and per
pair from the tallies, scored against what the layers then record.

What is pinned: it abstains below the evidence floor and says so; it uses
the conditional tally when that has enough tries and the unconditional one
otherwise; the score counts hits, misses and undecidables per layer and
keeps a confident miss as a surprise; the precondition it forecasts under
is the one the next update files the outcome under.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

import belief  # noqa: E402
import predictor  # noqa: E402
import relations  # noqa: E402
from predictor import ENTITY, PAIR, PREDICT_MIN_TRIES  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────

def cells(x0, y0, w=2, h=2):
    return frozenset((x0 + i, y0 + j) for i in range(w) for j in range(h))


class Engine:
    """A stand-in with the three things the predictor reads."""

    def __init__(self, records, updated=None, condition=None):
        self.records = records
        self.group_records = {}
        self.updated = updated if updated is not None else {k: k[1:] for k in records}
        self._condition = condition

    def record(self, key):
        return self.records.get(key)

    def condition_now(self, members):
        return self._condition


def pair(residual, previous=None, **tallies):
    r = relations.PairRecord()
    r.residual, r.previous = residual, previous
    for act, (d, u, f) in tallies.items():
        r.by_action[act] = {relations.DOWN: d, relations.UP: u, relations.FLAT: f}
    return r


def a_belief(rid, action, effects: dict, unchanged: int):
    b = belief.Belief(rid, 3)
    for effect, n in effects.items():
        for _ in range(n):
            b.observe(action, effect[0], effect if len(effect) == 3 else None)
    for _ in range(unchanged):
        b.observe(action, None)
    return b


class World:
    def __init__(self, *beliefs):
        self._beliefs = {b.region_id: b for b in beliefs}
        self.last_effects = {}


# ── forecasting ──────────────────────────────────────────────────────────

def test_entity_forecast_abstains_below_the_floor_and_names_the_majority_above_it():
    thin = a_belief(1, "ACTION1", {(belief.MOVED, 1, 0): 2}, unchanged=1)   # 3 tries
    fat = a_belief(2, "ACTION1", {(belief.MOVED, 1, 0): 7}, unchanged=3)    # 10 tries
    fc = predictor.Predictor().forecast(World(thin, fat), Engine({}), "ACTION1")
    assert 1 not in fc.entities and fc.abstained[ENTITY] == 1
    assert fc.entities[2] == ((belief.MOVED, 1, 0), 0.7)


def test_unchanged_is_a_forecastable_outcome():
    still = a_belief(1, "ACTION2", {(belief.GREW,): 1}, unchanged=5)
    fc = predictor.Predictor().forecast(World(still), Engine({}), "ACTION2")
    assert fc.entities[1] == (belief.UNCHANGED, 5 / 6)


def test_pair_forecast_prefers_the_conditional_tally_when_it_has_enough_tries():
    rec = pair(20, ACTION5=(2, 2, 6))                       # unconditional: flat 60%
    rec.by_action_given["adjacent:-x"] = {"ACTION5": {relations.DOWN: 4, relations.UP: 0, relations.FLAT: 0}}
    key = ("part_size_diff", 1, 2)
    p = predictor.Predictor()
    fc = p.forecast(World(), Engine({key: rec}, condition="adjacent:-x"), "ACTION5")
    assert fc.pairs[key] == (relations.DOWN, 1.0, True)
    fc = p.forecast(World(), Engine({key: rec}, condition="apart:+y"), "ACTION5")
    assert fc.pairs[key] == (relations.FLAT, 0.6, False)   # falls back to the unconditional tally


def test_pair_forecast_abstains_without_tries_or_without_a_residual():
    key_thin = ("distance", 1, 2)
    key_none = ("distance", 1, 3)
    eng = Engine({key_thin: pair(9, ACTION1=(2, 0, 1)), key_none: pair(None, ACTION1=(8, 0, 0))})
    fc = predictor.Predictor().forecast(World(), eng, "ACTION1")
    assert not fc.pairs and fc.abstained[PAIR] == 1     # None is not abstention, it is no question


def test_evidence_only_relations_are_never_forecast():
    key = ("cell_exchange", 1, 2)
    fc = predictor.Predictor().forecast(World(), Engine({key: pair(3, ACTION1=(8, 0, 0))}), "ACTION1")
    assert not fc.pairs and fc.abstained[PAIR] == 0


# ── scoring ──────────────────────────────────────────────────────────────

def test_score_counts_hits_misses_and_undecidables_per_layer_and_keeps_a_surprise():
    p = predictor.Predictor()
    fc = predictor.Forecast(action="ACTION1")
    fc.entities = {1: ((belief.MOVED, 1, 0), 0.9), 2: (belief.UNCHANGED, 0.6), 3: ((belief.GREW,), 0.5)}
    k_hit, k_miss, k_gone = ("distance", 1, 2), ("distance", 1, 3), ("distance", 2, 3)
    fc.pairs = {k_hit: (relations.DOWN, 0.8, False), k_miss: (relations.FLAT, 0.9, True),
                k_gone: (relations.DOWN, 0.7, False)}
    world = World()
    world.last_effects = {1: (belief.MOVED, 1, 0), 2: (belief.GREW,)}      # 3 vanished from view unobserved
    eng = Engine({k_hit: pair(4, previous=6), k_miss: pair(2, previous=5), k_gone: pair(1, previous=None)},
                 updated={k_hit: (1, 2), k_miss: (1, 3)})                     # k_gone not updated this step
    counts = p.score(fc, world, eng, step=7)
    assert counts[ENTITY] == {"hits": 1, "misses": 1, "undecidable": 1, "abstained": 0}
    assert counts[PAIR] == {"hits": 1, "misses": 1, "undecidable": 1, "abstained": 0}
    assert p.game.accuracy(ENTITY) == 0.5 and p.level.accuracy(PAIR) == 0.5
    assert p.game.by_relation["distance"] == [1, 1]
    assert p.game.conditional == [0, 1] and p.game.unconditional == [1, 0]
    # Movement splits: the entity layer forecast two changes (one right), and
    # both entities actually changed; the pair layer forecast one change
    # (right) and both decided pairs actually moved (one foreseen).
    assert p.game.moving[ENTITY] == [1, 0] and p.game.moved[ENTITY] == [1, 1]
    assert p.game.cells == {("ACTION1", "distance"): [1, 1]}
    assert p.game.moving[PAIR] == [1, 0] and p.game.moved[PAIR] == [1, 1]
    # Only the confident miss (0.9 on the FLAT forecast) is a surprise; the 0.6 one is not.
    assert [s[2] for s in p.surprises] == ["distance(#1,#3)"]
    assert p.surprises[0][0] == 7 and "down 5->2" in p.surprises[0][4]


def test_brier_rewards_calibration_not_boldness():
    p = predictor.Predictor()
    fc = predictor.Forecast(action="ACTION1")
    fc.entities = {1: (belief.UNCHANGED, 1.0), 2: (belief.UNCHANGED, 0.5)}
    world = World(); world.last_effects = {1: (belief.GREW,), 2: (belief.GREW,)}
    p.score(fc, world, Engine({}), step=1)
    assert p.game.brier[ENTITY] == 1.0 + 0.25


def test_coverage_reports_abstentions_beside_accuracy():
    p = predictor.Predictor()
    fc = predictor.Forecast(action="ACTION1"); fc.abstained[ENTITY] = 3
    fc.entities = {1: (belief.UNCHANGED, 1.0)}
    world = World(); world.last_effects = {1: belief.UNCHANGED}
    p.score(fc, world, Engine({}), step=1)
    assert p.game.accuracy(ENTITY) == 1.0 and p.game.coverage(ENTITY) == 0.25


def test_new_level_keeps_the_game_ledger_and_clears_the_level_one():
    p = predictor.Predictor()
    fc = predictor.Forecast(action="ACTION1"); fc.entities = {1: (belief.UNCHANGED, 1.0)}
    world = World(); world.last_effects = {1: belief.UNCHANGED}
    p.score(fc, world, Engine({}), step=1)
    p.new_level()
    assert p.game.predicted(ENTITY) == 1 and p.level.predicted(ENTITY) == 0


def test_describe_says_nothing_forecast_before_the_floor_and_reads_after():
    p = predictor.Predictor()
    assert "nothing forecast yet" in p.describe()[1]
    fc = predictor.Forecast(action="ACTION3")
    fc.entities = {i: (belief.UNCHANGED, 0.9) for i in range(5)}
    world = World(); world.last_effects = {i: (belief.GREW,) for i in range(5)}
    p.score(fc, world, Engine({}), step=4)
    text = "\n".join(p.describe())
    assert "things: 0% of 5" in text and "least predictable: ACTION3 (5 of 5 wrong)" in text
    assert "where the vocabulary is short" not in text     # no pair forecasts, no cell table
    assert "actual 0% of 5 foreseen" in text
    assert "surprised t=4 ACTION3: #4 expected unchanged (90%), got grew" in text


# ── the layers it reads ──────────────────────────────────────────────────

def test_belief_records_what_happened_to_each_entity_this_step():
    w = belief.WorldBelief()
    w.update({1: (3, cells(0, 0)), 2: (4, cells(10, 10))}, "ACTION1", [])
    assert w.last_effects == {1: belief.UNCHANGED, 2: belief.UNCHANGED}
    w.update({1: (3, cells(1, 0)), 2: (4, cells(10, 10))}, "ACTION1", list(cells(0, 0) | cells(1, 0)))
    assert w.last_effects == {1: (belief.MOVED, 1, 0), 2: belief.UNCHANGED}
    w.update({1: (3, cells(1, 0))}, "ACTION1", [])
    assert w.last_effects == {1: belief.UNCHANGED, 2: (belief.VANISHED,)}
    w.update({1: (3, cells(1, 0))}, "RESET", [])
    assert w.last_effects == {}


def test_condition_now_is_the_condition_the_next_update_files_under():
    """The forecast reads the precondition off the current frame; the next
    update must tally the outcome under that same string."""
    eng = relations.RelationEngine()
    control, block = 1, 2
    frame = lambda cx: {control: (7, cells(cx, 5)), block: (3, cells(10, 4, 4, 4))}  # noqa: E731
    eng.update(frame(0), {control, block}, None, control={control})
    eng.update(frame(0), {control, block}, "ACTION1", control={control})
    now = eng.condition_now((control, block))
    assert now == "apart:-x"
    eng.update(frame(2), {control, block}, "ACTION5", control={control})
    rec = eng.records[("distance", control, block)]
    assert rec.by_action_given[now]["ACTION5"][relations.DOWN] == 1
    assert eng.updated[("distance", control, block)] == (control, block)
    # Adjacent from the left once the gap closes.
    eng.update(frame(7), {control, block}, "ACTION5", control={control})
    assert eng.condition_now((control, block)) == "adjacent:-x"


def test_ledger_summary_is_json_able():
    import json
    p = predictor.Predictor()
    fc = predictor.Forecast(action="ACTION1"); fc.entities = {1: (belief.UNCHANGED, 1.0)}
    world = World(); world.last_effects = {1: belief.UNCHANGED}
    p.score(fc, world, Engine({}), step=1)
    s = json.loads(json.dumps(p.game.summary()))
    assert s[ENTITY]["accuracy"] == 1.0 and s["by_action"]["ACTION1"][ENTITY] == [1, 0]
    assert PREDICT_MIN_TRIES == 4


# ── k-step rollouts (H008) ───────────────────────────────────────────────

def test_effect_table_and_rollout_read_the_same_tallies():
    import belief as _belief
    import predictor as _predictor
    w = _belief.WorldBelief()
    b = w._beliefs[7] = _belief.Belief(7, 3)
    for _ in range(4):
        b.observe("ACTION1", _belief.MOVED, (_belief.MOVED, 1, 0))
    for _ in range(4):
        b.observe("ACTION2", None)                       # unchanged, four times
    b.observe("ACTION3", _belief.GREW, (_belief.GREW,))  # one try: below the floor
    table = _predictor.effect_table(w)
    assert table[7]["ACTION1"] == ((_belief.MOVED, 1, 0), 1.0)
    assert table[7]["ACTION2"] == (_belief.UNCHANGED, 1.0)
    assert "ACTION3" not in table[7]
    assert _predictor.rollout(table[7], ["ACTION1", "ACTION2", "ACTION1"]) == [
        (_belief.MOVED, 1, 0), _belief.UNCHANGED, (_belief.MOVED, 1, 0)]
    assert _predictor.rollout(table[7], ["ACTION1", "ACTION3"]) is None


def test_rollouts_are_scored_from_the_table_at_the_windows_start():
    """A 3-step rollout is a hit only if all three per-step effects are
    right; an entity that leaves the screen inside the window is
    undecidable; a window is never scored across an attempt boundary."""
    import belief as _belief
    import predictor as _predictor
    p = _predictor.Predictor()
    row = {"ACTION1": ((_belief.MOVED, 1, 0), 1.0), "ACTION2": (_belief.UNCHANGED, 1.0)}
    moved, still = (_belief.MOVED, 1, 0), _belief.UNCHANGED
    steps = [("ACTION1", moved), ("ACTION2", still), ("ACTION1", moved),   # 3 right
             ("ACTION1", still)]                                           # then one wrong
    for action, actual in steps:
        p._windows.append(({7: row}, action, {7: actual}))
        p._score_rollouts()
    assert p.game.horizon[1][:2] == [3, 1]
    assert p.game.horizon[3][:2] == [1, 1]          # steps 1-3 hit, steps 2-4 miss
    assert p.game.horizon[10][:2] == [0, 0]         # window not yet long enough
    p._windows.append(({7: row}, "ACTION2", {}))    # #7 gone this step
    p._score_rollouts()
    assert p.game.horizon[1][2] == 1                # undecidable
    p.new_attempt()
    assert len(p._windows) == 0
    summary = p.game.summary()["horizon"]
    assert summary["1"]["hits"] == 3 and summary["3"]["accuracy"] == 0.5
