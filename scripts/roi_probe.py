"""Screening measurement for the region-of-interest question.

Does NOT change or depend on the incentive-salience map built into
`agent/my_agent.py` (`_interest` / `INTEREST_*`) — it subclasses `MyAgent`
and taps two methods to record what they compute internally but don't
expose, so the two questions this answers are prior to and independent of
that feature:

  _residual_cells  -> the POSITIONS of "changed, and explained by neither
                      self nor the budget meter" (the agent itself only
                      keeps a per-action count of this)
  _track_stamina     -> per-cell change counts + vanish positions, derived
                      the same way the agent's own vanish detector is

Three questions, see docs/history.md (2026-09-13, "Region-of-interest
screening") for the full write-up:

  Q1 do residual/vanish sites CLUSTER, or are they diffuse? (if diffuse, a
     map of them carries no more information than "somewhere on the
     board")
  Q2 does the answer differ between the two game families -- games where a
     move map forms (navigational) vs games where it never does
     (constructive/matching)?
  Q3 is there a persistent non-background region that NEVER changes while
     other regions churn? That is the template/specification signature
     (e.g. "copy the shape on the left"), with no left/right or mirroring
     assumed.

Stats used:
  Clark-Evans nearest-neighbour index R = observed mean NN distance /
  expected under CSR (0.5*sqrt(A/n)). R<1 clustered, ~1 random, >1
  dispersed.
  Half-mass = how many distinct cells account for 50% of all hits.

Usage:
    .venv/bin/python scripts/roi_probe.py
    .venv/bin/python scripts/roi_probe.py --game ls20,sp80 --max-steps 400
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import math
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VENDOR = ROOT / "vendor" / "ARC-AGI-3-Agents"
if not VENDOR.exists():
    raise SystemExit(f"Framework not found at {VENDOR}. Run `make setup` first.")
sys.path.insert(0, str(VENDOR))

import arc_agi
from arc_agi import OperationMode

NN_SAMPLE_CAP = 600  # Clark-Evans is O(n^2); subsample above this


def load_my_agent_class():
    spec = importlib.util.spec_from_file_location(
        "user_agent_module", ROOT / "agent" / "my_agent.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit("Could not load agent/my_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "MyAgent"):
        raise SystemExit("agent/my_agent.py must define a class named `MyAgent`")
    return module.MyAgent


def make_probe_class(MyAgentCls):
    class Probe(MyAgentCls):
        """MyAgent, instrumented to keep positions it normally discards."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.p_residual = Counter()   # (x,y) -> times in a residual
            self.p_vanish = Counter()     # (x,y) -> times part of a vanish
            self.p_changes = Counter()    # (x,y) -> times the cell changed
            self.p_steps = 0
            self.p_residual_steps = 0
            self.p_vanish_steps = 0
            self._p_prev_grid = None
            self._p_final_grid = None

        def _residual_cells(self, prev_frame, latest_frame, diff_cells, offset):
            cells = super()._residual_cells(
                prev_frame, latest_frame, diff_cells, offset
            )
            if cells:
                self.p_residual_steps += 1
                for c in cells:
                    self.p_residual[c] += 1
            return cells

        def _track_stamina(self, latest_frame):
            prev = self._p_prev_grid
            super()._track_stamina(latest_frame)
            if not latest_frame.frame:
                return
            grid = latest_frame.frame[-1]
            self._p_final_grid = grid
            self.p_steps += 1

            if prev is not None:
                changed = []
                prev_counts, now_counts = Counter(), Counter()
                for y, (pr, lr) in enumerate(zip(prev, grid)):
                    for x, (pv, lv) in enumerate(zip(pr, lr)):
                        prev_counts[pv] += 1
                        now_counts[lv] += 1
                        if pv != lv:
                            self.p_changes[(x, y)] += 1
                            changed.append((x, y, pv))
                # Vanish positions: cells that lost a colour whose total
                # count dropped by more than the agent's own self-occlusion
                # floor. Independent re-derivation for measurement purposes
                # only — the agent's own discriminator (in _track_stamina)
                # additionally requires the drop be absorbed by the
                # background; this probe's job is to characterize the
                # rawer signal, not to reproduce the production gate.
                if self._pending_vanish:
                    floor = max(self._controlled_size, 8)
                    meter = self.stamina_colour
                    dropped = {
                        c for c in prev_counts
                        if c != meter and prev_counts[c] - now_counts[c] > floor
                    }
                    hit = False
                    for x, y, pv in changed:
                        if pv in dropped:
                            self.p_vanish[(x, y)] += 1
                            hit = True
                    if hit:
                        self.p_vanish_steps += 1

            self._p_prev_grid = [row[:] for row in grid]

    return Probe


def clark_evans(cells: Counter) -> float | None:
    n = len(cells)
    if n < 2:
        return None
    pts = list(cells)
    if n > NN_SAMPLE_CAP:
        pts = random.sample(pts, NN_SAMPLE_CAP)
        n = NN_SAMPLE_CAP
    total = 0.0
    for i, (x1, y1) in enumerate(pts):
        best = float("inf")
        for j, (x2, y2) in enumerate(pts):
            if i != j:
                d = math.hypot(x1 - x2, y1 - y2)
                if d < best:
                    best = d
        total += best
    expected = 0.5 * math.sqrt((64 * 64) / n)
    return (total / n) / expected


def half_mass(counter: Counter) -> int | None:
    if not counter:
        return None
    total = sum(counter.values())
    acc = k = 0
    for _, v in counter.most_common():
        acc += v
        k += 1
        if acc >= total / 2:
            break
    return k


