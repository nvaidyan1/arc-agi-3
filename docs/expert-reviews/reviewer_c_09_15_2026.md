Yes. I read the public repository and its research/architecture/history material, while deliberately **not reading the `review/` folder**. I also looked outward at the current ARC-AGI-3 ecosystem so I could evaluate your architecture against other approaches rather than judging it in isolation.

One caveat first: I could not find a reliable public source tying the name **“FUMO Labs”** to an ARC-AGI-3 score of 18, so I would not want to pretend I know their internals. The broader competitive picture is nevertheless clear: ARC-AGI-3 is explicitly testing exploration, world-model acquisition, goal-setting, and planning/execution, and the current competitive approaches span hand-built search, learned policies, LLM agents with persistent world models, object-centric world models, and hybrids. ([ARC Prize][1])

## My overall verdict

**I don't think you're missing a single giant representation trick.**

But I *do* think you're missing a more fundamental architectural distinction:

> **You are building an increasingly sophisticated system for representing and testing observable relations, while the strongest agents are increasingly treating the problem as online system identification + latent-state inference + active experimentation.**

Those sound similar, but they lead to very different architectures.

Your work is unusually disciplined about **epistemic validity**. That's a real strength. The problem is that you are beginning to optimize the *correctness of the representation machinery* faster than you are optimizing the *agent's ability to discover the latent state variables that actually control future outcomes*.

That's the biggest thing I'd change.

And importantly, I don't think the answer is "throw away your architecture and use an LLM."

---

# 1. What I think you've gotten unusually right

Your current architecture is much more serious than the 0.14 score makes it look.

The most impressive part to me is actually your epistemic discipline.

You have explicitly separated:

**observation → representation → relation → hypothesis → experiment → verification → policy**

rather than doing the common ARC thing of:

**pixels → "this looks like a maze" → hard-coded solver.**

Your rule:

> "No semantic slots without evidence"

is excellent. So is allowing `None` as a genuine outcome. Your `perception` layer returning evidence rather than decisions, and `navigation` accepting a target rather than deciding what the target is, are exactly the sorts of boundaries that prevent a research system from quietly accumulating benchmark-specific assumptions. ([GitHub][2])

Your experimental discipline has also improved dramatically. You discovered that the old apparent 0.063 baseline was basically noise, moved toward n=30 comparisons, and started separating mechanism validation from score validation. That's professional research practice, not leaderboard hacking. ([GitHub][2])

And your latest work has uncovered something genuinely important:

**representation can be correct without being sufficient.**

The cd82 example is particularly revealing. You can represent the spatial precondition, add conjunction, and verify that the conjunction machinery works, while still failing because the actual state variable is something like *which swatch is selected*, which isn't reducible to the spatial relation you chose. ([GitHub][2])

That is a very useful discovery.

---

# 2. But here's the architectural hole I see

I would draw your current system approximately like this:

```text
                 FRAME
                   │
                   ▼
             perceptual lenses
                   │
                   ▼
          entities / identity
                   │
                   ▼
             relational state
                   │
                   ▼
              residuals
                   │
                   ▼
             hypotheses
                   │
                   ▼
            short experiments
                   │
                   ▼
                action
```

The missing box is:

```text
                 LATENT STATE
```

More specifically:

```text
                  OBSERVATIONS
                       │
                       ▼
              ┌──────────────────┐
              │ latent world     │
              │ state / belief   │
              │                  │
              │ state variables  │
              │ + values         │
              │ + uncertainty    │
              └────────┬─────────┘
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
       transition model       goal model
             │                   │
             └─────────┬─────────┘
                       ▼
                    planner
                       │
                       ▼
                    action
```

You have pieces of this already.

Your `WorldBelief`, entity identities, relations, predictors, hypotheses, supervisor, etc. are all moving toward it.

But they aren't yet **one coherent latent-state model**.

That's the thing I think you're circling.

---

# 3. The important distinction: representation vs state

This is subtle.

Suppose the game contains:

* a bucket
* a block
* three color swatches
* a template

Your representation can correctly say:

```text
bucket: CONTROL
block: AFFECT
swatch1: ENVIRONMENT
swatch2: ENVIRONMENT
swatch3: ENVIRONMENT

bucket adjacent block
block palette differs template
```

That's a good representation.

But the environment may actually have an invisible state:

```text
selected_color = RED
```

and:

```text
ACTION5:
    block.color := selected_color
```

Now consider two frames that are **visually identical**:

```text
frame A:
    selected_color = RED

frame B:
    selected_color = BLUE
```

Your perceptual representation cannot distinguish them.

Yet the optimal action can be completely different.

This is a classic **partial observability / hidden-state** problem.

