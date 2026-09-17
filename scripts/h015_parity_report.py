"""H015 parity gate: read the n=30 seed-paired sweep, funnel first.

The two arms run identical code and differ only by ARC_BUDGET_GATE, so the
sweep summaries cannot be told apart on their own -- the manifest written by
the runner (seed, arm, summary path) is what separates them.

Read order is the standing one (docs/plan.md START HERE, 2026-09-17):
level-2 funnel, then hypothesis-status mix, then the named parity games,
then aggregate score LAST.
"""
from __future__ import annotations
import collections, json, statistics as st, sys

PARITY_GAMES = ("sp80", "ls20", "ar25", "m0r0", "dc22")


def load(manifest):
    runs = [json.loads(l) for l in open(manifest)]
    arms = {0: {}, 1: {}}
    for r in runs:
        if r["rc"] == 0 and r["summary"]:
            arms[r["arm"]][r["seed"]] = json.load(open(r["summary"]))
    return arms


def funnel(d):
    """L1/L2/L3 completions and actions-to-level across a whole sweep."""
    f = collections.Counter()
    for game, rec in d["observed"].items():
        lv = rec.get("levels_completed", 0) or 0
        f["L1_clears"] += 1 if lv >= 1 else 0
        f["L2_entries"] += 1 if lv >= 1 else 0     # entering L2 == clearing L1
        f["L2_clears"] += 1 if lv >= 2 else 0
        f["L3_clears"] += 1 if lv >= 3 else 0
        f["levels_total"] += lv
        idx = rec.get("completion_action_indices") or []
        if len(idx) >= 1:
            f["actions_to_L2_sum"] += idx[0]; f["actions_to_L2_n"] += 1
        if len(idx) >= 2:
            f["actions_to_L3_sum"] += idx[1]; f["actions_to_L3_n"] += 1
    return f


def statuses(d):
    c = collections.Counter()
    for rec in d["observed"].values():
        for e in rec.get("hypothesis_log", []):
            c[e[4]] += 1
    return c


def sign_test(pairs):
    """Wins/losses/ties for treatment over baseline, and a two-sided p."""
    w = sum(1 for a, b in pairs if b > a)
    l = sum(1 for a, b in pairs if b < a)
    t = sum(1 for a, b in pairs if b == a)
    n = w + l
    if n == 0:
        return w, l, t, 1.0
    from math import comb
    k = min(w, l)
    p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
    return w, l, t, p


def main(manifest):
    arms = load(manifest)
    seeds = sorted(set(arms[0]) & set(arms[1]))
    print(f"seed-paired sweeps: n={len(seeds)}  (seeds {seeds[0]}-{seeds[-1]})\n")

    print("=" * 72)
    print("1. LEVEL-2 FUNNEL  (read first; a change here outranks any score move)")
    print("=" * 72)
    fb = sum((funnel(arms[0][s]) for s in seeds), collections.Counter())
    ft = sum((funnel(arms[1][s]) for s in seeds), collections.Counter())
    rows = [("level-1 clears (game-sweeps)", "L1_clears"),
            ("level-2 ENTRIES", "L2_entries"),
            ("level-2 CLEARS", "L2_clears"),
            ("level-3 clears", "L3_clears"),
            ("total levels completed", "levels_total")]
    print(f"{'metric':<34}{'baseline':>12}{'treatment':>12}{'delta':>10}")
    for label, k in rows:
        print(f"{label:<34}{fb[k]:>12}{ft[k]:>12}{ft[k]-fb[k]:>+10}")
    for lbl, s, n in (("mean actions to L2", "actions_to_L2_sum", "actions_to_L2_n"),
                      ("mean actions to L3", "actions_to_L3_sum", "actions_to_L3_n")):
        b = fb[s] / fb[n] if fb[n] else float("nan")
        t = ft[s] / ft[n] if ft[n] else float("nan")
        print(f"{lbl:<34}{b:>12.1f}{t:>12.1f}{t-b:>+10.1f}")

    print("\n" + "=" * 72)
    print("2. HYPOTHESIS STATUS MIX  (did the mechanism do what it claims?)")
    print("=" * 72)
    sb = sum((statuses(arms[0][s]) for s in seeds), collections.Counter())
    stt = sum((statuses(arms[1][s]) for s in seeds), collections.Counter())
    print(f"{'status':<20}{'baseline':>12}{'treatment':>12}{'delta':>10}")
    for k in sorted(set(sb) | set(stt)):
        print(f"{k:<20}{sb[k]:>12}{stt[k]:>12}{stt[k]-sb[k]:>+10}")

    print("\n" + "=" * 72)
    print("3. PARITY GAMES  (gate: no loss > 1 level-1 clear per 30 sweeps)")
    print("=" * 72)
    print(f"{'game':<8}{'baseline':>10}{'treatment':>11}{'delta':>8}   verdict")
    for g in PARITY_GAMES:
        b = sum(1 for s in seeds if (arms[0][s]["observed"].get(g, {}).get("levels_completed") or 0) >= 1)
        t = sum(1 for s in seeds if (arms[1][s]["observed"].get(g, {}).get("levels_completed") or 0) >= 1)
        v = "OK" if t - b >= -1 else "REGRESSION"
        print(f"{g:<8}{b:>10}{t:>11}{t-b:>+8}   {v}")

    print("\n" + "=" * 72)
    print("4. AGGREGATE SCORE  (read LAST)")
    print("=" * 72)
    pairs = [(arms[0][s]["aggregate_score"], arms[1][s]["aggregate_score"]) for s in seeds]
    b = [p[0] for p in pairs]; t = [p[1] for p in pairs]
    print(f"baseline  median {st.median(b):.4f}  mean {st.mean(b):.4f}")
    print(f"treatment median {st.median(t):.4f}  mean {st.mean(t):.4f}")
    w, l, ti, p = sign_test(pairs)
    print(f"sign test: {w}W / {l}L / {ti}T   p = {p:.3f}"
          f"   {'significant' if p < 0.05 else 'NOT significant'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "h015_manifest.jsonl")
