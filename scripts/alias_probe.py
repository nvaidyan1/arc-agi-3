"""Perceptual aliasing: is the settled frame a sufficient state? Count.

Reviewer C (`docs/expert-reviews/reviewer_c_09_15_2026.md`, "the killer
test"): if two histories end in visually identical frames but the optimal
action differs, the pixels are not the state, and a latent variable is
needed. This is the free version of that test, over the settled frames in
`recordings/<run>/*.jsonl`, with no agent change:

  context  = (frame_t, action_t)           the agent's whole visible input
  aliased  = a context seen >= 2 times whose frame_{t+1} differed

A context that always yields the same next frame is Markov in pixels. One
that does not is either **hidden state** (something set earlier decides the
outcome) or **stochasticity** (the engine rolled a die). The second table
appends the previous k actions to the context: aliasing that vanishes at
small k is short-memory state carried by recent actions; aliasing that
persists while contexts still repeat is long-memory state or noise, and
telling those apart needs a candidate variable, not a bigger k — which is
what `H006` builds.

Caveats, stated so the numbers are not over-read: contexts thin out fast
as k grows (the denominators collapse), so the k-columns are a trend, not a
rate; entity ids are not in the key (pixels only), so this under-counts
nothing but cannot say *what* differed — read the per-context dump
(`--dump GAME`) for that.

Usage:
    .venv/bin/python scripts/alias_probe.py                      # all recordings/
    .venv/bin/python scripts/alias_probe.py recordings/2026091*  # some
    .venv/bin/python scripts/alias_probe.py --dump cd82          # one game's aliased contexts
    .venv/bin/python scripts/alias_probe.py --explain cd82       # + outcome diffs and run-up (H006 Day 1)
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KS = (0, 1, 2, 4, 8)


def _hash(rows: list[str]) -> str:
    return hashlib.md5("".join(rows).encode()).hexdigest()[:12]


def _action_key(entry: dict) -> str:
    a = entry["action"]
    if a == "ACTION6" and entry.get("data"):
        a += f"@{entry['data'].get('x')},{entry['data'].get('y')}"
    return a


def _load(path: Path) -> list[dict]:
    with path.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def contexts(steps: list[dict], k: int) -> dict[tuple, collections.Counter]:
    """(frame_t, action_t, previous k actions) -> Counter of frame_{t+1}."""
    hashes = [_hash(s["frame"]) if s.get("frame") else None for s in steps]
    acts = [_action_key(s) for s in steps]
    out: dict[tuple, collections.Counter] = collections.defaultdict(collections.Counter)
    for i in range(len(steps) - 1):
        if steps[i + 1]["step"] != steps[i]["step"] + 1 or i < k:
            continue
        if hashes[i] is None or hashes[i + 1] is None:
            continue
        out[(hashes[i], acts[i], tuple(acts[i - k:i]))][hashes[i + 1]] += 1
    return out


def _diff(a: list[str], b: list[str]) -> list[tuple[int, int, str, str]]:
    return [(x, y, ra[x], rb[x]) for y, (ra, rb) in enumerate(zip(a, b))
            for x in range(len(ra)) if ra[x] != rb[x]]


def explain(files: list[Path], runup: int = 8) -> None:
    """H006 Day 1: for each aliased context, what differed between the
    outcomes, and what led into each branch. Pixels only, read by eye."""
    for f in files:
        steps = _load(f)
        hashes = [_hash(s["frame"]) if s.get("frame") else None for s in steps]
        acts = [_action_key(s) for s in steps]
        branches: dict[tuple, list[int]] = collections.defaultdict(list)
        for i in range(len(steps) - 1):
            if steps[i + 1]["step"] != steps[i]["step"] + 1 or hashes[i] is None:
                continue
            branches[(hashes[i], acts[i])].append(i)
        for (fh, act), idx in branches.items():
            outs = {hashes[i + 1] for i in idx}
            if len(idx) < 2 or len(outs) < 2:
                continue
            print(f"\n== {f.parent.name}/{f.stem} frame={fh} {act}  ({len(idx)} visits, {len(outs)} outcomes)")
            by_out: dict[str, list[int]] = collections.defaultdict(list)
            for i in idx:
                by_out[hashes[i + 1]].append(i)
            ref = None
            for oh, js in by_out.items():
                j = js[0]
                s = steps[j]
                lvl = s["levels_completed"]
                print(f"  outcome {oh}  at steps {[steps[k]['step'] for k in js]}  level={lvl}"
                      f"  run-up={' '.join(acts[max(0, j - runup):j])}")
                if ref is None:
                    ref = steps[j + 1]["frame"]
                else:
                    d = _diff(ref, steps[j + 1]["frame"])
                    cols = collections.Counter((c1, c2) for _, _, c1, c2 in d)
                    xs = [x for x, *_ in d]; ys = [y for _, y, *_ in d]
                    box = f"x{min(xs)}-{max(xs)} y{min(ys)}-{max(ys)}" if d else "-"
                    print(f"    vs first: {len(d)} cells differ, bbox {box}, colours "
                          + ", ".join(f"{a}->{b} x{n}" for (a, b), n in cols.most_common(4)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*", help="recording dirs (default: all of recordings/)")
    ap.add_argument("--dump", metavar="GAME", help="print each aliased context of one game")
    ap.add_argument("--explain", metavar="GAME", help="dump plus outcome diffs and run-up actions")
    args = ap.parse_args()
    dirs = [Path(d) for d in args.dirs] or sorted((ROOT / "recordings").glob("*"))
    files = sorted(f for d in dirs for f in d.glob("*.jsonl"))
    if args.explain:
        explain([f for f in files if f.stem == args.explain])
        return
    if args.dump:
        files = [f for f in files if f.stem == args.dump]

    # per game, per k: [repeated contexts, aliased contexts, transitions in aliased]
    table: dict[str, dict[int, list[int]]] = collections.defaultdict(
        lambda: {k: [0, 0, 0] for k in KS})
    dumps: list[str] = []
    for f in files:
        steps = _load(f)
        for k in KS:
            ctx = contexts(steps, k)
            rep = {c: v for c, v in ctx.items() if sum(v.values()) >= 2}
            ali = {c: v for c, v in rep.items() if len(v) >= 2}
            row = table[f.stem][k]
            row[0] += len(rep)
            row[1] += len(ali)
            row[2] += sum(sum(v.values()) for v in ali.values())
            if k == 0 and args.dump:
                for (fh, act, _), v in ali.items():
                    dumps.append(f"{f.parent.name}/{f.stem} frame={fh} {act:<14} -> "
                                 + ", ".join(f"{h}x{n}" for h, n in v.most_common()))

    if args.dump:
        print("\n".join(dumps) or "no aliased contexts")
        return

    print(f"{'game':6} {'rep>=2':>7} {'aliased':>8} {'%':>6} {'al.trans':>9}")
    tot = [0, 0, 0]
    for g, d in sorted(table.items(), key=lambda kv: -(kv[1][0][1] / max(kv[1][0][0], 1))):
        rep, ali, tr = d[0]
        print(f"{g:6} {rep:7} {ali:8} {100 * ali / max(rep, 1):5.1f}% {tr:9}")
        for i in range(3):
            tot[i] += d[0][i]
    print(f"TOTAL  {tot[0]:7} {tot[1]:8} {100 * tot[1] / max(tot[0], 1):5.1f}% {tot[2]:9}")

    print("\nwith the previous k actions in the context (aliased/repeated):")
    print(f"{'game':6}" + "".join(f"{'k=' + str(k):>14}" for k in KS))
    for g, d in sorted(table.items(), key=lambda kv: -kv[1][0][1]):
        if d[0][1] == 0:
            continue
        print(f"{g:6}" + "".join(f"{d[k][1]:>7}/{d[k][0]:<6}" for k in KS))


if __name__ == "__main__":
    main()
