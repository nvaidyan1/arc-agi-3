"""The falsifiable lenses: pure tests over a pair of frames.

Every function here follows one contract, which is the agent's governing
principle in executable form (docs/plan.md, "Governing principle"):

    input observation -> try an explanation -> return it, or return None

**None is a first-class outcome.** None of these assert anything about
what games contain. `detect_translation` does not claim games have moving
objects — it asks whether *this* change is a translation and reports
nothing when it isn't. `classify_change` does not claim games have
objects that appear and vanish — it tests whether the change touches the
canvas. A game we have never seen yields no detections rather than a
wrong ontology, and that is the whole defence against building an agent
that only works on the 25 games we happened to look at.

Everything here is stateless and deterministic, which is why this is the
layer with real unit tests (tests/test_perception.py): given two grids,
the answer is checkable by hand.

Layer position: pixel > **change** > **object**, feeding "thing I
control" and "thing I affect" above.
"""
from __future__ import annotations

from arcengine import FrameData


def diff_cells(
    prev_frame: FrameData, latest_frame: FrameData
) -> list[tuple[int, int]]:
    """(x, y) cells that differ between two frames' settled state.

    `FrameData.frame` is NOT a stack of spatial layers — it's the
    animation sub-frames produced *within* one action (the engine loops
    step()+render until the action completes). So `frame[-1]` is the
    settled state the action produced and `frame[0]` is mid-animation.
    Measured: only ~10% of steps animate at all, but on a heavily
    animated game (tu93, 61% of steps) reading `frame[0]` drops move-map
    consistency to 21-29% versus 43-64% for `frame[-1]`, because it
    compares windows offset by a partial action.
    """
    if not prev_frame.frame or not latest_frame.frame:
        return []
    prev_grid, latest_grid = prev_frame.frame[-1], latest_frame.frame[-1]
    return [
        (x, y)
        for y, (prev_row, latest_row) in enumerate(zip(prev_grid, latest_grid))
        for x, (prev_val, latest_val) in enumerate(zip(prev_row, latest_row))
        if prev_val != latest_val
    ]


def lost_and_gained(
    prev_frame: FrameData, latest_frame: FrameData
) -> tuple[dict[int, set[tuple[int, int]]], dict[int, set[tuple[int, int]]]]:
    """Per colour, the cells that stopped being it and started being it.

    The shared substrate under every correspondence question we ask:
    translation, blocked-move confirmation, residual, and recolour /
    cardinality classification all start from exactly this.

    Note both dicts are keyed by *colour at that side of the change*: a
    cell that went 3 -> 7 appears in `lost[3]` and `gained[7]`, so a
    colour can appear in one, the other, or both.
    """
    lost: dict[int, set[tuple[int, int]]] = {}
    gained: dict[int, set[tuple[int, int]]] = {}
    if not prev_frame.frame or not latest_frame.frame:
        return lost, gained
    for y, (prev_row, latest_row) in enumerate(
        zip(prev_frame.frame[-1], latest_frame.frame[-1])
    ):
        for x, (prev_val, latest_val) in enumerate(zip(prev_row, latest_row)):
            if prev_val != latest_val:
                lost.setdefault(prev_val, set()).add((x, y))
                gained.setdefault(latest_val, set()).add((x, y))
    return lost, gained


