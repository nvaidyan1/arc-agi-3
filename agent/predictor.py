"""The predictive transition model: what the next frame will look like, in
the vocabulary the layers already speak — and how often that is right.

Reviewer C (2026-09-14, §12): a world model is not a set of tallies but a
set of *predictions* that can be wrong. Everything below this file records
what actions did; nothing said in advance what one would do, so nothing
could be surprised. This file says it. From the evidence already held —

    Belief.acted / effects[action]      what this action did to this entity
    PairRecord.by_action[_given]        which way it moved this residual,
                                        under which precondition

— it forecasts, for every live entity, the effect the action will have,
and for every pair, the direction its residual will move; then, once the
frame is in, it scores the forecast. The score is **prediction error per
layer**, the metric that sits between "the representation is valid" (the
relation probe) and "the agent scores" (the sweep), and it is kept per
level, per game, per action and per relation.

Three properties, the same three every lens has:

  * **Abstaining is an outcome.** Below PREDICT_MIN_TRIES tries of an
    action on a thing, nothing is forecast, and the count of abstentions
    is reported beside the accuracy — a model that abstains its way to a
    perfect score is visible as such (coverage).
  * **No simulator.** A forecast is one step from the tallies; it is
    compared to what happened, never to a counterfactual.
  * **Nothing decides on it.** The policy does not read the forecast. Its
    consumers are the brief (PREDICTED), the sweep summary, and the rival
    hypotheses of H004, which are proposed where the conditional and
    unconditional tallies disagree. A confident miss is where the
    vocabulary is missing a factor — cd82's paint rule is expected to
    show up as *error* on ACTION5 before anything can name it.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import belief as _belief
import relations as _relations

# The same evidence floor the determinism and lever tests use.
PREDICT_MIN_TRIES = 4
# A miss at or above this confidence is a surprise worth showing.
SURPRISE_CONFIDENCE = 0.75
SURPRISES_KEPT = 5

ENTITY, PAIR = "entity", "pair"
LAYERS = (ENTITY, PAIR)
# H008: how far the entity forecast can be rolled forward. A k-step
# prediction is the per-step effect for each of the next k actions,
# composed from the tallies as they stood at the window's start, and it
# is a hit only if every step is right — "can the model roll forward k
# steps without error", the predictive-sufficiency reading reviewer C
# asked for (2026-09-15, second note §13). No simulator: the tallies do
# not depend on the imagined state, so this measures exactly how much of
# the future the tallies alone carry.
HORIZONS = (1, 3, 10)


@dataclass
class Forecast:
    """One step's predictions, made before the frame that answers them."""
    action: str
    entities: dict = field(default_factory=dict)   # rid -> (outcome, confidence)
    pairs: dict = field(default_factory=dict)      # key -> (direction, confidence, conditional)
    abstained: dict = field(default_factory=lambda: {ENTITY: 0, PAIR: 0})
    table: dict = field(default_factory=dict)      # rid -> action -> (effect, confidence), H008


def effect_table(belief) -> dict:
    """Per live entity, per action tried PREDICT_MIN_TRIES times on it, the
    effect it most often had and how often. The one-step forecast is this
    table read at one action; a rollout reads it along a sequence."""
    table: dict = {}
    for b in belief._beliefs.values():
        if not b.live:
            continue
        row = {}
        for action, n in b.acted.items():
            if n < PREDICT_MIN_TRIES:
                continue
            counts = dict(b.effects.get(action, {}))
            unchanged = n - b.changed.get(action, 0)
            if unchanged:
                counts[_belief.UNCHANGED] = unchanged
            best = max(counts, key=counts.get)
            row[action] = (best, counts[best] / n)
        if row:
            table[b.region_id] = row
    return table


def rollout(row: dict, actions) -> list | None:
    """The predicted effect at each of `actions`, for one entity, from its
    table row — or None (abstain) when any action is unforecastable."""
    out = []
    for a in actions:
        if a not in row:
            return None
        out.append(row[a][0])
    return out


