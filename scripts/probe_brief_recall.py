"""Is the brief rich enough to hand over? Recall of the goal coordinate.

The cut-off test agreed on 2026-09-14 (`docs/plan.md` 5b (a)). For every
level advance in the recordings, replay the perception stack and compose
the brief as it stood k steps BEFORE the advance, then ask whether the
coordinate that turned out to matter — a residual that fell into the
advance under a lever, the relation probe's (iii') key — was in the text a
proposer would have read:

    FALLING    named as a candidate                    -> the brief said it
    RELATIONS  present, with or without its lever      -> findable
    engine     computed but crowded out of the text    -> a SELECTION gap
    absent     no such coordinate exists               -> a VOCABULARY gap

The three gaps are different work, which is the point of measuring this
rather than arguing about whether the vocabulary is "rich enough".

Usage:
    .venv/bin/python scripts/probe_brief_recall.py recordings/<run> [more...] [--lead 3 8]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

from arcengine import FrameData, GameAction  # noqa: E402

import belief as belief_mod  # noqa: E402
import brief as brief_mod  # noqa: E402
import entities  # noqa: E402
import perception  # noqa: E402
import relations  # noqa: E402
from constants import STAMINA_MIN_SIZE, USE_SHIFT_FALLBACK  # noqa: E402
from constraints import StaminaDetector  # noqa: E402
from control import MoveModel  # noqa: E402

WINDOW = 8


def _frame(entry):
    rows = entry.get("frame")
    if not rows:
        return None
    return FrameData(frame=[[[int(ch, 16) for ch in row] for row in rows]],
                     levels_completed=entry["levels_completed"])


class Replay:
    """The agent's perception stack, replayed from a recording, with the
    same attribute names the Briefer reads."""

    def __init__(self, game_id):
        self.game_id = game_id
        self.reset_level()

    def reset_level(self):
        self.regions = entities.RegionTracker()
        self.moves = MoveModel()
        self.relations = relations.RelationEngine()
        self.belief = belief_mod.WorldBelief()
        self.brief = brief_mod.Briefer()
        self.stamina = StaminaDetector()
        self._background = None
        self._exact = set()
        self._live = {}

    def _canvas_ids(self):
        best, size = None, 0
        for rid in self.regions.live:
            colour, cells = self.regions._tracked[rid]
            if colour == self._background and len(cells) > size:
                best, size = rid, len(cells)
        return {best} if best is not None else set()

    def step(self, prev, frame, acted: GameAction | None, prev_action_name):
        counts = perception.colour_counts(frame)
        if self._background is None and counts:
            self._background = max(counts, key=counts.get)
        if prev_action_name == "RESET":
            self.regions.expect_home()
        changed = perception.diff_cells(prev, frame) if prev is not None else []
        if prev is not None and acted is not None and changed:
            moved = perception.detect_translation(prev, frame)
            if moved is not None:
                _c, size, offset, anchor = moved
                self.moves.observe_translation(acted, offset, size, anchor, self.game_id)
                self._exact.add(acted)
            elif USE_SHIFT_FALLBACK and acted not in self._exact:
                shifted = perception.detect_shift(prev, frame, self._background)
                if shifted is not None:
                    _c, size, offset, anchor = shifted
                    self.moves.observe_translation(acted, offset, size, anchor, self.game_id)
        regions = perception.merge_enclosed(
            perception.connected_regions(frame, min_size=1), background=self._background)
        regions = [(c, cells) for c, cells in regions if len(cells) >= STAMINA_MIN_SIZE]
        expected = self.moves.learned_moves.get(acted) if acted is not None else None
        tracked = self.regions.update(regions, expected_offset=expected)
        self.stamina.update({rid: len(cells) for rid, (_c, cells) in tracked.items()}, self.game_id,
                            colours={rid: c for rid, (c, _s) in tracked.items()},
                            cells={rid: cells for rid, (_c, cells) in tracked.items()})
        if acted is not None:
            self.belief.update(tracked, acted.name, changed)
            self.relations.update(self.regions._tracked, self.regions.live, acted.name,
                                  skip=self._canvas_ids())
            self.brief.record(self, acted.name)


def replay(entries, game_id, leads):
    rp = Replay(game_id)
    prev = None; prev_level = None; prev_action = None
    snapshots, briefs, tallies_at = [], [], {}
    advances = []
    for i, e in enumerate(entries):
        frame = _frame(e)
        if frame is None:
            snapshots.append({}); briefs.append(""); prev_action = e["action"]; continue
        if prev_level is not None and e["levels_completed"] != prev_level:
            advances.append(i)
            tallies_at[i] = {k: {a: dict(t) for a, t in r.by_action.items()}
                             for k, r in rp.relations.records.items()}
            rp.reset_level(); prev = None
        prev_level = e["levels_completed"]
        acted = GameAction[prev_action] if prev_action and prev_action != "RESET" else None
        rp.step(prev, frame, acted, prev_action)
        snapshots.append(rp.relations.snapshot())
        briefs.append(rp.brief.compose(rp, level=e["levels_completed"],
                                       available=e.get("available_actions")) if acted else "")
        prev = frame; prev_action = e["action"]

    results = []
    for i in advances:
        lo = max(0, i - WINDOW); window = snapshots[lo:i]
        if len(window) < 3:
            continue
        # The (iii') keys: falling into the advance under a lever.
        keys = []
        for k in set().union(*(set(s) for s in window)):
            if k[0] in relations.EVIDENCE_ONLY or k[0] == "distance_drift" or not isinstance(k[1], int):
                continue
            series = [s.get(k) for s in window]
            if any(v is None for v in series):
                continue
            if all(x >= y for x, y in zip(series, series[1:])) and series[0] > series[-1]:
                rec = relations.PairRecord(); rec.by_action = tallies_at[i].get(k, {})
                if rec.lever(relations.DOWN) is not None:
                    keys.append(k)
        for lead in leads:
            t = i - lead
            if t < 0 or not briefs[t]:
                continue
            text = briefs[t]
            outcome = "absent" if not keys else "engine"
            where = None
            for rel, a, b in keys:
                sec = _section_of(text, rel, a, b)
                if sec == "FALLING":
                    outcome, where = "FALLING", (rel, a, b); break
                if sec == "RELATIONS" and outcome != "FALLING":
                    outcome, where = "RELATIONS", (rel, a, b)
            results.append(dict(game=game_id, frame=i, lead=lead, keys=len(keys), outcome=outcome, where=where))
    return results


def _section_of(text: str, rel: str, a: int, b: int) -> str | None:
    """Which brief section mentions relation `rel` between #a and #b."""
    current = None
    for line in text.splitlines():
        if line and not line.startswith(" "):
            current = line.split(" ")[0]
            continue
        if current in ("RELATIONS", "FALLING") and line.strip().startswith(rel + "("):
            ids = {int(x) for x in re.findall(r"#(\d+)", line)}
            if a in ids and b in ids:
                return current
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--lead", nargs=2, type=int, default=(3, 8), metavar=("MIN", "MAX"))
    args = ap.parse_args()
    leads = list(range(args.lead[0], args.lead[1] + 1))
    rows = []
    for d in args.dirs:
        for f in sorted(Path(d).glob("*.jsonl")):
            entries = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
            if not entries or not entries[-1].get("frame"):
                continue
            if not any(entries[k]["levels_completed"] != entries[k - 1]["levels_completed"] for k in range(1, len(entries))):
                continue                      # no advance: nothing to score
            rows.extend(replay(entries, f.stem, leads))
    if not rows:
        print("no advances found"); return
    print(f"{'game':6} {'frame':>6} {'lead':>5} {'levers':>7}  outcome     coordinate")
    for r in rows:
        w = f"{r['where'][0]}(#{r['where'][1]},#{r['where'][2]})" if r["where"] else ""
        print(f"{r['game']:6} {r['frame']:6} {r['lead']:5} {r['keys']:7}  {r['outcome']:10}  {w}")
    advances = {(r["game"], r["frame"]) for r in rows}
    print(f"\n=== recall over {len(advances)} advances x {len(leads)} leads ===")
    for o in ("FALLING", "RELATIONS", "engine", "absent"):
        n = sum(1 for r in rows if r["outcome"] == o)
        print(f"  {o:10} {n:4}  ({n / len(rows):.0%})")
    in_text = sum(1 for r in rows if r["outcome"] in ("FALLING", "RELATIONS"))
    # Per advance: best outcome across leads.
    rank = {"FALLING": 0, "RELATIONS": 1, "engine": 2, "absent": 3}
    best = {}
    for r in rows:
        k = (r["game"], r["frame"])
        if k not in best or rank[r["outcome"]] < rank[best[k]]:
            best[k] = r["outcome"]
    print(f"\n  in the text (any lead):  {sum(1 for v in best.values() if v in ('FALLING','RELATIONS'))}/{len(best)} advances   bar: a majority")
    print(f"  selection gap (engine only): {sum(1 for v in best.values() if v == 'engine')}   vocabulary gap (absent): {sum(1 for v in best.values() if v == 'absent')}")
    print(f"  row-level: {in_text}/{len(rows)} = {in_text / len(rows):.0%} of (advance, lead) pairs had the coordinate in the text")


if __name__ == "__main__":
    main()
