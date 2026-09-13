"""Reconstruct sweep summaries from the per-step JSONL logs still on disk.

One-shot recovery, not part of the loop. Roughly fifty sweeps were run before
summaries existed; four runs' worth of `recordings/` survived, and this
salvages what they still contain.

What it can recover: the action index at which each level completed, the final
state, and the action count — the agent-observed half.

What it cannot: anything from the scorer. Per-level action costs, per-level
scores and the aggregate are computed by `arc_agi` at the end of a run from a
live scorecard, which is gone. Backfilled summaries are therefore marked
`"backfilled": true` and carry no `scored` rows, so they are never mistaken
for a full record when configurations are compared later.

Usage:
    .venv/bin/python scripts/backfill_summaries.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sweep_summary import build_summary, write_summary  # noqa: E402

RECORDINGS = ROOT / "recordings"
RESULTS_DIR = ROOT / "results" / "sweeps"


def read_game_log(path: Path) -> dict:
    """Summarise one game's JSONL: completions, final state, action count.

    Uses each entry's recorded `step` rather than its position in the file, so
    a truncated or partially-flushed log reports the action index it actually
    observed instead of an index shifted by the missing lines.
    """
    completions: list[int] = []
    previous_levels = None
    final_state = None
    final_levels = 0
    last_step = 0

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # A run killed mid-write leaves a partial final line; the rest of
            # the file is still good evidence.
            continue
        levels = entry.get("levels_completed", 0)
        step = entry.get("step", last_step)
        if previous_levels is not None and levels > previous_levels:
            completions.extend([step] * (levels - previous_levels))
        previous_levels = levels
        final_levels = levels
        final_state = entry.get("state", final_state)
        last_step = step

    return {
        "state": final_state,
        "levels_completed": final_levels,
        "actions": last_step,
        "completion_action_indices": completions,
    }


def main() -> None:
    if not RECORDINGS.exists():
        print(f"No {RECORDINGS.relative_to(ROOT)}/ directory; nothing to backfill.")
        return

    run_dirs = sorted(d for d in RECORDINGS.iterdir() if d.is_dir())
    if not run_dirs:
        print("No recorded runs found.")
        return

    for run_dir in run_dirs:
        logs = sorted(run_dir.glob("*.jsonl"))
        if not logs:
            continue
        observed = {log.stem: read_game_log(log) for log in logs}
        summary = build_summary(
            run_id=run_dir.name,
            # The cap is not recorded in the logs. Infer it from the longest
            # game rather than assuming: every surviving run was capped, so
            # the maximum step reached is the cap or just under it.
            max_steps=max((g["actions"] for g in observed.values()), default=0),
            games=sorted(observed),
            observed=observed,
            scorecard=None,
            notes=(
                "Backfilled from per-step JSONL by scripts/backfill_summaries.py. "
                "The live scorecard for this run is gone, so per-level action "
                "costs, per-level scores and the aggregate are unavailable; "
                "max_steps is inferred from the longest game, not recorded. "
                "Agent-observed fields are authentic."
            ),
        )
        summary["backfilled"] = True
        path = write_summary(summary, RESULTS_DIR)

        total = sum(len(g["completion_action_indices"]) for g in observed.values())
        print(f"{run_dir.name}: {len(observed):2} games, {total} completions "
              f"-> {path.relative_to(ROOT)}")
        for game_id, fields in sorted(observed.items()):
            if fields["completion_action_indices"]:
                print(f"    {game_id}: completed at "
                      f"{fields['completion_action_indices']}")


if __name__ == "__main__":
    main()
