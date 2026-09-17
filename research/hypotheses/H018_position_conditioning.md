# H018: per-entity position as a conditioning variable

Status: **CLEARS THE CONSUMER LINK ON 2 OF 3 GAMES, SMALL (2026-09-17)** — the first variable in this branch to move `predictor.rollout` at all: k=1 no-meter **+0.028 sc25, +0.017 g50t, +0.001 sk48**, while the Z1 and LC controls stay at +0.000. Much attenuated from the offline holdout and decaying with horizon. Gameplay untested. Prior: PASSES DISCOVERY + HOLDOUT + TARGET FIREWALL WITHOUT FRAGMENTING (2026-09-17) — the first candidate in this branch to do so. Raw per-entity position lifts held-out instrumental accuracy **+0.035 / +0.106 / +0.062** (sk48 / sc25 / g50t) and **+0.075 / +0.257 / +0.090 on CONTROL entities**, with coverage holding at **0.97-1.00** at every resolution. The shape is the predicted one: monotonic in resolution, saturating, and 2-3x larger on CONTROL — the locus H017 diagnosed. **Still owes the two links that killed `last_changer`: the real predictor consumer and gameplay.** Nothing built, nothing wired.
Research question: RQ2 (predictive world modelling)
Date opened: 2026-09-17
Origin: the CONTROL/displacement audit. Per-entity position already exists —
every entity carries a bbox each step and ids persist 99.8-100% — but the
predictor cannot see it: `by_action_given` is keyed by (entity, action) and
`MoveModel.displacement` is a single **colour-keyed** quantity from
`perception.detect_translation`, which never touches entity ids. Rather than
build per-entity position bookkeeping on that observation, test first whether
position would survive the chain at all.

## Claim

    baseline   P(effect | entity, action)
    +posB      P(effect | entity, action, bbox centroid bucketed to B cells)

## Why failure was the expectation

Cardinality. `n_reset` (~400 values) would have fragmented `by_action_given`
to singletons; the E1 conjunction collapsed to 25% coverage — best accuracy
where it applied, almost never applying. Raw position is high-cardinality in
principle and looked like the same trap.

## Result

25 traces per game, 20 discovery / 5 held-out, instrumental target (k=1
per-entity effect), meter-like entities excluded, >= 4 observations to admit
a key, falling back to baseline where the conditioned key is unseen.

| game | arm | keys | coverage | acc | lift | **CONTROL lift** |
|---|---|---|---|---|---|---|
| sk48 | baseline | 110 | 0.995 | 0.840 | — | — |
| sk48 | +pos8 | 221 | 0.979 | 0.858 | +0.019 | +0.037 |
| sk48 | **+pos1** | 234 | **0.972** | 0.874 | **+0.035** | **+0.075** |
| sc25 | baseline | 60 | 1.000 | 0.887 | — | — |
| sc25 | +pos8 | 110 | 1.000 | 0.910 | +0.023 | +0.047 |
| sc25 | **+pos1** | 313 | **1.000** | **0.992** | **+0.106** | **+0.257** |
| g50t | baseline | 60 | 1.000 | 0.805 | — | — |
| g50t | +pos8 | 179 | 0.994 | 0.837 | +0.032 | +0.047 |
| g50t | **+pos1** | 231 | **0.986** | 0.867 | **+0.062** | **+0.090** |

**Coverage never collapses** — 0.97-1.00 even at raw position. That is the
opposite of every previous candidate.

The shape is the one the diagnosis predicted:
1. **monotonic in resolution** (32 -> 16 -> 8 -> 4 -> 1 rises on all three);
2. **saturating** — sk48 and g50t plateau at B=4 (key counts stop growing:
   236 -> 234, 231 -> 231), sc25 keeps gaining to B=1;
3. **concentrated on CONTROL**, 2-3x the overall lift on every game — exactly
   the locus H017 measured as 3.6-5.1x harder to predict.

## Why it does not fragment, and what that means

Entities occupy a **small discrete set of positions**, not a continuous
coordinate: median 2 distinct raw positions per entity (CONTROL median 5-6,
max 13-29). So (entity, action, position) has ~2-5 cells per (entity,
action) — hence the ~2-3x key growth and the intact coverage.

