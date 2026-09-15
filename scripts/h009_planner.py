"""H009: the planner factorial on cd82, E1 and E3.

E0 and E2 come free from the S_t traces (`research/hypotheses/
H009_planner_factorial.md`): the bucket's motion is a deterministic
function of (position, action) — eight orbit positions, 32 of 32
contexts deterministic across ten seeds — and a −x-adjacent position of
the block is reachable from every position in at most three actions
through that empirical graph. E1 asks what the agent's OWN planner does
with the same task, with its own move map, at every step of a real run:

    trace    play cd82 with the real agent, and at each decision compute
             the full path `_route_to(block, side="-x")` would follow —
             the same pixel math, the same `navigation.plan`, the same
             learned moves and obstacle map — and record it with the
             bucket's position and the move map as they stood.
    analyse  validate every recorded plan through the empirical position
             graph T_oracle (built from the same traces): does the path's
             first action move the bucket where the planner's offset says,
             and does following it end at a −x-adjacent position?

Readings (per the H009 doc): E2 path AND E1 honoured -> A; E2 path AND E1
none-or-not-honoured -> B (the model class, one offset per action, is
insufficient); E2 none -> C.

Usage:
    .venv/bin/python scripts/h009_planner.py trace --seeds 1-10
    .venv/bin/python scripts/h009_planner.py analyse
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "agent"))

OUT = ROOT / "recordings" / "latent_h009"
BLOCK = 10           # cd82 level 0: the block the bucket orbits
SIDE = "-x"
MOVE_ACTIONS = ("ACTION1", "ACTION2", "ACTION3", "ACTION4")


# ── trace ───────────────────────────────────────────────────────────────

def _planned_path(agent, target_id: int, candidates, side: str):
    """`MyAgent._route_to`'s exact target math and planner call, returning
    the whole path (the agent keeps only the first step)."""
    import navigation
    import relations
    pixel = agent.belief._beliefs[target_id].centroid if target_id in agent.belief._beliefs else None
    if pixel is None:
        return None, "no centroid"
    if side and target_id in agent.regions._tracked:
        md = relations.Descriptor.of(*agent.regions._tracked[target_id])
        half_m = ((md.bbox[2] - md.bbox[0]) // 2 + 1, (md.bbox[3] - md.bbox[1]) // 2 + 1)
        half_c = (agent.moves.controlled_size ** 0.5) // 2 + 1
        axis, sign = (0, -1) if side == "-x" else (0, 1) if side == "+x" else (1, -1) if side == "-y" else (1, 1)
        pixel = list(pixel); pixel[axis] += sign * int(half_m[axis] + half_c); pixel = tuple(pixel)
    target = agent.moves.to_relative(pixel) if pixel is not None else None
    if target is None:
        return None, "no anchor (to_relative is None)"
    if not agent.moves.learned_moves:
        return None, "no learned moves"
    moves = {act: off for act, off in agent.moves.learned_moves.items() if act in candidates}
    path = navigation.plan(agent.moves.displacement, target, moves, agent.obstacles.is_blocked)
    if not path:
        return None, "plan returned None"
    return [a.name for a in path], f"target_rel={target} pixel={pixel}"


def trace(seeds: list[int], max_steps: int) -> None:
    VENDOR = ROOT / "vendor" / "ARC-AGI-3-Agents"
    sys.path.insert(0, str(VENDOR))
    import arc_agi
    from arc_agi import OperationMode
    from play_local import load_my_agent_class

    OUT.mkdir(parents=True, exist_ok=True)
    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
    Cls = load_my_agent_class()
    Cls.MAX_ACTIONS = max_steps
    for seed in seeds:
        Cls.SEED = seed
        out = OUT / f"cd82_seed{seed}.jsonl"
        fh = out.open("w")

        class Tap(Cls):
            def _select(self, latest_frame, candidates):
                bucket = [rid for rid in self._control_ids()
                          if rid in self.regions._tracked and len(self.regions._tracked[rid][1]) < 200]
                pos = None
                if bucket:
                    cells = self.regions._tracked[bucket[0]][1]
                    pos = [min(c[0] for c in cells), min(c[1] for c in cells)]
                path, why = (None, "block not live")
                if BLOCK in self.regions.live:
                    path, why = _planned_path(self, BLOCK, candidates, SIDE)
                fh.write(json.dumps({
                    "step": len(self.frames), "level": latest_frame.levels_completed,
                    "pos": pos, "path": path, "why": why,
                    "learned_moves": {a.name: list(o) for a, o in self.moves.learned_moves.items()},
                    "displacement": list(self.moves.displacement),
                    "controlled_size": self.moves.controlled_size,
                }) + "\n")
                return super()._select(latest_frame, candidates)

        env = arc.make("cd82")
        agent = Tap(card_id="h009", game_id="cd82", agent_name="h009.cd82", ROOT_URL="http://localhost",
                    record=False, arc_env=env, tags=["h009"])
        agent.main()
        fh.close()
        print(f"seed {seed}: {sum(1 for _ in out.open())} decisions -> {out}")


# ── analyse ─────────────────────────────────────────────────────────────

def _oracle_graph():
    """T_oracle from the S_t traces: (pos, action) -> majority successor,
    plus the −x-adjacent target positions. Level 0 only."""
    import relations
    T = collections.defaultdict(collections.Counter)
    bboxes, block = {}, None
    for f in sorted((ROOT / "recordings" / "latent").glob("seed*/cd82.jsonl")):
        steps = [json.loads(l) for l in f.open()]
        for i in range(len(steps) - 1):
            a, b = steps[i], steps[i + 1]
            if b["step"] != a["step"] + 1 or a["action"] not in MOVE_ACTIONS:
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
            T[(pa, a["action"])][pb] += 1
    succ = collections.defaultdict(dict)
    for (pos, act), c in T.items():
        if sum(c.values()) >= 2:
            succ[pos][act] = c.most_common(1)[0][0]

    def is_target(pos):
        bb = bboxes[pos]
        c = ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)
        m = ((block[0] + block[2]) / 2, (block[1] + block[3]) / 2)
        return relations.bbox_gap(bb, block) <= relations.ADJACENT_GAP and relations.side_of(c, m) == SIDE
    targets = {p for p in bboxes if is_target(p)}
    return succ, targets


def _bfs(succ, targets, start):
    q = collections.deque([(start, [])]); seen = {start}
    while q:
        p, path = q.popleft()
        if p in targets:
            return path
        for act, nxt in succ[p].items():
            if nxt not in seen:
                seen.add(nxt); q.append((nxt, path + [act]))
    return None


def analyse() -> None:
    succ, targets = _oracle_graph()
    print(f"T_oracle: {len(succ)} positions, targets (adjacent {SIDE} of #{BLOCK}): {sorted(targets)}")
    c = collections.Counter()
    why = collections.Counter()
    lengths = collections.Counter()
    first_div = collections.Counter()
    for f in sorted(OUT.glob("cd82_seed*.jsonl")):
        for line in f.open():
            d = json.loads(line)
            if d["level"] != 0 or d["pos"] is None:
                continue
            pos = tuple(d["pos"])
            if pos in targets:
                c["already_at_target"] += 1
                continue
            if pos not in succ:
                c["pos_unknown_to_oracle"] += 1
                continue
            c["decisions"] += 1
            e2 = _bfs(succ, targets, pos)
            c["e2_reachable"] += e2 is not None
            if d["path"] is None:
                c["e1_no_path"] += 1
                why[d["why"]] += 1
                continue
            c["e1_path"] += 1
            lengths[len(d["path"])] += 1
            # honour the plan step by step through the oracle graph
            p, ok, div = pos, True, None
            lm = {a: tuple(o) for a, o in d["learned_moves"].items()}
            for j, act in enumerate(d["path"]):
                nxt = succ[p].get(act)
                if nxt is None:
                    ok, div = False, (j, "no oracle edge"); break
                expected = (p[0] + lm[act][0], p[1] + lm[act][1])
                if nxt != expected:
                    ok, div = False, (j, "offset not honoured"); break
                p = nxt
            if ok and p in targets:
                c["e1_honoured_and_arrives"] += 1
            elif ok:
                c["e1_honoured_but_misses_target"] += 1
            else:
                c["e1_not_honoured"] += 1
                first_div[div] += 1
            # The fairer question: never mind the offsets — if the agent
            # simply FOLLOWED this plan, where would the dynamics put it?
            q = pos
            for act in d["path"]:
                q = succ[q].get(act, q)
            c["e1_followed_arrives"] += q in targets
            c["e1_followed_passes_target"] += 0
            q, passed = pos, False
            for act in d["path"]:
                q = succ[q].get(act, q)
                passed = passed or q in targets
            c["e1_followed_passes_target"] += passed
    n = c["decisions"]
    print(f"\ndecisions off-target with a known position: {n}  (already at target: {c['already_at_target']})")
    print(f"E2  oracle graph reaches a target:            {c['e2_reachable']}/{n}")
    print(f"E1  planner returned a path:                  {c['e1_path']}/{n}   (no path: {c['e1_no_path']}; reasons {dict(why)})")
    print(f"    ...honoured by the dynamics and arriving: {c['e1_honoured_and_arrives']}/{max(c['e1_path'], 1)}")
    print(f"    ...honoured but ending off-target:        {c['e1_honoured_but_misses_target']}")
    print(f"    ...not honoured (first divergence):       {c['e1_not_honoured']}  {dict(first_div)}")
    print(f"    followed blindly through the dynamics — ends at a target: {c['e1_followed_arrives']}/{max(c['e1_path'], 1)}; "
          f"passes through one: {c['e1_followed_passes_target']}/{max(c['e1_path'], 1)}")
    print(f"    planned lengths: {dict(sorted(lengths.items()))}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trace")
    t.add_argument("--seeds", default="1-10")
    t.add_argument("--max-steps", type=int, default=400)
    sub.add_parser("analyse")
    args = ap.parse_args()
    if args.cmd == "trace":
        lo, _, hi = args.seeds.partition("-")
        seeds = list(range(int(lo), int(hi or lo) + 1))
        trace(seeds, args.max_steps)
    else:
        analyse()


if __name__ == "__main__":
    main()
