"""The brief: what the agent would tell a hypothesis proposer, as text.

The council's last instruction was to design the serialisation the proposer
reads *before* writing the proposer (`docs/council_2026-09-14_belief.md`).
This is that serialisation, and it is shown live in the recap so it can be
read as it would be sent — not reconstructed afterwards.

Everything in it is already believed elsewhere; nothing is computed here
that a layer below has not earned. The brief only selects and phrases:

  THINGS      live entities, role first, static ones compressed
  CONTROL     what each action does, from the move map and belief
  RELATIONS   residuals that have moved on this level, most recent first,
              each with the actions that moved it — the levers
  FALLING     residuals a recent action drove down: candidate goals
  OPEN        how much is undecidable, and a few concrete questions
  RECENT      the last few steps as events

Constraints, so the text does not smuggle in what the layers refuse to:
roles are the relational ones (CONTROL / AFFECT / CONTEXT), never PLAYER
or GOAL; relations are named by their residual, not by what they might
mean; nothing is ranked by how goal-like it looks — RELATIONS is ordered
by recency and FALLING by recent movement, both facts about what
happened. Bounded to a few dozen lines by construction: a brief a proposer
cannot read in one pass is worse than a short one that omits.
"""
from __future__ import annotations

from collections import deque

import belief as _belief
import relations as _relations

MAX_THINGS = 12
MAX_STATIC = 6
MAX_RELATIONS = 10
MAX_FALLING = 5
MAX_OPEN = 3
RECENT_STEPS = 8
RELATION_MEMORY = 30      # a residual that moved longer ago than this is not "current"
FALLING_WINDOW = 5


