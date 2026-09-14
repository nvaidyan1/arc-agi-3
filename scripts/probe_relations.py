"""Does the relation layer carry any signal? Replay recordings, count.

The council's gate before building anything on top of `agent/relations.py`
(`docs/council_2026-09-14_belief.md`, "The one thing to do first"). No agent
change: this replays the settled frames stored in `recordings/<run>/*.jsonl`
through the same stack the agent runs live — regions, tracker with explained
motion and home matching, relation engine — and counts three things per game:

  (i)   pairs whose residual ever changes           (does anything move?)
  (ii)  changes attributable to an action            (can I move it?)
  (iii) residuals monotone-decreasing over the 8 frames into a level advance
                                                     (does moving it matter?)

Exit criteria, all three: >= 15/25 games with a moving residual; >= 3 games
with >= 1 action-attributable change per episode; >= 50% of level advances
preceded by a monotone-decreasing residual. (iii) is the real gate — the
reviewers pointed out that (i) passes on pure noise, since `distance` moves
whenever anything translates. Also printed: pairs stuck at None at the end of
each game, which is the first intervention queue.

Usage:
    .venv/bin/python scripts/probe_relations.py recordings/20260914-010613-53036 [more dirs...]
    .venv/bin/python scripts/probe_relations.py --game cd82 recordings/...
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "vendor" / "ARC-AGI-3-Agents"))

from arcengine import FrameData, GameAction  # noqa: E402

import entities  # noqa: E402
import perception  # noqa: E402
import relations  # noqa: E402
from constants import STAMINA_MIN_SIZE, USE_SHIFT_FALLBACK  # noqa: E402
from control import MoveModel  # noqa: E402

WINDOW = 8


def _frame(entry: dict) -> FrameData | None:
    rows = entry.get("frame")
    if not rows:
        return None
    grid = [[int(ch, 16) for ch in row] for row in rows]
    return FrameData(frame=[grid], levels_completed=entry["levels_completed"])


def replay(entries: list[dict], game_id: str) -> dict:
    """Run the perception stack over one recording; return the counts."""
    tracker = entities.RegionTracker()
    moves = MoveModel()
    engine = relations.RelationEngine()
    exact: set[GameAction] = set()
    background: int | None = None
    prev: FrameData | None = None
    prev_level = None
    snapshots: list[dict] = []          # residual vector per frame
    actions: list[str | None] = []      # action that PRODUCED each frame
    advances: list[int] = []            # frame indices where a level was cleared
    prev_action_name: str | None = None

    for i, entry in enumerate(entries):
        frame = _frame(entry)
        if frame is None:
            snapshots.append({}); actions.append(None)
            prev_action_name = entry["action"]
            continue
        level = entry["levels_completed"]
        if prev_level is not None and level != prev_level:
            # Keep the per-action tallies as they stood when the level
            # ended: the engine is about to forget them, and (iii) needs to
            # know which residuals were levers ON THAT LEVEL.
            advances.append((i, {k: {a: dict(t) for a, t in r.by_action.items()}
                                 for k, r in engine.records.items()}))
            tracker.clear(); engine.clear(); moves.reset_position()
            background = None; exact.clear(); prev = None
        prev_level = level

        counts = perception.colour_counts(frame)
        if background is None and counts:
            background = max(counts, key=counts.get)

        acted = (GameAction[prev_action_name]
                 if prev_action_name and prev_action_name != "RESET" else None)
        if prev_action_name == "RESET":
            tracker.expect_home()

        # Move model, exactly as the agent feeds it (my_agent._learn_from).
        if prev is not None and acted is not None and perception.diff_cells(prev, frame):
            moved = perception.detect_translation(prev, frame)
            if moved is not None:
                _c, size, offset, anchor = moved
                moves.observe_translation(acted, offset, size, anchor, game_id)
                exact.add(acted)
            elif USE_SHIFT_FALLBACK and acted not in exact:
                shifted = perception.detect_shift(prev, frame, background)
                if shifted is not None:
                    _c, size, offset, anchor = shifted
                    moves.observe_translation(acted, offset, size, anchor, game_id)

        regions = perception.merge_enclosed(perception.connected_regions(frame, min_size=1))
        regions = [(c, cells) for c, cells in regions if len(cells) >= STAMINA_MIN_SIZE]
        expected = moves.learned_moves.get(acted) if acted is not None else None
        tracker.update(regions, expected_offset=expected)
        engine.update(tracker._tracked, tracker.live, acted.name if acted else None)

        snapshots.append(engine.snapshot())
        actions.append(acted.name if acted else None)
        prev = frame
        prev_action_name = entry["action"]

    return summarise(snapshots, actions, advances, engine)


def _selective_tally(by_action: dict, act: str, direction: str) -> bool:
    tally = by_action[act]
    n = sum(tally.values())
    if tally[direction] < 2 or n < 4:
        return False
    rates = sorted(t[direction] / max(sum(t.values()), 1) for t in by_action.values())
    median = rates[len(rates) // 2]
    return tally[direction] / n - median >= 0.2


def _selective(rec, act: str, direction: str) -> bool:
    return _selective_tally(rec.by_action, act, direction)


def _is_lever(by_action: dict, direction: str) -> bool:
    """Some action moves this residual in `direction` selectively."""
    return any(_selective_tally(by_action, a, direction) for a in by_action)


def summarise(snapshots, actions, advances, engine) -> dict:
    goal_keys = lambda snap: (k for k in snap if k[0] not in relations.EVIDENCE_ONLY)  # noqa: E731

    # (i) pairs whose residual ever changed, and (ii) attribution.
    ever_moved: set = set()
    moves_total = 0
    moves_repeatable = 0
    for t in range(1, len(snapshots)):
        a, b = snapshots[t - 1], snapshots[t]
        act = actions[t]
        for k in goal_keys(b):
            va, vb = a.get(k), b.get(k)
            if va is None or vb is None or va == vb:
                continue
            ever_moved.add(k)
            moves_total += 1
            # A lever, not a coincidence: this action has moved this
            # residual this way >= 2 times AND does so more often than the
            # other actions do. The second clause is the same contrast
            # `Belief` uses to keep the stamina bar out of every action's
            # profile — a residual that moves whatever is pressed (cd82's
            # bar draining: containment(*, bar) fell under every action)
            # is the weather, not a lever.
            rec = engine.records.get(k)
            if rec is not None and act in rec.by_action:
                direction = relations.DOWN if vb < va else relations.UP
                if _selective(rec, act, direction):
                    moves_repeatable += 1
    # Note: `engine` was cleared at each level, so `records` covers the last
    # level only; repeatability is therefore under-counted on games that
    # advance. Conservative in the right direction for a gate.

    # (iii) level advances with a residual that COLLAPSED into them:
    # non-increasing over the window, strictly decreasing at least once,
    # and 0 on the last frame before the advance. "Monotone" alone is not
    # enough — measured on cd82, the stamina bar's containment residual
    # fell 61 -> 57 into the advance, as it falls into everything, because
    # time passes. Collapse to 0 is the Expansionist's boundary-diff
    # reading: the coordinate that reached its target as the level ended.
    # Merely-monotone residuals are still reported, dimmed, as `drains`.
    #
    # And the criterion this probe actually reports as the gate, (iii'):
    # the residual was falling into the advance AND some action was
    # demonstrably driving it down on that level (a lever, by the same
    # selectivity test as (ii)), `distance_drift` excluded because a
    # derivative reads 0 whenever things stop. Why not the literal
    # "collapse to 0": the winning action produces the NEXT level's first
    # frame, so the solved state of the old level is never observed and
    # the last frame in the window is the state one action BEFORE the
    # goal — a residual whose final step to 0 is the winning move can
    # never read 0 here. Both numbers are printed; the literal one is kept
    # so the discrepancy stays visible.
    advance_hits = []
    for i, tallies in advances:
        lo = max(0, i - WINDOW)
        window = snapshots[lo:i]        # frames before the advance frame
        if len(window) < 3:
            advance_hits.append((i, [], [], [], "window too short")); continue
        keys = set().union(*(set(goal_keys(s)) for s in window))
        collapsed, drains, levers = [], [], []
        for k in keys:
            series = [s.get(k) for s in window]
            if any(v is None for v in series):
                continue
            if all(x >= y for x, y in zip(series, series[1:])) and series[0] > series[-1]:
                (collapsed if series[-1] == 0 else drains).append((k, series))
                if (k[0] != "distance_drift" and k in tallies
                        and _is_lever(tallies[k], relations.DOWN)):
                    levers.append((k, series))
        advance_hits.append((i, collapsed, drains, levers, ""))

    last = snapshots[-1] if snapshots else {}
    n_pairs = sum(1 for _ in goal_keys(last))
    n_none = sum(1 for k in goal_keys(last) if last[k] is None)
    return dict(pairs=n_pairs, none_at_end=n_none, ever_moved=len(ever_moved),
                moves_total=moves_total, moves_repeatable=moves_repeatable,
                advances=advance_hits,
                moved_relations=sorted({k[0] for k in ever_moved}))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dirs", nargs="+", help="recording directories with frames")
    ap.add_argument("--game", default=None, help="only this game id")
    ap.add_argument("--verbose", action="store_true", help="print every advance's hits")
    args = ap.parse_args()

    per_game: dict[str, list[dict]] = defaultdict(list)
    for d in args.dirs:
        for f in sorted(Path(d).glob("*.jsonl")):
            if args.game and f.stem != args.game:
                continue
            entries = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
            if not entries or not entries[-1].get("frame"):
                print(f"  {f}: no frames recorded, skipped"); continue
            per_game[f.stem].append(replay(entries, f.stem))

    games_moving = games_repeatable = 0
    total_adv = adv_hit = adv_lever = 0
    print(f"{'game':6} {'runs':>4} {'pairs':>6} {'None@end':>9} {'moved':>6} {'moves':>6} {'levers':>7} {'adv':>4} {'adv=0':>5} {'adv↓lever':>9}  moved relations")
    for g in sorted(per_game):
        rs = per_game[g]
        moved = sum(r["ever_moved"] for r in rs); rep = sum(r["moves_repeatable"] for r in rs)
        adv = [a for r in rs for a in r["advances"]]
        hit = sum(1 for _i, collapsed, _d, _l, _why in adv if collapsed)
        lever_hit = sum(1 for _i, _c, _d, levers, _why in adv if levers)
        drained = sum(1 for _i, collapsed, drains, _l, _why in adv if drains and not collapsed)
        adv_lever += lever_hit
        games_moving += moved > 0
        games_repeatable += rep > 0
        total_adv += len(adv); adv_hit += hit
        rels = sorted({x for r in rs for x in r["moved_relations"]})
        print(f"{g:6} {len(rs):4} {sum(r['pairs'] for r in rs)//len(rs):6} "
              f"{sum(r['none_at_end'] for r in rs)//len(rs):9} {moved:6} "
              f"{sum(r['moves_total'] for r in rs):6} {rep:7} {len(adv):4} {hit:5} {lever_hit:9}  {','.join(rels)}")
        if args.verbose:
            for i, collapsed, drains, levers, why in adv:
                print(f"    advance @frame {i}: {why or f'{len(collapsed)} collapsed to 0, {len(drains)} monotone, {len(levers)} monotone AND a lever'}")
                for k, series in levers[:6]:
                    print(f"      LEVER↓    {k[0]}({k[1]},{k[2]}): {series}")
                for k, series in collapsed[:3]:
                    print(f"      =0        {k[0]}({k[1]},{k[2]}): {series}")
                for k, series in drains[:2]:
                    print(f"      monotone  {k[0]}({k[1]},{k[2]}): {series}")

    n = len(per_game)
    print("\n=== exit criteria ===")
    print(f"(i)   games with a moving residual:            {games_moving}/{n}   need >= 15/25   {'PASS' if games_moving >= 15 else 'FAIL'}")
    print(f"(ii)  games with a repeatable action lever:     {games_repeatable}/{n}   need >= 3       {'PASS' if games_repeatable >= 3 else 'FAIL'}")
    frac = adv_hit / total_adv if total_adv else float('nan')
    print(f"(iii) literal: advances with a residual collapsing to 0:      {adv_hit}/{total_adv} = {frac:.0%}  "
          f"(unmeasurable by construction — the solved frame is never shown)")
    frac2 = adv_lever / total_adv if total_adv else float('nan')
    print(f"(iii') advances with a falling residual some action drives:    {adv_lever}/{total_adv} = {frac2:.0%}  need >= 50%   "
          f"{'PASS' if total_adv and frac2 >= 0.5 else ('NO ADVANCES' if not total_adv else 'FAIL')}")


if __name__ == "__main__":
    main()
