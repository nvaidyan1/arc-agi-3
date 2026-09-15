Yes. Looking at this as an experimental system rather than just an ARC agent, I think you're at a very important transition point: **the bottleneck is no longer "can we make the LLM work?" but "can we establish whether the LLM is adding useful causal decision-making to an already competent agent?"**

My overall assessment is:

1. **The 5×5 sweep is reasonable and I would run it.**
2. **Your durable logging is currently too thin for serious research once the LLM enters the loop.**
3. **`recap.py` should stop being a replay mechanism and become a visualization of an actual recorded trajectory.**
4. **Your LLM call rate is not obviously inefficient. The bigger question is whether each call is producing information that changes behavior.**
5. **The most likely score bottleneck is not Gemma's raw intelligence yet. It is the interface between hypotheses → validation → action selection.**

---

# 1. I would run the 5 seeds

I would **not reduce the sweep merely because it takes 45–50 minutes**.

You have a particularly nice experimental setup:

* same 5 games
* same game set reviewer C has already seen
* 5 seeds
* 200 steps
* fixed proposer implementation
* local model
* ~2.4 calls/game-seed

That is enough to answer a first-order question:

> Does the current LLM proposer produce a reproducible shift in behavior across stochastic trajectories?

And because you're presumably using the same seeds for the relevant comparison, you get a useful paired experiment.

### But freeze everything before launching.

This is more important than reducing runtime.

For E-H002-2, I would record something like:

```text
experiment_id: E-H002-2
git_commit: abc123
model: gemma3:4b
ollama_config:
  temperature: 0.2
  num_parallel: 1
prompt_version: P003
proposer_version: H002
steps: 200
games:
  cd82
  cn04
  tu93
  ka59
  ar25
seeds:
  1..5
```

Then **don't touch the implementation until the sweep is finished**.

Otherwise you get exactly the confounding you correctly identified in the single-seed comparison.

---

# 2. But don't use score as the only dependent variable

This is probably the most important experimental point.

Right now your question is implicitly:

> Did Gemma make the agent better?

But you actually have several causal layers:

```text
LLM output
    ↓
schema validity
    ↓
hypothesis acceptance
    ↓
hypothesis testing
    ↓
hypothesis confirmation
    ↓
action-policy influence
    ↓
trajectory
    ↓
score
```

A failure anywhere upstream can make the final score unchanged.

So your sweep should produce **two classes of metrics**.

### Gameplay metrics

Obviously:

```text
levels completed
score
actions / level
steps survived
```

### Mechanism metrics

These are arguably more important at this stage:

```text
LLM calls
valid responses
usable hypotheses
hypotheses tested
hypotheses confirmed
hypotheses falsified
hypotheses ignored
actions influenced by LLM hypothesis
LLM-influenced actions
successful LLM-influenced actions
```

Then you can distinguish:

### Case A

```text
Gemma produces garbage
→ score unchanged
```

### Case B

```text
Gemma produces excellent hypotheses
→ hypotheses never influence policy
→ score unchanged
```

### Case C

```text
Gemma produces good hypotheses
→ policy uses them
→ actions improve
→ score still unchanged due to trajectory variance
```

Those are completely different engineering problems.

---

# 3. Your current logging architecture is now the bigger problem

I agree with your own diagnosis.

Before the LLM, Tier 2 was probably sufficient.

You had:

```text
step
state
action
frame
reasoning
```

That gives you enough to reproduce the broad trajectory.

But once you have a model generating **ephemeral internal hypotheses**, your live agent contains scientifically interesting information that disappears.

That's not ideal.

The key conceptual change I'd make is:

> **The run itself should become the primary artifact. `recap.py` should become a view over that artifact.**

Right now you have:

```text
LIVE RUN
   │
   ├── Tier 2 log ───────► durable
   │
   └── rich state ───────► disposable
                              │
                              ▼
                         recap.py
                              │
                         re-run agent
                              │
                              ▼
                         rich snapshot
```

That's backwards once an LLM is involved.

I would change it to:

