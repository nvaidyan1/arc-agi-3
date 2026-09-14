# Council — 2026-09-14 — the next step toward a hypothesis-priming belief

Five independent advisors (Contrarian, First Principles, Expansionist,
Outsider, Executor), five anonymised peer reviews, one chairman. Method after
Karpathy's LLM Council. Recorded in full because the verdict overruled two
things the project had already agreed to build, and the reasoning is the
record of why. The operative summary is in `plan.md` ("NEXT"); this file is
the evidence behind it.

## The question, as framed

What is the next step toward a belief representation rich enough to prime
goal-hypothesis generation? Given: the governing principle (no semantic slots
without evidence; None is a first-class outcome), the measurement discipline
(n>=30, medians, permutation test, check reach first), what exists (entities
with identity, move/obstacle maps, sawtooth detector, interest map, router,
per-entity Belief with a cell-change vocabulary and roles by contrast and by
determinism), and the gap measured by dumping cd82's full belief: no
composites, no RECOLOUR event, no constant-distance relation, no binary
relations at all. The agreed direction before the council: objects with parts
grouped on evidence (co-motion / enclosure / cell exchange), invariant
descriptors, seven binary relations over all live pairs (`same_palette`,
`similar_shape`, `contains`, `adjacent`, `constant_distance`, `count_match`,
`distinguished`), an event log, hypotheses as checkable predicates with a
progress measure, an enumerator over "make R(A,B) hold" then a per-episode
LLM. Order: identity (done), control (done), composites+RECOLOURED,
relations+event log, hypothesis interface.

Asked: (a) composites first or relations first; (b) the minimal relation set
that lets template-matching be *proposed* without being *encoded*, and the
prior-smuggling risks; (c) a progress measure checkable in a few frames and
general across navigational / constructive / matching families; (d) the most
likely failure on unseen games and a cheap early probe; (e) anything in the
agreed representation that violates the governing principle.

## Advisors

**Contrarian.** Two build steps are done and no score was quoted: the gap was
found by reading a dump, which is aesthetic falsification, not measured. The
relation library *is* the goal library — an enumerator over R x pairs can only
propose goals R can express — so the prior has already been smuggled, from a
data structure into source code, where the discipline cannot see it.
`distinguished` is salience with no falsifiable test; cut. `ORBITS`: cut the
name, keep the scalar. Scale-invariant outline signatures presume 2x is the
same object; on a grid it is not. The existing stamina detector is already a
semantic slot ("sawtooth that refills on reset" = HP/fuel/timer) that passed
because its test was written first and called evidence. Most likely death:
rewards are sparse and level-gated, and a progress measure assumes a dense
monotone residual exists. Probe: at every level-transition frame in existing
logs, walk back 10 steps and ask whether any computable scalar was monotone
into it. Build the scorer before the thing being scored.

**First Principles.** Wrong question: richness is not the bottleneck. cd82's
dump was already too large to act on; more relations make the *selection*
problem worse. The environment gives exactly one certified signal — score and
level increments — so build the belief backwards from score events, not
forwards from pixels. `StepRecord{t, action, arg, entity_deltas, score, level,
frame_hash}`; a `ScoreEvent` is where score or level changed; enumerate
descriptors only inside the k=8 frames before one. A goal hypothesis is a
predicate that was False or None through the window and True at the event —
template-matching falls out as the one predicate that flipped, never encoded.
Do not design a progress measure: auto-generate scalars and keep those
monotone across >=2 independent windows. Type error: relations returning
"mostly false" is a bug; undetermined must be None. Probe: score-event rate per
1000 steps per game from existing logs; if <50% of games have an intra-level
event, the certifier must be novelty (first-visit frame hashes), a different
build.

**Expansionist.** Relations first because relations *subsume* grouping:
co-motion is a constant offset held over k frames, cell exchange is a binary
relation, enclosure is `contains`; composites fall out as union-find over
relations that persist — step 3 is duplicated machinery. Relations return a
scalar distance, not a bool; a hypothesis is "coordinate i -> 0", checkable in
three frames by the sign of the delta; family-general for free. The undervalued
asset: the **level-boundary diff** — every level advance is a free,
unbaked, per-episode ground-truth label of what the goal was; the coordinates
that collapsed between t-1 and t are the answer. Failure: temporal goals
(ordering, timing) leave the relation vector flat. Probe: replay existing logs
through the engine and count coordinates with variance above the noise floor.

**Outsider.** The whole "sufficient representation" was derived from one
game; its relations are cd82's features with generic names, and renaming
template-matching as "make same_palette hold" hides the prior inside the
vocabulary. Derive the relation set from a *second* game's dump and keep only
the intersection. Composites are not falsifiable and should be cut: a relation
can return None or False, but a partition has no observation that says "this
grouping is wrong". Keep grouping as relations over flat entities; parts are an
emergent read, never a stored node. Every relation must ship a distance
function or it cannot seed a goal; relations with no distance are diagnostics.
Failure is combinatorial: |R| x N^2 proposals, almost all false forever, none
reachable in budget. Probe: log the relation matrix per step; count flips,
action-attributable flips, and flips within 5 steps of a level advance — if the
last is near zero, relations are decoration.

