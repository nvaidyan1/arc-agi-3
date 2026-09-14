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


@dataclass
class Hypothesis:
    key: tuple                  # (relation, a, b)
    action: str                 # the lever
    lift: float                 # how much more this action moves it than others
    start: int                  # residual when proposed
    budget: int = HYPOTHESIS_BUDGET
    history: list = field(default_factory=list)
    status: str = LIVE

    @property
    def spent(self) -> int:
        return len(self.history)

    @property
    def current(self) -> int | None:
        return self.history[-1] if self.history else self.start

    def observe(self, residual: int | None) -> str:
        """Fold in the residual seen after one step taken under this
        hypothesis, and return the status it now has."""
        if self.status != LIVE:
            return self.status
        self.history.append(residual)
        values = [self.start] + [v for v in self.history]
        if residual is None:
            # The pair became undecidable (something left the screen). Not
            # evidence either way; it costs a step of budget and that is all.
            pass
        elif residual == 0:
            self.status = HELD
            return self.status
        else:
            defined = [v for v in values if v is not None]
            if len(defined) >= 3 and defined[-1] > defined[-2] > defined[-3]:
                self.status = FALSIFIED          # rose twice running
                return self.status
            if (len(defined) > HYPOTHESIS_PATIENCE
                    and min(defined[-HYPOTHESIS_PATIENCE:]) >= defined[-HYPOTHESIS_PATIENCE - 1]):
                self.status = FALSIFIED          # no fall within patience
                return self.status
        if self.spent >= self.budget:
            self.status = EXPIRED
        return self.status

    def describe(self) -> str:
        rel, a, b = self.key
        name = lambda k: ("{" + ",".join(f"#{m}" for m in k) + "}") if isinstance(k, tuple) else f"#{k}"  # noqa: E731
        return (f"drive {rel}({name(a)},{name(b)}) {self.start}->0 with {self.action} "
                f"(lever +{self.lift:.0%}), step {self.spent}/{self.budget}, now {self.current}")


class Proposer:
    """The enumerator. Picks the live pair whose residual is positive and
    has the clearest DOWN lever among the legal actions."""

    def __init__(self) -> None:
        self._cooldown: dict[tuple, int] = {}   # key -> step it may be proposed again
        self.log: list[tuple] = []              # (key, action, start, end, status, spent)

    def clear(self) -> None:
        self.__init__()

    def cool(self, key: tuple, step: int) -> None:
        self._cooldown[key] = step + HYPOTHESIS_COOLDOWN

    def close(self, h: Hypothesis, step: int) -> None:
        self.log.append((h.key, h.action, h.start, h.current, h.status, h.spent))
        if h.status in (FALSIFIED, EXPIRED):
            self.cool(h.key, step)

    def propose(self, engine, live, legal: set[str], step: int,
                exclude: set[int] = frozenset(), prior=None, typer=None,
                won: dict[str, int] | None = None, bonus=None) -> Hypothesis | None:
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
            lever = rec.lever(_relations.DOWN)
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
                best = (cand, Hypothesis(key=key, action=action, lift=lift, start=rec.residual))
        return best[1] if best else None