def detect_translation(
    prev_frame: FrameData, latest_frame: FrameData
) -> tuple[int, int, tuple[int, int], tuple[int, int]] | None:
    """Is this frame-to-frame change one coloured shape *moving*?

    Returns `(colour, cell_count, (dx, dy), anchor)` if the entire set of
    cells that lost colour C is exactly the set that gained colour C,
    displaced by a single consistent offset — otherwise None. `anchor` is
    the shape's pre-move reference cell (its lexicographically smallest),
    which is what lets a caller reconstruct an absolute board position
    from a chain of relative offsets.

    The object layer, derived rather than assumed (Gestalt common fate:
    things that change together are one thing). It makes no prior
    commitment to 2D space or to anything being an object: it *tests*
    whether a translation explains the change and reports nothing when it
    doesn't, so a non-spatial game yields no detections instead of a
    wrong ontology. Fires on 14 of 25 games; silent on vc33/ft09/tn36,
    which is the graceful-failure property working rather than a gap.
    """
    if not prev_frame.frame or not latest_frame.frame:
        return None

    lost, gained = lost_and_gained(prev_frame, latest_frame)
    for colour, source in lost.items():
        target = gained.get(colour)
        if not target or len(target) != len(source):
            continue
        # Anchor on each set's lexicographically smallest cell to get the
        # single candidate offset, then require an exact match.
        (sx, sy), (tx, ty) = min(source), min(target)
        offset = (tx - sx, ty - sy)
        if {(x + offset[0], y + offset[1]) for x, y in source} == target:
            return colour, len(source), offset, (sx, sy)
    return None


def expected_move_occurred(
    prev_frame: FrameData, latest_frame: FrameData, offset: tuple[int, int]
) -> bool:
    """Did *any* coloured component shift by exactly `offset`?

    Deliberately weaker than `detect_translation`. The precise
    difference, which is easy to state wrongly: `detect_translation`
    requires that for some colour, *every* cell that lost it is matched
    by a cell that gained it under one offset. Change in *other* colours
    doesn't block it — but one extra cell of the *moving shape's own*
    colour appearing or vanishing elsewhere does, because the sets stop
    matching. This function only asks whether some component shifted,
    and ignores the rest.

    Measured: the strict test misses ~4% of real moves, and every one of
    those would otherwise be recorded as a false obstacle.
    """
    if not prev_frame.frame or not latest_frame.frame:
        return False
    dx, dy = offset
    lost, gained = lost_and_gained(prev_frame, latest_frame)
    for colour, source in lost.items():
        target = gained.get(colour)
        if target and any((x + dx, y + dy) in target for x, y in source):
            return True
    return False


def classify_change(
    prev_frame: FrameData,
    latest_frame: FrameData,
    explained: set[tuple[int, int]] | None = None,
    background: int | None = None,
) -> tuple[
    dict[tuple[int, int], int], dict[int, int], set[tuple[int, int]]
] | None:
    """Name the change types translation doesn't cover.

    Returns `(recolours, cardinality, lost_cells)`, or None if there's
    nothing to classify:
      `recolours`   {(from_colour, to_colour): cell_count} — a thing at a
                    fixed position changed identity.
      `cardinality` {colour: signed_delta} — content appeared (positive)
                    or disappeared (negative) relative to the canvas.
      `lost_cells`  positions where content became canvas. This is the
                    sub-goal signal, and unlike the whole-board histogram
                    it replaced, it says *where* — so a salience bump can
                    land on the cells that actually emptied.

    Motivation: classifying 533 transitions across 8 games found
    translation is only **31%** of what games do — recolour-in-place is
    **53%** (vc33 97%) and cardinality-change **16%** (ft09 98%), the
    three together covering 99%. Only translation had a lens; this adds
    the other two, so ~69% of transitions stop being anonymous diff cells.

    The discriminator is the background, which is the same rule the
    vanish detector relies on: a change *touching the canvas* creates or
    destroys content, while a change *between two non-background colours*
    merely relabels something that was already there and still is.

    `background` is passed in rather than derived per frame, and that
    matters more than it looks: deriving it as "the most common colour
    right now" makes the classification flip when content grows enough to
    outvote the canvas. Measured across all 25 games — 24 stable, but
    **dc22 disagrees on 37.4% of steps** (argmax oscillating between
    colours 3 and 4), which is exactly the game whose mechanic is filling
    the board in. Callers should supply the level's *initial* mode: the
    canvas as it was before anything touched it. Falls back to per-frame
    argmax only when the caller has none yet.

    Note this taxonomy is deliberately *narrower* than the manual study's.
    ft09 toggles two foreground colours back and forth (9->8 468 cells,
    8->9 432, over a stable background of 5); the study counted that as
    cardinality-change because per-colour totals move, this counts it as
    recolour because nothing was created or destroyed.
    """
    if not prev_frame.frame or not latest_frame.frame:
        return None
    prev_grid, latest_grid = prev_frame.frame[-1], latest_frame.frame[-1]

    if background is None:
        counts: dict[int, int] = {}
        for row in latest_grid:
            for value in row:
                counts[value] = counts.get(value, 0) + 1
        if not counts:
            return None
        background = max(counts, key=counts.get)

    explained = explained or set()
    recolours: dict[tuple[int, int], int] = {}
    cardinality: dict[int, int] = {}
    lost_cells: set[tuple[int, int]] = set()
    for y, (prev_row, latest_row) in enumerate(zip(prev_grid, latest_grid)):
        for x, (prev_val, latest_val) in enumerate(zip(prev_row, latest_row)):
            if prev_val == latest_val or (x, y) in explained:
                continue
            if prev_val == background:
                # Canvas -> content: something came into existence.
                cardinality[latest_val] = cardinality.get(latest_val, 0) + 1
            elif latest_val == background:
                # Content -> canvas: something ceased to exist.
                cardinality[prev_val] = cardinality.get(prev_val, 0) - 1
                lost_cells.add((x, y))
            else:
                key = (prev_val, latest_val)
                recolours[key] = recolours.get(key, 0) + 1

    if not recolours and not cardinality:
        return None
    return recolours, cardinality, lost_cells


