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
from collections import Counter, defaultdict
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

sys.path.insert(0, str(ROOT / "agent"))
import perception  # noqa: E402

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


def _relative_to_board(agent, relative_cells) -> list[list[int]]:
    """Displacement-space cells (obstacles, visited) -> absolute board pixels.

    `ObstacleMap` and `MoveModel.visited` are keyed in the same relative
    space as `displacement` — not board pixels — because that space is
    what survives a level's own coordinate system moving around under it.
    `origin_anchor()` is the one already-existing bridge back to the
    board, and it stays None until a translation has actually confirmed
    where the origin is; empty here means exactly that, not "nothing
    known".
    """
    origin = agent.moves.origin_anchor()
    if origin is None:
        return []
    return [[origin[0] + dx, origin[1] + dy] for dx, dy in relative_cells]


def _offboard_fraction(agent, frame) -> float | None:
    """What share of known obstacles convert to coordinates off the board."""
    blocked = {pos for pos, _a in (getattr(agent.obstacles, "_blocked", {}) or {})}
    if not blocked:
        return None
    cells = _relative_to_board(agent, blocked)
    if not cells:
        return None
    grid = frame.frame[-1] if frame.frame else []
    rows = len(grid); cols = len(grid[0]) if rows else 0
    off = sum(1 for x, y in cells if not (0 <= x < cols and 0 <= y < rows))
    return round(off / len(cells), 3)


def _weighted_cells(counts: dict) -> list[list]:
    """A cell->count dict as [x, y, count] triples, for a heatmap."""
    return [[x, y, n] for (x, y), n in counts.items()]


def action_signature(transitions: dict) -> dict:
    """Per action, which colour transitions it causes — and which are its alone.

    The agent does not track this. `_action_changes` counts only *whether*
    something changed, and the colour census (`_recolour_counts`) is global
    rather than per action, so "ACTION5 is the only thing that ever turns
    colour 0 into colour 15" is invisible to it by construction.

    Measured on cd82: ACTION1-4 all produce the same 5<->15 / 2<->5 churn,
    while ACTION5 alone produces 0->15 across 400 cells and nothing else
    ever does. That is a strong, cheap, action-specific signal sitting in
    plain sight. Computed here in the viewer rather than in the agent so
    it costs the shipped hot path nothing while the question of whether to
    *act* on it is still open.
    """
    owners: dict[tuple, set] = {}
    for act, pairs in transitions.items():
        for pair in pairs:
            owners.setdefault(pair, set()).add(act)
    out = {}
    for act, pairs in transitions.items():
        ranked = sorted(pairs.items(), key=lambda kv: -kv[1])[:6]
        out[act] = [
            {"from": f, "to": t, "cells": n, "unique": len(owners[(f, t)]) == 1}
            for (f, t), n in ranked
        ]
    return out


