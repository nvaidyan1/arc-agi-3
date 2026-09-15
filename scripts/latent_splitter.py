"""H006 Step 3: candidate latent variables, scored as splitters.

A latent variable is admitted only if it splits an aliased context's
outcomes (`research/hypotheses/H006_latent_state.md`). This script
enumerates a small family of **history-derived** candidates over the
S_t traces `latent_probe.py trace` writes, and scores each one on every
pixel-aliased context of every game:

    resolved   every value-group of the context has ONE outcome, and at
               least one group has >= 2 visits  (the variable explains it)
    singleton  every group has one visit         (vacuous: the re-key only
                                                  made the visits unique)
    still      some group has >= 2 outcomes      (the variable is refuted
                                                  for this context)

Only history-derived candidates are enumerated. A visible descriptor
(H006's "kind a") is a function of the current frame and so cannot, by
construction, tell two pixel-identical contexts apart — it is H007's
*condition* kind, not a splitter. Day 1 found the dominant hidden
variable to be a sub-cell resource counter (actions since reset), so that
is candidate #1 and the bar the others must beat.

Candidates, all computed from the trace alone (actions, frames, S_t):
    n_reset            actions since the attempt began
    n_level            actions since the level began
    n_moved            steps on which the CONTROL thing's displacement changed
    n_changed          steps on which the frame changed
    n_<A>              count of action A since reset, and its parity mod 2/3/4
    last_click_colour  colour of the cell last clicked (None if none since reset)
    last_click_rel     last click's (sign dx, sign dy) from the CONTROL thing's bbox centre
    presses_since_click  non-click actions since the last click
    same_run           length of the current run of identical actions
    last_changer       the last action under which the frame changed

Shuffle control: each candidate's values are permuted across all visits
of the game (preserving the value pool); `null` is the resolved count
under that permutation, averaged over a few draws. A candidate whose
resolved count is not well above its null is fitting noise.

Usage:
    .venv/bin/python scripts/latent_splitter.py recordings/latent/seed*/ [--game su15,sk48] [--top 5]
"""
from __future__ import annotations

import argparse
import collections
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from alias_probe import _action_key, _hash, _load  # noqa: E402

ACTIONS = ("ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6", "ACTION7")


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def candidates_for(steps: list[dict]) -> dict[str, list]:
    """Per step index, every candidate's value. Pure function of the trace."""
    n = len(steps)
    feats: dict[str, list] = collections.defaultdict(lambda: [None] * n)
    H = [_hash(s["frame"]) if s.get("frame") else None for s in steps]
    n_reset = n_level = n_moved = n_changed = 0
    counts = collections.Counter()
    last_click_colour = None
    last_click_rel = None
    presses_since_click = 0
    same_run = 0
    last_changer = None
    prev_disp = None
    for i, s in enumerate(steps):
        prev = steps[i - 1] if i else None
        new_attempt = prev is None or prev["action"] == "RESET"
        new_level = prev is not None and s["levels_completed"] != prev["levels_completed"]
        if new_attempt or new_level:
            n_reset = 0
            counts = collections.Counter()
            last_click_colour = last_click_rel = None
            presses_since_click = 0
            prev_disp = None
        if new_level or prev is None:
            n_level = 0
            n_moved = 0
        st = s.get("state_t") or {}
        disp = tuple(st.get("displacement", (0, 0))) if st else None
        if prev is not None and not new_attempt and not new_level:
            n_reset += 1
            n_level += 1
            if H[i] != H[i - 1]:
                n_changed += 1
                last_changer = prev["action"]
            if disp is not None and prev_disp is not None and disp != prev_disp:
                n_moved += 1
        prev_disp = disp
        same_run = same_run + 1 if prev is not None and s["action"] == prev["action"] else 0
        feats["n_reset"][i] = n_reset
        feats["n_level"][i] = n_level
        feats["n_moved"][i] = n_moved
        feats["n_changed"][i] = n_changed
        for a in ACTIONS:
            feats[f"n_{a[-1]}"][i] = counts[a]
            for m in (2, 3, 4):
                feats[f"n_{a[-1]}_mod{m}"][i] = counts[a] % m
        feats["last_click_colour"][i] = last_click_colour
        feats["last_click_rel"][i] = last_click_rel
        feats["presses_since_click"][i] = presses_since_click
        feats["same_run"][i] = same_run
        feats["last_changer"][i] = last_changer
        # fold this step's action into the history for the next step
        a = s["action"]
        counts[a] += 1
        if a == "ACTION6" and s.get("data") and s.get("frame"):
            x, y = s["data"]["x"], s["data"]["y"]
            last_click_colour = s["frame"][y][x]
            ctrl = [e for e in st.get("entities", []) if e.get("control")]
            if ctrl:
                bx = (ctrl[0]["bbox"][0] + ctrl[0]["bbox"][2]) / 2
                by = (ctrl[0]["bbox"][1] + ctrl[0]["bbox"][3]) / 2
                last_click_rel = (_sign(x - bx), _sign(y - by))
            else:
                last_click_rel = ("noctrl",)
            presses_since_click = 0
        elif a != "RESET":
            presses_since_click += 1
    return dict(feats)


