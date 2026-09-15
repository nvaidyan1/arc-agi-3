"""Hypotheses: a residual to drive to zero, an action to drive it with, and
the few steps in which it must earn its keep.

The first consumer of the brief, and the council's step (c): a goal is a
**checkable predicate over the relation state** — here always
`residual(rel, a, b) -> 0` — with the residual itself as the progress
measure, verified against the next few frames and *falsified* when it does
not move. Nothing here knows what a game is about; a hypothesis is a bet
that a coordinate some action has been seen to drive is worth driving.

Two proposers are planned. This file holds the first, the **enumerator**:
it reads the same records the brief reads, picks the residual with the
clearest lever, and bets on it. It exists so that the verification loop —
propose, act, check, falsify, cool down — is built and measured before any
language model is asked to propose. The LLM proposer (`docs/plan.md` 5b
(c)) slots in behind the same `Hypothesis` type; the loop does not change.

What a hypothesis costs is actions, and actions are the score, so every
hypothesis carries a budget and dies at it. Three ways one ends:

    held        the residual reached 0 — the predicate holds
    falsified   it rose twice running, or did not fall within PATIENCE steps
    expired     the budget ran out with it still falling — not wrong, unpaid

A falsified or expired key is cooled down so the enumerator does not
propose it again immediately; a held one is not, because holding is not
the same as mattering — whether it mattered is the level-boundary diff's
question, not this file's.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import relations as _relations
from constants import (
    HYPOTHESIS_BUDGET,
    HYPOTHESIS_COOLDOWN,
    HYPOTHESIS_PATIENCE,
)

LIVE, HELD, FALSIFIED, EXPIRED = "live", "held", "falsified", "expired"
# Per-step outcomes, so a failure says WHICH way it failed (reviewer C,
# 2026-09-14: a boolean verifier collapses "the hypothesis is wrong" into
# "its precondition was not met", and those are different layers).
SUPPORTED, UNMET, INCONCLUSIVE, AGAINST = "supported", "precondition_unmet", "inconclusive", "against"
# What a bet forecasts for its residual if its action is taken now: DOWN,
# or — for an exclusive bet whose precondition is unmet — NOT_DOWN. Two
# rivals about the same action diverge exactly when one says each (H004).
NOT_DOWN = "not_down"


def conditions_of(precondition) -> tuple:
    """Normalize `precondition` into a tuple of `(cond, member)` pairs,
    regardless of which shape produced it.

    H005: every proposer built so far (enumerator, LLM) stores a single
    pair directly — `precondition = ("adjacent:-y", 7)` — because no
    hypothesis has ever needed more than one condition. That shape is
    kept as-is (no proposer changed) rather than forced through a
    wrapping convention at construction time, so this is the one place
    that understands both: a bare pair (its first element is the
    condition string) is one condition; anything else is already a tuple
    of pairs (H005's conjunctive case — every named condition must hold).
    `None` and `()` both normalize to no conditions."""
    if not precondition:
        return ()
    if isinstance(precondition[0], str):
        return (precondition,)
    return tuple(precondition)


def _clause(cond: str, member: int) -> str:
    """One condition, readably: "adjacent on side -x of #7", or (H007)
    "#7 in state a1b2c3d4" for a `state:<token>` condition."""
    if cond.startswith(_relations.STATE + ":"):
        return f"#{member} in state {cond.partition(':')[2]}"
    return f"{cond.replace(':', ' on side ')} of #{member}"


def describe_conditions(precondition, exclusive: bool = False) -> str:
    """The human-readable clause `Hypothesis.describe()` and the brief's
    hypothesis log both want: "" with none, "only when X of #7" with one,
    "only when X of #7 and Y of #12" with several (H005, conjunctive)."""
    conds = conditions_of(precondition)
    if not conds:
        return ""
    only = "only " if exclusive else ""
    clauses = " and ".join(_clause(c, m) for c, m in conds)
    return f" {only}when {clauses}"


@dataclass
class Hypothesis:
    key: tuple                  # (relation, a, b)
    action: str                 # the lever
    lift: float                 # how much more this action moves it than others
    start: int                  # residual when proposed
    budget: int = HYPOTHESIS_BUDGET
    history: list = field(default_factory=list)
    status: str = LIVE
    # A single ("adjacent", member_id) pair, or (H005) a tuple of such
    # pairs meaning their conjunction — the controlled thing must be
    # within ADJACENT_GAP of EVERY named member before the action counts
    # as a test. Read through `conditions_of()`, never indexed directly:
    # that is what lets both shapes coexist without every proposer or
    # consumer needing to know which one produced a given hypothesis.
    precondition: tuple | None = None
    outcomes: list = field(default_factory=list)   # per step: SUPPORTED / AGAINST / UNMET / INCONCLUSIVE
    pending_met: bool = True                       # set by the policy at decision time
    # Where the bet came from and what it says about itself. The enumerator
    # fills lift and leaves the rest; a language model must state a
    # falsifier and a confidence or the hypothesis is rejected at parse.
    source: str = "enumerator"
    confidence: float = 0.5
    falsifier: str = ""
    predicted: str = "down"
    # H004: the rival reading of the same tally, and which reading this
    # is. An exclusive bet says the action moves the residual ONLY under
    # its precondition, so a step taken without it is evidence — a fall
    # there is a strike, a hold is support. A non-exclusive conditional
    # bet (H001) says nothing about those steps and files them as UNMET.
    exclusive: bool = False
    rival: "Hypothesis | None" = field(default=None, repr=False, compare=False)
    mets: list = field(default_factory=list)       # per step: was the precondition met
    strikes: int = 0                               # exclusive: falls seen without the precondition

    @property
    def spent(self) -> int:
        return len(self.history)

    @property
    def current(self) -> int | None:
        return self.history[-1] if self.history else self.start

    def forecast(self, met: bool) -> str | None:
        """What this bet says its residual will do if its action is taken
        now: DOWN; NOT_DOWN for an exclusive bet without its precondition;
        None when it makes no claim (a non-exclusive bet, unmet)."""
        if met or self.precondition is None:
            return _relations.DOWN
        return NOT_DOWN if self.exclusive else None

    def observe(self, residual: int | None, met: bool = True) -> str:
        """Fold in the residual seen after one step taken under this
        hypothesis, and return the status it now has.

        `met`: did the precondition hold when the action was taken? For a
        non-exclusive bet a step with it unmet costs budget and is recorded
        as PRECONDITION_UNMET; it is not evidence about the residual and
        cannot falsify. For an exclusive bet that step tests the ONLY: a
        fall is a strike (two falsify), a hold is support. Rising twice
        and stalling past patience are judged on met steps alone."""
        if self.status != LIVE:
            return self.status
        self.mets.append(met)
        if not met and not self.exclusive:
            self.history.append(None)
            self.outcomes.append(UNMET)
            return self._expire()
        self.history.append(residual)
        if residual is None:
            # The pair became undecidable (something left the screen). Not
            # evidence either way; it costs a step of budget and that is all.
            self.outcomes.append(INCONCLUSIVE)
            return self._expire()
        defined = [v for v in [self.start] + self.history if v is not None]
        fell = len(defined) >= 2 and defined[-1] < defined[-2]
        if not met:
            if fell:
                self.outcomes.append(AGAINST)
                self.strikes += 1
                if self.strikes >= 2:
                    self.status = FALSIFIED      # it moved without the precondition, twice
                    return self.status
            else:
                self.outcomes.append(SUPPORTED)
            return self._expire()
        if residual == 0:
            self.outcomes.append(SUPPORTED)
            self.status = HELD
            return self.status
        self.outcomes.append(SUPPORTED if fell else AGAINST)
        met_defined = [self.start] + [v for v, m in zip(self.history, self.mets) if m and v is not None]
        if len(met_defined) >= 3 and met_defined[-1] > met_defined[-2] > met_defined[-3]:
            self.status = FALSIFIED          # rose twice running
            return self.status
        if (len(met_defined) > HYPOTHESIS_PATIENCE
                and min(met_defined[-HYPOTHESIS_PATIENCE:]) >= met_defined[-HYPOTHESIS_PATIENCE - 1]):
            self.status = FALSIFIED          # no fall within patience
            return self.status
        return self._expire()

    def _expire(self) -> str:
        if self.spent >= self.budget:
            self.status = EXPIRED
        return self.status

    @property
    def unmet(self) -> int:
        return sum(1 for o in self.outcomes if o == UNMET)

    def describe(self) -> str:
        rel, a, b = self.key
        name = lambda k: ("{" + ",".join(f"#{m}" for m in k) + "}") if isinstance(k, tuple) else f"#{k}"  # noqa: E731
        cond = describe_conditions(self.precondition, self.exclusive)
        basis = f"lever +{self.lift:.0%}" if self.source == "enumerator" else f"{self.source}, confidence {self.confidence:.0%}"
        return (f"drive {rel}({name(a)},{name(b)}) {self.start}->0 with {self.action}{cond} "
                f"({basis}), step {self.spent}/{self.budget}, now {self.current}")


class Proposer:
    """The enumerator. Picks the live pair whose residual is positive and
    has the clearest DOWN lever among the legal actions."""

    def __init__(self) -> None:
        self._cooldown: dict[tuple, int] = {}   # key -> step it may be proposed again
        self.log: list[tuple] = []              # (key, action, start, end, status, spent, unmet, precondition, exclusive, source)
        # `source` at the end, appended after `exclusive`, rather than
        # reordering the existing 9 fields: kept every reader that already
        # unpacks this tuple positionally (agent/brief.py) from silently
        # taking the wrong field when this was added. Needed to check
        # reviewer C's bottleneck #4 (second review, 2026-09-14,
        # "exploration policy": is action budget being spent reaching a
        # hypothesis rather than the hypothesis being wrong) SEPARATELY
        # for LLM- vs enumerator-sourced bets -- `closed_by_source` has
        # the status counts but not the unmet/spent figures this needs.
        self.closed_by_source: dict[str, dict[str, int]] = {}   # "enumerator"/"llm" -> status -> n
        # H004 accounting: rival pairs proposed, presses taken where two
        # live bets on the action disagreed, and which of a pair died first.
        self.rivals = 0
        self.discriminating = 0
        self.rival_outcomes: dict[str, int] = {}
        # A bet the pool drops because its entities left the screen, before
        # it was ever selected — distinct from `close()`, which only ever
        # sees a bet that reached a verdict or lost its action's legality.
        # Added after E-H002-1 (2026-09-14) found 12 valid LLM hypotheses
        # generated on cd82 and only 2 ever closed, with the gap
        # unexplained: this answers whether the other 10 lost a selection
        # contest (measurable via `close`) or simply vanished off-screen
        # first (this counter) — different problems, different fixes.
        self.evicted_by_source: dict[str, int] = {}

    def clear(self) -> None:
        self.__init__()

    def cool(self, key: tuple, step: int) -> None:
        self._cooldown[key] = step + HYPOTHESIS_COOLDOWN

    def evict(self, h: Hypothesis) -> None:
        """A live bet dropped from the pool because an entity it names is
        no longer on screen — never tested, never a verdict. See
        `evicted_by_source`."""
        self.evicted_by_source[h.source] = self.evicted_by_source.get(h.source, 0) + 1

    def close(self, h: Hypothesis, step: int) -> None:
        self.log.append((h.key, h.action, h.start, h.current, h.status, h.spent, h.unmet,
                         h.precondition, h.exclusive, h.source))
        self.closed_by_source[h.source] = self.closed_by_source.get(h.source, {})
        self.closed_by_source[h.source][h.status] = self.closed_by_source[h.source].get(h.status, 0) + 1
        if h.rival is not None:
            # A bet dropped while still LIVE (its action stopped being legal)
            # did not die: it is unlinked, not counted, and its partner goes
            # on alone. Only a verdict counts — and only the first of the pair.
            if h.status == LIVE:
                h.rival.rival = None
                h.rival = None
            elif h.rival.status == LIVE:
                which = ("specific" if h.precondition is not None else "general") + "_died_first"
                self.rival_outcomes[which] = self.rival_outcomes.get(which, 0) + 1
        # An expiry spent mostly failing to reach the precondition says
        # nothing about the residual; a short cooldown, not the full one.
        if h.status == FALSIFIED or (h.status == EXPIRED and h.unmet * 2 < max(h.spent, 1)):
            self.cool(h.key, step)
        elif h.status == EXPIRED:
            self._cooldown[h.key] = step + HYPOTHESIS_COOLDOWN // 4

    def rival(self, h: Hypothesis, rec, control: set[int] = frozenset()) -> Hypothesis | None:
        """The competing reading of the tally `h` was drawn from, or None.

        A conditional bet's rival is the general rule (same action, no
        precondition), and the conditional bet becomes exclusive: the two
        now disagree whenever the precondition is unmet, and a press there
        settles it. A general bet's rival is the exclusive rule under the
        condition where the action's DOWN rate stands out from its overall
        rate by LEVER_MIN_LIFT — no such condition, no rival. Nothing is
        asserted about the game either way: both readings are the same
        tally, and both die by observations the vocabulary already makes."""
        if rec is None or h.rival is not None or h.action == "ACTION6":
            return None
        rel, a, b = h.key
        members = [m for side in (a, b) for m in (side if isinstance(side, tuple) else (side,))]
        if h.precondition is not None:
            lever = rec.lever(_relations.DOWN)
            lift = lever[1] if lever is not None and lever[0] == h.action else 0.0
            other = Hypothesis(key=h.key, action=h.action, lift=lift, start=h.start,
                               source=h.source, confidence=h.confidence)
            h.exclusive = True
        else:
            tally = rec.by_action.get(h.action, {})
            n = sum(tally.values())
            overall = tally.get(_relations.DOWN, 0) / n if n else 0.0
            best = None
            for cond, actions in rec.by_action_given.items():
                t = actions.get(h.action)
                if t is None or sum(t.values()) < _relations.LEVER_MIN_TRIES:
                    continue
                rate = t[_relations.DOWN] / sum(t.values())
                if rate - overall >= _relations.LEVER_MIN_LIFT and (best is None or rate > best[1]):
                    best = (cond, rate)
            targets = [m for m in members if m not in control]
            if best is None or not targets:
                return None
            other = Hypothesis(key=h.key, action=h.action, lift=best[1] - overall, start=h.start,
                               precondition=(best[0], targets[0]), exclusive=True,
                               source=h.source, confidence=h.confidence)
        h.rival, other.rival = other, h
        self.rivals += 1
        return other

    def propose(self, engine, live, legal: set[str], step: int,
                exclude: set[int] = frozenset(), prior=None, typer=None,
                won: dict[str, int] | None = None, bonus=None,
                control: set[int] = frozenset()) -> Hypothesis | None:
        """`exclude` is for entities belief has judged CONTEXT — things
        that change whatever is pressed. Their relations can carry a
        lever by chance (cd82's stamina bar earned a +30% lever on four
        presses) and are never goals I can drive; the belief layer has
        already made that judgement, so it is reused rather than remade.

        `prior(typed_key) -> int` and `typer(key) -> typed_key` come from
        the level-boundary supervisor: a candidate whose colour-typed
        relation has fallen into a past advance ranks first, then one
        whose lever has been a winning move (`won`), then by lever
        strength. Weights, not rules — every other candidate stays
        proposable."""
        won = won or {}
        best = None
        both = list(engine.records.items()) + list(getattr(engine, "group_records", {}).items())
        for key, rec in both:
            rel, a, b = key
            if rel in _relations.EVIDENCE_ONLY or rel == "distance_drift":
                continue
            # Members: an int for a pair record, a tuple of ids for a group.
            members = [m for side in (a, b) for m in (side if isinstance(side, tuple) else (side,))]
            if any(m not in live or m in exclude for m in members):
                continue
            if rec.residual is None or rec.residual <= 0:
                continue
            if self._cooldown.get(key, -1) > step:
                continue
            precondition = None
            lever = rec.lever(_relations.DOWN)
            if lever is None:
                # No unconditional lever: is there a conditional one? The
                # precondition names a non-control member the controlled
                # thing must be adjacent to; the policy routes there first.
                cl = rec.conditional_lever(_relations.DOWN)
                if cl is not None and cl[1].startswith(_relations.ADJACENT):
                    targets = [m for m in members if m not in control]
                    if targets:
                        lever = (cl[0], cl[2])
                        precondition = (cl[1], targets[0])     # e.g. ("adjacent:-y", member)
            if lever is None or lever[0] not in legal or lever[0] == "ACTION6":
                # ACTION6 needs a coordinate the lever does not carry; a
                # click-driven hypothesis waits for a proposer that says
                # where to click.
                continue
            action, lift = lever
            mattered = prior(typer(key)) if (prior and typer) else 0
            extra = bonus(key) if bonus else 0
            cand = (mattered, extra, won.get(action, 0), lift, -rec.residual, key)
            if best is None or cand > best[0]:
                best = (cand, Hypothesis(key=key, action=action, lift=lift, start=rec.residual,
                                         precondition=precondition))
        return best[1] if best else None
