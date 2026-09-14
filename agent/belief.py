"""What each entity *is to me* — the layer that composes the rest.

Everything below this file answers a question about a moment: what changed,
was it a translation, which colour moved. Nothing answered a question about
a **thing over time**, so the agent held a pile of correlations and never
reduced them. Measured on cd82: the stamina bar changes on 52-66% of steps
*whatever* is pressed, and that common signal sits in every action's
profile, drowning the one effect that is actually action-specific
(ACTION5's 0->15, exclusive to it across 400 cells).

The fix is contrast, not more lenses. An entity's role is read from how its
behaviour differs **between** actions, not from how often it changes:

    responsiveness  P(this entity changed | I acted)        -- the baseline
    selectivity     max over actions of P(changed|a) - baseline

    responsiveness ~ 0                      -> ENVIRONMENT   (never moves)
    responsiveness high, selectivity low    -> CONTEXT       (changes regardless)
    selectivity high, and it displaces      -> CONTROL       (I move this)
    selectivity high, no displacement       -> AFFECT        (I act on this)
    too little evidence                     -> UNASSIGNED

Subtracting the baseline is what makes the stamina bar fall out as CONTEXT
instead of contaminating every action's profile — the same common-mode
removal that recovers ACTION5's purpose at +41% lift once applied.

WHY THIS IS NOT A SEMANTIC ONTOLOGY. The governing principle (docs/plan.md)
permits structure that constrains how a hypothesis is represented, and
forbids structure that decides which entities, goals or roles exist. These
five roles are **relational**: each is a statement about the correlation
between an entity's behaviour and the agent's own actions, and none of them
names anything about a game. There is no PLAYER, no GOAL, no ENEMY here —
those would be claims about what games contain. "The thing whose changes
track one of my buttons" is a claim about a measurement.

Two properties keep it honest, and they are the same two that every lens in
`perception.py` has:

  * **UNASSIGNED is a first-class outcome.** An entity with thin evidence
    gets no role, exactly as `learned_moves` refuses m0r0's 15/13 split
    rather than picking the winner.
  * **Roles are mutable.** Evidence accumulates and a role is recomputed
    from it every time it is asked for; nothing is stamped permanently.
    A thing that stops responding stops being CONTROL.
"""
from __future__ import annotations

from constants import (
    BELIEF_CONTEXT_BASELINE,
    BELIEF_MIN_ACTIONS,
    BELIEF_MIN_OBSERVATIONS,
    BELIEF_SELECTIVITY,
)

CONTROL = "control"
AFFECT = "affect"
CONTEXT = "context"
ENVIRONMENT = "environment"
UNASSIGNED = "unassigned"


