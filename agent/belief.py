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

import math

from constants import (
    BELIEF_CONTEXT_BASELINE,
    BELIEF_DETERMINISM,
    BELIEF_DETERMINISM_MIN_CHANGES,
    BELIEF_HYSTERESIS,
    BELIEF_MIN_ACTIONS,
    BELIEF_MIN_CERTAINTY,
    BELIEF_MIN_OBSERVATIONS,
    BELIEF_SELECTIVITY,
)

def _phi(z: float) -> float:
    """Standard normal CDF, via erf — no scipy, and none needed."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _one_sided(observed: float, threshold: float, n: int) -> float:
    """Confidence that a proportion genuinely exceeds a fixed threshold."""
    spread = threshold * (1 - threshold) / n
    if spread <= 0:
        return 1.0 if observed > threshold else 0.0
    return _phi((observed - threshold) / math.sqrt(spread))


# How an action changes a thing, in the only vocabulary available without
# knowing anything about the game: what happened to its cells. Measured to
# separate cleanly -- on wa30 the rotating object reads TURNED on 86 of 88
# events while the sliding one reads MOVED on 73 of 73, and on cd82 the
# stamina bar reads SHRANK under every action and never once GREW.
MOVED = "moved"          # centroid shifted, size held
TURNED = "turned"        # size held, cells changed, centroid did not move
GREW = "grew"
SHRANK = "shrank"
APPEARED = "appeared"
VANISHED = "vanished"
MOTION_KINDS = (MOVED, TURNED)
# The outcome key for "nothing happened to it" — the complement of every
# entry in `Belief.effects`, so that a forecast can name it and be scored.
UNCHANGED = ("unchanged",)

CONTROL = "control"
AFFECT = "affect"
CONTEXT = "context"
ENVIRONMENT = "environment"
UNASSIGNED = "unassigned"


class Belief:
    """One entity's accumulated evidence, and the role it currently earns."""

    __slots__ = ("region_id", "colour", "acted", "changed", "kinds",
                 "effects", "last_size", "last_cells", "_held", "live")

    def __init__(self, region_id: int, colour: int) -> None:
        self.region_id = region_id
        self.colour = colour
        # Per action name: how often it was taken while this entity existed,
        # and how often this entity changed in that step. The pair is the
        # whole basis of every role below — a rate needs its denominator.
        self.acted: dict[str, int] = {}
        self.changed: dict[str, int] = {}
        # Per action, a tally of HOW it changed. Knowing only *that* an
        # action affects a thing is most of the way to useless: "ACTION5
        # affects #12" and "ACTION5 grows #12 while ACTION3 moves it" are
        # different amounts of understanding, and the second is available
        # from the same observations.
        self.kinds: dict[str, dict[str, int]] = {}
        # Per action, a tally of the EFFECT: the kind plus, for motion, the
        # direction it went. `kinds` answers "how does this action change
        # it"; this answers "does this action always do the same thing to
        # it", which is what control looks like when several buttons all
        # move one thing.
        self.effects: dict[str, dict[tuple, int]] = {}
        self.last_size = 0
        # The cells this entity occupied on the PREVIOUS frame. Needed
        # because a change at its edge removes that cell from the region:
        # a draining bar's front cell has just stopped being the meter
        # colour, so testing only against the current cells misses it.
        # Measured cost of getting this wrong: the cd82 meter read 7%
        # responsive where it is really 77%, and stayed UNASSIGNED.
        self.last_cells: frozenset = frozenset()
        # The last role this entity earned. Roles are still recomputed
        # from evidence every time, but a held one is given a slightly
        # lower bar to keep than it needed to win — without that, an
        # entity sitting near the threshold flips on and off as evidence
        # trickles in. Measured on cd82 before this: 12 of 17 entities
        # gained a role, lost it and regained it, one of them seven times,
        # and the Controls readout changed on 19% of steps.
        self._held: str = UNASSIGNED
        # Whether the tracker saw this entity in the most recent frame. A
        # belief outlives its entity on purpose — a stamina bar that
        # empties comes back — but an entity that is not on screen cannot
        # be observed, targeted or acted on, and until this flag existed
        # every one of those was happening to ghosts.
        self.live = True

    def observe(self, action: str, kind: str | None,
                effect: tuple | None = None) -> None:
        self.acted[action] = self.acted.get(action, 0) + 1
        if kind is None:
            return
        self.changed[action] = self.changed.get(action, 0) + 1
        per = self.kinds.setdefault(action, {})
        per[kind] = per.get(kind, 0) + 1
        eff = self.effects.setdefault(action, {})
        key = effect if effect is not None else (kind,)
        eff[key] = eff.get(key, 0) + 1

    def determinism(self, action: str) -> tuple[tuple | None, float]:
        """The effect this action most often has on this entity, and how
        reliably — the fraction of the changes it caused that were that
        effect. (None, 0.0) below the evidence floor."""
        eff = self.effects.get(action, {})
        total = sum(eff.values())
        if total < BELIEF_DETERMINISM_MIN_CHANGES:
            return None, 0.0
        best = max(eff, key=eff.get)
        return best, eff[best] / total

    @property
    def controllers(self) -> list[tuple[str, tuple, float]]:
        """Actions that each do one fixed thing to this entity, with
        DISTINCT effects — the d-pad signature. Sorted by reliability."""
        out = []
        for action in self.acted:
            effect, rel = self.determinism(action)
            if effect is not None and rel >= BELIEF_DETERMINISM:
                out.append((action, effect, rel))
        if len({e for _a, e, _r in out}) < 2:
            return []
        return sorted(out, key=lambda t: -t[2])

    def kind_for(self, action: str | None) -> str | None:
        """The way this action most often changes this entity."""
        per = self.kinds.get(action or "", {})
        return max(per, key=per.get) if per else None

    @property
    def dominant_kind(self) -> str | None:
        """The way it most often changes at all, whatever the action."""
        total: dict[str, int] = {}
        for per in self.kinds.values():
            for k, n in per.items():
                total[k] = total.get(k, 0) + n
        return max(total, key=total.get) if total else None

    @property
    def observations(self) -> int:
        return sum(self.acted.values())

    @property
    def centroid(self) -> tuple[int, int] | None:
        """Where this entity is, as one board pixel — None if it has none.

        Descriptive, not interpretive: the mean of the cells it occupied
        on the last frame, rounded to the nearest cell. It says where the
        thing is, never what being there means. Reads `last_cells` rather
        than live cells for the same reason `observe` does — a vanished
        entity still has a last known position, and a target that
        evaporates the moment it is reached is not a target.
        """
        cells = self.last_cells
        if not cells:
            return None
        return (round(sum(c[0] for c in cells) / len(cells)),
                round(sum(c[1] for c in cells) / len(cells)))

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
        # Several actions each doing one fixed, different thing to this
        # entity is control regardless of rate: the rate contrast below
        # cannot see it, because a thing every button moves has no button
        # that stands out.
        if self.controllers:
            self._held = CONTROL
            return CONTROL
        _action, lift = self.selectivity
        # Hysteresis: keeping a role needs less than winning it did.
        bar = (BELIEF_SELECTIVITY - BELIEF_HYSTERESIS
               if self._held in (CONTROL, AFFECT) else BELIEF_SELECTIVITY)
        if lift >= bar:
            if self._selective_certainty < BELIEF_MIN_CERTAINTY:
                return UNASSIGNED
            # Control is motion under my hand; anything else I merely act
            # upon. Read from how the driving action changes it, not from
            # a global flag, so an entity that both moves and grows is
            # classified by what its *own* button does to it.
            action, _l = self.selectivity
            self._held = (CONTROL if self.kind_for(action) in MOTION_KINDS
                          else AFFECT)
            return self._held
        ctx_bar = (BELIEF_CONTEXT_BASELINE - BELIEF_HYSTERESIS
                   if self._held == CONTEXT else BELIEF_CONTEXT_BASELINE)
        if self.responsiveness >= ctx_bar:
            self._held = CONTEXT
            return CONTEXT
        if self.responsiveness == 0.0:
            return ENVIRONMENT
        return UNASSIGNED

    @property
    def _selective_certainty(self) -> float:
        """Confidence that the winning action's rate really beats the rest.

        Deliberately independent of `role`, because `role` consults it —
        making this dispatch on the role instead produced infinite
        recursion, caught by the tests.
        """
        action, _lift = self.selectivity
        if action is None:
            return 0.0
        n_a = self.acted.get(action, 0)
        hits_a = self.changed.get(action, 0)
        n_rest = self.observations - n_a
        hits_rest = sum(self.changed.values()) - hits_a
        if not n_a or not n_rest:
            return 0.0
        p_a, p_rest = hits_a / n_a, hits_rest / n_rest
        pooled = (hits_a + hits_rest) / (n_a + n_rest)
        spread = pooled * (1 - pooled) * (1 / n_a + 1 / n_rest)
        if spread <= 0:
            return 1.0 if p_a > p_rest else 0.0
        return _phi((p_a - p_rest) / math.sqrt(spread))

    @property
    def certainty(self) -> float:
        """How sure we are of this role, 0-1 — NOT the size of the effect.

        A lift of +100% seen four times is a weaker claim than +30% seen
        two hundred times, and reporting the lift alone would say the
        opposite. Sample size therefore enters the answer, which is what
        stops a rarely-tried action from looking decisive on a handful of
        tries.

        It saturates: past a few hundred observations nearly any real
        effect reads 100%, so this gates whether a role is claimed at all
        while `strength` is what gets shown.
        """
        role = self.role
        if role == ENVIRONMENT:
            return 1.0 if self.observations else 0.0
        if role == UNASSIGNED:
            return 0.0
        if role == CONTEXT:
            n = self.observations
            if not n:
                return 0.0
            return _one_sided(sum(self.changed.values()) / n,
                              BELIEF_CONTEXT_BASELINE, n)
        return self._selective_certainty

    @property
    def strength(self) -> float:
        """How reliably the role's relationship holds, 0-1.

        Distinct from `certainty`, and this is the one worth showing. With
        a few hundred observations the statistical confidence saturates at
        100% for every entity, so it discriminates nothing on screen; what
        varies, and what a reader wants, is *how dependable* the relation
        is:

          CONTROL / AFFECT  P(this entity changes | its driving action)
                            -- "press that and this responds, 93% of the time"
          CONTEXT           P(it changes at all | any action)
          ENVIRONMENT       how consistently it has stayed still

        `certainty` is still what decides whether a row is worth showing;
        `strength` is what the row says.
        """
        role = self.role
        if role == ENVIRONMENT:
            return 1.0
        if role == UNASSIGNED:
            return 0.0
        if role == CONTEXT:
            return self.responsiveness
        if role == CONTROL and self.controllers:
            return self.controllers[0][2]
        action, _lift = self.selectivity
        return self.rates.get(action, 0.0) if action else 0.0

    def describe(self) -> str:
        role = self.role
        if role == CONTROL and self.controllers:
            named = ", ".join(
                f"{a} {e[0]}{' ' + _dir_name(e) if len(e) == 3 else ''} it "
                f"({rel:.0%})"
                for a, e, rel in self.controllers[:4])
            return named
        if role in (CONTROL, AFFECT):
            drivers = self.drivers
            if not drivers:
                # Held under hysteresis: the role stands on less than the
                # winning bar, so `drivers` (which uses the full bar) is
                # empty. Name the winner anyway — a blank row was seen
                # live on cd82 and reads as a bug rather than as caution.
                action, lift = self.selectivity
                drivers = [(action, lift)] if action else []
            named = ", ".join(
                f"{a} {self.kind_for(a) or 'changes'} it +{lift:.0%}"
                for a, lift in drivers[:3])
            more = f" (+{len(drivers) - 3} more)" if len(drivers) > 3 else ""
            return f"{named}{more}"
        if role == CONTEXT:
            kind = self.dominant_kind or "changes"
            return (f"{kind} whatever I press "
                    f"({self.responsiveness:.0%} of steps)")
        if role == ENVIRONMENT:
            return "never changes"
        return "not enough evidence yet"