class Briefer:
    """Keeps the little state a brief needs — when each residual last moved,
    and the last few steps as events — and composes the text on demand."""

    def __init__(self) -> None:
        self._step = 0
        self._last_moved: dict[tuple, int] = {}
        self._down_recent: dict[tuple, deque] = {}
        self._events: deque[str] = deque(maxlen=RECENT_STEPS)
        self._prev_live: set[int] = set()

    def clear(self) -> None:
        self.__init__()

    # ── per step ────────────────────────────────────────────────────────

    def record(self, agent, action_name: str) -> None:
        """Call once per step after every layer has updated."""
        self._step += 1
        live = set(agent.regions.live)
        moved = agent.relations.moved()
        parts = []
        for key, prev, cur in moved:
            self._last_moved[key] = self._step
            if key[0] not in _relations.EVIDENCE_ONLY and cur < prev:
                q = self._down_recent.setdefault(key, deque(maxlen=FALLING_WINDOW))
                q.append(self._step)
        # Events: identity changes and the few most informative residual moves.
        for rid in sorted(live - self._prev_live):
            parts.append(f"#{rid} appeared")
        for rid in sorted(self._prev_live - live):
            parts.append(f"#{rid} vanished")
        exchanges = [(k, c) for k, _p, c in moved if k[0] == "cell_exchange" and c]
        for (rel, a, b), c in exchanges[:2]:
            parts.append(f"#{a} lost {c} cells that #{b} gained")
        # Drift is a derivative and reads 0 whenever things stop; as an
        # event it says nothing the distance move did not already say.
        goal_moves = [(k, p, c) for k, p, c in moved
                      if k[0] not in _relations.EVIDENCE_ONLY and k[0] != "distance_drift"]
        for (rel, a, b), p, c in sorted(goal_moves, key=lambda m: -abs(m[1] - m[2]))[:3]:
            parts.append(f"{rel}(#{a},#{b}) {p}->{c}")
        if parts:
            self._events.append(f"t={self._step} {action_name}: " + "; ".join(parts))
        else:
            self._events.append(f"t={self._step} {action_name}: nothing changed")
        self._prev_live = live

    # ── the text ────────────────────────────────────────────────────────

    def compose(self, agent, level: int | None = None) -> str:
        out: list[str] = []
        stamina = agent.stamina.stamina_fraction
        head = f"step {self._step} of this level"
        if level is not None:
            head += f"  (level {level})"
        if stamina is not None:
            head += f"  stamina {stamina:.0%}"
        out.append(head)

        out.extend(self._things(agent))
        out.extend(self._groups(agent))
        out.extend(self._control(agent))
        out.extend(self._relations(agent))
        out.extend(self._falling(agent))
        out.extend(self._open(agent))
        out.append("RECENT")
        out.extend(f"  {e}" for e in self._events)
        return "\n".join(out)

    def _things(self, agent) -> list[str]:
        live = agent.regions.live
        rows, static = [], []
        for b in agent.belief.ordered():
            if b.region_id not in live:
                continue
            cells = agent.regions._tracked[b.region_id][1]
            where = b.centroid
            desc = f"#{b.region_id} colour {b.colour} {len(cells)} cells at {where}"
            role = b.role
            if b.region_id in agent._canvas_ids():
                rows.insert(0, f"  {desc}  — the canvas")
                continue
            if role == _belief.ENVIRONMENT:
                static.append(desc)
            elif role == _belief.UNASSIGNED:
                rows.append(f"  {desc}  — no role yet ({b.observations} obs)")
            else:
                rows.append(f"  {desc}  {role.upper()} — {b.describe()}")
        out = [f"THINGS ({len(live)} on screen)"]
        out.extend(rows[:MAX_THINGS])
        if len(rows) > MAX_THINGS:
            out.append(f"  … {len(rows) - MAX_THINGS} more with roles")
        if static:
            shown = "; ".join(s.replace(" cells at", "c @") for s in static[:MAX_STATIC])
            more = f" … +{len(static) - MAX_STATIC}" if len(static) > MAX_STATIC else ""
            out.append(f"  static ({len(static)}): {shown}{more}")
        return out

    def _groups(self, agent) -> list[str]:
        groups = agent.relations.groups()
        if not groups:
            return []
        out = ["GROUPS (things that persistently sit inside one another or trade cells — a view, not a claim)"]
        for g in groups[:6]:
            cols = sorted({agent.regions._tracked[r][0] for r in g})
            out.append(f"  {{{', '.join(f'#{r}' for r in sorted(g))}}} colours {cols}")
        # Group-level residuals that have moved recently, or hold.
        # Group-to-group rows first (two composite things compared), then
        # group-to-singleton; within each, lowest residual first.
        shown = 0
        for (rel, ka, kb), rec in sorted(agent.relations.group_records.items(),
                                         key=lambda kv: (kv[1].residual is None,
                                                         not (len(kv[0][1]) > 1 and len(kv[0][2]) > 1),
                                                         kv[1].residual or 0)):
            if rec.residual is None or (rec.residual > 0 and not rec.moved and rec.defined_steps > 5 and shown):
                continue
            name = lambda k: "{" + ",".join(f"#{r}" for r in k) + "}" if len(k) > 1 else f"#{k[0]}"
            line = f"  {rel}({name(ka)}, {name(kb)}) = {rec.residual}"
            lever = rec.lever(_relations.DOWN)
            if lever:
                line += f"   {lever[0]} drives it down"
            out.append(line); shown += 1
            if shown >= 6:
                break
        return out

    def _control(self, agent) -> list[str]:
        moves = agent.moves.learned_moves
        canvas = agent._canvas_ids()
        control = [b for b in agent.belief.by_role(_belief.CONTROL) if b.region_id not in canvas]
        lines = []
        for action, off in sorted(moves.items(), key=lambda kv: kv[0].name):
            # Name only the things THIS action is known to move: an entity
            # that is CONTROL because a click turns it is not moved by the
            # d-pad, and listing it there was a false statement.
            what = [f"#{b.region_id}" for b in control
                    if action.name in {a for a, _e, _r in b.controllers}
                    or action.name in {a for a, _l in b.drivers}]
            lines.append(f"  {action.name} moves {', '.join(what[:4]) or 'something'} by {off}")
        # Actions belief knows about that the move map does not.
        known = {a.name for a in moves}
        by_action: dict[str, list[str]] = {}
        for b in agent.belief.ordered():
            if b.region_id not in agent.regions.live or b.role not in (_belief.CONTROL, _belief.AFFECT):
                continue
            for a, lift in b.drivers[:3]:
                if a in known:
                    continue
                by_action.setdefault(a, []).append(f"{b.kind_for(a) or 'changes'} #{b.region_id}")
        for a in sorted(by_action):
            lines.append(f"  {a} {', '.join(by_action[a][:4])}")
        return ["CONTROL"] + (lines or ["  nothing learned yet"])

    def _relations(self, agent) -> list[str]:
        live = agent.regions.live
        recent = [(k, t) for k, t in self._last_moved.items()
                  if k[0] not in _relations.EVIDENCE_ONLY
                  and self._step - t <= RELATION_MEMORY
                  and k[1] in live and k[2] in live]
        recent.sort(key=lambda kt: -kt[1])
        # One moving thing changes its relation to everything static in the
        # same way at the same time: on cd82 the bucket's move produced ten
        # rows of distance/containment(static, bucket) with identical lever
        # tallies. Rows that share a relation, a member and the same lever
        # signature are one fact — the thing moved — and are written once,
        # with the partners listed. This is compression, not selection:
        # nothing is dropped, and the residuals stay per pair.
        # Anchor each row on the member that takes part in more moving
        # relations — the thing that moved — so the statics are the list.
        degree: dict[int, int] = {}
        for (rel, a, b), _t in recent:
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
        groups: dict[tuple, list] = {}
        for key, t in recent:
            rec = agent.relations.records[key]
            rel, a, b = key
            anchor, other = (a, b) if degree[a] >= degree[b] else (b, a)
            # Levers, not movers: an action that drives the residual more
            # than the others do. A residual every action moves alike is
            # the weather, and is said to be.
            levers = (rec.lever(_relations.DOWN), rec.lever(_relations.UP))
            groups.setdefault((rel, anchor, levers), []).append((other, rec.residual, t))
        rows = sorted(groups.items(), key=lambda g: -max(m[2] for m in g[1]))
        out = [f"RELATIONS (residual, 0 = holds; moved on this level, newest first)"]
        for (rel, anchor, (down, up)), members in rows[:MAX_RELATIONS]:
            if len(members) == 1:
                other, val, _t = members[0]
                line = f"  {rel}(#{anchor},#{other}) = {val}"
            else:
                vals = ", ".join(f"#{o}={v}" for o, v, _t in members[:6])
                more = f" … +{len(members) - 6}" if len(members) > 6 else ""
                line = f"  {rel}(#{anchor}, each of {vals}{more})"
            if down:
                line += f"   {down[0]} drives it down (+{down[1]:.0%} over other actions)"
            if up:
                line += f"   {up[0]} drives it up (+{up[1]:.0%})"
            if not down and not up:
                line += "   moves under every action alike"
            out.append(line)
        if not recent:
            out.append("  nothing has moved yet")
        return out

    def _falling(self, agent) -> list[str]:
        live = agent.regions.live
        falling = []
        for key, steps in self._down_recent.items():
            n = sum(1 for s in steps if self._step - s < FALLING_WINDOW)
            if n >= 2 and key[1] in live and key[2] in live:
                rec = agent.relations.records[key]
                lever = rec.lever(_relations.DOWN)
                if lever is None:
                    continue        # falling on its own is a drain, not a candidate
                falling.append((n, key, rec.residual, lever))
        falling.sort(key=lambda f: (-f[0], f[2] if f[2] is not None else 1e9))
        out = [f"FALLING (down >= 2 times in the last {FALLING_WINDOW} steps AND some action drives it)"]
        for n, (rel, a, b), val, (act, lift) in falling[:MAX_FALLING]:
            out.append(f"  {rel}(#{a},#{b}) = {val}   down x{n}, {act} drives it")
        if not falling:
            out.append("  nothing")
        return out

    def _open(self, agent) -> list[str]:
        live = agent.regions.live
        undecided = agent.relations.undecided()
        both_live = [k for k in undecided if k[1] in live and k[2] in live
                     and k[0] not in _relations.EVIDENCE_ONLY]
        ghosts = len(undecided) - len(both_live)
        out = [f"OPEN ({len(both_live)} undecidable between things on screen, "
               f"{ghosts} involving things off screen)"]
        for rel, a, b in both_live[:MAX_OPEN]:
            out.append(f"  {rel}(#{a},#{b}) — not yet decidable")
        return out
