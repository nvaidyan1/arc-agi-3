# H002: An intermittent LLM as hypothesis scientist, not controller

Status: IN PROGRESS — two free analyses from already-collected data found the clearest results in the whole thread: self-referential preconditions burn ~51% of their budget on unmet routing (vs 0% for proper third-entity ones), and a hand-authored oracle hypothesis for cd82 failed on 2 of 3 seeds when actually tested, directly confirming the schema's representation ceiling
Research question: RQ5 (compute-efficient reasoning) / RQ3 (active testing)
Date opened: 2026-09-14
Origin: council verdict step (c'); reviewer C §7, §8, §11, §28, §32 steps 3–4,
and the second note ("the LLM does not need to be in the action loop; it
needs to be in the hypothesis loop").

## Claim

A language model called *rarely* — at level start and after a run of
falsifications — that reads the brief and returns a few **structured,
falsifiable hypotheses** (precondition, action, target pair, predicted
change, falsifier, confidence) will propose bets the enumerator cannot,
in particular multi-factor rules like cd82's "paint from side −x while the
black swatch is selected", and the deterministic verifier will accept or
falsify them at no per-step model cost.

## Mechanism

```
brief text ──► LLMProposer.propose() ──► JSON ──► parse + validate ──► [Hypothesis]
                      │                                    │
                 client.complete()               reject: unknown entity,
                 (scripted | OpenAI-compatible    illegal action, unknown
                  base URL: Ollama / vLLM /       relation, no falsifier,
                  remote — interchangeable)       non-checkable prediction
                                                          │
                                            candidate pool ◄── enumerator
                                                          │
                                           experiment selector: the legal
                                           action that tests the most live
                                           hypotheses whose preconditions
                                           hold (discrimination), by
                                           confidence; verifier as before
```

The LLM never selects an action. Calls per level are capped; the same
`Hypothesis` type and verifier serve enumerated and proposed bets.

## Prediction

1. Schema validity ≥ 80% of returned hypotheses on the five oracle games.
2. On cd82, at least one proposed hypothesis names ACTION5 with a side
   precondition (or the swatch), and its verification outcomes differ from
   the enumerator's (fewer PRECONDITION_UNMET, more SUPPORTED/AGAINST).
3. Behaviourally: cd82 sweeps reaching L1 return toward the base 16/30
   with the proposer arm, without sp80/m0r0 losing — measured on the
   touched set at n=30, with model calls counted.

## Falsifier

- Valid-schema rate < 50%: the brief or the schema is unreadable to the model.
- Valid but never verified (SUPPORTED rate ≈ enumerator's or lower): the
  model adds vocabulary the world does not have.
- cd82 unchanged even with a correct-looking two-factor hypothesis: the
  bottleneck is arrangement/execution, not proposal.
- Score-per-call: if the model's gain disappears when calls are capped at
  the Kaggle time budget, the design is not deployable.

## Experiments

- E-H002-0: scripted client end-to-end (tests only) — parser, validator,
  selector, call policy.
- E-H002-1: five cold briefs → a real model → valid-schema rate, and read
  the hypotheses by eye (does anyone propose the two-factor cd82 rule?).
- E-H002-2: touched set n=30, base vs proposer vs proposer+LLM; calls per
  level, tokens, latency recorded.

## Metrics

valid_hypotheses / returned; verified / valid; PRECONDITION_UNMET share;
calls per level; latency; per-game L1 reach; touched-8 median.

## Status log

- 2026-09-14 opened. Interface built first with a scripted client, per the
  reviewer's staging; no model attached yet.
- 2026-09-14 E-H002-0 done: parser/validator (9 rejection reasons tested),
  call policy, pool + `select_experiment`, failure accounting; 214 tests.
  Smoke on sp80/cd82 with a dead server: degrades to the enumerator, 3
  warnings per level. Next: E-H002-1 needs a model runtime.
- 2026-09-14 E-H002-1 run. First attempt used `qwen3.5:4b` (Ollama) and
  failed outright: it is a "thinking" model, `think:false` is not honoured
  by this Ollama build's OpenAI-compatible endpoint, and generation does
  not terminate in bounded time (one probe reached 2,100+ reasoning tokens
  and was still going after 3+ minutes; the user independently saw a plain
  "hi" hang 5 minutes). Not a context-window or prompt problem — any
  `max_tokens` cap just truncates mid-thought with empty `content`. Switched
  to `gemma3:4b` (no thinking mode, `stop` token set) — first direct test
  came back in 5.1s (`think:false`) and 29.9s on the real proposer prompt,
  syntactically valid JSON.

  Five games (cd82, cn04, tu93, ka59, ar25), 400 steps, `ARC_PROPOSER=1
  ARC_LLM_PROPOSER=1 ARC_LLM_MODEL=gemma3:4b`, seed 8:

  | game | calls | returned | valid | valid-schema rate | closed (llm-sourced) |
  |---|---|---|---|---|---|
  | cd82 | 5 | 25 | 12 | 48% | 2 dropped live (action went illegal) |
  | cn04 | 2 | 10 | 0 | 0% | — |
  | tu93 | 2 | 6 | 5 | 83% | **5 tested, 5 falsified** |
  | ka59 | 3 | 11 | 0 | 0% | — |
  | ar25 | 3 | 11 | 0 | 0% | — |
  | **total** | **15** | **63** | **17** | **27%** | |

  Rejection reasons, summed: entity not on screen 18 (39% of all rejects —
  the dominant failure, not yet root-caused: hallucinated ids vs. reading
  stale ones from RECENT), action not legal or a bare click 11, no such
  pair in the relation records 8, precondition member not on screen 4,
  already holds 2, unparseable (malformed JSON, e.g. bare `#66` inside an
  array) 3. Mean latency 57.6s/call (34-80s range) — fine for a
  level-start/falsification-triggered cap of 3 calls/level, nowhere near
  usable per-step. cd82 and ar25 reached further levels this run (n=1,
  not a controlled comparison).

**Inference.** The reframed question (not "does it solve cd82" but "can it
propose hypotheses the enumerator wouldn't, and does the deterministic
machinery engage them") gets a real, if modest, yes: on tu93 all 5 valid
LLM hypotheses were pulled into the pool, selected, and falsified by the
same verifier the enumerator uses — the pipeline works end to end. On
cd82, valid hypotheses were generated but mostly never got a chance to be
tested (12 valid, only 2 ever closed, competing with the enumerator's own
bets for `HYPOTHESIS_POOL` slots) — a prioritisation gap, not a schema or
model failure, and an easy lever (favour model-sourced bets in
`select_experiment`, or guarantee at least one gets tested per level) if
this arm is developed further. No hypothesis anywhere in the 63 returned
named a precondition on another entity's state, confirming the earlier
diagnosis: **the precondition schema has no slot for it**
(`{adjacency, side, member}` only), so cd82's two-factor rule cannot be
stated in the current schema regardless of what the model infers from the
brief — this is a representation-language ceiling, not (yet) evidence
about the model's reasoning. `entity not on screen` at 39% of rejects is
the more actionable finding: worth reading a few raw rejected replies to
tell hallucination apart from stale-id confusion before spending more
calls on it.

**Not yet done.** Root-cause the `entity not on screen` rejections. A
scripted-oracle arm (hand-write cd82's real two-factor rule as a canned
reply) to separate "the model can't propose it" from "the schema can't
express it" — the schema gap above already answers this for the swatch
precondition specifically, but the same oracle would tell us whether the
verifier and selector actually *use* a correct hypothesis when handed one,
independent of the model. Then E-H002-2 (touched set, n=30, calls/tokens
counted) — deferred: this arm is not close to promotable yet given the
prioritisation gap above.
- 2026-09-14 both open items from the E-H002-1 writeup addressed:
  1. **Entity-id root cause found and fixed.** The raw replies show it was
     never hallucination: the model echoes the brief's own display
     notation (`"#5"`) back rather than the bare int the schema asks for,
     and sometimes leaves `b` null when only one entity seems relevant.
     `_ids`/`_one_id` in `agent/proposer_llm.py` now accept `"#5"`/`"5"`
     alongside `5` — a serialisation normalisation, not a loosening of the
     liveness check itself, which still requires an exact match against
     `live`. `SCHEMA_DOC` gained one worked example (a 4B model follows a
     concrete pattern far more reliably than a written rule) and states
     both fields are required.
  2. **Pool-priority fix.** `select_experiment` (`proposer_llm.py`) now
     tiebreaks toward an untested `source == "llm"` bet, placed after
     readiness/discrimination/batch-size (the structural criteria) and
     before confidence/lift (deliberately — the enumerator's "confidence"
     is its measured lift and the model's is self-reported, not a
     comparable scale, which is the other reason not to blend them).
  3. **New instrumentation**: `Proposer.evict()` / `evicted_by_source`
     counts a pool bet dropped because its entities left the screen,
     before ever being selected — distinct from `close()`, which only
     sees a verdict or an illegal-action drop. This was needed to answer
     which of two different problems the cd82 gap actually was: bets
     losing a selection contest (fixable in `select_experiment`, done
     above) or bets simply vanishing off-screen first (not fixable by
     reordering a selector at all). 3 new tests, 242 total.

  Re-ran cd82 and tu93 against the live model (same seed, same 400 steps)
  to check the fixes rather than assume them. Not a clean before/after —
  the priority fix changes which action gets taken, so the trajectory
  differs — but the direction is unambiguous: cd82 produced **zero**
  `"entity not on screen"` rejections (previously the largest category
  game-wide), and its 2 valid LLM hypotheses both received real verdicts
  (`falsified`, `expired`) with the evictions landing on *enumerator* bets
  instead (`evicted_by_source: {'enumerator': 5}`) — the reverse of the
  original run, where 12 valid LLM bets were generated and only 2 ever
  closed. tu93 stayed clean throughout (5/5 valid, 5/5 tested, no evictions).

**Not yet done.** A proper seed-paired re-run of the full 5-game E-H002-1
now that both fixes are in, to get a real before/after number rather than
a single-run directional check; the scripted-oracle arm to separate
verifier capability from proposal capability; extending the precondition
schema to name another entity's state, if the swatch-selection factor on
cd82 is still worth chasing once the arm above is further along.
- 2026-09-14 seed-paired rerun (same 5 games, same seed 8, both fixes in
  place) against the original E-H002-1 numbers:

  | game | calls | returned | valid | valid% before | valid% after | llm closed before | llm closed after |
  |---|---|---|---|---|---|---|---|
  | cd82 | 2 | 10 | 3 | 48% | 30% | 2 live (never verdicted) | **3/3: 2 falsified, 1 HELD** |
  | cn04 | 3 | 15 | 7 | 0% | 47% | — | 0/7 (not yet tested this run) |
  | tu93 | 1 | 5 | 5 | 83% | 100% | 5 falsified | 5 falsified |
  | ka59 | 3 | 15 | 3 | 0% | 20% | — | 2/3 falsified |
  | ar25 | 3 | 11 | 4 | 0% | 36% | — | 0/4 (not yet tested this run) |
  | **total** | **12** | **56** | **22** | **27%** | **39%** | 7/17 tested | 13/22 tested |

  `entity not on screen` (the dominant rejection, 18 of 46 before) fell to
  1 of 34. Not a clean ablation — the priority fix changes which action
  the agent takes, so this is a different trajectory through the same
  seed, not a frozen replay — but the direction and size of the change on
  every axis (valid rate, entity-id rejections, LLM bets actually tested)
  matches what the fixes were built to do.

  **A first**: one LLM-sourced hypothesis reached `HELD` on cd82 — a
  residual it bet on actually hit 0. First confirmed-correct LLM
  hypothesis recorded in this project.

  **A second format bug, not yet fixed**: `precondition not an object`
  (5 of 34 rejects, all on ka59) — the model writes `"precondition":
  "adjacency", "side": "+y"` as sibling keys at the item level instead of
  nesting `side` inside the `precondition` object as the schema asks.
  Same family as the entity-id bug (brief-notation vs. schema-notation
  mismatch); same fix shape would apply (lenient reconstruction in
  `parse_hypotheses`, not yet written).

**Inference.** The two fixes measurably worked, in the direction and
rough size predicted, on a real reproducible re-run. cd82's specific gap
(valid bets generated but never exercised) is closed for this game. cn04
and ar25 show the same generated-but-not-yet-tested pattern cd82 had —
worth watching whether it resolves given more steps/levels or is a
separate, still-open capacity question. The `HELD` result is one data
point, not evidence the model is reliably correct, but it is the first
proof the full pipeline (propose -> validate -> pool -> select -> verify
-> confirm) can complete end to end with a real model's output.
- 2026-09-14 **E-H002-2**: same 5 games as E-H002-1, seeds 1-5, 200-step
  cap (closed-loop-control check, not full-episode completion, per the
  user), `gemma3:4b`, both proposer fixes committed (`eaad22f`). 25 runs,
  2,523s wall (~42 min; matches the ETA given before launch).

  | | E-H002-1 (n=1) | E-H002-1 rerun (n=1, fixed) | **E-H002-2 (n=5, fixed)** |
  |---|---|---|---|
  | valid-schema rate | 27% | 39% | **55.9% (146/261)** |
  | calls | 15 | 12 | 57 (2.28/run) |

  Confirms the fixes generalise across seeds — not a lucky single rerun.
  Of 146 valid LLM hypotheses: 1 `held`, 78 `falsified`, 19 `expired`, 11
  still `live` at the 200-step cutoff, 8 evicted. LLM hit rate
  (`held/(held+falsified)`) = 1/79 = **1.3%**; the enumerator's own hit
  rate in the *same* sweep = 11/416 = **2.6%** — lower, same order of
  magnitude, on a system where most bets of either source get falsified
  by design (falsification-driven; a low hit rate is not itself evidence
  of bad reasoning). Gameplay: 3/25 runs reached level 1+ (cd82 0/5, cn04
  1/5, tu93 0/5, ka59 0/5, ar25 2/5).

  **No matched non-LLM baseline exists at these same seeds/games/steps.**
  E-7a's baseline numbers (cd82 2/30, etc.) are a different seed set and a
  different step cap (400) — not a valid pairing. This was flagged before
  the sweep and confirmed after: E-H002-2 cannot yet answer "does Gemma
  help the score," only "does the proposer mechanism work and generalise"
  (yes to the second question).

**Inference.** The mechanism question is answered: the pipeline
(propose → validate → pool → select → verify) works end to end and the
27%→39%→55.9% trend across three independent checks is real, not noise.
The score question remains genuinely open. Next: the matched baseline arm
(same seeds/games/steps, `ARC_PROPOSER=1` without the LLM) before any
score claim is defensible. Full context and a second external review in
`docs/plan.md` START HERE and `docs/expert-reviews/reviewer_c_09_14_2026b.md`.
- 2026-09-14 **matched baseline arm**: same 5 games, same seeds 1-5, same
  200-step cap, `ARC_PROPOSER=1` **without** the LLM — via `play_local.py`
  directly (not an ad hoc script), so git sha/flags/seed/config are
  captured automatically as a proper committed sweep summary this time.
  4m10s wall (vs. 42 min for the LLM arm — confirms the LLM call latency,
  not the game simulation, was the entire cost).

  Paired against E-H002-2 at the same seeds:

  | game | seed | baseline levels | llm levels | diff |
  |---|---|---|---|---|
  | cn04 | 2 | 0 | 1 | +1 (llm) |
  | ar25 | 1 | 0 | 1 | +1 (llm) |
  | ar25 | 4 | 1 | 0 | -1 (llm lost one the baseline had) |
  | ar25 | 5 | 1 | 2 | +1 (llm went one level deeper) |
  | *(other 21 of 25 cells)* | | *identical* | | 0 |

  20 of 25 seed×game pairs are identical between arms. Net: LLM arm
  reached level 1+ in 3/25 runs vs. baseline's 2/25 — one net additional
  run, with one gain partly offset by one loss on the same game (ar25).
  At n=5/game this is not distinguishable from ordinary run-to-run noise
  in either direction.

  **Known gap in this comparison**: `eh002_2.py` (the LLM-arm script)
  never queried the scorecard, so only `levels_completed` is compared,
  not `aggregate_score` (which the baseline arm has: 0, 0, 0, 0.046,
  0.228 by seed). A real score-level comparison needs the LLM arm re-run
  through `play_local.py` too, which would also close this gap for free
  going forward (see below).

**Inference.** The matched baseline this doc has been asking for now
exists, and the honest read is: **still no signal, in either direction,
at this sample size.** Not a failure of the fixes (mechanism metrics
E-H002-2 established stand on their own) and not evidence the LLM helps
the score. The fix for *this* gap is the same fix as the metadata-freeze
one: route the next LLM sweep through `play_local.py` directly (now that
it captures `llm_stats`/`llm_trace` automatically), at a larger n, rather
than another ad hoc script — that gets `aggregate_score` for both arms
for free and removes this exact comparison gap.
- 2026-09-14 **aggregate_score comparison** (closing the gap the baseline
  entry above flagged): the LLM arm re-run through `play_local.py`
  directly, same 5 games, same seeds 1-5, same 200-step cap, so
  `aggregate_score` exists for both arms this time.

  | seed | baseline score | llm score | diff |
  |---|---|---|---|
  | 1 | 0.0000 | 0.0497 | +0.0497 |
  | 2 | 0.0000 | 0.0427 | +0.0427 |
  | 3 | 0.0000 | 0.0214 | +0.0214 |
  | 4 | 0.0462 | 0.0000 | -0.0462 |
  | 5 | 0.2276 | 0.5487 | +0.3212 |

  Mean: baseline 0.0547 -> **llm 0.1325 (2.4x)**. Median: 0.0000 ->
  0.0427. LLM arm wins 4 of 5 seeds paired, loses 1 (seed 4, small).
  Exact sign-permutation test (n=5, the only valid test at this n, no
  distributional assumption): **p=0.25** — not significant by any
  conventional threshold; the smallest achievable two-sided p at n=5 with
  a clean sweep is 0.0625, so this reads as "consistent direction, not
  enough seeds to rule out chance" rather than either a positive or null
  result.

  Seed 5 drives a large share of the mean gain (ar25 reaching level 2
  under the LLM arm vs level 1 under baseline — matches the
  levels_completed table in the previous entry). Removing seed 5: mean
  diff over the remaining 4 becomes (0.0497+0.0427+0.0214-0.0462)/4 =
  +0.0169 — still positive on 3 of 4, much smaller. The result is not
  purely one outlier, but is not evenly spread either.

**Inference.** This is the first score-level (not just levels-completed)
comparison, and it updates the read from the previous entry: the
levels-completed table looked like noise (3/25 vs 2/25 across all games);
the score table — which is what the competition actually grades, and
rewards depth/speed rather than a binary level-reached — is directionally
consistent (4/5 seeds) though not statistically distinguishable from
chance at n=5. Not a claim that the LLM proposer helps the score. A
reason, that didn't exist before this sweep, to spend a larger n finding
out rather than deprioritising the arm.

**Sweep-retention note.** Both arms' sweep summaries (10 files: 5
baseline + 5 LLM, seeds 1-5) are kept together in `results/sweeps/`,
exceeding the usual "latest 5" retention — see `docs/plan.md` standing
rules for why: a matched-pair comparison needs both arms reproducible
from the committed record, and pruning either half would make this
result irreproducible from the repo alone.
- 2026-09-14 **n=10 extension** (seeds 6-10 added to both arms, same
  games/steps, via `play_local.py`):

  | seed | baseline | llm | diff |
  |---|---|---|---|
  | 6 | 0.0650 | 0.0650 | 0.0000 |
  | 7 | 0.1011 | 0.2469 | +0.1458 |
  | 8 | 0.0000 | 0.0397 | +0.0397 |
  | 9 | 0.0470 | 0.0470 | 0.0000 |
  | 10 | 0.0364 | 0.0000 | -0.0364 |

  Full n=10: mean baseline 0.0523 -> llm 0.1061 (2.0x); **median 0.0413 ->
  0.0448 — essentially unchanged.** 6 wins / 2 losses / 2 ties. Exact sign
  test p=0.125 (n=10; was 0.25 at n=5 — moved toward significance but not
  there). Exact Wilcoxon signed-rank (weights by magnitude) p=**0.193** —
  *less* significant than the sign test, because the losses (seeds 4, 10:
  -0.046, -0.036) are moderate while most of the wins are small; the mean
  is carried almost entirely by two standout runs (seeds 5 and 7: +0.32,
  +0.15 respectively).

**Inference.** Doubling n did not resolve this, and the specific way it
didn't is informative: a real, uniform effect should tighten the sign
test *and* the Wilcoxon together as n grows; instead the mean/median
divergence widened and the more sensitive test moved the *wrong* way.
That is the signature of a couple of good outlier runs sitting on top of
a flat or near-flat typical case, not a shift in the typical case itself.
**Not continuing to chase this via larger n** — the marginal information
per additional 40-minute sweep looks low, and reviewer C's own point 15
(policy integration / validation / credit assignment as more likely
bottlenecks than raw model reasoning) is a better next lever than a
bigger sample on the same comparison. Next: the replay-ablation
experiment (second review §14) using the traces already recorded from
these ten runs — no new sweeps required, and it separates generation
quality from integration quality, which a score comparison alone cannot.
- 2026-09-14/15 **replay-ablation harness** (`scripts/replay_ablation.py`,
  second review §14). Small addition on purpose: `ScriptedClient`
  (`agent/proposer_llm.py`) already replays a list of canned replies in
  order, and `LLMProposer.trace` (previous entry) already saves every
  call's exact raw reply into every sweep summary — this script is the
  plumbing joining the two, nothing more. Reads a saved sweep summary's
  `llm_trace` for one game, feeds the recorded replies through
  `ScriptedClient` instead of a live model, re-runs the same game/seed
  fully offline (no Ollama), and checks the outcome against what was
  originally recorded.

  Bundled in the same pass, prompted by re-reading reviewer C's bottleneck
  ranking (§15): `Proposer.log` (`agent/hypothesis.py`) now tags each
  closed hypothesis with its `source`, and `play_local.py`'s sweep summary
  carries the full log as `hypothesis_log`. Needed to check bottleneck #4
  ("exploration policy": is action budget spent reaching a hypothesis
  rather than the hypothesis being wrong) separately for LLM- vs
  enumerator-sourced bets — `closed_by_source`/`llm_stats` have status
  counts but not the per-hypothesis `spent`/`unmet` figures that question
  needs. Not yet analysed on real data (none of the twenty existing sweep
  summaries carry it — this capture is only live from here forward); the
  next LLM sweep will have it for free. 251 tests.

  **Stage 1 (reproducibility) run against five real recorded games**
  (ar25 seeds 1/3/5, cd82 from two different seeds; 3-4 calls each):
  **5 of 5 exact matches** on `levels_completed`, `actions`, `final_state`,
  and call count — every replay reached the identical outcome to the
  original live run, with zero model calls made. Confirms the pipeline
  is genuinely deterministic downstream of the model's output, which
  `recap.py`'s rerun-vs-replay docstring only asserted before this.

**Inference.** Stage 1 passing on every game tried is itself informative,
not just a sanity check cleared: it means any future counterfactual
replay (feed a hand-authored oracle reply, or only the `held` hypotheses,
through the same harness) can be trusted to isolate the effect of *what
the model said*, with no confound from hidden nondeterminism elsewhere in
the pipeline. **Not yet done**: Stage 2 — an actual counterfactual replay
(e.g. cd82's oracle two-factor rule) to separate generation quality from
integration quality, which is the point of building this at all.
- 2026-09-15 **the generation-quality fix.** Traced one real call in detail
  (ar25, level_step=20, 5 accepted hypotheses) and found every one of them
  claimed an unconditional "lever" for a pair the brief's own RELATIONS
  section explicitly marked `moves under every action alike` — the
  project's own phrase for `PairRecord.lever() is None`. The model wasn't
  malformed, it was fabricating groundedness: fluent, plausible-sounding
  justifications ("the strongest lever," "consistently moving") that
  contradict the evidence it was just shown, not extend it. One
  hypothesis was internally contradictory (claimed the pair was moving
  *apart* while predicting the distance would fall); another misread a
  single flagged `surprised` deviation from a 100%-flat baseline as a
  "consistent" trend.

  Fixed in `parse_hypotheses` (`agent/proposer_llm.py`): an unconditional
  hypothesis (`precondition: null`) is now rejected unless the pair's own
  tallies actually show a lever (`rec.lever(DOWN) is not None`) — the
  exact bar the enumerator already holds itself to (`Proposer.propose`
  never bets without one). A hypothesis *with* a stated precondition is
  exempt — that's the one case the model is allowed to say something the
  tallies don't already show (cd82's swatch-state factor is this shape),
  so nothing here narrows what the LLM can propose beyond the enumerator's
  reach, only what it can claim without new information. 254 tests.

  **Verified against the exact real failure, no new LLM calls needed** —
  replayed the recorded ar25 reply (same file as the original finding)
  through the fixed validator: all 5 fabricated hypotheses now rejected
  as `no unconditional lever for this pair`. The replay's trajectory then
  diverged from the original (levels_completed 2 -> 0 on this one seed,
  and 2 LLM calls consumed instead of 4) — expected, since removing bad
  pool entries changes what the agent actually does next, not just the
  accounting. **This is one data point, not a score verdict** — a real
  before/after read needs a matched-seed sweep, not an anecdote, and
  hasn't been run yet.

**Inference.** The fix does exactly what it was built to do: stop
ungrounded claims from entering the pool, at the same evidentiary
standard the enumerator already applies to itself. Whether *that*
improves the score is a separate, still-open question — the honest
position is this reduces noise in what the model contributes, and noise
reduction is not the same claim as improvement. **Not yet done**: a
proper matched-seed sweep with this fix in place, to see whether it
changes the outlier-driven pattern from the n=10 comparison; a
complementary prompt-side fix (explicitly explain "moves under every
action alike" in the schema/instructions) that would reduce how often
the model makes these claims in the first place rather than only
catching them after the fact — needs live model calls to verify, not
done here since the validator fix alone was verifiable for free.
- 2026-09-15 **matched-seed sweep with the fix** (same 5 games, same
  seeds 1-10, same 200-step cap as the n=10 comparison; only the code
  changed — the generation-quality fix from the previous entry):

  | | baseline | pre-fix llm | fixed llm |
  |---|---|---|---|
  | mean | 0.0523 | 0.1061 | **0.0817** |
  | median | 0.0413 | 0.0448 | **0.0182** |

  Fixed vs. pre-fix, directly (the actual test of the fix): mean diff
  **-0.0244**, 2 wins / 5 losses / 3 ties, sign p=0.156 — not
  significant, but leaning negative, not positive. Fixed vs. baseline:
  2 wins / 2 losses / **6 ties**, sign p=0.625 — the weakest signal of
  any comparison run this session.

  Mechanism-level totals confirm the fix fired at scale, not just on the
  one traced example: 131 `no unconditional lever` rejections across the
  fixed arm (444 total returned), valid-schema rate **47.1% -> 19.4%** —
  less than half as many hypotheses now enter the pool. Call counts
  stayed similar (107 vs 104), so `should_call`'s gating wasn't
  meaningfully disturbed.

**Inference.** The fix does what it was built to do, confirmed at scale:
cutting fabricated-justification content by more than half. It is not a
score win, and leans (not significantly) toward a small score cost.
Read honestly, not as "the fix is wrong" but as evidence the simple
story — bad content in, bad content out, remove it and things improve —
isn't what's happening. A plausible mechanism: even a hypothesis with a
fabricated "why" still names a real `(action, relation, pair)` triple,
falsified cheaply (budget 8) if wrong; if some of those "wrong
justification, plausible target" bets were functioning as exploration
diversity via the priority tiebreak (`select_experiment` favouring
untested LLM bets), rejecting them removes that diversity along with the
noise, not just the noise. **Not reverting** — the fix is correct on its
own terms regardless of score, and the score effect isn't significant
either direction. **Open question, not yet decided**: keep the strict
reject, or accept-but-downweight an ungrounded unconditional claim
instead of dropping it, to preserve some exploration diversity while
still not treating a fabricated justification as trustworthy content.
- 2026-09-15 **the alleviation, decided and shipped.** The open question
  from the previous entry (strict reject vs. downweight) resolved:
  reject was throwing away whatever exploration value the *target* of an
  ungrounded claim carried, even though its *justification* was
  fabricated. `parse_hypotheses` no longer rejects an unconditional claim
  with no lever — it tags it `source="llm_ungrounded"` (instead of
  `"llm"`) and keeps it in the pool. The whole mechanism is that one
  string: `select_experiment`'s untested-LLM priority tiebreak checks
  `source == "llm"` exactly, so an ungrounded bet no longer jumps the
  queue ahead of a well-evidenced enumerator bet on the strength of a
  fabricated "why" alone, but it is still live, still selectable, and
  still gets tested through the ordinary flow. `closed_by_source`/
  `evicted_by_source` (already keyed by `source`) now separate
  `llm_ungrounded` outcomes from `llm` ones for free, no new plumbing.
  `LLMProposer.stats["ungrounded"]` counts how many valid hypotheses
  were tagged this way, separate from `rejects`. `brief.py`'s "N from
  the model" count fixed to include ungrounded ones (`source.startswith
  ("llm")` instead of an exact match) so it doesn't undercount. 255
  tests.

  **Verified for free again**: replayed the same recorded ar25 reply
  through the softened validator. All 5 hypotheses that were rejected by
  the strict version are now accepted and tagged `llm_ungrounded`
  (`stats["ungrounded"]` = 6 across the call). Trajectory diverged from
  the original run again (expected, not a verdict) — not reading
  anything into this one seed given how much this session has already
  warned against exactly that.

**Inference.** The mechanism is exactly as designed and cheap to verify
without new LLM calls, same as every fix this session. **Not yet
matched-seed swept** — that is the next thing to actually do, not
optional: only a real n=10 comparison against both existing arms
(baseline, pre-fix llm, strict-reject fixed llm) tells us whether
downweighting recovers the lost exploration value without also
reintroducing the fabricated-justification problem the strict fix
correctly solved.
- 2026-09-15 **the softened fix, matched-seed swept** (same 5 games,
  same seeds 1-10, same 200-step cap as every arm in this thread):

  | arm | mean | median | nonzero seeds | max |
  |---|---|---|---|---|
  | baseline | 0.0523 | 0.0413 | 6/10 | 0.2276 |
  | pre-fix llm | 0.1061 | 0.0448 | 8/10 | 0.5487 |
  | strict-reject | 0.0817 | 0.0182 | 5/10 | 0.5487 |
  | soft (alleviated) | 0.0761 | **0.0704** | 6/10 | 0.2276 |

  Sign test / Wilcoxon (magnitude-weighted), pairwise: soft vs baseline
  p=0.28/0.31; soft vs pre-fix p=0.55/0.74; **soft vs strict p=0.94/0.81
  — the closest to an exact coin flip in this whole investigation**;
  strict vs pre-fix (recorded previously) p=0.16/0.16. **None significant.**

  The one interpretable pattern, held to a "suggestive" standard given
  none of this reaches significance: soft has the highest median of all
  four arms, but its max drops back to exactly baseline's ceiling
  (0.2276) — both LLM arms before it hit 0.5487 on seed 5's outlier, and
  softening lost that specific spike while becoming more consistent
  elsewhere (6/10 nonzero seeds vs. strict's 5/10). Consistent with
  "traded an occasional big win for broader small ones," not proof of it.

**Inference.** Four n=10 sweeps on this one axis (baseline, pre-fix,
strict, soft) and zero significant pairwise differences. Diminishing
returns from continuing to sweep at this n — a fifth arm or a larger n
on the same comparison is unlikely to be the efficient next move.
**Recommending a pause on score sweeps here**, in favour of the cheaper
analyses already queued in `docs/plan.md` that use data these four sweeps
already collected (`llm_trace`, `hypothesis_log`) without any new LLM
calls: Stage 2 of the replay-ablation, and the bottleneck-#4
`unmet`/`spent` check. Left for the user's call whether to keep pushing
n on score instead.
- 2026-09-15 **bottleneck #4, checked** (second review §15, "exploration
  policy": is action budget spent reaching a hypothesis rather than the
  hypothesis being wrong) — using `hypothesis_log` from the strict and
  soft arms, no new sweep. Restricted to hypotheses that actually carry
  a precondition (only those can ever record an `unmet` step):

  | source | conditional bets | spent | unmet | unmet/spent |
  |---|---|---|---|---|
  | enumerator (strict arm) | 352 | 1494 | 0 | 0.0% |
  | llm (strict arm) | 4 | 15 | 7 | 46.7% |
  | enumerator (soft arm) | 444 | 2110 | 0 | 0.0% |
  | llm (soft arm) | 13 | 57 | 22 | 38.6% |

  The enumerator's conditional bets never waste a step on an unmet
  precondition, across nearly 800 closed conditional hypotheses total.
  The LLM's do, roughly 40-47% of the time. Traced further: **12 of 17
  LLM conditional hypotheses across both arms name a precondition
  `member` that is one of the relation's own two entities** — e.g.
  `distance(2,4)` with a precondition on being adjacent to `#2` itself,
  rather than a genuine third reference entity. Split by this:

  | precondition shape | n | spent | unmet | unmet/spent |
  |---|---|---|---|---|
  | self-referential (member ∈ pair) | 12 | 57 | 29 | **50.9%** |
  | third-entity (member ∉ pair) | 5 | 15 | 0 | **0.0%** |

  The largest, cleanest effect size found anywhere in this whole
  investigation — far larger than any score comparison. When the model
  names a real third entity, routing succeeds every time, matching the
  enumerator. When it names one of the hypothesis's own two entities
  (71% of the time), roughly half its budget burns on failed routing
  before ever testing the claim.

  **Not yet fixed.** The validator currently only checks that a
  precondition's `member` is live and isn't the controlled thing — not
  that it differs from the relation's own `a`/`b`. A cheap next fix,
  same shape as the lever-grounding one: flag or reject a self-
  referential precondition, or at minimum tag it so `select_experiment`
  treats it the way `llm_ungrounded` bets are treated now.

- 2026-09-15 **Stage 2 of the replay-ablation: the actual counterfactual,
  finally run.** Hand-authored an oracle hypothesis for cd82 from the
  project's own best existing knowledge (H001's "ACTION5, adjacent side
  -x" finding) — a real, schema-valid claim about `part_size_diff`
  between the bucket group and the template group, using real entity ids
  read from an actual recorded brief. Replayed it (via
  `scripts/replay_ablation.py`'s `replay()`, bypassing the recorded
  reply) against three different cd82 seeds:

  | seed | outcome |
  |---|---|
  | 1 | levels=1 (up from 0); oracle bet never closed — pool wiped before it was ever tested |
  | 2 | levels=0, GAME_OVER; oracle bet **expired**, 7 of 8 budget steps `unmet` |
  | 3 | levels=0, GAME_OVER; oracle bet **falsified**, tested properly, residual never moved (35->35) |

  For context: `cd82` reached level 1 in **zero** of the ~30 real
  gemma3-driven and baseline runs recorded this session, so seed 1's
  level-up is a genuine anomaly worth noting — but the oracle bet was
  never closed there either, so it cannot be attributed to the
  hypothesis being exploited; more likely ordinary trajectory divergence
  from a different pool composition, the same effect seen in every
  fix-vs-fix comparison this session.

**Inference.** This is the cleanest, most conclusive result in the
entire H002 thread, and it is a negative result for the oracle, not a
positive one — which is exactly what makes it valuable. A hand-crafted
hypothesis built from the project's own strongest prior evidence still
failed when tested on 2 of 3 seeds. That is direct, causal confirmation
(not inference from absence) of what the project already suspected:
cd82's real rule is two-factor (side x selected paint colour), the
precondition schema can express only the first factor, and no amount of
generation or integration improvement changes that — the ceiling is
representational. The bottleneck-#4 finding is the more broadly
actionable one: self-referential preconditions are a large, clean,
fixable defect (50.9% vs 0.0% unmet), independent of cd82's specific
ceiling, and worth fixing before spending more calls on this thread.
