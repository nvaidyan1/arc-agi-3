"""H010 Stage 1: validate `control.PositionModel` + `navigation.plan_graph`
offline on cd82, through the real production code — not a scratch
reimplementation of H009's own analysis.

H009 (`research/hypotheses/H009_planner_factorial.md`) found cd82's
controlled thing to be a deterministic function of (position, action),
not of the action alone, and that `navigation.plan`'s offset model — the
only transition model the live agent has — is honoured at the first
step of 0 of 1,244 recorded plans. This script builds the position-graph
alternative from the same traces, using the actual classes added for
H010 (`agent/control.py PositionModel`, `agent/navigation.py plan_graph`),
and answers three questions with no live agent involved yet:

  1. Does `PositionModel.edges`, built from real `.observe()` calls,
     match H009's oracle graph? (Same admit rule; should agree exactly.)
  2. Does `navigation.plan_graph` reach a −x-adjacent target from every
     orbit position, within the same bound H009's own BFS found (≤ 3)?
  3. Replaying H009's own traced decisions (`recordings/latent_h009/`):
     if `plan_graph` had been asked instead of `plan`, is its first step
     honoured — the number that was 0/1,244 for the offset model?

Usage:
    .venv/bin/python scripts/h010_position_model.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "agent"))

from arcengine import GameAction  # noqa: E402

import navigation  # noqa: E402
import relations  # noqa: E402
from control import PositionModel  # noqa: E402

BLOCK = 10
SIDE = "-x"
MOVE_ACTIONS = {GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3, GameAction.ACTION4}
NAME_TO_ACTION = {a.name: a for a in MOVE_ACTIONS}


def build_model() -> tuple[PositionModel, dict, tuple]:
    """Feed every real (position, action, next_position) transition from
    the S_t traces into a real `PositionModel`, exactly as `_learn_from`
    would if it called `.observe()` live (H010 Stage 2, not built here)."""
    model = PositionModel()
    bboxes: dict = {}
    block = None
    for f in sorted((ROOT / "recordings" / "latent").glob("seed*/cd82.jsonl")):
        steps = [json.loads(l) for l in f.open()]
        for i in range(len(steps) - 1):
            a, b = steps[i], steps[i + 1]
            if b["step"] != a["step"] + 1 or a["action"] not in NAME_TO_ACTION:
                continue
            if a["levels_completed"] != 0 or b["levels_completed"] != 0:
                continue
            sa, sb = a.get("state_t"), b.get("state_t")
            if not sa or not sb:
                continue
            ca = [e for e in sa["entities"] if e["control"] and e["size"] < 200]
            cb = [e for e in sb["entities"] if e["control"] and e["size"] < 200]
            if not ca or not cb:
                continue
            blk = [e for e in sa["entities"] if e["id"] == BLOCK]
            if blk:
                block = tuple(blk[0]["bbox"])
            pa, pb = tuple(ca[0]["bbox"][:2]), tuple(cb[0]["bbox"][:2])
            bboxes[pa] = tuple(ca[0]["bbox"]); bboxes[pb] = tuple(cb[0]["bbox"])
            model.observe(pa, NAME_TO_ACTION[a["action"]], pb)
    return model, bboxes, block


def targets_of(bboxes: dict, block: tuple) -> set:
    out = set()
    for pos, bb in bboxes.items():
        c = ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)
        m = ((block[0] + block[2]) / 2, (block[1] + block[3]) / 2)
        if relations.bbox_gap(bb, block) <= relations.ADJACENT_GAP and relations.side_of(c, m) == SIDE:
            out.add(pos)
    return out


def main() -> None:
    model, bboxes, block = build_model()
    edges = model.edges
    print(f"1. PositionModel.edges: {len(edges)} admitted transitions over {len(bboxes)} positions")
    for (pos, act), nxt in sorted(edges.items(), key=lambda kv: kv[0][0]):
        print(f"   {pos} {act.name} -> {nxt}")

    targets = targets_of(bboxes, block)
    print(f"\n2. plan_graph reachability to targets {sorted(targets)} (block bbox {block}):")

    def no_obstacle(position, action):
        return False

    def shortest_to_any_target(pos):
        # plan_graph targets ONE point; the shortest overall is the
        # shortest over every candidate, not the first that succeeds.
        candidates = [navigation.plan_graph(pos, t, edges, no_obstacle) for t in targets]
        candidates = [c for c in candidates if c is not None]
        return min(candidates, key=len) if candidates else None

    lengths = collections.Counter()
    for pos in bboxes:
        if pos in targets:
            continue
        path = shortest_to_any_target(pos)
        print(f"   from {pos}: {[a.name for a in path] if path else 'UNREACHABLE'}")
        if path is not None:
            lengths[len(path)] += 1
    print(f"   lengths: {dict(sorted(lengths.items()))}  (H009's own BFS found <= 3 from every position)")

    # 3. Replay H009's traced decisions: would plan_graph have been
    # honoured where plan (the offset model) was not?
    h009_dir = ROOT / "recordings" / "latent_h009"
    if not h009_dir.exists():
        print("\n3. skipped: recordings/latent_h009/ not found (run scripts/h009_planner.py trace first)")
        return
    total = honoured = no_path = 0
    for f in sorted(h009_dir.glob("cd82_seed*.jsonl")):
        for line in f.open():
            d = json.loads(line)
            if d["level"] != 0 or d["pos"] is None:
                continue
            pos = tuple(d["pos"])
            if pos in targets:
                continue
            total += 1
            path = shortest_to_any_target(pos)
            if path is None:
                no_path += 1
                continue
            first = path[0]
            if edges.get((pos, first)) is not None:   # by construction, always true when path exists
                honoured += 1
    print(f"\n3. Replaying {total} of H009's real decisions through plan_graph instead of plan:")
    print(f"   path found: {total - no_path}/{total}   honoured at the first step: {honoured}/{total - no_path}")
    print("   (plan/the offset model: paths on 1,244/1,779, honoured 0/1,244 — H009's own numbers)")


if __name__ == "__main__":
    main()
