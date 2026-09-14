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

from constants import MIN_ROTATION_CELLS, MIN_SHIFT_CELLS, SHIFT_AXIS_RATIO


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


def connected_regions(
    frame: FrameData, min_size: int = 1
) -> list[tuple[int, frozenset[tuple[int, int]]]]:
    """Contiguous same-coloured regions, as `(colour, cells)` pairs.

    A *grouping*, not an interpretation — it proposes that some pixels may
    be one thing and says nothing whatever about what that thing is. That
    is the side of the governing principle this belongs on: structure may
    constrain how a hypothesis is represented, only not which entities or
    roles exist.

    Built because the aggregate it replaces destroys real signal. cd82's
    stamina bar drains 64 cells to 0 — perfectly — but 100 static cells
    elsewhere share its colour, so the whole-board total only falls
    164 -> 100 and the sawtooth test rejects it at 61%. The same bar
    measured as a region reads 0% and passes. A signal that is flawless at
    the region level was unrecoverable at the colour level.

    Four-connectivity, iterative flood fill: a 64x64 grid is 4096 cells, so
    this is cheap, and recursion would risk a stack overflow on a large
    region for no benefit. Pure Python on purpose — `scipy` is not
    installed and is not worth a dependency for twenty lines.

    Where a game uses non-contiguous motifs this degrades by returning
    *more, smaller* regions — it detects less rather than asserting
    something false, which is the failure mode we can live with.
    """
    if not frame.frame:
        return []
    grid = frame.frame[-1]
    height = len(grid)
    width = len(grid[0]) if height else 0
    seen = [[False] * width for _ in range(height)]
    out: list[tuple[int, frozenset[tuple[int, int]]]] = []

    for y0 in range(height):
        for x0 in range(width):
            if seen[y0][x0]:
                continue
            colour = grid[y0][x0]
            stack = [(x0, y0)]
            seen[y0][x0] = True
            cells = []
            while stack:
                x, y = stack.pop()
                cells.append((x, y))
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if (0 <= nx < width and 0 <= ny < height
                            and not seen[ny][nx] and grid[ny][nx] == colour):
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if len(cells) >= min_size:
                out.append((colour, frozenset(cells)))
    return out


def merge_enclosed(
    regions: list[tuple[int, frozenset[tuple[int, int]]]],
) -> list[tuple[int, frozenset[tuple[int, int]]]]:
    """Fold a region wholly surrounded by one other region into it.

    Same-colour contiguity necessarily splits a bordered object in two: a
    frame of one colour and a fill of another. Measured on wa30's first
    frame, three objects are each a 12-cell 4x4 frame around a 4-cell 2x2
    core — one thing on screen, two regions to us, which is why the entity
    mask appeared to show two objects where there was plainly one.

    Enclosure is a geometric fact, not a guess about what games contain:
    every cell bordering the inner region from outside belongs to the same
    outer region. That is as far as this goes — two shapes merely touching
    stay separate, because "adjacent" is not "part of".

    The merged region keeps the OUTER colour, since the frame is what
    bounds the object; the caller sees one region where it saw two.
    """
    by_cells = {cells: (colour, i) for i, (colour, cells) in enumerate(regions)}
    lookup: dict[tuple[int, int], int] = {}
    for i, (_colour, cells) in enumerate(regions):
        for cell in cells:
            lookup[cell] = i

    absorbed: dict[int, int] = {}
    for i, (_colour, cells) in enumerate(regions):
        outside = set()
        for x, y in cells:
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (nx, ny) in cells:
                    continue
                owner = lookup.get((nx, ny))
                if owner is None:          # board edge — not enclosed
                    outside.add(None)
                else:
                    outside.add(owner)
        if len(outside) == 1:
            owner = next(iter(outside))
            if owner is not None and owner != i:
                absorbed[i] = owner

    if not absorbed:
        return regions
    # Resolve chains (a core inside a frame inside a frame).
    def root(i):
        seen = set()
        while i in absorbed and i not in seen:
            seen.add(i); i = absorbed[i]
        return i

    merged: dict[int, set] = {}
    for i, (_colour, cells) in enumerate(regions):
        merged.setdefault(root(i), set()).update(cells)
    return [(regions[i][0], frozenset(cells)) for i, cells in merged.items()]


