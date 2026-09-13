"""Run `agent/my_agent.py` locally against a real ARC-AGI-3 game.

This is the fast inner-loop: no Docker, no Kaggle round-trip. Uses the
`arc-agi` PyPI package to host the game engine and the ARC-AGI-3-Agents
framework's `Agent.main()` loop to drive it — exactly what the Kaggle
gateway does, just in-process.

Usage:
    .venv/bin/python scripts/play_local.py --game ls20 --max-steps 200
    .venv/bin/python scripts/play_local.py --list
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VENDOR = ROOT / "vendor" / "ARC-AGI-3-Agents"
if not VENDOR.exists():
    raise SystemExit(f"Framework not found at {VENDOR}. Run `make setup` first.")
sys.path.insert(0, str(VENDOR))

import arc_agi
from arc_agi import OperationMode


def _wrap_with_step_logging(choose_action: Callable, log_path: Path) -> Callable:
    """Wrap an agent's bound `choose_action` to append one JSON line per step.

    NOTE: this exists instead of the framework's built-in `record=True`
    recorder because that recorder's `FrameData.action_input` is always
    left at its default (see `_convert_raw_frame_data` in
    vendor/ARC-AGI-3-Agents/agents/agent.py) — it never actually records
    which action was taken or why, only the raw frame. This wrapper
    captures the useful part: what the agent chose, its stated reasoning,
    and how many cells the *previous* action's effect touched.
    """
    log_file = log_path.open("a", encoding="utf-8")

    def wrapped(frames, latest_frame):
        action = choose_action(frames, latest_frame)

        diff_cells = None
        if len(frames) >= 2 and frames[-2].frame and latest_frame.frame:
            prev_grid, latest_grid = frames[-2].frame[0], latest_frame.frame[0]
            diff_cells = sum(
                1
                for prev_row, latest_row in zip(prev_grid, latest_grid)
                for prev_val, latest_val in zip(prev_row, latest_row)
                if prev_val != latest_val
            )

        entry = {
            "step": len(frames),
            "state": str(latest_frame.state),
            "levels_completed": latest_frame.levels_completed,
            "prev_action_diff_cells": diff_cells,
            "action": action.name,
            "reasoning": getattr(action, "reasoning", None),
        }
        log_file.write(json.dumps(entry) + "\n")
        log_file.flush()
        return action

    return wrapped


def load_my_agent_class():
    """Import MyAgent from agent/my_agent.py via importlib."""
    spec = importlib.util.spec_from_file_location(
        "user_agent_module", ROOT / "agent" / "my_agent.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit("Could not load agent/my_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "MyAgent"):
        raise SystemExit("agent/my_agent.py must define a class named `MyAgent`")
    return module.MyAgent


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--game", default=None,
                   help="Game id to play. If omitted, plays ALL available games "
                        "(mirrors what Kaggle does in competition rerun). "
                        "Comma-separated list also accepted, e.g. ls20,vc33.")
    p.add_argument("--max-steps", type=int, default=200,
                   help="Per-game cap on actions (overrides MyAgent.MAX_ACTIONS).")
    p.add_argument("--list", action="store_true",
                   help="List available games and exit.")
    p.add_argument("--render", default=None,
                   choices=[None, "terminal", "terminal-fast", "human"],
                   help="Optional rendering each step: 'terminal' (ANSI colors "
                        "in this shell, paced to the game's FPS), 'terminal-fast' "
                        "(same, no pacing delay), or 'human' (a live matplotlib "
                        "window — needs a real display, not headless SSH).")
    p.add_argument("--log", action=argparse.BooleanOptionalAction, default=True,
                   help="Write one JSON line per step (action, reasoning, "
                        "previous action's diff-cell count) to "
                        "recordings/<run-timestamp>/<game_id>.jsonl. On by "
                        "default; disable with --no-log. Use this instead of "
                        "watching a live render for debugging after the fact.")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # NORMAL = local execution; game source is downloaded on first call into
    # ./environment_files/ and cached for subsequent runs.
    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
    all_envs = arc.get_environments()

    if args.list:
        print(f"{len(all_envs)} environments:")
        for e in all_envs:
            print(f"  {e.game_id}: {getattr(e, 'title', '?')}")
        return

    # Resolve which games to play. `arc.make()` accepts the short game id
    # (e.g. "ls20") even though the EnvironmentInfo.game_id includes the
    # version suffix ("ls20-9607627b"), so we normalize to short ids.
    if args.game:
        wanted = {g.strip().split("-")[0] for g in args.game.split(",")}
        game_ids = [e.game_id.split("-")[0] for e in all_envs
                    if e.game_id.split("-")[0] in wanted]
        missing = wanted - set(game_ids)
        if missing:
            raise SystemExit(f"Unknown game id(s): {sorted(missing)}. Run --list.")
    else:
        game_ids = [e.game_id.split("-")[0] for e in all_envs]
        print(f"No --game specified; playing all {len(game_ids)} games "
              f"(this is what Kaggle does in competition rerun).\n")

    MyAgentCls = load_my_agent_class()
    if hasattr(MyAgentCls, "MAX_ACTIONS"):
        # Set it, don't min() it — the old form silently clamped to the
        # class default (80), so asking for a LARGER budget did nothing
        # and every "bigger budget" experiment secretly ran at 80.
        MyAgentCls.MAX_ACTIONS = args.max_steps

    log_dir = None
    if args.log:
        log_dir = ROOT / "recordings" / datetime.now().strftime("%Y%m%d-%H%M%S")
        log_dir.mkdir(parents=True, exist_ok=True)
        print(f"Logging one JSON line per step to {log_dir}/<game_id>.jsonl\n")

    per_game = []
    for i, game_id in enumerate(game_ids, 1):
        print(f"=== [{i}/{len(game_ids)}] {game_id} ===")
        env = arc.make(game_id, render_mode=args.render)
        if env is None:
            print(f"  could not create env for {game_id!r}, skipping")
            continue

        agent = MyAgentCls(
            card_id="local-dev",
            game_id=game_id,
            agent_name=f"MyAgent.local.{game_id}",
            ROOT_URL="http://localhost",
            record=False,
            arc_env=env,
            tags=["local-dev"],
        )
        if log_dir is not None:
            agent.choose_action = _wrap_with_step_logging(
                agent.choose_action, log_dir / f"{game_id}.jsonl"
            )
        agent.main()

        final = agent.frames[-1]
        per_game.append((game_id, final.state, final.levels_completed,
                         agent.action_counter))
        print(f"  → state={final.state}, levels_completed={final.levels_completed}, "
              f"actions={agent.action_counter}")

    sc = arc.get_scorecard()
    print("\n========= SUMMARY =========")
    for gid, state, levels, actions in per_game:
        print(f"  {gid:8} levels={levels:3}  actions={actions:5}  state={state}")
    score_val = sc.score if hasattr(sc, "score") else sc
    print(f"\nAggregate scorecard score: {score_val}")
    if log_dir is not None:
        print(f"Per-step logs written to {log_dir}/")


if __name__ == "__main__":
    main()
