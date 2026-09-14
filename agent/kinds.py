"""Kinds: things that look alike, and what that lets one instance say about
the others.

A *kind* is a view over the grouping view: two or more units (a group, or
a lone entity) with the same palette and the same number of parts — an
**exact** kind when their shapes match too, a **palette** kind when only
the colours do. Nothing is stored as a node; the view is recomputed each
step from evidence, and a kind with one member is not a kind.

Three things are attached to a kind, each answering a question the user
put on 2026-09-14 (`docs/plan.md` 4e):

  * **Role asymmetry.** Each member carries the roles belief has given its
    parts. "Same stuff, one member never changes, one changes under
    ACTION5" is expressible without naming either — the static member is
    the natural reference *because its role is ENVIRONMENT*, not because
    anything called it a template.
  * **Drift.** For a member that changes, its residuals to the static
    member (`part_size_diff`, `shape_diff`) are how far it has evolved from
    the reference, with whatever lever moves them. The same rows the brief
    already had, now with a reason to be read together.
  * **Transfer.** What happened to one member is evidence about the rest.
    `KindMemory` records, per palette, the members that vanished and how
    the stamina fraction moved on the step they went. Eat one food, expect
    the same of its lookalikes — as a weighted prior the proposer may
    read, never a rule.

None where it should be: no kind until two members exist; no drift without
a static member; no transfer until a member has actually gone.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import belief as _belief
import relations as _relations


@dataclass
class Member:
    key: tuple                      # unit key: (rid,) or a sorted group tuple
    roles: dict[str, int]           # role -> how many of its parts hold it
    live: bool = True

    @property
    def static(self) -> bool:
        return set(self.roles) <= {_belief.ENVIRONMENT, _belief.UNASSIGNED} and \
            self.roles.get(_belief.ENVIRONMENT, 0) > 0

    @property
    def holds_control(self) -> bool:
        return self.roles.get(_belief.CONTROL, 0) > 0

    def describe_roles(self) -> str:
        if self.holds_control:
            return "holds the CONTROL thing"
        if self.static:
            return "static"
        if self.roles.get(_belief.AFFECT, 0):
            return "changes under my actions"
        if self.roles.get(_belief.CONTEXT, 0):
            return "changes whatever I press"
        return "no role yet"


@dataclass
class Kind:
    palette: frozenset[int]
    parts: int
    exact: bool
    members: list[Member] = field(default_factory=list)

    def name(self) -> str:
        return "{" + ",".join(str(c) for c in sorted(self.palette)) + "}" + (f"x{self.parts}" if self.parts > 1 else "")


def _unit_key(x) -> tuple:
    return x if isinstance(x, tuple) else (x,)


def compute_kinds(engine, belief_world, live, background: int | None = None) -> list[Kind]:
    """The kinds on screen now, from the relation engine's units — groups,
    the content of framed groups, and lone entities."""
    units: list[tuple[tuple, frozenset[int], int, frozenset]] = []
    groups = engine.groups()
    grouped = set().union(*groups) if groups else set()
    for g in groups:
        key = tuple(sorted(g))
        cols = frozenset().union(*(engine._now[r].colours for r in g))
        cells = frozenset().union(*(engine._now[r].cells for r in g))
        units.append((key, cols, len(g), cells))
        content = _relations.content(engine._now, g, background)
        if content and len(content) < len(g):
            ccols = frozenset().union(*(engine._now[r].colours for r in content))
            ccells = frozenset().union(*(engine._now[r].cells for r in content))
            units.append((content, ccols, len(content), ccells))
    for rid in sorted(live):
        if rid in engine._now and rid not in grouped:
            d = engine._now[rid]
            units.append(((rid,), d.colours, 1, d.cells))

    by_sig: dict[tuple, list] = {}
    for key, cols, parts, cells in units:
        by_sig.setdefault((cols, parts), []).append((key, cells))

    kinds: list[Kind] = []
    for (cols, parts), us in by_sig.items():
        if len(us) < 2:
            continue
        shapes = {_relations._shape(cells) for _k, cells in us}
        kind = Kind(palette=cols, parts=parts, exact=len(shapes) == 1)
        for key, _cells in us:
            roles: dict[str, int] = {}
            for rid in key:
                b = belief_world._beliefs.get(rid)
                role = b.role if b is not None else _belief.UNASSIGNED
                roles[role] = roles.get(role, 0) + 1
            kind.members.append(Member(key=key, roles=roles))
        kinds.append(kind)
    return sorted(kinds, key=lambda k: (-len(k.members), sorted(k.palette)))


def drift(engine, a: Member, b: Member) -> list[str]:
    """How far member `a` is from `b`, in the residuals the engine keeps."""
    out = []
    for rel in ("part_size_diff", "shape_diff"):
        rec = engine.record((rel, a.key, b.key)) or engine.record((rel, b.key, a.key))
        if rec is None or rec.residual is None:
            continue
        txt = f"{rel} {rec.residual}"
        lever = rec.lever(_relations.DOWN)
        if lever:
            txt += f" ({lever[0]} drives it down)"
        out.append(txt)
    return out


class KindMemory:
    """Per palette, what has happened to members of the kind."""

    def __init__(self) -> None:
        # palette -> list of (action, stamina_delta) for members that vanished
        self.vanished: dict[frozenset[int], list[tuple[str | None, float | None]]] = {}
        self._prev_members: dict[frozenset[int], set[tuple]] = {}
        self._prev_stamina: float | None = None

    def clear(self) -> None:
        self.__init__()

    def new_attempt(self) -> None:
        """A reset teleports everything and refills the stamina bar; the
        step across it is not a vanishing and not a stamina change.
        Measured on tu93 before this: '4 of this kind have vanished,
        stamina +98% when they did' — four resets."""
        self._prev_members = {}
        self._prev_stamina = None

    def new_level(self) -> None:
        """Ids are gone with the layout; what vanished on earlier levels is
        kept, because it is typed by palette and that is a game property."""
        self._prev_members = {}
        self._prev_stamina = None

    def record(self, kinds: list[Kind], live, action: str | None, stamina: float | None) -> None:
        """Call once per step with the current kinds. A member present last
        step and gone now, with no live part left, has vanished."""
        now: dict[frozenset[int], set[tuple]] = {}
        for k in kinds:
            now.setdefault(k.palette, set()).update(m.key for m in k.members)
        delta = (stamina - self._prev_stamina) if (stamina is not None and self._prev_stamina is not None) else None
        for palette, before in self._prev_members.items():
            for key in before - now.get(palette, set()):
                if any(r in live for r in key):
                    continue                   # still here, just regrouped
                self.vanished.setdefault(palette, []).append((action, delta))
        self._prev_members = now
        self._prev_stamina = stamina

    def transfer(self, palette: frozenset[int]) -> tuple[int, float | None]:
        """(how many of this kind have vanished, mean stamina delta when they did)."""
        events = self.vanished.get(palette, [])
        deltas = [d for _a, d in events if d is not None]
        return len(events), (sum(deltas) / len(deltas) if deltas else None)

    def gain_prior(self, palette: frozenset[int] | None) -> int:
        """1 when members of this kind have vanished with stamina rising —
        the snake reading — else 0. A weight for the proposer, not a rule."""
        if palette is None:
            return 0
        n, mean = self.transfer(palette)
        return 1 if n and mean is not None and mean > 0 else 0

    def describe(self, kinds: list[Kind], engine) -> list[str]:
        if not kinds:
            return []
        out = ["KINDS (things that look alike; a view, not a claim)"]
        for k in kinds[:5]:
            static = [m for m in k.members if m.static]
            parts = []
            for m in k.members[:4]:
                txt = f"{_name(m.key)} {m.describe_roles()}"
                if static and not m.static:
                    d = drift(engine, m, static[0])
                    if d:
                        txt += " — drifted from the static one: " + ", ".join(d)
                parts.append(txt)
            more = f" · +{len(k.members) - 4} more" if len(k.members) > 4 else ""
            grade = "exact" if k.exact else "same colours"
            line = f"  kind {k.name()} x{len(k.members)} ({grade}): " + " · ".join(parts) + more
            n, mean = self.transfer(k.palette)
            if n:
                line += f" · {n} of this kind have vanished" + (f", stamina {mean:+.0%} when they did" if mean is not None else "")
            out.append(line)
        return out


def _name(key: tuple) -> str:
    return ("{" + ",".join(f"#{r}" for r in key) + "}") if len(key) > 1 else f"#{key[0]}"