And this is exactly why your cd82 finding is so interesting.

Your latest conclusion essentially says:

> "The representation can express the spatial condition, but the environment's relevant state isn't actually spatial."

I agree.

But I would go one step further:

> **The agent needs a mechanism for hypothesizing latent state variables, not merely additional predicates over visible entities.**

That's a much bigger conceptual upgrade than adding another relation.

---

# 4. This is where I think some of the high-scoring approaches differ

There are several families of competitors, and they don't all solve the same problem.

### A. Search / engineered systems

Some systems build explicit state graphs, BFS, frame-change models, segmentation, action priors, etc.

One public example describes a stack involving trigger-aware BFS, learned frame-change behavior, segmentation, state hashing and search. Another public agent is exploring an object-centric JEPA/world-model architecture. ([GitHub][3])

This family is relatively close to what you're doing.

Your advantage is that your representation is considerably more epistemically careful.

Their advantage can be **brute-force coverage of possible transitions**.

---

### B. LLM + persistent world model

The other major family is quite different.

A public ARC-AGI-3 submission describes giving an LLM a persistent "world model" note that survives turns and levels, with the model continually updating its understanding of the environment. ([Kaggle][4])

The interesting part isn't "LLM magic."

It's that the LLM is functioning as a **latent-state hypothesis generator**.

It can say:

```text
I think the red object is selected.
I think pressing ACTION5 applies the selected color.
I haven't confirmed that yet.
```

That's qualitatively different from:

```text
relation(block, swatch) = adjacent
```

The former is a hypothesis about a hidden state variable.

---

### C. Learned world models

The other important direction is object-centric predictive modeling.

One public ARC-AGI-3 project is explicitly pursuing an object-centric JEPA-style world model: learn a compact latent representation and predict future latent states rather than reconstructing pixels. ([GitHub][5])

Again, that's addressing the same fundamental gap:

> **What compact internal state is sufficient to predict what will happen if I act?**

That's the question I think your project should increasingly revolve around.

---

# 5. Your "belief" is not yet the kind of belief I mean

This is probably the most important critique.

You call `WorldBelief` a belief layer, but currently it is mostly a **belief about entity roles**:

```text
entity #7 → CONTROL
entity #12 → AFFECT
entity #15 → CONTEXT
```

and action/effect statistics.

That's useful.

But I would reserve the word **belief** for something more like:

```text
P(z_t | observations, actions)
```

where `z_t` is a latent environment state.

For example:

```text
belief:
    selected_color = red       0.72
    selected_color = blue      0.21
    selected_color = green     0.07

    switch_state = left        0.81
    switch_state = right       0.19
```

Then actions update the belief:

```text
ACTION2
    predicted:
        selected_color remains red
        bucket moves right

observation:
    bucket moved right
    block unchanged

posterior:
    selected_color = red      0.76
```

Now you've got an actual Bayesian-ish state estimator, even if you don't implement formal Bayes.

Your current system mostly asks:

> "What relationship is visible?"

The next level is:

> **"What hidden state of the environment best explains everything I've observed so far?"**

That's the jump I would make.

---

# 6. Your residual framework is actually very promising for this

This is where I would **not** throw away what you've built.

Your residual idea is good.

You currently have things like:

```text
distance(A,B)
palette_missing(A,B)
part_size_diff(A,B)
shape_diff(A,B)
```

and a hypothesis essentially says:

```text
apply action X
→ residual should decrease
```

That's elegant.

But you currently constrain hypotheses too much toward:

> "drive an existing observable residual to zero."

I'd generalize the abstraction to:

```text
Hypothesis
    latent variables
    preconditions
    transition prediction
    observable consequences
    confidence
    falsifier
```

Then:

```text
H:
    selected_color = swatch_2

    ACTION5:
        block.color ← selected_color

Prediction:
    after ACTION5,
    block palette should change toward swatch_2
```

Now the hypothesis isn't just:

```text
drive residual R to zero
```

It's:

```text
if latent state Z is true,
then action A should cause observation O.
```

That's much closer to a real world model.

---

# 7. The other big missing concept: information gain

This is the other thing I think you're underweighting.

Your agent has an implicit notion of:

> "What action is likely to accomplish something?"

But ARC-AGI-3 also requires:

> **"What action will tell me something useful?"**

Those are not the same.

Suppose you have three candidate hypotheses:

| Hypothesis | P(correct) | If tested | Information |
| ---------- | ---------: | --------: | ----------: |
| A          |        .55 |     cheap |        high |
| B          |        .80 | expensive |         low |
| C          |        .35 |     cheap |   very high |

A rational agent might choose C.

Not because it expects C to succeed.

Because **the result will discriminate between competing world models**.