def detect_shift(
    prev_frame: FrameData,
    latest_frame: FrameData,
    background: int | None = None,
    tolerance: float = 0.25,
) -> tuple[int, int, tuple[int, int], tuple[int, int]] | None:
    """Did one coloured thing *go somewhere*, allowing it to change shape?

    Same return shape as `detect_translation` — `(colour, cells, (dx, dy),
    anchor)` — so a caller can use either without knowing which answered.

    `detect_translation` and `detect_rotation` both demand the shape be
    **identical** before and after, and that is too strict for anything
    that animates. cd82's controllable object deforms by up to 14 cells as
    it moves — a walk cycle, a tilt — so both refuse it and the game has
    no move map at all. Masking its stamina bar does not help: 0
    detections before and after. The deformation is real.

    This asks the weaker question. Take the cells a colour lost and the
    cells it gained; if the two are comparable in size, report the shift
    between their centroids, rounded to whole cells. Measured on cd82 that
    recovers a complete directional map — ACTION1 up, ACTION2 down,
    ACTION3 left, ACTION4 right, stride 11 — **100% consistent across 179
    observations**, on a game where nothing was detected before.

    It is weaker evidence and it is treated as such: try `detect_translation`
    first, because an exact offset is a stronger claim than an average one,
    and only fall back to this. The size guard is what keeps it honest —
    without it, a colour being consumed on one side of the board and
    created on the other would read as motion. It stays silent where it
    should: sb26 and tn36 produce nothing, lp85 is noisy at 29% and so
    never reaches `MoveModel`'s majority bar.

    **`background` must be supplied**, and a unit test exists because
    leaving it out is silently catastrophic. When an object moves right
    the canvas *also* "moves": it loses cells where the object arrived and
    gains them where it left, so its centroid shifts **left** — the exact
    opposite direction — and being the complement of every mover at once,
    it is usually the largest candidate. Picking it would teach the move
    map a reversed offset for every action. The exact lenses never had
    this problem because a hole is not shaped like the thing that left it,
    so set equality rejected it; tolerating deformation removes that
    accidental protection.

    `tolerance` is the fraction by which the two sides may differ in size.
    """
    if not prev_frame.frame or not latest_frame.frame:
        return None

    lost, gained = lost_and_gained(prev_frame, latest_frame)
    best = None
    for colour, source in lost.items():
        if background is not None and colour == background:
            continue
        target = gained.get(colour)
        if not target:
            continue
        n, k = len(source), len(target)
        if n < MIN_SHIFT_CELLS:
            continue
        if abs(n - k) > max(2, tolerance * n):
            continue
        sx = sum(p[0] for p in source) / n
        sy = sum(p[1] for p in source) / n
        tx = sum(p[0] for p in target) / k
        ty = sum(p[1] for p in target) / k
        dx, dy = round(tx - sx), round(ty - sy)
        if dx == 0 and dy == 0:
            continue
        # Square up a clearly axis-aligned move. A deforming shape drags
        # its centroid a little sideways as it travels, so cd82 reports
        # (-1,-11) on one step and (1,-11) on the next — different offsets
        # to `MoveModel`, which then splits the majority 20/16 = 56%,
        # falls under its 60% bar and learns nothing. The minor component
        # is the deformation, not the motion: measured on the dominant
        # axis alone those same steps agree 100% across 179 observations.
        # Only applied when one axis genuinely dominates, so a real
        # diagonal move is still reported as diagonal.
        if abs(dx) >= SHIFT_AXIS_RATIO * abs(dy):
            dy = 0
        elif abs(dy) >= SHIFT_AXIS_RATIO * abs(dx):
            dx = 0
        # The largest coherent thing that moved is the best candidate for
        # "an object", and picking deterministically matters: dict order
        # would otherwise decide which of two movers the caller learns.
        if best is None or n > best[1]:
            best = (colour, n, (dx, dy), min(source))
    return best


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


