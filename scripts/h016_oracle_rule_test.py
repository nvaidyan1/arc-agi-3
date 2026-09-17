"""H016: does the H007 conditional rule survive a direct causal test?

Four gates of infrastructure (H010 routing, H011 click coverage, H015 budget
economy) were built to make ONE proposition executable on cd82:

    (adjacent:-x of the block) AND (swatch strip in state K0)
        -> ACTION5 -> the template-vs-block residual falls

That proposition has been jointly satisfied and actually tested exactly once
-- H007 Day 4, seed 2, three met presses -- and the residual did not move
("falsified: residual 5 held under three met presses"). Every gate since has
made it easier to execute without re-asking whether it is true.

So: give the oracle enough budget that travel is affordable, and measure the
only thing that matters.

    dR = R_before - R_after,  at steps where the condition is JOINTLY MET

Not "did we clear level 1". The per-press residual transition under the
satisfied condition is the causal experiment.

WHAT A NEGATIVE RESULT FALSIFIES, precisely: the specific H007 causal rule
above. NOT "cd82's mechanic" and NOT the broader cd82 theory -- one failed
conditional action leaves the underlying mechanic undiscovered, which is a
different and still-open question.

Outcomes:
  A  joint condition reached AND residual responds  -> the rule is supported;
     H015's budget finding becomes actionable and the budget-pricing
     mechanism is worth building properly.
  B  joint condition reached AND residual does not  -> the specific rule is
     falsified. Stop investing in making it executable.
  C  joint condition never reached even with budget -> classify the trace
     (see `classify`) rather than opening another hypothesis: travel
     unaffordable / target computation wrong / geometrically unreachable /
     condition never actually established.

Usage:
    .venv/bin/python scripts/h016_oracle_rule_test.py --budget 120 \
        --seed 1 --seed 2 --seed 3 --seed 4 --seed 5
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
import relations as _relations  # noqa: E402


def run_seed(seed: int, budget: int, max_steps: int) -> dict:
    import arc_agi
    from arc_agi import OperationMode
    from play_local import load_my_agent_class

    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
    Cls = load_my_agent_class()
    Cls.MAX_ACTIONS = max_steps
    Cls.SEED = seed
    env = arc.make("cd82")
    agent = Cls(card_id="h016", game_id="cd82", agent_name="h016.cd82",
                ROOT_URL="http://localhost", record=False, arc_env=env, tags=["h016"])

    st = {"calls": 0, "k0": None, "h": None}
    trace: list = []
    real_choose = agent.choose_action

    def strip_token():
        if oracle.STRIP in agent.regions.live and oracle.STRIP in agent.regions._tracked:
            return _relations.state_key(*agent.regions._tracked[oracle.STRIP])
        return None

    def wrapped(frames, latest_frame):
        action = real_choose(frames, latest_frame)
        st["calls"] += 1
        n = st["calls"]
        inj = oracle.INJECT_AFTER_CALLS
        if n == inj:
            st["k0"] = strip_token()
        if inj < n <= inj + len(oracle.FORCED_CLICKS):
            return oracle.force_click(agent, oracle.FORCED_CLICKS[n - inj - 1])
        if n == inj + len(oracle.FORCED_CLICKS) + 1:
            missing = [m for m in (oracle.ADJ_MEMBER, oracle.STRIP) if m not in agent.regions.live]
            if missing:
                st["abort"] = f"entities {missing} not live at injection"
                return action
            key, rec = oracle._block_key(agent)
            if key is None:
                st["abort"] = "no template-vs-block record at injection"
                return action
            h = _hypothesis.Hypothesis(
                key=key, action=oracle.ACTION, lift=0.0, start=rec.residual,
                budget=budget,                      # <-- the whole point
                precondition=(("adjacent:-x", oracle.ADJ_MEMBER), (f"state:{st['k0']}", oracle.STRIP)),
                source="oracle_h016", confidence=1.0, predicted="down",
                falsifier="the residual does not fall under jointly-met presses of ACTION5",
            )
            agent.hypothesis = h
            st["h"] = h
            action = agent._hypothesis_action(agent._legal_actions(latest_frame)) or action

        h = st["h"]
        if h is not None and h.status == _hypothesis.LIVE:
            conds = {}
            for cond, member in _hypothesis.conditions_of(h.precondition):
                try:
                    conds[cond] = bool(agent._condition_met(cond, member))
                except Exception as exc:
                    conds[cond] = f"error: {exc.__class__.__name__}"
            trace.append({
                "step": n, "action": action.name,
                "tier": agent._decision.get("tier"),
                "conds": conds,
                "all_met": all(v is True for v in conds.values()),
                "pos": list(agent.moves.displacement) if agent.moves.displacement else None,
            })
        return action

    agent.choose_action = wrapped
    agent.main()

    h = st["h"]
    out = {"seed": seed, "budget": budget, "abort": st.get("abort"),
           "levels": agent.frames[-1].levels_completed, "trace": trace}
    if h is not None:
        # dR per press, paired with whether that press was jointly met.
        presses = []
        prev = h.start
        for i, after in enumerate(h.history):
            met = h.mets[i] if i < len(h.mets) else None
            presses.append({"i": i, "met": bool(met), "before": prev, "after": after,
                            "dR": (None if (prev is None or after is None) else prev - after)})
            prev = after if after is not None else prev
        out.update(status=h.status, spent=h.spent, unmet=h.unmet,
                   start=h.start, presses=presses,
                   jointly_met=sum(1 for m in h.mets if m))
    return out


def classify(res: dict) -> str:
    """Outcome C only: why was the condition never jointly met?"""
    t = res["trace"]
    if not t:
        return "condition never established (no live steps recorded)"
    state_ok = sum(1 for r in t if any(k.startswith("state:") and v is True for k, v in r["conds"].items()))
    adj_ok = sum(1 for r in t if r["conds"].get("adjacent:-x") is True)
    positions = {tuple(r["pos"]) for r in t if r["pos"]}
    if state_ok == 0:
        return "condition never established (the STATE half was never satisfied)"
    if adj_ok == 0 and len(positions) <= 2:
        return "travel unaffordable or blocked (state held; adjacency never met; agent barely moved)"
    if adj_ok == 0:
        return ("adjacency never met despite movement over "
                f"{len(positions)} positions -> target computation or geometric reachability")
    return "adjacency and state each met, never simultaneously"


def report(res: dict) -> None:
    print(f"\n=== seed {res['seed']}  budget={res['budget']} ===")
    if res.get("abort"):
        print(f"  ABORTED: {res['abort']} (pre-existing oracle guard, not a result)")
        return
    print(f"  status={res.get('status')} spent={res.get('spent')}/{res['budget']} "
          f"unmet={res.get('unmet')} jointly_met={res.get('jointly_met')} "
          f"levels={res['levels']} live-steps={len(res['trace'])}")
    met = [p for p in res.get("presses", []) if p["met"]]
    if not met:
        print(f"  NO jointly-met press. Outcome C -> {classify(res)}")
        return
    print(f"  {len(met)} JOINTLY-MET presses (start residual {res.get('start')}):")
    for p in met:
        print(f"    press {p['i']:>3}  R_before={p['before']}  R_after={p['after']}  dR={p['dR']}")
    fell = [p for p in met if p["dR"] is not None and p["dR"] > 0]
    print(f"  residual FELL on {len(fell)} of {len(met)} jointly-met presses")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, action="append", default=None)
    ap.add_argument("--budget", type=int, default=120)
    ap.add_argument("--max-steps", type=int, default=400)
    ap.add_argument("--json", type=str, default=None)
    a = ap.parse_args(argv[1:])
    seeds = a.seed or [1, 2, 3, 4, 5]
    out = [run_seed(s, a.budget, a.max_steps) for s in seeds]
    for r in out:
        report(r)

    ok = [r for r in out if not r.get("abort")]
    all_met = [p for r in ok for p in r.get("presses", []) if p["met"]]
    fell = [p for p in all_met if p["dR"] is not None and p["dR"] > 0]
    print("\n" + "=" * 68)
    print(f"seeds run {len(out)}  usable {len(ok)}  jointly-met presses {len(all_met)}  "
          f"residual fell on {len(fell)}")
    print("=" * 68)
    MIN_MET = 8          # below this, no verdict is stated at all
    rose = [p for p in all_met if p["dR"] is not None and p["dR"] < 0]
    flat = [p for p in all_met if p["dR"] == 0]
    verdicts = collections.Counter(r.get("status") for r in ok if r.get("status"))
    if all_met:
        print(f"  of {len(all_met)} jointly-met presses: fell {len(fell)}, "
              f"flat {len(flat)}, ROSE {len(rose)}")
        print(f"  the verifier's own per-seed verdicts: {dict(verdicts)}")
    if not all_met:
        print("OUTCOME C: the condition was never jointly satisfied even with budget.")
        for r in ok:
            print(f"  seed {r['seed']}: {classify(r)}")
        print("  -> classify the traces; do NOT open another hypothesis yet.")
    elif len(all_met) < MIN_MET:
        print(f"NO VERDICT: only {len(all_met)} jointly-met presses (need >= {MIN_MET}).")
        print("  A single large fall is not support: the residual is a part-size")
        print("  difference that other events can move. Run more seeds.")
    elif len(fell) > len(all_met) / 2 and not rose:
        print("OUTCOME A: the H007 conditional rule is SUPPORTED. The residual")
        print("  falls on a majority of jointly-met presses and never rises, so")
        print("  H015's budget finding is actionable and budget pricing is worth")
        print("  building properly.")
    elif len(fell) <= len(all_met) / 2 or rose:
        print("OUTCOME B: the SPECIFIC H007 causal rule is FALSIFIED --")
        print("  (adjacent:-x, state K0) -> ACTION5 -> residual fall does not hold")
        print("  reliably: the residual does not fall on most jointly-met presses,")
        print("  and/or rises on some. This does NOT falsify cd82's mechanic, which")
        print("  remains undiscovered -- one failed conditional action leaves the")
        print("  underlying rule unfound.")
        print("  -> stop investing in making THIS proposition executable.")
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
        print(f"\ntrace -> {a.json}")


if __name__ == "__main__":
    main(sys.argv)
