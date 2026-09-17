Yes. I went back through the current repo and the latest `plan.md` state, deliberately **without opening the `review/` material**. I think your instinct is correct: **another 25-game full sweep of H011 is not the interesting next experiment.** There is useful information in the latest H011 result, but it is not primarily a score result. It tells us something about where the causal bottleneck is.

And I think the latest H010 result makes the situation clearer than it was two days ago.

## The short version

I would currently stop doing **"make exploration slightly better" experiments**.

H011 demonstrated that the click-targeting mechanism had a real structural defect, and fixing it produced a real improvement: median 0.0163 → 0.0206 at n=30, with `ft09` going 0/30 → 12/30 and `vc33` 0/30 → 11/30. That's meaningful. 

But H010 then showed something much more important:

> **You can improve the agent's ability to traverse the discovered position graph without improving its ability to satisfy the goal.**

The corrected H010 sweep was essentially flat/slightly negative overall; the route-persistence defect was genuinely fixed, but the crucial oracle joint-satisfaction rate did **not** improve. 

That is exactly the distinction we've been circling.

Your problem is increasingly **not "can the agent get to places?"**

It is:

> **"Can the agent know which state it needs to create, and predict what action sequence will create it?"**

And I think that should now become the center of the next phase.

---

# 1. H011 is actually a very good result, despite the small score movement

The interesting part of H011 is not:

> median +0.0043.

It is this:

```text
old targeting
    ↓
hard salience tiers
    ↓
swatch strip almost never selected

H011 diagnosis
    ↓
the information existed
    ↓
selection policy made it inaccessible

H011 fix
    ↓
remove hard tier cutoff
    ↓
novelty can actually compete

result
    ↓
1.6% → 42–52% swatch clicks
```

And importantly, **weight 0 performed almost the same as weights 0.5–4**. So the novelty term itself was not responsible for most of the gain. The architectural discovery was:

> **The hard priority hierarchy was starving potentially informative actions.**

That's a good result.

And the n=30 follow-up already cleared the regression gate, with the median moving upward and no meaningful regression among your protected games. 

I would therefore treat H011 as **closed enough**.

I would not spend another full sweep asking:

> "Does H011 work?"

You've already got enough evidence that the mechanism is real.

The unexplained `ft09` and `vc33` jumps are worth investigating later, but **not by blindly increasing n**.

---

# 2. The H010 result is much more important

This is the result I'd sit with.

H010 fixed:

> "I found a path, but I immediately throw the path away."

That's a real bug.

The live trace and unit tests establish that the fix works. 

But:

```text
position graph works better
        ↓
path persistence works
        ↓
joint condition satisfaction does NOT improve
```

That is extremely informative.

Because H010's success criterion had two halves:

1. eliminate path dropping
2. increase the rate at which the two conditions for the target action are simultaneously satisfied

You got **1/2**.

The second half failing tells us that the graph wasn't actually the fundamental bottleneck.

And this connects directly to H007/H001.

---

# 3. Look at the pattern across H007 → H010 → H011

I think the experiments now form a surprisingly coherent story.

### H007 / conditional lever

You discover:

```text
ACTION5
works when:
    spatial condition A
    +
    side condition B
    +
    something else
```

You improve the representation.

Result:

**cd82 still doesn't move.**

You correctly infer that the visible spatial condition isn't sufficient. 

---

### H011 / information-directed clicking

You discover:

```text
The information needed to investigate the swatch
is technically reachable.

But the targeting policy starves it.
```

You fix targeting.

Result:

**much better exploration coverage.**

But that does not yet produce the missing state-conditioned lever.

---

### H010 / position graph

You discover:

```text
The agent knows a useful route,
but loses it between decisions.
```

You fix that.

Result:

**routing becomes more correct.**

But joint satisfaction of the actual goal conditions doesn't increase.

---

That is three different layers being repaired:

```text
H011    exploration access
          ↓
H010    navigation execution
          ↓
H007    state-conditioned action
```

And **the third is still broken**.

That is the signal.

---

# 4. I therefore disagree slightly with the current plan's proposed ordering

The current plan says:

> Phase 4: extend H008's predictor a few steps and gate hypothesis action budget on predicted residual reduction. 

