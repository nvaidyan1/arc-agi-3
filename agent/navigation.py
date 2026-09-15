"""How to reach a given position using moves we have learned.

**This module is deliberately dumb, and that is a design constraint, not
an accident.** It answers exactly one question:

    Given a displacement graph and a target, what sequence of
    currently-known actions gets there?

It does NOT decide what the target should be, whether routing is
appropriate, or whether reaching the target is worth doing. Those are
policy, and they live in `my_agent.py`. An earlier version reached into
the interest map to choose its own target, which quietly made navigation
the privileged problem-solving paradigm — routing became something the
agent did because it *could*, not because the situation called for it.

That matters because navigation is not the general case. BFS here is a
consequence of having discovered a move map and an obstacle map, not
evidence that the game is a maze. On the 9 of 25 games where no move map
forms, `plan` correctly returns None and the agent does something else.

Measured caution for anyone extending this: *more routing made the score
worse* (mean 0.0511 -> 0.0164) because the score is quadratic in speed
and the targets available to us mark where things happened, not where
the goal is. The bottleneck was never routing capacity. See
docs/history.md, 2026-09-13.
"""
from __future__ import annotations

from collections import deque

from arcengine import GameAction

from constants import ROUTE_MAX_NODES


def chebyshev(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Chessboard distance — matches grid movement better than Euclidean,
    since a diagonal-capable move set shouldn't be penalised for it."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _bfs(
    start: tuple[int, int],
    target: tuple[int, int],
    actions,
    successor,
    is_blocked,
) -> list[GameAction] | None:
    """The search both `plan` and `plan_graph` share. `successor(position,
    action) -> position | None` is the one thing that differs between
    them — a fixed offset per action, or a position-keyed graph lookup —
    and everything else (frontier order, the closest-reachable fallback,
    the obstacle check) is identical, so the two callers cannot drift
    apart in behaviour that has nothing to do with the transition model.
    """
    if not actions or start == target:
        return None

    frontier = deque([start])
    came_from: dict[tuple[int, int], tuple[tuple[int, int], GameAction]] = {}
    visited = {start}
    best, best_dist = start, chebyshev(start, target)
    expanded = 0

    while frontier and expanded < ROUTE_MAX_NODES:
        node = frontier.popleft()
        expanded += 1
        if node == target:
            best = node
            break
        for action in actions:
            nxt = successor(node, action)
            if nxt is None or nxt in visited or is_blocked(node, action):
                continue
            visited.add(nxt)
            came_from[nxt] = (node, action)
            frontier.append(nxt)
            dist = chebyshev(nxt, target)
            if dist < best_dist:
                best, best_dist = nxt, dist

    if best == start:
        return None  # nothing reachable got any closer

    path: list[GameAction] = []
    node = best
    while node in came_from:
        node, action = came_from[node]
        path.append(action)
    path.reverse()
    return path


def plan(
    start: tuple[int, int],
    target: tuple[int, int],
    moves: dict[GameAction, tuple[int, int]],
    is_blocked,
) -> list[GameAction] | None:
    """Actions from `start` toward `target`, or None if there's no route.

    All coordinates are in *displacement space* — relative to wherever
    the current attempt began. Converting an absolute board pixel into
    this space is `MoveModel.to_relative`, and is the caller's job.

    `is_blocked(position, action) -> bool` is injected rather than
    imported so this stays a pure graph search with no knowledge of how
    obstacles were learned.

    Unknown edges are treated as traversable (optimistic): we only know
    an obstacle after bumping into it, and refusing to plan through
    unexplored space would make the router useless early. A plan that
    turns out to be wrong is detected by the caller when the agent's
    actual displacement stops matching the plan's expectation.

    If `target` isn't exactly reachable — commonly because it doesn't sit
    on the move map's stride lattice — this returns the path to the
    closest reachable node found instead of refusing to move. Same
    graceful-degrade stance as every lens: best available answer, or None,
    never a forced one.

    This assumes an action's effect is the SAME OFFSET wherever it is
    taken — the model `MoveModel.learned_moves` holds. H009 found that
    assumption false on cd82 (the controlled thing's motion is a function
    of position AND action, not of the action alone): the offset model
    is optimistic in the same way an unknown obstacle is, and it can be
    confidently wrong rather than merely silent about it. `plan_graph`
    below is the position-keyed alternative for exactly that case.
    """
    def offset_successor(node, action):
        offset = moves.get(action)
        return None if offset is None else (node[0] + offset[0], node[1] + offset[1])

    return _bfs(start, target, moves, offset_successor, is_blocked)


