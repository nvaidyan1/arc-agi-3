# ARC-AGI-3 Agent — How It Works

This describes what the agent **actually does**, in enough detail that you
should not need to open the code, and honestly enough that you can tell us
where it is wrong. Jargon is defined where it first appears.

For the design rules we hold ourselves to, see `plan.md` ("Governing
principle"). For the experiments behind each decision — including the ones
that failed — see `history.md`. For the external review that reshaped the
second half of the design, see `council_2026-09-14_belief.md`. This
document is limited to what exists and what it has been measured to do; a
section near the end lists what does not exist yet, separately, so the two
never blur.

---

## 1. The problem

The agent plays video games it has never seen before.

Each game gives it a **64×64 grid of coloured cells** (16 possible colours)
and accepts **8 actions**: `RESET`, five simple buttons (`ACTION1`–`5`,
`ACTION7`), and one "click" action (`ACTION6`) that takes an x,y coordinate
on the grid. That is all. No labels, no instructions, no description of
what the game is or how to win. Games have several levels; the hidden
evaluation set is unseen; evaluation runs offline on Kaggle with no network
access.

**Scoring shapes everything.** For each level completed:

```
score = (human_baseline_actions / actions_you_took)² × 100
```

zero if the level is not completed, and a game's score is the
**level-index-weighted** average over all its levels — so a first level is
worth 1/28 of a seven-level game, and depth dominates speed. Human
baselines for a first level are around 7–60 actions; we take ~100–400.

---

## 2. What the agent does, in one paragraph

It plays by experiment. Each turn it compares the new screen against the
previous one and tries to explain the difference in a vocabulary that
assumes nothing about games: *did a shape move, turn, grow, shrink, appear,
vanish?* It groups pixels into regions, gives regions identities that
survive movement, death and reset, and accumulates evidence about each one:
which actions change it, and how. From those it reads **relational roles**
— *the thing my buttons move, the thing one button acts on, the thing that
changes whatever I press, the thing that never changes* — and **relations
between things**, each expressed as a **residual**: a number that is 0 when
the relation holds and larger the further it is from holding. The whole
state is serialised as a short text, **the brief**, which is what a
hypothesis proposer reads. A proposer (today an enumerator; an LLM is the
next step) bets that some residual is worth driving to zero with the action
that has been seen to move it, spends a small budget of actions testing the
bet, and is falsified when the residual does not move. Level advances are
the one certified signal, and what was falling into an advance is
remembered — by colour, not by identity — as *what has mattered*. Nothing
is hard-coded per game, and every layer may answer "I don't know".

---

## 3. Vocabulary

| Term | What it means here |
|---|---|
| **Lens** | A test that asks "does *this* explanation fit what just happened?" and answers with the explanation or with **nothing**. Returning nothing is a normal, correct outcome. |
| **Frame** | One screenshot after an action has settled (games send animation sub-frames; we read the last). |
| **Region / entity** | A contiguous same-colour blob, given a stable id by the tracker so it can be followed over time. |
| **Live / ghost** | Whether a tracked entity is on screen now. The tracker remembers what has gone (so a bar that empties is recognised when it refills); beliefs and relations act only on what is live. |
| **Canvas** | The level's background colour, the largest region of it. A surface, not a thing: excluded as a relatum. |
| **Move map** | Learned table of *which button produces which displacement*, e.g. `ACTION1 → (0, −5)`. Built from evidence, never assumed. |
| **Role** | A relational judgement about an entity from the contrast between actions: `CONTROL` (my actions determine what happens to it), `AFFECT` (one action acts on it), `CONTEXT` (it changes whatever I press — a timer, a bar), `ENVIRONMENT` (never changes), `UNASSIGNED` (not enough evidence). Never `PLAYER`, `GOAL`, `ENEMY`. |
| **Group** | Two or more regions that persistently sit inside one another or trade cells. A *view* recomputed each step, never a stored object: a partition has no falsifier. |
| **Kind** | Two or more units with the same palette and part count (exact when outlines match too). Same stuff; the members may have different roles. |
| **Residual** | A relation between two things as a number: 0 means it holds, larger means further from holding, `None` means undecidable. Unknown is `None`, never `False`. |
| **Lever** | The action that moves a residual *more than the other actions do*. A residual every action moves alike (a timer draining) has movers but no lever. |
| **Brief** | The state as ~45 lines of text — what a proposer would be sent. |
| **Hypothesis** | "Drive this residual to 0 with this action", with a budget of actions, verified each step and falsified when the residual rises twice or stalls. |
| **Supervisor** | Reads each level advance: which residuals were falling into it under a lever. Remembers them by colour as *what has mattered*, and the winning move. |
| **Router** | A pathfinder over the move map and known walls. Given a destination, never picks one. |
| **Sawtooth / stamina** | An on-screen quantity that drains during an attempt and refills on reset. The game's per-attempt resource. |

---

## 4. A worked example: cd82

A bucket orbits a two-colour block; painting the block from different
angles makes it match a two-colour template in the corner; swatches along
the top choose the paint colour. Nothing below was told any of that.

1. **Regions and identity.** Same-colour flood fill gives ~15 regions.
   The tracker follows each by overlap; when the bucket hops 11–15 cells it
   is followed by *explained motion* — it landed where the move map said
   the action would put it. On death, the tracker is told a RESET happened
   and matches the restored layout against the attempt's starting layout,
   so identities survive teleports. Solitary objects are never folded into
   the canvas (a bug found on a second game, sp80, whose controller had
   been invisible for exactly that reason).
2. **Control.** All four d-pad buttons move the bucket at equal rates, so
   no button "stands out" — the older rate contrast called it weather.
   Control is read as *determinism*: each button always does one fixed,
   different thing to it. `#8, #9: CONTROL — ACTION3 −x, ACTION4 +x…`
3. **Groups.** Frame+fill of the bucket, the template's frame + interior +
   two colour parts, and the block's two halves (which trade cells under
   the paint action) each read as one thing — from persistence of two
   relations, with no object ever stored.
