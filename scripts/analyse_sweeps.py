"""Read `results/sweeps/*.json` and report what the sweeps actually say.

This is the payoff of keeping summaries: every question the project has been
unable to answer — what is the noise floor, does a change move the score, how
deep do we get — is a query over this directory rather than a fresh batch of
runs.

Grouping is by **configuration**: git sha, dirty flag, action cap, and how
many games were played. Sweeps from a dirty tree are grouped together but
flagged, because a dirty tree is not a reproducible configuration and
comparing across two of them proves nothing.

Two things are reported that the aggregate score hides:

  * **Depth.** An environment's score is a level-index-weighted average over
    every level in the game, so reaching level 2 is worth roughly as much as
    a 4x speedup on level 1 (docs/history.md, 2026-09-13). `levels>=2` is
    therefore a headline number, not a footnote.
  * **Spread.** Mean alone is useless here: a single configuration has been
    seen to span 0.0-0.19. The min/max and standard deviation say whether a
    difference between two configurations means anything at all.

Usage:
    .venv/bin/python scripts/analyse_sweeps.py
    .venv/bin/python scripts/analyse_sweeps.py --by-game
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results" / "sweeps"


def load_summaries(results_dir: Path) -> list[dict]:
    summaries = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            summaries.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            print(f"  (skipping unreadable {path.name})")
    return summaries


def config_key(summary: dict) -> tuple:
    """Identify a comparable configuration.

    Game count is part of the key: a single-game probe and a 25-game sweep
    produce aggregates on completely different scales, and averaging them
    together would silently corrupt the very variance estimate these
    summaries exist to provide.
    """
    cfg = summary.get("config") or {}
    git = cfg.get("git") or {}
    return (
        (git.get("sha") or "unknown")[:8],
        bool(git.get("dirty")),
        cfg.get("max_steps"),
        len(cfg.get("games_requested") or summary.get("observed") or {}),
        bool(summary.get("backfilled")),
    )


def depth_stats(summary: dict) -> tuple[int, int, int]:
    """(games completing >=1 level, games completing >=2, total levels)."""
    observed = summary.get("observed") or {}
    levels = [g.get("levels_completed") or 0 for g in observed.values()]
    return (
        sum(1 for n in levels if n >= 1),
        sum(1 for n in levels if n >= 2),
        sum(levels),
    )


def describe(values: list[float]) -> str:
    if not values:
        return "n=0"
    if len(values) == 1:
        return f"n=1  value={values[0]:.4f}"
    return (
        f"n={len(values):<3} mean={statistics.mean(values):.4f}  "
        f"median={statistics.median(values):.4f}  "
        f"sd={statistics.stdev(values):.4f}  "
        f"min={min(values):.4f}  max={max(values):.4f}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--by-game", action="store_true",
                    help="Also break depth down per game, across all sweeps.")
    args = ap.parse_args()

    summaries = load_summaries(RESULTS_DIR)
    if not summaries:
        print(f"No summaries in {RESULTS_DIR.relative_to(ROOT)}/. Run a sweep.")
        return

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for summary in summaries:
        groups[config_key(summary)].append(summary)

    print(f"{len(summaries)} sweep(s) in {RESULTS_DIR.relative_to(ROOT)}/\n")

    for (sha, dirty, cap, n_games, backfilled), runs in sorted(
        groups.items(), key=lambda kv: (kv[0][3], kv[0][2] or 0, kv[0][0])
    ):
        label = f"{sha}{'-dirty' if dirty else ''} @ cap {cap}, {n_games} game(s)"
        if backfilled:
            label += "  [backfilled — no scorer half, cap inferred]"
        print(f"=== {label} ===")

        scores = [s["aggregate_score"] for s in runs
                  if isinstance(s.get("aggregate_score"), (int, float))]
        print(f"  score   {describe(scores)}")

        got1, got2, total = zip(*(depth_stats(s) for s in runs))
        print(f"  depth   games reaching L1: {describe([float(v) for v in got1])}")
        print(f"          games reaching L2: {sum(got2)} across {len(runs)} sweep(s)"
              f"  (total levels cleared: {sum(total)})")

        indices = [i for s in runs
                   for g in (s.get("observed") or {}).values()
                   for i in (g.get("completion_action_indices") or [])]
        if indices:
            print(f"  when    {len(indices)} completion(s) at actions "
                  f"min={min(indices)} median={int(statistics.median(indices))} "
                  f"max={max(indices)}")
        else:
            print("  when    no completions")
        print()

    if args.by_game:
        per_game: dict[str, list[int]] = defaultdict(list)
        for summary in summaries:
            for game_id, fields in (summary.get("observed") or {}).items():
                per_game[game_id].append(fields.get("levels_completed") or 0)
        print("=== levels cleared per game, across every sweep ===")
        for game_id, levels in sorted(per_game.items(),
                                      key=lambda kv: -sum(kv[1])):
            hits = sum(1 for n in levels if n >= 1)
            print(f"  {game_id:6} best={max(levels)}  "
                  f"cleared L1 in {hits}/{len(levels)} sweeps")


if __name__ == "__main__":
    main()
