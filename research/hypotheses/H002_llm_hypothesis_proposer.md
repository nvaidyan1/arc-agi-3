# H002: An intermittent LLM as hypothesis scientist, not controller

Status: IN PROGRESS — E-H002-2 (n=5 seeds) confirms the fixes generalise (55.9% valid rate); no score verdict yet, missing the matched non-LLM baseline
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