# Each entry solves its transform's two constants in closed form from the
# coordinate sums, so there is no search and no fitting — only a candidate,
# which is then verified by exact set equality. Same discipline as
# `detect_translation`, which derives its single offset the same way.
#
#   rot90cw   (x, y) -> (a - y, b + x)
#   rot90ccw  (x, y) -> (a + y, b - x)
#   rot180    (x, y) -> (a - x, b - y)
#
# Reflections were implemented and measured alongside these and fired
# **zero** times across 25 games, so they are deliberately absent rather
# than carried as untested code. Add them when something needs them.
_ROTATIONS = (
    ("rot90cw", lambda sx, sy, tx, ty: (tx + sy, ty - sx),
     lambda x, y, a, b: (a - y, b + x)),
    ("rot90ccw", lambda sx, sy, tx, ty: (tx - sy, ty + sx),
     lambda x, y, a, b: (a + y, b - x)),
    ("rot180", lambda sx, sy, tx, ty: (tx + sx, ty + sy),
     lambda x, y, a, b: (a - x, b - y)),
)


def detect_rotation(
    prev_frame: FrameData, latest_frame: FrameData
) -> tuple[int, int, str, tuple[int, int]] | None:
    """Is this frame-to-frame change one coloured shape *turning*?

    Returns `(colour, cell_count, kind, pivot_doubled)` when the cells a
    colour lost are exactly the cells it gained, rotated a quarter or half
    turn about a point — otherwise `None`, like every other lens here.

    Why this exists. `detect_translation` gets as far as "this colour lost
    exactly as many cells as it gained" — a rigid-motion signature — and
    then discards the event if no single *offset* explains it. A rotation
    dies precisely there, which is why an object visibly turning under the
    agent's own actions produced no evidence at all. Measured across 25
    games: 285 such balanced-but-not-translated events, of which 77 are
    exact rotations — and on wa30 **57 of 57** are, a quarter of all its
    change steps.

    `pivot_doubled` is the centre of rotation multiplied by two, because a
    shape can legitimately turn about a cell *corner* — a half-integer
    point — and returning that as a float would invite rounding at the one
    place exactness is the whole guarantee.

    This asserts nothing about games containing rotating things, and it
    must be tried only *after* translation: a centrally-symmetric shape
    sliding sideways satisfies both descriptions, and the translation is
    the one that composes into a position.
    """
    if not prev_frame.frame or not latest_frame.frame:
        return None

    lost, gained = lost_and_gained(prev_frame, latest_frame)
    for colour, source in lost.items():
        target = gained.get(colour)
        if not target or len(target) != len(source):
            continue
        n = len(source)
        if n < MIN_ROTATION_CELLS:
            continue
        sx, sy = sum(p[0] for p in source), sum(p[1] for p in source)
        tx, ty = sum(p[0] for p in target), sum(p[1] for p in target)
        for kind, solve, apply in _ROTATIONS:
            big_a, big_b = solve(sx, sy, tx, ty)
            # A non-integer constant means no rotation of this kind can map
            # these sets, so there is nothing to verify.
            if big_a % n or big_b % n:
                continue
            a, b = big_a // n, big_b // n
            if {apply(x, y, a, b) for x, y in source} != target:
                continue
            pivot = ((a - b, a + b) if kind == "rot90cw"
                     else (a + b, b - a) if kind == "rot90ccw"
                     else (a, b))
            return colour, n, kind, pivot
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
    stamina_colour: int | None,
    stamina_cells: frozenset[tuple[int, int]] | None = None,
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
        # Prefer the meter's own CELLS when they are known: filtering by
        # colour removes every cell sharing that colour anywhere, which on
        # a board where 100 unrelated cells match is the difference
        # between subtracting the meter and subtracting play area.
        if stamina_cells is not None:
            if cell in stamina_cells:
                continue
        elif stamina_colour is not None and prev_frame.frame and latest_frame.frame:
            x, y = cell
            # Depletion recolours meter cells *away* from the meter
            # colour, so check both sides of the change, not just the new
            # value.
            if stamina_colour in (
                prev_frame.frame[-1][y][x],
                latest_frame.frame[-1][y][x],
            ):
                continue  # the budget ticking down, not something we hit
        out.append(cell)
    return out
