# H005: Conjunctive preconditions — carrying a two-factor rule intact

Status: IN PROGRESS — Stage 1 (representation + tests) built and green; Stage 3 (cd82 oracle replay) run on 3 seeds, mechanism confirmed, the anticipated condition-kind gap found; Stage 2 (historical replay) and Stage 4 (matched-seed) still open
Research question: RQ2 (predictive world modelling) / RQ3 (active testing)
Date opened: 2026-09-15
Origin: a third reviewer-C pass narrowed to one concrete, evidence-backed
gap (`docs/expert-reviews/reviewer_c_09_14_2026c.md`), read against
`H001`'s cd82 oracle finding and the two prior attempts this reframing
would otherwise have collided with or ignored: `H003` (predictor — the
missing primitive was named as state-dependent geometry, not more
vocabulary) and `H004` (rival hypotheses — the first behavioural result
was mixed and not cleanly seed-paired). H005 is scoped narrower than the
proposal that opened this thread specifically because of those two.

## Claim

`Hypothesis.precondition` has only ever carried one `(cond, member)` pair
— the controlled thing must be adjacent (optionally on a stated side) to
one named entity. `H001`'s Stage-2 oracle replay proved this is
insufficient for cd82: the strongest hand-authored hypothesis available
(adjacent, side −x) could not also express the rule's second factor (the
state of which paint swatch is selected) because the schema has no slot
for a second condition, and that oracle still failed on 2 of 3 seeds
tested. Improving the proposer cannot fix a representation that cannot
hold the complete rule.

**Extend `precondition` to optionally carry several conditions,
interpreted conjunctively** — every named condition must hold — without
introducing a new condition *kind*, a semantic ontology, or a change to
the enumerator, the LLM schema, the predictor, or experiment selection.
The only question this stage answers:

> Can the existing system represent, validate, test, and exploit a
> hypothesis with two or more grounded simultaneous conditions?

Score is deliberately not the primary criterion (see Predictions, P4).

## Why this is scoped narrower than the reframing that opened it

The council-style proposal that prompted this doc bundled three
interventions: richer (compositional) hypotheses, information-directed
experiment selection, and a predictive model loop with prediction-error-
driven refinement. Two of those already have a name and a result in this
project:

- **The predictive model loop is `H003`** (`agent/predictor.py`). Already
  built: one-step forecast scored against what happens. Its own finding
  was that the largest gap is state-dependent geometry — an argument for
  making *position* the next primitive, not for assuming a richer
  hypothesis language is the fix.
- **Discriminative/information-directed experiment selection is `H004`**
  (`agent/hypothesis.py`, rival general/specific bets, `select_experiment`
  preferring a discriminating press). Already built and tested against
  E-7a on cd82: mechanism fires as designed, behavioural read mixed, and
  the comparison was never cleanly seed-paired against its baseline.

Reopening either under a new name, without reconciling why the first
attempt didn't cleanly land, would not be a new experiment. What *is*
new and has a direct measured gap behind it — not a hypothesis about a
gap — is representational: the oracle failure is causal, not inferred.
That is the one piece this doc builds. H003 and H004 are treated as
existing evidence that constrains the design (don't touch the predictor
or experiment selector; the oracle test, not a live sweep, is the first
real exercise of this), not as untried ideas.

## Evidence

**E1 — the cd82 oracle failure** (`H002` log, `docs/history.md`
2026-09-15 "Stage 2 of the replay-ablation..."). A hand-authored
hypothesis using the project's strongest existing finding (adjacent,
side −x) was replayed against three recorded seeds: level 1 reached but
the bet never closed (seed 1), expired 7-of-8 unmet (seed 2), tested and
falsified (seed 3). cd82 reached level 1 in zero of the ~30 real runs
recorded that session. This establishes only the narrow claim that the
representation cannot express the complete rule — not that a second
condition would solve cd82 (the second factor, "which swatch is
selected," is itself an open question about *what kind* of condition it
even is; see Scope below).

**E2 — H003's finding.** The predictor's own gap analysis named
state-dependent geometry, not insufficient vocabulary, as the largest
source of forecast error. H005 therefore keeps the predictor untouched
and treats this as a reason to expect a modest, not transformative,
effect from representation alone.

**E3 — H004's finding.** Discriminative experiment selection already
exists and its first score-level test was mixed and confounded (not
seed-paired). H005 does not add a second discrimination mechanism; it
reuses `select_experiment`/`diverges` exactly as they stand, which
already read `h.precondition` only for presence, not shape — see below.

## What was built (Stage 1)

`Hypothesis.precondition` keeps its name and its existing single-pair
shape for every current producer — **the enumerator and the LLM parser
are byte-for-byte unchanged**, so this is purely a consumer-side
generalisation:

```python
def conditions_of(precondition) -> tuple:
    """None/() -> (); a bare (cond, member) pair -> (that pair,); an
    already-multi tuple -> itself. The one place that understands both
    shapes, so no proposer needs to know which one it's building."""

def describe_conditions(precondition, exclusive=False) -> str:
    """"" / " when X of #7" / " when X of #7 and Y of #12"."""
```

