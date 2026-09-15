"""H008 Day 5: k-step predictive sufficiency, two arms, offline.

The agent now scores its own entity rollouts live (`predictor.HORIZONS`,
`Ledger.horizon`, in every sweep summary). This script recomputes the
same number from the S_t traces `latent_probe.py trace` writes — with
the same `predictor.rollout` — and adds the arm the agent cannot run
yet: the same tallies **plus H006's admitted variable** `Z1 = actions
since reset`.

    tallies     the effect table as it stood at the window's start, read
                along the k actions actually taken (what the agent scores)
    tallies+Z1  Z1 is admitted for an entity only when that entity's whole
                history so far in this trace is a FUNCTION of Z1 — every
                Z1 value seen >= 2 times saw exactly one effect, and at
                least MIN_FUNCTION_POINTS such values exist. For an
                admitted entity the prediction at a Z1 value seen before
                is that effect; otherwise the tallies' majority. Generic
                — nothing names a meter; H006 measured the meter lines to
                be the entities whose history is deterministic in Z1.
                (A per-value rule — "one effect seen twice at this Z1" —
                over-admits on coincidences: measured on su15, which has
                no meter, it cost 5 points at k=10.)

A k-step prediction is a hit only if every one of its k per-step effects
is right. Undecidable when the entity leaves the screen inside the
window; abstained when the tallies cannot forecast one of the actions.
Windows never span a RESET or a level change.

H008 P1 says the +Z1 arm rises on the aliased (meter) games and not on
the 0%-aliased controls; P2 says k=10 already separates the navigational
games from the rest under the plain tallies.

Usage:
    .venv/bin/python scripts/latent_rollout.py recordings/latent/seed*/ [--game cd82,sp80]
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "agent"))

from alias_probe import _load  # noqa: E402
from predictor import HORIZONS, rollout  # noqa: E402

ARMS = ("tallies", "tallies+Z1")
MIN_FUNCTION_POINTS = 3


def _admitted(hist: dict) -> bool:
    """Is this entity's (Z1 -> effect) history a function, on enough points?"""
    points = [c for c in hist.values() if sum(c.values()) >= 2]
    return len(points) >= MIN_FUNCTION_POINTS and all(len(c) == 1 for c in points)


def _tuple(e):
    return tuple(e) if isinstance(e, list) else e


def _z1(steps: list[dict]) -> list[int]:
    out, n = [], 0
    for i, s in enumerate(steps):
        if i == 0 or steps[i - 1]["action"] == "RESET" or s["levels_completed"] != steps[i - 1]["levels_completed"]:
            n = 0
        else:
            n += 1
        out.append(n)
    return out


def score_trace(steps: list[dict], tally: dict) -> None:
    """tally[arm][k] -> [hits, misses, undecidable, abstained]."""
    z1 = _z1(steps)
    # what each entity did at each Z1 value so far in THIS trace, learned
    # online: seen[rid][z] -> Counter of effects (from last_effects, which
    # describes the transition INTO step i, i.e. the action at i-1 taken
    # at z1[i-1]).
    seen: dict = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    n = len(steps)
    for i in range(n):
        st = steps[i].get("state_t")
        if not st:
            continue
        # learn from the transition that led here, before predicting from here
        if i and steps[i - 1].get("state_t"):
            for rid, e in st.get("last_effects", {}).items():
                seen[rid][z1[i - 1]][_tuple(e)] += 1
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
                actual = [window[t]["state_t"]["last_effects"].get(rid) for t in range(k)]
                if any(a is None for a in actual):
                    for arm in ARMS:
                        tally[arm][k][2] += 1
                    continue
                actual = [_tuple(a) for a in actual]
                pred = rollout(row, actions)
                if pred is None:
                    for arm in ARMS:
                        tally[arm][k][3] += 1
                    continue
                tally["tallies"][k][0 if pred == actual else 1] += 1
                pred_z1 = list(pred)
                if _admitted(seen[rid]):
                    for t in range(k):
                        hist = seen[rid].get(z1[i] + t)
                        if hist and len(hist) == 1 and sum(hist.values()) >= 2:
                            pred_z1[t] = next(iter(hist))
                tally["tallies+Z1"][k][0 if pred_z1 == actual else 1] += 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+", type=Path)
    ap.add_argument("--game", default=None)
    args = ap.parse_args()
    wanted = set(args.game.split(",")) if args.game else None
    files = sorted(f for d in args.dirs for f in d.glob("*.jsonl") if not wanted or f.stem in wanted)
    by_game: dict[str, dict] = collections.defaultdict(
        lambda: {arm: {k: [0, 0, 0, 0] for k in HORIZONS} for arm in ARMS})
    for f in files:
        steps = _load(f)
        if not any(s.get("state_t", {}) and "effects" in s["state_t"] for s in steps if s.get("state_t")):
            continue          # an older trace without the H008 fields
        score_trace(steps, by_game[f.stem])

    def cell(v):
        n = v[0] + v[1]
        return f"{v[0] / n:5.0%}({n:5})" if n else "    -       "

    print(f"{'game':5} " + " ".join(f"{'k=' + str(k):>12}" for k in HORIZONS) + "   | +Z1: "
          + " ".join(f"{'k=' + str(k):>12}" for k in HORIZONS) + "   (accuracy over forecasts made)")
    for g, arms in sorted(by_game.items()):
        row = f"{g:5} " + " ".join(cell(arms['tallies'][k]) for k in HORIZONS)
        row += "   |      " + " ".join(cell(arms['tallies+Z1'][k]) for k in HORIZONS)
        print(row)


if __name__ == "__main__":
    main()
