"""H006 Step 2: the agent's internal state S_t along a trajectory, and what
it already resolves of the pixel aliasing.

`alias_probe.py` keys a transition by the settled frame — the agent's
whole *visible* input. But the agent does not decide from pixels; it
decides from S_t: tracked entities with ids and roles, the residual vector
over their pairs, its displacement since the attempt began, the stamina
fraction. Two histories that end in the same frame can differ in S_t
(entity ids carry attempt history; displacement carries the route), so
the first question before inventing any latent variable is how much of
the aliasing S_t already resolves — and how the one-step forecast (H003)
does on exactly those contexts.

`trace` plays a game with the real agent (`MyAgent`, unmodified) and taps
`_select` — the point in `choose_action` after every layer has folded the
new frame in — to write one JSON line per step: the same fields as a
standard recording (so `alias_probe.py` reads it unchanged) plus
`state_t`. No re-implementation of any layer; the seed makes the run
reproduce a `play_local.py` run with the same seed exactly (verified by
`--check` against that recording's action stream — the determinism claim
the replay harness proved at 50/50, now for free on every trace).

`analyse` reads trace dirs and prints, per game:
    aliased in pixels / still aliased keyed by S_t / resolved by S_t
    one-step forecast accuracy on the aliased contexts vs all steps

Usage:
    .venv/bin/python scripts/latent_probe.py trace --game su15,sk48 --seed 3 [--max-steps 400]
    .venv/bin/python scripts/latent_probe.py trace --game su15 --seed 3 --check recordings/<run>/su15.jsonl
    .venv/bin/python scripts/latent_probe.py analyse recordings/latent/seed*/ [--with-counter]

Traces land in `recordings/latent/seed<N>/<game>.jsonl` (gitignored with
the rest of recordings/).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "agent"))

from alias_probe import _action_key, _hash, _load  # noqa: E402
import predictor as _predictor  # noqa: E402


# ── trace ───────────────────────────────────────────────────────────────

def _descriptor_key(colour: int, cells) -> str:
    """What an entity looks like, position removed: colour + shape."""
    x0 = min(c[0] for c in cells)
    y0 = min(c[1] for c in cells)
    shape = sorted((x - x0, y - y0) for x, y in cells)
    return hashlib.md5(f"{colour}:{shape}".encode()).hexdigest()[:10]


def state_of(agent) -> dict:
    """S_t as the layers hold it at decision time. Everything here is read
    from the agent, nothing is computed that it does not already have."""
    tracked = agent.regions._tracked
    live = agent.regions.live
    control = set(agent._control_ids())
    entities = []
    for rid in sorted(live):
        if rid not in tracked:
            continue
        colour, cells = tracked[rid]
        b = agent.belief._beliefs.get(rid)
        xs = [c[0] for c in cells]; ys = [c[1] for c in cells]
        entities.append({
            "id": rid, "colour": colour, "size": len(cells),
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
            "desc": _descriptor_key(colour, cells),
            "role": b.role if b is not None else None,
            "control": rid in control,
        })
    residuals = [[list(map(str, k)) if isinstance(k, tuple) else str(k), v]
                 for k, v in sorted(agent.relations.snapshot().items(), key=lambda kv: str(kv[0]))]
    return {
        "level_step": agent._level_step,
        "displacement": list(agent.moves.displacement),
        "stamina_fraction": agent.stamina.stamina_fraction,
        "entities": entities,
        "residuals": residuals,
        # The score of the forecast made at the previous decision, against
        # this frame: {layer: {hits, misses, undecidable, abstained}}.
        "forecast_score": agent.predictor.last or None,
        # H008: the effect table the NEXT forecast will be read from, and
        # what the previous action actually did — enough to score k-step
        # rollouts offline with the same `predictor.rollout` the agent uses.
        "effects": {str(rid): {a: [list(e), round(c, 3)] for a, (e, c) in row.items()}
                    for rid, row in _predictor.effect_table(agent.belief).items()},
        "last_effects": {str(rid): list(e) for rid, e in agent.belief.last_effects.items()},
    }


def make_tap_class(MyAgentCls, out_path: Path):
    class Tap(MyAgentCls):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._tap_file = out_path.open("w", encoding="utf-8")
            self._tap_n = 0
            self._tap_pending = None

        def choose_action(self, frames, latest_frame):
            action = super().choose_action(frames, latest_frame)
            self._tap_n += 1
            grid = latest_frame.frame[-1] if latest_frame.frame else None
            entry = {
                "step": self._tap_n,
                "state": str(latest_frame.state),
                "levels_completed": latest_frame.levels_completed,
                "action": action.name,
                "data": (action.action_data.model_dump()
                         if getattr(action, "action_data", None) is not None else None),
                "available_actions": list(latest_frame.available_actions or []),
                "frame": ["".join(f"{v:x}" for v in row) for row in grid] if grid else None,
                # None on the RESET path: the layers did not run.
                "state_t": self._tap_pending,
            }
            self._tap_pending = None
            self._tap_file.write(json.dumps(entry) + "\n")
            self._tap_file.flush()
            return action

        def _select(self, latest_frame, candidates):
            self._tap_pending = state_of(self)
            return super()._select(latest_frame, candidates)

    return Tap


def trace(games: list[str], seed: int, max_steps: int, check: Path | None) -> None:
    VENDOR = ROOT / "vendor" / "ARC-AGI-3-Agents"
    sys.path.insert(0, str(VENDOR))
    import arc_agi  # noqa: E402
    from arc_agi import OperationMode  # noqa: E402
    from play_local import load_my_agent_class  # noqa: E402

    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
    Cls = load_my_agent_class()
    Cls.MAX_ACTIONS = max_steps
    Cls.SEED = seed
    out_dir = ROOT / "recordings" / "latent" / f"seed{seed}"
    out_dir.mkdir(parents=True, exist_ok=True)
    for game in games:
        out = out_dir / f"{game}.jsonl"
        Tap = make_tap_class(Cls, out)
        env = arc.make(game)
        agent = Tap(card_id="latent-probe", game_id=game, agent_name=f"latent.{game}",
                    ROOT_URL="http://localhost", record=False, arc_env=env, tags=["latent-probe"])
        agent.main()
        steps = _load(out)
        print(f"{game} seed={seed}: {len(steps)} steps, levels={steps[-1]['levels_completed']} -> {out}")
        if check is not None:
            ref = _load(check)
            mine = [(_action_key(s)) for s in steps]
            theirs = [(_action_key(s)) for s in ref]
            n = min(len(mine), len(theirs))
            first = next((i for i in range(n) if mine[i] != theirs[i]), None)
            if first is None and len(mine) == len(theirs):
                print(f"  check: action stream identical to {check.name} ({n} steps)")
            else:
                print(f"  check: DIVERGES at step {first if first is not None else n + 1} "
                      f"(lengths {len(mine)} vs {len(theirs)})")


# ── analyse ─────────────────────────────────────────────────────────────

def _state_key(st: dict | None) -> str | None:
    if st is None:
        return None
    ents = [(e["id"], e["colour"], e["desc"], tuple(e["bbox"]), e["role"]) for e in st["entities"]]
    body = json.dumps([ents, st["displacement"], st["stamina_fraction"], st["residuals"]], sort_keys=True)
    return hashlib.md5(body.encode()).hexdigest()[:12]


def _counter(steps: list[dict]) -> list[int]:
    """Actions since the attempt began — Day 1's meter variable, which S_t
    does not carry (the layers hold what is on screen, not how long)."""
    out, n = [], 0
    for i, s in enumerate(steps):
        if i == 0 or steps[i - 1]["action"] == "RESET" or s["levels_completed"] != steps[i - 1]["levels_completed"]:
            n = 0
        else:
            n += 1
        out.append(n)
    return out


def analyse(dirs: list[Path], with_counter: bool = False) -> None:
    files = sorted(f for d in dirs for f in d.glob("*.jsonl"))
    per = collections.defaultdict(lambda: collections.Counter())
    for f in files:
        steps = _load(f)
        g = f.stem
        H = [_hash(s["frame"]) if s.get("frame") else None for s in steps]
        A = [_action_key(s) for s in steps]
        S = [_state_key(s.get("state_t")) for s in steps]
        if with_counter:
            C = _counter(steps)
            S = [None if k is None else f"{k}+{c}" for k, c in zip(S, C)]
        pix = collections.defaultdict(list)
        for i in range(len(steps) - 1):
            if steps[i + 1]["step"] == steps[i]["step"] + 1 and H[i] and S[i]:
                pix[(H[i], A[i])].append(i)
        for _, idx in pix.items():
            outs = {H[i + 1] for i in idx}
            if len(idx) < 2:
                continue
            per[g]["repeated"] += 1
            if len(outs) < 2:
                continue
            per[g]["aliased_pixels"] += 1
            by_state = collections.defaultdict(set)
            for i in idx:
                by_state[S[i]].add(H[i + 1])
            if any(len(v) > 1 for v in by_state.values()):
                per[g]["still_by_state"] += 1
            elif any(len([i for i in idx if S[i] == k]) >= 2 for k in by_state):
                per[g]["resolved_by_state"] += 1
            else:
                per[g]["singleton_by_state"] += 1
            # the forecast made AT an aliased context is scored on the next line
            for i in idx:
                sc = steps[i + 1].get("state_t", {}) and steps[i + 1]["state_t"].get("forecast_score")
                if sc:
                    for layer in ("entity", "pair"):
                        per[g][f"al_{layer}_hits"] += sc[layer]["hits"]
                        per[g][f"al_{layer}_n"] += sc[layer]["hits"] + sc[layer]["misses"]
        for s in steps:
            sc = (s.get("state_t") or {}).get("forecast_score")
            if sc:
                for layer in ("entity", "pair"):
                    per[g][f"all_{layer}_hits"] += sc[layer]["hits"]
                    per[g][f"all_{layer}_n"] += sc[layer]["hits"] + sc[layer]["misses"]

    def acc(c, pre, layer):
        n = c[f"{pre}_{layer}_n"]
        return f"{c[f'{pre}_{layer}_hits'] / n:5.0%}" if n else "    -"

    print(f"{'game':5} {'rep':>5} {'aliased':>8} | by S_t: {'still':>5} {'resolved':>8} {'singleton':>9} | "
          f"1-step acc on aliased vs all: entity {'al':>5} {'all':>5}  pair {'al':>5} {'all':>5}")
    for g, c in sorted(per.items()):
        print(f"{g:5} {c['repeated']:5} {c['aliased_pixels']:8} |         {c['still_by_state']:5} "
              f"{c['resolved_by_state']:8} {c['singleton_by_state']:9} |                              "
              f"{acc(c, 'al', 'entity')} {acc(c, 'all', 'entity')}       {acc(c, 'al', 'pair')} {acc(c, 'all', 'pair')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trace")
    t.add_argument("--game", required=True)
    t.add_argument("--seed", type=int, required=True)
    t.add_argument("--max-steps", type=int, default=400)
    t.add_argument("--check", type=Path, default=None,
                   help="a play_local recording of the same game+seed to compare action streams with")
    a = sub.add_parser("analyse")
    a.add_argument("dirs", nargs="+", type=Path)
    a.add_argument("--with-counter", action="store_true",
                   help="add actions-since-reset to the S_t key (Day 1's meter variable)")
    args = ap.parse_args()
    if args.cmd == "trace":
        trace([g.strip() for g in args.game.split(",")], args.seed, args.max_steps, args.check)
    else:
        analyse(args.dirs, args.with_counter)


if __name__ == "__main__":
    main()
