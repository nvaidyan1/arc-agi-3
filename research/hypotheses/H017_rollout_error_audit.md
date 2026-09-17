# H017: what information is the action-effect model actually missing?

Status: AUDIT DONE; **INTERVENTION UNTESTABLE AS SPECIFIED 2026-09-17** — conditioning the effect table on `ObstacleMap.is_blocked` is degenerate: **0 of 17,666 held-out movement rows had `blocked=True`**, because `_select` drops blocked actions from the candidate list (`my_agent.py:779`) so the action actually taken is essentially never one the map flags. The premise "the agent already knows whether the movement is blocked" is **false as stated**: the map is a LAGGING indicator that learns from failures, and by the time it knows, the agent avoids the action. Audit findings below stand. Original: AUDIT DONE 2026-09-17 — three findings. (1) **The dominant error mode is the aliased case, not regime change**: 83-94% of k=1 misses are on (entity, action) pairs whose effect history is *inconsistent*. (2) **The CONTROL entity is 3.6-5.1x harder to predict than everything else** on sk48 and sc25 — the agent is worst at exactly the thing it must control. (3) The confidently-wrong residue is dominated by `moved -> unchanged`, i.e. **blocked movement**, which needs current-frame occupancy the agent already computes for routing and never gives the predictor. No candidate generated yet, by design.
Research question: RQ2 (predictive world modelling)
Date opened: 2026-09-17
Origin: every candidate family so far (H006 A-G, conjunctions, LMU) was
generated first and tested after, and three turned out to predict a
goal-irrelevant part of the observation (`n_reset`'s frame-hash lift, H008's
Z1 k-step gain, gate 2's strip bbox). Reviewer C: *"error attribution comes
before candidate generation"*. So start from the predictor's own mistakes.

## The target firewall this adopts

| target | question | use |
|---|---|---|
| **A — observational** | does it predict the frame? | diagnostic only |
| **B — instrumental** | does it predict the consequence of an action on the controllable mechanic? | **the promotion gate** |

Only B may justify changing the agent. A candidate can be excellent at A and
irrelevant to B — `n_reset` and H008's Z1 both were. This audit is on B
only: `predictor.effect_table` read at k=1, on **non-meter entities**, which
is what `predictor.rollout` consumes.

## Result

30 traces per game, k=1, non-meter entities.

| game | predictions | accuracy | confidently wrong | inconsistent-history misses | share of misses that are inconsistent |
|---|---|---|---|---|---|
| sk48 | 140,544 | 0.872 | 3,128 (0.030) | 14,914 (0.413) | **83%** |
| su15 | 46,584 | 0.927 | 1,683 (0.038) | 1,731 (0.663) | 51% |
| g50t | 57,351 | 0.779 | 1,151 (0.037) | 11,526 (0.437) | **91%** |
| sc25 | 109,737 | 0.865 | 913 (0.011) | 13,885 (0.471) | **94%** |

`confidence` is the majority *rate* of an effect over pairs already tried
>= `PREDICT_MIN_TRIES` (4) times. **Low confidence therefore means the effect
VARIES, not that observations are few** — an earlier draft of the script
called this "sampling", which was wrong and is corrected.

### Finding 1 — the dominant error is the aliased case

83-94% of misses (51% on su15) are on pairs whose effect history is
inconsistent. That is exactly H006's premise, but now measured **on the
instrumental target rather than the frame**. It is the first time the
aliasing question has been posed where it matters.

### Finding 2 — the agent is worst at the thing it controls

| game | CONTROL miss rate | non-control | ratio |
|---|---|---|---|
| sk48 | **0.262** | 0.073 | **3.6x** |
| sc25 | **0.312** | 0.061 | **5.1x** |
| g50t | 0.225 | 0.211 | 1.1x |

(su15's control entity has 17 predictions — not read.) On two of three
readable games the action-effect model is 3.6-5.1x worse on the CONTROL
entity than on everything else. Every prediction that matters for navigation
or goal-seeking is about that entity.

### Finding 3 — the confidently-wrong residue is blocked movement

Top confusions among confidently-wrong cells:

| game | predicted -> actual | n |
|---|---|---|
| sk48 | `unchanged -> vanished` | 1155 |
| sk48 | `moved(0,-1) -> unchanged` | 606 |
| sk48 | `moved(0,1) -> unchanged` | 472 |
| g50t | `moved(1,0) -> unchanged` | 154 |
| sc25 | `moved(1,0) -> unchanged` | 122 |

`moved -> unchanged` is the model expecting the controlled thing to move
when it did not: **blocked by geometry**. The agent already computes an
obstacle map (`obstacles.is_blocked`, used by `navigation.plan`/`plan_graph`)
and **never gives it to the predictor**. This is current-frame information,
not hidden history — the opposite of everything the last two days looked for.

## What this does NOT claim

No candidate is proposed and nothing is wired. Finding 3 names information
the agent already holds; whether conditioning the effect table on it improves
rollout accuracy is an experiment, not a conclusion, and it must pass the
same chain: instrumental target -> holdout -> consumer -> gameplay.

Finding 1 says the aliased mass is where a conditioning variable would pay
**if anything does**; H013/E1 showed families A-G do not pay on the frame
target, and the consumer test showed `last_changer` does not pay here. The
open question is what would make an inconsistent (entity, action) effect
consistent, asked on this target.

## Status log

- 2026-09-17 audit built and run on sk48/su15/g50t/sc25,
  `scripts/h017_rollout_error_audit.py`. One labelling error found and fixed
  mid-analysis: low confidence was described as a sampling problem when it
  is an inconsistency signal, which inverts what that 83-94% mass means.

## The intervention, and why it could not be run as specified (2026-09-17)

The experiment was built exactly as scoped — `is_blocked` into the effect
predictor, obstacle map as-is, same admit bar, same holdout protocol,
instrumental target, with the blocked/unblocked x CONTROL breakdown.

**It is degenerate.** Every cell came back +0.000, and the `blocked
movement` and `CONTROL x blocked` rows were **absent entirely** — the
signature of a condition that is always False, not of a null result.
Measured directly: **0 of 17,666 held-out movement rows on sk48 had
`blocked=True`.**

**Cause, verified in code.** `my_agent.py:779` — *"drop blocked actions
while alternatives remain"* — removes exactly the actions the map flags from
the candidate list. So the action actually taken is almost never one
`is_blocked` reports, and conditioning the effect table on it conditions on
a constant.

**This falsifies the premise the intervention rested on.** `ObstacleMap` is
a **lagging** indicator: `_blocked[(position, action)]` only reaches
`BLOCKED_MIN_OBSERVATIONS` *after* the failures happen. At the instant of a
confidently-wrong `moved -> unchanged` prediction the map does not yet know —
that prediction error **is** the observation the map learns from. The
information the predictor needs is not in the obstacle map and cannot be:
these are first-time collisions, which no learned failure map can anticipate.

**What would be needed instead: a LEADING indicator** — current-frame
destination occupancy, i.e. whether the CONTROL entity's bbox translated by
the expected displacement lands on another entity or off-grid. That is
available at prediction time. It is also, explicitly, *"a new spatial
computation"*, which the intervention was scoped to avoid, so it is a
decision rather than a continuation.

**A first probe of that is recorded as INCONCLUSIVE, not as evidence.** The
quick version returned "destination occupied" for **100%** of cases on all
three games — a bug signature, not a finding: these games have a
board-spanning container entity (sk48's entity 0 is bbox [0,0,63,52]) that
every translated box overlaps, and the probe excluded only meter-like
entities. It also found very few CONTROL 'moved' predictions to score (339 /
65 / 5), which needs explaining before any occupancy result would mean
anything. Not patched further under time pressure; it needs proper design.

**Status of the three audit findings: unchanged.** The aliasing
concentration (83-94%), the CONTROL-entity gap (3.6-5.1x) and the
`moved -> unchanged` dominance are measurements of the predictor's errors and
do not depend on this intervention. What changed is the candidate: the
cheapest information the agent already holds turns out to be unavailable at
the moment it is needed.

## Why CONTROL 'moved' predictions looked rare: they are not. There are 3-6 CONTROL entities per step

The question was posed off a bad count of mine — the probe took `ctrl[0]`,
the **first** control entity, when these games have several. Corrected, over
all control entities under movement actions:

| game | predicted `moved` | actual `moved` | predicted `unchanged` | actual `unchanged` |
|---|---|---|---|---|
| sk48 | 10,173 | 8,808 | 7,640 | 10,033 |
| sc25 | 7,299 | 4,960 | 8,172 | 10,724 |
| g50t | 3,846 | 3,951 | 20,344 | 19,762 |

`moved` predictions are not rare at all. **The real finding is the number of
CONTROL entities per step:**

| game | control entities per step (modal) | distribution |
|---|---|---|
| sk48 | **4** | {0: 413, 1: 15, 2: 187, 3: 2363, **4: 4213**, 5: 386, 6: 40} |
| sc25 | **4** | {0: 1012, 1: 359, 2: 1165, 3: 2176, **4: 3771**} |
| g50t | **4** | {0: 388, 1: 27, 2: 178, 3: 2234, **4: 4945**, 5: 21} |

**The agent does not have "the controlled thing". It has three to six
entities simultaneously labelled CONTROL**, on every one of these games.

And the set is over-predicted to move: sk48 predicts `moved` 10,173 times
against 8,808 actual, and `unchanged` 7,640 against 10,033 — exactly the
signature of a set containing members that are not in fact controlled.

### What this does to H017's findings

- **Finding 2 needs re-reading.** "The CONTROL entity is 3.6-5.1x harder to
  predict" is not about one hard entity; it is about a *set* whose
  membership is doubtful. The difficulty may be an artefact of
  **mislabelling** rather than intrinsic to control.
- **Finding 3 survives and sharpens.** The confidently-wrong
  `moved -> unchanged` errors are overwhelmingly on CONTROL-labelled
  entities — sk48 907 vs 35 non-control, g50t 256 vs 25, sc25 147 vs 52 —
  so they are concentrated exactly where the labelling is suspect.
- It also connects to a standing open item: *"`sp80` assigns no CONTROL
  despite having two controllable objects"*. Over-assignment here,
  under-assignment there — the same detector.

### The question this replaces the old one with

Before any further conditioning variable: **are these entities actually
controlled?** If 3 of 4 are not, then the effect table is being asked to
learn action effects for entities the action does not drive, which would
explain a large share of the aliasing that H017 measured without any hidden
state being involved at all.

That is cheap to check against `Belief.controllers` / the CONTROL-by-
determinism rule, and it is a **detector** question, not a representation
one. No new machinery is implied.

### My error, recorded

The probe that produced "339 CONTROL 'moved' predictions on sk48" took only
the first control entity. The true figure is 10,173. The bad number is what
prompted the question; the correction is what produced the finding. Fourth
probe bug in two days of this branch, and the same lesson: a surprising
count is a bug signal before it is a result.

## The cheap test: CONTROL is never a singleton, on any game

Modal count of simultaneously CONTROL-labelled entities, 5 traces per game:

| game | modal CONTROL count | share of steps | distribution |
|---|---|---|---|
| **cd82** | **2** | 52% | {0: 185, 2: 1034, 3: 768} |
| m0r0 | 3 | 72% | {0: 101, 1: 5, 2: 443, 3: 1435, 4: 11} |
| sk48 | 3 | 47% | {0: 102, 1: 2, 2: 36, 3: 935, 4: 698, 5: 114, 6: 87, 7: 26} |
| sc25 | 4 | 44% | {0: 277, 1: 120, 2: 77, 3: 625, 4: 871} |
| g50t | 4 | 77% | {0: 100, 1: 7, 2: 31, 3: 322, 4: 1530} |
| **dc22** | **0** | 87% | {0: 1725, 1: 265} |
| **su15** | **0** | 100% | {0: 1995} |

**No game has a modal CONTROL count of 1.** Not one. Even **cd82** — the
flagship where H009/H010 proved the controlled thing's motion is a
deterministic function of `(position, action)` — carries **2**, and reaches
3 on 38% of steps. Two games get essentially no CONTROL at all, which is the
under-assignment counterpart of the standing item *"`sp80` assigns no
CONTROL despite having two controllable objects"*: the same detector,
failing in both directions across the set.

### The structural mismatch this exposes

`MoveModel` is singular by construction. `self.displacement` is **one**
running position, advanced by `observe_translation(action, offset, size, …)`
for whatever translated; `controlled_size` is a single `max()`. And
`PositionModel` (H010) keys its whole transition graph on that one
`displacement`.

So a single coordinate is accumulating the motion of a 2-4 member set.

### What is and is NOT established

**Established:** the counts above, read straight from the traces, and the
singularity of `MoveModel`/`PositionModel`'s position key, read from the
code.

**NOT established: that the role is over-assigned.** An earlier version of
this analysis claimed that, using a bar I invented (counting `unchanged`
outcomes). The agent's actual rule — `Belief.controllers`, via
`determinism()` — tallies **only the changes an action caused**, since
`UNCHANGED` is by definition the complement of every entry in
`Belief.effects`. Replicating the real rule: sc25 **5 of 5** labelled
entities earn it, sk48 6 of 11, g50t 2 of 6 — and every "failure" is an
entity with too few *changes* in-sample to evaluate, not one that fails the
discrimination test. Role assignment also uses accumulated evidence with
hysteresis and a 20-observation floor that a trace-slice reconstruction
cannot reproduce. **The claim "most CONTROL labels are unearned" is
withdrawn.**

They are also not one fragmented object: effects differ across the set on
58-80% of steps, and on sc25 no two control bboxes overlap at all (0 of
14,436 pairs).

### The question this leaves

Not "is the role wrong?" but: **what does a single `displacement` mean when
2-4 entities are labelled control?** `PositionModel` passed its offline
validation on cd82 at a control count of 2 (1,779/1,779 first steps
honoured), so two did not break it there. Whether the position key degrades
as the set grows is measurable on the traces already collected, and is a
detector/bookkeeping question — no new representation is implied.