class Ledger:
    """Hits, misses and the rest, per layer — and the splits that say
    where the error lives."""

    def __init__(self) -> None:
        self.hits = {l: 0 for l in LAYERS}
        self.misses = {l: 0 for l in LAYERS}
        self.undecidable = {l: 0 for l in LAYERS}
        self.abstained = {l: 0 for l in LAYERS}
        self.brier = {l: 0.0 for l in LAYERS}
        self.by_action: dict[str, dict[str, list[int]]] = {}   # action -> layer -> [hits, misses]
        self.by_relation: dict[str, list[int]] = {}            # relation -> [hits, misses]
        # Pair-layer forecasts split by which tally made them.
        self.conditional = [0, 0]
        self.unconditional = [0, 0]
        # The numbers that are not swamped by the static majority: a
        # forecast of "flat"/"unchanged" on a pair nothing has ever moved
        # is right almost by definition (measured on sp80: 99% of 43,000
        # pair forecasts, nearly all of them flat). So, per layer:
        #   moving   [hits, misses] where the forecast was of a change
        #   moved    [hits, misses] where a change actually happened
        # The first is precision of "something will happen", the second
        # is recall of what did.
        self.moving = {l: [0, 0] for l in LAYERS}
        self.moved = {l: [0, 0] for l in LAYERS}
        # (action, relation) -> [hits, misses] over NON-TRIVIAL pair
        # forecasts only — a change was forecast, or one happened. This is
        # the table that localises error: H003's second prediction is that
        # on cd82 the misses concentrate in one cell of it.
        self.cells: dict[tuple, list[int]] = {}
        self.steps = 0
        # H008: k -> [hits, misses, undecidable, abstained] for entity
        # rollouts over the last k actions.
        self.horizon: dict[int, list[int]] = {k: [0, 0, 0, 0] for k in HORIZONS}

    def record(self, layer: str, hit: bool, confidence: float, action: str,
               relation: str | None = None, conditional: bool | None = None,
               predicted_change: bool = False, actual_change: bool = False) -> None:
        (self.hits if hit else self.misses)[layer] += 1
        self.brier[layer] += (1 - confidence) ** 2 if hit else confidence ** 2
        if predicted_change:
            self.moving[layer][0 if hit else 1] += 1
        if actual_change:
            self.moved[layer][0 if hit else 1] += 1
        per = self.by_action.setdefault(action, {l: [0, 0] for l in LAYERS})[layer]
        per[0 if hit else 1] += 1
        if relation is not None:
            self.by_relation.setdefault(relation, [0, 0])[0 if hit else 1] += 1
        if conditional is not None:
            (self.conditional if conditional else self.unconditional)[0 if hit else 1] += 1
        if relation is not None and (predicted_change or actual_change):
            self.cells.setdefault((action, relation), [0, 0])[0 if hit else 1] += 1

    def predicted(self, layer: str) -> int:
        return self.hits[layer] + self.misses[layer]

    def accuracy(self, layer: str) -> float | None:
        n = self.predicted(layer)
        return self.hits[layer] / n if n else None

    def coverage(self, layer: str) -> float | None:
        """Of everything that could have been forecast and then decided,
        how much was forecast."""
        n = self.predicted(layer) + self.abstained[layer]
        return self.predicted(layer) / n if n else None

    def mean_brier(self, layer: str) -> float | None:
        n = self.predicted(layer)
        return self.brier[layer] / n if n else None

    def summary(self) -> dict:
        """JSON-able, for the sweep summary."""
        out: dict = {"steps": self.steps}
        for layer in LAYERS:
            out[layer] = {
                "hits": self.hits[layer], "misses": self.misses[layer],
                "undecidable": self.undecidable[layer], "abstained": self.abstained[layer],
                "accuracy": _r(self.accuracy(layer)), "coverage": _r(self.coverage(layer)),
                "brier": _r(self.mean_brier(layer)),
            }
        out["by_action"] = {a: {l: list(v) for l, v in per.items()} for a, per in self.by_action.items()}
        out["by_relation"] = {r: list(v) for r, v in self.by_relation.items()}
        out["conditional"] = list(self.conditional)
        out["unconditional"] = list(self.unconditional)
        out["moving"] = {l: list(v) for l, v in self.moving.items()}
        out["moved"] = {l: list(v) for l, v in self.moved.items()}
        out["cells"] = {f"{a} {r}": list(v) for (a, r), v in self.cells.items()}
        out["horizon"] = {str(k): {"hits": v[0], "misses": v[1], "undecidable": v[2],
                                   "abstained": v[3],
                                   "accuracy": _r(v[0] / (v[0] + v[1])) if v[0] + v[1] else None,
                                   "coverage": _r((v[0] + v[1]) / (v[0] + v[1] + v[3]))
                                   if v[0] + v[1] + v[3] else None}
                          for k, v in self.horizon.items()}
        return out


def _r(x):
    return None if x is None else round(x, 3)