def score(contexts: list[list[tuple[str, int]]], outcome: dict, values: dict) -> collections.Counter:
    """contexts: per aliased context, its visits as (file, index).
    outcome[(file, i)] -> next-frame hash; values[(file, i)] -> candidate value."""
    c = collections.Counter()
    for visits in contexts:
        groups = collections.defaultdict(list)
        for v in visits:
            groups[values[v]].append(outcome[v])
        if any(len(set(o)) > 1 for o in groups.values()):
            c["still"] += 1
        elif any(len(o) >= 2 for o in groups.values()):
            c["resolved"] += 1
        else:
            c["singleton"] += 1
    return c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+", type=Path)
    ap.add_argument("--game", default=None)
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--null-draws", type=int, default=5)
    args = ap.parse_args()
    wanted = set(args.game.split(",")) if args.game else None
    files = sorted(f for d in args.dirs for f in d.glob("*.jsonl") if not wanted or f.stem in wanted)
    by_game: dict[str, list[Path]] = collections.defaultdict(list)
    for f in files:
        by_game[f.stem].append(f)
    rng = random.Random(0)
    for g, fs in sorted(by_game.items()):
        outcome: dict = {}
        values: dict[str, dict] = collections.defaultdict(dict)
        pix = collections.defaultdict(list)
        for f in fs:
            steps = _load(f)
            H = [_hash(s["frame"]) if s.get("frame") else None for s in steps]
            A = [_action_key(s) for s in steps]
            feats = candidates_for(steps)
            for i in range(len(steps) - 1):
                if steps[i + 1]["step"] != steps[i]["step"] + 1 or not H[i] or not H[i + 1]:
                    continue
                v = (str(f), i)
                pix[(H[i], A[i])].append(v)
                outcome[v] = H[i + 1]
                for name, col in feats.items():
                    values[name][v] = col[i]
        contexts = [vs for vs in pix.values() if len(vs) >= 2 and len({outcome[v] for v in vs}) >= 2]
        repeated = sum(1 for vs in pix.values() if len(vs) >= 2)
        print(f"\n{g}: {len(fs)} traces, {repeated} repeated contexts, {len(contexts)} aliased")
        if not contexts:
            continue
        rows = []
        visits_all = [v for vs in contexts for v in vs]
        for name, vals in values.items():
            c = score(contexts, outcome, vals)
            nulls = []
            for _ in range(args.null_draws):
                pool = [vals[v] for v in visits_all]
                rng.shuffle(pool)
                shuffled = dict(vals)
                shuffled.update(zip(visits_all, pool))
                nulls.append(score(contexts, outcome, shuffled)["resolved"])
            rows.append((c["resolved"], -c["still"], name, c, sum(nulls) / len(nulls)))
        rows.sort(reverse=True)
        print(f"  {'candidate':22} {'resolved':>8} {'singleton':>9} {'still':>6} {'null':>6}")
        for res, _, name, c, null in rows[:args.top]:
            print(f"  {name:22} {c['resolved']:8} {c['singleton']:9} {c['still']:6} {null:6.1f}")


if __name__ == "__main__":
    main()