```text
LIVE RUN
   │
   ▼
EVENT / STEP RECORD
   │
   ├──────────────► durable trajectory
   │
   └──────────────► recap.py
                         │
                         ▼
                    HTML visualization
```

No replay required.

---

# 4. The LLM makes replay fundamentally different

You identified this exactly.

Before:

```text
seed
 + deterministic agent
 + deterministic game
 → trajectory
```

So:

```text
seed → replay
```

was legitimate.

Now:

```text
seed
 + deterministic game
 + deterministic agent
 + stochastic LLM
 → trajectory
```

is not enough.

You now need:

```text
seed
 + exact code
 + exact model
 + exact prompt
 + exact LLM parameters
 + exact LLM response
 → trajectory
```

And even that can have complications depending on Ollama/model implementation.

Therefore:

> **A replay that calls the LLM again is not a replay. It is a rerun.**

That's an important distinction I would actually encode into the project terminology.

`recap.py` currently performs a **rerun-based reconstruction**.

That's fine historically.

But for LLM experiments, I would stop treating it as ground truth.

---

# 5. What I would save per step

I would not necessarily dump the entire agent object.

That can become enormous and couple your logs to implementation details.

Instead, define a deliberate:

```python
agent.trace_snapshot()
```

or:

```python
agent.export_step()
```

contract.

Something approximately like:

```json
{
  "step": 37,

  "observation": {
    "frame": "...",
    "available_actions": [...]
  },

  "action": {
    "chosen": "ACTION3",
    "coordinate": null
  },

  "perception": {
    "diff_cells": [...],
    "translation": {...},
    "residual_cells": [...],
    "vanish": [...]
  },

  "control": {
    "anchor": [x, y],
    "moves": {...}
  },

  "environment": {
    "blocked_moves": [...],
    "meter": {...}
  },

  "attention": {
    "top_regions": [...],
    "selected_coordinate": [...]
  },

  "decision": {
    "tier": "router",
    "candidates": [...],
    "weights": {...}
  },

  "hypotheses": {
    "proposed": [...],
    "tested": [...],
    "confirmed": [...],
    "falsified": [...]
  },

  "llm": {
    "called": true,
    "request_id": "...",
    "prompt": "...",
    "response": "...",
    "latency_ms": 42100
  }
}
```

You don't necessarily need all of that **every step**.

In fact, I'd separate:

### Step trace

Small, frequent:

```text
observation
action
decision
important state deltas
```

### Event trace

Only when something meaningful occurs:

```text
LLM_CALL
HYPOTHESIS_CREATED
HYPOTHESIS_TESTED
HYPOTHESIS_CONFIRMED
HYPOTHESIS_FALSIFIED
MODEL_UPDATE
LEVEL_COMPLETE
```

This is much more scalable.

---

# 6. Think "event sourcing", not "snapshot everything"

This is where I think your system can become considerably cleaner.

Instead of asking:

> "What was the entire state of the agent at step 83?"

ask:

> "What changed at step 83?"

For example:

```text
STEP 83
  action = ACTION3

EVENTS
  displacement(E1, +1,0)
  disappearance(E7)
  hypothesis_test(H12)
  hypothesis_confidence(H12, .61 → .83)
```

Then the recap UI can reconstruct the state.

You already have the ingredients for this because your architecture is heavily based around **diffs and events**.

---

# 7. Don't save the LLM's "reasoning"; save its actual interface

This is another distinction I'd make.

You currently have:

```text
reasoning: "hypothesis: drive containment(#9,#10)..."
```

That's useful for human inspection, but it isn't enough to reproduce or audit the LLM.

For every LLM call, I would save:

```text
model
model version
prompt version
system prompt
serialized input
raw output
parsed output
parse success
validation result
latency
call trigger
```

You don't need hidden chain-of-thought. You need the **actual input/output contract**.

For research purposes:

```text
LLM_INPUT
    ↓
LLM_OUTPUT
    ↓
PARSER
    ↓
VALIDATOR
    ↓
AGENT
```

