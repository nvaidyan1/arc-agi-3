# ARC-AGI-3 Agent — How It Works

This describes what the agent **actually does**, in enough detail that you
should not need to open the code. Jargon is defined where it first appears.

For the design rules we hold ourselves to, see `plan.md` ("Governing
principle"). For the experiments behind each decision — including the ones
that failed — see `history.md`. This document is deliberately limited to
what exists and what it achieves; a section at the end lists what doesn't
exist yet, separately, so the two never blur.

---

## 1. The problem

The agent plays video games it has never seen before.

Each game gives it a **64×64 grid of coloured cells** (16 possible
colours) and accepts **8 actions**: `RESET`, five simple buttons
(`ACTION1`–`5`, `ACTION7`), and one "click" action (`ACTION6`) that takes
an x,y coordinate on the grid. That's all. No labels, no instructions, no
description of what the game is or how to win.

The agent isn't told whether it's controlling a character, painting a
picture, matching shapes, or something with no name. It has to work that
out — or, more precisely, it has to behave sensibly *without ever
necessarily working it out*.

**Scoring is brutal and it shapes everything.** For each level completed:

```
score = (human_baseline_actions / actions_you_took)² × 100
```

and **zero** if the level isn't completed. Note the square. Human
baselines for the first level are around 7 actions (vc33), 22 (ls20), 39
(sp80), 59 (dc22). Completing sp80's first level in 100 actions scores
15.2; in 400 actions it scores 0.95. **A 4× difference in speed is a 16×
difference in score.** Finishing is not enough; finishing fast is the
entire game.

---

## 2. What the agent does, in one paragraph

It plays by experiment. Each turn it compares the new screen against the
previous one, and tries to explain the difference: *did a shape move? did
something change colour? did something appear or vanish?* It accumulates
those explanations into small models — which button moves things and by
how much, where movement is blocked, which colour is counting down like a
timer, which parts of the screen have been worth touching. Then it picks
an action: usually the one whose track record is best, sometimes a
deliberate random one, sometimes a move into territory it hasn't visited,
and occasionally a planned multi-step walk toward a location it has
reason to care about. Nothing is hard-coded per game.

---

## 3. Vocabulary

These terms recur throughout the codebase and the rest of this document.

| Term | What it means here |
|---|---|
| **Lens** | A test that asks "does *this* explanation fit what just happened?" and answers either with the explanation or with **nothing**. Returning nothing is a normal, correct outcome. |
| **Frame** | One screenshot: the 64×64 grid after an action has settled. |
| **Diff** | The set of cells whose colour changed between two frames. |
| **Translation** | A shape moving: the exact set of cells that lost a colour is the same set that gained it, shifted by one consistent offset. |
| **Move map** | The learned table of *which button produces which movement*, e.g. `ACTION1 → up 5 pixels`. Built from evidence, never assumed. |
| **Displacement** | Where the controlled shape is **relative to where this attempt started** — not an absolute screen position. |
| **Anchor** | Where the controlled shape is in **absolute screen pixels**. Needed because some things are tracked relative and some absolute. |
| **Residual** | The part of a change that is *not* explained by our own movement or by the timer ticking. In other words: something we affected that isn't us. |
| **Interest map** | A per-pixel score of "something notable happened here". Decays over time. **Not** a map of goals — see §5.4. |
| **Router** | A pathfinder. Given the move map and the obstacle map, it works out the button sequence that walks from where we are to a target square. It does **not** decide where to go; it's given a destination. |
| **Frontier** | Squares reachable in one move that this attempt hasn't visited yet. Moving to one is "cover new ground". |
| **Meter / budget** | An on-screen bar that **depletes and refills** — a life or step counter. Tells you how long you have left. |
| **Drain** | Something that depletes and **never refills** — e.g. a progress bar filling in. Looks similar, means the opposite. See §5.3. |
| **Habituation** | Ignoring a spot that has been clicked before and did nothing. |
| **Level-up** | The game reporting that a level was completed. The only signal that matches what's scored. |

---

## 4. A worked example

Concretely, playing `ls20`:

1. **Steps 1–10.** The agent presses buttons semi-randomly. After each
   press it compares frames. Several times, a 4-cell shape is in a
   different place — the *translation* lens fires.
2. **~Step 12.** `ACTION1` has now produced the offset `(0, -5)` three
   times with no disagreement, so it enters the **move map**: *ACTION1
   moves something up by 5 pixels*. Eventually all four directions are
   learned — on ls20 this comes out perfectly, 122 observations with zero
   contradictions. The 5-pixel stride also reveals the game's logical
   cell size, which nobody told us.
3. **Ongoing.** The agent now prefers moves that land somewhere it hasn't
   been (the **frontier**), rather than wandering at random.
4. **When a move fails.** It presses `ACTION4` expecting to move right;
   the shape doesn't move. That `(position, ACTION4)` pair is recorded as
   **blocked**. It won't waste budget there again. This cut wasted moves
   on ls20 from 63% to 21%.
5. **Meanwhile.** A colour is quietly tracked falling from 84 cells to 0
   over an attempt, then jumping back to 84. That sawtooth identifies it
   as a **budget**: 84 units at 2 per action ≈ 42 actions per life.
6. **When something vanishes.** A block of cells turns into background.
   That's recorded as sub-goal progress, and those exact pixels gain
   **interest**.
7. **Choosing.** Most turns it picks the action with the best track
   record; 25% of turns it picks at random on purpose; when the frontier
   has somewhere new, it goes there.

On a game with no movement at all — say `ft09`, where clicking paints
cells — steps 2–4 simply never happen. The move map stays empty, the
router never runs, blocked-move detection never fires. The agent falls
back to click targeting. **Nothing breaks, and nothing is forced.**

---

## 5. The layers

Seven modules, each answering one question. The names describe *roles*,
not game contents — there is no `objects.py` or `goals.py`, because those
words would assume things a game might not contain.

### 5.1 `perception.py` — *what happened?*

Stateless tests over a pair of frames. Given the same two frames they
always return the same answer, which is why this layer carries most of
the unit tests.

- **`diff_cells`** — which cells changed. (Subtlety: a frame arrives as
  several animation sub-frames within one action; we read the *settled*
  last one. Reading the mid-animation frame drops move-map consistency
  from 43–64% to 21–29% on an animated game.)
- **`detect_translation`** — did one shape move, and by how much? Returns
  the colour, size, offset, and the pre-move anchor. Fires on **14 of 25
  games**; silent on the rest, which is correct rather than a gap.
- **`expected_move_occurred`** — a weaker check: did *anything* shift by
  the offset we expected? Used to tell "blocked" from "moved", because
  the strict test misses ~4% of real moves and each miss would be logged
  as a phantom wall.
- **`classify_change`** — the change types translation doesn't cover.
  Measured across 533 transitions: translation is only **31%** of what
  games do, **53%** is recolouring in place, **16%** is things appearing
  or disappearing. The test uses the **canvas** (the level's starting
  background colour): a change *touching* the canvas creates or destroys
  something; a change *between two non-background colours* just relabels
  something already there.
- **`residual_cells`** — what changed that our own movement and the timer
  don't explain.

**This layer reports evidence and never interprets it.** There is no
`is_goal()` here, by rule.

### 5.2 `control.py` — *what can I make happen?*

`MoveModel` holds the move map. An action enters it only after **3+
sightings of the same offset and a 60% majority**. This threshold earns
its keep: on `m0r0`, `ACTION1` moves one way 15 times and the other way
13 times, and the model correctly **refuses to learn it**. A confident
wrong answer there would poison the router, the obstacle map, and the
frontier all at once.

It also tracks where the controlled shape is, in both relative
(displacement) and absolute (anchor) terms, and converts between them.
The absolute position is re-derived from what's actually on screen each
time rather than accumulated, so it can't quietly drift.

### 5.3 `constraints.py` — *what limits me?*

Two different limits, both discovered:

- **`ObstacleMap`** — where a known move fails. Keyed by *position and
  action*, which is also its own sanity check: a real wall blocks in
  specific places, while a broken move map would fail everywhere.
- **`StaminaDetector`** — finds an on-screen budget by its **sawtooth**: it
  must fall during an attempt *and* return to the same starting value
  afterwards. Fires on ~9 of 25 games.

**The refill requirement is the important part.** `dc22` has a colour
that declines steadily all game — because the player is filling the board
in. That's a **drain** (how much of the level is done), not a **budget**
(how much is left before dying). They look almost identical and imply
*opposite* behaviour: a budget near zero means hurry, a drain near zero
means you're nearly finished. Reading dc22's progress bar as a timer
would have the agent panicking exactly when it's winning.

### 5.4 `attention.py` — *what's worth investigating?*

`InterestMap` scores pixels where something notable happened — a residual
change, something vanishing, a level completing — weighted by how good
the evidence was, and decaying so stale spots fade.

**Interest is not the same as a goal, and the distinction is expensive.**
An entry means *"change happened here that I didn't cause"*. It does
**not** mean *"the win condition is here"*. We measured what happens when
those get conflated (§7).

We checked this map was worth building before building it: these spots
**cluster tightly** rather than scattering — on the games we score, 8–29
cells out of 4096 carry half the weight. Had they been evenly spread, a
map of them would have carried no information.

`ClickTargeting` picks where to click, in order of evidence quality:
learned interest → recently changed *and* distinct → recently changed →
anything non-background → random. It skips spots that were clicked and
did nothing (**habituation**), and prefers never-clicked spots — earlier
measurement found ~half of all clicks were exact repeats, pure waste.

It also learns whether clicking affects *the cell you touched* or
*something elsewhere*. On `ft09` a click changes the cell under the
cursor (and exactly 38 cells each time); on `vc33` it never does and
changes 1–2 cells somewhere else. That matters: when clicks act at a
distance, the cells that changed are the *effect*, so aiming at them is a
category error. Respecting this cut repeat waste from ~50% to 1–3%.

### 5.5 `navigation.py` — *how do I get there?*

A pathfinder (breadth-first search) over the move map, treating known
blocked moves as walls. Given a target square, it returns the button
sequence to reach it.

**It is deliberately dumb, and that's a constraint.** It takes a
destination; it never picks one. An earlier version reached into the
interest map to choose its own target, which quietly made navigation the
privileged strategy — the agent routed because it *could*, not because
the situation called for it.

If the target isn't exactly reachable (common: the target may not sit on
the move map's 5-pixel grid), it returns the route to the closest
reachable square rather than refusing. If no move map exists, it returns
nothing and the agent does something else.

Plans are checked as they execute: if a step doesn't land where predicted
— an unknown obstacle — the rest of the plan was computed for a position
we never reached, so it's discarded.

### 5.6 `my_agent.py` — *what should I do next?*

The only place evidence from the other layers becomes a decision. Each
turn it picks exactly one of:

1. **Random** (25% of the time) — deliberately, so under-tried actions
   keep getting sampled.
2. **Route** — follow a plan, but only toward a target with real
   accumulated evidence behind it, and only while no action has already
   proven itself.
3. **Frontier** — move somewhere this attempt hasn't been.
4. **Best track record** — a weighted draw where each action's score
   combines: *did it change anything* (common), *did it affect something
   other than us* (×3), *did it make something vanish* (×8), *did it
   complete a level* (×20). Level-ups dominate whenever they've ever
   happened.

### 5.7 `constants.py`

Every tunable, grouped by layer, each with a comment saying what
measurement set it. Several carry explicit warnings about relationships
that would break if tuned in isolation.

---

## 6. What it achieves

Honest numbers, on the 25 games available locally, at 400 actions each:

| | |
|---|---|
| Games where a move map forms | 16 of 25 |
| Games where a budget meter is found | ~9 of 25 |
| Aggregate score per sweep | mean ~0.027, best ~0.15 |
| Sweeps producing any completion | 13 of 14 |

**For scale: one level of sp80 completed in our typical ~400 actions is
worth about 0.95 out of a per-level maximum of 100.** The agent reliably
completes a first level on a handful of games and is roughly 10–50×
slower than a human at it. Because scoring is quadratic, that gap is
almost the whole distance between where we are and a competitive score.

---

## 7. Two things we learned the hard way

Both are in the code as comments now, because both are counter-intuitive
enough to be re-broken by a well-meaning future change.

**Routing more made the score worse.** Across three configurations the
relationship was monotonic: more routing produced *more reliable*
completion (5/9 → 7/8 sweeps scoring non-zero) and a *lower* score (mean
0.0511 → 0.0164). This isn't a contradiction — it's the quadratic. The
interest map marks where things *happened*, not where the *goal* is, so
walking deliberately to a hotspot spends real actions on a destination
with no established link to winning. Every high score came from
stumbling onto the goal early. **Directed movement toward a non-goal is
worse than undirected search that might get lucky.**

**A signal nothing acts on cannot help.** We measurably improved the
sub-goal detector — and the score didn't move, because nothing downstream
could use it. Improving perception on top of a policy that can't consume
it is a reliable way to spend effort for nothing.

---

## 8. What is *not* built

Listed separately so nothing above is mistaken for a plan, and nothing
here is mistaken for a feature.

- **No goal detection.** The agent has no mechanism for identifying a win
  condition. This is the single biggest gap, and §7 explains why it's the
  one that matters.
- **No hypothesis ledger.** No explicit tracked beliefs with confidences,
  no experiments chosen to discriminate between competing explanations.
- **No causal graph.** Contingency is learned per action, not as a
  network of cause and effect.
- **No rotation, reflection, scaling, splitting or merging detection.**
  Only translation, recolouring, and appearance/disappearance — which
  covered 99% of measured transitions, so there's no evidence these are
  needed yet.
- **No probabilistic confidence.** Thresholds are hard cutoffs (3
  sightings, 60% majority) rather than posteriors.
- **No cross-game learning.** Nothing carries between games, by choice —
  and `m0r0`'s ambiguous control mapping is direct evidence that a
  "ACTION1 usually means left" prior would actively mislead.
- **The budget meter is detected but unused.** Measured cost per action
  is flat, so knowing time is short doesn't change which action is best.
  It would need a goal to be useful.

---

## 9. The one rule

> **No semantic slots without evidence.** Every interpretation must come
> from a test that can return nothing. Structure may constrain *how* we
> represent and test ideas; it must not constrain *which* entities,
> goals, or game types can exist.

Every component follows this. Translation detection doesn't claim games
contain moving objects — it asks whether this particular change was a
translation. The meter detector doesn't claim games have timers — it
tests for a sawtooth. Click locality stays undecided until there's
evidence. **Reporting nothing is a first-class answer.**

The practical consequence: game *type* is an output, never an input.
There is no `if maze: use_pathfinding()`. Pathfinding runs because a move
map and an obstacle map happened to be discovered — which, on a game with
no movement, they never are, and the agent simply does something else.

The point isn't to be excellent at the 25 games we can see. It's to
behave sensibly on the twenty-sixth.
