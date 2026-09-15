"""A language model as hypothesis scientist — never as controller.

The council's step (c') and reviewer C's §7–§11, §28: the model reads the
brief and returns a few **structured, falsifiable hypotheses**; the same
deterministic verifier that judges the enumerator's bets judges these. The
model does not choose actions, is called rarely (a cap per level; at level
start and after a run of falsifications), and every hypothesis it returns
must survive validation against what the agent actually knows: entities
that are on screen, relations that exist, actions that are legal, a
falsifier that is stated. Anything else is rejected and counted — the
valid-schema rate is the first metric in `research/hypotheses/H002`.

The client is interchangeable behind one method, `complete(prompt) -> str`:

  * `ScriptedClient` — canned answers, for tests and for the loop before any
    model exists (reviewer C: "test whether your experimental machinery
    actually works" first).
  * `OpenAICompatibleClient` — a POST to `{base_url}/chat/completions` with
    the standard library only. That is the shape Ollama and vLLM serve, and
    the shape the Kaggle path uses (vLLM from offline wheels on
    `127.0.0.1:8000/v1`), so the development and competition clients differ
    in a URL and a model name.

`select_experiment` is the other half of the reviewer's step: when several
hypotheses are live, prefer the legal action that **tests the most of them
at once** (their preconditions holding), so one step discriminates rather
than confirms.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field

import hypothesis as _hypothesis
import relations as _relations

RELATION_NAMES = set(_relations.RELATIONS) - _relations.EVIDENCE_ONLY - {"distance_drift"}

# One worked example, added after E-H002-1 (2026-09-14) measured the
# single largest rejection category (18 of 46 across five games, mostly
# gemma3:4b) was entities written the way the brief DISPLAYS them ("#5")
# rather than the bare int the schema asks for, plus "b" left null when
# only one entity seemed obviously relevant. `_ids` in this file now also
# accepts "#5"/"5" as a normalisation, but a concrete example is cheaper
# than relying on a 4B model to generalise a written rule, and fixes the
# null-b case a parser cannot repair.
EXAMPLE = """Example (ids are bare integers, never "#5"; both a and b are required):
{"hypotheses": [
  {"relation": "distance", "a": 5, "b": 9, "action": "ACTION2",
   "precondition": null, "predicted": "down",
   "falsifier": "distance(5,9) does not fall after 3 presses of ACTION2",
   "confidence": 0.7, "why": "ACTION2 has been the strongest lever on this pair."}
]}"""

SCHEMA_DOC = """Reply with JSON only, in exactly this shape:
{"hypotheses": [
  {"relation": "<one of: %s>",
   "a": <entity id (a bare integer, e.g. 5 -- not "#5"), or a list of such ids for a group>,
   "b": <entity id, or a list of ids for a group -- required, never null>,
   "action": "ACTION1".."ACTION5" or "ACTION7",
   "precondition": null or {"adjacency": "adjacent"|"apart", "side": "-x"|"+x"|"-y"|"+y"|null, "member": <entity id the controlled thing must be next to>},
   "predicted": "down" (the residual falls) or "zero" (the residual reaches 0),
   "falsifier": "<the observation that would make you abandon this>",
   "confidence": <0.0-1.0>,
   "why": "<one sentence>"}
]}
%s
Rules: name only entities that are on screen in the brief; a hypothesis is a bet that
the action drives the named relation's residual toward 0; state what would falsify it;
at most %d hypotheses; prefer bets that would explain how a level is cleared.""" % (
    ", ".join(sorted(RELATION_NAMES)), EXAMPLE, 5)


def build_prompt(brief_text: str, legal: set[str]) -> str:
    return (
        "You are proposing falsifiable hypotheses for an agent playing an unknown grid game.\n"
        "Below is the agent's brief: everything it currently believes, built only from what it has\n"
        "observed. Entities are #ids; relations are residuals (0 = holds); a 'lever' is an action\n"
        "that moves a residual more than the others do. Legal actions now: "
        + ", ".join(sorted(legal)) + ".\n\n=== BRIEF ===\n" + brief_text + "\n=== END ===\n\n" + SCHEMA_DOC
    )


@dataclass
class Rejection:
    reason: str
    item: dict


def _one_id(x) -> int | None:
    """An entity id, from whatever notation the model used for it.

    The brief displays ids as `#5`; a 4B model reliably echoes that
    notation back even though the schema asks for a bare int — measured
    live (E-H002-1, 2026-09-14): the single largest rejection category,
    18 of 46 across five games, and nearly all of it this, not a model
    that invented an id nobody showed it. Accepting `"#5"` and `"5"`
    alongside `5` is normalisation of a harmless serialisation choice,
    not a loosening of the check itself — every form still has to name a
    LIVE entity below, exactly as before."""
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, str):
        try:
            return int(x.lstrip("#").strip())
        except ValueError:
            return None
    return None


def _ids(x) -> tuple | None:
    if (i := _one_id(x)) is not None:
        return (i,)
    if isinstance(x, list) and x:
        ids = [_one_id(v) for v in x]
        if all(i is not None for i in ids):
            return tuple(sorted(set(ids)))
    return None


def parse_hypotheses(text: str, engine, live, legal: set[str], control: set[int] = frozenset()
                     ) -> tuple[list[_hypothesis.Hypothesis], list[Rejection]]:
    """Turn the model's reply into Hypothesis objects, rejecting anything the
    agent cannot check. Lenient about the wrapper (a bare list, or JSON
    inside prose), strict about the content."""
    live = set(live)
    out: list[_hypothesis.Hypothesis] = []
    rejects: list[Rejection] = []
    items = _extract_items(text)
    if items is None:
        return out, [Rejection("unparseable", {"text": text[:200]})]
    for item in items:
        if not isinstance(item, dict):
            rejects.append(Rejection("not an object", {"item": item})); continue
        rel = item.get("relation")
        if rel not in RELATION_NAMES:
            rejects.append(Rejection("unknown relation", item)); continue
        a, b = _ids(item.get("a")), _ids(item.get("b"))
        if a is None or b is None or not (set(a) | set(b)) <= live:
            rejects.append(Rejection("entity not on screen", item)); continue
        ka = a[0] if len(a) == 1 else a
        kb = b[0] if len(b) == 1 else b
        key = (rel, ka, kb)
        rec = engine.record(key) or engine.record((rel, kb, ka))
        if rec is None:
            rejects.append(Rejection("no such pair in the relation records", item)); continue
        if rec is not engine.record(key):
            key = (rel, kb, ka)
        action = item.get("action")
        if action not in legal or action == "ACTION6":
            rejects.append(Rejection("action not legal (or a bare click)", item)); continue
        pre = item.get("precondition")
        precondition = None
        if pre is not None:
            if not isinstance(pre, dict):
                rejects.append(Rejection("precondition not an object", item)); continue
            adj = pre.get("adjacency", _relations.ADJACENT)
            side = pre.get("side")
            member = pre.get("member")
            if adj not in (_relations.ADJACENT, _relations.APART) or (side is not None and side not in _relations.SIDES):
                rejects.append(Rejection("precondition vocabulary", item)); continue
            if not isinstance(member, int) or member not in live or member in control:
                rejects.append(Rejection("precondition member not on screen or is the controlled thing", item)); continue
            precondition = (f"{adj}:{side}" if side else adj, member)
        if item.get("predicted") not in ("down", "zero"):
            rejects.append(Rejection("prediction not checkable (down|zero)", item)); continue
        fals = item.get("falsifier")
        if not isinstance(fals, str) or len(fals.strip()) < 8:
            rejects.append(Rejection("no falsifier", item)); continue
        try:
            conf = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        conf = min(1.0, max(0.0, conf))
        if rec.residual is None:
            rejects.append(Rejection("residual undecidable right now", item)); continue
        if rec.residual == 0:
            rejects.append(Rejection("already holds", item)); continue
        out.append(_hypothesis.Hypothesis(
            key=key, action=action, lift=conf, start=rec.residual,
            precondition=precondition, confidence=conf,
            falsifier=fals.strip(), source="llm", predicted=item["predicted"]))
    return out, rejects


def _extract_items(text: str):
    text = text.strip()
    for candidate in (text, text[text.find("{"):text.rfind("}") + 1], text[text.find("["):text.rfind("]") + 1]):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("hypotheses"), list):
            return data["hypotheses"]
        if isinstance(data, list):
            return data
    return None


class ScriptedClient:
    """Canned replies, consumed in order; the last one repeats."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if len(self._replies) > 1:
            return self._replies.pop(0)
        return self._replies[0] if self._replies else "{\"hypotheses\": []}"


