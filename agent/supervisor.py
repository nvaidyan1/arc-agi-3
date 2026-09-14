"""The level-boundary diff: what has ever mattered, learned from advances.

The one signal this environment certifies is a level advance. The council
called it the undervalued asset (`docs/council_2026-09-14_belief.md`):
every advance is a free, per-episode, unbaked label of what the goal
*was* — the coordinates that were collapsing as the level ended are the
answer, and no game knowledge was used to read it.

This module keeps the last few residual vectors, and at an advance asks
which residuals were falling into it *under a lever* (the same test as the
relation probe's (iii')). Entity ids die with the level, so what is kept is
**typed by colour**: "part_size_diff between a {0,15} thing and a
{0,4,5,15} thing fell into the advance", and "ACTION5 was the winning
move". The proposer then ranks a candidate whose type has mattered ahead
of one that has not, and a lever that has won ahead of one that has not.

Three limits, on purpose:

  * It **weights**, it never asserts. Goals may change per level (the
    plan says nothing may assume otherwise), so a type that mattered once
    is a preference, not a rule, and a type that never mattered is still
    proposable.
  * It is **per episode**. Nothing crosses games; the competition's
    evaluation philosophy is explicit about that and so is this project.
  * It records only what the vocabulary can express. An advance with no
    falling lever coordinate teaches nothing here — which is exactly the
    signal that the vocabulary is missing something, and that is written
    down rather than papered over.
"""
from __future__ import annotations

from collections import deque

import relations as _relations

WINDOW = 8


def type_of(key: tuple, colour_of) -> tuple | None:
    """A relation key with its ids replaced by colour sets, sides ordered
    for symmetric relations. `colour_of(id) -> int | None`."""
    rel, a, b = key
    def side(x):
        ids = x if isinstance(x, tuple) else (x,)
        cols = [colour_of(i) for i in ids]
        return None if any(c is None for c in cols) else frozenset(cols)
    ca, cb = side(a), side(b)
    if ca is None or cb is None:
        return None
    if rel in _relations.SYMMETRIC or rel == "part_size_diff":
        ca, cb = sorted((ca, cb), key=lambda s: sorted(s))
    return (rel, ca, cb)


class BoundarySupervisor:
    def __init__(self) -> None:
        self._window: deque[dict] = deque(maxlen=WINDOW)
        # (relation, colours_a, colours_b) -> how many advances it fell into
        self.mattered: dict[tuple, int] = {}
        # action name -> how many advances it was the winning move of
        self.won: dict[str, int] = {}
        self.advances = 0
        self.unexplained = 0          # advances with no falling lever coordinate
        self.last: list[str] = []     # human-readable record of the last advance

    def observe(self, snapshot: dict) -> None:
        """Call once per step with `engine.snapshot()`."""
        self._window.append(snapshot)

    def on_advance(self, engine, colour_of, winning_action: str | None) -> list[tuple]:
        """The level just ended; read what was falling into it.

        `engine` still holds the old level's records (this must run before
        the level reset). Returns the typed keys that mattered."""
        self.advances += 1
        if winning_action:
            self.won[winning_action] = self.won.get(winning_action, 0) + 1
        window = list(self._window)
        found: list[tuple] = []
        if len(window) >= 3:
            keys = set().union(*(set(s) for s in window))
            for key in keys:
                rel = key[0]
                if rel in _relations.EVIDENCE_ONLY or rel == "distance_drift":
                    continue
                series = [s.get(key) for s in window]
                if any(v is None for v in series):
                    continue
                if not (all(x >= y for x, y in zip(series, series[1:])) and series[0] > series[-1]):
                    continue
                rec = engine.record(key)
                if rec is None or rec.lever(_relations.DOWN) is None:
                    continue
                typed = type_of(key, colour_of)
                if typed is None or typed in found:
                    continue          # one count per type per advance, however many pairs
                found.append(typed)
                self.mattered[typed] = self.mattered.get(typed, 0) + 1
        if not found:
            self.unexplained += 1
        self.last = [f"{rel} between {sorted(ca)} and {sorted(cb)}" for rel, ca, cb in found]
        self._window.clear()
        return found

    def clear_window(self) -> None:
        """A reset within a level: the frames before it are not the run-up
        to anything."""
        self._window.clear()

    def prior(self, typed: tuple | None) -> int:
        return self.mattered.get(typed, 0) if typed is not None else 0

    def describe(self) -> list[str]:
        if not self.advances:
            return []
        out = [f"MATTERED (from {self.advances} level advance{'s' if self.advances != 1 else ''} this game"
               + (f", {self.unexplained} with no expressible coordinate" if self.unexplained else "") + ")"]
        for (rel, ca, cb), n in sorted(self.mattered.items(), key=lambda kv: -kv[1])[:5]:
            out.append(f"  {rel} between a {sorted(ca)} thing and a {sorted(cb)} thing fell into {n} advance{'s' if n != 1 else ''}")
        if self.won:
            out.append("  winning moves: " + ", ".join(f"{a} x{n}" for a, n in sorted(self.won.items(), key=lambda kv: -kv[1])))
        return out
