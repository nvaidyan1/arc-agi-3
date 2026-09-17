"""H017: does an ALREADY-KNOWN geometric condition resolve the dominant
action-effect aliasing?

    baseline   P(effect | entity, action, learned history)
    H017       P(effect | entity, action, learned history, is_blocked)

Brutally small by design. `is_blocked` comes from the agent's existing
`ObstacleMap`, dumped into the traces as-is: the detector is not improved, no
new spatial representation is added, no history variable is introduced. The
question is only whether a piece of information the agent ALREADY computes
for routing resolves the aliasing the predictor suffers.

Why this and not another latent variable: `ObstacleMap.is_blocked` is keyed
by (position, action), and the effect table is keyed by (entity, action). The
missing dimension is position -- the same one H009 found for cd82's motion
and H010 built `PositionModel` for. `is_blocked` is its cheapest boolean
projection, 2 values, so it cannot fragment the tally the way `n_reset`
(~400 values) or the E1 conjunction did.

Protocol, unchanged from the standard the last two days established:
  * instrumental target only (per-entity effect, k=1), never frame hash
  * meter-like entities excluded from every headline number
  * seed-paired discovery/holdout split, fit on discovery, score on holdout
  * H006's admit rule as the bar

The prediction that makes it falsifiable: the gain must CONCENTRATE in
blocked movement, and especially in CONTROL x blocked. If conditioning on
is_blocked improves everything indiscriminately, that is a broader
correlation being exploited, not the diagnosed mechanism.

Usage:
    .venv/bin/python scripts/h017_blocked_conditioning.py --game sk48,sc25,g50t,su15
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

MOVE_ACTIONS = {"ACTION1", "ACTION2", "ACTION3", "ACTION4"}


def _tuple(e):
    return tuple(e) if isinstance(e, list) else e


def _meterish(bbox) -> bool:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0 + 1, y1 - y0 + 1
    return (h <= 2 and w >= 8) or (w <= 2 and h >= 8)


def rows_for(files):
    """One row per (step, entity) scorable k=1 prediction."""
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
            blocked = bool((st.get("blocked") or {}).get(action, False))
            ents = {str(e["id"]): e for e in st.get("entities", []) or []}
            meter = {rid for rid, e in ents.items() if _meterish(e["bbox"])}
            actual_all = nxt.get("last_effects") or {}
            for rid in (st.get("effects") or {}):
                if rid in meter:
                    continue
                actual = actual_all.get(rid)
                if actual is None:
                    continue
                e = ents.get(rid, {})
                out.append({"rid": rid, "action": action, "blocked": blocked,
                            "actual": _tuple(actual),
                            "control": bool(e.get("control")),
                            "is_move": action in MOVE_ACTIONS})
    return out


def fit(rows, keyfn):
    table = collections.defaultdict(collections.Counter)
    for r in rows:
        table[keyfn(r)][r["actual"]] += 1
    return {k: c.most_common(1)[0][0] for k, c in table.items() if sum(c.values()) >= 4}


def score(held, base, cond, keyb, keyc):
    """Per cell: n, baseline hits, H017 hits."""
    cells = collections.defaultdict(lambda: [0, 0, 0])
    for r in held:
        pb, pc = base.get(keyb(r)), cond.get(keyc(r))
        if pb is None:
            continue                     # unseen by BOTH arms' shared key
        p_h017 = pc if pc is not None else pb      # fall back to baseline
        for name in cell_names(r):
            c = cells[name]
            c[0] += 1
            c[1] += (pb == r["actual"])
            c[2] += (p_h017 == r["actual"])
    return cells


def cell_names(r):
    yield "ALL"
    yield "CONTROL" if r["control"] else "non-CONTROL"
    if r["is_move"]:
        yield "blocked movement" if r["blocked"] else "unblocked movement"
        if r["control"]:
            yield "CONTROL x blocked" if r["blocked"] else "CONTROL x unblocked"
    else:
        yield "non-movement action"


ORDER = ["ALL", "CONTROL", "non-CONTROL", "blocked movement", "unblocked movement",
         "CONTROL x blocked", "CONTROL x unblocked", "non-movement action"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="sk48,sc25,g50t,su15")
    ap.add_argument("--dirs", default="recordings/latent/seed1[0-2][0-9]/")
    ap.add_argument("--split", type=int, default=20, help="first N traces discover")
    a = ap.parse_args()

    for game in a.game.split(","):
        files = sorted(glob.glob(f"{a.dirs}{game}.jsonl"))
        if len(files) < 4:
            print(f"{game}: only {len(files)} traces with obstacle data"); continue
        disc, held = rows_for(files[:a.split]), rows_for(files[a.split:])
        if not disc or not held:
            print(f"{game}: no rows"); continue
        base = fit(disc, lambda r: (r["rid"], r["action"]))
        cond = fit(disc, lambda r: (r["rid"], r["action"], r["blocked"]))
        cells = score(held, base, cond,
                      lambda r: (r["rid"], r["action"]),
                      lambda r: (r["rid"], r["action"], r["blocked"]))
        print(f"\n=== {game}: {len(files[:a.split])} discovery / "
              f"{len(files[a.split:])} held-out traces, {len(held)} scored ===")
        print(f"  {'cell':22} {'n':>8} {'baseline':>9} {'H017':>8} {'delta':>8}")
        for name in ORDER:
            if name not in cells:
                continue
            n, b, h = cells[name]
            if not n:
                continue
            print(f"  {name:22} {n:>8} {b/n:>9.3f} {h/n:>8.3f} {h/n - b/n:>+8.3f}")

    print("\nThe diagnosis predicts the gain CONCENTRATES in blocked movement,")
    print("especially CONTROL x blocked. Indiscriminate improvement would mean a")
    print("broader correlation is being exploited, not the diagnosed mechanism.")


if __name__ == "__main__":
    main()
