"""Does `last_changer` pass the DOWNSTREAM CONSUMER link of the chain?

    discovery -> holdout -> [downstream consumer] -> gameplay

`last_changer` (which action last changed the frame) is the one candidate to
survive discovery (+68.2 over null, H013), holdout (+0.234) and the
meter-masked control (+0.281 at 98% coverage). Those all score a *frame-hash*
target. The agent's actual consumer is different: `predictor.rollout`
forecasts per-entity EFFECTS at k = 1/3/10, and its tallies are keyed by a
spatial condition only.

So the honest consumer question is not "does the variable predict frames" but:

    does conditioning the predictor's own effect table on `last_changer`
    raise the predictor's own rollout accuracy?

Method is `scripts/latent_rollout.py`'s, unchanged, with the variable swapped
and one control added. An entity's prediction is overridden only where its
(variable -> effect) history is a FUNCTION on enough points -- H006's admit
rule, the same bar Z1 had to clear.

THE METER CONTROL. The meter is an entity, so a variable that predicts only
the meter raises overall accuracy while being goal-irrelevant -- the confound
that retracted `n_reset`'s frame-hash result. Every number is therefore
reported twice: over all entities, and excluding meter-like entities (a thin
bar: bbox <= 2 cells thick and >= 8 long, either orientation).

Usage:
    .venv/bin/python scripts/h013_consumer.py --game sk48,su15,g50t,sc25
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
ARMS = ("tallies", "tallies+LC", "tallies+Z1")


def _admitted(hist: dict) -> bool:
    """H006's rule: is (variable -> effect) a function, on enough points?"""
    points = [c for c in hist.values() if sum(c.values()) >= 2]
    return len(points) >= MIN_FUNCTION_POINTS and all(len(c) == 1 for c in points)


def _tuple(e):
    return tuple(e) if isinstance(e, list) else e


def _new_attempt(steps, i):
    return (i == 0 or steps[i - 1]["action"] == "RESET"
            or steps[i]["levels_completed"] != steps[i - 1]["levels_completed"])


def _z1(steps) -> list:
    out, n = [], 0
    for i, _ in enumerate(steps):
        n = 0 if _new_attempt(steps, i) else n + 1
        out.append(n)
    return out


def _last_changer(steps) -> list:
    """Which action last changed the frame. ~8 values, unlike Z1's ~400."""
    out, cur = [], None
    for i, s in enumerate(steps):
        if _new_attempt(steps, i):
            cur = None
        elif (steps[i - 1].get("state_t") or {}).get("last_effects"):
            cur = steps[i - 1]["action"]
        out.append(cur)
    return out


def _meterish(bbox) -> bool:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0 + 1, y1 - y0 + 1
    return (h <= 2 and w >= 8) or (w <= 2 and h >= 8)


def score_trace(steps, tally, tally_nm) -> None:
    varz = {"tallies+Z1": _z1(steps), "tallies+LC": _last_changer(steps)}
    seen = {a: collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
            for a in varz}
    n = len(steps)
    for i in range(n):
        st = steps[i].get("state_t")
        if not st:
            continue
        # ids are ints in `entities` and STRINGS in `effects`/`last_effects`
        meter_ids = {str(e["id"]) for e in st.get("entities", []) if _meterish(e["bbox"])}
        if i and steps[i - 1].get("state_t"):
            for arm, col in varz.items():
                for rid, e in (st.get("last_effects") or {}).items():
                    seen[arm][rid][col[i - 1]][_tuple(e)] += 1
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
                actual = [(window[t]["state_t"]["last_effects"] or {}).get(rid) for t in range(k)]
                books = [tally] + ([tally_nm] if rid not in meter_ids else [])
                if any(a is None for a in actual):
                    for b in books:
                        for arm in ARMS:
                            b[arm][k][2] += 1
                    continue
                actual = [_tuple(a) for a in actual]
                pred = rollout(row, actions)
                if pred is None:
                    for b in books:
                        for arm in ARMS:
                            b[arm][k][3] += 1
                    continue
                for b in books:
                    b["tallies"][k][0 if pred == actual else 1] += 1
                for arm, col in varz.items():
                    p = list(pred)
                    if _admitted(seen[arm][rid]):
                        for t in range(k):
                            # Z1 increments deterministically, so z1[i]+t is a
                            # legitimate forecast (latent_rollout.py does this).
                            # `last_changer` is categorical and unknowable ahead
                            # of time -- the agent holds the value it has NOW.
                            key = (col[i] + t) if arm == "tallies+Z1" else col[i]
                            hist = seen[arm][rid].get(key)
                            if hist and len(hist) == 1 and sum(hist.values()) >= 2:
                                p[t] = next(iter(hist))
                    for b in books:
                        b[arm][k][0 if p == actual else 1] += 1


def acc(cell):
    hits, misses = cell[0], cell[1]
    return hits / (hits + misses) if hits + misses else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="sk48,su15,g50t,sc25")
    ap.add_argument("--dirs", default="recordings/latent/seed*/")
    a = ap.parse_args()

    print("Downstream-consumer test: does the variable raise the PREDICTOR's own")
    print("rollout accuracy? 'all' = every entity; 'no-meter' excludes thin bars.\n")
    for game in a.game.split(","):
        files = sorted(glob.glob(f"{a.dirs}{game}.jsonl"))
        if not files:
            print(f"{game}: no traces"); continue
        tally = {arm: {k: [0, 0, 0, 0] for k in HORIZONS} for arm in ARMS}
        tally_nm = {arm: {k: [0, 0, 0, 0] for k in HORIZONS} for arm in ARMS}
        for f in files:
            score_trace(_load(Path(f)), tally, tally_nm)
        print(f"=== {game} ({len(files)} traces) ===")
        for label, book in (("all", tally), ("no-meter", tally_nm)):
            row = []
            for k in HORIZONS:
                b, lc, z = (acc(book["tallies"][k]), acc(book["tallies+LC"][k]),
                            acc(book["tallies+Z1"][k]))
                row.append(f"k={k}: {b:.3f} | LC {lc:+.3f} | Z1 {z - b:+.3f}"
                           .replace(f"LC {lc:+.3f}", f"LC {lc - b:+.3f}"))
            print(f"  {label:9} " + "   ".join(row))
        print()


if __name__ == "__main__":
    main()