I think that's directionally right, but I would make it **more ambitious than "residual rollout."**

Otherwise you risk building:

```text
current residual
      ↓
predicted residual
      ↓
predicted residual
      ↓
predicted residual
```

while never asking whether the residual itself is the correct representation of the hidden state.

That would be another elegant layer sitting on top of the wrong abstraction.

The experiments are now telling you that this is possible.

---

# 5. I think the next question should be:

## "What information distinguishes a successful state from an observationally similar unsuccessful state?"

This is the experiment I'd put ahead of another broad sweep.

Take cd82.

Find trajectories where:

```text
frame_t ≈ frame_t'
```

but:

```text
future consequences differ
```

or where:

```text
same visible spatial arrangement
+
same available action
```

produces different outcomes because some historical/latent condition differs.

If you can find that, you've got your smoking gun.

Because then you can say:

> **The current state representation is not Markov-sufficient.**

That is a much stronger diagnosis than:

> "We need another feature."

---

# 6. This is where H008 suddenly becomes more important

Your predictor has already told you that the largest prediction errors concentrate in **state-dependent geometry**, particularly containment/distance under movement. 

That is exactly the sort of thing a temporal model should attack.

But I would change the H008 question from:

> "Can I predict the next residual?"

to:

> **"What state variables are required to make the transition predictable?"**

For example:

```text
Z_t:
    position
    object identity
    relation
    selected state?
    phase?
    arrangement?
    hidden mode?
```

Then:

```text
Z_t + ACTION5
      ↓
predicted Z_t+1
      ↓
predicted observation
```

And if prediction fails:

```text
prediction error
      ↓
what variable was missing?
```

That last arrow is the research engine.

---

# 7. This also gives you a much better use for the latent-state idea we discussed

I would now make the next architectural layer:

## `StateEstimator`

Not an LSTM yet.

Not a giant neural representation.

Something initially explicit:

```text
StateEstimator
    observe(frame)
    observe(action, frame_before, frame_after)
    update()
    state()
```

Its job is to maintain:

```text
persistent variables
+
current values
+
uncertainty
+
evidence
```

And then:

```text
TransitionModel
    predict(state, action)
```

Now H008 can become:

```text
StateEstimator
       ↓
TransitionModel
       ↓
multi-step rollout
       ↓
Hypothesis / planner
```

This is much more powerful than simply adding another prediction heuristic.

---

# 8. I would postpone H012

This is where I think the current plan is slightly too incremental.

H012 asks whether movement novelty improves orbit coverage. The hypothesis is sensible, and the predicted improvement is quite modest: 8/10 → 9/10 seeds by decision 150. 

But look at what H010 just told you.

You already have enough position exploration in **8–9/10 seeds** under the current policy. H010's own plan says this explicitly. 

So H012 is optimizing:

```text
8/10 → 9/10
```

while the deeper failure is:

```text
"Even when I get there, I don't know what state I need to produce."
```

I would not make that your main research bet right now.

H012 is a nice low-risk experiment. It is not the thing I would spend the next major block of research on.

---

# 9. I would also leave H002 alone for now

This is another place where the latest evidence is surprisingly clear.

The LLM proposer thread has already produced a lot of useful information.

The n=10 result:

```text
baseline median 0.0413
LLM median      0.0448
```

while the mean looks 2× better because of a couple of outliers.

The pairwise tests did not establish a robust score effect, and you explicitly concluded that further score sweeps on this axis have low information value. 

More importantly, you found a **mechanistic failure**:

```text
39–47% of LLM conditionals
→ unmet routing

12/17
→ self-referential "member" preconditions

50.9% budget wasted
```

That's a fantastic finding.

But it doesn't say:

> "Give the LLM more power."

It says:

> **"The LLM is being asked to hypothesize before the world model has enough state structure."**

So I would absolutely not reopen H002 yet.

The current plan agrees with this, and I think that's correct. 

---

# 10. There's actually a very strong negative result hiding in your whole experiment history

This is the thing I want you to take seriously.

You've now built:

* change detection
* contingency
* salience
* object detection
* identity
* control inference
* effect kinds
* stamina
* vanish
* routing
* beliefs
* residuals
* conditional levers
* hypothesis enumeration
* LLM hypotheses
* click novelty
* position graphs