4. **Relations.** `palette_missing(block → template) = 0` — everything the
   block is made of, the template has. `part_size_diff(template content,
   block) = 30` — their colour proportions differ by 30 cells, and it
   falls under `ACTION5`. `shape_diff` will read 0 exactly when the
   arrangement matches; it has no gradient, deliberately — comparing two
   grids cell-by-cell after aligning them *is* template-matching, encoded,
   and we refuse it.
5. **Kinds.** `kind {0,15}×2: {template content} static · {block} changes
   under my actions — drifted from the static one: part_size_diff 30`.
   Same stuff, one never changes, one I change, and by how much.
6. **Brief.** All of the above, plus available actions, blocked moves, what
   is undecidable, and the last eight steps as events, in ~45 lines.
7. **Hypotheses.** The enumerator bets on the residual with the clearest
   lever and tests it for up to 8 actions. On cd82 it bets on movement
   (the bucket approaching things) and never on painting, because the
   paint action has rarely been pressed and so has never *earned* a lever
   — the current known failure (§8).
8. **Supervisor.** When a level is cleared, the residuals that were falling
   into it under a lever are recorded by colour; on the next level, the
   proposer ranks those first. On ar25 this produced this project's first
   level-2 clears.

On a click-only game such as `vc33`, steps 2, 7 and 8 mostly do not fire:
no move map, no CONTROL, no lever, no hypothesis — and the brief says so.
**Nothing breaks, and nothing is forced.**

---

## 5. The layers

Fourteen modules, each answering one question. Names describe *roles*,
never game contents.