That is **H009's cd82 finding generalised**: cd82's controlled thing has 8
orbit positions and its motion is a deterministic function of
`(position, action)`, which is why `PositionModel` worked. H018 says the same
structure holds *per entity* on games nobody built it for — and that the
effect table, keyed by (entity, action), is missing the dimension that makes
the effect determinate.

## What this has NOT passed

- **The real consumer.** The scoring here is a majority-vote table, not
  `predictor.effect_table` + `predictor.rollout`. `last_changer` passed
  discovery, holdout and the meter control and then scored **+0.000** on the
  real consumer. This owes exactly that test.
- **Gameplay.** Untouched, and the standing rule applies: a candidate that
  predicts better has still not been shown to act better.

## Where to draw the line, answered empirically

B=4 captures most of the available lift on sk48 and g50t; sc25 wants raw. So
the resolution question has a measured answer rather than a guessed one, and
the cost is bounded — 200-300 keys against a 60-110 baseline.

## Status log

- 2026-09-17 opened and run, `scripts/h018_position_conditioning.py`. Passes
  discovery, holdout and the target firewall without fragmenting; consumer
  and gameplay links not yet run. No agent change.

## The consumer link (2026-09-17)

`scripts/h018_consumer.py` — `predictor.rollout` as the agent runs it, H006's
admit rule, meter-excluded, with Z1 and `last_changer` as controls known to
score +0.000.

| game (no-meter) | k=1 | k=3 | k=10 |
|---|---|---|---|
| sc25 | base 0.876, **POS +0.028** | 0.767, **+0.022** | 0.678, +0.008 |
| g50t | base 0.785, **POS +0.017** | 0.554, **+0.012** | 0.245, +0.001 |
| sk48 | base 0.872, POS +0.001 | 0.765, -0.000 | 0.654, -0.000 |
| controls, all games | Z1 +0.000, LC +0.000 | +0.000 | +0.000 |

**POS is the first variable in this branch to move the real consumer at
all.** It clears the bar `last_changer` failed. But the result is small and
honest about it:

- **Two of three games.** sk48 gains essentially nothing.
- **Attenuated** versus the offline holdout (+0.106 -> +0.028 on sc25). Two
  causes, both mine: the consumer applies H006's *function* admit rule where
  the offline test used majority vote, and the rollout **holds position at
  step i** instead of forecasting it forward.
- **Decays with horizon** (+0.028 -> +0.008 on sc25), which follows directly
  from holding position constant. `PositionModel` could forecast position
  across the rollout — the obvious next lever, and additional machinery.

**Admission is not the limiter.** Under the `(action, position) -> effect`
function rule, sk48 admits **42%** of entity-traces and gains nothing, while
g50t admits **8%** and gains the most. So position genuinely carries
information on sc25/g50t and genuinely does not on sk48; the rule is not
what is suppressing it.

### A key mismatch found and fixed, with a caveat it raises

The inherited harness (`h013_consumer.py`, from `latent_rollout.py`) keys its
admit rule on the **variable alone** — asking "is this entity's effect a
function of position?", which is stronger and different from H018's claim
about `(entity, action, position)`. The effect table is per-action, so
per-action is the faithful shape; fixed here. Under the variable-only key POS
scored +0.000 on every game, so the fix is the difference between a null and
a result.

The caveat: that means the earlier `last_changer` consumer test also ran
under the stronger keying. **Re-run here with the corrected per-action key,
`last_changer` is still +0.000 on every game and horizon** — its rejection
stands, and so does Z1's.

### What remains

Gameplay. The standing rule is unchanged: predicting better is not acting
better, and nothing here has been wired into the agent.

## The persistence fork: TRUE FUTURE POSITION PRESERVES AND GROWS THE GAIN

`POS*` is the oracle arm — the same learned table, queried with the **true
position at each rollout step** instead of holding step i's. A→B is the value
of knowing current position; B→C the value of maintaining it through the
rollout.