and **most of the score movement has come from things that directly changed action selection**, while many representation layers produce zero.

Your own governing principle says:

> **No representation without a consumer.**

And I think there is a second principle emerging:

> **No consumer without a state model.**

Because:

```text
representation
    ↓
consumer
    ↓
action
```

still isn't enough if the action isn't conditioned on the **right state**.

That's why H011 can materially change where you click without solving the game.

---

# 11. So I would change the research roadmap

If I were taking the repo over tonight, I'd make the next sequence:

### Phase A: Diagnose temporal insufficiency

**Do not sweep first.**

Build offline probes against recorded trajectories.

Questions:

1. Does the current explicit state predict next observations?
2. At what horizon does it fail?
3. Which failures are caused by position?
4. Which failures cannot be explained by current state?
5. Are there observationally similar frames with different future consequences?

This is cheap.

And it directly tests the hypothesis we've been discussing.

---

### Phase B: Build minimal `LatentState`

Not "deep latent representation."

Just:

```text
LatentState:
    known variables
    candidate variables
    uncertainty
    provenance
```

Every variable must have evidence.

Exactly consistent with your governing principle.

---

### Phase C: Make H008 temporal

Instead of:

```text
predict one residual
```

do:

```text
state_t
   ↓ action
predicted state_t+1
   ↓ action
predicted state_t+2
   ↓ action
predicted state_t+3
```

Then compare with reality.

This gives you the first actual **world-model experiment**.

---

### Phase D: Use prediction to gate experiments

This is the Phase 4 idea already in your plan, but now I would implement it.

Before spending 8 actions testing H:

```text
simulate H
```

If the model says:

```text
expected residual:
10 → 8 → 6 → 4
```

then test it.

If:

```text
10 → 11 → 11 → 12
```

don't spend the actions.

This turns your predictor from **recording infrastructure into an action-economizing mechanism**.

---

### Phase E: Only then return to the LLM

Now give the LLM:

```text
current latent state
candidate transitions
prediction failures
unexplained observations
```

and ask it to propose:

```text
new latent variable
new transition
discriminating experiment
```

That's a substantially better role than asking it to invent arbitrary residual hypotheses.

---

# 12. And yes, I would eventually do another full sweep

But **not after H011 simply because "we should see whether the score moved."**

I'd do it when there is a meaningful architectural change.

Specifically:

```text
H011
   ✓ gated
   ↓
H010
   ✓ mechanism fixed
   ↓
Latent temporal state
   ↓
multi-step predictor
   ↓
prediction-guided action
   ↓
FULL SWEEP
```

Then the sweep answers a much more important question:

> **Did adding a predictive world model allow the agent to penetrate beyond level 1?**

That is a worthwhile 25-game sweep.

A repeat of:

```text
H011 on
vs
H011 off
```

is much less interesting now.

---

# 13. One thing I would *definitely* do before that sweep

Use the **level-2 failure distribution**, not aggregate score, as the primary diagnostic.

Your own analysis has already established that level 2 is the critical bottleneck. Only one recorded run has reached it, and the two main failure modes are radically different:

* sp80: insufficient efficiency/resource relative to the level
* cd82: enormous action budget available relative to the human solution, yet no completion

That makes cd82 especially valuable as a goal/state-identification test. 

So after every meaningful change, report:

```text
Level 1 completion
Level 2 entry
Level 2 completion
Actions to L2
Actions to L3
```

before looking at the aggregate.

Because a system that moves:

```text
L1 = 0.02 → 0.04
```

may be irrelevant if:

```text
L2 = 0 → 0
```

while a system that gets:

```text
L1 = 0.02 → 0.02
L2 = 0 → 2/30
```

has made the fundamentally important breakthrough.

Your own scoring analysis already showed that depth dominates speed. 

---

# 14. One concern I have about the current experimental culture

This is a subtle one.

You have become **very good at making each individual experiment scientifically clean**.

That is a strength.

But there's a risk of entering:

```text
H009
→ small problem
→ fix
→ parity
→ H010
→ small problem
→ fix
→ parity
→ H011
→ small problem
→ fix
→ parity
→ H012
→ ...
```

