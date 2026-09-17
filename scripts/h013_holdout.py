"""E1: does the conjunction PREDICT out of sample, or did it just partition?

`h013_family_splitter.py` found that `G_ngram3 AND n_reset` raises g50t's
resolved contexts from 44 to 81 and cuts unresolved from 217 to 100. That is
a discovery signal, not a causal result: a conjunction partitions
observations into smaller groups where local consistency is easier to reach,
and the >= 2-visit rule blocks only wholly vacuous singletons.

So: discover on one set of trajectories, FREEZE, and predict held-out ones.

    discovery traces -> table[(context, candidate value)] = majority outcome
    held-out traces  -> predict each visit, score against what happened

The baseline that matters is **context-majority**: predicting the most common
outcome for that pixel-context while ignoring the candidate entirely. That is
exactly "no state variable". A candidate earns its place only by beating it
on data it was not fitted to.

Reported per candidate:
    coverage   held-out visits whose (context, value) was seen in discovery
    acc        accuracy on covered visits
    acc_all    accuracy counting uncovered visits as context-majority fallback
    lift       acc_all - baseline accuracy

Usage:
    .venv/bin/python scripts/h013_holdout.py --game g50t --split 20
"""
from __future__ import annotations

import argparse
import collections
import glob
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import latent_splitter as ls            # noqa: E402
from h013_family_splitter import extra_candidates, is_meter_context  # noqa: E402


def seed_of(path: str) -> int:
    d = os.path.basename(os.path.dirname(path))
    return int("".join(c for c in d if c.isdigit()) or 0)


def build(files: list[str]):
    """Per-visit context, outcome and candidate values across a set of traces."""
    rows = []
    for fp in files:
        steps = ls._load(Path(fp))
        H = [ls._hash(s["frame"]) if s.get("frame") else None for s in steps]
        A = [ls._action_key(s) for s in steps]
        feats = ls.candidates_for(steps)
        feats.update(extra_candidates(steps))
        for i in range(len(steps) - 1):
            if steps[i + 1]["step"] != steps[i]["step"] + 1 or not H[i] or not H[i + 1]:
                continue
            rows.append({"ctx": (H[i], A[i]), "out": H[i + 1],
                         "frame_next": steps[i + 1]["frame"],
                         "vals": {k: v[i] for k, v in feats.items()}})
    return rows


def value_of(row, name):
    if " AND " in name:
        a, b = name.split(" AND ")
        return (row["vals"].get(a), row["vals"].get(b))
    return row["vals"].get(name)


def evaluate(disc, held, name, aliased_ctx):
    """Fit on `disc`, score on `held`, restricted to contexts aliased in disc."""
    table: dict = collections.defaultdict(collections.Counter)
    ctx_only: dict = collections.defaultdict(collections.Counter)
    for r in disc:
        if r["ctx"] not in aliased_ctx:
            continue
        ctx_only[r["ctx"]][r["out"]] += 1
        table[(r["ctx"], value_of(r, name))][r["out"]] += 1

    n = cov = hit_cov = hit_all = base_hit = 0
    for r in held:
        if r["ctx"] not in aliased_ctx or r["ctx"] not in ctx_only:
            continue
        n += 1
        base = ctx_only[r["ctx"]].most_common(1)[0][0]
        base_hit += (base == r["out"])
        key = (r["ctx"], value_of(r, name))
        if key in table:
            cov += 1
            pred = table[key].most_common(1)[0][0]
            hit_cov += (pred == r["out"])
            hit_all += (pred == r["out"])
        else:
            hit_all += (base == r["out"])          # fall back to context-majority
    return {"n": n, "cov": cov, "hit_cov": hit_cov, "hit_all": hit_all,
            "base": base_hit}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="g50t")
    ap.add_argument("--dirs", default="recordings/latent/seed*/")
    ap.add_argument("--split", type=int, default=20,
                    help="seeds <= this discover; seeds above are held out")
    ap.add_argument("--heldout-from", type=int, default=0,
                    help="E2: FIX the held-out set at seeds >= this, and let "
                         "--split vary the DISCOVERY budget only. Without it, "
                         "growing --split also shrinks the held-out set and the "
                         "curve conflates two changes.")
    ap.add_argument("--only", default=None, help="comma-separated candidates")
    ap.add_argument("--mechanic-only", action="store_true", default=True)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dirs, f"{a.game}.jsonl")), key=seed_of)
    hold_from = a.heldout_from or (a.split + 1)
    disc_f = [f for f in files if seed_of(f) <= a.split]
    held_f = [f for f in files if seed_of(f) >= hold_from]
    print(f"{a.game}: discovery seeds {len(disc_f)}, held-out seeds {len(held_f)}")

    disc, held = build(disc_f), build(held_f)

    # Contexts that are ALIASED in the DISCOVERY data -- where state matters.
    # Anything deterministic is predicted perfectly by the baseline and would
    # only dilute the comparison.
    by_ctx = collections.defaultdict(list)
    for r in disc:
        by_ctx[r["ctx"]].append(r)
    aliased = set()
    for ctx, rs in by_ctx.items():
        if len(rs) >= 2 and len({r["out"] for r in rs}) >= 2:
            if a.mechanic_only:
                frames = [r["frame_next"] for r in rs]
                if is_meter_context(frames):
                    continue
            aliased.add(ctx)
    print(f"  aliased{' mechanic' if a.mechanic_only else ''} contexts in discovery: "
          f"{len(aliased)}\n")

    names = (a.only.split(",") if a.only else
             ["n_level", "G_ngram3", "n_reset", "presses_since_click", "B_disp",
              "G_ngram3 AND n_reset", "G_ngram3 AND presses_since_click"])
    print(f"  {'candidate':36} {'held-out n':>10} {'cov':>6} {'acc|cov':>8} "
          f"{'acc_all':>8} {'baseline':>9} {'lift':>7}")
    base_shown = None
    for name in names:
        r = evaluate(disc, held, name, aliased)
        if not r["n"]:
            print(f"  {name:36} (no held-out visits in aliased contexts)"); continue
        acc_cov = r["hit_cov"] / r["cov"] if r["cov"] else float("nan")
        acc_all = r["hit_all"] / r["n"]
        base = r["base"] / r["n"]
        base_shown = base
        print(f"  {name:36} {r['n']:>10} {r['cov']/r['n']:>6.2f} {acc_cov:>8.3f} "
              f"{acc_all:>8.3f} {base:>9.3f} {acc_all - base:>+7.3f}"
              f"   [disc={len(disc_f)}]")

    print(f"\n  baseline = predict the context's majority outcome, ignoring the")
    print(f"  candidate entirely. That is 'no state variable'. A candidate earns")
    print(f"  its place only by beating it on data it was not fitted to.")


if __name__ == "__main__":
    main()