That's active system identification.

I don't see this as a first-class objective in your architecture yet.

You have exploration, contingency detection, interest maps, hypotheses, etc., but they mostly operate as *useful-action selection*. I would explicitly introduce:

```text
Expected information gain
+
Expected progress
+
Action cost
+
Risk
```

as competing terms.

For example:

```text
utility(action) =
    λp * expected_progress
  + λi * expected_information_gain
  - λc * expected_cost
  - λr * expected_risk
```

And importantly, the weights should change with the agent's epistemic state.

Early game:

```text
information >> progress
```

Once the model is identified:

```text
progress >> information
```

That's a very natural ARC-AGI-3 architecture.

---

# 8. I think you're also underusing the level boundary

This part of your system is particularly valuable.

You've discovered that the level transition gives you a surprisingly strong piece of supervision.

You currently use it to remember which residuals were falling into successful transitions.

I'd elevate this substantially.

A level transition is effectively:

```text
SUCCESS
```

in a world where you otherwise receive almost no reward.

So rather than merely:

```text
what residual was decreasing?
```

I'd ask:

> **What latent state transition occurred immediately before success?**

For example:

```text
Z_t
   ↓
action sequence
   ↓
Z_{t+k}
   ↓
SUCCESS
```

Then maintain a causal trace:

```text
candidate causal chain:

swatch selected
    ↓
ACTION5
    ↓
block recoloured
    ↓
template match
    ↓
level advance
```

You don't know this initially.

But the level boundary is precisely the supervision signal that lets you discover it.

Your existing `BoundarySupervisor` is therefore potentially much more important than it looks.

---

# 9. There's an especially interesting clue in your own data

This is probably the strongest evidence for my critique.

Your representation experiments have often produced:

> **better understanding, but no score improvement.**

And you explicitly documented the principle:

> "A signal nothing acts on cannot help."

That's correct. ([GitHub][6])

But there's a second version of that principle:

> **A representation that is locally correct but doesn't predict future consequences isn't yet a world model.**

Your latest numbers are actually telling you this.

You have things like:

* identity working
* control working
* relations partially working
* goal coordinates appearing before advances
* hypotheses sometimes finding useful targets

yet the score remains tiny.

That suggests the bottleneck isn't primarily:

```text
"we don't know what the pixels mean."
```

It's closer to:

```text
"we don't know which internal state variables matter,
and therefore cannot predict the consequences of actions
well enough to act efficiently."
```

That is a substantially more interesting problem.

---

# 10. I would change your architecture in one major way

I would evolve it toward:

```text
                    FRAME
                      │
                      ▼
               PERCEPTUAL LENSES
                      │
                      ▼
              ENTITY / EVENT STATE
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
      OBSERVABLES            LATENT VARIABLES
          │                       │
          └───────────┬───────────┘
                      ▼
                WORLD BELIEF
             ┌────────┼────────┐
             │        │        │
             ▼        ▼        ▼
          state    transition  goal
          belief     model     belief
             │        │        │
             └────────┼────────┘
                      ▼
             HYPOTHESIS GENERATOR
                      │
             ┌────────┴─────────┐
             ▼                  ▼
       progress value      information value
             │                  │
             └────────┬─────────┘
                      ▼
                EXPERIMENT
                      │
                      ▼
                    ACTION
                      │
                      ▼
                  OBSERVATION
                      │
                      └──────────────► update belief
```

Notice what stays:

* your evidence-first perception
* entity tracking
* falsifiable relations
* residuals
* hypotheses
* level-boundary supervisor
* explicit routing
* LLM as hypothesis scientist

What changes is **what a hypothesis is allowed to talk about**.

---

# 11. And I would make the LLM much more ambitious than you currently do

Your H002 experiment is interesting, but I think you're asking the LLM the wrong question if the ultimate role is merely:

> "Can an LLM propose a good residual hypothesis?"

That's a fairly narrow use of a language model.

I would instead give it the job of:

### **latent-state scientist**

Input:

```text
current world belief
recent events
candidate relations
unexplained transitions
failed hypotheses
successful transitions
available actions
```

Output:

```text
latent variable hypotheses
transition hypotheses
goal hypotheses
discriminating experiments
```

For example:

```text
Hypothesis H17

Latent variable:
    selected_colour ∈ {8, 9, 10}

Evidence:
    ACTION6 at coordinates X,Y repeatedly precedes
    changes in ACTION5's effect.

Prediction:
    after selecting colour 9,
    ACTION5 will recolour the target with colour 9.

Discriminating experiment:
    select colour 8
    apply ACTION5
    observe target colour.

Falsifier:
    target changes to colour ≠ 8.
```

That's a much more powerful role.

