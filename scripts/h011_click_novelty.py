"""H011 Stage 1: would a pure novelty rule have clicked the swatch strip
far more often than the real salience-tiered policy did?

`ClickTargeting.pick()` (`agent/attention.py`) tries five tiers in a
fixed order — a learned region of interest, recently-active cells,
non-background cells, a random fallback — and within whichever tier has
ANY unclicked candidate, picks one of those uniformly at random. The
strip only competes in the LAST, broadest tier (any non-background
cell), and that tier is reached only once every narrower, more salient
tier has run out of fresh candidates — which, on a board this active,
is close to never. H007 measured the outcome: 4 of 322 real clicks
(1.2%) land on the strip.

This script re-scores the same 322 real decisions by a single rule that
ignores tiers entirely — pick uniformly among whichever cells are tied
for fewest real clicks so far, over every non-background cell actually
visible in that frame — and asks how many strip clicks that would
produce IN EXPECTATION. It changes nothing about *when* ACTION6 is
chosen, only where it would aim once it is; it needs no game engine,
since it re-ranks candidates against the frames and real per-cell click
counts already on disk.

CAUTION built in from the start, not added after a bad first result:
with ~800 non-background cells and only 322 total clicks, almost every
cell sits tied at zero clicks throughout, so "is the strip EVER tied for
the minimum" is close to vacuous — nearly any rarely-clicked region
would pass that test. The metric that actually says something is the
EXPECTED number of strip clicks a uniform draw from the tied set would
produce, weighted by how large that set is each time — the same
discipline this project applied to itself on 2026-09-15 ("Day 1: most
of the aliasing is a quantised meter", the since_reset-resolves-100%
correction).

Usage:
    .venv/bin/python scripts/h011_click_novelty.py
"""
from __future__ import annotations

import collections
import glob
import json

# The swatch strip's own bbox, read directly from S_t traces (entity #2,
# 2,375/2,375 sightings agree): x 18-63, y 0-8.
STRIP_BBOX = (18, 0, 63, 8)


def in_strip(x: int, y: int) -> bool:
    x0, y0, x1, y1 = STRIP_BBOX
    return x0 <= x <= x1 and y0 <= y <= y1


def background_of(grid: list[str]) -> str:
    counts = collections.Counter(ch for row in grid for ch in row)
    return counts.most_common(1)[0][0]


def non_background_cells(grid: list[str], background: str) -> list[tuple[int, int]]:
    return [(x, y) for y, row in enumerate(grid) for x, ch in enumerate(row) if ch != background]


def main() -> None:
    total_decisions = 0
    strip_real = 0
    strip_absent = 0
    expected_strip_clicks = 0.0
    tie_set_sizes = []
    strip_shares = []

    for f in sorted(glob.glob("recordings/latent/seed*/cd82.jsonl")):
        tries: dict[tuple[int, int], int] = collections.defaultdict(int)
        for line in open(f):
            d = json.loads(line)
            if d["action"] != "ACTION6" or not d.get("frame"):
                continue
            x, y = d["data"]["x"], d["data"]["y"]
            grid = d["frame"]
            bg = background_of(grid)
            cells = non_background_cells(grid, bg)
            strip_cells = [c for c in cells if in_strip(*c)]
            total_decisions += 1
            if in_strip(x, y):
                strip_real += 1
            if not strip_cells:
                strip_absent += 1
                tries[(x, y)] += 1
                continue
            # The set tied for fewest real clicks so far, over EVERY
            # visible non-background cell -- then the honest question:
            # if a novelty-uniform policy drew one cell from that tied
            # set, what is the probability it lands in the strip?
            min_tries = min(tries.get(c, 0) for c in cells)
            tied = [c for c in cells if tries.get(c, 0) == min_tries]
            tied_strip = [c for c in tied if c in strip_cells]
            p_strip = len(tied_strip) / len(tied)
            expected_strip_clicks += p_strip
            tie_set_sizes.append(len(tied))
            strip_shares.append(p_strip)
            tries[(x, y)] += 1

    print(f"real ACTION6 decisions with a recorded frame: {total_decisions}")
    print(f"  real clicks landing in the strip's bbox {STRIP_BBOX}: {strip_real} "
          f"({100 * strip_real / total_decisions:.1f}%)")
    print(f"  decisions where the strip had no visible non-background cell: {strip_absent}")
    scored_n = total_decisions - strip_absent
    sizes = sorted(tie_set_sizes)
    shares = sorted(strip_shares)
    print(f"\nsize of the tied-for-fewest-clicks set: median {sizes[len(sizes)//2]} "
          f"(min {sizes[0]}, max {sizes[-1]})")
    print(f"strip's share of that tied set per decision: median {shares[len(shares)//2]:.3f} "
          f"(this is p(a uniform draw from the tie hits the strip), not '100% in the top tier')")
    print(f"\nEXPECTED strip clicks under uniform-random-among-tied-novelty, over "
          f"{scored_n} decisions: {expected_strip_clicks:.1f}")
    print(f"REAL strip clicks under the salience-tiered policy:                {strip_real}")
    print(f"ratio (expected novelty / real):                                    "
          f"{expected_strip_clicks / max(strip_real, 1):.1f}x")


if __name__ == "__main__":
    main()
