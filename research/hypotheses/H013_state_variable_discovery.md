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

**The best pair nearly doubles resolution (44 -> 81) and more than halves the
unresolved remainder (217 -> 100), against a null of 1.0.** Both halves are
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