**Executor.** Relations first: grouping changes entity ids, which changes the
tracker, belief keys, move model and all 140 tests; relations are a pure
function of the existing entity list, zero blast radius, runnable offline over
recordings before touching the policy. Every relation returns a *residual*,
`int | None`, 0 == holds, None == undecidable (ghost, history < 2 frames,
appeared this step). Six: `palette_diff` (|symmetric difference|),
`cell_exchange` (cells a lost this step that b gained), `shape_diff` (0 if
equal else None — thresholds are priors), `containment` (cells of b outside a's
bbox), `distance_drift`, `count_diff`. Progress *is* the residual decreasing
over k=5 frames. The smuggling risk is cellwise comparison after alignment —
that IS template-matching: keep residuals set-cardinality and counting only,
**never align two grids**. Cut `ORBITS`, `similar_shape`, `part_count`.
Composites = `cell_exchange` persisting, free by step 5.

## Peer review (anonymised; A=Executor B=Contrarian C=Outsider D=Expansionist E=First Principles)

Strongest: A (3 reviews) for being both epistemically clean and shippable —
residual-not-bool, "never align two grids", blast radius argued from the code;
D (2) for the level-boundary diff and for dissolving (a) constructively; E (1)
for being the only one to question the premise. Biggest blind spot: B (3) —
the best single hit (the stamina slot) but no buildable step, and an exit gate
("median score beats the no-hypothesis arm") whose instrument has no power for
a representation change; A (2) — never engages "cd82 read backwards", and its
probe ("a residual ever changes") passes on pure noise because
`distance_drift` moves whenever anything translates.

What all five missed, named by the reviewers: **actuation** — a moving
residual changes no policy; the existing per-action change tallies should be
extended to relation coordinates (`action -> delta residual`) as the credit
assignment. Goals plausibly change per level within a game, which D's
compounding claim assumes away. Every probe is passive replay; nothing
proposes an intervention to make an undecidable residual decide. ACTION6 has
4096 targets, so the proposal space is pairs x relations x targets, gated by
reachability. Hypothesis tests cost actions from the depth-weighted budget and
nobody priced one. Nobody designed the serialisation the LLM proposer would
actually read.

## Verdict (chairman)

**Agreed 5/5.** Relations before composites, with composites falling out as a
persisting relation rather than a node type. Residual not bool, `int | None`,
undetermined is None never False. The residual is the progress measure.
Cut the semantic names (`ORBITS`, `distinguished`/`odd_one_out`,
`similar_shape`, `part_count`; stamina -> `sawtooth_region`). Probe before
build.

**Clashes resolved.** Contrarian's "no score moved, stop" — rejected: an agent
that cannot represent the goal cannot produce a score delta, so a flat score
is the predicted observation; keep the discipline, change the instrument.
"cd82 read backwards" — upheld, with the Outsider's operational fix: derive
the relation set from a second game and ship the intersection. Normalised
shape/Jaccard signatures — cut, they are thresholds re-entering as floats.
"Never align two grids" — upheld as the sharpest smuggling rule given.

**Recommendation.** The Executor's engine, aimed by First Principles'
windows, supervised by the Expansionist's boundary diff. (1) `relations.py`,
offline, no policy change, six residuals over all live pairs including ghosts,
no ranking by "looks like a goal". (2) The probe, gating everything after it.
(3) Event log of every residual that moved plus `action -> delta residual`;
exit: cd82 shows `palette_diff(block, template): 2 -> 1` attributable to a
paint action. (4) Level-boundary diff as supervisor: only residuals that
collapsed at >=2 independent boundaries are admissible targets; a hypothesis
is admissible only if its residual is finite and strictly decreased at least
once in the last 5 steps under our own action. (5) Enumerator, then LLM;
design the serialisation the proposer reads before writing the proposer.
**Composites are never built** — a partition has no falsifier.

**The one thing first.** `scripts/probe_relations.py`: replay recordings
through the engine, no agent change. Per game count (i) pairs whose residual
ever changes, (ii) changes attributable to an action, (iii) residuals monotone
over the 8 frames into a level advance. Exit, all three: >=15/25 games with a
moving residual; >=3 games with >=1 action-attributable change per episode;
**>=50% of level advances preceded by a monotone-decreasing residual.** (iii)
is the real gate; if it fails the fallback is novelty certification over
first-visit frame hashes, a different build. Also emit the pairs stuck at
None: that list is the first intervention queue.

## What the project changed in response

See `plan.md` "NEXT". Step 3 (composites) deleted rather than deferred; step 4
becomes residual-valued relations behind a probe gate; the relation set must
be derived from a second game's dump; the level-boundary diff becomes the
supervision signal; `action -> delta residual` becomes the actuation bridge;
the LLM serialisation is designed before the proposer. One practical
prerequisite the council's probe assumes and the recordings lacked: frames.