def _pct(hm: list) -> str:
    return f"{hm[0] / sum(hm):.0%}" if sum(hm) else "-"


class Predictor:
    def __init__(self) -> None:
        self.game = Ledger()
        self.level = Ledger()
        # (level step, action, what, predicted, actual, confidence)
        self.surprises: deque = deque(maxlen=SURPRISES_KEPT)
        # The most recent step's counts, recording only.
        self.last: dict = {}
        # H008: the last HORIZONS[-1] scored steps — (table at forecast
        # time, action, actual effects) — so a k-step rollout made at the
        # window's start can be scored against what then happened.
        self._windows: deque = deque(maxlen=max(HORIZONS))

    def new_level(self) -> None:
        self.level = Ledger()
        self.surprises.clear()
        self._windows.clear()

    def new_attempt(self) -> None:
        """A RESET: the steps before it are not the run-up to what follows."""
        self._windows.clear()

    # ── before ──────────────────────────────────────────────────────────

    def forecast(self, belief, engine, action: str) -> Forecast:
        """What `action` will do, from the tallies as they stand. Call
        before the layers fold the resulting frame in."""
        fc = Forecast(action=action, table=effect_table(belief))
        for b in belief._beliefs.values():
            if not b.live:
                continue
            row = fc.table.get(b.region_id, {})
            if action not in row:
                fc.abstained[ENTITY] += 1
                continue
            fc.entities[b.region_id] = row[action]
        for key, members in engine.updated.items():
            rel = key[0]
            if rel in _relations.EVIDENCE_ONLY or rel == "distance_drift":
                continue
            rec = engine.record(key)
            if rec is None or rec.residual is None:
                continue        # no direction can be defined from None
            condition = engine.condition_now(members)
            tally, conditional = None, False
            given = rec.by_action_given.get(condition, {}).get(action) if condition else None
            if given is not None and sum(given.values()) >= PREDICT_MIN_TRIES:
                tally, conditional = given, True
            elif action in rec.by_action and sum(rec.by_action[action].values()) >= PREDICT_MIN_TRIES:
                tally = rec.by_action[action]
            if tally is None:
                fc.abstained[PAIR] += 1
                continue
            best = max(tally, key=tally.get)
            fc.pairs[key] = (best, tally[best] / sum(tally.values()), conditional)
        return fc

    # ── after ───────────────────────────────────────────────────────────

    def score(self, fc: Forecast, belief, engine, step: int) -> dict:
        """Compare the forecast with what the layers just recorded."""
        counts = {l: {"hits": 0, "misses": 0, "undecidable": 0, "abstained": fc.abstained[l]}
                  for l in LAYERS}
        for ledger in (self.game, self.level):
            ledger.steps += 1
            for l in LAYERS:
                ledger.abstained[l] += fc.abstained[l]
        actual_effects = belief.last_effects
        for rid, (predicted, conf) in fc.entities.items():
            actual = actual_effects.get(rid)
            if actual is None:
                counts[ENTITY]["undecidable"] += 1
                self._undecidable(ENTITY)
                continue
            hit = actual == predicted
            counts[ENTITY]["hits" if hit else "misses"] += 1
            self._record(ENTITY, hit, conf, fc.action,
                         predicted_change=predicted != _belief.UNCHANGED,
                         actual_change=actual != _belief.UNCHANGED)
            if not hit and conf >= SURPRISE_CONFIDENCE:
                self.surprises.append((step, fc.action, f"#{rid}", _effect(predicted), _effect(actual), conf))
        for key, (predicted, conf, conditional) in fc.pairs.items():
            rec = engine.record(key) if key in engine.updated else None
            if rec is None or rec.previous is None or rec.residual is None:
                counts[PAIR]["undecidable"] += 1
                self._undecidable(PAIR)
                continue
            actual = (_relations.DOWN if rec.residual < rec.previous
                      else _relations.UP if rec.residual > rec.previous else _relations.FLAT)
            hit = actual == predicted
            counts[PAIR]["hits" if hit else "misses"] += 1
            self._record(PAIR, hit, conf, fc.action, key[0], conditional,
                         predicted_change=predicted != _relations.FLAT,
                         actual_change=actual != _relations.FLAT)
            if not hit and conf >= SURPRISE_CONFIDENCE:
                self.surprises.append((step, fc.action, _name(key), predicted,
                                       f"{actual} {rec.previous}->{rec.residual}", conf))
        self._windows.append((fc.table, fc.action, dict(actual_effects)))
        self._score_rollouts()
        self.last = counts
        return counts

    def _score_rollouts(self) -> None:
        """For each horizon k that the window covers: the rollout made from
        the table as it stood k steps ago, along the k actions actually
        taken, against the k effects actually recorded, per entity."""
        window = list(self._windows)
        for k in HORIZONS:
            if len(window) < k:
                continue
            table0, actions = window[-k][0], [w[1] for w in window[-k:]]
            for rid, row in table0.items():
                actual = [w[2].get(rid) for w in window[-k:]]
                if any(a is None for a in actual):
                    self._horizon(k, 2)          # left the screen: undecidable
                    continue
                pred = rollout(row, actions)
                if pred is None:
                    self._horizon(k, 3)          # abstained
                    continue
                self._horizon(k, 0 if pred == actual else 1)

    def _horizon(self, k: int, slot: int) -> None:
        for ledger in (self.game, self.level):
            ledger.horizon[k][slot] += 1

    def _record(self, layer, hit, conf, action, relation=None, conditional=None,
                predicted_change=False, actual_change=False) -> None:
        for ledger in (self.game, self.level):
            ledger.record(layer, hit, conf, action, relation, conditional,
                          predicted_change, actual_change)

    def _undecidable(self, layer) -> None:
        for ledger in (self.game, self.level):
            ledger.undecidable[layer] += 1

    # ── the brief ───────────────────────────────────────────────────────

    def describe(self) -> list[str]:
        led = self.level
        out = ["PREDICTED (one-step forecasts from the tallies; accuracy among forecasts made, "
               "coverage of what could have been forecast)"]
        parts = []
        for layer, label in ((ENTITY, "things"), (PAIR, "relations")):
            acc, cov = led.accuracy(layer), led.coverage(layer)
            if acc is None:
                continue
            line = f"  {label}: {acc:.0%} of {led.predicted(layer)} (coverage {cov:.0%})"
            mv, md = led.moving[layer], led.moved[layer]
            if sum(mv) or sum(md):
                line += (f"; changes: forecast {_pct(mv)} of {sum(mv)} right, "
                         f"actual {_pct(md)} of {sum(md)} foreseen")
            parts.append(line)
        if not parts:
            out.append(f"  nothing forecast yet (fewer than {PREDICT_MIN_TRIES} tries of an action on any thing)")
            return out
        out.extend(parts)
        hz = [(k, v) for k, v in led.horizon.items() if v[0] + v[1]]
        if hz:
            out.append("  rolled forward: " + ", ".join(
                f"{k} step{'s' if k > 1 else ''} {v[0] / (v[0] + v[1]):.0%} of {v[0] + v[1]}" for k, v in hz))
        c, u = led.conditional, led.unconditional
        if sum(c) and sum(u):
            out.append(f"  relations with a precondition {c[0] / sum(c):.0%} of {sum(c)}, without {u[0] / sum(u):.0%} of {sum(u)}")
        worst = sorted(((h + m, m, a) for a, per in led.by_action.items()
                        for h, m in [tuple(map(sum, zip(*per.values())))] if h + m >= PREDICT_MIN_TRIES),
                       key=lambda t: -t[1] / t[0])[:2]
        if worst and worst[0][1]:
            out.append("  least predictable: " + ", ".join(
                f"{a} ({m} of {n} wrong)" for n, m, a in worst if m))
        # Where the misses on changes concentrate: the (action, relation)
        # cells with the most wrong non-trivial forecasts.
        short = sorted(((m, h + m, a, r) for (a, r), (h, m) in led.cells.items()
                        if h + m >= PREDICT_MIN_TRIES and m), reverse=True)[:3]
        if short:
            out.append("  where the vocabulary is short: " + ", ".join(
                f"{a} on {r} ({m} of {n} change forecasts wrong)" for m, n, a, r in short))
        for step, action, what, predicted, actual, conf in list(self.surprises)[-3:]:
            out.append(f"  surprised t={step} {action}: {what} expected {predicted} ({conf:.0%}), got {actual}")
        return out


def _name(key: tuple) -> str:
    rel, a, b = key
    side = lambda k: ("{" + ",".join(f"#{m}" for m in k) + "}") if isinstance(k, tuple) else f"#{k}"  # noqa: E731
    return f"{rel}({side(a)},{side(b)})"


def _effect(outcome: tuple) -> str:
    if len(outcome) == 3:
        return f"{outcome[0]} {_belief._dir_name(outcome)}"
    return outcome[0]
