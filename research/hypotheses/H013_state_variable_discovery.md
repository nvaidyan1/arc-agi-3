# H013: can our state-selection machinery discover the variables that disambiguate an unseen mechanic?

Status: TESTED 2026-09-17 — **YES, and the missing ingredient was repeats, not a new candidate family.** With 3x H006's traces (30 seeds, not 10), the existing *temporal* family resolves the mechanic remainder above null on all four games: su15 `n_moved` +19.2, sk48 `last_changer` +68.2, g50t `n_level` +40.8, sc25 essentially all-meter (4 mechanic contexts left). **The relational family — the one H006 and reviewer C both predicted was needed — did not win on any game.** A real remainder persists (still-refuted: su15 36%, sk48 23%, g50t 54%).
Research question: RQ2 (predictive world modelling)
Date opened: 2026-09-17
Origin: branch 2 of the 09-17 diagnostic fork, and deliberately the one line
of work that does **not** depend on the cd82 story — H007, H010 and H015 all
hang off the same unresolved bet, and the project had become dangerously
concentrated on one game. H006 left ~72 mechanic-aliased contexts on
su15/sk48/sc25/g50t where its history-derived family was "refuted or below
null", and named two requirements: more repeats (at ~2 visits a splitter can
only be REFUTED, never confirmed) and a family referencing the controlled
thing's relation to the clicked or moved entity.

## Claim

Scoped as the reviewer framed it, deliberately larger than "find one more
latent variable": **can the existing state-selection machinery discover the
variables required to disambiguate an unseen mechanic?** For each unresolved
alias, classify candidate splits by family and ask whether any produces a
repeatable split above the null.

