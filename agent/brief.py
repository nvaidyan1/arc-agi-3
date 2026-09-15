"""The brief: what the agent would tell a hypothesis proposer, as text.

The council's last instruction was to design the serialisation the proposer
reads *before* writing the proposer (`docs/council_2026-09-14_belief.md`).
This is that serialisation, and it is shown live in the recap so it can be
read as it would be sent — not reconstructed afterwards.

Everything in it is already believed elsewhere; nothing is computed here
that a layer below has not earned. The brief only selects and phrases:

  THINGS      live entities, role first, static ones compressed
  CONTROL     what each action does, from the move map and belief
  PREDICTED   how well the tallies forecast the last frames, per layer,
              and the confident misses — where the vocabulary is short
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
import hypothesis as _hypothesis
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

    def record(self, agent, action_name: str, action_data=None) -> None:
        """Call once per step after every layer has updated.

        `action_data` is the coordinate payload when the action carried
        one: eight lines of bare "ACTION6" are unreadable (the vc33 cold
        read asked for exactly this).
        """
        self._step += 1
        if action_data is not None and getattr(action_data, "x", None) is not None:
            action_name = f"{action_name}@({action_data.x},{action_data.y})"
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

    def compose(self, agent, level: int | None = None, available=None) -> str:
        out: list[str] = []
        stamina = agent.stamina.stamina_fraction
        head = f"step {self._step} of this level"
        if level is not None:
            head += f"  (level {level})"
        if stamina is not None:
            head += f"  stamina {stamina:.0%}"
        out.append(head)
        # What can be pressed. The vc33 cold reader planned three moves on
        # a click-only game; the frame knew and the brief did not say.
        if available:
            names = [f"ACTION{a}" if isinstance(a, int) else str(a) for a in available]
            out.append("ACTIONS available: " + ", ".join(names)
                       + ("  (ACTION6 takes an x,y)" if any(n == "ACTION6" for n in names) else ""))

        out.extend(self._hypothesis(agent))
        sup = getattr(agent, "supervisor", None)
        if sup is not None:
            out.extend(sup.describe())
        out.extend(self._things(agent))
        out.extend(self._groups(agent))
        km = getattr(agent, "kinds", None)
        if km is not None:
            out.extend(km.describe(getattr(agent, "_kinds_now", []), agent.relations))
        out.extend(self._control(agent))
        pred = getattr(agent, "predictor", None)
        if pred is not None:
            out.extend(pred.describe())
        out.extend(self._relations(agent))
        out.extend(self._falling(agent))
        out.extend(self._open(agent))
        out.append("RECENT")
        out.extend(f"  {e}" for e in self._events)
        return "\n".join(out)

    def _hypothesis(self, agent) -> list[str]:
        h = getattr(agent, "hypothesis", None)
        proposer = getattr(agent, "proposer", None)
        if h is None and not (proposer and proposer.log):
            return []
        out = ["HYPOTHESIS"]
        if h is not None:
            out.append(f"  testing: {h.describe()}")
            if h.falsifier:
                out.append(f"    falsified if: {h.falsifier}")
            rival = getattr(h, "rival", None)
            if rival is not None:
                out.append(f"    vs rival: {rival.describe()} [{rival.status}]")
        pool = getattr(agent, "pool", None)
        if pool:
            out.append(f"  waiting: {len(pool)} more bet{'s' if len(pool) != 1 else ''}"
                       + (f", {sum(1 for g in pool if g.source.startswith('llm'))} from the model"
                          if any(g.source.startswith('llm') for g in pool) else ""))
        if proposer and getattr(proposer, "rivals", 0):
            outcomes = ", ".join(f"{k.replace('_', ' ')} x{n}" for k, n in sorted(proposer.rival_outcomes.items()))
            out.append(f"  rivals: {proposer.rivals} pair{'s' if proposer.rivals != 1 else ''} proposed, "
                       f"{proposer.discriminating} discriminating press{'es' if proposer.discriminating != 1 else ''}"
                       + (f"; {outcomes}" if outcomes else ""))
        if proposer and proposer.log:
            name = lambda k: ("{" + ",".join(f"#{m}" for m in k) + "}") if isinstance(k, tuple) else f"#{k}"  # noqa: E731
            for key, action, start, end, status, spent, unmet, precondition, exclusive, _source in proposer.log[-3:]:
                rel, a, b = key
                extra = f", {unmet} with the precondition unmet" if unmet else ""
                cond = _hypothesis.describe_conditions(precondition, exclusive)
                out.append(f"  {status}: {rel}({name(a)},{name(b)}) {start}->{end} with {action}{cond} in {spent} steps{extra}")
        return out

    def _things(self, agent) -> list[str]:
        live = agent.regions.live
        rows, static = [], []
        for b in agent.belief.ordered():
            if b.region_id not in live:
                continue
            cells = agent.regions._tracked[b.region_id][1]
            where = b.centroid
            xs = [c[0] for c in cells]; ys = [c[1] for c in cells]
            # Extent as w x h: descriptive, not alignment. With shape_diff
            # equality-only, every shape row read "not decidable" and a
            # reader could not tell an L-piece from a bar.
            desc = (f"#{b.region_id} colour {b.colour} {len(cells)} cells "
                    f"{max(xs)-min(xs)+1}x{max(ys)-min(ys)+1} at {where}")
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
        # One line per pair of groups (composites compared with composites
        # first, then a group against a lone thing): the whole profile of
        # the pair on one row, most-related pairs first. A flat sort by
        # residual put eight palette_missing = 1 rows ahead of the one
        # part_size_diff row that carries the gradient on cd82.
        live = agent.regions.live
        profiles: dict[tuple, dict] = {}
        for (rel, ka, kb), rec in agent.relations.group_records.items():
            if rec.residual is None:
                continue
            if not all(m in live for m in ka) or not all(m in live for m in kb):
                continue
            pair = (ka, kb) if (ka, kb) in profiles or (kb, ka) not in profiles else (kb, ka)
            profiles.setdefault(pair, {})[(rel, ka, kb)] = rec
        name = lambda k: ("{" + ",".join(f"#{r}" for r in k) + "}") if len(k) > 1 else f"#{k[0]}"  # noqa: E731

        def relatedness(item):
            (ka, kb), recs = item
            missing = [r.residual for (rel, a, b), r in recs.items() if rel == "palette_missing"]
            return (not (len(ka) > 1 and len(kb) > 1), min(missing) if missing else 99)

        for (ka, kb), recs in sorted(profiles.items(), key=relatedness)[:6]:
            parts = []
            for (rel, a, b), rec in sorted(recs.items(), key=lambda kv: kv[0][0]):
                arrow = "" if (a, b) == (ka, kb) else "\u2190"    # directional, read the other way
                txt = f"{rel}{arrow} {rec.residual}"
                lever = rec.lever(_relations.DOWN)
                if lever:
                    txt += f" ({lever[0]} drives it down)"
                parts.append(txt)
            out.append(f"  {name(ka)} vs {name(kb)}: " + "; ".join(parts))
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
        # Where a learned move failed to happen. Walls are invisible in the
        # relations (nothing changes), and tu93's cold reader asked for
        # exactly "which presses were blocked". Positions are in the move
        # model's frame, so they are said relative to here.
        obstacles = getattr(agent, "obstacles", None)
        if obstacles is not None and getattr(obstacles, "_blocked", None):
            here = agent.moves.displacement
            here_blocked = sorted(a.name for (pos, a) in obstacles._blocked if pos == here)
            elsewhere: dict[str, int] = {}
            for (pos, a) in obstacles._blocked:
                if pos != here:
                    elsewhere[a.name] = elsewhere.get(a.name, 0) + 1
            parts = []
            if here_blocked:
                parts.append("blocked from here: " + ", ".join(here_blocked))
            if elsewhere:
                parts.append("blocked elsewhere: " + ", ".join(
                    f"{a} at {n} position{'s' if n > 1 else ''}" for a, n in sorted(elsewhere.items())))
            if parts:
                lines.append("  " + "; ".join(parts))
        return ["CONTROL"] + (lines or ["  nothing learned yet"])

    def _relations(self, agent) -> list[str]:
        live = agent.regions.live
        # Drift is a derivative of distance and reads 0 whenever things
        # stop; it is kept in the engine for the probe and left out of the
        # brief, where it only repeats what the distance row already says.
        recent = [(k, t) for k, t in self._last_moved.items()
                  if k[0] not in _relations.EVIDENCE_ONLY and k[0] != "distance_drift"
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
            down = rec.lever(_relations.DOWN)
            cond = rec.conditional_lever(_relations.DOWN) if down is None else None
            levers = (down, rec.lever(_relations.UP), cond)
            groups.setdefault((rel, anchor, levers), []).append((other, rec.residual, t))
        rows = sorted(groups.items(), key=lambda g: -max(m[2] for m in g[1]))
        out = [f"RELATIONS (residual, 0 = holds; moved on this level, newest first)"]
        for (rel, anchor, (down, up, cond)), members in rows[:MAX_RELATIONS]:
            if len(members) == 1:
                other, val, _t = members[0]
                line = f"  {rel}(#{anchor},#{other}) = {val}"
            else:
                vals = ", ".join(f"#{o}={v}" for o, v, _t in members[:6])
                more = f" … +{len(members) - 6}" if len(members) > 6 else ""
                line = f"  {rel}(#{anchor}, each of {vals}{more})"
            if down:
                line += f"   {down[0]} drives it down (+{down[1]:.0%} over other actions)"
            elif cond:
                line += f"   {cond[0]} drives it down when the controlled thing is {cond[1].replace(':', ' on side ')} (+{cond[2]:.0%})"
            if up:
                line += f"   {up[0]} drives it up (+{up[1]:.0%})"
            if not down and not up and not cond:
                line += "   moves under every action alike"
            out.append(line)
        if not recent:
            out.append("  nothing has moved yet")
        return out

    def _falling(self, agent) -> list[str]:
        live = agent.regions.live
        falling = []
        for key, steps in self._down_recent.items():
            if key[0] == "distance_drift":
                continue
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
