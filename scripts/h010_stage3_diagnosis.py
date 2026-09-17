"""H010 Stage 3 (gate 1): WHY does the cd82 two-condition oracle still expire
unmet, now that the position graph is wired?

H010 Stage 2 shipped the position-graph router and proved the mechanism
(routes persist, no crashes, parity held). But the oracle it was meant to
close still expired unmet on seeds 1 and 3, and Stage 2 recorded the reason
as "graph coverage incompleteness at the exact moment the oracle needs it --
not chased further". That undetermined diagnosis is a confound: it blocks any
claim that navigation is no longer the bottleneck.

This chases it. It runs the H007 oracle unchanged and taps the routing path,
recording at every step the bet is LIVE:

    pos             the controlled thing's displacement now
    target          the displacement `_route_to` computed for `adjacent:-x`
    edges_from_pos  how many position-graph edges leave `pos`
    graph_path      what plan_graph returned (H010's model)
    offset_path     what plan returned  (the pre-H010 offset model)
    used            which one `_plan_route` actually returned
    action/tier     what the agent then did
    adj/state       each condition's own met-ness this step

The four readings the plan fixes in advance:
    A  no path from either model, repeatedly     -> COVERAGE  (H012's mandate)
    B  a path exists and is followed to arrival, -> TARGET    (goal/state
       yet adjacency never becomes met              representation)
    C  a path exists but another tier takes the  -> SELECTION (planner /
       decision                                     lever formation)
    D  none of the above                         -> investigate the model

Usage:
    .venv/bin/python scripts/h010_stage3_diagnosis.py --seed 1
    .venv/bin/python scripts/h010_stage3_diagnosis.py --seed 1 --seed 3 --json out.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import h007_cd82_oracle as oracle  # noqa: E402  (sets sys.path + ARC_PROPOSER)
import hypothesis as _hypothesis  # noqa: E402
import navigation  # noqa: E402


def instrument(agent, trace: list, state: dict):
    """Tap `_plan_route` and `_precondition_met`; record only while LIVE."""
    real_plan_route = agent._plan_route
    real_precond = agent._precondition_met

    def plan_route(target, candidates):
        pos = agent.moves.displacement
        edges = {k: v for k, v in agent.position_model.edges.items() if k[1] in candidates}
        from_pos = {k: v for k, v in edges.items() if k[0] == pos}
        graph_path = navigation.plan_graph(pos, target, edges, agent.obstacles.is_blocked) if edges else None
        moves = {a: o for a, o in agent.moves.learned_moves.items() if a in candidates}
        offset_path = navigation.plan(pos, target, moves, agent.obstacles.is_blocked) if moves else None
        used = real_plan_route(target, candidates)
        state["last"] = {
            "pos": list(pos) if pos else None,
            "target": list(target) if target else None,
            "edges_total": len(edges),
            "edges_from_pos": len(from_pos),
            "graph_path": [a.name for a in graph_path] if graph_path else None,
            "offset_path": [a.name for a in offset_path] if offset_path else None,
            "used": [a.name for a in used] if used else None,
        }
        return used

    def precondition_met(h):
        met = real_precond(h)
        if h is not None and getattr(h, "precondition", None):
            # `precondition` is EITHER a single (cond, member) pair OR a
            # tuple of them; `hypothesis.conditions_of()` is the canonical
            # normalizer the agent itself uses. `_condition_met(cond, member)`
            # takes the two parts separately. Both verified in agent/ first.
            per = {}
            for cond, member in _hypothesis.conditions_of(h.precondition):
                try:
                    per[str(cond)] = bool(agent._condition_met(cond, member))
                except Exception as exc:      # keep the run alive; record the gap
                    per[str(cond)] = f"error: {exc.__class__.__name__}"
            state["conds"] = per
        return met

    agent._plan_route = plan_route
    agent._precondition_met = precondition_met


def run_seed(seed: int, max_steps: int) -> dict:
    trace: list = []
    state: dict = {"last": None, "conds": None}
    real_run = oracle.run

    # Re-implement oracle.run's tail so we can tap the agent it builds, without
    # editing the oracle itself (it is the shipped, already-cited harness).
    import arc_agi
    from arc_agi import OperationMode
    from play_local import load_my_agent_class

    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
    Cls = load_my_agent_class()
    Cls.MAX_ACTIONS = max_steps
    Cls.SEED = seed
    env = arc.make("cd82")
    agent = Cls(card_id="h010-s3", game_id="cd82", agent_name="h010.s3",
                ROOT_URL="http://localhost", record=False, arc_env=env, tags=["h010-stage3"])

    st = {"calls": 0, "k0": None, "tokens": [], "h": None, "acted": 0}
    real_choose = agent.choose_action
    instrument(agent, trace, state)

    def strip_token():
        import relations as _relations
        if oracle.STRIP in agent.regions.live and oracle.STRIP in agent.regions._tracked:
            return _relations.state_key(*agent.regions._tracked[oracle.STRIP])
        return None

    def wrapped(frames, latest_frame):
        state["last"] = None; state["conds"] = None
        action = real_choose(frames, latest_frame)
        st["calls"] += 1
        n = st["calls"]
        if n == oracle.INJECT_AFTER_CALLS:
            st["k0"] = strip_token()
        if oracle.INJECT_AFTER_CALLS < n <= oracle.INJECT_AFTER_CALLS + len(oracle.FORCED_CLICKS):
            return oracle.force_click(agent, oracle.FORCED_CLICKS[n - oracle.INJECT_AFTER_CALLS - 1])
        if n == oracle.INJECT_AFTER_CALLS + len(oracle.FORCED_CLICKS) + 1:
            missing = [m for m in (oracle.ADJ_MEMBER, oracle.STRIP) if m not in agent.regions.live]
            if missing:
                raise SystemExit(f"entities {missing} not live at injection (seed {seed}).")
            key, rec = oracle._block_key(agent)
            if key is None:
                raise SystemExit(f"no template-vs-block record at injection (seed {seed}).")
            h = _hypothesis.Hypothesis(
                key=key, action=oracle.ACTION, lift=0.0, start=rec.residual,
                precondition=(("adjacent:-x", oracle.ADJ_MEMBER), (f"state:{st['k0']}", oracle.STRIP)),
                source="oracle_h010_s3", confidence=1.0, predicted="down",
                falsifier="gate 1 diagnosis",
            )
            agent.hypothesis = h; st["h"] = h
            action = agent._hypothesis_action(agent._legal_actions(latest_frame)) or action

        h = st["h"]
        if h is not None and h.status == _hypothesis.LIVE:
            row = {"step": n, "action": action.name, "tier": agent._decision.get("tier"),
                   "why": str(getattr(action, "reasoning", ""))[:80],
                   "conds": state["conds"], "route": state["last"]}
            trace.append(row)
        return action

    agent.choose_action = wrapped
    agent.main()

    h = st["h"]
    return {"seed": seed, "levels": agent.frames[-1].levels_completed,
            "status": None if h is None else h.status,
            "spent": None if h is None else h.spent,
            "unmet": None if h is None else h.unmet,
            "jointly_met": None if h is None else sum(1 for m in h.mets if m),
            "trace": trace}


def report(res: dict) -> None:
    t = res["trace"]
    print(f"\n=== seed {res['seed']}  status={res['status']} spent={res['spent']} "
          f"unmet={res['unmet']} jointly_met={res['jointly_met']} levels={res['levels']} "
          f"live-steps={len(t)} ===")
    have_target = [r for r in t if r["route"] and r["route"]["target"]]
    no_path = [r for r in have_target if not r["route"]["graph_path"] and not r["route"]["offset_path"]]
    graph_ok = [r for r in have_target if r["route"]["graph_path"]]
    offset_only = [r for r in have_target if not r["route"]["graph_path"] and r["route"]["offset_path"]]
    followed = [r for r in have_target if r["route"]["used"] and r["action"] == r["route"]["used"][0]]
    adj_met = [r for r in t if r["conds"] and r["conds"].get("adjacent:-x") is True]

    print(f"  steps where a route was requested : {len(have_target)}")
    print(f"    NO path from either model        : {len(no_path)}")
    print(f"    graph model found a path         : {len(graph_ok)}")
    print(f"    only the offset model found one  : {len(offset_only)}")
    print(f"    route's first action was taken   : {len(followed)}")
    print(f"  steps where adjacency was MET      : {len(adj_met)}")
    print(f"  tiers seen while live: {dict(collections.Counter(r['tier'] for r in t))}")
    for r in t[:12]:
        rt = r["route"] or {}
        print(f"   step {r['step']:>3} {r['action']:<8} tier={str(r['tier']):<14} "
              f"pos={rt.get('pos')} tgt={rt.get('target')} "
              f"e@pos={rt.get('edges_from_pos')} g={rt.get('graph_path')} "
              f"o={rt.get('offset_path')} conds={r['conds']}")
    if len(t) > 12:
        print(f"   ... {len(t)-12} more live steps")

    print("  READING:", end=" ")
    if not have_target:
        print("D -- the bet never even requested a route; look upstream of routing.")
    elif len(no_path) >= 0.5 * len(have_target):
        print("A -- COVERAGE. No representable path on most live steps.")
    elif adj_met:
        print("B/C -- a path existed and adjacency was reached; read the conds column.")
    elif len(followed) < 0.5 * len([r for r in have_target if r['route']['used']]):
        print("C -- SELECTION. A route existed but another tier took the decision.")
    else:
        print("B -- TARGET. Routes existed and were followed, adjacency never became met.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, action="append", default=None)
    ap.add_argument("--max-steps", type=int, default=200)
    ap.add_argument("--json", type=str, default=None)
    a = ap.parse_args()
    seeds = a.seed or [1, 3]
    out = [run_seed(s, a.max_steps) for s in seeds]
    for r in out:
        report(r)
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
        print(f"\nfull trace -> {a.json}")