def _centroid(cells) -> tuple[float, float]:
    n = len(cells)
    return (sum(c[0] for c in cells) / n, sum(c[1] for c in cells) / n)


def _dir_name(effect: tuple) -> str:
    """(kind, sx, sy) -> a compass-free direction word pair."""
    _k, sx, sy = effect
    x = {-1: "-x", 0: "", 1: "+x"}[sx]
    y = {-1: "-y", 0: "", 1: "+y"}[sy]
    return (x + y) or "in place"


def _kind(belief, cells, hit: bool, first_seen: bool) -> tuple[str | None, tuple | None]:
    """How this entity changed, from its cells alone: (kind, effect).

    Nothing here knows anything about a game: the whole vocabulary is what
    happened to a set of cells. Never classifies on the first sighting —
    `last_cells` is initialised to the current cells, so without that guard
    an entity that appears reads as having moved, and a recolour would be
    described as motion, which is a claim about the world and the wrong one.

    `effect` is the kind plus, for motion, the direction — the unit of
    determinism.

    Motion is read from the EXTENT, not the size: a thing has moved along
    an axis when both edges of its bounding box shift the same way. Growth
    extends one edge and leaves the other; motion carries both. That
    separates the two without any tolerance constant, and it is what lets
    a thing that turns as it moves — re-rasterising to a different cell
    count at each angle — still be read as moving. Measured on cd82: the
    bucket's frame read GREW/SHRANK on every hop (30 cells above the block,
    43 beside it) and so could never be control, because control was
    defined as motion.
    """
    if first_seen:
        return (APPEARED, (APPEARED,)) if hit else (None, None)
    if not hit or cells == belief.last_cells:
        return None, None
    moved_x = _extent_shift(belief.last_cells, cells, 0)
    moved_y = _extent_shift(belief.last_cells, cells, 1)
    if moved_x or moved_y:
        return MOVED, (MOVED, moved_x, moved_y)
    if len(cells) != belief.last_size:
        kind = GREW if len(cells) > belief.last_size else SHRANK
        return kind, (kind,)
    # Same size, same extent, different cells: it turned on the spot.
    return TURNED, (TURNED,)


