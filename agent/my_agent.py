"""Your ARC-AGI-3 agent: the entry point, and the only place decisions happen.

`scripts/build_notebook.py` ships this file and its sibling modules into
the Kaggle notebook, so the local dev loop and the submission stay in
lock-step:

    [edit agent/*.py] → [make play-local] → [make submit]

GOVERNING PRINCIPLE — NO SEMANTIC SLOTS WITHOUT EVIDENCE:

    Every perceptual or semantic interpretation must be produced by a
    falsifiable test and may return None. General structure may constrain
    *how* hypotheses are represented and tested, but must not constrain
    *which* entities, goals, roles, or game types exist.

Every detector here is a *lens*: it asks whether some specific
explanation fits, and reports nothing when it doesn't. `detect_translation`
does not assert that games contain moving objects; `stamina_colour` does not
assert that games have resource bars; `acts_locally` stays None until
evidence exists. **None is a first-class outcome** — it is what keeps a
game we have never seen from being force-fit into the shape of the 25 we
have. Game *type* is an output, never an input: the router runs BFS
because a move map and an obstacle map were discovered, not because
anything recognised a maze. See docs/plan.md.

The layers, each in its own module, each answering one question:

    perception   what happened?
    control      what can I make happen?
    constraints  what limits what I can make happen?
    attention    what appears worth investigating?
    navigation   how do I get there with what I've learned?
    my_agent     given all of that, what should I do next?

Synthesis lives HERE and only here. The lower modules report evidence;
none of them decides anything. In particular `navigation` takes a target
rather than choosing one — deciding *whether* to route, and *toward
what*, is policy and belongs in this file.

Contract (enforced by the ARC-AGI-3-Agents framework):
  - Subclass `agents.agent.Agent`.
  - Class must be named `MyAgent` (the notebook's __init__.py registers it).
  - Implement `is_done(frames, latest_frame) -> bool`.
  - Implement `choose_action(frames, latest_frame) -> GameAction`.
"""
from __future__ import annotations

import hashlib
import logging
import os
import random
import sys
from typing import Any

# Make this file's own directory importable, so the sibling layer modules
# resolve in BOTH contexts we run in: locally, where play_local.py loads
# this file standalone via importlib, and on Kaggle, where it is imported
# as `agents.templates.my_agent` inside the framework package. Neither
# plain absolute nor relative imports work in both.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arcengine import FrameData, GameAction, GameState

# When run inside the ARC-AGI-3-Agents framework (locally or on Kaggle)
# the `agents` package is on sys.path, so this import resolves.
from agents.agent import Agent

import belief
import brief
import entities
import hypothesis
import kinds
import navigation
import perception
import relations
import supervisor
from attention import ClickTargeting, InterestMap
from constants import (
    EXPLORATION_EPSILON,
    INTERACTION_WEIGHT,
    INTEREST_LEVEL_UP_WEIGHT,
    INTEREST_RESIDUAL_WEIGHT,
    INTEREST_VANISH_WEIGHT,
    LEVEL_UP_WEIGHT,
    MIN_VANISH_CELLS,
    STAMINA_MIN_SIZE,
    USE_BELIEF_TARGET,
    USE_PER_LEVEL_ROUTE_GATE,
    USE_PROPOSER,
    USE_SHIFT_FALLBACK,
    VANISH_WEIGHT,
)
from constraints import StaminaDetector, ObstacleMap
from control import MoveModel

logger = logging.getLogger(__name__)