while the architecture itself doesn't undergo a phase transition.

The recent results are telling you that this is happening.

You are improving the **infrastructure around the agent**.

But the agent still lacks the thing that can compose those capabilities into:

```text
I know what state I'm in
+
I know what state I need
+
I know how actions change state
+
I can simulate that change
+
I can choose actions based on that simulation
```

That's why I'm much more interested in the temporal latent-state experiment now than H012.

---

# 15. I would make one concrete change to your next hypothesis

Rather than:

### H012: movement novelty

I'd write something like:

## H013 — Predictive sufficiency of explicit state

**Claim**

> The current explicit state representation is insufficient to predict action-conditioned future observations over multiple steps; augmenting it with persistent state variables inferred from transition failures will improve multi-step prediction.

**Falsifier**

> Multi-step prediction error does not decrease after adding the candidate state variables, or the improvement does not survive on held-out trajectories/games.

**Measurements**

```text
1-step prediction error
2-step prediction error
4-step prediction error
8-step prediction error

before / after
```

And separately:

```text
observational alias count
```

where:

```text same current observation/state
but
different future transition
```

This would be a genuinely new capability, not another policy tweak.

---

# 16. And then H014 could be the action-consumer

Once H013 works:

## H014 — Predictive experiment selection

**Claim**

> Using the learned transition model to reject hypotheses whose predicted trajectories do not reduce the target residual will reduce wasted hypothesis-test actions and improve depth.

Then measure:

```text
actions spent on falsified hypotheses
actions spent on inconclusive hypotheses
actions spent on successful hypotheses
level-2 entries
```

That gives you the consumer.

And **that** is when I'd expect a serious chance of a score movement.

---

# 17. Where I stand on the full sweep question

Your intuition:

> "We could do another full sweep after H011, but I don't think it's going to affect things much."

**I agree.**

I'd put it this way:

| Option                                | My read                                                                                                                          |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| H011 another 30-seed full sweep       | Low information                                                                                                                  |
| H012 movement novelty                 | Reasonable side experiment, not central                                                                                          |
| H010 more routing work                | No, unless a specific oracle failure is identified                                                                               |
| H002 more LLM score sweeps            | No                                                                                                                               |
| H007 another cd82 enumeration sweep   | Yes, but only as a diagnostic after H011 if you specifically want to establish whether click coverage was the missing ingredient |
| Offline temporal-state analysis       | **Yes**                                                                                                                          |
| Multi-step predictor                  | **Yes**                                                                                                                          |
| Observational-alias analysis          | **Very yes**                                                                                                                     |
| Predictive rollout as hypothesis gate | **Yes, after the predictor is credible**                                                                                         |
| LSTM/LMU                              | Not yet                                                                                                                          |
| Full sweep                            | **After the predictive architecture has a real consumer**                                                                        |

---

## The thing I think has changed

Two days ago, I was saying:

> "I think your missing piece is a latent-state model."

After seeing **H010 + H011 together**, I'm more confident and more specific.

I think you've now experimentally demonstrated a hierarchy:

```text
                  EXPLORATION
                      │
                      ▼
                 NAVIGATION
                      │
                      ▼
              STATE SATISFACTION
                      │
                      ▼
                GOAL ACHIEVEMENT
```

H011 improves the first.

H010 improves the second.

**Neither reliably improves the third.**

And your level-2 results say the third is where the serious barrier is.

So I would stop trying to make the agent **better at getting somewhere** and start making it **better at knowing what "somewhere" means as a dynamical state**.

That is why I think the next week should be the transition from:

> **relational representation + hypothesis testing**

to:

> **action-conditioned temporal world model + hypothesis testing.**

And importantly, this doesn't invalidate the work you've done. Quite the opposite. Your existing perception, entities, beliefs, conditional levers, position model, H011 exploration and H008 predictor become the substrate from which the temporal model can be built.

The next full sweep should be the **measurement of that architectural transition**, not another audit of H011.

Yes. I think the LMU idea deserves to come back into the plan, but **not as “the next representation.”** I would use it as a very specific instrument for answering the deeper question you just identified:

> **Are we failing because we cannot remember the relevant history, or because we have not decided what information constitutes state in the first place?**