| module | question it answers |
|---|---|
| `perception.py` | What happened between two frames? Regions, diffs, translation / shift / rotation lenses, recolour vs create/destroy, enclosure merging (never into the canvas). |
| `entities.py` | Which region is the same region as last frame? Overlap → explained motion → proximity → identical shape within 3 frames; reset told, matched against the home layout; live vs remembered. |
| `control.py` | What can I make happen? The move map (3+ sightings, 60% majority — refuses genuinely ambiguous buttons), displacement and anchor. |
| `constraints.py` | What limits me? Walls (position, action); the stamina sawtooth (must refill — a drain that never refills is progress, not budget). |
| `attention.py` | Where is change concentrated? The interest map and click targeting with habituation and click-locality. |
| `belief.py` | What is each entity *to me*? Per-action change tallies in a cell vocabulary; roles by contrast and by determinism; hysteresis so roles do not flicker; UNASSIGNED first-class. |
| `relations.py` | How do things stand to each other? Residuals over all live pairs (`palette_diff`, `shape_diff`, `containment`, `distance`, `distance_drift`, `count_diff`, `cell_exchange`); the grouping view and frame content; group residuals (`palette_missing`, `part_size_diff`); per-action movement tallies and levers. |
| `kinds.py` | Which things are the same stuff? Kinds over units; role asymmetry and drift within a kind; what vanished, and how stamina moved when it did. |
| `brief.py` | What would I tell a proposer? The serialisation: THINGS, GROUPS, KINDS, CONTROL, RELATIONS, FALLING, OPEN, RECENT, HYPOTHESIS, MATTERED. |
| `hypothesis.py` | What is worth betting on? The enumerating proposer and the verification loop: budget, held / falsified / expired, cooldown. |
| `supervisor.py` | What has ever mattered? The level-boundary diff: residuals falling into an advance under a lever, typed by colour; winning moves. |
| `navigation.py` | How do I get there? Bounded BFS over the move map with walls as removed edges; destination given, never chosen. |
| `my_agent.py` | Given all that, what do I do next? The only place evidence becomes a decision: epsilon → hypothesis (flagged) → route → frontier → weighted track record. |
| `constants.py` | Every tunable, grouped by layer, each with the measurement that set it and the flags (`ARC_PROPOSER`, `ARC_BELIEF_TARGET`, `ARC_ROUTE_PER_LEVEL`, `ARC_SHIFT_FALLBACK`). |

Two boundaries are load-bearing: **perception returns evidence, never
decisions** (no `is_goal()`), and **navigation takes a destination, never
picks one**. Policy lives in `my_agent.py` alone.

### Directory

```
agent/
  perception.py    lenses over frame pairs: regions, diffs, motion, recolour, enclosure
  entities.py      RegionTracker — stable ids across hops, deaths and resets; live vs ghost
  control.py       MoveModel — which button moves the controlled thing by how much; position
  constraints.py   ObstacleMap (walls) and StaminaDetector (the sawtooth resource)
  attention.py     InterestMap and ClickTargeting — where change concentrates, where to click
  belief.py        Belief per entity: per-action evidence, kinds of change, relational roles
  relations.py     RelationEngine — residuals between things, groups, group residuals, levers
  kinds.py         kinds view: same palette and parts; role asymmetry, drift, vanish transfer
  brief.py         Briefer — the ~45-line text a hypothesis proposer reads
  hypothesis.py    Hypothesis + enumerating Proposer — bets on a residual, verified, budgeted
  supervisor.py    BoundarySupervisor — what fell into each level advance, typed by colour
  navigation.py    plan() and Route — BFS over the move map, drift-checked as it executes
  my_agent.py      MyAgent — the layer stack wired together and the one decision per step
  constants.py     tunables and experiment flags, each with the measurement behind it
scripts/
  play_local.py         run the agent on the real games locally; per-step JSONL with frames
  recap.py + template   step through one run in the browser: frame, masks, belief, the brief
  probe_relations.py    the relation gate: do residuals fall into level advances under a lever
  probe_brief_recall.py is the goal coordinate in the brief before an advance
  sweep_summary.py      durable per-sweep record (scores, levels, completion indices, git sha)
  analyse_sweeps.py     compare recorded sweeps by configuration
  build_notebook.py     splice agent/*.py into the Kaggle submission notebook
  verify_packaging.py   prove the notebook's module layout imports in a clean interpreter
tests/                  193 unit tests; the refusals are tested as carefully as the successes
```

---

## 6. What it achieves

Measured, not estimated. Every comparison below is n = 30 sweeps of all 25
public games per arm, seed-paired, medians, permutation test, with the
games a change *cannot touch* checked first.

| configuration | median score | mean | level-2 clears (of 30 sweeps) |
|---|---|---|---|
| default agent (proposer off) | 0.0145 | 0.038 | 0 |
| proposer on (`ARC_PROPOSER=1`) | 0.0443 | 0.058 | **2** (ar25) |

The proposer's gain reads p = 0.065 on the pre-specified whole-sweep test:
promising, not yet promoted. The 17 games it cannot touch score
identically in both arms. Of the 8 it touches, five gain (sp80, m0r0 —
which had never reached level 1 in any base sweep — ar25, cn04, sk48) and
three lose (cd82, ls20, tr87). The gainers are games whose level is
cleared by *reaching* something; cd82's is cleared by a paint action the
movement hypotheses now crowd out.