| game (no-meter) | k=1 | k=3 | k=10 |
|---|---|---|---|
| sc25 POS | +0.028 | +0.022 | +0.008 |
| sc25 **POS\*** | +0.028 | **+0.055** | **+0.075** |
| g50t POS | +0.017 | +0.012 | +0.001 |
| g50t **POS\*** | +0.017 | **+0.037** | **+0.039** |
| sk48 POS | +0.001 | -0.000 | -0.000 |
| sk48 POS\* | +0.001 | +0.002 | +0.002 |

**With true future position the gain GROWS with horizon instead of decaying**
— sc25 +0.028 → +0.075 (2.7x), g50t +0.017 → +0.039 (2.3x). The k=3/k=10
attenuation was **entirely the constant-position assumption**, not position
ceasing to matter. Position is useful throughout the trajectory.

So the fork resolves to **yes: forward position prediction has a concrete
justification**, and `PositionModel` already exists to provide it. That is one
specific piece of machinery earned by a measurement, not a ladder rung.

**sk48 stays null even with the oracle** (+0.002 at k=10). It is not a
data or rollout artefact: sk48's mechanic simply does not depend on position.
That is the argument against installing POS globally — **state variables
should be admitted per game/mechanic**, which is what the per-entity,
per-action admit rule already does.

### POS almost never breaks a correct prediction

| game | FIXED | BROKE | ratio |
|---|---|---|---|
| sc25 | 2,587 | 7 | 369:1 |
| g50t | 795 | 3 | 265:1 |
| sk48 | 152 | 8 | 19:1 |

A strong safety property: the conditioning adds information without
displacing what the tallies already had right.

### What POS actually predicts — and it is NOT only geometry

| game | corrected class | n | share |
|---|---|---|---|
| **g50t** | `unchanged -> moved` | 446 | |
| | `moved -> unchanged` | 328 | |
| | **movement-related total** | **774 / 795** | **97%** |
| **sc25** | **`unchanged -> grew`** | **914** | **35%** |
| | `grew -> unchanged` | 349 | |
| | `shrank -> unchanged` | 238 | |
| | **size-transformation total** | **~1,501 / 2,587** | **~58%** |
| | movement-related (`moved -> unchanged`, `moved -> turned`) | 604 | 23% |

**g50t is almost purely geometric** — expected movement versus
blocked/edge movement, 97% of its corrections. That matches the prior
exactly.

**sc25 is not.** Its single largest corrected class is `unchanged -> grew`,
and ~58% of its gain is **size transformations**, against 23% movement. So
position is not merely a collision-constraint variable there: it conditions
*whether an entity grows or shrinks*, which implies position-dependent
interactions rather than geometry alone. That is the more interesting of the
two outcomes the prior allowed for, and it was worth checking rather than
naming.

### Still not demonstrated

**Gameplay.** POS remains a *predictive* improvement, not an accuracy
improvement in the agent. Nothing is wired. Until it changes action selection
and moves depth or level progression, it should be called what it is.

## The predicted-position arm: FIRST ATTEMPT DISCARDED, then rewritten clean

*(The account below stands as the record of the discarded attempt. The
clean-room rewrite and its result follow it.)*

### First attempt — discarded

The pre-gameplay ablation needs a third arm: position stepped forward by a
learned model rather than held (POS) or read from the future (POS*). Note
first that **`PositionModel` cannot be reused for this**: it keys on the
global, colour-derived `MoveModel.displacement`, while H018 is per-entity.
The arm therefore learns a per-entity `(entity, position, action) ->
position'` model — the per-entity analogue, which is new machinery however
small.

**That arm's implementation is producing internally inconsistent numbers and
its output is discarded.** Adding it moved the *baseline* `tallies` arm on
sc25 from 0.876 to 0.793 and turned k=10 from 0.678 into `nan`. The baseline
cannot legitimately move: it depends only on `rollout(row, actions)` versus
the recorded effect, and nothing in the added arm touches either.

Isolated as far as: a copy of the file with **only** the `ARMS` tuple, the
`LEARN_AS` map and one print line reverted reproduces the original numbers
exactly (0.876 / POS +0.028 / POS* +0.075), twice, deterministically. So the
contamination follows from adding the arm, and the mechanism is not yet
found. Each version is self-consistent across repeated runs, so this is not
nondeterminism.

