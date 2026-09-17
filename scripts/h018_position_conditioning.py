"""Would per-entity POSITION survive the chain, before we build bookkeeping for it?

The audit established that a per-entity position already exists -- every
entity carries a bbox every step and ids persist 99.8-100% -- but that the
predictor cannot see it. Before building per-entity position history, test
whether position would survive as a conditioning variable at all.

    baseline   P(effect | entity, action)
    +posB      P(effect | entity, action, bbox centroid bucketed to B cells)

The reason to expect failure, and the reason to test cheaply: **cardinality**.
`n_reset` (~400 values) would have fragmented the tally to singletons; the E1
conjunction collapsed to 25% coverage -- best accuracy where it applied,
almost never applying. Raw position is high-cardinality and is a strong
candidate to fail the same way. So sweep the bucket size: B=32 (2x2 grid),
16 (4x4), 8 (8x8). If a coarse bucket survives and a fine one does not, the
coarseness that works is a principled answer to "how much position detail is
actually needed" rather than a guessed one.

Protocol is the one that killed `n_reset`, the conjunction and
`last_changer`: instrumental target only (per-entity effect, k=1), meter-like
entities excluded, seed-paired discovery/holdout, >= 4 observations to admit
a key, fall back to the baseline where the conditioned key is unseen.
COVERAGE is reported beside accuracy, because coverage is what killed the
others.

Usage:
    .venv/bin/python scripts/h018_position_conditioning.py --game sk48,sc25,g50t
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

BUCKETS = (32, 16, 8, 4, 2, 1)


def _tuple(e):
    return tuple(e) if isinstance(e, list) else e


def _meterish(bbox) -> bool:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0 + 1, y1 - y0 + 1
    return (h <= 2 and w >= 8) or (w <= 2 and h >= 8)


def _bucket(bbox, b):
    cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
    return (int(cx) // b, int(cy) // b)


def rows_for(files):
    out = []
    for fp in files:
        steps = _load(Path(fp))
        for i in range(len(steps) - 1):
            st, nxt = steps[i].get("state_t"), steps[i + 1].get("state_t")
            if not st or not nxt or steps[i]["action"] == "RESET":
                continue
            if steps[i + 1]["levels_completed"] != steps[i]["levels_completed"]:
                continue
            action = steps[i]["action"]
            ents = {str(e["id"]): e for e in st.get("entities", []) or []}
            actual_all = nxt.get("last_effects") or {}
            for rid in (st.get("effects") or {}):
                e = ents.get(rid)
                if not e or _meterish(e["bbox"]):
                    continue
                actual = actual_all.get(rid)
                if actual is None:
                    continue
                out.append({"rid": rid, "action": action, "actual": _tuple(actual),
                            "control": bool(e.get("control")),
                            "pos": {b: _bucket(e["bbox"], b) for b in BUCKETS}})
    return out


def fit(rows, keyfn, min_obs=4):
    t = collections.defaultdict(collections.Counter)
    for r in rows:
        t[keyfn(r)][r["actual"]] += 1
    return {k: c.most_common(1)[0][0] for k, c in t.items() if sum(c.values()) >= min_obs}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="sk48,sc25,g50t")
    ap.add_argument("--dirs", default="recordings/latent/seed1[0-2][0-9]/")
    ap.add_argument("--split", type=int, default=20)
    a = ap.parse_args()

    for game in a.game.split(","):
        files = sorted(glob.glob(f"{a.dirs}{game}.jsonl"))
        if len(files) < 4:
            print(f"{game}: only {len(files)} traces"); continue
        disc, held = rows_for(files[:a.split]), rows_for(files[a.split:])
        if not disc or not held:
            print(f"{game}: no rows"); continue

        base = fit(disc, lambda r: (r["rid"], r["action"]))
        conds = {b: fit(disc, lambda r, b=b: (r["rid"], r["action"], r["pos"][b]))
                 for b in BUCKETS}
        n_keys_base = len(base)

        print(f"\n=== {game}: {len(disc)} discovery / {len(held)} held-out rows ===")
        print(f"  {'arm':>10} {'keys':>7} {'coverage':>9} {'acc|cov':>8} "
              f"{'acc_all':>8} {'lift':>7}   {'CONTROL lift':>12}")
        # baseline
        hits = sum(1 for r in held if base.get((r["rid"], r["action"])) == r["actual"])
        seen = [r for r in held if (r["rid"], r["action"]) in base]
        b_acc = hits / len(held)
        bc = [r for r in held if r["control"]]
        b_ctrl = sum(1 for r in bc if base.get((r["rid"], r["action"])) == r["actual"]) / max(len(bc), 1)
        print(f"  {'baseline':>10} {n_keys_base:>7} {len(seen)/len(held):>9.3f} "
              f"{'-':>8} {b_acc:>8.3f} {'-':>7}   {b_ctrl:>12.3f}")
        for b in BUCKETS:
            cond = conds[b]
            cov = hit_cov = hit_all = ctrl_hit = 0
            for r in held:
                kb, kc = (r["rid"], r["action"]), (r["rid"], r["action"], r["pos"][b])
                pb, pc = base.get(kb), cond.get(kc)
                p = pc if pc is not None else pb
                if pc is not None:
                    cov += 1
                    hit_cov += (pc == r["actual"])
                hit_all += (p == r["actual"])
                if r["control"]:
                    ctrl_hit += (p == r["actual"])
            acc_all = hit_all / len(held)
            print(f"  {'+pos' + str(b):>10} {len(cond):>7} {cov/len(held):>9.3f} "
                  f"{(hit_cov / cov if cov else float('nan')):>8.3f} {acc_all:>8.3f} "
                  f"{acc_all - b_acc:>+7.3f}   "
                  f"{ctrl_hit / max(len(bc), 1) - b_ctrl:>+12.3f}")

    print("\nCoverage is the number that killed n_reset and the E1 conjunction:")
    print("high accuracy where a key applies means nothing if it rarely applies.")


if __name__ == "__main__":
    main()