Every place that only *checked presence* (`h.precondition is None`, in
`Hypothesis.forecast`/`rival`, `select_experiment`, `diverges`) needed no
change — a multi-condition precondition is still truthy and not-`None`.
Only the places that *indexed into* the pair changed:

- `Hypothesis.describe()` and `brief.py`'s hypothesis-log rendering now
  call `describe_conditions`.
- `MyAgent._precondition_met` now conjoins `_condition_met(cond, member)`
  (the exact per-condition body that used to be `_precondition_met`
  itself) over every pair in `conditions_of(h.precondition)`.
- `MyAgent._hypothesis_action`'s routing now finds the *first still-
  unmet* condition, in the order they were given, and routes to that one
  — one step can only close the distance to one target, so a hypothesis
  with two unmet conditions satisfies them in sequence, same as it would
  discovering a second condition after routing to the first.

`agent/proposer_llm.py` and `agent/hypothesis.py`'s `Proposer` (the
enumerator) are **untouched** — neither the LLM schema nor the
conditional-lever tallying changed, matching the explicit scope below.

**Tests** (`tests/test_hypothesis.py`): `conditions_of`/`describe_conditions`
against every shape (`None`, `()`, a bare pair, a multi-tuple); `describe()`
rendering a two-condition precondition; and — since `_precondition_met`/
`_condition_met` had **no prior unit coverage at all** (this layer has
only ever been validated through live/replayed games, consistent with
this project's existing test boundary of perception/navigation/control/
constraints, not the decision layer) — a minimal harness
(`object.__new__(MyAgent)` plus a `SimpleNamespace` for `regions`, the
same pattern `_agent_with` already uses) proving the AND: one condition
met and one far away reads `False`; moving the far entity adjacent flips
it to `True`. **261/261 tests pass, including all 257 that predate this
change** — zero behavioural change for every existing single- or no-
condition hypothesis.

## Scope

**In scope (this stage):** multiple conditions of the *existing*
adjacency/side/member shape, conjunction only, grounding unchanged
(whatever a single condition already required), serialisation (the
`hypothesis_log` tuple carries whatever shape `h.precondition` holds,
already exercised by `describe_conditions`), routing to satisfy several
conditions in sequence.

**Explicitly out of scope:** OR/NOT/nested logic, temporal logic, a new
condition *kind* (e.g. "entity X is in state Y" as distinct from
adjacency — cd82's real second factor, "which swatch is selected," may
turn out to need exactly this, which Stage 3 below will show empirically
rather than assume), new semantic entity types, changing the LLM
model/prompt/schema, changing `H003`'s predictor, changing `H004`'s
experiment selection or the enumerator's own conditional-lever tallying,
changing exploration policy.

