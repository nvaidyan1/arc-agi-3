"""Relations between entities, as residuals — the layer beneath any goal.

Everything below this file describes one entity at a time. The council of
2026-09-14 (`docs/council_2026-09-14_belief.md`) was unanimous that the
missing piece is not richer monads but *relations*, and unanimous on their
type: a relation between two entities returns a **residual**,

    int   — how far the relation is from holding; 0 means it holds
    None  — undecidable right now

and undecidable is None, **never False**. A relation that has not been
observed long enough to know is a question, not a fact, and the council's
type error to avoid is the one where "mostly false" relations feed an
enumerator that then proposes garbage. None is also the first intervention
queue: a pair stuck at None is something the agent could act to decide.

The residual *is* the progress measure. "Reach that thing" is
`distance -> 0`; "make these two the same colours" is `palette_diff -> 0`;
"have as many of these as of those" is `count_diff -> 0`. There is no
separate progress function to design, and the three game families the plan
names (navigational, constructive, matching) are one mechanism.

Three rules from the verdict are load-bearing and are enforced here:

  * **Never align two grids.** Every residual is set cardinality or a
    count. Comparing two shapes cell-by-cell after lining them up *is*
    template-matching, encoded; it does not happen in this file.
  * **No thresholds.** `shape_diff` is 0 on equality and None otherwise. A
    similarity threshold is a prior in disguise, and so is a normalised
    signature (rotation-, scale-invariant): on a 64x64 grid a shape at 2x is
    a different object.
  * **Composites are never built.** A partition has no falsifier — nothing
    can observe "this grouping is wrong" — so parts are not nodes. Where a
    grouping is wanted it is a *view* over a relation that persists
    (`cell_exchange`, `containment`), recomputed and never stored.

What is recorded, and why. Per (relation, a, b) the current residual, the
previous one, and — the thing every advisor missed and every reviewer
named — **per action, how the residual moved**: down, up, or flat. That is
the same structure `Belief` keeps per entity, lifted to a pair, and it is the
bridge from "this relation could be a goal" to "this action moves it". A
residual nobody can move is a diagnostic, not a goal.

Nothing here ranks relations by how goal-like they look. All pairs of known
entities are computed; almost all residuals stay large or None forever, and
that is correct — selection is the job of the boundary diff and the
enumerator above this layer, not of the vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

RELATIONS = (
    "palette_diff",    # |colours(a) Δ colours(b)|                 symmetric
    "shape_diff",      # 0 if same cells up to translation, else None  symmetric
    "containment",     # cells of b outside a's bounding box       directional
    "distance",        # Chebyshev distance between centroids       symmetric
    "distance_drift",  # |distance_t - distance_{t-1}|             symmetric
    "count_diff",      # |#entities coloured like a - like b|       symmetric
    "cell_exchange",   # cells a lost this step that b gained       directional
    # Over the grouping view only (a composite against a composite or a
    # thing), the matching family's two counting residuals:
    "palette_missing", # colours of a that b lacks                  directional
    "part_size_diff",  # sum over shared colours of |cells_a - cells_b|  symmetric
)
SYMMETRIC = frozenset({"palette_diff", "shape_diff", "distance",
                       "distance_drift", "count_diff"})
# Grouping evidence rather than a goal residual: two regions that trade
# cells share a substrate. 0 here means "no exchange", which is the
# opposite polarity from every other relation, so it is kept out of any
# "residual -> 0" reading and named as evidence in `moved()`.
EVIDENCE_ONLY = frozenset({"cell_exchange"})

DOWN, UP, FLAT = "down", "up", "flat"
# How long a containment must hold, or how many steps two regions must
# trade cells, before the grouping view treats them as one thing. Three:
# the same bar the tracker's shape-revive window uses for "moments ago".
GROUP_MIN_STEPS = 3
# A lever needs a few tries of the action and a clear margin over the
# median action's rate — the same +0.20 selectivity Belief uses.
LEVER_MIN_TRIES = 4
LEVER_MIN_LIFT = 0.20
# A precondition worth tallying separately: the controlled thing's bounding
# box within this many cells of a member of the pair, BEFORE the action.
# Adjacency, not centroid distance — a 43-cell bucket touching an 80-cell
# block has centroids ten cells apart.
ADJACENT_GAP = 1
ADJACENT, APART = "adjacent", "apart"


@dataclass(frozen=True)
class Descriptor:
    """What one entity looks like this frame, in terms no game can bias.

    `shape` is the cells re-expressed relative to their own top-left — the
    only normalisation permitted, because translation is the one thing the
    tracker already treats as identity-preserving. No rotation, no scale.
    """
    colours: frozenset[int]
    cells: frozenset[tuple[int, int]]
    bbox: tuple[int, int, int, int]
    shape: frozenset[tuple[int, int]]
    centroid: tuple[float, float]

    @classmethod
    def of(cls, colour: int, cells: Iterable[tuple[int, int]]) -> "Descriptor":
        cells = frozenset(cells)
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        x0, y0 = min(xs), min(ys)
        return cls(
            colours=frozenset({colour}),
            cells=cells,
            bbox=(x0, y0, max(xs), max(ys)),
            shape=frozenset((x - x0, y - y0) for x, y in cells),
            centroid=(sum(xs) / len(xs), sum(ys) / len(ys)),
        )


Key = tuple[str, int, int]


@dataclass
class PairRecord:
    """Everything remembered about one (relation, a, b)."""
    residual: int | None = None
    previous: int | None = None
    # action -> {down, up, flat}: how this residual moved when that action
    # was taken. Only counted when both this and the previous residual were
    # defined — a None -> 3 transition is a question resolving, not motion.
    by_action: dict[str, dict[str, int]] = field(default_factory=dict)
    # The same tallies split by a precondition that held BEFORE the action
    # (`ADJACENT` / `APART`). An action with no unconditional effect can
    # have a decisive conditional one: cd82's paint action was pressed 76
    # times in one run and painted 8 — every time the bucket stood at the
    # block. The unconditional contrast reads that as "no lever".
    by_action_given: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    defined_steps: int = 0
    # Consecutive steps at 0 (the relation holding) and steps with a
    # positive value — the two kinds of persistence the grouping view
    # reads. A bbox that contains another for one step is a thing passing
    # through; one that contains it for k steps is a frame around a fill.
    holding_streak: int = 0
    positive_steps: int = 0

    def observe(self, value: int | None, action: str | None,
                condition: str | None = None) -> None:
        self.previous, self.residual = self.residual, value
        if value is not None:
            self.defined_steps += 1
            self.holding_streak = self.holding_streak + 1 if value == 0 else 0
            if value > 0:
                self.positive_steps += 1
        else:
            self.holding_streak = 0
        if action and value is not None and self.previous is not None:
            way = DOWN if value < self.previous else UP if value > self.previous else FLAT
            tally = self.by_action.setdefault(action, {DOWN: 0, UP: 0, FLAT: 0})
            tally[way] += 1
            if condition is not None:
                given = self.by_action_given.setdefault(condition, {})
                given.setdefault(action, {DOWN: 0, UP: 0, FLAT: 0})[way] += 1

    @property
    def moved(self) -> bool:
        return (self.residual is not None and self.previous is not None
                and self.residual != self.previous)

    def movers(self, direction: str = DOWN) -> list[tuple[str, int]]:
        """Actions that have moved this residual in `direction`, most first."""
        out = [(a, t[direction]) for a, t in self.by_action.items() if t[direction]]
        return sorted(out, key=lambda kv: -kv[1])

    def conditional_lever(self, direction: str = DOWN) -> tuple[str, str, float] | None:
        """(action, condition, lift): an action that moves this residual in
        `direction` under one precondition more than it does otherwise AND
        more than the other actions do under that same precondition.
        Both contrasts, so that neither a drain (every action alike) nor
        an action that works everywhere (an ordinary lever) reads as
        conditional. None when nothing stands out."""
        best = None
        for cond, actions in self.by_action_given.items():
            rates = {a: t[direction] / n for a, t in actions.items()
                     if (n := sum(t.values())) >= LEVER_MIN_TRIES}
            for a, r in rates.items():
                if actions[a][direction] < 2:
                    continue
                elsewhere = [t for c, acts in self.by_action_given.items() if c != cond
                             for a2, t in acts.items() if a2 == a]
                n_else = sum(sum(t.values()) for t in elsewhere)
                r_else = (sum(t[direction] for t in elsewhere) / n_else) if n_else >= 2 else 0.0
                others = sorted(r2 for a2, r2 in rates.items() if a2 != a)
                r_others = others[len(others) // 2] if others else 0.0
                lift = r - max(r_else, r_others)
                if lift >= LEVER_MIN_LIFT and (best is None or lift > best[2]):
                    best = (a, cond, lift)
        return best

    def lever(self, direction: str = DOWN) -> tuple[str, float] | None:
        """The action that moves this residual in `direction` MORE than the
        others do, and by how much — or None when nothing stands out.

        The same contrast Belief uses to keep the stamina bar out of every
        action's profile, lifted to a pair: a residual that falls whatever
        is pressed (a timer draining, a bar filling) has movers but no
        lever, and only a lever is evidence that *I* can drive it.
        """
        if len(self.by_action) < 2:
            return None
        rates = {a: t[direction] / n for a, t in self.by_action.items()
                 if (n := sum(t.values())) >= LEVER_MIN_TRIES}
        if len(rates) < 2:
            return None
        best = max(rates, key=rates.get)
        # Against the median of the OTHER actions: with two actions the
        # pooled median is the best action's own rate and no lever could
        # ever exist, which is wrong — one button that moves a thing and
        # one that does not is the plainest lever there is.
        others = sorted(r for a, r in rates.items() if a != best)
        median = others[len(others) // 2]
        lift = rates[best] - median
        if self.by_action[best][direction] < 2 or lift < LEVER_MIN_LIFT:
            return None
        return best, lift


class RelationEngine:
    """Residuals for every pair of known entities, updated once per step."""

    def __init__(self) -> None:
        self._now: dict[int, Descriptor] = {}
        self._prev: dict[int, Descriptor] = {}
        self._first_seen: dict[int, int] = {}
        self._distance_history: dict[tuple[int, int], list[int]] = {}
        self._step = 0
        self.records: dict[Key, PairRecord] = {}
        self.live: set[int] = set()
        # Residuals between GROUPS (see `groups`). Keyed by the sorted
        # member tuples, so a group whose membership changes is a new pair
        # of relata with a fresh record — a view has no identity to keep.
        self.group_records: dict[tuple, PairRecord] = {}
        # A group is a view keyed by its members, and members change ids
        # when a part is repainted (cd82: the block's pink half gets a new
        # region id each time black is painted over it). Without
        # continuity every such step started a fresh record and the paint
        # action could never accumulate a lever on part_size_diff(template,
        # block) — measured: 0 levers at 4 cd82 advances. So a new group
        # key inherits the record of an earlier key with the same colours
        # whose members it mostly shares — the tracker's overlap rule,
        # applied to composites. `_alias` maps a member tuple to the tuple
        # its records live under.
        self._alias: dict[tuple, tuple] = {}
        self._unit_colours: dict[tuple, frozenset[int]] = {}
        self._background: int | None = None
        self._control: set[int] = set()

    # ── update ──────────────────────────────────────────────────────────

    def update(
        self,
        tracked: dict[int, tuple[int, frozenset[tuple[int, int]]]],
        live: Iterable[int],
        action: str | None,
        skip: Iterable[int] = (),
        control: Iterable[int] = (),
    ) -> dict[Key, int | None]:
        """Fold one frame in and return every residual.

        `tracked` is the tracker's memory (all known ids, ghosts included);
        `live` is which of them are on screen now. Ghost pairs are computed
        so they land in the None queue rather than vanishing from view.

        `skip` is for the canvas. It is a tracked region like any other, but
        as a *relatum* it is the substrate everything else sits on: every
        static thing's bounding box "contains" thousands of its cells and
        the controlled thing trades cells with it on every move. Measured on
        cd82's brief before this: all ten RELATIONS rows and six of eight
        RECENT events were canvas noise. The caller decides what the canvas
        is (the largest live region of the background colour); this layer
        only agrees not to relate things to it.
        """
        self._step += 1
        self.live = set(live)
        skip = set(skip)
        for rid in skip:                      # the canvas colour, for content units
            if rid in tracked:
                self._background = tracked[rid][0]
        self._prev = self._now
        self._now = {rid: Descriptor.of(colour, cells)
                     for rid, (colour, cells) in tracked.items() if rid not in skip}
        # The precondition is read from the frame BEFORE this action —
        # `_prev` now holds it — with the CONTROL set as it stood then;
        # `control` is this step's, kept for the next.
        control_prev = [self._prev[c] for c in self._control if c in self._prev]
        self._control = set(control)
        for rid in self._now:
            self._first_seen.setdefault(rid, self._step)

        colour_counts: dict[int, int] = {}
        for rid in self.live:
            if rid not in self._now:      # skipped (the canvas)
                continue
            for c in self._now[rid].colours:
                colour_counts[c] = colour_counts.get(c, 0) + 1

        ids = sorted(self._now)
        out: dict[Key, int | None] = {}
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                for rel in SYMMETRIC:
                    out[(rel, a, b)] = self._symmetric(rel, a, b, colour_counts)
                out[("containment", a, b)] = self._containment(a, b)
                out[("containment", b, a)] = self._containment(b, a)
                out[("cell_exchange", a, b)] = self._exchange(a, b)
                out[("cell_exchange", b, a)] = self._exchange(b, a)
        def condition_for(members) -> str | None:
            """Where the controlled thing stood relative to the nearest
            non-control member of this pair before the action:
            'adjacent:-x' / 'apart:+y' and so on. Adjacency alone was
            measured to be useless on cd82 — the bucket's every orbit
            position touches the block — while WHICH SIDE it paints from
            decides which half changes. None when there is no control
            thing, or the pair is the control thing itself."""
            if not control_prev:
                return None
            others = [self._prev[m] for m in members if m not in self._control and m in self._prev]
            if not others:
                return None
            c, m = min(((c, m) for c in control_prev for m in others),
                       key=lambda cm: bbox_gap(cm[0].bbox, cm[1].bbox))
            gap = bbox_gap(c.bbox, m.bbox)
            return f"{ADJACENT if gap <= ADJACENT_GAP else APART}:{side_of(c.centroid, m.centroid)}"

        for key, value in out.items():
            self.records.setdefault(key, PairRecord()).observe(
                value, action, condition_for(key[1:]))
        for key, value in self._group_residuals().items():
            rel, ka, kb = key
            canon = (rel, self._canonical(ka), self._canonical(kb))
            self.group_records.setdefault(canon, PairRecord()).observe(
                value, action, condition_for(tuple(ka) + tuple(kb)))
        return out

    def _canonical(self, members: tuple) -> tuple:
        """The member tuple this unit's records live under: itself, or an
        earlier unit with the same colours sharing at least half its
        members. Singletons are their own key."""
        if len(members) == 1:
            return members
        if members in self._alias:
            return self._alias[members]
        colours = self._unit_colours.get(members)
        best, best_overlap = None, 0
        mine = set(members)
        for other, canon in self._alias.items():
            if self._unit_colours.get(canon) != colours:
                continue
            overlap = len(mine & set(other))
            if overlap * 2 >= max(len(mine), len(other)) and overlap > best_overlap:
                best, best_overlap = canon, overlap
        canon = best if best is not None else members
        self._alias[members] = canon
        self._unit_colours.setdefault(canon, colours)
        return canon

    # ── the grouping view ───────────────────────────────────────────────

    def groups(self, min_steps: int = GROUP_MIN_STEPS) -> list[frozenset[int]]:
        """Live entities that have persistently sat inside one another or
        traded cells, as a partition — recomputed from the records every
        call, never stored. Only groups of two or more are returned.

        This is the council's "composites fall out for free": no node is
        created, nothing is stamped, and the evidence is exactly the two
        relations whose persistence means "one thing". Adjacency alone is
        not evidence and does not appear here. Measured on cd82: the
        bucket's frame and fill (containment 0, cells traded on every
        turn), the template's frame and its interior, the block's halves
        (they trade cells under the paint action).
        """
        parent: dict[int, int] = {rid: rid for rid in self.live if rid in self._now}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)

        for (rel, a, b), rec in self.records.items():
            if a not in parent or b not in parent:
                continue
            if rel == "containment" and rec.holding_streak >= min_steps:
                union(a, b)
            elif rel == "cell_exchange":
                # Trading cells is symmetric evidence: a paint that goes
                # back and forth alternates direction, and counting each
                # direction alone made a repainted pair take twice as long
                # to be one thing again.
                back = self.records.get(("cell_exchange", b, a))
                if rec.positive_steps + (back.positive_steps if back else 0) >= min_steps:
                    union(a, b)
        members: dict[int, set[int]] = {}
        for rid in parent:
            members.setdefault(find(rid), set()).add(rid)
        return sorted((frozenset(m) for m in members.values() if len(m) > 1),
                      key=lambda g: min(g))

    def _group_residuals(self) -> dict[tuple, int | None]:
        """Residuals between every pair of groups, and between each group
        and each live singleton. Set cardinality, counting, and
        translation-normalised equality only — no alignment, as ever.

        Two of these exist because the matching family was measured to be
        inexpressible without them (cd82: four level advances with no
        coordinate, and the first A/B loss). `palette_missing(A, B)` is
        the colours of A that B lacks — 0 says "everything A is made of,
        B has too", which is the correlation a template and its copy show
        before any painting has happened. `part_size_diff(A, B)` sums, over
        the colours they share, how far apart their cell counts per colour
        are — a *proportion* residual with a gradient, so the paint action
        that changes the mix becomes a lever. Arrangement stays what it
        was: `shape_diff = 0` at the end, or nothing. The snake reading of
        the same primitives: two things with identical descriptors are the
        same kind, and what one did is evidence about the other — that is
        the next view, not this one.
        """
        groups = self.groups()
        if not groups:
            return {}
        grouped = set().union(*groups)
        units: list[tuple[tuple, frozenset[int], frozenset, dict[int, int]]] = []
        def unit(ids):
            key = tuple(sorted(ids))
            cells = frozenset().union(*(self._now[r].cells for r in ids))
            cols = frozenset().union(*(self._now[r].colours for r in ids))
            self._unit_colours[key] = cols
            per_colour: dict[int, int] = {}
            for r in ids:
                for c in self._now[r].colours:
                    per_colour[c] = per_colour.get(c, 0) + len(self._now[r].cells)
            return (key, cols, cells, per_colour)

        for g in groups:
            units.append(unit(g))
            # What a framed group encloses is a unit of its own (see
            # `content`): cd82's template content {black, pink} against the
            # block {black, pink} is the pair the matching family is about,
            # and the frame's own colours hid it.
            inner = content(self._now, g, self._background)
            if inner and len(inner) < len(g):
                units.append(unit(inner))
        for rid in sorted(self.live):
            if rid in self._now and rid not in grouped:
                d = self._now[rid]
                units.append(((rid,), d.colours, d.cells,
                              {c: len(d.cells) for c in d.colours}))
        out: dict[tuple, int | None] = {}
        for i, (ka, ca, cea, na) in enumerate(units):
            for kb, cb, ceb, nb in units[i + 1:]:
                if len(ka) == 1 and len(kb) == 1:
                    continue        # singleton pairs are the ordinary records
                if set(ka) <= set(kb) or set(kb) <= set(ka):
                    continue        # a thing against its own inside says nothing
                out[("palette_diff", ka, kb)] = len(ca ^ cb)
                out[("shape_diff", ka, kb)] = 0 if _shape(cea) == _shape(ceb) else None
                out[("palette_missing", ka, kb)] = len(ca - cb)
                out[("palette_missing", kb, ka)] = len(cb - ca)
                shared = ca & cb
                out[("part_size_diff", ka, kb)] = (
                    sum(abs(na[c] - nb[c]) for c in shared) if shared else None)
        return out

    def record(self, key: tuple):
        """The record for a pair key or a group key, or None."""
        if key in self.records:
            return self.records[key]
        rel, ka, kb = key
        return self.group_records.get((rel, self._alias.get(ka, ka), self._alias.get(kb, kb)))

    # ── the relations ───────────────────────────────────────────────────

    def _decidable(self, a: int, b: int) -> bool:
        """Both on screen, neither seen for the first time this step."""
        return (a in self.live and b in self.live
                and self._first_seen[a] < self._step
                and self._first_seen[b] < self._step)

    def _symmetric(self, rel: str, a: int, b: int, counts: dict[int, int]) -> int | None:
        if not self._decidable(a, b):
            return None
        da, db = self._now[a], self._now[b]
        if rel == "palette_diff":
            return len(da.colours ^ db.colours)
        if rel == "shape_diff":
            return 0 if da.shape == db.shape else None
        if rel == "count_diff":
            ca = sum(counts.get(c, 0) for c in da.colours)
            cb = sum(counts.get(c, 0) for c in db.colours)
            return abs(ca - cb)
        d = _chebyshev(da.centroid, db.centroid)
        if rel == "distance":
            return d
        # distance_drift: needs the previous distance of this same pair.
        hist = self._distance_history.setdefault((a, b), [])
        hist.append(d)
        del hist[:-2]
        return abs(hist[-1] - hist[-2]) if len(hist) == 2 else None

    def _containment(self, a: int, b: int) -> int | None:
        if not self._decidable(a, b):
            return None
        x0, y0, x1, y1 = self._now[a].bbox
        return sum(1 for x, y in self._now[b].cells
                   if not (x0 <= x <= x1 and y0 <= y <= y1))

    def _exchange(self, a: int, b: int) -> int | None:
        if not self._decidable(a, b) or a not in self._prev or b not in self._prev:
            return None
        lost = self._prev[a].cells - self._now[a].cells
        gained = self._now[b].cells - self._prev[b].cells
        return len(lost & gained)

    # ── views ───────────────────────────────────────────────────────────

    def moved(self) -> list[tuple[Key, int, int]]:
        """(key, previous, current) for every residual that changed this step."""
        return [(k, r.previous, r.residual) for k, r in self.records.items() if r.moved]

    def undecided(self) -> list[Key]:
        """Pairs whose residual is None right now — the intervention queue."""
        return [k for k, r in self.records.items() if r.residual is None]

    def snapshot(self) -> dict:
        """Every residual, pair and group, as it stands."""
        out = {k: r.residual for k, r in self.records.items()}
        out.update({k: r.residual for k, r in self.group_records.items()})
        return out

    def group_moved(self) -> list[tuple[tuple, int, int]]:
        return [(k, r.previous, r.residual) for k, r in self.group_records.items() if r.moved]

    def clear(self) -> None:
        """New level: entity ids are gone, so every pair is too."""
        self.__init__()


def content(now: dict, g, background: int | None) -> tuple | None:
    """What a framed group encloses: if one member's bounding box holds
    every other member, the others minus canvas-coloured filler are the
    frame's content. Enclosure is the geometry the grouping view already
    uses; this only names the inside. None when no member frames the rest."""
    for frame in g:
        x0, y0, x1, y1 = now[frame].bbox
        others = [r for r in g if r != frame]
        if others and all(x0 <= x <= x1 and y0 <= y <= y1
                          for r in others for (x, y) in now[r].cells):
            inner = tuple(sorted(r for r in others
                                 if background is None or now[r].colours != {background}))
            return inner or None
    return None


def side_of(control: tuple[float, float], member: tuple[float, float]) -> str:
    """Which side of `member` the controlled thing is on, by the dominant
    axis of the centroid difference: '-x' (left), '+x', '-y' (above), '+y'."""
    dx, dy = control[0] - member[0], control[1] - member[1]
    if abs(dx) >= abs(dy):
        return "-x" if dx < 0 else "+x"
    return "-y" if dy < 0 else "+y"


SIDES = ("-x", "+x", "-y", "+y")


def bbox_gap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    """Empty cells between two bounding boxes (Chebyshev): 0 when they
    touch or overlap, 1 when one empty cell separates them."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = max(0, bx0 - ax1 - 1, ax0 - bx1 - 1)
    dy = max(0, by0 - ay1 - 1, ay0 - by1 - 1)
    return max(dx, dy)


def _chebyshev(p: tuple[float, float], q: tuple[float, float]) -> int:
    return int(round(max(abs(p[0] - q[0]), abs(p[1] - q[1]))))


def _shape(cells: frozenset) -> frozenset:
    x0 = min(c[0] for c in cells)
    y0 = min(c[1] for c in cells)
    return frozenset((x - x0, y - y0) for x, y in cells)