def _extent_shift(before, after, axis: int) -> int:
    """-1, 0 or +1: did the whole extent move along this axis?"""
    lo = min(c[axis] for c in after) - min(c[axis] for c in before)
    hi = max(c[axis] for c in after) - max(c[axis] for c in before)
    if lo > 0 and hi > 0:
        return 1
    if lo < 0 and hi < 0:
        return -1
    return 0


class WorldBelief:
    """Every entity's belief, updated once per decision."""

    def __init__(self) -> None:
        self._beliefs: dict[int, Belief] = {}
        # What happened to each entity on the most recent step, keyed the
        # way `Belief.effects` is keyed (effect tuple, `(kind,)`, or
        # UNCHANGED) — the ground truth a forecast is scored against.
        # Recording only; nothing here reads it.
        self.last_effects: dict[int, tuple] = {}

    def update(self, tracked: dict, action: str, changed_cells) -> None:
        """Fold one step into every entity on screen this frame.

        `tracked` is `RegionTracker.update`'s return value — what is
        present NOW, not its memory of what has been. An entity is
        "changed" this step if any cell that differed lies inside it, and
        "displaced" if its cells moved while its size held — a cheap proxy
        that deliberately does not re-run the motion lenses, since the point
        here is to relate evidence rather than to produce more of it.

        An entity that was on screen last step and is not now is observed
        exactly once more, as VANISHED, and then left alone: it cannot be
        observed while it is not there, and letting it accumulate "did not
        change" observations every step was quietly diluting the rates of
        everything that had merely moved out of the tracker's reach.
        """
        self.last_effects = {}
        if not action or action == "RESET":
            return
        touched = set(changed_cells or ())
        for rid, belief in self._beliefs.items():
            if belief.live and rid not in tracked:
                belief.observe(action, VANISHED)
                belief.live = False
                self.last_effects[rid] = (VANISHED,)
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
            kind, effect = _kind(belief, cells, hit, first_seen)
            belief.observe(action, kind, effect)
            self.last_effects[rid] = (UNCHANGED if kind is None
                                      else effect if effect is not None else (kind,))
            belief.last_size = len(cells)
            belief.last_cells = cells
            belief.live = True

    def by_role(self, role: str, live_only: bool = True) -> list[Belief]:
        """Every entity currently holding `role`, best evidence first.

        On-screen entities only by default: a role is a fact about a thing,
        but acting on it needs the thing to be there.
        """
        out = [b for b in self._beliefs.values()
               if b.role == role and (b.live or not live_only)]
        return sorted(out, key=lambda b: -b.selectivity[1])

    def summary(self) -> list[tuple[int, str, str, str]]:
        """(region id, colour, role, description, strength) per entity.

        A role whose statistical certainty is unconvincing is reported as
        UNASSIGNED rather than shown with a low number: "we are not sure"
        is a cleaner statement than a confident-looking row with a small
        percentage beside it.
        """
        return [(b.region_id, b.colour, b.role, b.describe(), b.strength)
                for b in sorted(self._beliefs.values(),
                                key=lambda b: -b.observations)]

    def ordered(self) -> list:
        """The Belief objects behind `summary()`, in the same order."""
        return sorted(self._beliefs.values(), key=lambda b: -b.observations)

    def clear(self) -> None:
        """New level: entity ids are gone, so the beliefs attached to them are too."""
        self._beliefs.clear()
