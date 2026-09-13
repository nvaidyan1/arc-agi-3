"""Step through one run and watch the agent think.

Every sweep so far has reported an outcome and hidden the reasoning. When a
run does something strange — sp80 clearing level 1 in 9 actions, cd82 failing
15 attempts with twelve times the budget it needs — the score says it happened
and nothing says why.

This runs the real agent in-process, captures the complete internal state
before and after every decision, then writes a self-contained page you step
through one keypress at a time: what changed, what each layer currently
believes, and which branch of `_select` actually fired.

Two properties make it worth trusting:

  * It reads the **live objects**, not a log, so it shows what the agent
    actually held — not what someone remembered to serialise. Adding a layer
    means adding it to `_snapshot` and nothing else.
  * The run is **seeded**, so what you watch is the run you are debugging. Any
    sweep summary records its seed; pass it here and you re-enter that exact
    run. (Before this existed the RNG mixed in wall-clock time and a
    per-process-salted `hash()`, so no run could ever be revisited.)

Usage:
    .venv/bin/python scripts/recap.py --game cd82 --max-steps 400
    .venv/bin/python scripts/recap.py --game sp80 --seed 1556935581 --open

Keys in the page: space/right = next, left = back, j = jump to step,
l = next level-up, d = next death, v = next vanish, b = next blocked move,
t = next non-epsilon decision, home/end = first/last.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import random
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

VENDOR = ROOT / "vendor" / "ARC-AGI-3-Agents"
if not VENDOR.exists():
    raise SystemExit(f"Framework not found at {VENDOR}. Run `make setup` first.")
sys.path.insert(0, str(VENDOR))

import arc_agi  # noqa: E402
from arc_agi import OperationMode  # noqa: E402

OUT_DIR = ROOT / "results" / "recaps"


def load_my_agent_class():
    spec = importlib.util.spec_from_file_location(
        "user_agent_module", ROOT / "agent" / "my_agent.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit("Could not load agent/my_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MyAgent


def encode_grid(grid) -> str:
    """Flatten a grid to one hex character per cell.

    A 64x64 grid is 4096 cells; as JSON integers that is ~16KB per step and
    ~6MB over a full run, which makes the page slow to load and awkward to
    keep. One hex char per cell is 4KB per step instead, and ARC colour
    indices are 0-15 so nothing is lost. Values outside that range (should
    not occur) are clamped rather than silently corrupting the row length.
    """
    if not grid:
        return ""
    return "".join(
        f"{min(max(int(v), 0), 15):x}" for row in grid for v in row
    )


def _jsonable(value):
    """Make layer state JSON-safe without hiding its shape.

    Tuple keys (cell coordinates, displacements) are the norm in this agent
    and are not valid JSON keys, so they become "x,y" strings.
    """
    if isinstance(value, dict):
        return {
            (",".join(map(str, k)) if isinstance(k, tuple) else str(k)): _jsonable(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def snapshot(agent, frame, action, step: int) -> dict:
    """Everything worth knowing at one decision point.

    Deliberately reads the agent's live layer objects. If a layer is added
    later and not added here, its absence is visible as a missing panel
    rather than as a plausible-looking but stale value.
    """
    grid = frame.frame[-1] if frame.frame else []
    moves = agent.moves.learned_moves
    decision = dict(getattr(agent, "_decision", {}) or {})

    reasoning = getattr(action, "reasoning", None)
    payload = None
    if action.is_complex():
        data = getattr(action, "data", None) or {}
        payload = {"x": data.get("x"), "y": data.get("y")}

    return {
        "step": step,
        "state": str(frame.state),
        "levels_completed": frame.levels_completed,
        "score": getattr(frame, "score", None),
        "grid": encode_grid(grid),
        "rows": len(grid),
        "cols": len(grid[0]) if grid else 0,
        # The framework reports these as raw ints in some paths and as
        # GameAction members in others; accept either.
        "available": [getattr(a, "name", None) or f"ACTION{a}"
                      for a in (frame.available_actions or [])],
        # ── what each layer believes, right now ──────────────────────────
        "perception": {
            "background": agent._background,
            "displacement": list(agent.moves.displacement),
            "moves": {a.name: list(v) for a, v in moves.items()},
            "visited": len(agent.moves.visited),
            "obstacles": len(getattr(agent.obstacles, "_blocked", {}) or {}),
            "stamina_fraction": agent.stamina.stamina_fraction,
            "stamina_colour": agent.stamina.stamina_colour,
            "acts_locally": agent.clicks.acts_locally,
            "interest_cells": len(agent.interest),
            "interest_peak": round(agent.interest.peak, 3) if len(agent.interest) else 0,
            "interest_top": [list(c) for c in agent.interest.top_cells(8)],
            "route_len": len(agent.route),
            "pending_vanish": agent._pending_vanish,
        },
        # ── evidence accumulated per action ──────────────────────────────
        "evidence": {
            "tries": {a.name: n for a, n in agent._action_tries.items()},
            "changes": {a.name: n for a, n in agent._action_changes.items()},
            "level_ups": {a.name: n for a, n in agent._action_level_ups.items()},
            "vanishes": {a.name: n for a, n in agent._action_vanishes.items()},
            "interactions": {a.name: n for a, n in agent._action_interactions.items()},
        },
        # ── the decision itself ──────────────────────────────────────────
        "decision": {
            "tier": decision.get("tier"),
            "candidates": decision.get("candidates", []),
            "weights": _jsonable(decision.get("weights")),
            "novel": decision.get("novel"),
            "n_blocked": decision.get("n_blocked", 0),
            "all_blocked": decision.get("all_blocked", False),
            "action": action.name,
            "payload": payload,
            "reasoning": _jsonable(reasoning),
        },
    }


def capture(game_id: str, max_steps: int, seed: int | None) -> dict:
    MyAgent = load_my_agent_class()
    MyAgent.MAX_ACTIONS = max_steps
    if seed is None:
        seed = random.SystemRandom().randrange(2**31)
    MyAgent.SEED = seed

    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
    env = arc.make(game_id)
    if env is None:
        raise SystemExit(f"Could not create env for {game_id!r}.")

    agent = MyAgent(
        card_id="recap", game_id=game_id, agent_name=f"recap.{game_id}",
        ROOT_URL="http://localhost", record=False, arc_env=env, tags=["recap"],
    )

    steps: list[dict] = []
    original = agent.choose_action

    def wrapped(frames, latest_frame):
        action = original(frames, latest_frame)
        # Snapshot AFTER the decision: the layers have observed this frame and
        # `_decision` is populated, so the panel shows the state the choice was
        # actually made from.
        steps.append(snapshot(agent, latest_frame, action, len(steps)))
        return action

    agent.choose_action = wrapped
    agent.main()

    final = agent.frames[-1]
    baselines = []
    try:
        for info in arc.get_environments():
            if info.game_id.split("-")[0] == game_id:
                baselines = list(getattr(info, "baseline_actions", None) or [])
                break
    except Exception:  # noqa: BLE001 — a missing baseline must not lose the capture
        pass

    return {
        "game_id": game_id,
        "seed": seed,
        "agent_seed": getattr(agent, "seed", None),
        "max_steps": max_steps,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "final_state": str(final.state),
        "levels_completed": final.levels_completed,
        "actions": agent.action_counter,
        "baselines": baselines,
        "steps": steps,
    }


def write_page(run: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run['game_id']}-{run['seed']}.html"
    template = (Path(__file__).parent / "recap_template.html").read_text(
        encoding="utf-8"
    )
    payload = json.dumps(run, separators=(",", ":"))
    path.write_text(template.replace("/*__RUN_DATA__*/null", payload),
                    encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", required=True, help="Game id, e.g. cd82")
    ap.add_argument("--max-steps", type=int, default=400)
    ap.add_argument("--seed", type=int, default=None,
                    help="Replay an exact run. Sweep summaries record theirs.")
    ap.add_argument("--open", action="store_true",
                    help="Open the page in a browser when it is written.")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    print(f"Capturing {args.game} (seed "
          f"{args.seed if args.seed is not None else 'fresh'}) ...")
    run = capture(args.game, args.max_steps, args.seed)
    path = write_page(run, OUT_DIR)

    print(f"  {len(run['steps'])} steps, levels_completed={run['levels_completed']}, "
          f"final={run['final_state']}")
    print(f"  seed {run['seed']} — replay with: "
          f".venv/bin/python scripts/recap.py --game {args.game} --seed {run['seed']}")
    print(f"  page: {path}")
    if args.open:
        webbrowser.open(path.as_uri())


if __name__ == "__main__":
    main()