And crucially, your existing verifier can police it.

So the LLM doesn't get to *believe* its own story.

It proposes scientific experiments.

That's a very defensible architecture.

---

# 12. There's another thing I'd steal from the competitive landscape

Not literally code. Conceptually.

The public competitors seem to fall into two extremes:

**learned policy**

```text
pixels → neural net → action
```

or

**explicit symbolic agent**

```text
pixels → objects → relations → rules → action
```

Your project is currently strongly in the second camp.

I think the winning territory is likely somewhere in between:

```text
pixels
   ↓
structured perceptual state
   ↓
learned / inferred latent dynamics
   ↓
explicit hypotheses
   ↓
search/planning
```

That is why the JEPA/object-centric world-model direction is worth watching, even if you don't adopt JEPA itself. ([GitHub][5])

The learned component doesn't need to decide actions.

It can instead learn:

> **what changes, what stays invariant, and what hidden state explains those changes.**

That would fit your philosophy extremely well.

---

# 13. One thing I would *not* do

I would **not** respond to the leaderboard by adding a giant vision model.

Nor would I replace the architecture with a frontier LLM.

Nor would I start accumulating semantic object types:

```text
player
enemy
goal
key
door
switch
hazard
```

Your insistence on not doing that is correct.

ARC explicitly describes the benchmark as requiring agents to build adaptable world models from interaction without instructions. ([ARC Prize][1])

The danger is actually the opposite:

> **Your architecture could become beautifully principled but too "symbolic" to discover latent state.**

That's the failure mode I'd guard against.

---

# 14. My ranking of your current bottlenecks

If I were sitting with you as a research collaborator, I'd rank them:

| Rank   | Bottleneck                                                                             | Severity        |
| ------ | -------------------------------------------------------------------------------------- | --------------- |
| **1**  | No unified latent-state / hidden-state model                                           | **Very high**   |
| **2**  | Hypotheses mostly operate on existing predicates rather than inventing state variables | **Very high**   |
| **3**  | Information-seeking actions aren't first-class                                         | **High**        |
| **4**  | Transition model is still shallow / mostly one-step                                    | **High**        |
| **5**  | Goal inference is still too closely tied to observable residuals                       | **High**        |
| **6**  | LLM is currently used too narrowly                                                     | **Medium-high** |
| **7**  | Representation vocabulary gaps                                                         | **Medium**      |
| **8**  | Object/composite representation                                                        | **Medium**      |
| **9**  | Perceptual robustness                                                                  | **Low-medium**  |
| **10** | More clever routing                                                                    | **Low**         |

That last one is important.

**I would stop spending much time on routing right now.**

Your router is probably not the thing preventing 0.14 → 5 → 10.

The system needs to know **what state it is trying to reach** before better navigation matters.

---

# 15. Your current score is therefore misleading

Your latest full sweep is around **0.1431**. ([GitHub][7])

That sounds terrible compared with a team reporting ~18.

But I would not interpret it as:

> "Their agent is 100× better."

The scoring landscape has enormous variance, and even public competitive writeups report substantial run-to-run variance. One public submission, for example, reported an official 1.21% score while observing materially different scores on repeated runs. ([Kaggle][4])

More importantly, you're measuring two different things:

### Their question

> "How can I maximize completed levels with this architecture?"

### Your question

> "What is the smallest principled architecture that can discover the latent structure of an unknown interactive environment?"

You're doing research on the second problem.

That's why some of your work looks "overengineered" relative to the score.

The danger is only if you never make the transition from:

```text
good representation research
```

to:

```text
representation → prediction → experiment → successful action.
```

---

# 16. If I were taking over your repo tomorrow

I would **not** add another perception primitive.

I'd build one thing:

## `LatentState`

Something deliberately tiny.

Not a giant ontology.

Something like:

```python
LatentState:
    variables:
        name
        domain
        current_belief

    transitions:
        action
        preconditions
        predicted_updates

    evidence:
        observations
        supporting_events
        contradicting_events
```

And let the system discover variables such as:

```text
selected_color
switch_state
mode
phase
orientation
target_identity
activation_state
counter_value
```

without having those names hard-coded.

The actual variable could internally just be:

```text
Z17
```

and the description can be generated afterward.

Then make the key research question:

> **Can the agent discover a latent variable when observable relations alone are insufficient to predict the next transition?**

That gives you an extremely clean experimental program.

And cd82 is already handing you your first test case.

---

# 17. The deepest compliment I can give the project

After reading it as an outsider, I **don't** think you've been blindly reinventing ARC agents.

You've independently converged on several ideas that are genuinely central:

* object/entity persistence
* action-conditioned representations
* world-state memory
* explicit hypotheses
* falsification
* transition prediction
* active experimentation
* level-boundary supervision
* persistent memory
* planning over learned dynamics