def colour_counts(frame: FrameData) -> dict[int, int]:
    """How many cells each colour occupies in the settled frame."""
    counts: dict[int, int] = {}
    if not frame.frame:
        return counts
    for row in frame.frame[-1]:
        for value in row:
            counts[value] = counts.get(value, 0) + 1
    return counts


def residual_cells(
    prev_frame: FrameData,
    latest_frame: FrameData,
    changed: list[tuple[int, int]],
    offset: tuple[int, int] | None,
    meter_colour: int | None,
) -> list[tuple[int, int]]:
    """Changed cells NOT explained by our own shape moving.

    The "thing I affect" layer: subtract self (the translation we caused)
    and the budget meter (which ticks on its own schedule), and whatever
    is left is something else we acted upon. Nothing here assumes what
    that something is.

    With `offset=None` there is no self to subtract, so this returns the
    whole diff minus the meter — which is exactly right for a game with
    no controllable movement, where every change is "other than self" by
    construction. Callers that use this as a *reward* should still gate
    on knowing their own movement (otherwise it double-counts ordinary
    frame-change); callers that use it as a *map* should not, since a map
    double-counts nothing. Gating the map cost us dearly once: it read
    0.0% of steps on ft09/sb26/cd82/tn36, the exact games it was needed
    for (docs/history.md, 2026-09-13).
    """
    if not changed:
        return []
    explained: set[tuple[int, int]] = set()
    if offset is not None and prev_frame.frame and latest_frame.frame:
        dx, dy = offset
        lost, gained = lost_and_gained(prev_frame, latest_frame)
        for colour, source in lost.items():
            target = gained.get(colour)
            if not target:
                continue
            moved = {p for p in source if (p[0] + dx, p[1] + dy) in target}
            if moved:
                explained |= moved
                explained |= {(x + dx, y + dy) for x, y in moved}

    out = []
    for cell in changed:
        if cell in explained:
            continue
        if meter_colour is not None and prev_frame.frame and latest_frame.frame:
            x, y = cell
            # Depletion recolours meter cells *away* from the meter
            # colour, so check both sides of the change, not just the new
            # value.
            if meter_colour in (
                prev_frame.frame[-1][y][x],
                latest_frame.frame[-1][y][x],
            ):
                continue  # the budget ticking down, not something we hit
        out.append(cell)
    return out