def plan_graph(
    start: tuple[int, int],
    target: tuple[int, int],
    edges: dict[tuple[tuple[int, int], GameAction], tuple[int, int]],
    is_blocked,
) -> list[GameAction] | None:
    """Same contract as `plan`, but the transition model is a graph —
    `(position, action) -> position'` — rather than one offset per
    action. `edges` is `PositionModel.edges` (`agent/control.py`, H010):
    admitted only where the transition has been seen to be deterministic,
    the same standard `MoveModel.learned_moves` holds for an offset.

    The one behavioural difference from `plan`, and it is deliberate: an
    edge with no evidence is simply absent, so BFS cannot extrapolate
    into a position it has never observed a transition from — unlike
    `plan`'s optimistic offset-everywhere assumption. That is the correct
    trade for a model class known to be position-dependent: extrapolating
    an untested offset is exactly the mistake `plan` was making on cd82
    (H009: 0 of 1,244 planned paths honoured at their first step).

    `actions` is sorted by `.value` rather than left as a bare set: a
    `GameAction`'s hash is identity-based and not stable across process
    runs (measured: two invocations of this file gave `hash(ACTION2)`
    two different 64-bit values), so a set of them iterates in an order
    that varies run to run even given byte-identical `edges` — which
    would make `plan_graph` pick a different one of several equally-short
    routes on two replays of the same recorded seed. That is exactly the
    determinism this project's replay harness depends on
    (`docs/history.md` 2026-09-14, "the replay-ablation harness... passes
    reproducibility 5/5"), so it is enforced here rather than left to
    chance.
    """
    actions = sorted({a for (_pos, a) in edges}, key=lambda a: a.value)

    def graph_successor(node, action):
        return edges.get((node, action))

    return _bfs(start, target, actions, graph_successor, is_blocked)


class Route:
    """A plan in progress, and the bookkeeping that keeps it honest.

    The only non-trivial part is drift detection. A queued plan assumes
    each step lands where BFS predicted; if a step hits an obstacle we
    didn't know about, every remaining action was computed for a position
    we never reached. So the plan records where it expects to be, and the
    caller drops it when reality disagrees.
    """

    def __init__(self) -> None:
        self.actions: list[GameAction] = []
        self.target: tuple[int, int] | None = None
        self.expected_position: tuple[int, int] | None = None

    def __bool__(self) -> bool:
        return bool(self.actions)

    def __len__(self) -> int:
        return len(self.actions)

    def set(self, actions: list[GameAction], target: tuple[int, int]) -> None:
        self.actions = actions
        self.target = target

    def has_drifted(self, position: tuple[int, int]) -> bool:
        """Are we somewhere the plan didn't expect?

        False before the first step is taken (nothing to compare yet),
        and correctly False when an interleaved action was *blocked* —
        we're still where the plan left us, so it remains valid.
        """
        return (
            self.expected_position is not None
            and position != self.expected_position
        )

    def next_action(
        self, position: tuple[int, int], moves: dict[GameAction, tuple[int, int]]
    ) -> GameAction:
        """Pop the next action and record where it should land us."""
        action = self.actions.pop(0)
        offset = moves[action]
        self.expected_position = (position[0] + offset[0], position[1] + offset[1])
        return action

    def clear(self) -> None:
        self.actions = []
        self.target = None
        self.expected_position = None
