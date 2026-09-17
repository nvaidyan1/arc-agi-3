"""H017: what information is the ACTION-EFFECT model actually missing?

Error attribution BEFORE candidate generation. Every candidate family tried
so far (H006 A-G, conjunctions, LMU) was generated first and tested after,
and three of them turned out to predict a goal-irrelevant part of the
observation. So start from the predictor's own mistakes instead.

Target discipline, learned the hard way (H008's Z1 gain, `n_reset`'s
frame-hash lift, gate 2's strip bbox -- all goal-irrelevant):

    Target A (observational, diagnostic only): does it predict the frame?
    Target B (instrumental, the promotion gate): does it predict the
             consequence of an action on the controllable mechanic?

This audits Target B only: `predictor.effect_table` read at k=1, on
NON-METER entities, which is exactly what `predictor.rollout` consumes.

The central split is by the table's own confidence:

    low-confidence miss   this (entity, action) has an INCONSISTENT effect
                          history -- the aliased case. Either a missing
                          conditioning variable or genuine stochasticity.
                          This is where latent state would pay, if anything
                          does.
    CONFIDENTLY WRONG     historically consistent, wrong NOW -- a regime the
                          model does not track.

NOTE: `confidence` is the majority RATE of that effect, over pairs already
tried >= PREDICT_MIN_TRIES times. Low confidence therefore means "the effect
varies", NOT "too few observations" -- an earlier draft of this script
labelled it "sampling", which was wrong.

Usage:
    .venv/bin/python scripts/h017_rollout_error_audit.py --game sk48,su15,g50t,sc25
"""
from __future__ import annotations

import argparse
import collections
import glob
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "agent"))

from alias_probe import _load                      # noqa: E402

CONF_HI = 0.8


def _tuple(e):
    return tuple(e) if isinstance(e, list) else e


def _meterish(bbox) -> bool:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0 + 1, y1 - y0 + 1
    return (h <= 2 and w >= 8) or (w <= 2 and h >= 8)


def audit(files):
    rows = []
    for fp in files:
        steps = _load(Path(fp))
        for i in range(len(steps) - 1):
            st, nxt = steps[i].get("state_t"), steps[i + 1].get("state_t")
            if not st or not nxt:
                continue
            if steps[i]["action"] == "RESET" or \
               steps[i + 1]["levels_completed"] != steps[i]["levels_completed"]:
                continue
            action = steps[i]["action"]
            ents = {str(e["id"]): e for e in st.get("entities", []) or []}
            meter = {rid for rid, e in ents.items() if _meterish(e["bbox"])}
            actual_all = nxt.get("last_effects") or {}
            for rid, row in (st.get("effects") or {}).items():
                if rid in meter or action not in row:
                    continue
                pred, conf = _tuple(row[action][0]), row[action][1]
                actual = actual_all.get(rid)
                if actual is None:
                    continue
                e = ents.get(rid, {})
                rows.append({"rid": rid, "action": action, "pred": pred,
                             "actual": _tuple(actual), "conf": conf,
                             "hit": _tuple(actual) == pred,
                             "control": bool(e.get("control")),
                             "role": e.get("role")})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="sk48,su15,g50t,sc25")
    ap.add_argument("--dirs", default="recordings/latent/seed*/")
    ap.add_argument("--top", type=int, default=6)
    a = ap.parse_args()

    for game in a.game.split(","):
        files = sorted(glob.glob(f"{a.dirs}{game}.jsonl"))
        if not files:
            print(f"{game}: no traces"); continue
        rows = audit(files)
        if not rows:
            print(f"{game}: no scorable predictions"); continue
        hits = sum(r["hit"] for r in rows)
        print(f"\n=== {game}: {len(rows)} k=1 predictions on non-meter entities, "
              f"accuracy {hits/len(rows):.3f} ===")

        # 1. the central split: is the model uncertain, or confidently wrong?
        hi = [r for r in rows if r["conf"] >= CONF_HI]
        lo = [r for r in rows if r["conf"] < CONF_HI]
        hi_miss = [r for r in hi if not r["hit"]]
        lo_miss = [r for r in lo if not r["hit"]]
        print(f"  confidence >= {CONF_HI}: {len(hi):>6}  misses {len(hi_miss):>5} "
              f"({len(hi_miss)/max(len(hi),1):.3f})   <- CONFIDENTLY WRONG: regime the model does not track")
        print(f"  confidence <  {CONF_HI}: {len(lo):>6}  misses {len(lo_miss):>5} "
              f"({len(lo_miss)/max(len(lo),1):.3f})   <- INCONSISTENT effect history: the aliased case")
        miss_total = len(hi_miss) + len(lo_miss)
        if miss_total:
            print(f"  share of ALL misses that are confidently wrong: "
                  f"{len(hi_miss)/miss_total:.3f}")

        # 2. what does it get confidently wrong -- predicted vs actual
        conf_pairs = collections.Counter((r["pred"], r["actual"]) for r in hi_miss)
        if conf_pairs:
            print("  confidently-wrong confusions (predicted -> actual):")
            for (p, act), n in conf_pairs.most_common(a.top):
                print(f"    {str(p):<22} -> {str(act):<22} {n:>5}")

        # 3. where do they concentrate?
        for label, key in (("action", lambda r: r["action"]),
                           ("entity", lambda r: r["rid"]),
                           ("is CONTROL", lambda r: r["control"])):
            by = collections.defaultdict(lambda: [0, 0])
            for r in rows:
                cell = by[key(r)]
                cell[0] += 1
                cell[1] += (not r["hit"])
            worst = sorted(by.items(), key=lambda kv: -kv[1][1])[:a.top]
            print(f"  misses by {label}: " + "  ".join(
                f"{k}={m}/{n}" for k, (n, m) in worst if m))

    print("\nconfidence is a majority RATE over pairs already tried >= 4 times, so")
    print("low confidence means the effect VARIES, not that observations are few.")
    print("The low-confidence mass is the aliased case -- where a conditioning")
    print("variable would pay. The confidently-wrong cells are a regime change.")


if __name__ == "__main__":
    main()