Those are exactly the ingredients ARC-AGI-3 is intended to stress. ([ARC Prize][1])

What you're missing isn't some secret "FUMO representation."

It's a **unification**.

Right now:

```text
perception
belief
relations
predictor
hypothesis
supervisor
navigation
```

are excellent research components.

I think the next leap is to make them all describe and update **one latent dynamical model of the game**.

Then your philosophy becomes much more powerful:

> **Don't assume what exists. Infer the smallest latent state that makes the observed transitions predictable.**

That, to me, is the architectural thesis I would pursue from your current codebase.

And I would make **cd82 the canonical benchmark for this transition**, because your own experiments have already demonstrated that simply adding more visible relations does not solve it. ([GitHub][2])

### One final comparison

If I had to summarize the difference in one sentence:

**Your current agent is becoming an excellent scientist of observations; the next version needs to become a scientist of hidden state.**

That's the biggest gap I see.

[1]: https://arcprize.org/competitions/2026/arc-agi-3?utm_source=chatgpt.com "ARC Prize 2026 - ARC-AGI-3 Competition"
[2]: https://github.com/nvaidyan1/arc-agi-3/blob/main/docs/plan.md "arc-agi-3/docs/plan.md at main · nvaidyan1/arc-agi-3 · GitHub"
[3]: https://github.com/AR6420/arc-agi-3-agent/blob/main/research-findings.md?utm_source=chatgpt.com "arc-agi-3-agent/research-findings.md at main · AR6420/arc-agi-3-agent · GitHub"
[4]: https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/discussion/717133?utm_source=chatgpt.com "ARC Prize 2026 - ARC-AGI-3 | Kaggle"
[5]: https://github.com/arodmor/arc-agi-3/blob/main/README.md?utm_source=chatgpt.com "arc-agi-3/README.md at main · arodmor/arc-agi-3 · GitHub"
[6]: https://github.com/nvaidyan1/arc-agi-3/blob/main/docs/system_architecture.md "arc-agi-3/docs/system_architecture.md at main · nvaidyan1/arc-agi-3 · GitHub"
[7]: https://github.com/nvaidyan1/arc-agi-3 "GitHub - nvaidyan1/arc-agi-3 · GitHub"


Yes. And I think your instinct here is **exactly right**. There are actually two separate questions hiding inside "latent space":

1. **Can the agent represent a spatial/world state at one instant?**
2. **Can it represent how that state evolves through time under actions?**

Your architecture has meaningful pieces of both already, but **the second one is much less developed than the first**. I would *not* say you need to bolt an LSTM onto the system tomorrow. I would say you need to explicitly define a **temporal latent state / transition model**, and only then decide whether a recurrent neural model is useful.

This matters even more now because the strongest public ARC-AGI-3 approaches are explicitly converging on executable world models and historical transition verification. The current community leaderboard has public systems reporting extremely high results from precisely this direction: executable world models, retrodiction of history, and persistent game models. ([ARC Prize][1])

## 1. Your current architecture already has "time," but not quite the thing you mean

From what I've seen of your architecture, you already have:

```text
frame_t
   ↓
perception
   ↓
state_t
   ↓
action_t
   ↓
frame_{t+1}
```

And you retain things like:

* action history
* pair/action statistics
* `by_action_given`
* preconditions
* observed effects
* hypotheses
* residual trajectories
* level transitions
* `WorldBelief`

So **you absolutely do not need to invent temporal memory from scratch.**

In fact, your recent conditional-lever work is already a primitive transition model:

```text
condition_t + action_t
        ↓
    effect_{t+1}
```

That's temporal.

But it is currently mostly **a collection of local transition facts**.

What I think you don't yet have is:

> **a persistent latent state whose value at time t is itself the sufficient context for predicting t+1, t+2, ...**

That's a meaningful distinction.

---

# 2. The thing you're describing is closer to a dynamical system

Suppose we have:

```text
Z_t = latent state at time t
A_t = action
O_t = observation
```

You ultimately want something conceptually like:

```text
             action_t
                ↓
Z_t ─────────────────────→ Z_{t+1}
 ↑                            ↓
 │                            │
 │                            ↓
 │                           O_{t+1}
 │
 └──────────── belief update
```

More formally:

```text
Z_{t+1} = F(Z_t, A_t)
O_t     = G(Z_t)
```

And because the environment may be partially observable:

```text
belief_t = P(Z_t | O_0:t, A_0:t-1)
```

You don't need to implement the probability equation literally.

But **that conceptual object is what I think your architecture is currently missing.**

Your current system is much closer to:

```text
O_t
 ↓
entities
 ↓
relations
 ↓
residuals
 ↓
hypotheses
```

I want to see:

```text
O_t
 ↓
belief_t
 ↓
latent state Z_t
 ↓
transition model F
 ↓
predicted Z_{t+1}
 ↓
predicted O_{t+1}
```

That is the bridge between your current architecture and a proper world model.

ARC itself describes the modeling capability as building a world model capable of predicting future states and outcomes, and explicitly says the benchmark tests memory compression and belief updates over time. ([ARC Prize][2])

---

# 3. And here's the key: I don't think an LSTM is the answer

At least **not yet**.

This is where I would strongly resist the temptation to say:

> "Oh, temporal latent state = LSTM."

An LSTM answers a different question:

> "Can a neural network learn a useful compressed representation of a sequence?"

Your problem is more fundamental:

> **What information should persist through time?**

If you haven't answered that, an LSTM will happily learn a 512-dimensional vector that you have absolutely no idea how to inspect, verify, manipulate, or plan with.

That would actually work *against* one of the strongest properties of your project.

---

# 4. I would first build a symbolic/structured temporal latent state

Something like:

```python
LatentState
    variables:
        selected_color = ?
        lever_state = ?
        mode = ?
        orientation = ?
        phase = ?
        target = ?
        inventory = ?
    
    persistent:
        ...
    
    transient:
        ...
```

Then:

```python
TransitionHypothesis

    preconditions:
        lever_state == LEFT

    action:
        ACTION_5

    state_update:
        lever_state -> RIGHT

    predicted_observation:
        ...
```

Now you can literally run:

```text
state_0
  ↓ action A
state_1
  ↓ action B
state_2
  ↓ action C
state_3
```

That's already a **temporal latent-space model**.

And crucially, it is inspectable.

---

# 5. But I would add something even more important: state compression

Here's the experiment I think you should run.

Take an actual successful trajectory:

```text
O0
A0
O1
A1
O2
A2
O3
...
O20
```

Ask:

> **What information from O0...O19 is actually required to predict O20?**

For example, perhaps the entire history collapses to:

```text
Z19:

player_position = (x,y)
selected_color = RED
switch_A = ON
switch_B = OFF
phase = 2
target = object_7
```

Everything else can be thrown away.

That's **the latent state**.

Your system currently remembers lots of history. What it doesn't yet explicitly do is determine:

> **What is the minimum sufficient summary of history for future prediction?**

That is the temporal version of your existing "don't introduce representations without evidence" philosophy.

---

# 6. This gives you a very nice research principle

You already have something like:

> Don't represent semantic entities unless the observations justify them.

Extend it:

> **Don't retain historical information unless it changes the predictive distribution over future observations.**

That's beautiful for this project.

For example:

```text
History:
    player moved left
    player moved right
    player moved up
    player moved down
```

might be irrelevant.

But:

```text
History:
    player pressed red switch
```

may matter forever.

So your model should discover:

```text
switch_red_activated = TRUE
```

and then compress the preceding 50 actions away.

That's exactly the kind of memory compression humans appear to perform.

And ARC explicitly calls out memory compression as part of what ARC-AGI-3 is intended to measure. ([ARC Prize][2])

---

# 7. This also clarifies what "latent space" should mean for you

I would actually distinguish three layers.

### Layer 1: perceptual state

What is visibly present?

```text
objects
positions
colors
shapes
```

### Layer 2: relational state

How are visible things related?

```text
A adjacent B
A contains B
A aligned B
A differs_from B
```

### Layer 3: dynamical latent state

What invisible/internal state determines what happens next?

```text
selected_color
mode
phase
switch_state
orientation
activation
ownership
progress
```

Then:

```text
          OBSERVATION
               ↓
       perceptual state
               ↓
       relational state
               ↓
      latent dynamical state
               ↓
       transition model
               ↓
       future prediction
```

**I think your current architecture is strong through Layer 2 and is beginning to touch Layer 3.**

That's why I don't think you need another giant perception system.

---

# 8. And then comes the really exciting part: imagined trajectories

Once you have:

```text
Z_t
```

and:

```text
F(Z_t, A)
```

you can do:

```text
Z_t
 ├── A1 → Z_t+1
 │          └── A3 → Z_t+2
 │
 ├── A2 → Z'_t+1
 │          └── A4 → Z'_t+2
 │
 └── A5 → Z''_t+1
```

You can compare them against the goal.

That is where your existing hypothesis/residual machinery becomes much more powerful.

Instead of:

> "Which action should I try?"

you get:

> "Which sequence of actions, according to my current world model, should move the latent state toward the goal?"

That's actual planning.

---

# 9. This is also where the recent high-performing systems are giving you a useful signal

