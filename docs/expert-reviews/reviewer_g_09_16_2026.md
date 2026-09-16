**PI plan: next experiments from the current H00* state**

You are correctly shifting from pure representation work into making beliefs produce actionable, falsifiable hypotheses that get tested with a controlled amount of exploration. The recent series already gives a clean causal chain. Here is how I would sequence the next 7–10 days of work so that every experiment is small, has a clear falsifier, and directly advances the “belief → predictive hypothesis → test → plan” loop without abandoning your principles.

### Current inventory (what is already earned)

| ID | Status | Key result that constrains next steps |
|----|--------|---------------------------------------|
| H001 | Tested | Conditional affordance exists; single precondition is insufficient on cd82 |
| H005 | In progress | Conjunctive preconditions work; the missing piece is a *state* condition kind, not more adjacency |
| H006–H008 | Tested | `Z1 = actions-since-reset` resolves meter-class aliasing; gains predictive sufficiency where state exists |
| H009 | Closed | Reading B: transition model class is the defect (offset lattice cannot represent position-dependent hops) |
| H010 Stage 1 | Done | `PositionModel` + `plan_graph` proven offline (100 % found + honoured on the same 1 779 decisions) |
| H011 Stage 1 | Done | Novelty ranking would have hit the swatch strip ~32× more often; the gap is pure tier ordering |

The two live gaps that keep recurring are:
1. Exploration does not guarantee the coverage a later decision will need (H007, H009 live validation, H011).
2. The hypothesis language still cannot express the real second factor on cd82 (“which swatch is selected” is a persistent state, not another adjacency).

Everything else should be ordered so that these two gaps are closed before we reopen broader proposers or score sweeps.

---

### Recommended experimental sequence

**Phase 0 – Housekeeping (½ day, no new science)**  
- Finish the regression design for H010 Stage 2 that the doc already calls for: a seed-paired parity sweep on the games that already have a clean move map (sp80, ls20, ar25, m0r0, dc22, …).  
  Metric: action-stream divergence rate and level-1 completion rate vs current `plan`.  
  Gate: only promote `plan_graph` preference if the parity games do not regress.  
- Close H005 Stage 2 / Stage 4 if they are still open; they are no longer on the critical path.

**Phase 1 – Close the exploration gap that is already diagnosed (2–3 days)**  
This is the highest-leverage, lowest-risk next move because both H009’s live validation and H011 Stage 1 point at the same mechanism.

**H012 (proposed): Novelty-aware selection becomes first-class in `_select` and `ClickTargeting.pick`**

- Claim: Adding an explicit novelty term (1 / (1 + sightings)) as a tier (or a soft blend) inside the existing decision functions raises coverage of under-characterised cells/positions without harming the games that already clear level 1 by salience/reward.  
- Mechanism:  
  - Clicks: novelty tier (or weighted blend) in `ClickTargeting.pick`.  
  - Movement: score candidate actions by how few times the current (position, action) pair has been observed in `PositionModel` / `MoveModel`.  
- Predictions:  
  - On cd82, strip clicks rise from ~1.6 % to ≥ 15 % of ACTION6 decisions (still well below the theoretical 50 % of the tied set).  
  - On the same ten seeds used for H009 live validation, the missing orbit position appears in ≥ 9/10 seeds by decision 150.  
  - Whole-sweep median on the 25 games does not fall (n ≥ 30, seed-paired).  
- Falsifier: strip / missing-position coverage does not rise, *or* the parity games that already work regress by > 1 level-1 clear per 30 sweeps.  
- Experiment design: Stage 1 already done offline. Stage 2 is a live A/B with the novelty term behind a flag (`ARC_NOVELTY=1`). Measure both local coverage metrics and the global score/depth metrics you already trust.  
- Why this first: it is pure decision weighting over evidence you already keep. It does not touch representation, does not require an LLM, and removes the common failure mode that blocked both H007 and H009 live.