class MyAgent(Agent):
    """Explores by favouring actions and regions that visibly change things."""

    # Upper bound on actions per game. The framework's default was 80,
    # but that is a demo guard against infinite loops, NOT a competition
    # rule — no server- or gateway-side cap exists anywhere, and the
    # framework's own Playback class uses 1,000,000. At 80, ls20 (42
    # actions per life) gets under two attempts and completions were pure
    # noise. At 400 both replicate runs produced completions.
    MAX_ACTIONS = 400

    # Set to an int to make a run replayable; None draws a fresh seed and
    # records it. See `seed` below.
    SEED: int | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The previous line here claimed "replays of one game are
        # reproducible" and was false twice over: it mixed in wall-clock
        # time, and `hash()` of a str is salted per process (measured:
        # hash('ls20') returned three different values in three runs). So
        # no run could ever be replayed — including the sp80 run that
        # cleared level 1 in 9 actions, which we cannot go back and watch.
        #
        # Now: the seed is an explicit number, drawn fresh when not given
        # and always *recorded*, so any run can be re-entered later with
        # `--seed`. Per-game offset keeps games exploring independently
        # while one sweep seed reproduces the whole sweep. The offset uses
        # a stable digest rather than hash() for exactly the reason above.
        base = self.SEED if self.SEED is not None else random.SystemRandom().randrange(2**31)
        digest = hashlib.sha256(self.game_id.encode()).digest()
        self.seed = (base + int.from_bytes(digest[:4], "big")) % 2**31
        self.rng_seed_base = base
        random.seed(self.seed)

        # ── Layers ──────────────────────────────────────────────────────
        self.moves = MoveModel()
        self.obstacles = ObstacleMap()
        self.stamina = StaminaDetector()
        self.regions = entities.RegionTracker()
        self._tracked_live: dict = {}
        # Recording only for now: composes the layers below into a
        # role per entity. Nothing reads it to decide yet — naming
        # the consumer before wiring one is the point (three
        # recording-only layers this session moved the score zero).
        self.belief = belief.WorldBelief()
        # Relations between entities, as residuals (agent/relations.py).
        # Recording-only: nothing reads it to decide. It exists in the live
        # agent so the brief a proposer would read can be seen in the recap
        # exactly as it would be sent, not reconstructed offline.
        self.relations = relations.RelationEngine()
        # The text a hypothesis proposer would read (agent/brief.py).
        # Recording-only; composed on demand by the recap.
        self.brief = brief.Briefer()
        # The first consumer (agent/hypothesis.py): a residual to drive to
        # zero with the action that has been seen to drive it, verified
        # over the next few frames. Only acts under USE_PROPOSER.
        self.proposer = hypothesis.Proposer()
        self.hypothesis: hypothesis.Hypothesis | None = None
        self._level_step = 0
        # What has ever mattered, read at level advances and typed by
        # colour (agent/supervisor.py). A property of the game: survives
        # levels and resets, dies with the game.
        self.supervisor = supervisor.BoundarySupervisor()
        # Things that look alike, and what one of them did (agent/kinds.py).
        # The memory is palette-typed and survives levels; the view is
        # recomputed every step.
        self.kinds = kinds.KindMemory()
        self._kinds_now: list = []
        self.interest = InterestMap()
        self.clicks = ClickTargeting()
        self.route = navigation.Route()
        # Why the current route exists. Read only while a route is live
        # (`_maintain_route` returns False before consulting it otherwise),
        # so a value left behind by a cleared plan is never acted on.
        self._route_from_belief = False

        # ── Reward evidence, per action ─────────────────────────────────
        # All persist across RESET: which action makes progress is a
        # property of the game, not of one attempt, and these signals are
        # far too rare to afford forgetting.
        self._action_level_ups: dict[GameAction, int] = {}
        self._action_interactions: dict[GameAction, int] = {}
        self._action_vanishes: dict[GameAction, int] = {}
        self._interaction_sites: dict[tuple[int, int], int] = {}
        # Vanishes on the CURRENT level only. Deliberately a separate
        # counter rather than a reinterpretation of the two above: those
        # feed `_weighted_choice`, where cross-level persistence is
        # load-bearing and must not change. This one feeds only the router
        # gate, where "has anything proven itself on the layout I am
        # standing in" is the question actually being asked — and a
        # level-up never can have, since it is what ended the last one.
        self._level_proven = 0

        # Recording only, and here rather than in `_reset_attempt` for the
        # same reason as everything above: these say what an ACTION does,
        # which is a property of the game and not of one attempt. Both
        # were briefly reset per attempt by mistake, and the cost was
        # exact and measurable — wa30's rotation count read 7 instead of
        # 57, because every death threw the evidence away.
        #
        # `_controlled_by_action`: which colour each action moves.
        # `detect_translation` identifies it and `MoveModel` then discards
        # it, so the agent cannot tell "I moved" from "a second
        # controllable thing moved". Measured: on sp80 ACTION1/3 move
        # colour 12 while ACTION2/4 move colour 9, two independent objects
        # collapsed into one move map.
        #
        # `_action_rotations`: translation was the only rigid motion ever
        # tested for, so an object *turning* under our own actions
        # produced no evidence at all — 57 of 57 such events on wa30.
        # Nothing reads either to decide yet: a rotation does not compose
        # into a position the way an offset does, so the router would need
        # a different representation before it could use one.
        # Actions for which an EXACT lens has ever explained the change.
        # The tolerant fallback is barred from these: mixing an averaged
        # offset into a histogram that already holds exact ones corrupts
        # it. Measured — on ar25 the fallback pushed ACTION1 from a clean
        # (0,3) x20 to (0,-5) x17 / (0,-4) x12, the opposite direction,
        # and the action fell out of the map entirely; g50t lost one too.
        self._exact_actions: set[GameAction] = set()
        self._controlled_by_action: dict[str, int] = {}
        self._action_rotations: dict[GameAction, dict[str, int]] = {}
        # Lifetime totals. `_action_tries` and `_action_changes` reset every
        # attempt on purpose (contingency is re-measured per life), but a
        # panel reading "tried 0" after two hundred presses looks broken
        # rather than principled, so the running total is kept alongside.
        self._action_tries_total: dict[GameAction, int] = {}
        self._action_changes_total: dict[GameAction, int] = {}

        # ── Change-type census (recording only) ─────────────────────────
        # Deliberately not wired into action selection. Adding a signal
        # and changing decision logic in one pass makes a regression
        # impossible to attribute — that lesson cost a full debugging
        # cycle (docs/history.md, 2026-09-13).
        self._recolour_counts: dict[tuple[int, int], int] = {}
        self._cardinality_counts: dict[int, int] = {}
        self._change_steps = 0
        self._translation_steps = 0
        self._recolour_steps = 0
        self._cardinality_steps = 0

        # The canvas for this level, captured once from the first frame
        # rather than re-derived per frame. Per-frame argmax flips when
        # content outgrows the canvas — measured on dc22, 37.4% of steps.
        self._background: int | None = None
        self._map_level = 0
        self._pending_vanish = 0
        self._reset_attempt()

    # ── Attempt / level lifecycle ───────────────────────────────────────

    def _reset_attempt(self) -> None:
        """A fresh attempt: forget per-attempt state, keep game knowledge."""
        # Recording only; `_select` overwrites it every step. Initialised
        # here so anything reading it before the first decision (a test, a
        # viewer attaching mid-run) sees an empty dict rather than raising.
        self._decision: dict[str, Any] = {}
        # Recording only, same reason: `_learn_from` computes "thing I
        # affect" every step already, to update a scalar reward counter
        # and bump the interest map, then discards the positions. Keeping
        # them is what lets a debugging view show *where* that evidence
        # is rather than just its count. Cleared here so a fresh attempt
        # doesn't show the previous attempt's residual for one stale step.
        self._last_residual_cells: list[tuple[int, int]] = []
        # Positional, so it dies with the attempt: a footprint is where an
        # object was on *this* attempt's board, and the level restarts the
        # object at its origin. The action->colour mapping it is derived
        # from is a game property and lives in __init__ instead.
        self._controlled_cells: dict[int, list[tuple[int, int]]] = {}
        self._action_tries: dict[GameAction, int] = {}
        self._action_changes: dict[GameAction, int] = {}
        self._last_action: GameAction | None = None
        self._last_click: tuple[int, int] | None = None
        self.moves.reset_position()
        self.clicks.reset_attempt()
        self.route.clear()
        # Tell the tracker, so the next frame is matched against the
        # attempt's starting layout and identities survive the teleport.
        self.regions.expect_home()
        # The frames before a death were not the run-up to an advance, and
        # the step across a reset is neither a vanishing nor a stamina change.
        if hasattr(self, "supervisor"):
            self.supervisor.clear_window()
        if hasattr(self, "kinds"):
            self.kinds.new_attempt()

    def _reset_level(self) -> None:
        """A new level is a new layout, so position-keyed knowledge dies.

        What survives is deliberately everything keyed by *action* rather
        than by *place*: the move map (ACTION1 moves me up) and the
        `acts_locally` signature describe the controller, which the game
        does not rebuild between levels. Cell coordinates describe the
        layout, which it does.

        Two structures used to be missed here, both coordinate-keyed, so
        the agent entered a new layout holding a map of a vanished one:
        the per-cell click memory (wiped on the next death, so it
        corrupted the first attempt of every level) and
        `_interaction_sites`, which was never cleared at all for the whole
        run. `clicks.reset_attempt()` is the right call rather than a
        fresh ClickTargeting, because it keeps `acts_locally`.
        """
        self.obstacles.clear()
        self.interest.clear()
        self.regions.clear()
        self.belief.clear()
        self.relations.clear()
        self.brief.clear()
        self.proposer.clear()
        self.hypothesis = None
        self._level_step = 0
        self.kinds.new_level()
        self._kinds_now = []
        # `_observe_frame` has already run this step and holds the new
        # layout's regions under ids the tracker has just forgotten; left
        # in place they would seed beliefs for ids that never recur
        # (measured: 13 phantom beliefs on cd82 at the level-2 boundary).
        self._tracked_live = {}
        self.moves.reset_position()
        self.route.clear()
        self.clicks.reset_attempt()
        self._interaction_sites.clear()
        self._background = None
        # Nothing has proven itself on a layout nobody has played yet.
        self._level_proven = 0

    @property
    def name(self) -> str:
        return f"{super().name}.{self.MAX_ACTIONS}"

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        # Stop once we win. Don't stop on GAME_OVER — we RESET and retry,
        # which is free: the engine's level_reset() preserves progress.
        return latest_frame.state is GameState.WIN

    # ── The decision ────────────────────────────────────────────────────

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            self._reset_attempt()
            # Recording only: name this path so a viewer shows "reset"
            # rather than an absent decision, which reads like a bug.
            self._decision = {"tier": "reset", "candidates": []}
            return GameAction.RESET

        candidates = self._legal_actions(latest_frame)
        self._observe_frame(latest_frame)

        if latest_frame.levels_completed != self._map_level:
            self._map_level = latest_frame.levels_completed
            # Read the boundary before the level's records are cleared:
            # which residuals were falling into this advance, and under
            # what. The last action taken is the winning move.
            self.supervisor.on_advance(
                self.relations, self._colour_of,
                self._last_action.name if self._last_action is not None else None)
            self._reset_level()

        if len(frames) >= 2 and self._last_action is not None:
            self._learn_from(frames[-2], latest_frame)

        return self._select(latest_frame, candidates)

    def _legal_actions(self, latest_frame: FrameData) -> list[GameAction]:
        """Only ever consider what the game currently reports as legal.

        ls20 exposes only ACTION1-4, so trying ACTION5-7 there is pure
        wasted budget. (Gibson's affordances: the actions an environment
        offers in a given state.)
        """
        if latest_frame.available_actions:
            return [
                a
                for a in (GameAction.from_id(i) for i in latest_frame.available_actions)
                if a is not GameAction.RESET
            ]
        return [a for a in GameAction if a is not GameAction.RESET]

    def _observe_frame(self, latest_frame: FrameData) -> None:
        """Per-frame bookkeeping that doesn't depend on the previous frame."""
        counts = perception.colour_counts(latest_frame)
        if self._background is None and counts:
            self._background = max(counts, key=counts.get)

        # Stamina is measured per tracked REGION, not per colour. The
        # aggregate was hiding a perfect signal: cd82's bar drains 64
        # cells to zero, but 100 static cells elsewhere share its colour,
        # so the whole-board total only falls 164 -> 100 = 61% and the
        # "must actually empty" test rejected it. Per region it reads 0%.
        # Only regions that could BE a meter are tracked, which also keeps
        # the per-step cost bounded.
        # Merge a region wholly enclosed by another before tracking: a
        # bordered object is one thing, and same-colour grouping alone
        # splits it into frame and fill.
        regions = perception.merge_enclosed(
            perception.connected_regions(latest_frame, min_size=1),
            background=self._background,
        )
        regions = [(c, cells) for c, cells in regions
                   if len(cells) >= STAMINA_MIN_SIZE]
        # Tell the tracker what we just did, so it can recognise the thing
        # that went where our own move map says it would. This is the only
        # matching evidence that scales with a game's stride rather than
        # with a constant of ours (cd82 hops 11-15 cells; proximity is 8).
        expected = (
            self.moves.learned_moves.get(self._last_action)
            if self._last_action is not None else None
        )
        tracked = self.regions.update(regions, expected_offset=expected)
        self._tracked_live = tracked
        self.stamina.update(
            {rid: len(cells) for rid, (_c, cells) in tracked.items()},
            self.game_id,
            colours={rid: colour for rid, (colour, _s) in tracked.items()},
            cells={rid: cells for rid, (_c, cells) in tracked.items()},
        )

    def _learn_from(
        self, prev_frame: FrameData, latest_frame: FrameData
    ) -> None:
        """Credit or blame the action we took, across every layer.

        NOTE: we track our own last action rather than reading
        `latest_frame.action_input` — the framework's
        `_convert_raw_frame_data()` never populates that field.
        """
        action = self._last_action
        assert action is not None
        self.interest.decay()

        changed = perception.diff_cells(prev_frame, latest_frame)
        origin = self.moves.displacement  # before any move updates it
        self._action_tries[action] = self._action_tries.get(action, 0) + 1
        self._action_tries_total[action] = self._action_tries_total.get(action, 0) + 1

        moved = None
        if changed:
            self._action_changes[action] = self._action_changes.get(action, 0) + 1
            self._action_changes_total[action] = (
                self._action_changes_total.get(action, 0) + 1)
            self.clicks.observe_change(changed)
            moved = perception.detect_translation(prev_frame, latest_frame)
            if moved is not None:
                _colour, size, offset, pre_anchor = moved
                self.moves.observe_translation(
                    action, offset, size, pre_anchor, self.game_id
                )
                # Recording only (see __init__). One extra `lost_and_gained`
                # pass, and only on steps where a translation was already
                # confirmed, rather than widening `detect_translation`'s
                # tested return contract. `gained` is where the shape moved
                # *to*; cells it already occupied don't appear in either
                # set, so this is the newly-occupied region, not the full
                # silhouette.
                self._exact_actions.add(action)
                _lost, _gained = perception.lost_and_gained(prev_frame, latest_frame)
                if _colour in _gained:
                    self._controlled_cells[_colour] = sorted(_gained[_colour])
                    self._controlled_by_action[action.name] = _colour
            if (moved is None and USE_SHIFT_FALLBACK
                    and action not in self._exact_actions):
                # EXPERIMENT (docs/plan.md, "In flight"). Nothing exact
                # explained this change; ask the weaker question — did a
                # comparable mass of one colour simply go somewhere? This
                # is what gives cd82 a move map, and it feeds the SAME
                # `observe_translation`, so everything downstream treats
                # it as an ordinary offset and the majority bar still has
                # to be cleared before it is believed.
                shifted = perception.detect_shift(
                    prev_frame, latest_frame, self._background
                )
                if shifted is not None:
                    moved = shifted
                    _colour, size, offset, pre_anchor = shifted
                    self.moves.observe_translation(
                        action, offset, size, pre_anchor, self.game_id
                    )
                    self._controlled_by_action[action.name] = _colour

            if moved is None:
                # Only asked once translation has already declined, because
                # a centrally-symmetric shape sliding sideways satisfies
                # both descriptions and the offset is the one that composes
                # into a position. Recording only (see __init__).
                turned = perception.detect_rotation(prev_frame, latest_frame)
                if turned is not None:
                    _colour, _n, kind, _pivot = turned
                    per = self._action_rotations.setdefault(action, {})
                    per[kind] = per.get(kind, 0) + 1
                    self._controlled_cells[_colour] = sorted(
                        perception.lost_and_gained(prev_frame, latest_frame)[1]
                        .get(_colour, set())
                    )
                    self._controlled_by_action[action.name] = _colour

        # "Thing I affect": what our own movement and the meter don't
        # explain. Falls back to what this action is *known* to do when
        # the strict whole-diff test fails, otherwise our own movement
        # goes unexplained and every step looks like an interaction.
        observed_offset = (
            moved[2] if moved else self.moves.learned_moves.get(action)
        )
        residual = perception.residual_cells(
            prev_frame, latest_frame, changed, observed_offset,
            self.stamina.stamina_colour, self.stamina.stamina_cells,
        )
        self._last_residual_cells = list(residual)  # recording only, see __init__
        # Relate this step to every entity: which ones changed under which
        # action. The roles fall out of the contrast between actions, so
        # this needs the action name and nothing else.
        # What is on screen NOW — never the tracker's memory. Passing the
        # memory here had beliefs forming about ghosts, and the router
        # aiming at them (docs/history.md, 2026-09-14).
        self.belief.update(self._tracked_live, action.name, changed)
        self.relations.update(self.regions._tracked, self.regions.live, action.name,
                              skip=self._canvas_ids())
        self.supervisor.observe(self.relations.snapshot())
        self._kinds_now = kinds.compute_kinds(self.relations, self.belief, self.regions.live,
                                              background=self._background)
        self.kinds.record(self._kinds_now, self.regions.live, action.name,
                          self.stamina.stamina_fraction)
        self.brief.record(self, action.name, getattr(action, "action_data", None))
        self._level_step += 1
        # Verify the live hypothesis against what its action just did to
        # its residual. Only steps taken under it count; an epsilon step
        # in between is not its evidence.
        h = self.hypothesis
        if h is not None and self._decision.get("tier") == "hypothesis":
            rec = self.relations.record(h.key)
            status = h.observe(rec.residual if rec is not None else None)
            if status != hypothesis.LIVE:
                self.proposer.close(h, self._level_step)
                self.hypothesis = None

        # Two consumers, two different gates. As a *reward* the residual
        # is only meaningful once we know our own effect — with no move
        # map there is no self to subtract, so it would collapse to
        # "anything changed" and double-count frame-change. As a *map* it
        # double-counts nothing, so it runs unconditionally. That
        # distinction is why the copy/match games get an interest map at
        # all: gated, the residual read 0.0% of steps on ft09/sb26/cd82/tn36.
        if residual and observed_offset is not None:
            self._action_interactions[action] = (
                self._action_interactions.get(action, 0) + 1
            )
            self._interaction_sites[origin] = self._interaction_sites.get(origin, 0) + 1
        if residual:
            self.interest.bump(residual, INTEREST_RESIDUAL_WEIGHT)

        self._census_and_vanish(prev_frame, latest_frame, changed, residual, moved)

        if self._pending_vanish:
            self._action_vanishes[action] = self._action_vanishes.get(action, 0) + 1
            self._level_proven += 1

        # Environment layer: an action with a known effect that failed to
        # produce it.
        expected = self.moves.learned_moves.get(action)
        if expected is not None:
            self.obstacles.observe(
                origin,
                action,
                perception.expected_move_occurred(prev_frame, latest_frame, expected),
            )

        # The signal that actually matches what's scored.
        if latest_frame.levels_completed > prev_frame.levels_completed:
            self._action_level_ups[action] = self._action_level_ups.get(action, 0) + 1
            # Deliberately NOT counted in `_level_proven`. A level-up ends
            # the layout it happened on, and by the time we get here
            # `_reset_level` has already run for the new one, so the credit
            # would land on a level nobody has played yet and latch its
            # router shut on step one. Measured on cd82 seed 8 before this
            # guard: gate latched at the first step of level 2, every time.
            logger.info(
                "LEVEL UP on %s via %s -> levels_completed=%d",
                self.game_id, action.name, latest_frame.levels_completed,
            )
            # Falling back to the raw diff covers a level-up reached by
            # pure movement, where residual is empty because the whole
            # change is explained as self.
            self.interest.bump(residual or changed, INTEREST_LEVEL_UP_WEIGHT)

        if action is GameAction.ACTION6 and self._last_click is not None:
            self.clicks.observe_click(self._last_click, changed)

    def _census_and_vanish(
        self,
        prev_frame: FrameData,
        latest_frame: FrameData,
        changed: list[tuple[int, int]],
        residual: list[tuple[int, int]],
        moved,
    ) -> None:
        """Classify the change, and derive the sub-goal signal from it."""
        self._pending_vanish = 0
        if not changed:
            return

        self._change_steps += 1
        if moved is not None:
            self._translation_steps += 1

        # `changed - residual` is exactly what another lens already
        # accounted for (our movement, and the meter ticking), so
        # subtracting it stops two lenses claiming the same pixels and
        # keeps the meter's steady drain out of the cardinality count.
        classified = perception.classify_change(
            prev_frame, latest_frame, set(changed) - set(residual), self._background
        )
        if classified is None:
            return
        recolours, cardinality, lost_cells = classified

        if recolours:
            self._recolour_steps += 1
            for key, count in recolours.items():
                self._recolour_counts[key] = self._recolour_counts.get(key, 0) + count
        if cardinality:
            self._cardinality_steps += 1
            for colour, delta in cardinality.items():
                self._cardinality_counts[colour] = (
                    self._cardinality_counts.get(colour, 0) + delta
                )

        # Sub-goal signal: a colour losing more than a whole object's
        # worth to the canvas in one step. Below the floor it's churn
        # (ka59 produces 244 one-cell drops). Our own shape sliding over
        # something can't be mistaken for a deletion — that is
        # content-over-content, which lands in `recolours` — and our
        # vacated trail is at most `controlled_size` cells, which is
        # exactly why the floor is sized against it.
        floor = max(self.moves.controlled_size, MIN_VANISH_CELLS)
        vanished = sum(
            -delta for delta in cardinality.values() if delta < 0 and -delta > floor
        )
        if vanished:
            self._pending_vanish = vanished
            # Bump where content was actually destroyed, not across every
            # residual cell — the old histogram signal had no positions
            # to offer, so it had to smear the credit.
            self.interest.bump(sorted(lost_cells), INTEREST_VANISH_WEIGHT)

    def _kind_bonus(self, key: tuple) -> int:
        """1 when a distance hypothesis aims the CONTROL thing at a member
        of a kind whose members have vanished with stamina rising — the
        snake reading, as a weight the proposer adds to its ranking."""
        rel, a, b = key
        if rel != "distance" or not isinstance(a, int):
            return 0
        control = {x.region_id for x in self.belief.by_role(belief.CONTROL)}
        target = b if a in control and b not in control else a if b in control and a not in control else None
        if target is None:
            return 0
        for k in self._kinds_now:
            if any(target in m.key for m in k.members):
                return self.kinds.gain_prior(k.palette)
        return 0

    def _colour_of(self, rid: int) -> int | None:
        entry = self.regions._tracked.get(rid)
        return entry[0] if entry is not None else None

    def _canvas_ids(self) -> set[int]:
        """The largest live region of the background colour, if any.

        Only the largest: the background colour can also fill a bounded
        area that IS a thing (cd82's template interior is colour 5, the
        canvas colour, at 156 cells). Everything but the biggest keeps its
        place in the relations.
        """
        best, size = None, 0
        for rid in self.regions.live:
            colour, cells = self.regions._tracked[rid]
            if colour == self._background and len(cells) > size:
                best, size = rid, len(cells)
        return {best} if best is not None else set()

    # ── Policy ──────────────────────────────────────────────────────────

    def _select(
        self, latest_frame: FrameData, candidates: list[GameAction]
    ) -> GameAction:
        """Decide what to do, given everything the layers have reported."""
        moves = self.moves.learned_moves
        position = self.moves.displacement

        # Don't walk into something we've learned resists us here. Only
        # drop blocked actions while alternatives remain, so we never end
        # up with nothing to pick.
        unblocked = [a for a in candidates if not self.obstacles.is_blocked(position, a)]
        n_blocked = len(candidates) - len(unblocked)
        if unblocked:
            candidates = unblocked

        novel = [
            a
            for a in candidates
            if a in moves
            and (position[0] + moves[a][0], position[1] + moves[a][1])
            not in self.moves.visited
        ]

        strong_route = self._maintain_route(candidates, moves, position)

        # Which branch fired is recorded on every path. Without it an
        # epsilon coin-flip and a deliberate weighted choice both surface
        # as a bare "ACTION3", so a suspicious run cannot be diagnosed
        # even with a perfect viewer: you cannot tell whether the agent
        # decided or flipped a coin. Recording only; nothing reads it to
        # make a decision, and no RNG call is added, so the action stream
        # is byte-identical to before.
        self._decision = {
            "tier": None,
            "candidates": [a.name for a in candidates],
            "position": position,
            "n_blocked": n_blocked,
            "all_blocked": not unblocked,
        }

        if random.random() < EXPLORATION_EPSILON:
            self._decision["tier"] = "epsilon"
            action = random.choice(candidates)
        elif USE_PROPOSER and (chosen := self._hypothesis_action(candidates)) is not None:
            self._decision["tier"] = "hypothesis"
            return chosen
        elif strong_route:
            self._decision["tier"] = "route_strong"
            return self._take_route(position, moves, well_evidenced=True)
        elif novel:
            self._decision["tier"] = "frontier"
            self._decision["novel"] = [a.name for a in novel]
            action = random.choice(novel)
            action.reasoning = (
                f"frontier: {action.name} moves {moves[action]} to unvisited "
                f"displacement from {position}"
            )
            self._last_click = None
            self._last_action = action
            return action
        elif self.route:
            self._decision["tier"] = "route_weak"
            return self._take_route(position, moves, well_evidenced=False)
        else:
            self._decision["tier"] = "weighted"
            action = self._weighted_choice(candidates)

        return self._finish(action, latest_frame)

    def _hypothesis_action(self, candidates) -> GameAction | None:
        """The live hypothesis's action if it is legal, else propose one.

        The proposer reads the relation records the brief is built from
        and returns None when no live pair has a legal lever — the common
        case early in a level, and on games where nothing has been shown
        to move anything — in which case the tiers below decide as before.
        """
        legal = {a.name for a in candidates}
        h = self.hypothesis
        if h is not None and h.action not in legal:
            self.proposer.close(h, self._level_step)
            h = self.hypothesis = None
        if h is None:
            context = {b.region_id for b in self.belief.by_role(belief.CONTEXT)}
            h = self.proposer.propose(
                self.relations, self.regions.live, legal, self._level_step,
                exclude=context, prior=self.supervisor.prior,
                typer=lambda key: supervisor.type_of(key, self._colour_of),
                won=self.supervisor.won, bonus=self._kind_bonus)
            self.hypothesis = h
        if h is None:
            return None
        # A distance hypothesis is a destination, and the router already
        # knows how to reach one: plan from the controlled thing to the
        # other entity and take the first step, verifying on the residual
        # as before. One lever repeated cannot turn a corner (tu93: 17,
        # 17, 17); a path can. Falls back to the lever when no path.
        action = None
        routed = ""
        if h.key[0] == "distance" and self.moves.learned_moves and isinstance(h.key[1], int):
            action, routed = self._route_for(h, candidates)
        if action is None:
            action = next(a for a in candidates if a.name == h.action)
        action.reasoning = f"hypothesis: {h.describe()}{routed}"
        self._last_click = None
        self._last_action = action
        return action

    def _route_for(self, h, candidates):
        """First step of a path that brings the controlled thing to the
        other member of a distance hypothesis, or (None, "")."""
        control = {b.region_id for b in self.belief.by_role(belief.CONTROL)}
        _rel, a, b = h.key
        if a in control and b not in control:
            target_id = b
        elif b in control and a not in control:
            target_id = a
        else:
            return None, ""
        pixel = self.belief._beliefs[target_id].centroid if target_id in self.belief._beliefs else None
        target = self.moves.to_relative(pixel) if pixel is not None else None
        if target is None:
            return None, ""
        moves = {act: off for act, off in self.moves.learned_moves.items() if act in candidates}
        path = navigation.plan(self.moves.displacement, target, moves, self.obstacles.is_blocked)
        if not path:
            return None, ""
        return path[0], f"; routed toward #{target_id} ({len(path)} steps)"

    def _maintain_route(self, candidates, moves, position) -> bool:
        """Keep the route honest, and report whether it deserves priority.

        Returns True when the route should outrank covering new ground —
        i.e. its target carries at least a sub-goal's worth of
        accumulated salience rather than a single residual bump. That
        threshold is one of the existing weights rather than a new tuned
        constant: "something meaningful happened there", not "something
        changed there".
        """
        if self.route and (
            self.route.actions[0] not in candidates
            or self.route.actions[0] not in moves
            or self.route.has_drifted(position)
        ):
            # Three ways a plan goes stale. The next action may no longer
            # be legal; a prior step may not have landed where the plan
            # assumed (an obstacle we didn't know about), leaving the rest
            # computed for positions we never reached; or the action may
            # have dropped out of the move map entirely. That last one is
            # easy to miss: `learned_moves` is recomputed every step, and
            # an action whose offsets stop meeting the majority threshold
            # silently disappears from it, so a plan built when it was
            # known would raise KeyError on the offset lookup. Seen live
            # on sc25 and wa30.
            self.route.clear()

        # A level-up or vanish means some action has *proven* itself, and
        # that evidence must win the weighted branch every time. Without
        # this, an unconditional router preempted the only channel that
        # had ever produced a completion — measured as two full 25-game
        # sweeps scoring 0.0 on every game. Vanishes stay in this gate:
        # removing them raised routing and *lowered* the score, because
        # scoring is quadratic in speed and routing aims at where things
        # happened, not where the goal is (docs/history.md, 2026-09-13).
        #
        # Scoped per level under USE_PER_LEVEL_ROUTE_GATE: see
        # `constants.USE_PER_LEVEL_ROUTE_GATE` for why, and note that
        # `_weighted_choice` still reads the cross-level counters
        # untouched, so the channel the original regression ran through
        # is unchanged either way.
        proven = (
            self._level_proven > 0
            if USE_PER_LEVEL_ROUTE_GATE
            else bool(self._action_level_ups or self._action_vanishes)
        )
        if proven:
            self.route.clear()
            return False

        if not self.route:
            target_pixel, well_evidenced = self._route_target()
            target = (
                self.moves.to_relative(target_pixel)
                if target_pixel is not None
                else None
            )
            if target is not None:
                path = navigation.plan(
                    self.moves.displacement, target, moves, self.obstacles.is_blocked
                )
                if path:
                    self.route.set(path, target_pixel)
                    self._route_from_belief = well_evidenced

        if not self.route:
            return False
        # A belief target carries its own warrant — an action has been
        # *shown* to act on that entity — so it does not also have to
        # clear the interest map's salience bar, which is a statement
        # about a different and weaker kind of evidence entirely.
        return self._route_from_belief or self.interest.peak >= INTEREST_VANISH_WEIGHT

    def _route_target(self) -> tuple[tuple[int, int] | None, bool]:
        """Where to route, and whether the reason is belief or salience.

        Target *selection* is policy, so it lives here rather than in
        `navigation` (which must never pick its own destination) or in
        `belief` (which reports evidence and draws no conclusions). This
        method is the whole of the policy: it reads `by_role`, applies
        three exclusions, and returns a pixel.

        Belief first when enabled, interest as the fallback, so a game
        where no role has been earned behaves exactly as before.
        """
        if USE_BELIEF_TARGET:
            pixel = self._belief_target()
            if pixel is not None:
                return pixel, True
        return next(iter(self.interest.top_cells(1)), None), False

    def _belief_target(self) -> tuple[int, int] | None:
        """The strongest thing some action has been shown to act upon.

        The destination is an AFFECT entity: one whose changes track a
        specific action against its own baseline. Not CONTEXT (that is a
        meter or an animation — cd82's stamina bar is CONTEXT precisely so
        that it stops contaminating everything, and travelling to a HUD
        element is the clearest possible category error), not ENVIRONMENT
        (it never changes, so there is nothing to go and do), and not
        UNASSIGNED (no evidence is not a target).

        Three exclusions, each for a reason that would otherwise produce a
        meaningless route:

          * **The canvas.** The background is a tracked region like any
            other and is usually the largest thing on the board; its
            centroid is the middle of the screen and means nothing.
          * **Whatever we are.** Routing the controlled object to itself
            is a no-op at best. CONTROL entities are excluded, and so is
            anything sitting where we already are.
          * **Entities with no position.** A belief whose last known cells
            are empty has nowhere to be gone to.

        Returns None — a real answer — whenever no entity survives, which
        is the common case early and on the 9 of 25 games where no move
        map forms at all.
        """
        origin = self.moves.origin_anchor()
        if origin is None:
            return None  # no controlled thing, so no displacement space to plan in

        here = self.moves.anchor
        best, best_lift = None, 0.0
        for candidate in self.belief.by_role(belief.AFFECT):
            if candidate.colour == self._background:
                continue
            pixel = candidate.centroid
            if pixel is None or pixel == here:
                continue
            _action, lift = candidate.selectivity
            if lift > best_lift:
                best, best_lift = pixel, lift
        return best

    def _take_route(self, position, moves, well_evidenced: bool) -> GameAction:
        action = self.route.next_action(position, moves)
        if self._route_from_belief:
            noun, qualifier = "entity", "acted on by some action"
        elif well_evidenced:
            noun = "interest cell"
            qualifier = f"well-evidenced (weight {self.interest.peak:.1f})"
        else:
            noun, qualifier = "interest cell", "best available"
        action.reasoning = (
            f"router: {action.name} to {qualifier} {noun} "
            f"{self.route.target}, {len(self.route)} steps left"
        )
        self._last_click = None
        self._last_action = action
        return action

    def _weighted_choice(self, candidates: list[GameAction]) -> GameAction:
        """Laplace-smoothed value per action, combining every reward tier.

        Frame change is dense (fires most steps, keeps the policy
        learning while nothing is scored); interactions and vanishes sit
        between that and the real thing; level-ups are what the
        competition actually scores and dominate whenever they fire.
        """
        weights = [
            (
                self._action_changes.get(a, 0)
                + INTERACTION_WEIGHT * self._action_interactions.get(a, 0)
                + VANISH_WEIGHT * self._action_vanishes.get(a, 0)
                + LEVEL_UP_WEIGHT * self._action_level_ups.get(a, 0)
                + 1
            )
            / (self._action_tries.get(a, 0) + 2)
            for a in candidates
        ]
        # Recording only — the per-action weights are the whole content of
        # this decision, and without them the choice is unreadable after
        # the fact.
        self._decision["weights"] = {a.name: round(w, 4)
                                     for a, w in zip(candidates, weights)}
        return random.choices(candidates, weights=weights, k=1)[0]

    def _finish(self, action: GameAction, latest_frame: FrameData) -> GameAction:
        """Attach the payload and reasoning, and remember what we chose."""
        if action.is_complex():
            grid = latest_frame.frame[-1] if latest_frame.frame else []
            x, y, why = self.clicks.pick(grid, self.interest)
            action.set_data({"x": x, "y": y})
            action.reasoning = {
                "why": why,
                "acts_locally": self.clicks.acts_locally,
                "interest_cells": len(self.interest),
            }
            self._last_click = (x, y)
        else:
            stamina = self.stamina.stamina_fraction
            action.reasoning = (
                f"exploration: {action.name} "
                f"tried={self._action_tries.get(action, 0)} "
                f"changed={self._action_changes.get(action, 0)} "
                f"level_ups={self._action_level_ups.get(action, 0)}"
                + (f" stamina={stamina:.2f}" if stamina is not None else "")
            )
            self._last_click = None
        self._last_action = action
        return action