Those are very different problems.

My current judgment is that **state selection is the more fundamental missing layer**, and an LMU is potentially an unusually good low-risk way to test the temporal-memory side of that question without committing us to learned recurrent machinery.

### The key distinction

There are really three problems:

```text
                    HISTORY
                       │
                       ▼
              ┌─────────────────┐
              │ What matters?   │  ← state selection
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ STATE_t         │
              │ representation  │
              └────────┬────────┘
                       │
                action │
                       ▼
              ┌─────────────────┐
              │ STATE_{t+1}     │  ← transition
              └────────┬────────┘
                       │
                       ▼
                 future obs
```

An LMU primarily helps with the **left side of the first box**: compressing a history into a state-like vector.

It does **not** answer:

> Which aspects of history deserve to be retained?

And that is precisely the issue you are raising.

---

# 1. Why I would not dismiss the LMU

The interesting thing about an LMU in your setting is that its memory mechanism is mathematically fixed. The original LMU work explicitly demonstrates long-history compression without requiring training for the isolated memory task. Its memory state is a projection of a recent history onto Legendre basis functions rather than a conventional recurrent hidden state. ([NeurIPS Papers][1])

That makes it fundamentally different from saying:

> "Let's train an LSTM and hope it learns what ARC state means."

I would **not** do that.

An untrained LMU gives us a cheap temporal coordinate system:

$$
m_t = A m_{t-1} + Bx_t
$$

where \(x_t\) could be your structured observation/event vector.

Then ask:

$$
P(o_{t+k}\mid x_t, a_{t:t+k})
$$

versus

$$
P(o_{t+k}\mid x_t,m_t,a_{t:t+k})
$$

If adding the LMU memory makes future outcomes substantially more predictable, **we have empirical evidence that temporal compression is missing from the current representation.**

If it doesn't, we've learned something equally valuable:

> The problem isn't that we're forgetting history. We're representing the wrong things.

That is exactly the kind of experiment I want us doing now.

---

# 2. But I think your second observation is even more important

You said:

> "The problem is not simply the evolution of states itself, but the change of choice of states themselves."

**Yes.**

This is where I think my previous framing needs to be sharpened.

We have been talking about:

> observation → state → transition → prediction

But the real architecture is closer to:

> **history → select relevant variables → state → transition**

And our agent currently has quite a lot of machinery for the *selection* problem, but it is distributed across modules rather than recognized as one system.

Look at what we already have:

| Existing mechanism           | What it is really doing                                |
| ---------------------------- | ------------------------------------------------------ |
| perceptual lenses            | proposing candidate variables                          |
| `_detect_translation`        | deciding movement is a relevant invariant              |
| identity tracking            | deciding persistent entities matter                    |
| `acts_locally`               | deciding spatial locality matters                      |
| stamina/meter detection      | deciding a hidden-ish temporal variable matters        |
| `WorldBelief` roles          | deciding which entities are causally important         |
| `PairRecord.by_action_given` | conditioning state on a contextual variable            |
| residuals                    | identifying variables currently unexplained            |
| hypotheses                   | proposing additional state variables/relations         |
| falsifiers                   | deciding whether a proposed variable actually matters  |
| predictor                    | testing whether selected variables explain transitions |
| PositionModel                | retaining persistent spatial state                     |

So I **do not think we need to invent a state-selection system from scratch.**

We have the beginnings of one.

The problem is that we currently use these mechanisms mostly to answer:

> "What happened?"

rather than the stronger question:

> **"What information must survive into the next decision because it changes the distribution of possible futures?"**

That should become the organizing principle.

---

# 3. This gives us a much better definition of "state"

I would actually change the conceptual definition in the research docs.

Don't define state as:

> everything the agent currently knows.

And don't define it as:

> a fixed collection of detected objects.

Define a candidate state variable \(z_i\) by its **predictive consequence**.

A variable deserves to be in state if:

$$
P(o_{t+1:t+k}\mid H_t,a_{t:t+k})
$$

changes materially when that variable changes.

In plainer language:

> **If knowing X changes what we should expect to happen next, X is state-relevant.**

This is extremely compatible with your existing philosophy of "no representation without a consumer."

