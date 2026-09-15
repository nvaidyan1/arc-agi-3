# H004: Competing transition hypotheses — one press falsifies one

Status: TESTED — mechanism fires as designed; behavioural read is mixed, not a clean win over E-7a
Research question: RQ3 (active testing) / RQ2 (predictive world modelling)
Date opened: 2026-09-14
Origin: reviewer C §32 steps 3–4 and the second note ("genuinely competing
hypotheses, before a language model"); `docs/plan.md` START HERE, item 2.
Depends on H003 (the forecast vocabulary the rivals disagree in).

## Claim

The enumerator's bets are not in competition: it proposes one lever per
residual, and a step under an unmet precondition is filed as "not
evidence". So the agent never asks the question whose answer would settle
a rule — *does the paint action work from any side, or only from −x?* —
and every precondition it adopts is adopted on a tally, not on a test.
Proposing **rival rules about the same action whose forecasts differ**,
and pressing where they differ, turns one step into a falsification of
one of them. The rule the agent keeps is then the one that survived a
test designed to kill it.

## Mechanism

```
rivals(key, action):
    G  general    "ACTION drives residual(key) down"                 precondition None
    S  specific   "ACTION drives residual(key) down ONLY when <cond>" precondition cond, exclusive

    proposed together whenever the record shows a conditional lever
    (S's condition) — or an unconditional lever whose DOWN rate under
    one condition exceeds its overall rate by LEVER_MIN_LIFT.

forecasts in the current state:
    condition met      G: down      S: down       -> no discrimination
    condition unmet    G: down      S: not down   -> one press decides

select_experiment prefers, among legal actions, one whose live bets
diverge in the current state; the bet acted under is the ready one (G),
so the press happens now rather than after a route.

verification: every live bet whose action was taken is scored (riders),
each under its own precondition reading at decision time:
    S, unmet, residual fell      -> AGAINST (a strike; two strikes falsify)
    S, unmet, residual held      -> SUPPORTED (the exclusivity held)
    S, met                        -> as before (down = supported, held at 0)
    G, any                        -> as before
```

Nothing new is asserted about games: a rival is only ever a *weaker* or
*stronger* reading of a tally the layers already hold, and both readings
are killed by observations the vocabulary can already make.

## Prediction

1. On cd82, G (`ACTION5` drives `part_size_diff(template content, block)`
   down from any side) is falsified within one budget and S
   (`adjacent:-x`, exclusive) survives it; the PRECONDITION_UNMET share
   of ACTION5 steps falls, because unmet steps now test G.
2. On the navigational games (sp80, ls20, m0r0, ar25) rivals rarely form
   — d-pad levers are unconditional — and behaviour is unchanged.
3. Touched-8 score under `ARC_PROPOSER=1` holds against the E-7a arm
   (n=30 seed-paired): no per-game loss beyond the paired noise. cd82 is
   *not* expected to recover (the arrangement problem is not this one).

## Falsifier

- Rivals form and the discriminating press is never taken: the selector
  is not choosing the divergent state (a selector bug, or preconditions
  are always met when the bet is live).
- G and S die at the same rate on cd82: the press does not discriminate,
  so side is not the factor — H001's diagnosis was wrong.
- The navigational games lose under the proposer arm: rivals are
  displacing levers that were working.

## Experiment

E-H004-1: touched-8, n=30 seed-paired, `ARC_PROPOSER=1`, against the
E-7a arm at the same seeds. Read per game: rival pairs proposed,
discriminating presses, which rival died first, PRECONDITION_UNMET
share, sweeps reaching L1, median score.

## Metrics

rival pairs proposed per level; discriminating presses per level; (G
falsified, S survived) / (S falsified, G survived) / (both) / (neither)
per game; PRECONDITION_UNMET share of hypothesis steps; touched-8 median.

## Status log

- 2026-09-14 opened, after H003's forecast layer.
- 2026-09-14 built (`agent/hypothesis.py`: `forecast`/`exclusive`/`strikes`,
  `Proposer.rival`; `agent/proposer_llm.py`: `select_experiment` prefers a
  divergent action, `diverges`; `agent/my_agent.py`: `_arm_riders`, every
  pool bet on the pressed action scored alongside the live one, rival
  linking survives an illegal-action drop without counting a death). 239
  tests. Mechanism check, cd82 seed 8, 400 steps: 30 rival pairs proposed,
  46 discriminating presses, 6 general-died-first, 3 specific-died-first —
  the discrimination fires as designed and is not rare.
- 2026-09-14 E-H004-1 (touched 8 × 30 seeds × 400 steps, `ARC_PROPOSER=1`),
  read against E-7a's numbers in `history.md` (same arm, same n, **not
  seed-paired** — E-7a's seed list was not preserved, so this is an
  unpaired arm comparison, not a permutation test):

  | game | L1 reach, E-7a | L1 reach, H004 |
  |---|---|---|
  | cd82 | 2/30 | 1/30 |
  | sp80 | 25/30 | 24/30 |
  | ar25 | 15/30 | 13/30 |
  | m0r0 | 6/30 | 11/30 |
  | cn04 | 5/30 | 4/30 |
  | sk48 | 1/30 | 1/30 |
  | ls20 | 0/30 | 0/30 |
  | tr87 | 0/30 | 0/30 |

  touched-8 median score: 0.110 (E-7a) -> **0.075** (H004).

**Inference.** Prediction 1 (cd82 unaffected) holds — flat within noise, as
expected; H004 was never expected to fix cd82's arrangement problem.
Prediction 2 (navigational games hold) is not clean: m0r0 gains sharply
(+5/30) but ar25 gives back 2/30 and the median score falls 32% against
E-7a. Reach counts and score disagree in direction (m0r0 up on reach, net
score down), consistent with score being quadratic in speed — a rival
press can win the same level slower. Without seed pairing this is not
strong enough to call the falsifier met, but it is not the clean hold
Prediction 3 asked for either. **Not promoted.** Kept behind
`ARC_PROPOSER` (default OFF, unchanged). Before this arm is reconsidered:
a seed-paired re-run against E-7a's actual seeds (recover or redraw them),
and a per-level cost breakdown to see whether the discriminating presses
are the ones adding steps on ar25.
