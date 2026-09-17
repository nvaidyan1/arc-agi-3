"""H011 Stage 2: pick `CLICK_NOVELTY_WEIGHT` from a live sweep, not a guess.

Plays cd82 live with the real, unmodified agent (the change already
lives in `agent/attention.py`) at several candidate weights, and reports
two things per weight: how often the swatch strip actually gets clicked,
and whether the strip's own recolour-selection mechanic still gets
exercised (a rough proxy that the blend isn't just spraying clicks
everywhere at the cost of the productive action zone). No score claim —
this is about the click-targeting mechanism only.

Usage:
    .venv/bin/python scripts/h011_weight_sweep.py --seeds 1-5 --weights 0,0.5,1,2,4
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

STRIP_BBOX = (18, 0, 63, 8)


def in_strip(x: int, y: int) -> bool:
    x0, y0, x1, y1 = STRIP_BBOX
    return x0 <= x <= x1 and y0 <= y <= y1


def run(weight: float, seeds: list[int], max_steps: int) -> dict:
    import constants
    constants.CLICK_NOVELTY_WEIGHT = weight
    import attention
    attention.CLICK_NOVELTY_WEIGHT = weight   # already imported by name into the module

    VENDOR = ROOT / "vendor" / "ARC-AGI-3-Agents"
    sys.path.insert(0, str(VENDOR))
    import arc_agi
    from arc_agi import OperationMode
    from play_local import load_my_agent_class

    Cls = load_my_agent_class()
    Cls.MAX_ACTIONS = max_steps
    totals = collections.Counter()
    for seed in seeds:
        arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
        Cls.SEED = seed
        env = arc.make("cd82")
        agent = Cls(card_id="h011-sweep", game_id="cd82", agent_name="h011.sweep",
                    ROOT_URL="http://localhost", record=False, arc_env=env, tags=["h011-sweep"])

        clicks = collections.Counter()
        by_region: collections.Counter = collections.Counter()

        def observe_click(cell, changed, _orig=agent.clicks.observe_click):
            clicks["total"] += 1
            if in_strip(*cell):
                clicks["strip"] += 1
            by_region[(cell[0] // 8, cell[1] // 8)] += 1
            return _orig(cell, changed)

        agent.clicks.observe_click = observe_click
        agent.main()
        totals["total_clicks"] += clicks["total"]
        totals["strip_clicks"] += clicks["strip"]
        totals["steps"] += agent.action_counter
        totals["seeds"] += 1
        if by_region:
            totals["hottest_region_clicks"] += by_region.most_common(1)[0][1]
    return dict(totals)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1-5")
    ap.add_argument("--weights", default="0,0.5,1,2,4")
    ap.add_argument("--max-steps", type=int, default=400)
    args = ap.parse_args()
    lo, _, hi = args.seeds.partition("-")
    seeds = list(range(int(lo), int(hi or lo) + 1))
    weights = [float(w) for w in args.weights.split(",")]

    print(f"{'weight':>8} {'steps':>7} {'clicks':>7} {'strip':>7} {'strip%':>8} "
          f"{'hottest8x8':>11} {'hottest%':>9}")
    for w in weights:
        r = run(w, seeds, args.max_steps)
        total = max(r.get("total_clicks", 0), 1)
        pct = 100 * r.get("strip_clicks", 0) / total
        hot = r.get("hottest_region_clicks", 0)
        hot_pct = 100 * hot / total
        print(f"{w:>8} {r.get('steps', 0):>7} {r.get('total_clicks', 0):>7} "
              f"{r.get('strip_clicks', 0):>7} {pct:>7.2f}% {hot:>11} {hot_pct:>8.2f}%")


if __name__ == "__main__":
    main()