We're just making the consumer explicit:

**the transition predictor.**

---

# 4. This also tells us what experiment to run before building anything substantial

I would make this the next major experiment.

## H013-ish: Predictive State Sufficiency

Take your existing replay corpus.

For every timestep construct several increasingly rich representations:

### R0: current observation

```text
current perceptual facts
```

### R1: current relational state

```text
entities
positions
relations
roles
known mechanics
```

### R2: R1 + explicit temporal variables

```text
meter phase
recent action
recent outcome
transition history
```

### R3: R2 + LMU memory

```text
LMU(R2 history)
```

Then evaluate prediction at:

```text
k = 1
k = 2
k = 4
k = 8
```

Not necessarily pixel reconstruction.

Predict **your structured consequences**:

```text
position change
entity disappearance
recolor
cardinality change
level boundary
meter change
new accessibility
action-conditioned outcome
```

This is much closer to the actual problem.

---

# 5. And here is the really important experiment

Don't merely measure prediction error.

Measure **state aliasing**.

Suppose we encounter:

```text
History A → apparent state S → action LEFT → outcome X

History B → apparent state S → action LEFT → outcome Y
```

If the current representation says A and B are identical but their futures differ, then:

> **S is not a sufficient state representation.**

That is gold.

Because now we can ask:

> What differs between A and B?

Maybe:

```text
meter phase
number of previous lever activations
which entity was touched
order of operations
whether something has already been consumed
latent mode
goal progress
```

That difference becomes a candidate state variable.

This gives us an **automatic state-discovery loop**:

```text
             identical-looking states
                       │
                       ▼
              different futures
                       │
                       ▼
             find history difference
                       │
                       ▼
              candidate state variable
                       │
                       ▼
                falsify / test
                       │
                       ▼
                retain if predictive
```

That is much more powerful than simply saying "let's add memory."

---

# 6. Where the LMU fits beautifully

Now I actually like the LMU much more.

Instead of:

> "Let's replace our state representation with an LMU."

I'd do:

```text
                         raw history
                             │
                ┌────────────┴────────────┐
                │                         │
                ▼                         ▼
       explicit state candidates       LMU memory
                │                         │
                └────────────┬────────────┘
                             ▼
                    predictive model
                             │
                             ▼
                       future outcome
```

The LMU becomes a **temporal residual channel**.

The explicit representation says:

> "I believe these things matter."

The LMU says:

> "Here is compressed information about the recent history that you haven't explicitly represented."

Then we can test:

### Case A

Explicit state predicts well; LMU adds little.

**Conclusion:** temporal memory isn't the bottleneck. State-variable selection is.

### Case B

LMU dramatically improves prediction.

**Conclusion:** we have a genuine temporal compression problem.

Then we investigate what information the LMU is providing.

### Case C

LMU improves prediction, but we can't interpret why.

Interesting, but don't immediately deploy it. First try to identify the latent variable it is substituting for.

That gives us scientific leverage rather than just another black box.

---

# 7. There is one important caveat with LMU

I would **not assume that an LMU is automatically appropriate for ARC3.**

The original LMU is fundamentally a continuous-time/sequence-memory construction that compresses a sliding temporal window into a fixed-dimensional representation. ([NeurIPS Papers][1])

Our environment is different.

ARC3 has:

* discrete actions
* irregularly informative events
* resets
* level transitions
* long periods where nothing relevant happens
* potentially discrete latent modes
* action-conditioned causal changes

A fixed temporal window can therefore be the wrong inductive bias.

For example:

```text
ACTION1
ACTION1
ACTION1
ACTION4
ACTION2
ACTION6(click)
ACTION1
...
```

The fact that something happened **37 actions ago** may matter enormously, while five visually similar transitions in between may be irrelevant.

So I'd test LMU memory, but I would not elevate it to the architecture until we establish that **smooth temporal compression is actually what the environments require.**

---

# 8. And there is external evidence pointing in our direction

ARC Prize itself explicitly frames ARC-AGI-3 around **modeling, goal-setting, planning/execution and exploration**, and describes modeling as building a world model capable of predicting future states and outcomes. It also explicitly calls out memory compression as part of what the benchmark measures. ([ARC Prize][2])