The public systems are increasingly doing something surprisingly close to this, although with very different implementations.

For example, the executable-world-model work explicitly maintains a programmatic model, verifies it against observations, and plans through that model. ([arXiv][3])

Tycho goes even further: it constructs models from structured history, tests and repairs them, and separates the problem of accurately reproducing transitions from deciding whether using that model is worthwhile. Its authors call the broader problem **active abstraction**. ([arXiv][4])

That is extremely relevant to your project.

Because I think your eventual architecture could be:

```text
              OBSERVATIONS
                   ↓
             structured state
                   ↓
          ┌─────────────────┐
          │ latent dynamics │
          │                 │
          │ Z_t + A → Z_t+1 │
          └────────┬────────┘
                   ↓
             imagined rollout
                   ↓
             candidate plan
                   ↓
                ACTION
                   ↓
              observation
                   ↓
             model correction
```

That is much more powerful than simply adding predicates.

---

# 10. So where would an LSTM/LMU fit?

**After** you have the above.

Then I would absolutely consider one.

There are three possible levels.

### Level A: no neural temporal model

Start here.

```text
Z_t = explicit structured state
Z_{t+1} = symbolic transition
```

This is the experiment I would do first.

### Level B: recurrent latent memory

Then try:

```text
h_t = GRU(h_{t-1}, observation_t, action_t)
```

or an LSTM/LMU-like state-space model.

But use `h_t` for **unknown residual information**, not as a replacement for your explicit state.

Something like:

```text
Z_t = explicit known state
h_t = learned residual memory
```

That's much more interesting.

### Level C: learned dynamics

Eventually:

```text
Z_t + A_t
      ↓
neural transition model
      ↓
Z_{t+1}
```

Now you're approaching the JEPA/RSSM/world-model territory. There are already public ARC-AGI-3 experiments exploring action-conditioned latent prediction and recurrent state-space models, including GRU-based latent dynamics. ([Hugging Face][5])

But I would **not start there**.

---

# 11. Your LMU idea is actually intellectually interesting

Because your project is fundamentally about:

> **long-horizon temporal structure with sparse meaningful events**

a long-memory state-space architecture is arguably more conceptually appropriate than an LSTM.

But I'd treat this as a later experiment, not architecture V-next.

The research question would be:

> Can a learned continuous temporal state retain information about latent environment variables that the symbolic model hasn't yet discovered?

That's a very clean experiment.

For example:

```text
Explicit state:
    position
    objects
    relations
    known switches

Learned memory:
    h_t
```

Then test whether `h_t` improves prediction of:

```text
O_{t+k}
```

for k = 1, 5, 10, 20.

If it doesn't, you don't need it.

If it does, **then you've demonstrated a real missing capability** rather than adding an LSTM because temporal models are fashionable.

---

# 12. What I would actually do over the next 7 days

I would *not* attempt the entire architecture I proposed earlier.

I'd make this a **one-week "temporal world model sprint."**

### Day 1: Formalize the state

Create:

```text
LatentState
Transition
Prediction
Belief
```

Don't implement learning yet.

Just define exactly what each means.

The most important question:

> What is allowed to persist from t to t+1?

---

### Day 2: Build trajectory reconstruction

Given:

```text
O0, A0, O1, A1, ... On
```

produce:

```text
S0 → S1 → S2 → ... → Sn
```

where each `S` contains your current explicit state.

Then verify:

```text
predict(S_t, A_t) == S_{t+1}
```

This will immediately expose how much of your existing system is actually temporal.

---

### Day 3: Build multi-step prediction

Don't stop at:

```text
S_t + A → S_t+1
```

Do:

```text
S_t
 + A1 → S_t+1
 + A2 → S_t+2
 + A3 → S_t+3
```

Now you've got a genuine world-model test.

---

### Day 4: Hidden-state challenge

Use cd82 and several other levels where your current representation fails.

For each one ask:

> "What variable would make the next transition predictable?"

Not:

> "What new relation do I need?"

That distinction is crucial.

Create candidate variables such as:

```text
mode
phase
selection
activation
orientation
ownership
progress
```

but don't hard-code those as universal semantics. Treat them as candidate latent variables.

---

### Day 5: Hypothesis → latent variable

Upgrade your hypothesis object.

Currently:

```text
Hypothesis:
    relation
    condition
    action
    effect
```

Move toward:

```text
Hypothesis:
    latent variable
    candidate value
    evidence
    action
    predicted transition
    falsifier
```

Now your hypothesis engine can discover hidden state.

---

### Day 6: Planning through the model

Implement something deliberately dumb:

```text
for candidate action sequence:
    simulate through current model
    calculate expected goal progress
    rank sequences
```

