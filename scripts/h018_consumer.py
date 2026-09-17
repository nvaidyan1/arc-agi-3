"""H018 at the REAL consumer -- SUPERSEDED by scripts/h018_ablation.py.

Kept because it produced the validated BASE / POS / POS* consumer numbers
(sc25 no-meter 0.876 / +0.028 / +0.075). A later edit added a
forward-predicted-position arm here and silently moved the BASE arm from
0.876 to 0.793; that edit is reverted and the arm was rewritten clean in
`h018_ablation.py`, which asserts BASE is bit-for-bit identical with and
without the other arms. **Use the ablation script for new work.**

Original docstring follows.

H018 at the REAL consumer: does per-entity position raise `predictor.rollout`?

H018 passed discovery, holdout and the target firewall without fragmenting
(coverage 0.97-1.00, CONTROL lift +0.075/+0.257/+0.090). So did
`last_changer` on the first three — and it scored +0.000 here, on the thing
the agent actually runs. This is that test.

Method is `scripts/h013_consumer.py`'s, unchanged, with one difference that
matters: position is a **per-entity** variable, so the admitted value is
looked up per (entity, step) rather than from one global column.

    tallies          `predictor.rollout` as the agent runs it
    tallies+POS      override an entity's predicted effect where its
                     (position -> effect) history is a FUNCTION on enough
                     points -- H006's admit rule, the same bar Z1 cleared
    tallies+Z1       control: known to be +0.000 once meters are excluded
    tallies+LC       control: known to be +0.000 everywhere

Discipline kept: the agent knows its CURRENT position, not the ones the next
k steps will produce, so the admitted value is held at step i across the
rollout rather than forecast forward. Every number is reported twice, all
entities and meter-like entities excluded.

Usage:
    .venv/bin/python scripts/h018_consumer.py --game sk48,sc25,g50t --bucket 1
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

MIN_FUNCTION_POINTS = 3
# POS*  = ORACLE: the same learned table, queried with the TRUE FUTURE
#         position at each rollout step instead of holding step i's.
#         A->B measures the value of knowing current position; B->C the
#         value of maintaining position through the rollout.
# POSpred = the implementable arm: position stepped forward by a learned
#           PER-ENTITY (position, action) -> position' model, the per-entity
#           analogue of H010's PositionModel (which keys on the GLOBAL,
#           colour-derived displacement and so cannot be reused directly).
#           It sees no future ground truth. POS* is the oracle ceiling.
ARMS = ("tallies", "tallies+POS", "tallies+POS*", "tallies+Z1", "tallies+LC")
LEARN_AS = {"tallies+POS*": "tallies+POS"}


def _admitted(hist: dict) -> bool:
    points = [c for c in hist.values() if sum(c.values()) >= 2]
    return len(points) >= MIN_FUNCTION_POINTS and all(len(c) == 1 for c in points)


def _tuple(e):
    return tuple(e) if isinstance(e, list) else e


def _meterish(bbox) -> bool:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0 + 1, y1 - y0 + 1
    return (h <= 2 and w >= 8) or (w <= 2 and h >= 8)


def _bucket(bbox, b):
    cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
    return (int(cx) // b, int(cy) // b)


def _new_attempt(steps, i):
    return (i == 0 or steps[i - 1]["action"] == "RESET"
            or steps[i]["levels_completed"] != steps[i - 1]["levels_completed"])


def _z1(steps):
    out, n = [], 0
    for i, _ in enumerate(steps):
        n = 0 if _new_attempt(steps, i) else n + 1
        out.append(n)
    return out


def _last_changer(steps):
    out, cur = [], None
    for i, s in enumerate(steps):
        if _new_attempt(steps, i):
            cur = None
        elif (steps[i - 1].get("state_t") or {}).get("last_effects"):
            cur = steps[i - 1]["action"]
        out.append(cur)
    return out


def value_for(arm, i, rid, ctx):
    """The admitted variable's value for this entity at this step."""
    if arm == "tallies+POS":
        return ctx["pos"][i].get(rid)
    if arm == "tallies+Z1":
        return ctx["z1"][i]
    return ctx["lc"][i]