class OpenAICompatibleClient:
    """POST /chat/completions to any OpenAI-shaped server — Ollama, vLLM,
    or a remote — using only the standard library."""

    def __init__(self, base_url: str, model: str, api_key: str = "local", timeout_s: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s

    def complete(self, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]


@dataclass
class LLMProposer:
    client: object
    max_calls_per_level: int = 3
    min_step: int = 20            # let the brief fill before the first call
    after_falsified: int = 4      # call again once this many bets have died since the last call
    calls_this_level: int = 0
    falsified_since_call: int = 0
    last_call_step: int = -10**9
    stats: dict = field(default_factory=lambda: {"calls": 0, "returned": 0, "valid": 0,
                                                  "rejects": {}, "latency_s": []})

    def new_level(self) -> None:
        self.calls_this_level = 0
        self.falsified_since_call = 0
        self.last_call_step = -10**9

    def should_call(self, level_step: int, pool_empty: bool) -> bool:
        if self.calls_this_level >= self.max_calls_per_level or level_step < self.min_step:
            return False
        if self.calls_this_level == 0:
            return True
        return pool_empty and self.falsified_since_call >= self.after_falsified

    def propose(self, brief_text: str, engine, live, legal: set[str], control: set[int],
                level_step: int) -> list[_hypothesis.Hypothesis]:
        t0 = time.time()
        # A failed call is still a call: it counts toward the cap, so a dead
        # server is tried at most `max_calls_per_level` times per level
        # rather than on every step the pool runs dry.
        self.stats["calls"] += 1
        self.calls_this_level += 1
        self.falsified_since_call = 0
        self.last_call_step = level_step
        try:
            reply = self.client.complete(build_prompt(brief_text, legal))
        except Exception as exc:  # noqa: BLE001 — any client failure, the game must go on
            self.stats["errors"] = self.stats.get("errors", 0) + 1
            self.stats["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
            return []
        self.stats["latency_s"].append(round(time.time() - t0, 2))
        hyps, rejects = parse_hypotheses(reply, engine, live, legal, control)
        self.stats["returned"] += len(hyps) + len(rejects)
        self.stats["valid"] += len(hyps)
        for r in rejects:
            self.stats["rejects"][r.reason] = self.stats["rejects"].get(r.reason, 0) + 1
        return hyps


def select_experiment(pool: list[_hypothesis.Hypothesis], legal: set[str], met) -> _hypothesis.Hypothesis | None:
    """The hypothesis to act on: first one whose precondition holds; then
    one whose action, taken now, is forecast differently by two live bets
    (H004 — one press falsifies one of them); then the action that tests
    the most live bets at once; ties by confidence. `met(h) -> bool`.

    The bet returned is the READY one of a divergent pair, so the press
    happens now rather than after a route to the other's precondition."""
    live = [h for h in pool if h.status == _hypothesis.LIVE and h.action in legal]
    if not live:
        return None
    ready = {id(h): (h.precondition is None or met(h)) for h in live}
    def score(h):
        same = [g for g in live if g.action == h.action]
        forecasts = [g.forecast(ready[id(g)]) for g in same]
        # An untested model-sourced bet, among ties on readiness/discrimination/
        # batch size: measured live (E-H002-1, 2026-09-14) that without this,
        # valid LLM hypotheses mostly never get a turn — cd82 generated 12,
        # only 2 were ever closed, because the enumerator refills the pool on
        # every decision while the LLM is called at most 3 times a level, and
        # nothing broke the tie in its favour once both were ready. This does
        # not override readiness or a discriminating press (still the higher-
        # order criteria); it only stops a proposed-but-unexercised bet from
        # starving behind an enumerator bet that ties it on everything else.
        return (ready[id(h)], len(set(forecasts) - {None}) > 1,
                sum(1 for f in forecasts if f is not None),
                h.source == "llm" and h.spent == 0, h.confidence, h.lift)
    return max(live, key=score)


def diverges(pool: list[_hypothesis.Hypothesis], action: str, met) -> bool:
    """Do two live bets on `action` forecast its residual differently in
    the current state? True is a discriminating press."""
    live = [h for h in pool if h is not None and h.status == _hypothesis.LIVE and h.action == action]
    forecasts = {h.forecast(h.precondition is None or met(h)) for h in live} - {None}
    return len(forecasts) > 1