def bbox(cells):
    if not cells:
        return None
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return min(xs), min(ys), max(xs), max(ys)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--game", default=None,
                   help="Comma-separated game id(s). Default: all local games.")
    p.add_argument("--max-steps", type=int, default=400,
                   help="Per-game action budget (default 400, matching "
                        "MyAgent.MAX_ACTIONS).")
    args = p.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
    all_envs = arc.get_environments()
    if args.game:
        wanted = {g.strip().split("-")[0] for g in args.game.split(",")}
        game_ids = [e.game_id.split("-")[0] for e in all_envs
                    if e.game_id.split("-")[0] in wanted]
    else:
        game_ids = [e.game_id.split("-")[0] for e in all_envs]

    MyAgentCls = load_my_agent_class()
    MyAgentCls.MAX_ACTIONS = args.max_steps
    Probe = make_probe_class(MyAgentCls)

    rows = []
    for i, gid in enumerate(game_ids, 1):
        print(f"[{i}/{len(game_ids)}] {gid}", file=sys.stderr, flush=True)
        env = arc.make(gid, render_mode=None)
        if env is None:
            continue
        agent = Probe(card_id="roi-probe", game_id=gid,
                      agent_name=f"Probe.{gid}", ROOT_URL="http://localhost",
                      record=False, arc_env=env, tags=["roi-probe"])
        try:
            agent.main()
        except Exception as exc:  # keep the sweep going
            print(f"  {gid} raised {exc!r}", file=sys.stderr)
            continue

        moves = agent.learned_moves
        steps = max(agent.p_steps, 1)

        # Q3: static non-background structure vs the cells that ever change.
        static_out = None
        static_n = dyn_n = 0
        if agent._p_final_grid:
            grid = agent._p_final_grid
            counts = Counter(v for row in grid for v in row)
            background = counts.most_common(1)[0][0]
            dynamic = set(agent.p_changes)
            static_salient = {
                (x, y)
                for y, row in enumerate(grid)
                for x, v in enumerate(row)
                if v != background and (x, y) not in dynamic
            }
            static_n, dyn_n = len(static_salient), len(dynamic)
            db = bbox(dynamic)
            if static_salient and db:
                x0, y0, x1, y1 = db
                outside = sum(
                    1 for x, y in static_salient
                    if not (x0 <= x <= x1 and y0 <= y <= y1)
                )
                static_out = outside / len(static_salient)

        rows.append({
            "game": gid,
            "moves": len(moves),
            "steps": agent.p_steps,
            "levels": agent.frames[-1].levels_completed if agent.frames else 0,
            "res_pct": 100.0 * agent.p_residual_steps / steps,
            "res_cells": len(agent.p_residual),
            "res_half": half_mass(agent.p_residual),
            "res_R": clark_evans(agent.p_residual),
            "van_pct": 100.0 * agent.p_vanish_steps / steps,
            "van_cells": len(agent.p_vanish),
            "van_R": clark_evans(agent.p_vanish),
            "static_n": static_n,
            "dyn_n": dyn_n,
            "static_out": static_out,
        })

    def fmt(v, spec=".2f"):
        return "  -  " if v is None else format(v, spec)

    print("\n=== PER GAME (budget %d) ===" % args.max_steps)
    hdr = (f"{'game':6} {'mv':>2} {'lvl':>3} {'res%':>6} {'rcells':>6} "
           f"{'rhalf':>5} {'R_res':>6} {'van%':>5} {'vcells':>6} {'R_van':>6} "
           f"{'static':>6} {'dyn':>5} {'out%':>5}")
    print(hdr)
    for r in rows:
        print(f"{r['game']:6} {r['moves']:>2} {r['levels']:>3} "
              f"{r['res_pct']:>6.1f} {r['res_cells']:>6} "
              f"{(r['res_half'] if r['res_half'] else '-'):>5} "
              f"{fmt(r['res_R']):>6} {r['van_pct']:>5.1f} {r['van_cells']:>6} "
              f"{fmt(r['van_R']):>6} {r['static_n']:>6} {r['dyn_n']:>5} "
              f"{fmt(r['static_out'] and r['static_out'] * 100, '.0f'):>5}")

    nav = [r for r in rows if r["moves"] > 0]
    con = [r for r in rows if r["moves"] == 0]

    def summarize(label, group):
        if not group:
            print(f"\n{label}: none")
            return
        rs = [r["res_R"] for r in group if r["res_R"] is not None]
        vs = [r["van_R"] for r in group if r["van_R"] is not None]
        outs = [r["static_out"] for r in group if r["static_out"] is not None]
        print(f"\n{label}  (n={len(group)}: {', '.join(r['game'] for r in group)})")
        print(f"  residual fires on {sum(r['res_pct'] for r in group)/len(group):.1f}% "
              f"of steps; distinct cells median "
              f"{sorted(r['res_cells'] for r in group)[len(group)//2]}")
        if rs:
            print(f"  Clark-Evans R (residual): mean {sum(rs)/len(rs):.2f}, "
                  f"min {min(rs):.2f}, max {max(rs):.2f}  [<1 = clustered]")
        if vs:
            print(f"  Clark-Evans R (vanish):   mean {sum(vs)/len(vs):.2f}")
        if outs:
            print(f"  static salient cells outside the dynamic bbox: mean "
                  f"{100*sum(outs)/len(outs):.0f}%")
        print(f"  static/dynamic cell counts: "
              f"{sum(r['static_n'] for r in group)//len(group)} static, "
              f"{sum(r['dyn_n'] for r in group)//len(group)} dynamic")

    summarize("NAVIGATIONAL family (move map formed)", nav)
    summarize("CONSTRUCTIVE family (no move map)", con)


if __name__ == "__main__":
    main()