class Belief:
    """One entity's accumulated evidence, and the role it currently earns."""

    __slots__ = ("region_id", "colour", "acted", "changed", "displaced",
                 "last_size", "last_cells")

    def __init__(self, region_id: int, colour: int) -> None:
        self.region_id = region_id
        self.colour = colour
        # Per action name: how often it was taken while this entity existed,
        # and how often this entity changed in that step. The pair is the
        # whole basis of every role below — a rate needs its denominator.
        self.acted: dict[str, int] = {}
        self.changed: dict[str, int] = {}
        # Times this entity's change looked like going somewhere, rather
        # than merely being different. Splits CONTROL from AFFECT.
        self.displaced = 0
        self.last_size = 0
        # The cells this entity occupied on the PREVIOUS frame. Needed
        # because a change at its edge removes that cell from the region:
        # a draining bar's front cell has just stopped being the meter
        # colour, so testing only against the current cells misses it.
        # Measured cost of getting this wrong: the cd82 meter read 7%
        # responsive where it is really 77%, and stayed UNASSIGNED.
        self.last_cells: frozenset = frozenset()

    def observe(self, action: str, changed: bool, displaced: bool) -> None:
        self.acted[action] = self.acted.get(action, 0) + 1
        if changed:
            self.changed[action] = self.changed.get(action, 0) + 1
        if displaced:
            self.displaced += 1

    @property
    def observations(self) -> int:
        return sum(self.acted.values())

    @property
    def rates(self) -> dict[str, float]:
        """P(this entity changed | each action)."""
        return {a: self.changed.get(a, 0) / n for a, n in self.acted.items() if n}

    @property
    def responsiveness(self) -> float:
        """The baseline: how much this entity changes whatever I press.

        Median rather than mean, so one heavily-sampled action cannot drag
        the baseline it is then measured against.
        """
        rates = sorted(self.rates.values())
        if not rates:
            return 0.0
        mid = len(rates) // 2
        return rates[mid] if len(rates) % 2 else (rates[mid - 1] + rates[mid]) / 2

    @property
    def selectivity(self) -> tuple[str | None, float]:
        """The action that stands out most, and by how much over baseline."""
        rates = self.rates
        if not rates:
            return None, 0.0
        base = self.responsiveness
        action = max(rates, key=lambda a: rates[a] - base)
        return action, rates[action] - base

    @property
    def drivers(self) -> list[tuple[str, float]]:
        """EVERY action that stands out, not just the winner.

        Reporting only the maximum claims an exclusivity the evidence
        often does not support. Measured on wa30: one entity responds to
        ACTION2 on 93% of steps and to ACTION4 on 84%, against a 53%
        baseline — calling it "ACTION2's" and stopping there is a false
        precision. Several buttons really do drive the same thing.
        """
        base = self.responsiveness
        out = [(a, r - base) for a, r in self.rates.items()
               if r - base >= BELIEF_SELECTIVITY]
        return sorted(out, key=lambda kv: -kv[1])

    @property
    def role(self) -> str:
        """Recomputed from current evidence every time — never cached.

        Order matters. Selectivity is checked before responsiveness because
        an entity can be both busy and action-specific, and "one button
        drives this" is the more useful reading; a thing that changes
        constantly *and* has a button of its own is still that button's.
        """
        if (self.observations < BELIEF_MIN_OBSERVATIONS
                or len(self.acted) < BELIEF_MIN_ACTIONS):
            return UNASSIGNED
        _action, lift = self.selectivity
        if lift >= BELIEF_SELECTIVITY:
            return CONTROL if self.displaced else AFFECT
        if self.responsiveness >= BELIEF_CONTEXT_BASELINE:
            return CONTEXT
        if self.responsiveness == 0.0:
            return ENVIRONMENT
        return UNASSIGNED

    def describe(self) -> str:
        role = self.role
        if role in (CONTROL, AFFECT):
            drivers = self.drivers
            named = ", ".join(f"{a} +{lift:.0%}" for a, lift in drivers[:3])
            more = f" (+{len(drivers) - 3} more)" if len(drivers) > 3 else ""
            verb = "I move this with" if role == CONTROL else "acted on by"
            return f"{verb} {named}{more}"
        if role == CONTEXT:
            return f"changes whatever I press ({self.responsiveness:.0%} of steps)"
        if role == ENVIRONMENT:
            return "never changes"
        return "not enough evidence yet"


class WorldBelief:
    """Every entity's belief, updated once per decision."""

    def __init__(self) -> None:
        self._beliefs: dict[int, Belief] = {}

    def update(self, tracked: dict, action: str, changed_cells) -> None:
        """Fold one step into every currently-tracked entity.

        `tracked` is `RegionTracker`'s output for this frame. An entity is
        "changed" this step if any cell that differed lies inside it, and
        "displaced" if its cells moved while its size held — a cheap proxy
        that deliberately does not re-run the motion lenses, since the point
        here is to relate evidence rather than to produce more of it.
        """
        if not action or action == "RESET":
            return
        touched = set(changed_cells or ())
        for rid, (colour, cells) in tracked.items():
            belief = self._beliefs.get(rid)
            first_seen = belief is None
            if first_seen:
                belief = self._beliefs[rid] = Belief(rid, colour)
                belief.last_size = len(cells)
                belief.last_cells = cells
            # Union of where it is and where it just was, so a change at
            # the boundary counts for the entity that boundary belongs to.
            hit = bool(touched & (cells | belief.last_cells))
            # Same size but DIFFERENT cells is the signature of going
            # somewhere; a size change is growing, shrinking or draining.
            # Never on the first sighting: `last_size` is initialised to
            # the current size, so without this guard an entity that
            # appears counts as having moved, and a recolour gets
            # described as "I move this" — which is a claim about the
            # world, and the wrong one.
            displaced = (not first_seen and hit
                         and len(cells) == belief.last_size
                         and cells != belief.last_cells)
            belief.observe(action, hit, displaced)
            belief.last_size = len(cells)
            belief.last_cells = cells

    def by_role(self, role: str) -> list[Belief]:
        """Every entity currently holding `role`, best evidence first."""
        out = [b for b in self._beliefs.values() if b.role == role]
        return sorted(out, key=lambda b: -b.selectivity[1])

    def summary(self) -> list[tuple[int, str, str, str]]:
        """(region id, colour, role, description) for every believed entity."""
        return [(b.region_id, b.colour, b.role, b.describe())
                for b in sorted(self._beliefs.values(),
                                key=lambda b: -b.observations)]

    def clear(self) -> None:
        """New level: entity ids are gone, so the beliefs attached to them are too."""
        self._beliefs.clear()
