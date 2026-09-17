"""H007 P2 re-test (gate 2): does a state-conditioned lever form on cd82 now
that H011's click blend has shipped?

H007 Day 4 could not build the enumerator's state-conditioned tally because
"the state never varies under exploration (6 strip clicks / 4,000 steps)".
H011 then shipped a novelty blend that raised swatch-strip clicks from 1.6%
to a reported 42-52%. This asks the question that was queued and never run:
given the new click distribution, does the enumerator form a lever whose
precondition kind is `state:`?

It reads three things off the same runs, because the answer is only
interpretable with all three:

  1. state-conditioned levers formed      (the P2 question itself)
  2. clicks landing in the strip's BBOX   (what H011 measured)
  3. clicks landing on an actual SWATCH   (what actually sets the state)

(2) and (3) differ by a factor of ~12 and that turned out to be the whole
result -- the strip ENTITY's bbox is 414 cells, of which ~23 are the two
interactive swatches and ~391 are inert filler of colour '3'.

Schema, verified against the recordings before this was written (and against
`scripts/h011_click_novelty.py`, which parses the same files):
    record['frame']  list[str], 64 rows x 64 chars, indexed grid[y][x]
    record['data']   {'x': int, 'y': int} for ACTION6
    record['frame']  is the grid the agent DECIDED from (pre-action), so the
                     effect of the action at index i is visible at i+1 --
                     confirmed by recomputing `prev_action_diff_cells`
                     (372/399 records agree; mismatches cluster at resets).

Usage:
    for s in $(seq 1 10); do
      ARC_PROPOSER=1 .venv/bin/python scripts/play_local.py \
        --game cd82 --max-steps 400 --seed $s
    done
    .venv/bin/python scripts/h007_p2_retest.py recordings/<run>/ ...
"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys

# The swatch strip ENTITY's bbox (entity #2 in the S_t traces, 2,375/2,375
# sightings agree), as used by `scripts/h011_click_novelty.py`.
STRIP_BBOX = (18, 0, 63, 8)
# Colours inside that bbox that belong to the interactive swatches rather
# than the strip's inert backing. Read off the frame, not assumed: the
# backing is '3'; the two swatches are '4'-outlined boxes filled '0' and 'f'.
SWATCH_COLOURS = frozenset("04f")


def in_strip(x: int, y: int) -> bool:
    x0, y0, x1, y1 = STRIP_BBOX
    return x0 <= x <= x1 and y0 <= y <= y1


def strip_view(grid: list[str]) -> str:
    x0, y0, x1, y1 = STRIP_BBOX
    return "\n".join(row[x0 : x1 + 1] for row in grid[y0 : y1 + 1])


def summary_for(run_dir: str) -> dict | None:
    """The sweep summary written alongside a recording directory."""
    path = os.path.join("results", "sweeps", os.path.basename(run_dir.rstrip("/")) + ".json")
    return json.load(open(path)) if os.path.exists(path) else None


def main(argv: list[str]) -> None:
    run_dirs = argv[1:] or sorted(glob.glob("recordings/*/"))
    n_state = n_adj = n_hyp = 0
    a6 = bbox = swatch = changed = 0
    colours: collections.Counter[str] = collections.Counter()
    rows = []

    for run_dir in run_dirs:
        rec_path = os.path.join(run_dir, "cd82.jsonl")
        if not os.path.exists(rec_path):
            continue
        recs = [json.loads(line) for line in open(rec_path)]

        r_a6 = r_bbox = r_swatch = r_changed = 0
        views = [strip_view(r["frame"]) if r.get("frame") else None for r in recs]
        for i, rec in enumerate(recs):
            if rec.get("action") != "ACTION6" or not rec.get("frame"):
                continue
            r_a6 += 1
            d = rec.get("data") or {}
            x, y = d.get("x", -1), d.get("y", -1)
            if not in_strip(x, y):
                continue
            r_bbox += 1
            colour = rec["frame"][y][x]
            colours[colour] += 1
            if colour in SWATCH_COLOURS:
                r_swatch += 1
            if i + 1 < len(views) and views[i] and views[i + 1] and views[i] != views[i + 1]:
                r_changed += 1

        # The P2 question itself: preconditions on the levers the enumerator formed.
        summary = summary_for(run_dir)
        game = (summary or {}).get("observed", {}).get("cd82", {})
        log = game.get("hypothesis_log", [])
        kinds = collections.Counter(e[7][0] if e[7] else None for e in log)
        r_state = sum(v for k, v in kinds.items() if k and str(k).startswith("state:"))
        r_adj = sum(v for k, v in kinds.items() if k and not str(k).startswith("state:"))

        n_state += r_state; n_adj += r_adj; n_hyp += len(log)
        a6 += r_a6; bbox += r_bbox; swatch += r_swatch; changed += r_changed
        rows.append((os.path.basename(run_dir.rstrip("/")), game.get("levels_completed"),
                     len(log), r_adj, r_state, r_a6, r_bbox, r_swatch, r_changed))

    print(f"{'run':>22} {'lvl':>3} {'hyps':>5} {'adj':>4} {'state':>5} "
          f"{'A6':>4} {'bbox':>5} {'swatch':>6} {'changed':>7}")
    for r in rows:
        print(f"{r[0]:>22} {str(r[1]):>3} {r[2]:>5} {r[3]:>4} {r[4]:>5} "
              f"{r[5]:>4} {r[6]:>5} {r[7]:>6} {r[8]:>7}")

    pct = lambda n, d: (100.0 * n / d) if d else 0.0
    print(f"\nseeds={len(rows)}  hypotheses={n_hyp}  adjacency-conditioned={n_adj}  "
          f"STATE-conditioned={n_state}")
    print(f"ACTION6={a6}  strip-bbox clicks={bbox} ({pct(bbox, a6):.1f}%)  "
          f"actual-swatch clicks={swatch} ({pct(swatch, a6):.2f}%)")
    print(f"strip-bbox clicks followed by a strip change: {changed} "
          f"({pct(changed, bbox):.1f}%)")
    print(f"clicked colours inside the bbox: {dict(colours)}")

    print("\nREADING:", end=" ")
    if n_state:
        print("P2 MET -- a state-conditioned lever formed.")
    elif pct(swatch, a6) >= 15:
        print("P2 NOT MET despite real swatch coverage -> the gap is the\n"
              "  enumerator's tally / lever-formation logic.")
    else:
        print("P2 NOT MET, and swatch coverage was never delivered: the bbox\n"
              "  clicks are dominated by inert backing, so the state still does\n"
              "  not vary and no tally can form. H011 raised bbox coverage, not\n"
              "  coverage of the cells that set the state.")


if __name__ == "__main__":
    main(sys.argv)
