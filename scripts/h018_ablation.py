"""H018 pre-gameplay ablation: BASE / POS / PRED / POS*, clean room.

Four arms over the SAME immutable rows, action sequences, effect tables,
target mask and scoring function. The ONLY thing that differs is where the
position handed to the override comes from:

    BASE   none
    POS    the entity's recorded position at the decision step, held
    PRED   position stepped forward by a learned per-entity model
    POS*   the entity's TRUE recorded position at each rollout step (oracle)

INVARIANT, asserted rather than hoped for: adding or removing arms must
leave BASE bit-for-bit identical. `--check-invariant` runs the full arm set
and the BASE-only set and compares the raw [hits, misses, undecidable,
abstained] cells, not just the rounded score. The previous implementation of
this ablation silently moved BASE from 0.876 to 0.793 when an arm was added;
this check is what would have caught it in one run.

On the forward model: `PositionModel` is NOT reusable here. It keys on the
global, colour-derived `MoveModel.displacement`; H018 is per-entity, so
entity identity has to be part of the transition. This builds the smallest
research-only thing that answers the question -- `(entity, position, action)
-> position'`, learned online, never from the future -- and deliberately not
a general spatial state model.

Two failure modes are separated, because they imply different conclusions:
  * the forward model is INACCURATE                -> mechanism unearned
  * it is accurate but PRED still gains nothing    -> the oracle's
    information is not transportable by this state representation

Usage:
    .venv/bin/python scripts/h018_ablation.py --game sc25,g50t,sk48
    .venv/bin/python scripts/h018_ablation.py --game sc25 --check-invariant
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
from predictor import HORIZONS, rollout            # noqa: E402

ALL_ARMS = ("BASE", "POS", "PRED", "POS*")
MIN_FUNCTION_POINTS = 3


def _tuple(e):
    return tuple(e) if isinstance(e, list) else e


def _meterish(bbox) -> bool:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0 + 1, y1 - y0 + 1
    return (h <= 2 and w >= 8) or (w <= 2 and h >= 8)


def _bucket(bbox, b):
    cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
    return (int(cx) // b, int(cy) // b)


def _admitted(hist: dict) -> bool:
    pts = [c for c in hist.values() if sum(c.values()) >= 2]
    return len(pts) >= MIN_FUNCTION_POINTS and all(len(c) == 1 for c in pts)


def new_book(arms):
    return {a: {k: [0, 0, 0, 0] for k in HORIZONS} for a in arms}


def walk(steps, bucket, arms, book, book_nm, tdiag):
    """One online pass. Learning never reads the future."""
    n = len(steps)
    pos = [{str(e["id"]): _bucket(e["bbox"], bucket)
            for e in ((s.get("state_t") or {}).get("entities") or [])} for s in steps]

    eff_hist: dict = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    trans: dict = collections.defaultdict(collections.Counter)

    for i in range(n):
        st = steps[i].get("state_t")
        if not st:
            continue
        meter = {str(e["id"]) for e in (st.get("entities") or []) if _meterish(e["bbox"])}

        # ---- learn from the transition that led here (strictly past) ----
        if i and steps[i - 1].get("state_t"):
            pa = steps[i - 1]["action"]
            for rid, e in (st.get("last_effects") or {}).items():
                v = pos[i - 1].get(rid)
                if v is not None:
                    eff_hist[rid][(pa, v)][_tuple(e)] += 1
            for rid, pv in pos[i - 1].items():
                nv = pos[i].get(rid)
                if nv is not None:
                    trans[(rid, pv, pa)][nv] += 1

        table = st.get("effects") or {}
        for k in HORIZONS:
            if i + k >= n:
                continue
            window = steps[i + 1:i + k + 1]
            if any(w["action"] == "RESET" for w in steps[i:i + k]) or \
               any(w["levels_completed"] != steps[i]["levels_completed"] for w in window) or \
               any(not w.get("state_t") for w in window):
                continue
            actions = [steps[i + t]["action"] for t in range(k)]
            for rid, row_json in table.items():
                row = {a: (_tuple(v[0]), v[1]) for a, v in row_json.items()}
                actual = [(w["state_t"]["last_effects"] or {}).get(rid) for w in window]
                books = [book] + ([book_nm] if rid not in meter else [])
                if any(x is None for x in actual):
                    for b in books:
                        for a in arms:
                            b[a][k][2] += 1
                    continue
                actual = [_tuple(x) for x in actual]
                pred = rollout(row, actions)
                if pred is None:
                    for b in books:
                        for a in arms:
                            b[a][k][3] += 1
                    continue

                # ---- BASE: identical in every configuration, by construction
                if "BASE" in arms:
                    for b in books:
                        b["BASE"][k][0 if pred == actual else 1] += 1

                ok = _admitted(eff_hist[rid])
                walked = pos[i].get(rid)
                for a in arms:
                    if a == "BASE":
                        continue
                    p = list(pred)
                    w = walked
                    for t in range(k):
                        if a == "POS":
                            v = pos[i].get(rid)
                        elif a == "POS*":
                            v = pos[i + t].get(rid)
                        else:                                   # PRED
                            if t:
                                c = trans.get((rid, w, actions[t - 1]))
                                if c:
                                    best, cnt = c.most_common(1)[0]
                                    if cnt / sum(c.values()) >= 0.5:
                                        if tdiag is not None:
                                            truth = pos[i + t].get(rid)
                                            tdiag["hit" if best == truth else "miss"] += 1
                                        w = best
                                    elif tdiag is not None:
                                        tdiag["unclear"] += 1
                                elif tdiag is not None:
                                    tdiag["unseen"] += 1
                            v = w
                        if ok:
                            h = eff_hist[rid].get((actions[t], v))
                            if h and len(h) == 1 and sum(h.values()) >= 2:
                                p[t] = next(iter(h))
                    for b in books:
                        b[a][k][0 if p == actual else 1] += 1


def acc(cell):
    h, m = cell[0], cell[1]
    return h / (h + m) if h + m else float("nan")


def run(game, dirs, bucket, arms, tdiag=None):
    files = sorted(glob.glob(f"{dirs}{game}.jsonl"))
    book, book_nm = new_book(arms), new_book(arms)
    for f in files:
        walk(_load(Path(f)), bucket, arms, book, book_nm, tdiag)
    return files, book, book_nm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="sc25,g50t,sk48")
    ap.add_argument("--dirs", default="recordings/latent/seed1[0-2][0-9]/")
    ap.add_argument("--bucket", type=int, default=1)
    ap.add_argument("--check-invariant", action="store_true")
    a = ap.parse_args()

    for game in a.game.split(","):
        tdiag = collections.Counter()
        files, book, book_nm = run(game, a.dirs, a.bucket, ALL_ARMS, tdiag)
        if not files:
            print(f"{game}: no traces"); continue

        if a.check_invariant:
            _f, b_only, b_only_nm = run(game, a.dirs, a.bucket, ("BASE",))
            same = all(book[x][k] == b_only[x][k] and book_nm[x][k] == b_only_nm[x][k]
                       for x in ("BASE",) for k in HORIZONS)
            print(f"  INVARIANT BASE identical with/without other arms: "
                  f"{'PASS' if same else '*** FAIL ***'}")
            if not same:
                for k in HORIZONS:
                    print(f"    k={k}: all-arms {book['BASE'][k]}  base-only {b_only['BASE'][k]}")
                continue

        print(f"\n=== {game} ({len(files)} traces) ===")
        for label, b in (("all", book), ("no-meter", book_nm)):
            parts = []
            for k in HORIZONS:
                base = acc(b["BASE"][k])
                parts.append(f"k={k}: {base:.3f}" + "".join(
                    f" | {arm} {acc(b[arm][k]) - base:+.3f}" for arm in ("POS", "PRED", "POS*")))
            print(f"  {label:9} " + "   ".join(parts))
        tot = sum(tdiag.values())
        if tot:
            hm = tdiag["hit"] + tdiag["miss"]
            print(f"  forward-model transitions used: {tot}  "
                  f"accuracy {tdiag['hit']/hm if hm else float('nan'):.3f} "
                  f"(hit {tdiag['hit']}, miss {tdiag['miss']}, "
                  f"unclear {tdiag['unclear']}, unseen {tdiag['unseen']})")
        print()


if __name__ == "__main__":
    main()