def snapshot(agent, frame, action, step: int, transitions=None) -> dict:
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
        # `set_data` stores a pydantic ComplexAction on `.action_data` — not
        # a plain dict on `.data`, which is what this read first and why
        # every click coordinate came back empty.
        data = getattr(action, "action_data", None)
        if data is not None:
            payload = {"x": getattr(data, "x", None), "y": getattr(data, "y", None)}

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
            # Absolute board pixel matching `displacement`, once a
            # translation has actually been observed (None until then).
            # This is what lets the viewer draw a "you are here" marker
            # on the real frame instead of a bare coordinate pair.
            "anchor": list(agent.moves.anchor) if agent.moves.anchor else None,
            "moves": {a.name: list(v) for a, v in moves.items()},
            "visited": len(agent.moves.visited),
            "obstacles": len(getattr(agent.obstacles, "_blocked", {}) or {}),
            # Obstacles live in relative displacement space. If the move
            # map is wrong -- as it is on any game with two controllable
            # objects -- converting them to board pixels lands off-board.
            # Measured on wa30: 94% of them, at coordinates from -193 to
            # 221 on a 64x64 board. Reporting the ratio turns a silently
            # clipped mask into a visible diagnostic.
            "obstacles_offboard": _offboard_fraction(agent, frame),
            "stamina_fraction": agent.stamina.stamina_fraction,
            "stamina_colour": agent.stamina.stamina_colour,
            "acts_locally": agent.clicks.acts_locally,
            # Which colour each action was last seen to move. On a
            # single-avatar game every action maps to one colour; two
            # colours here means two independently controllable objects
            # that the move map is currently conflating.
            "controlled_by_action": dict(agent._controlled_by_action),
            # The scene as the agent groups it. cd82 is 15 regions — a
            # completely tractable description — which is the argument for
            # this layer: a number that small can be reasoned about, while
            # 4096 pixels cannot.
            # On screen now. The tracker also remembers what has gone (so
            # a bar that empties is recognised when it refills), and that
            # memory used to be shown here as if it were the scene: on cd82
            # the panel listed the bucket twice, once where it was and once
            # where it had been, and the mask painted both.
            "entity_count": len(agent.regions.live),
            # The canvas as the tracked entity it is: the largest live
            # region of the background colour. Shown in the Belief panel
            # rather than as a standalone "background" perception.
            "canvas": next(
                ({"id": rid, "colour": colour}
                 for rid, (colour, cells) in sorted(
                     agent.regions._tracked.items(), key=lambda kv: -len(kv[1][1]))
                 if colour == agent._background and rid in agent.regions.live),
                None),
            "ghost_count": len(agent.regions._tracked) - len(agent.regions.live),
            "stamina_entity": agent.stamina.stamina_region,
            # Per action, the rotations it has been seen to cause. Sits
            # beside the move map because it answers the same question —
            # what does this button do to the world — for the rigid motion
            # translation cannot express.
            "rotations_by_action": {a.name: dict(k)
                                    for a, k in agent._action_rotations.items()},
            "interest_cells": len(agent.interest),
            "interest_peak": round(agent.interest.peak, 3) if len(agent.interest) else 0,
            "route_len": len(agent.route),
            "pending_vanish": agent._pending_vanish,
            # Every spatial signal that already exists but was previously
            # thrown away after updating a scalar counter — each one
            # answers a different question from the layer stack in
            # agent/my_agent.py's own docstring:
            #   interest     "where should I look next?"      (attention)
            #   affect       "what does this action change,    (control's
            #                 besides me?"                      complement)
            #   environment  "what resists me, and where?"     (constraints)
            #   explored     "where have I already been?"      (control)
            #   clicked      "where has ACTION6 already aimed, (attention)
            #                 and did it do anything?"
            # Capped at 120 cells each so a dense map still produces a
            # small, comparable-across-steps payload; every game measured
            # so far concentrates mass in well under that.
            "masks": {
                "interest": [[x, y, round(w, 2)] for (x, y), w
                             in agent.interest.top_cells_with_weight(120)],
                # Every object confirmed to translate, weighted by its
                # colour index only so distinct objects render as visibly
                # distinct bands — the point of this mask is to show *how
                # many* controllable things there are, not how hot they are.
                "controlled": [[x, y, colour]
                               for colour, cells in agent._controlled_cells.items()
                               for x, y in cells][:120],
                "affect": [[x, y, 1] for x, y in agent._last_residual_cells[:120]],
                "clicked": _weighted_cells(getattr(agent.clicks, "_tries", {}) or {})[:120],
                # Every tracked region, weighted by its id so distinct
                # entities render as distinct bands.
                # The canvas is excluded: it is a region like any other,
                # but painting 3000+ cells of it hides every object the
                # mask exists to show.
                "entities": [[x, y, rid]
                             for rid, (colour, cells) in agent.regions._tracked.items()
                             if colour != agent._background
                             and rid in agent.regions.live
                             for x, y in cells][:1500],
                "click_effect": _weighted_cells(
                    getattr(agent.clicks, "_effect", {}) or {})[:120],
            },
        },
        # ── the brief: what a proposer would be sent, verbatim ───────────
        # Composed live by the agent's own Briefer, not reconstructed here,
        # so what the panel shows is exactly what would leave the agent.
        "brief": agent.brief.compose(agent, level=frame.levels_completed,
                                     available=frame.available_actions),
        # ── evidence accumulated per action ──────────────────────────────
        "evidence": {
            "tries": {a.name: n for a, n in agent._action_tries.items()},
            "changes": {a.name: n for a, n in agent._action_changes.items()},
            "tries_total": {a.name: n for a, n in agent._action_tries_total.items()},
            "changes_total": {a.name: n
                              for a, n in agent._action_changes_total.items()},
            "level_ups": {a.name: n for a, n in agent._action_level_ups.items()},
            "vanishes": {a.name: n for a, n in agent._action_vanishes.items()},
            "interactions": {a.name: n for a, n in agent._action_interactions.items()},
            # Viewer-computed, not agent state — see `action_signature`.
            "signature": action_signature(transitions or {}),
            # What each entity IS to the agent, composed from everything
            # below it. Roles are relational (how does this thing's
            # behaviour correlate with my actions), never semantic, and
            # "unassigned" is a real answer.
            # Ordered by how much the role tells you, not by how much
            # evidence backs it: a dozen "never changes" rows are true and
            # useless, and they were crowding out the one entity an action
            # actually drives.
            # ENVIRONMENT is excluded: "never changes" is true of most of
            # the board and tells you nothing, and a dozen such rows were
            # crowding out the entities an action actually drives.
            # `live` says whether the entity is on screen this frame. A
            # belief outlives its entity on purpose; the panel shows the
            # off-screen ones dimmed and last, so a role earned by a thing
            # that is not there is never mistaken for the scene.
            "beliefs": sorted(
                ({"id": rid, "colour": colour, "role": role, "why": why,
                  "strength": round(strength, 3), "live": bel.live}
                 for (rid, colour, role, why, strength), bel in
                 zip(agent.belief.summary(), agent.belief.ordered())
                 if role not in ("unassigned", "environment")),
                key=lambda b: (not b["live"],
                               {"control": 0, "affect": 1, "context": 2}[b["role"]],
                               -b["strength"]),
            )[:12],
            "belief_roles": {
                r: sum(1 for b in agent.belief.ordered() if b.live and b.role == r)
                for r in ("control", "affect", "context", "environment", "unassigned")
            },
            "belief_ghosts": sum(1 for b in agent.belief.ordered() if not b.live),
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

    # Cumulative per-action colour transitions, attributed to the action that
    # *caused* the change — so to the previous step's choice, not this one.
    transitions: dict[str, Counter] = defaultdict(Counter)
    previous_action: list = [None]

    def wrapped(frames, latest_frame):
        if len(frames) >= 2 and previous_action[0] is not None:
            lost, gained = perception.lost_and_gained(frames[-2], latest_frame)
            for c_from, from_cells in lost.items():
                for c_to, to_cells in gained.items():
                    overlap = len(from_cells & to_cells)
                    if overlap:
                        transitions[previous_action[0]][(c_from, c_to)] += overlap

        action = original(frames, latest_frame)
        # Snapshot AFTER the decision: the layers have observed this frame and
        # `_decision` is populated, so the panel shows the state the choice was
        # actually made from.
        steps.append(snapshot(agent, latest_frame, action, len(steps), transitions))
        previous_action[0] = action.name
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