def score_trace(steps, bucket, tally, tally_nm, breakdown=None) -> None:
    n = len(steps)
    pos = []
    for s in steps:
        st = s.get("state_t") or {}
        pos.append({str(e["id"]): _bucket(e["bbox"], bucket)
                    for e in (st.get("entities") or [])})
    ctx = {"pos": pos, "z1": _z1(steps), "lc": _last_changer(steps)}
    seen = {a: collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
            for a in ARMS if a != "tallies" and a not in LEARN_AS}
    # (entity, position, action) -> position', learned online from the same
    # stream, never from the future.
    posmodel: dict = collections.defaultdict(collections.Counter)

    for i in range(n):
        st = steps[i].get("state_t")
        if not st:
            continue
        meter_ids = {str(e["id"]) for e in (st.get("entities") or [])
                     if _meterish(e["bbox"])}
        if i and steps[i - 1].get("state_t"):
            # KEY INCLUDES THE ACTION. Inherited from h013_consumer.py, the
            # admit rule keyed on the variable ALONE -- asking "is this
            # entity's effect a function of position?", a far stronger and
            # different claim than H018's, which is about
            # (entity, ACTION, position). The effect table is per-action, so
            # per-action is also the faithful shape.
            prev_action = steps[i - 1]["action"]
            for rid, pv in pos[i - 1].items():
                nv = pos[i].get(rid)
                if nv is not None:
                    posmodel[(rid, pv, prev_action)][nv] += 1
            for rid, e in (st.get("last_effects") or {}).items():
                for arm in seen:
                    v = value_for(arm, i - 1, rid, ctx)
                    if v is not None:
                        seen[arm][rid][(prev_action, v)][_tuple(e)] += 1
        table = st.get("effects", {})
        for k in HORIZONS:
            j = i + k
            if j >= n:
                continue
            window = steps[i + 1:j + 1]
            if any(w["action"] == "RESET" for w in steps[i:j]) or \
               any(w["levels_completed"] != steps[i]["levels_completed"] for w in window) or \
               any(not w.get("state_t") for w in window):
                continue
            actions = [steps[i + t]["action"] for t in range(k)]
            for rid, row_json in table.items():
                row = {a: (_tuple(v[0]), v[1]) for a, v in row_json.items()}
                actual = [(w["state_t"]["last_effects"] or {}).get(rid) for w in window]
                books = [tally] + ([tally_nm] if rid not in meter_ids else [])
                if any(x is None for x in actual):
                    for b in books:
                        for arm in ARMS:
                            b[arm][k][2] += 1
                    continue
                actual = [_tuple(x) for x in actual]
                pred = rollout(row, actions)
                if pred is None:
                    for b in books:
                        for arm in ARMS:
                            b[arm][k][3] += 1
                    continue
                for b in books:
                    b["tallies"][k][0 if pred == actual else 1] += 1
                for arm in [a for a in ARMS if a != "tallies"]:
                    src = LEARN_AS.get(arm, arm)
                    p = list(pred)
                    walked = value_for(src, i, rid, ctx) if arm == "tallies+POSpred" else None
                    if _admitted(seen[src][rid]):
                        for t in range(k):
                            if arm == "tallies+POSpred" and t:
                                # step position forward with the learned model;
                                # hold it where the transition is unknown or
                                # not majority-clear.
                                c = posmodel.get((rid, walked, actions[t - 1]))
                                if c:
                                    best, n = c.most_common(1)[0]
                                    if n / sum(c.values()) >= 0.5:
                                        walked = best
                            # the oracle arm looks up the TRUE position at the
                            # step being predicted; every other arm holds i's.
                            if arm == "tallies+POS*":
                                v = value_for(src, i + t, rid, ctx)   # oracle
                            elif arm == "tallies+POSpred":
                                v = walked                            # stepped forward
                            else:
                                v = value_for(src, i, rid, ctx)
                            hist = seen[src][rid].get((actions[t], v))
                            if hist and len(hist) == 1 and sum(hist.values()) >= 2:
                                p[t] = next(iter(hist))
                    if k == 1 and arm == "tallies+POS" and breakdown is not None:
                        # pred[0]/actual[0] are the step-0 EFFECT TUPLES;
                        # their [0] is the kind string we want to tabulate.
                        def _k(e):
                            return e[0] if isinstance(e, tuple) and e else str(e)
                        if pred != actual and p == actual:
                            breakdown["fixed"][(_k(pred[0]), _k(actual[0]))] += 1
                        elif pred == actual and p != actual:
                            breakdown["broke"][(_k(pred[0]), _k(actual[0]))] += 1
                    for b in books:
                        b[arm][k][0 if p == actual else 1] += 1


def acc(cell):
    h, m = cell[0], cell[1]
    return h / (h + m) if h + m else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="sk48,sc25,g50t")
    ap.add_argument("--dirs", default="recordings/latent/seed1[0-2][0-9]/")
    ap.add_argument("--bucket", type=int, default=1)
    a = ap.parse_args()

    print(f"H018 at the real consumer (predictor.rollout), position bucket={a.bucket}")
    print("POS is the candidate; Z1 and LC are controls known to score +0.000.\n")
    for game in a.game.split(","):
        files = sorted(glob.glob(f"{a.dirs}{game}.jsonl"))
        if not files:
            print(f"{game}: no traces"); continue
        bd = {"fixed": collections.Counter(), "broke": collections.Counter()}
        t = {arm: {k: [0, 0, 0, 0] for k in HORIZONS} for arm in ARMS}
        tnm = {arm: {k: [0, 0, 0, 0] for k in HORIZONS} for arm in ARMS}
        for f in files:
            score_trace(_load(Path(f)), a.bucket, t, tnm, bd)
        print(f"=== {game} ({len(files)} traces) ===")
        for label, book in (("all", t), ("no-meter", tnm)):
            parts = []
            for k in HORIZONS:
                b = acc(book["tallies"][k])
                parts.append(f"k={k}: {b:.3f}"
                             f" | POS {acc(book['tallies+POS'][k]) - b:+.3f}"
                             f" | POS* {acc(book['tallies+POS*'][k]) - b:+.3f}"
                             f" | Z1 {acc(book['tallies+Z1'][k]) - b:+.3f}"
                             f" | LC {acc(book['tallies+LC'][k]) - b:+.3f}")
            print(f"  {label:9} " + "   ".join(parts))
        fixed = sum(bd["fixed"].values()); broke = sum(bd["broke"].values())
        print(f"  k=1 corrections: POS FIXED {fixed}, BROKE {broke}  (net {fixed-broke:+d})")
        for (pk, ak), n in bd["fixed"].most_common(5):
            print(f"      fixed  {pk:>12} -> {ak:<12} {n:>5}")
        for (pk, ak), n in bd["broke"].most_common(3):
            print(f"      broke  {pk:>12} -> {ak:<12} {n:>5}")
        print()


if __name__ == "__main__":
    main()