| | family |
|---|---|
| A | **temporal** — actions since reset, event history (`latent_splitter`'s own) |
| B | **spatial** — absolute / relative position of the controlled thing |
| C | **relational** — controlled entity <-> clicked / moved entity |
| D | **interaction history** — which object has been touched / activated |
| E | **configuration** — arrangement, occupancy, cardinality |
| F | **unexplained** |

Family A is reused from `latent_splitter.py` unchanged, so this is a strict
extension rather than a reimplementation.

## Result (2026-09-17)

30 seeds per game (H006 had 10), 12,030 steps each, restricted to the
**mechanic** remainder — contexts whose outcomes differ OFF the quantised
meter line, which is H006's own classification and H013's actual target.
Without that filter the temporal family simply re-finds the meters H006
already explained.

| game | aliased | mechanic | winner | family | resolved | still | null | lift |
|---|---|---|---|---|---|---|---|---|
| su15 | 115 | 98 | `n_moved` | **A** | 28 | 35 | 8.8 | **+19.2** |
| sk48 | 1488 | 314 | `last_changer` | **A** | 97 | 72 | 28.8 | **+68.2** |
| sc25 | 644 | 4 | `n_reset` | **A** | 4 | 0 | 0.0 | +4.0 |
| g50t | 1597 | 400 | `n_level` | **A** | 44 | 217 | 3.2 | **+40.8** |

**Families that won: A on all four. B, C, D and E won nowhere.** The closest
any non-temporal family came was `D_touched_set` on sk48 (+33.8), runner-up
to `last_changer` (+68.2).

**The headline is what this says about H006's negatives.** H006 reported
sk48's best candidate at 19 resolved vs a null of 21 — noise — and su15's
`n_moved` at 10 vs 1.8 as "suggestive, not confirmed". At 30 seeds sk48's
`last_changer` is 97 vs 28.8 and su15's `n_moved` is 28 vs 8.8. **Those
refutations were underpowered, not correct.** H006's own stated requirement
— more repeats — was the binding constraint, and the candidate family it
guessed was missing was not missing at all.

## What this does and does not support

- **Supports:** the existing machinery *can* discover disambiguating
  variables on games it was not designed around, given enough visits per
  context. That is a positive result for the current representation
  philosophy and an argument against reaching for new representation first.
- **Does not support:** a relational state layer. The family reviewer C and
  H006 both predicted would be needed lost to plain temporal candidates on
  every game.
- **Leaves open:** a substantial remainder. Still-refuted after the winner:
  su15 35 of 98 (36%), sk48 72 of 314 (23%), g50t 217 of 400 (54%). g50t in
  particular is more than half unexplained.

## Consequence for H014 (LMU)

Weakened, not strengthened. The variables that resolve these mechanics are
*explicit temporal* ones the enumerator already generates. An untrained LMU
asks whether generic temporal compression finds structure **beyond** those —
and the explicit temporal family has just been shown to do most of the
available work once it has data. The honest remaining question for H014 is
narrower: does it explain the g50t remainder? That is a smaller mandate than
"is temporal memory the missing architecture".

## Method caveats, stated

- The meter/mechanic filter is an operational proxy for H006's hand
  classification: a context is METER when its outcomes differ within <= 2
  rows or <= 2 columns. The first version tested a single row/column and
  wrongly called all 644 sc25 contexts mechanic; H006 documents sc25's meter
  as columns 62-63. Corrected, sc25 has 4 mechanic contexts — i.e. it is
  essentially all meter, consistent with H006.
- `singleton` counts stay large (e.g. sk48 145 of 314). A singleton is a
  re-key that merely made every visit unique and is vacuous by H006's own
  definition; only `resolved` counts, and the table reports it.

## Status log

- 2026-09-17 opened, traces run (seeds 11-30, four games, ~31 s each),
  `scripts/h013_family_splitter.py` written as an extension of
  `latent_splitter.py`. Result above. Two bugs found and fixed while
  building: candidate keys differ between traces so `values` was sparse
  across files (filled the union with None, "not applicable" being a
  legitimate group), and the meter filter above.

## Evidence curves: the sample-complexity result (2026-09-17)

Mined from the data already collected — no new sweep — by rescoring each
winning candidate against its own shuffle null using only the first N traces.
The question: *when* did each candidate become distinguishable from null?

| traces | su15 `n_moved` | sk48 `last_changer` | g50t `n_level` |
|---|---|---|---|
| 5 | +5.4 | **-2.0** | +3.0 |
| 10 (H006's regime) | +6.0 | **+1.6** | +14.6 |
| 15 | +6.6 | +9.2 | +34.8 |
| 20 | +11.4 | +17.2 | +42.0 |
| 25 | +14.0 | +47.0 | +38.4 |
| 30 | +18.2 | +65.8 | +41.2 |

**Three different shapes, and the difference is the finding.**

- **sk48 is a pure sample-complexity result.** At 10 traces `last_changer`
  sits at +1.6 — indistinguishable from null, exactly the "19 resolved vs
  null 21, noise" H006 recorded. It emerges near 15 and only becomes strong
  past 25. **H006 could not have found it; it was 2-3x under-powered.** This
  is the clean case for "the learner needs to know how much evidence it
  needs".
- **su15 rises steadily and is still rising at 30.** Detectable weakly at 10
  (which is why H006 called it "suggestive"), never saturating. More data
  keeps helping.
- **g50t SATURATES at ~20 traces** (+42.0, +38.4, +41.2) while its
  unresolved count keeps climbing: 45 -> 86 -> 134 -> 185 -> 217. More data
  adds unresolved contexts faster than `n_level` resolves them. **g50t is
  therefore NOT an evidence problem.** `n_level` explains a fixed subset and
  the remaining 217 are a genuine representational gap.

That distinction matters more than the headline. "Give the learner more
repeats" is the right answer for sk48 and su15 and the *wrong* answer for
g50t, and only the curve separates them. An agent that could read its own
curve would know which of its uncertainties deserve more experience and
which need a different question asked.

## The g50t remainder, and the one narrow mandate left for H014

Reviewer C's gate before any appeal to an LMU: *first ask whether a simple
explicit variable — last action, last changer, action counts, time-since,
a short action n-gram — solves it. If yes, we do not need an LMU.*

Family **G (ordered / sequence)** was added and run on g50t's 400 mechanic
contexts: `G_ngram2/3/4` (the last 2-4 actions in order), `G_since_change`,
`G_last2_changers`, and `G_since_<action>` per action.

| candidate | family | resolved | still | null | lift |
|---|---|---|---|---|---|
| `n_level` | A | 44 | 217 | 2.8 | **+40.4** |
| `presses_since_click` | A | 21 | 323 | 11.0 | +10.0 |
| `G_ngram3` | **G** | 33 | 200 | 26.0 | +7.0 |
| `G_ngram4` | **G** | 21 | 89 | 15.2 | +5.8 |
| `n_4` | A | 27 | 183 | 21.6 | +5.4 |

**Explicit sequence variables do not crack it.** `G_ngram3` is weakly above
its own null (+7.0) and still leaves 200 of 400 refuted; nothing in families
A-G resolves more than ~11% of g50t's mechanic contexts, and the best
candidate saturates with more data rather than improving.

So the answer to the gate is **no** — and that is precisely the narrow
condition under which H014 keeps a mandate. Not "is temporal memory the
missing architecture", but: **does an order-sensitive history representation
separate the g50t contexts that every explicit candidate we can enumerate
has failed to separate?** One game, one well-posed question, offline, with
the explicit alternatives already ruled out rather than assumed away.

## The conjunction test: g50t's remainder was a missing PAIR, not a missing representation

The cheaper thing, tried first as the gate required. Scoring **pairs** of the
top-8 single candidates (28 pairs) on g50t's 400 mechanic contexts:

| candidate | resolved | still | null | lift |
|---|---|---|---|---|
| `n_level` (best single) | 44 | 217 | 2.8 | +40.4 |
| **`G_ngram3` AND `n_reset`** | **81** | **100** | 1.0 | **+80.0** |
| `G_ngram3` AND `presses_since_click` | 81 | 100 | 1.3 | +79.7 |
| `presses_since_click` AND `G_last2_changers` | 62 | 52 | 1.0 | +61.0 |

**The best conjunctive candidate increased resolved contexts from 44 to 81
while reducing unresolved contexts from 217 to 100, against a null of 1.0.**
That is a strong *discovery signal*, not yet a causal result: 81 resolved is
not 81 contexts causally explained, because a conjunction also partitions
observations into smaller groups where local consistency is easier to reach.
The >= 2-visit requirement blocks wholly vacuous singletons but does not
remove the fragmentation and multiple-comparisons concern. Held-out
prediction is the test that settles it (E1). Both halves are
explicit candidates the machinery already enumerates: a three-action n-gram
AND actions-since-reset.

So g50t's remainder was **not** a representational gap needing an
order-sensitive memory. It was a missing *conjunction* of two variables we
already had. The machinery held both pieces and never combined them.

**This retires H014's last narrow mandate.** The condition under which an
LMU stayed interesting was "every explicit candidate we can enumerate fails
on g50t". That is now false — a pair of them succeeds. H014 is parked with
no live question. Revisit only if the residual 100 contexts prove resistant
to further conjunction and to triples.

**The concrete upgrade this implies**, and the real value of the result:
H006's admission machinery scores **single** candidates only. H005 already
built conjunctive *preconditions* for hypotheses — the same idea, one layer
up — but the splitter that promotes a variable into predictive state never
learned it. Scoring conjunctions at admission is cheap, uses only what
exists, and is worth 37 extra resolved contexts on the one game we thought
needed new representation.

**Caveat, stated honestly.** The pair fragments the context space:
singletons rise from 139 to 219 as still falls from 217 to 100, so part of
the movement is contexts becoming vacuously unique rather than genuinely
explained. `resolved` (which requires at least one value-group with >= 2
visits) is the honest measure, and at 81 against a null of 1.0 it is far
above chance — but the conjunction is not free, and triples would fragment
further. Diminishing returns should be expected.

## E1 — held-out validation: the conjunction does NOT survive (2026-09-17)

Discover on seeds <= 20, freeze, predict seeds 21-30. Baseline is
**context-majority** — predict the pixel-context's most common outcome,
ignoring the candidate entirely; that is exactly "no state variable".
Restricted to contexts aliased (and mechanic) in the discovery data, since
deterministic contexts are predicted perfectly by the baseline and only
dilute the comparison.

**g50t** — 461 held-out visits, baseline accuracy 0.289

| candidate | coverage | acc where covered | acc overall | lift |
|---|---|---|---|---|
| **`n_reset`** | **0.92** | 0.566 | **0.523** | **+0.234** |
| `n_level` | 0.59 | 0.467 | 0.367 | +0.078 |
| `G_ngram3 AND n_reset` | **0.25** | **0.612** | 0.349 | +0.061 |
| `B_disp` | 0.09 | 0.537 | 0.306 | +0.017 |
| `G_ngram3` | 0.40 | 0.350 | 0.299 | +0.011 |

**sk48** — 128 held-out visits, baseline 0.453

| candidate | coverage | acc where covered | acc overall | lift |
|---|---|---|---|---|
| **`G_ngram3`** | 0.32 | 0.805 | **0.508** | **+0.055** |
| `G_ngram3 AND n_reset` | **0.10** | **0.923** | 0.461 | +0.008 |
| `n_reset` | 0.23 | 0.655 | 0.461 | +0.008 |
| `B_disp` | 0.23 | 0.667 | 0.445 | -0.008 |

**su15** — 13 held-out visits. **Too few to interpret**; every candidate sits
at or below a baseline of 1.000. Not read.

**Verdict: E1 fails for the conjunction. The 81-vs-44 result was largely
partitioning, exactly as suspected.** On both games with enough held-out
data the pair is beaten by a *single* variable, and the retrospective
ranking reverses.

**But the failure has a precise shape, and it is not "the pair is wrong".**
The conjunction has the **highest accuracy wherever it applies** — 0.612 on
g50t, 0.923 on sk48 — and the lowest coverage, 0.25 and 0.10. It is
*precise but narrow*: when its key was seen in discovery it predicts very
well, and most of the time its key was never seen. That is a data-volume
problem, not a validity problem, and it is the sample-complexity result
again one level up: **a conjunction costs far more evidence than either of
its parts, and we do not have that evidence.**

**What E1 did establish, and it is not nothing.** A single explicit temporal
variable carries real, substantial held-out predictive lift: `n_reset` on
g50t is +0.234 over the no-state baseline at 92% coverage. The best variable
differs per game (`n_reset` on g50t, `G_ngram3` on sk48), so no single
candidate is universal — which is itself an argument for per-game admission
rather than a fixed schema.

**The methodological finding is the most valuable part.** Retrospective
context-resolution ranked the pair first; held-out prediction ranks it
third. **Resolved-context counts are a misleading metric on their own**, and
every H006/H013-style result should be read through a holdout gate before it
is allowed to motivate code. This is the filter working as intended, on the
first result it was pointed at.

**Consequence: conjunctive admission is NOT the next code change.** It was
the leading candidate an hour ago on retrospective evidence and it does not
survive its own validation. Caveat kept: coverage would rise with far more
data, so the finding is "does not pay at available data volumes", not
"never".

## E2 — the evidence curve, with a FIXED held-out set (2026-09-17)

The earlier curves varied discovery and held-out together. Here the held-out
set is fixed at seeds 26-30 and only the discovery budget moves, so the
curve measures one thing.

**g50t** (lift over the no-state baseline)

| discovery seeds | `n_reset` | `n_level` | `G_ngram3` | `n_reset` coverage |
|---|---|---|---|---|
| 5 | **+0.122** | -0.073 | +0.049 | 0.73 |
| 10 | **+0.165** | +0.028 | +0.037 | 0.84 |
| 15 | **+0.190** | +0.076 | +0.027 | 0.87 |
| 20 | **+0.247** | +0.076 | +0.022 | 0.91 |
| 25 | **+0.253** | +0.122 | +0.033 | 0.94 |

**sk48**

| discovery seeds | `last_changer` | `G_ngram3` | `n_reset` |
|---|---|---|---|
| 5 | (n=4, not interpretable) | — | — |
| 10 | **+0.161** | +0.065 | +0.000 |
| 15 | **+0.289** | +0.067 | +0.000 |
| 20 | **+0.297** | +0.047 | -0.016 |
| 25 | **+0.247** | +0.026 | +0.013 |

**Answer to "can early evidence predict eventual usefulness?": YES, and
earlier than expected.** On g50t `n_reset` is the best candidate at **5**
discovery seeds and at every budget after; the ranking never changes. On
sk48 `last_changer` is clearly best from **10** seeds and stays there. More
evidence sharpens accuracy (g50t +0.122 -> +0.253); it does not change
*which* variable wins.

### This corrects H013's own sample-complexity claim

H013 concluded from the *retrospective* curve that H006 was "2-3x
under-powered" on sk48 — `last_changer` sat at +1.6 over null at 10 traces,
indistinguishable from noise. But **held-out prediction at the same 10-seed
budget already shows `last_changer` at +0.161**, clearly the best candidate.

So H006 had enough data. **It used a metric that could not see the signal.**
The retrospective resolved-context count is not merely misleading for
conjunctions (E1) — it is *less sensitive than held-out prediction for
single candidates too*. "H006 was under-powered" should read: **H006 was
under-powered *for the metric it used*.**

### A correction to E1

E1 reported sk48's best held-out variable as `G_ngram3` (+0.055). That was
an artefact of an incomplete candidate list: `last_changer` — H013's own
retrospective winner on sk48 — was not among the candidates scored. At the
same split it reaches **+0.297**, six times better. E1's claim that "the best
variable differs per game" survives (g50t `n_reset`, sk48 `last_changer`),
but the sk48 figure was wrong.

Caveat on the curves: the evaluated context set grows with the discovery
budget (more contexts are identified as aliased), so the baseline drifts
between rows and absolute lifts are not perfectly comparable down a column.
**The within-row ranking is the robust read**, and it is what the question
turns on.

## E3 — promotion audit: there is no pathway, not a bad threshold

Where does a discovered variable get used? Traced through `agent/`:

- `grep` for `n_reset`, `since_reset`, `Z1`, `attempt_actions` across
  `agent/*.py` returns **nothing**. The variable with +0.25 held-out lift on
  g50t **does not exist in the agent**.
- The live predictor conditions its tallies through
  `relations.condition_now()`, whose docstring is explicit: *"where the
  controlled thing stands relative to its nearest non-control member **on
  the current frame**"*. The conditioning vocabulary is **spatial-relational
  and computed from the current frame only**.
- `scripts/latent_rollout.py` says so in as many words: it "adds the arm
  **the agent cannot run yet**".

**So the answer to "why wasn't this variable already driving behaviour?" is
not premature rejection, not a threshold, and not evidence allocation. There
is no slot in the tally key for a history-derived variable.** Every
discovery from H006, H008, H013, E1 and E2 lives in offline scripts. The
agent has never had access to any of it.

That makes the next intervention much smaller and better-founded than
"evidence-aware promotion": give `by_action_given` a key that can carry a
history-derived variable, admit one per game on the evidence the machinery
already computes, and measure. The three-state promotion ladder
(rejected / provisional / promoted) is a refinement of a mechanism that does
not yet exist — build the mechanism first.

## THE METER CONFOUND — E1's headline retracted, and one result survives (2026-09-17)

Before wiring anything, one design-gating check. The outcome E1 and E2
predict is the **whole next-frame hash**, and the quantised meter line is
part of every frame. A variable that predicts only the meter therefore
scores as predicting the frame — even on contexts my filter called
"mechanic", because that filter tested the *diff* and let through any
context whose outcomes differed on the meter *and* elsewhere.

The correct control is to blank the game's meter line before hashing the
outcome (H006's documented lines: g50t row 63, sk48 row 53, sc25 cols 62-63,
cd82 row 63).

| game | candidate | unmasked lift | **meter-masked lift** | masked coverage |
|---|---|---|---|---|
| g50t | `n_reset` | +0.234 | **-0.019** | 0.66 |
| g50t | `n_level` | +0.078 | **-0.041** | 0.40 |
| sk48 | `last_changer` | +0.234 | **+0.281** | **0.98** |
| sk48 | `G_ngram3` | +0.055 | **+0.210** | 0.89 |

**RETRACTED: "a single explicit temporal variable carries real held-out
predictive lift (`n_reset`, +0.234 on g50t)".** With the meter masked it is
**-0.019** — worse than the no-state baseline. Its entire lift was
predicting the meter, which H006 established is real, deterministic and
**goal-irrelevant**. E2's g50t curve (best at 5 seeds, rising to +0.253) is
measuring meter prediction throughout and carries the same retraction.
g50t's aliased-mechanic count falls from 284 to 58 under masking: most of
what the diff-based filter called mechanic was meter-contaminated.

**SURVIVES, and gets stronger: sk48's `last_changer`, +0.281 at 98%
coverage.** This is the first candidate in the entire branch to pass every
filter in sequence:

```text
retrospective discovery   +68.2 over null   (H013)
        -> holdout        +0.234            (E1/E2)
        -> meter-masked   +0.281 at 0.98    (this check)
```

It is explicit, interpretable and history-derived: *which action last
changed the frame*.

**And it is cheap to key on.** `last_changer` has ~8 values (the actions
plus None). `n_reset` has ~400 and is strictly increasing within an attempt,
so H006's own note applies — keying a tally by it produces singletons, not
tallies, and it would have fragmented `by_action_given` below
`PREDICT_MIN_TRIES = 4` exactly as the conjunction fragmented in E1. **The
variable that survives the evidence is also the one that fits the
mechanism.** That is a coincidence worth not relying on, but it removes the
obstacle to the next step.

**Revised next step, now well-founded:** let the tally key carry
`last_changer`, admitted per game on the evidence the machinery already
computes. It must still pass the remaining links of the chain — downstream
consumer, then gameplay — before it means anything for score.

## DOWNSTREAM CONSUMER — `last_changer` FAILS, and H008's Z1 result is revealed as the meter

The third link of the chain. `last_changer` had passed discovery (+68.2 over
null), holdout (+0.234) and the meter-masked control (+0.281 at 98%
coverage) — all of which score a **frame-hash** target. The agent's actual
consumer is different: `predictor.rollout` forecasts **per-entity effects**
at k = 1/3/10. `scripts/h013_consumer.py` runs `latent_rollout.py`'s method
unchanged, with the variable swapped and H006's admit rule as the same bar
Z1 had to clear, and reports every number twice — all entities, and
excluding meter-like entities (thin bars).

| game | | k=1 | k=3 | k=10 |
|---|---|---|---|---|
| sk48 | base / **LC** / Z1 | 0.872 / **+0.000** / +0.000 | 0.763 / **+0.000** / +0.000 | 0.650 / **+0.000** / +0.000 |
| su15 | (no-meter) | 0.927 / **+0.000** / +0.000 | 0.873 / **+0.000** / +0.000 | 0.772 / **+0.000** / +0.000 |
| g50t | (no-meter) | 0.779 / **+0.000** / +0.000 | 0.541 / **+0.000** / +0.000 | 0.220 / **+0.000** / +0.000 |
| sc25 | (no-meter) | 0.865 / **+0.000** / +0.000 | 0.750 / **+0.000** / +0.000 | 0.656 / **+0.000** / +0.000 |

**`last_changer` fails the downstream-consumer link: +0.000 on every game,
every horizon, with and without the meter control.** It passed three filters
and does not improve the thing the agent actually uses.

Why, most likely: the effect table is *already keyed by the action being
taken*, and `last_changer` is largely redundant given the action. It
predicted frame hashes because knowing which action last changed things
correlates with whole-frame configuration; it adds nothing to "what will
ACTION2 do to entity 5". Stated as interpretation, not established.

### And the control result is the bigger finding

On g50t, **all** entities: Z1 gains +0.024 / +0.044 / **+0.055** at k=1/3/10.
That reproduces H008's headline — *"Z1 gains 2-7 points of k=10 accuracy on
5 of 10 aliased games"*. On the same game with meter-like entities excluded:
**+0.000 / +0.000 / +0.000**.

**H008's Z1 gain was the meter entity.** The variable was predicting the
quantised resource bar, which H006 characterised as real, deterministic and
**goal-irrelevant**, and the predictor scores every entity alike so it
counted as accuracy. Under the meter control it is exactly zero.

That makes three results retracted or qualified by the same confound in one
day — `n_reset`'s frame-hash lift, H008's k-step gain, and (differently) the
strip bbox of gate 2. The rule earned: **a predictive score is only about
the mechanic once the goal-irrelevant part of the target is removed.**

### Consequence

**Do not wire `last_changer`.** It fails the link that decides whether
wiring is worth anything, so the E3 finding ("there is no slot in the tally
key") no longer has a candidate worth building a slot for. Nothing in
families A-G has now passed the full chain on any game.

Caveat, stated: the negative is conditional on H006's admit rule (a function
on >= 3 points with >= 2 visits each). On these traces that rule admits
`last_changer` only for entities whose effect is constant, where the
override necessarily matches the baseline. A laxer rule might admit it
where it could matter — but relaxing the bar that Z1 cleared, in order to
rescue a candidate that failed at it, is exactly the move this project's
discipline exists to prevent. It would need its own hypothesis and its own
justification.