should be completely auditable.

That gives you a very powerful post-hoc question:

> "Gemma suggested the right thing. Why didn't we use it?"

or:

> "Gemma was wrong, but why did our validator accept it?"

Those are far more actionable than simply looking at a score.

---

# 8. I would change `recap.py` accordingly

Eventually:

```text
recap.py --game cd82 --seed 8
```

should ideally mean:

> **Open the recorded run.**

Not:

> Re-run cd82 with seed 8 and hope the trajectory matches.

You could have:

```text
recordings/
    E-H002-2/
        cd82/
            seed-001.jsonl
            seed-002.jsonl
            ...
```

Then:

```text
recap.py recordings/E-H002-2/cd82/seed-001.jsonl
```

renders the actual historical trajectory.

And if you want replay for debugging, make that explicit:

```text
replay.py
```

That distinction will save you headaches later.

---

# 9. Your current HTML architecture is actually fine

I wouldn't overengineer this.

The self-contained HTML:

```text
HTML
 ├── CSS
 ├── JS
 └── embedded JSON
```

is perfectly reasonable for experiment inspection.

It's portable, git-friendly if desired, and doesn't require a server.

The problem isn't the HTML.

The problem is that **the HTML is being generated from a reconstructed trajectory rather than the authoritative trajectory**.

Fix that and I'd keep the frontend almost exactly as it is.

---

# 10. Now, the LLM call efficiency question

I don't think **2.4 calls/game** is inherently excessive.

In fact, for a 200-step episode, that's only about:

```text
1 LLM call / 83 steps
```

if averaged evenly, though obviously yours are event-triggered rather than evenly distributed.

That is quite conservative.

The important metric isn't:

> calls per game

It's:

> **useful information gained per call**

For example:

```text
call 1
→ proposes H1
→ tested
→ confirmed
→ changes policy
```

That's a great call.

Versus:

```text
call 2
→ 8 hypotheses
→ 7 invalid
→ 1 vague
→ none tested
```

That's expensive noise.

Your recent change from:

```text
12 proposed
2 tested
```

to:

```text
3 proposed
3 tested
1 confirmed
```

is actually a **much more interesting improvement** than the 27% → 39% schema-validity improvement.

You're moving toward a better interface.

---

# 11. I would optimize the LLM around "decision leverage"

Give the LLM calls a purpose.

A call should ideally answer one of:

### Model discovery

> What mechanism could explain this unexplained observation?

### Hypothesis discrimination

> Which of these hypotheses is best supported?

### Experiment selection

> Which available action most efficiently distinguishes these hypotheses?

### Recovery

> The current model predicted X, but Y happened. What alternative explanations should we consider?

Those are high-value calls.

I'd avoid:

> "Describe the current scene."

That's something your deterministic machinery should handle.

And avoid:

> "What should I do?"

That's too unconstrained.

---

# 12. Your LLM context should be extremely compressed

This ties directly back to our earlier discussion about state representation.

Don't send:

```text
200 frames
full state
all masks
all historical hypotheses
all actions
```

Instead create an **LLM brief** from the structured state.

Something like:

```text
CURRENT CONTROL MODEL
ACTION1 → (-1,0), confidence .94
ACTION3 → (+1,0), confidence .97

RECENT EVENTS
ACTION3 moved E1 adjacent to E7.
E7 disappeared.
Level did not change.

UNEXPLAINED
Why does E7 disappear?

ACTIVE HYPOTHESES
H1: contact causes disappearance, p=.62
H2: ACTION3 causes disappearance, p=.18
H3: coordinate-triggered disappearance, p=.20

AVAILABLE EXPERIMENTS
A: ACTION3 toward another E7
B: approach E7 using ACTION1/ACTION2
C: ACTION3 away from E7
```

That's an **excellent LLM prompt**.

It gives Gemma the abstraction it is good at reasoning over without asking it to rediscover your perception stack.

---

# 13. I would also introduce a call budget

Not necessarily a fixed number.

Something like:

```text
LLM budget
    ↓
remaining calls / remaining time
    ↓
expected information gain
```

Because once you're running hundreds or thousands of games, the question becomes:

> Is another 50-second Gemma call worth more than 50 seconds of deterministic exploration?

You can eventually estimate this empirically.

For example:

```text
LLM call:
  55 sec

deterministic action:
  0.05 sec
```

That's a **1,100× latency ratio**.

So the LLM needs to be doing something enormously more valuable than one additional ordinary action.

That argues strongly for using it on **bottleneck uncertainty**, not routine perception.

---

# 14. The most important experiment I'd run after H002-2

Suppose H002-2 produces:

```text
LLM ON
score = X
```

Don't immediately build H003.

Run an **LLM replay ablation**.

Because you'll now have the actual LLM traces, you can ask:

### A. No LLM

Same deterministic agent.

### B. LLM suggestions recorded, but ignored

Measures raw trajectory baseline.

### C. LLM suggestions accepted

Current system.

### D. LLM suggestions injected offline

Take the exact hypotheses generated in C and replay them against a deterministic version of the agent.

This separates:

```text
LLM generation quality
```

from:

```text
LLM integration quality
```

That's extremely valuable.

---

# 15. What I suspect is currently stopping you from a better score

Based on everything you've described, **I don't think you have evidence yet that the LLM itself is the bottleneck**.

I'd rank the possibilities:

### 1. Hypothesis → policy integration

The LLM can discover something useful, but the agent doesn't give that information enough weight when choosing actions.

### 2. Hypothesis validation

The LLM proposes useful abstractions, but the experiments chosen to validate them aren't sufficiently discriminative.

### 3. Credit assignment

The agent observes an effect but doesn't connect it to the action/condition that produced it strongly enough.

### 4. Exploration policy

The correct hypothesis may exist, but the agent spends too much of its action budget reaching it.

### 5. LLM reasoning quality

Only after the above are established would I conclude:

> "Gemma 3 4B isn't smart enough."

Right now your own data already suggests the **mechanical integration** is improving:

```text
27% → 39% valid schema
12 proposed / 2 tested
        ↓
3 proposed / 3 tested
```

That's evidence that the plumbing is getting better.

But you haven't yet established that **better plumbing produces better gameplay**.

That's exactly what H002-2 should answer.

---

# My recommended near-term plan

I would do this in this order:

### Now

**Run E-H002-2 exactly as scoped.**

Don't change the code.

### Immediately after

Analyze:

```text
score
calls
valid outputs
hypotheses generated
hypotheses tested
confirmed/falsified
LLM-influenced actions
```

across all 25 trajectories.

### Then

Change the logging architecture:

```text
LIVE RUN
   ↓
AUTHORITATIVE TRACE
   ├── step records
   ├── event records
   └── LLM records
          ↓
      recap.py
          ↓
     HTML visualization
```

Do **not** spend time making the HTML more sophisticated yet.

### Then

Run a controlled ablation:

```text
baseline
LLM proposer
LLM proposer + validation
LLM proposer + validation + policy integration
```

You want to identify **where the causal gain disappears**.

---

## And one architectural change I'd make now

Your current system has:

```text
Tier 1: outcome record
Tier 2: trajectory record
Tier 3: reconstructed rich recap
```

I'd replace that mental model with:

```text
Tier 1 — RESULT
    What happened?

Tier 2 — TRACE
    What did the agent actually observe and do?

Tier 3 — EVENTS
    What internal discoveries/decisions occurred?

Tier 4 — LLM I/O
    What did the model actually receive and return?

Tier 5 — VIEW
    HTML generated from the above
```

**Tier 5 is disposable. Tiers 1–4 are evidence.**

That's the big change I'd make.

And given where the project is now, I think that is more important than making Gemma smarter. You are beginning to run actual scientific experiments on the architecture. Once you have a stochastic LLM inside the loop, **the trajectory itself becomes your experimental data**, and you don't want to discover three weeks from now that the one run where Gemma found the critical hypothesis was never actually recorded.