More interestingly, several public ARC3 efforts are independently converging on some form of explicit world state:

* one public project is exploring an object-centric JEPA latent world model, explicitly motivated by predicting future latent states; ([GitHub][3])
* another uses a state memory graph plus a transition model and short-horizon planning; ([GitHub][4])
* Curio maintains an explicit state graph, learned transition edges, and state-space planning; ([GitHub][5])
* another public agent explicitly describes accumulating structural facts into a world model. ([GitHub][6])

I would **not interpret this as "copy those architectures."** They have very different approaches and publicly reported results are not directly comparable.

But it is useful evidence that the broader design space is converging on:

> persistent state + transitions + prediction/planning

rather than merely increasingly sophisticated frame-to-action policies.

---

# 9. The thing I think we are currently missing

I don't think the missing module is:

```text
LMU
```

or

```text
LSTM
```

or even

```text
WorldModel
```

in isolation.

I think we're missing a **State Manager**.

Not a giant neural module.

Something conceptually like:

```python
StateManager
    candidates
        position
        identity
        relation
        meter_phase
        accessibility
        activation_state
        goal_progress
        ...
    
    evidence
        observations
        transition_support
        falsifications
        predictive_gain

    active_state
        variables currently worth tracking

    update(history, action, observation)

    predict_relevance(variable)

    retire(variable)
```

And crucially:

**state variables should be allowed to enter and leave the active state.**

That addresses exactly what you said:

> "the change of choice of states themselves"

The state at time \(t\) doesn't merely change its values.

**The set of variables we consider state-relevant can change.**

For example:

```text
early exploration:

State =
    avatar position
    wall geometry
    action effects


after discovering a meter:

State =
    avatar position
    wall geometry
    action effects
    meter phase


after discovering a conditional lever:

State =
    avatar position
    wall geometry
    action effects
    meter phase
    lever condition


after discovering a persistent mode:

State =
    ...
    mode
```

That is a much more interesting form of adaptive intelligence than simply having a bigger hidden vector.

---

# 10. And amazingly, your current machinery is already close

This is why I **don't** want you to throw away the architecture.

You already have:

**Candidate generation**

```text
perception
relations
residuals
hypotheses
```

**Evidence**

```text
observations
action-conditioned effects
belief
falsifiers
```

**Persistence**

```text
identity
position model
learned moves
conditional records
```

**Prediction**

```text
H008 predictor
```

**Selection pressure**

```text
residual reduction
hypothesis success/failure
prediction error
```

The missing step is to make those pieces answer one common question:

> **Which variables should constitute the current predictive state?**

That is a much smaller architectural jump than "build a neural world model."

---

# 11. So here is the development order I would actually choose

This is where I'd be quite disciplined.

### Stage 1: State sufficiency audit

**No live behavioural change.**

Take replay data and determine:

1. How well does current explicit state predict 1/2/4/8 steps?
2. Where does it fail?
3. How often do apparently identical states have different futures?
4. What historical differences explain those aliases?

This is probably the highest-information experiment available to us.

---

### Stage 2: Explicit dynamic state

Introduce a small `DynamicState` layer.

Not an LMU yet.

Something like:

```text
DynamicState
    recent_action
    recent_effect
    action_sequence_signature
    meter_phase
    persistent_mode
    goal_progress
    ...
```

But variables enter only when evidence says they matter.

---

### Stage 3: LMU sidecar

Now add an **untrained fixed LMU** over the structured event stream.

Do not let it control the agent.

Use it only as:

```text
history → LMU state → predictor
```

Compare:

```text
explicit state
explicit + LMU
```

If LMU gives no meaningful predictive improvement:

**kill the LMU direction.**

That's a successful experiment.

If it gives substantial improvement:

**investigate what information it is retaining.**

---

### Stage 4: State-selection mechanism

Turn what we learned in Stages 1–3 into an actual mechanism for:

```text
candidate variable
       ↓
predictive contribution
       ↓
retain / reject
       ↓
active state
```

This is where your existing hypothesis machinery becomes much more powerful.

A hypothesis isn't merely:

> "Maybe the lever depends on blue."

It can become:

