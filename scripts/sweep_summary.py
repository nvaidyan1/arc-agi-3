"""Build the durable, self-scoring record of one sweep.

Why this exists
---------------
Roughly fifty 25-game sweeps have been run on this project. Exactly one
survives on disk, because `recordings/` is gitignored and holds only bulky
per-step logs. Every configuration comparison in `docs/history.md` was
therefore made against numbers that no longer exist and cannot be re-derived.
Given a within-configuration score range of 0.0-0.15, that is the single
biggest obstacle to deciding anything.

A sweep summary is small (a few KB), committed, and carries enough to
re-answer questions we have not thought to ask yet:

  * **per-level action costs and scores**, taken from the real scorer rather
    than re-derived — see `_level_costs_are_cumulative_deltas` below for why
    this distinction is load-bearing;
  * the **cumulative action index at which each level completed**, which is
    what "do completions arrive early?" actually asks;
  * a **configuration fingerprint** (git SHA, dirty flag, action cap), so a
    score can be attributed to the code that produced it.

Nothing here reads the game engine or the agent. It takes what the sweep
already observed and shapes it for storage, so it can be unit-tested without
a game.

A note on the scorer, established by reading
`arc_agi/scorecard.py:_calculate_score` (line ~476)
-----------------------------------------------------------------
    level_actions = actions_at_level - prev_actions

A level's cost is the cumulative action counter at its completion *minus* the
counter at the previous level's completion. The agent-side counter
(`agents/agent.py:87`) never resets — not on RESET, not on level change. So
every action spent on failed attempts *within* a level is charged to that
level. Six 60-action attempts before clearing level 1 charge level 1 with
360, not 60. A truncate-and-retry policy therefore buys nothing on score.

Two further consequences, both recorded here because they are easy to
re-derive and easy to forget:

  * `EnvironmentScoreCalculator.to_score` averages level scores **weighted by
    level index**, dividing by the summed weight of *every* level in the game
    including ones never reached. Clearing only level 1 of a 5-level game
    caps the environment at `1/(1+2+3+4+5)` = 6.7% of its value, however fast
    that level was. Depth dominates speed.
  * A per-level score is capped at 115.0, not 100.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1


def git_fingerprint(root: Path) -> dict[str, Any]:
    """Identify the code that produced a sweep.

    Returns `{"sha": None, "dirty": None}` rather than raising when git is
    unavailable — a summary with a missing fingerprint is still worth far more
    than no summary, and this must never be able to fail a sweep that has
    already cost 25 games of compute.
    """
    def _git(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    sha = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    return {
        "sha": sha,
        "dirty": None if status is None else bool(status),
        "subject": _git("log", "-1", "--pretty=%s"),
    }


def completion_indices(levels_by_step: Iterable[int]) -> list[int]:
    """Cumulative action indices at which `levels_completed` stepped up.

    `levels_by_step[i]` is the level count observed *before* choosing the
    i-th action, so the index returned is the action count at which the
    level-up became visible. Jumps of more than one are expanded, so a
    two-level jump in a single step reports that index twice rather than
    silently losing a completion.
    """
    indices: list[int] = []
    previous = None
    for step, levels in enumerate(levels_by_step):
        if previous is None:
            previous = levels
            continue
        if levels > previous:
            indices.extend([step] * (levels - previous))
        previous = levels
    return indices


def environment_rows(scorecard: Any) -> list[dict[str, Any]]:
    """Flatten a scorecard into one row per game.

    Tolerant by construction: the scorecard is a third-party pydantic model
    whose optional fields are dropped when None, and a sweep summary is worth
    keeping even when the scorer declined to score it (it does that whenever
    human baselines are unavailable, which is the case on hidden games).
    """
    rows: list[dict[str, Any]] = []
    for env in getattr(scorecard, "environments", []) or []:
        runs = getattr(env, "runs", None) or [env]
        for run in runs:
            rows.append(
                {
                    "game_id": getattr(run, "id", None) or getattr(env, "id", None),
                    "score": getattr(run, "score", None),
                    "levels_completed": getattr(run, "levels_completed", None),
                    "actions": getattr(run, "actions", None),
                    "resets": getattr(run, "resets", None),
                    "state": _as_str(getattr(run, "state", None)),
                    "completed": getattr(run, "completed", None),
                    "level_scores": getattr(run, "level_scores", None),
                    "level_actions": getattr(run, "level_actions", None),
                    "level_baseline_actions": getattr(
                        run, "level_baseline_actions", None
                    ),
                    "message": getattr(run, "message", None),
                }
            )
    return rows


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value)


def build_summary(
    *,
    run_id: str,
    max_steps: int,
    games: Sequence[str],
    observed: Mapping[str, Mapping[str, Any]],
    scorecard: Any = None,
    aggregate_score: Any = None,
    fingerprint: Mapping[str, Any] | None = None,
    seed: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Assemble the summary document.

    `observed` is what the sweep itself watched, keyed by game id: the final
    state, the agent's own action counter, and `completion_indices`. It is
    kept **alongside** the scorer's numbers rather than merged into them,
    because the two answer different questions and disagreeing is informative:
    the scorer charges a level for every action spent failing at it, while the
    observed index says when the level-up was actually seen.
    """
    scored = environment_rows(scorecard) if scorecard is not None else []
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "max_steps": max_steps,
            "games_requested": list(games),
            # The sweep seed. With it plus the git sha, any run in this
            # file can be re-entered exactly — which is what makes a
            # suspicious result investigable rather than merely noted.
            "seed": seed,
            "git": dict(fingerprint) if fingerprint else None,
        },
        "aggregate_score": aggregate_score,
        "observed": {
            game_id: dict(fields) for game_id, fields in sorted(observed.items())
        },
        "scored": scored,
        "notes": notes,
    }


def write_summary(summary: Mapping[str, Any], results_dir: Path) -> Path:
    """Write the summary to `results_dir`, creating it if needed."""
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{summary['run_id']}.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n",
                    encoding="utf-8")
    return path