Even depth 2–4 would be enough initially.

The point is not performance.

The point is proving:

> **The latent model is usable for action selection.**

---

### Day 7: Ablation

Run:

```text
A: current architecture

B: current + explicit latent state

C: current + latent state + multi-step prediction

D: current + latent state + planning
```

And measure:

1. prediction accuracy
2. number of unnecessary actions
3. hypothesis survival/falsification
4. level completion
5. score

That will tell you **which layer is actually buying you something**.

---

# 13. And I would add one particularly important metric

Don't just measure score.

Measure:

## **Predictive sufficiency**

For each timestep:

> Given the current internal state, can I predict the next observation after each possible action?

For example:

```text
                 prediction accuracy

             1-step     3-step     10-step

current         61%        24%        5%
latent-v1       84%        62%       31%
latent-v2       91%        78%       55%
```

That would be **fantastic research data**.

Because then you can see whether you're genuinely building a world model even before the benchmark score moves.

---

# 14. There's one subtle thing I would change from my previous answer

I previously emphasized:

> "Build a latent-state model."

After thinking through your question more carefully, I'd make it:

> **Build a temporal latent-state model, not merely a latent representation.**

The word **temporal** is doing a lot of work.

A static latent embedding:

```text
frame → z
```

is not enough.

You want:

```text
(history, action) → z_t → predicted z_{t+1}
```

and eventually:

```text
z_t + action sequence → imagined future trajectory
```

That's the thing that turns your representation work into an actual **world model**.

---

# 15. And this makes your architecture's eventual shape much clearer

I now picture your system as:

```text
                         ┌───────────────┐
                         │   OBSERVATION │
                         └───────┬───────┘
                                 ↓
                    ┌─────────────────────┐
                    │ perceptual state    │
                    │ objects / geometry  │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ relational state    │
                    │ spatial structure   │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ LATENT STATE        │
                    │ hidden variables    │
                    │ + uncertainty       │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    ↓                     ↓
             transition model       goal model
                    │                     │
                    ↓                     ↓
             imagined future        target state
                    └──────────┬──────────┘
                               ↓
                           planner
                               ↓
                             action
                               ↓
                         new observation
                               │
                               └──────────────┐
                                              ↓
                                      belief update
```

And **only the latent-state box needs to eventually have a learned recurrent component**.

That is an important architectural boundary.

You don't need:

```text
LSTM everywhere
```

You might eventually have:

```text
explicit state
      +
learned temporal residual
```

which I actually think is much more interesting for *your* project.

---

## My strongest recommendation

For the next week, **do not build an LSTM or LMU yet.**

Build the **interface that an LSTM/LMU would eventually plug into**.

Specifically:

> `LatentState_t + Action_t → LatentState_{t+1}`

Then make the system capable of asking:

1. What parts of the current state are persistent?
2. What changed because of the action?
3. What hidden variable would explain that change?
4. Can my current latent state predict the next observation?
5. Can I roll it forward several steps?
6. If two histories look identical now, does my model correctly distinguish them because their latent states differ?

**That sixth question is the killer test.**

If you can construct a pair of histories:

```text
History A ──→ visually identical frame
History B ──→ visually identical frame
```

but:

```text
optimal action(A) ≠ optimal action(B)
```

then you have found a genuine hidden-state problem.

And that is exactly where a temporal latent model earns its keep.

So I would make **"find and represent histories that are observationally equivalent but behaviorally different"** one of the central experiments of your next week.

That's the point where your current representation program becomes a real dynamical world-model program, rather than simply growing a richer ontology. And it aligns extremely well with what ARC-AGI-3 is explicitly trying to measure: adaptation across time, persistent beliefs, modeling future states, and long-horizon planning. ([ARC Prize][2])

[1]: https://arcprize.org/leaderboard/community?utm_source=chatgpt.com "ARC Prize - Community Leaderboard"
[2]: https://arcprize.org/arc-agi/3?utm_source=chatgpt.com "ARC-AGI-3"
[3]: https://arxiv.org/abs/2605.05138?utm_source=chatgpt.com "Executable World Models for ARC-AGI-3 in the Era of Coding Agents"
[4]: https://arxiv.org/abs/2607.28287?utm_source=chatgpt.com "Tycho: Active Abstraction with Programmatic World Models for ARC-AGI-3"
[5]: https://huggingface.co/guychuk/arc-agi-3-grid-jepa/blob/95bf5e7188d914ac2f163f4f32496074fdaffd26/docs/architecture.md?utm_source=chatgpt.com "docs/architecture.md · guychuk/arc-agi-3-grid-jepa at 95bf5e7188d914ac2f163f4f32496074fdaffd26"