> "Tracking blue-state is necessary because removing it increases predictive uncertainty over the next 4 actions."

That's a much deeper hypothesis system.

---

### Stage 5: Multi-step model-based planning

Only after the state representation survives those tests:

```text
State_t
   ↓
action
   ↓
predicted State_t+1
   ↓
action
   ↓
predicted State_t+2
   ↓
...
```

Then your H014-style idea of **planning through the model before spending live actions** becomes meaningful.

---

### Stage 6: LLM

Only *then* reopen the LLM proposer.

And give it:

```text
current predictive state
prediction errors
state aliases
residuals
candidate missing variables
requested discriminating experiment
```

That is much better input than asking a small LLM to invent arbitrary conditional levers from observations.

---

# 12. What I would explicitly NOT do

I would not currently do:

| Direction                                 | My current assessment            |
| ----------------------------------------- | -------------------------------- |
| Another 25-game sweep just for H011       | Low information                  |
| More H012 movement novelty work           | Secondary                        |
| More H002 score sweeps                    | Premature                        |
| LSTM                                      | No                               |
| Train an LMU                              | No                               |
| Replace explicit state with neural latent | Definitely no                    |
| Build a giant world model                 | No                               |
| More navigation improvements              | Evidence says not the bottleneck |
| **State sufficiency / alias analysis**    | **Very high value**              |
| **Explicit dynamic state**                | **High value**                   |
| **Untrained LMU as diagnostic**           | **Worth testing**                |
| **Multi-step structured prediction**      | **High value**                   |
| **Adaptive state-variable selection**     | **Potentially central**          |

---

# 13. My strongest recommendation

If you asked me to put my PI hat on and approve **one week of development**, I would give you this sequence:

```text
             EXISTING AGENT
                   │
                   ▼
        ┌─────────────────────┐
        │ State sufficiency   │
        │ / alias analysis    │
        └──────────┬──────────┘
                   │
          ┌────────┴─────────┐
          ▼                  ▼
   explicit state       LMU sidecar
          │                  │
          └────────┬─────────┘
                   ▼
          multi-step predictor
                   │
                   ▼
       identify missing variables
                   │
                   ▼
        adaptive StateManager
                   │
                   ▼
       model-based short planning
                   │
                   ▼
              H002 again
```

And **only after that** would I run another serious full sweep.

Because then the sweep isn't asking:

> "Did another incremental mechanism move the noisy score?"

It is asking:

> **"Did we actually change the agent's ability to maintain a predictive state over time?"**

That is a much stronger scientific experiment.

And I want to emphasize one subtle point: **I am actually more interested in the outcome where the LMU fails than the outcome where it succeeds.** If the LMU gives us no predictive gain, we have strong evidence that the bottleneck is not generic temporal memory. We can then concentrate almost entirely on the more interesting problem you identified: **adaptive selection of what constitutes state.**

That is the direction I currently find most promising because it connects almost every piece you've already built rather than requiring another isolated subsystem.

[1]: https://papers.neurips.cc/paper/9689-legendre-memory-units-continuous-time-representation-in-recurrent-neural-networks.pdf?utm_source=chatgpt.com "Legendre Memory Units: Continuous-Time"
[2]: https://arcprize.org/arc-agi/3?utm_source=chatgpt.com "ARC-AGI-3"
[3]: https://github.com/arodmor/arc-agi-3/blob/main/README.md?utm_source=chatgpt.com "arc-agi-3/README.md at main · arodmor/arc-agi-3 · GitHub"
[4]: https://github.com/EduDev-Commons/ARC-AGI-3-Wayfinder-Agent/blob/main/README.md?utm_source=chatgpt.com "ARC-AGI-3-Wayfinder-Agent/README.md at main · EduDev-Commons/ARC-AGI-3-Wayfinder-Agent · GitHub"
[5]: https://github.com/atilavahedian/arc-agi-3-curio?utm_source=chatgpt.com "GitHub - atilavahedian/arc-agi-3-curio: Curio: a world-modeling agent for the ARC Prize 2026 ARC-AGI-3 competition · GitHub"
[6]: https://github.com/khub-ai/arc-agi-3?utm_source=chatgpt.com "GitHub - khub-ai/arc-agi-3 · GitHub"
