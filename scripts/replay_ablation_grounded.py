"""Case D of the third review's ablation ladder
(`docs/expert-reviews/reviewer_c_09_14_2026c.md` §2, §14): hold the LLM's
*generation* fixed — replay the exact recorded raw replies, never call the
model again — and vary only what *integration* does with them, to ask
whether the "junk" content (`llm_ungrounded`/`llm_selfref`-tagged
hypotheses: an unconditional claim with no lever, or a precondition that
names one of the relation's own two entities) is helping or hurting the
same trajectory it actually produced.

This is a different, cleaner comparison than the four live matched-seed
sweeps already run this session (baseline / pre-fix / strict-reject /
soft-tag, `docs/history.md` 2026-09-15): those re-called the model fresh
each time, so a filtered hypothesis changes the pool, which changes the
trajectory, which changes what the *next live call* even sees — the
model's own content downstream of the first divergence is not the same
between arms. Here the raw replies are byte-identical in both arms; only
`parse_hypotheses`'s output is filtered, via
`replay_ablation.replay(..., drop_sources=...)`. Any score difference is
attributable to integration, not to new sampling.

Caveat inherited from the harness: dropping a hypothesis before it can be
tested changes when the pool goes empty, which can shift *when* the next
LLM call is triggered (`LLMProposer.should_call`) even though *what* that
call returns is still the next recorded reply in order, not a fresh
sample. A trajectory can therefore still diverge from the original run —
same reproducibility check as Stage 1, run again here per cell — but any
divergence traces to integration-driven timing, not to model variance.

Reads the 10 soft-arm sweep summaries already on disk (seeds 1-10, 5
games, `results/sweeps/202609151{01704,02238,...}*.json` — the arm
`docs/history.md` 2026-09-15 calls "soft"), replays every (game, seed)
cell twice (baseline: identical replay; grounded-only: drop_sources=
{"llm_ungrounded", "llm_selfref"}), and reports the paired difference.
No new LLM calls; no new sweep.

Usage:
    .venv/bin/python scripts/replay_ablation_grounded.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from replay_ablation import load_recorded_replies, replay  # noqa: E402

DROP = frozenset({"llm_ungrounded", "llm_selfref"})


def find_soft_arm_files() -> list[Path]:
    """The 10 sweep summaries this session's "soft" arm produced — the
    only files with an `llm_ungrounded`/`llm_selfref` source anywhere in
    their `hypothesis_log`, so this discovers them by content rather than
    by a hardcoded filename list that would silently go stale."""
    hits = []
    for path in sorted(Path("results/sweeps").glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        for entry in data.get("observed", {}).values():
            sources = {h[9] for h in (entry.get("hypothesis_log") or [])}
            if sources & {"llm_ungrounded", "llm_selfref"}:
                hits.append(path)
                break
    return hits


def score_of(arc) -> float:
    sc = arc.get_scorecard()
    return float(sc.score if hasattr(sc, "score") else sc)


def run_cell(path: Path, game: str) -> dict | None:
    try:
        meta, replies = load_recorded_replies(path, game)
    except SystemExit:
        return None
    if meta["n_calls"] == 0:
        return None
    seed, max_steps = meta["seed"], meta["max_steps"]

    agent_a, arc_a = replay(game, seed, max_steps, replies)
    score_a = score_of(arc_a)

    agent_b, arc_b = replay(game, seed, max_steps, replies, drop_sources=DROP)
    score_b = score_of(arc_b)

    return {
        "file": path.name, "game": game, "seed": seed,
        "baseline_replay_matches_original": (
            agent_a.frames[-1].levels_completed == meta["original"]["levels_completed"]
            and agent_a.action_counter == meta["original"]["actions"]),
        "score_baseline_replay": score_a,
        "score_grounded_only": score_b,
        "diff": score_b - score_a,
    }


def sign_test_p(diffs: list[float]) -> float:
    """Exact two-sided sign test over the non-zero diffs — no scipy in
    this project (docs/plan.md, "On hold and why")."""
    import math
    nonzero = [d for d in diffs if d != 0]
    n = len(nonzero)
    if n == 0:
        return 1.0
    k = sum(1 for d in nonzero if d > 0)
    k = min(k, n - k)
    total = sum(math.comb(n, i) for i in range(0, k + 1))
    return min(1.0, 2 * total / (2 ** n))


def main() -> None:
    files = find_soft_arm_files()
    if not files:
        raise SystemExit("No soft-arm sweep summaries found under results/sweeps/.")
    print(f"Found {len(files)} soft-arm sweep summaries.\n")

    rows = []
    for path in files:
        data = json.loads(path.read_text())
        for game in sorted(data.get("observed", {})):
            row = run_cell(path, game)
            if row is not None:
                rows.append(row)
                print(f"  {row['file']:28} {row['game']:6} seed={row['seed']:2}  "
                      f"baseline={row['score_baseline_replay']:.4f}  "
                      f"grounded_only={row['score_grounded_only']:.4f}  "
                      f"diff={row['diff']:+.4f}"
                      + ("" if row["baseline_replay_matches_original"] else "  [REPLAY MISMATCH]"))

    if not rows:
        raise SystemExit("No (game, seed) cell had any LLM calls to replay.")

    diffs = [r["diff"] for r in rows]
    wins = sum(1 for d in diffs if d > 0)
    losses = sum(1 for d in diffs if d < 0)
    ties = sum(1 for d in diffs if d == 0)
    mean_a = sum(r["score_baseline_replay"] for r in rows) / len(rows)
    mean_b = sum(r["score_grounded_only"] for r in rows) / len(rows)
    mismatches = sum(1 for r in rows if not r["baseline_replay_matches_original"])

    print(f"\n{len(rows)} cells replayed twice (no new LLM calls).")
    print(f"baseline-replay reproduced the original recorded outcome in "
          f"{len(rows) - mismatches}/{len(rows)} cells.")
    print(f"mean score: baseline-replay {mean_a:.4f}, grounded-only {mean_b:.4f}")
    print(f"grounded-only wins {wins} / losses {losses} / ties {ties}")
    print(f"sign-test p = {sign_test_p(diffs):.4f}")

    out_path = ROOT / "research" / "replay_ablation_grounded_only.json"
    out_path.write_text(json.dumps(rows, indent=2))
    print(f"\nFull per-cell results written to {out_path}")


if __name__ == "__main__":
    main()