**Phase 2 – Wire the already-proven transition model (1–2 days after Phase 1)**  
**H010 Stage 2** becomes safe once novelty is improving coverage.

- Wire `PositionModel.observe` into `_learn_from`.  
- Prefer `plan_graph` over `plan` when the graph has edges from the current position; fall back to the offset model otherwise.  
- Regression design from Phase 0 is the gate.  
- Success criterion: on cd82 the agent can now string the 2–3 hop walks that H009 showed exist; the live “route found but immediately dropped” failure disappears.  
- Secondary metric: does any other game with position-dependent motion improve?

**Phase 3 – Give hypotheses a state condition kind (2–3 days)**  
This is the direct continuation of H005’s finding.

**H013 (proposed): A `state` / attribute condition kind**

- Claim: A second condition kind that tests a persistent, evidence-derived attribute of an entity (or of the global attempt state) lets a conjunctive hypothesis express “adjacent on −x *and* the correct swatch is selected.”  
- Mechanism candidates (choose the cheapest that is still falsifiable):  
  - Colour of a named region (the selected swatch colour).  
  - A boolean “has been clicked / has changed under ACTION6 since last RESET.”  
  - The existing `Z1` or a simple meter-derived flag.  
- Scope discipline: only the condition language and the `_condition_met` dispatcher change. Enumerator and LLM schema stay untouched until the representation is proven useful.  
- Predictions:  
  - Hand-authored two-condition oracle (adjacency + state) now jointly satisfies on a material fraction of steps on cd82 (contrast H005’s near-zero joint rate).  
  - When the state condition is met, the residual move under the lever is more often in the correct direction.  
- Falsifier: even with the correct state expressed, joint satisfaction remains rare *or* the residual never moves usefully → the bottleneck is still elsewhere (goal identification or exploration of the paint action itself).  
- Experiment: first offline / oracle injection (same style as H005 Stage 3), then a small live flag if the oracle succeeds.

**Phase 4 – Make the model predictive enough for internal checks (parallel or immediately after Phase 3)**  
**H003 completion / H014**

You already have a one-step predictor. The next useful step is:

- Extend the predictor to multi-step residual trajectories under a candidate action sequence (using either the position graph or the existing residual dynamics).  
- Require that a hypothesis only spends live budget after a short internal roll-out shows the residual is expected to fall.  
- This is the minimal version of “plan through the model” that stays inside your residual language and does not require a full pixel simulator.

**Phase 5 – Only then reopen the proposer**  
H002 (LLM as hypothesis scientist) and a richer enumerator become high-value once:

- exploration covers what later decisions need,  
- the transition model can represent position-dependent motion,  
- hypotheses can carry state conditions,  
- and a short internal prediction can be checked before live actions are spent.

Until those four pieces are in place, giving the proposer more power mainly amplifies the existing failure modes.

---

### Operating rules for the next two weeks

1. One live behavioural change at a time, always behind a flag, always with an n ≥ 30 seed-paired parity check on the games that already work.  
2. Offline / oracle / counterfactual first whenever the claim is about representation or ranking; live only after the mechanism is proven.  
3. Score is a secondary metric until level-2 clears become reproducible on at least one game that currently has ample budget (cd82 is still the cleanest testbed).  
4. Keep the hypothesis files exactly as you have been writing them — claim, mechanism, prediction, falsifier, status log. That discipline is already paying off.

### Immediate next actions (this week)

1. Write the short regression design for H010 Stage 2 and run the parity sweep.  
2. Open H012 and implement the novelty term in click targeting first (lowest risk, highest measured opportunity).  
3. Once novelty is live and measured, wire H010 Stage 2.  
4. In parallel, design the cheapest state-condition representation for H013 and run the oracle test on cd82.

This sequence turns the advice I gave earlier into concrete, ordered experiments that stay inside the evidence-gated philosophy you have already established. It closes the two recurring gaps first, then makes the belief layer actually actionable, and only then widens the hypothesis language. That is the path that both respects the record you have built and gives the highest chance of converting representation quality into depth and score.