**The validated results are unaffected** — POS and POS* were measured before
this arm existed, reproduce in the clean copy, and are what the sections
above report.

**The fix is a clean-room reimplementation, not another patch.** This file
has now been edited five times by string substitution, which is how the
defect got in. That is also the standing lesson of this branch: five probe
bugs, every one caught by a number that could not be true. A baseline that
moves when only an unrelated arm is added is exactly such a number.

**Until that is done there is no predicted-vs-oracle result**, and the
engineering question it was meant to settle — does a learned forward
position recover a meaningful fraction of the oracle's +0.075 — remains
open. The gameplay gate sits behind it.

## The clean-room ablation: PRED recovers 93-100% of the oracle

`scripts/h018_ablation.py`. Four arms over the same immutable rows, action
sequences, effect tables, target mask and scoring function; the only
difference is where the position handed to the override comes from. The
invariant is **asserted, not hoped for** — `--check-invariant` re-runs with
the BASE-only arm set and compares the raw `[hits, misses, undecidable,
abstained]` cells, not the rounded score.

**INVARIANT: PASS on all three games.** BASE also reproduces the previously
validated numbers exactly (sc25 no-meter 0.876 / 0.767 / 0.678), which is the
second, independent check that the rewrite is measuring the same thing.

| game (no-meter) | k | BASE | POS | **PRED** | POS* | PRED / POS* |
|---|---|---|---|---|---|---|
| sc25 | 1 | 0.876 | +0.028 | **+0.028** | +0.028 | — |
| sc25 | 3 | 0.767 | +0.022 | **+0.053** | +0.055 | **96%** |
| sc25 | 10 | 0.678 | +0.008 | **+0.070** | +0.075 | **93%** |
| g50t | 1 | 0.785 | +0.017 | **+0.017** | +0.017 | — |
| g50t | 3 | 0.554 | +0.012 | **+0.036** | +0.037 | **97%** |
| g50t | 10 | 0.245 | +0.001 | **+0.039** | +0.039 | **100%** |
| sk48 | 10 | 0.654 | -0.000 | +0.001 | +0.002 | (null, as predicted) |

**A learned per-entity forward model transports essentially all of the
positional information.** PRED equals POS at k=1 (nothing to step forward
yet), then tracks POS* almost exactly at k=3 and k=10 while POS decays to
nothing. The earlier attenuation was entirely the frozen-position artefact,
and the fix is implementable without an oracle.

Forward-model transition accuracy, measured only on the transitions the PRED
rollout actually used: **sc25 0.908, g50t 0.817, sk48 0.893** (unseen
transitions fall back to holding, and are counted separately). So the two
failure modes this was built to separate do not arise — the model is
accurate *and* the information transports.

**sk48 stays null under every arm including the oracle** (+0.002 at k=10).
It is the negative control behaving as the hypothesis predicts: a mechanic
whose action effects do not depend on position gains nothing from position
conditioning. That is evidence *for* per-(entity, action) admission and
against installing position globally.

### The chain as it now stands

```text
retrospective signal          PASS
held-out mechanic signal      PASS
meter-confound control        PASS
action-conditional admission  PASS   (variable-only admission scored +0.000)
actual rollout consumer       PASS   (+0.028 / +0.017 at k=1)
future-position oracle        PASS   (gain grows with horizon)
implementable forward model   PASS   (93-100% of the oracle recovered)
does not harm correct cases   PASS   (369:1, 265:1 fixed:broke)
negative control behaves      PASS   (sk48 null under the oracle too)
gameplay                      NOT TESTED
```

**Every link but the last.** And the last is the one that decides whether
this is an accuracy mechanism or a predictive curiosity: nothing is wired
into `agent/`, and until POS changes action selection and moves depth or
level progression it remains a predictive improvement only.

### The abstraction this supports

Not `state = position`. The result is per-(entity, action): position earns
admission for particular pairs on particular games and is refused elsewhere
by the same rule. The shape is

    (entity, action, context) -> effect distribution

with position as one candidate context variable that has now earned
admission on two games and been refused on a third — which is the
conditional-affordance framing the project already had, extended one level
down into the effect model.
