"""H009's closing experiment: does a SINGLE live episode's own exploration
build a usable position graph fast enough to matter?

H010 Stage 1 validated `PositionModel` + `plan_graph` against data pooled
from all ten recorded seeds — about 4,000 transitions. That proves the
model SHAPE is right; it says nothing about whether one real episode,
with its own action budget and nobody feeding it ten seeds of hindsight,
accumulates enough (position, action) coverage in time to route
correctly before the budget runs out. That is the one uncertainty left
before Stage 2 (wiring into the live router) is worth prioritizing, and
it is answerable without touching `my_agent.py` at all: play cd82 live
with the real, unmodified agent, and at each decision maintain a
`PositionModel` fed ONLY by what this one episode has actually seen so
far (not the pooled traces), then ask what `plan_graph` would have said
with only that much evidence, alongside what the live agent's own
`plan` (learned_moves) actually said.

No agent code is touched. `PositionModel.observe` is exactly the method
Stage 2 would call from `_learn_from`; this script calls it from a tap
instead, so the online-accumulation behaviour under test is identical to
what Stage 2 would produce, without shipping it.

Usage:
    .venv/bin/python scripts/h009_live_validation.py --seeds 1-10
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "agent"))

from arcengine import GameAction  # noqa: E402

import navigation  # noqa: E402
import relations  # noqa: E402
from control import PositionModel  # noqa: E402

BLOCK = 10
SIDE = "-x"
MOVE_ACTIONS = {GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3, GameAction.ACTION4}

# Checkpoints (in live decisions taken) at which coverage is reported —
# a real episode's own budget is ~200-400 actions total, most of them
# NOT movement, so this is finer-grained early where it matters.
CHECKPOINTS = (10, 25, 50, 100, 150, 200, 300, 400)


def _bucket_bbox(agent):
    for rid in agent._control_ids():
        if rid in agent.regions._tracked and len(agent.regions._tracked[rid][1]) < 200:
            _colour, cells = agent.regions._tracked[rid]
            xs = [c[0] for c in cells]; ys = [c[1] for c in cells]
            return rid, (min(xs), min(ys), max(xs), max(ys))
    return None, None


def _targets(agent, block_bbox):
    """Which currently-known bucket positions are -x-adjacent to the
    block — recomputed as new positions are seen, since a live episode
    does not know the full orbit up front."""
    out = set()
    for pos, bbox in agent._h009_bboxes.items():
        c = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        m = ((block_bbox[0] + block_bbox[2]) / 2, (block_bbox[1] + block_bbox[3]) / 2)
        if relations.bbox_gap(bbox, block_bbox) <= relations.ADJACENT_GAP and relations.side_of(c, m) == SIDE:
            out.add(pos)
    return out


def no_obstacle(position, action):
    return False


def run_seed(Cls, seed: int, max_steps: int) -> dict:
    VENDOR = ROOT / "vendor" / "ARC-AGI-3-Agents"
    import arc_agi
    from arc_agi import OperationMode

    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
    Cls.SEED = seed
    Cls.MAX_ACTIONS = max_steps
    env = arc.make("cd82")

    log: list[dict] = []

    class Tap(Cls):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._h009_pm = PositionModel()          # THIS episode's own evidence only
            self._h009_bboxes: dict = {}
            self._h009_prev_pos = None
            self._h009_decisions = 0
            self._h009_block_bbox = None

        def _select(self, latest_frame, candidates):
            rid, bbox = _bucket_bbox(self)
            if bbox is not None:
                pos = (bbox[0], bbox[1])
                self._h009_bboxes[pos] = bbox
                if self._h009_prev_pos is not None and self._last_action in MOVE_ACTIONS:
                    self._h009_pm.observe(self._h009_prev_pos, self._last_action, pos)
                self._h009_prev_pos = pos
            if BLOCK in self.regions.live and BLOCK in self.regions._tracked:
                self._h009_block_bbox = relations.Descriptor.of(*self.regions._tracked[BLOCK]).bbox

            self._h009_decisions += 1
            n = self._h009_decisions
            if n in CHECKPOINTS and bbox is not None and self._h009_block_bbox is not None:
                edges = self._h009_pm.edges
                targets = _targets(self, self._h009_block_bbox)
                pos = (bbox[0], bbox[1])
                graph_path = None
                if targets and pos not in targets:
                    cands = [p for p in (navigation.plan_graph(pos, t, edges, no_obstacle) for t in targets)
                             if p is not None]
                    graph_path = min(cands, key=len) if cands else None
                offset_path = None
                if self.moves.learned_moves and targets and pos not in targets:
                    cands = [p for p in (navigation.plan(pos, t, self.moves.learned_moves, no_obstacle)
                                         for t in targets) if p is not None]
                    offset_path = min(cands, key=len) if cands else None
                log.append({
                    "n": n, "edges": len(edges), "positions_seen": len(self._h009_bboxes),
                    "at_target": pos in targets, "graph_path": len(graph_path) if graph_path else None,
                    "offset_path": len(offset_path) if offset_path else None,
                })
            return super()._select(latest_frame, candidates)

    from play_local import load_my_agent_class  # noqa: E402 (re-import guard, harmless if cached)
    agent = Tap(card_id="h009-live", game_id="cd82", agent_name="h009.live",
                ROOT_URL="http://localhost", record=False, arc_env=env, tags=["h009-live"])
    agent.main()
    final_edges = agent._h009_pm.edges
    return {"seed": seed, "log": log, "final_edges": len(final_edges),
            "final_positions": len(agent._h009_bboxes)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1-10")
    ap.add_argument("--max-steps", type=int, default=400)
    args = ap.parse_args()
    lo, _, hi = args.seeds.partition("-")
    seeds = list(range(int(lo), int(hi or lo) + 1))

    sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))
    from play_local import load_my_agent_class
    Cls = load_my_agent_class()

    results = [run_seed(Cls, s, args.max_steps) for s in seeds]

    print(f"{'checkpoint (decisions)':>24}  " + "  ".join(f"seed{r['seed']:<3}" for r in results))
    for cp in CHECKPOINTS:
        row = []
        for r in results:
            entry = next((e for e in r["log"] if e["n"] == cp), None)
            if entry is None:
                row.append("   -  ")
            else:
                row.append(f"e{entry['edges']:<3}" + ("G" if entry["graph_path"] else ("g" if entry["at_target"] else "-")))
        print(f"{cp:>24}  " + "  ".join(row))
    print("\n(e<N> = admitted edges at that point; G = plan_graph found a route; "
          "g = already at a target; - = plan_graph found nothing yet)")

    print(f"\n{'seed':>6} {'final edges':>12} {'final positions':>16} {'ceiling (all 8 pos x 4 act)':>28}")
    for r in results:
        print(f"{r['seed']:>6} {r['final_edges']:>12} {r['final_positions']:>16} {'32':>28}")

    # How often, across every checkpoint where a target was known and the
    # bucket was off it, did the LIVE-BUILT graph vs the offset model find
    # an honoured route (graph paths are honoured by construction; the
    # offset model's honoured rate is H009's own finding: 0%).
    checked = graph_found = offset_found = 0
    for r in results:
        for e in r["log"]:
            if e["at_target"]:
                continue
            checked += 1
            graph_found += e["graph_path"] is not None
            offset_found += e["offset_path"] is not None
    print(f"\nAcross all checkpoints where off-target with a known target ({checked} of them):")
    print(f"  live-built position graph finds a route: {graph_found}/{checked}")
    print(f"  live offset model (plan) finds A path:    {offset_found}/{checked}  "
          f"(H009: honoured at 0% regardless of whether one is found)")
    print("\nby checkpoint, seeds with EITHER a usable live-built route OR already at target:")
    for cp in CHECKPOINTS:
        ok = sum(1 for r in results
                 for e in r["log"] if e["n"] == cp and (e["graph_path"] is not None or e["at_target"]))
        print(f"  decision {cp:>4}: {ok}/{len(results)}")


if __name__ == "__main__":
    main()