If Stage 3 shows the oracle needs a condition kind this stage doesn't
have, that is a finding (E1 already half-predicted it: "which swatch is
selected" is a *state* fact, not obviously an *adjacency* fact), not a
failure of Stage 1 — it would mean the conjunctive plumbing built here
is necessary but not sufficient, and would motivate a distinct, smaller
follow-up (a second condition kind) rather than a bigger one.

## Predictions

- **P1 (representational).** A hand-built two-condition hypothesis can
  be constructed, described, logged, and carried through
  propose → test → close without special-case code. (Testable now —
  Stage 1's tests already exercise this at the unit level; Stage 3 is
  the live-game version.)
- **P2 (mechanism).** `_precondition_met`'s conjunction and the routing
  order require no changes to `H004`'s rival mechanism or
  `select_experiment` — both already treat `precondition` as
  presence-only. (Confirmed by Stage 1: zero lines changed in either.)
- **P3 (behavioural).** On a game with a genuine multi-factor mechanism,
  routing spends its steps satisfying conditions in a legible sequence
  rather than looping on one it can never satisfy alone.
- **P4 (score — weakest, not required).** If representational
  insufficiency materially limits cd82, a hand-authored two-condition
  oracle should behave differently (not necessarily better — see Stage
  3) than the one-condition oracle already tested. A null result here is
  still informative: it would mean the bottleneck is elsewhere, per the
  Failure criteria below.

## Evaluation stages

1. **Unit/mechanism tests — DONE.** See "What was built" above. 261/261
   green, 4 new tests targeting exactly the conjunction and the
   normalization helpers.

3. **cd82 oracle replay — DONE (out of order; answered before Stage 2
   below, since it needed no new LLM/data-mining work and settles the
   more important question first).** `scripts/h005_cd82_oracle.py`: no LLM,
   no parser — a hand-built two-condition `Hypothesis` is injected
   directly into `agent.hypothesis` after 20 steps (long enough that its
   target entities are confirmed live), bypassing the schema entirely
   since it was deliberately not extended this stage. Key
   `("part_size_diff", (0,1,5,6), (8,9))` (template vs. bucket/block, the
   same relation `H001`'s oracle used); precondition
   `(("adjacent:-x", 0), ("adjacent", 3))` — condition 1 is `H001`'s
   finding verbatim (template, side −x); condition 2 is *not* an attempt
   to correctly encode "swatch is selected" (a persistent state fact) —
   it is the cheapest test of the conjunction machinery available this
   stage: adjacency to a second real entity, `#3`, one member of the
   strip/swatch group. Entity ids read from an actual run (same method
   `H001`'s Stage 2 used) and confirmed identical across seeds 1-3 at
   this early a step.

   Ran on seeds 1-3 (matching `H001`'s Stage 2 seed count):

   | seed | oracle status | met/8 steps | history | levels | score |
   |---|---|---|---|---|---|
   | 1 | expired | 0/8 | all `None` | 1 | 0.6235 |
   | 2 | expired | 1/8 | `[34, None×7]` (fell) | 0 | 0.0000 |
   | 3 | expired | 1/8 | `[35, None×7]` (rose) | 0 | 0.0000 |

   **Mechanism (P1, P2): confirmed.** The two-condition hypothesis was
   built, injected, described (`"...when adjacent on side -x of #0 and
   adjacent of #3..."`), and its conjunction gated correctly — on seeds
   2 and 3 exactly one step found *both* conditions met simultaneously,
   and only that step was scored as real evidence (a residual move, down
   on seed 2 and up on seed 3); every other step correctly recorded as
   precondition-unmet, costing budget without being treated as evidence.
   The full two-condition precondition survived `close()`/logging intact
   on seeds 2 and 3 (seed 1's log entry itself didn't survive to the end
   of the episode only because `Proposer.clear()` runs on every level
   transition and seed 1 reached level 1 — a pre-existing, unrelated
   behavior of `proposer.log`, not a defect in this change; the oracle's
   own `.status`/`.history` still confirm it expired correctly).

   **The anticipated condition-kind gap: confirmed, exactly as the Scope
   section predicted.** The conjunction was almost never jointly
   satisfiable — the template and the swatch are in different screen
   regions, so being simultaneously adjacent to both is geometrically
   rare. This is direct evidence that "adjacency to the swatch" is the
   wrong proxy for "the swatch is selected": selection is plausibly a
   persistent state set by an earlier click, not a fact about where the
   controlled thing is standing right now. Confirms, rather than assumes,
   that solving cd82 for real needs a second condition *kind* (a state/
   attribute check, not another adjacency), which this stage deliberately
   did not build.

   **Score note, read cautiously.** Seed 1 reached level 1 — cd82's
   first level-1 clear anywhere in this session's ~30+ recorded runs.
   Not attributed to the oracle succeeding (it expired unmet on all 8
   steps): more likely the injection perturbed the first ~20-28 steps'
   trajectory, same sensitivity-to-early-perturbation this project has
   documented all session on the LLM side (Case D, the matched-seed
   arms). One seed is exactly the sample size this project's own
   protocol says not to read anything into.

2. **Historical replay — OPEN, and limited by construction.** Feed
   existing recorded LLM outputs through the new representation. Caveat
   worth stating up front: the *old* schema never let the model emit a
   second precondition object, so this can at best surface *felt need*
   (a `why` field gesturing at a second qualifier it had nowhere to put)
   — not literal multi-condition JSON, since none exists yet. Lower
   priority now that Stage 3 has already answered the mechanism question
   directly.

4. **Small matched evaluation — OPEN, and now a different question than
   originally scoped.** Stage 3 already shows this stage's condition kind
   (adjacency-only conjunction) is not the fix for cd82 specifically — a
   matched-seed sweep of *this* oracle would mostly be re-measuring
   trajectory-perturbation noise (seed 1's level-1 clear vs. seeds 2-3's
   zero), not a representation effect. The better next step Stage 3
   points at directly: a second condition *kind* — a persistent
   entity-state check ("is `#S`'s current descriptor equal to its
   'selected' appearance", answerable the same falsifiable way
   `kinds.py`'s equal-descriptor view already works) rather than another
   adjacency — is its own, smaller follow-up, not a bigger sweep of what
   Stage 1 already built.

## Success criteria

Primary: a multi-factor rule that could not be expressed before can now
be represented, validated, tested, logged, and replayed intact through
the existing machinery (Stage 1: done at the unit level; Stage 3: the
live-game version). Secondary: the cd82 oracle can express and test its
complete two-factor mechanism, whatever condition kind that turns out to
require. Only after both should score become the question, per P4.

## Failure criteria

Reconsider this direction if: the representation carries the rule but
`H003`'s predictor or `H004`'s experiment selection can't evaluate/use it
(neither was touched, so this would be a real gap, not a regression);
multi-condition hypotheses are too hard to ground reliably once a second
condition *kind* is added; Stage 3 needs a condition kind so different
from adjacency that "conjunction of the same shape" was the wrong
generalisation entirely; or Stage 3 passes mechanically but produces no
behavioural change, which would relocate the bottleneck downstream of
representation — informative either way, not a wasted stage.

## Experimental discipline

Same rule as everywhere else in this project's H00x line: this is one
isolated intervention. A later positive or negative result should not be
read as evidence about H003, H004, the LLM proposer, or exploration
policy unless those are the thing that actually changed. `agent/`
untouched here beyond the specific lines in "What was built" — no sweep
was frozen out by this work since none was running.
