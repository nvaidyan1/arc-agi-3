# H017: what information is the action-effect model actually missing?

Status: AUDIT DONE 2026-09-17 — three findings. (1) **The dominant error mode is the aliased case, not regime change**: 83-94% of k=1 misses are on (entity, action) pairs whose effect history is *inconsistent*. (2) **The CONTROL entity is 3.6-5.1x harder to predict than everything else** on sk48 and sc25 — the agent is worst at exactly the thing it must control. (3) The confidently-wrong residue is dominated by `moved -> unchanged`, i.e. **blocked movement**, which needs current-frame occupancy the agent already computes for routing and never gives the predictor. No candidate generated yet, by design.
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