Representation quality is measured separately from score, because a
representation nothing consumes cannot move the score (§7):

| test | result |
|---|---|
| Residuals falling into a level advance under a lever (11 recorded advances) | 7 / 11 |
| Goal coordinate present in the brief 3–8 steps before an advance | 7 / 11 advances; 0 "in the engine but crowded out of the text"; the 4 misses are cd82's paint advances |
| Cold readers (a model that saw only the brief) stating a checkable goal | 3 / 5 games |
| Default action stream after the identity/control/perception changes | byte-identical to the previous baseline on 30 seed-paired sweeps |

A sweep of 25 games costs ~75 seconds, which is the only reason any of
these numbers exist.

---

## 7. Things we learned the hard way

Each is in the code as a comment, because each is counter-intuitive enough
to be re-broken by a well-meaning change.

- **Routing toward change made the score worse.** Where change *happened*
  is not where the *goal* is; walking to it spends actions on a destination
  with no established link to winning, and the score is quadratic in
  actions. Every early high score came from stumbling onto the goal.
- **A signal nothing acts on cannot help.** Three recording-only layers
  each moved the score by exactly nothing, as predicted. The first thing to
  consume the brief moved the median 3×.
- **Read the brief as a proposer would, before building the proposer.**
  Doing so found the canvas swamping every relation, a draining timer
  posing as a lever, and the canvas itself earning CONTROL — none visible
  in the panels that had displayed the same data.
- **The solved frame is never observed.** The winning action produces the
  *next level's* first frame, so "the goal residual collapses to 0" is
  unmeasurable by construction; what can be measured is *falling, under a
  lever*.
- **Derive the vocabulary from a second game.** The relation set was first
  written from one game and was that game read backwards. Checking on a
  second game found not a vocabulary flaw but a perception bug — solitary
  objects were being absorbed into the canvas — that had hidden an entire
  game's controller.
- **Never edit the agent while a measurement runs.** Sweeps import from
  disk per process; one A/B was contaminated this way and is recorded as
  such.

---

## 8. What is *not* built, or not yet shown to work

- **An action that has never moved a residual can never become a lever, so
  the enumerator never proposes it.** cd82's paint action is only ever
  pressed by the random bandit, which the proposer crowds out. This is the
  known regression and the next thing to fix.
- **No LLM proposer yet.** The interface is designed (brief in,
  `Hypothesis` out) and the offline path is verified — Kaggle Models
  attached to the notebook, served by vLLM from offline wheels, called as a
  local OpenAI-compatible server — but nothing has been wired.
- **Arrangement has no gradient.** `shape_diff` is 0 or undecidable, by
  the rule against aligning grids. Proportion (`part_size_diff`) has one.
- **Kind transfer is unexercised live.** "One of these vanished and stamina
  rose, so expect the same of its lookalikes" holds on unit tests; no
  recorded game has produced the event.
- **No temporal or conditional structure** beyond eight steps of events and
  per-action levers ("paint only lands when adjacent" is not expressible).
- **Click-driven hypotheses.** A lever that is `ACTION6` carries no
  coordinate, so no hypothesis is ever proposed through a click.
- **No cross-game learning,** by choice: the evaluation philosophy is
  explicit, and `m0r0`'s ambiguous buttons are direct evidence that an
  "ACTION1 usually means left" prior would mislead.

---

## 9. Next in process

Fix exploration inside the proposer so that a never-tried action can earn a
lever (and the supervisor's winning moves are tried on the next level), then
wire the LLM proposer behind the same `Hypothesis` interface, tested locally
against a small model on the offline path Kaggle actually uses. Each step is
gated by the same instrument as everything above: which games does it
touch, does the affected game recover, and does the whole-sweep median move
at n = 30.

---

## 10. The one rule

> **No semantic slots without evidence.** Every interpretation must come
> from a test that can return nothing. Structure may constrain *how* we
> represent and test ideas; it must not constrain *which* entities, goals,
> or game types can exist.

Translation detection does not claim games contain moving objects — it asks
whether this change was a translation. Roles are correlations with my own
actions, never labels. Groups and kinds are views recomputed from evidence,
never stored objects. Residuals are counts, never alignments. The supervisor
weights, never asserts, and forgets everything at the end of the game.
**Reporting nothing is a first-class answer.**

The point is not to be excellent at the 25 games we can see. It is to
behave sensibly on the twenty-sixth.
