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
)
SYMMETRIC = frozenset({"palette_diff", "shape_diff", "distance",
                       "distance_drift", "count_diff"})
# Grouping evidence rather than a goal residual: two regions that trade
# cells share a substrate. 0 here means "no exchange", which is the
# opposite polarity from every other relation, so it is kept out of any
# "residual -> 0" reading and named as evidence in `moved()`.
EVIDENCE_ONLY = frozenset({"cell_exchange"})

DOWN, UP, FLAT = "down", "up", "flat"


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
    defined_steps: int = 0

    def observe(self, value: int | None, action: str | None) -> None:
        self.previous, self.residual = self.residual, value
        if value is not None:
            self.defined_steps += 1
        if action and value is not None and self.previous is not None:
            tally = self.by_action.setdefault(action, {DOWN: 0, UP: 0, FLAT: 0})
            tally[DOWN if value < self.previous else UP if value > self.previous else FLAT] += 1

    @property
    def moved(self) -> bool:
        return (self.residual is not None and self.previous is not None
                and self.residual != self.previous)

    def movers(self, direction: str = DOWN) -> list[tuple[str, int]]:
        """Actions that have moved this residual in `direction`, most first."""
        out = [(a, t[direction]) for a, t in self.by_action.items() if t[direction]]
        return sorted(out, key=lambda kv: -kv[1])


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

    # ── update ──────────────────────────────────────────────────────────

    def update(
        self,
        tracked: dict[int, tuple[int, frozenset[tuple[int, int]]]],
        live: Iterable[int],
        action: str | None,
    ) -> dict[Key, int | None]:
        """Fold one frame in and return every residual.

        `tracked` is the tracker's memory (all known ids, ghosts included);
        `live` is which of them are on screen now. Ghost pairs are computed
        so they land in the None queue rather than vanishing from view.
        """
        self._step += 1
        self.live = set(live)
        self._prev = self._now
        self._now = {rid: Descriptor.of(colour, cells)
                     for rid, (colour, cells) in tracked.items()}
        for rid in self._now:
            self._first_seen.setdefault(rid, self._step)

        colour_counts: dict[int, int] = {}
        for rid in self.live:
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
        for key, value in out.items():
            self.records.setdefault(key, PairRecord()).observe(value, action)
        return out

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

    def snapshot(self) -> dict[Key, int | None]:
        return {k: r.residual for k, r in self.records.items()}

    def clear(self) -> None:
        """New level: entity ids are gone, so every pair is too."""
        self.__init__()


def _chebyshev(p: tuple[float, float], q: tuple[float, float]) -> int:
    return int(round(max(abs(p[0] - q[0]), abs(p[1] - q[1]))))
