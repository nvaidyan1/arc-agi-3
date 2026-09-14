Yes. I went through both documents as a system-design/research artifact rather than merely reading them as a project plan, and I also checked the current ARC-AGI-3 specification and recent public work. My overall judgment is:

> **You are going in a very strong direction scientifically, but I think your current architecture has one major conceptual risk: you are becoming exceptionally good at building an evidence-disciplined *description* of the world, while the competition's hardest problem is deciding which latent model of the world is worth acquiring and acting on.**

That distinction matters enormously.

Your work is much more rigorous than the typical "throw a VLM at the game and hope" ARC-3 approach. In particular, the insistence on falsifiability, explicit measurement, second-game derivation, and separating representation quality from behavioral improvement is excellent. The official benchmark explicitly identifies **exploration, modeling, goal-setting, and planning/execution** as the four capabilities being tested, and your system is strongest on modeling and increasingly strong on exploration/planning. ([ARC Prize][1])

But I would now shift the center of gravity substantially toward **goal inference + hypothesis formation + temporal/conditional world models + deliberate experimentation**.

---

# 1. My high-level assessment

I'd characterize your current system like this:

| Dimension                           | My assessment                                                                                    |
| ----------------------------------- | ------------------------------------------------------------------------------------------------ |
| Scientific methodology              | **Excellent**                                                                                    |
| Measurement discipline              | **Excellent**                                                                                    |
| Avoidance of game-specific ontology | **Excellent**                                                                                    |
| Perceptual representation           | **Strong**                                                                                       |
| Entity tracking                     | **Strong**                                                                                       |
| Action-effect learning              | **Strong**                                                                                       |
| Relational representation           | **Promising**                                                                                    |
| Exploration                         | **Moderate**                                                                                     |
| Planning                            | **Moderate, currently narrow**                                                                   |
| Goal discovery                      | **Weak / central bottleneck**                                                                    |
| Temporal/conditional modeling       | **Weak**                                                                                         |
| Hypothesis generation               | **Promising but underpowered**                                                                   |
| LLM integration                     | **Not yet demonstrated**                                                                         |
| Generalization argument             | **Conceptually strong, empirically still thin**                                                  |
| Main danger                         | **Overengineering representation before proving what representation the planner actually needs** |

The most important thing is that I **would not throw away your architecture**.

I would change what it is *for*.

Your own measurements already tell you this. You have repeatedly added representation layers that produce elegant descriptions but zero score improvement. Then the first consumer of the representation produced a substantial behavioral change. Your document explicitly records that pattern: recording-only layers had no score effect, whereas the first layer that consumed the brief changed the median substantially. 

That is one of the strongest findings in your whole project.

---

# 2. The most important thing you have gotten right

## "No semantic slots without evidence" is an excellent principle

I think this is genuinely valuable, rather than merely a philosophical preference.

Your distinction between:

> semantic ontology: *player, goal, enemy, resource*

and

> relational ontology: *entity, transition, relation, contingency, hypothesis*

is very useful.

The former can accidentally solve the problem by assuming the answer.

The latter lets you discover that something behaves like a goal without calling it a goal beforehand.

Your `None` semantics are particularly good:

> Unknown is `None`, never `False`.

That is exactly the kind of epistemic discipline that prevents a system from turning lack of evidence into negative evidence. Your plan repeatedly tests this idea, including ambiguous movement, stamina detection, translation, and relation detection. 

I would **keep this principle**.

But I would add a second principle:

> **No hypothesis without an experiment.**

You have the first half very strongly. You now need the second half just as strongly.

Your architecture currently asks:

**What can I infer from what has happened?**

It needs to become increasingly capable of asking:

**What should I do next in order to distinguish the hypotheses I currently have?**

That is a much deeper agentic problem.

---

# 3. The biggest conceptual hole: you're modeling observations more than interventions

This is the biggest thing I would change.

Right now the architecture roughly looks like:

```text
observation
    ↓
perception
    ↓
entities
    ↓
control / constraints / relations
    ↓
brief
    ↓
hypothesis
    ↓
action
```

That's good.

But I think the more powerful abstraction is:

```text
                         ┌───────────────┐
                         │  Hypotheses   │
                         │ H1 H2 H3 ...  │
                         └───────┬───────┘
                                 │
                         choose experiment
                                 │
                                 ▼
Observation ──→ World Model ──→ Intervention
      ▲                              │
      │                              ▼
      └──────── predicted outcome ←──┘
```

In other words, **the action is not merely an attempt to make progress.**

It is also an experiment designed to discriminate between competing models.

That is much closer to what humans are doing in these games.

For example:

> "ACTION5 changed the block."

is useful.

But:

> "Hypothesis A: ACTION5 paints whichever region is currently adjacent to the bucket."

versus

> "Hypothesis B: ACTION5 paints according to the bucket's orientation."

is vastly more powerful.

Now your next action is not:

> "Try ACTION5 because it seems useful."

It is:

> "Move the bucket to a configuration in which A and B predict different outcomes, then execute ACTION5."

That is **active system identification**.

And I think this is the biggest upgrade available to your architecture.

---

# 4. Your residual framework is good, but you are making residuals carry too much weight

I like your residual formulation.

It's elegant:

```text
relation → residual
0       → satisfied
>0      → distance from satisfaction
None    → undecidable
```

And the insistence on not introducing arbitrary similarity thresholds is intellectually clean.

But there's a problem.

Some ARC games don't naturally have a **scalar monotonic progress variable**.

You are implicitly privileging:

```text
state → residual → decrease → goal
```

That works beautifully for things like:

```text
distance(object, target)
part_size_diff(A,B)
palette_missing(A,B)
```

But consider a rule like:

> "Press A, then B, then A."

Or:

> "Only when X is active can Y be manipulated."

Or:

> "Touch object A, then move object B to the location A previously occupied."

Or:

> "The third time you do something, the state changes."

There may be **no useful monotonic residual**.

Your own document already recognizes this hole:

> no temporal or conditional structure beyond eight steps of events and per-action levers. 

I think this is more important than several of the remaining representation tasks.

---

# 5. I would introduce an explicit transition/hypothesis layer

Not another perception layer.

Not another ontology.

A **transition model**.

Something like:

```python
TransitionHypothesis(
    condition = C,
    action = A,
    predicted_change = Δ,
    confidence = ...
)
```

where `C` could eventually be composed from relational evidence.

For example:

```text
IF
    bucket is adjacent to block
AND
    bucket is on left side
AND
    ACTION5

THEN
    left-facing block region changes colour
```

Or:

```text
IF
    object A overlaps object B
AND
    ACTION2

THEN
    A disappears
AND
    B grows
```

Notice that this does **not** require semantic labels.

It's still your epistemic philosophy.

You're simply moving from:

> "What relationships exist?"

to:

> "What transition rule explains the relationships?"

That is a very important step.

---

# 6. This is where the recent research strongly validates your direction

There is a particularly relevant recent ARC-AGI-3 paper: **Tycho: Active Abstraction with Programmatic World Models for ARC-AGI-3**.

It describes an agent that constructs game-specific executable models, tests them against observations, repairs them, and decides when constructing/using/bypassing a model is worthwhile. The authors explicitly frame the problem as **active abstraction** rather than merely world-model construction. ([arXiv][2])

That distinction maps remarkably well onto what your project is approaching.

Even more interestingly, another recent study compared textual agents, executable world models, simplification, and verification. Its conclusion was that executable modeling isn't universally beneficial by itself; **verification** was consistently valuable, and stronger models/reasoning effort mattered substantially. ([arXiv][3])

So I would *not* conclude:

> "I need to copy Tycho and build a giant executable simulator."

Instead, I would take the more general lesson:

> **A world model is valuable only insofar as it improves the next intervention.**

That fits your own empirical findings almost perfectly.

---

# 7. Your LLM architecture is actually better than simply "put an LLM in the loop"

This part I really like.

You're not proposing:

```text
frame → LLM → action
```

You're proposing:

```text
structured evidence
       ↓
      brief
       ↓
 hypothesis proposer
       ↓
 structured Hypothesis
       ↓
 verifier
       ↓
 action
```

That's a much better interface.

Your current `Hypothesis` abstraction is particularly important because it prevents the LLM from becoming an uncontrolled policy generator.

Your document says:

> brief in, `Hypothesis` out

and then verification occurs through residual movement. 

**Keep that.**

But I would change the output schema.

Currently you're essentially asking the LLM to produce:

```text
target relation
progress coordinate
action
```

I'd make it produce something closer to:

```text
Hypothesis:
    preconditions
    predicted transition
    candidate action
    target entity/pair
    expected evidence
    falsifier
    action cost
    information gain
    confidence
```

The crucial addition is:

### `falsifier`

The LLM should explicitly say:

> "What observation would make me abandon this hypothesis?"

That fits your entire scientific philosophy.

---

# 8. And I'd add "information gain" to the hypothesis interface

This may be the single most useful new field.

Suppose the agent has:

```text
H1: ACTION5 paints the target.
H2: ACTION5 rotates the target.
H3: ACTION5 changes whatever is closest to the bucket.
```

A dumb planner asks:

> Which hypothesis seems most likely?

A stronger agent asks:

> Which action gives me the most useful information per action?

That produces an acquisition policy:

```text
utility(action) =
    expected_task_progress
  + λ × expected_information_gain
  - μ × action_cost
```

You don't need to calculate Bayesian information gain initially.

A coarse empirical approximation is enough:

```text
information_gain =
    number_of_live_hypotheses_discriminated
```

This gives you a principled exploration mechanism.

And importantly, it turns exploration from:

> random epsilon

into:

> **structured uncertainty reduction**.

That is much closer to the benchmark's stated exploration requirement. ARC-AGI-3 explicitly describes exploration as actively obtaining information from the environment, not merely passively observing it. ([ARC Prize][1])

---

# 9. Your current "lever" concept has a subtle weakness

This is one of the more important technical gotchas.

You define a lever as roughly:

> the action that moves a residual more than other actions do.

That's useful.

But **causal action selectivity is not necessarily the same thing as goal relevance**.

You already discovered this in cd82.

An action can have:

```text
very strong causal effect
```

and still be:

```text
completely irrelevant to winning
```

Conversely, an action may have no obvious effect until a precondition is satisfied.

For example:

```text
ACTION5
```

might do nothing when the bucket is far away, but become decisive when adjacent.

Your current statistics can therefore conclude:

```text
ACTION5: no lever
```

when the correct hypothesis is:

```text
ACTION5 is a conditional lever.
```

This is exactly the gap you have started to encounter.

---

# 10. So I'd split "lever" into unconditional and conditional causality

Something like:

```text
Direct lever:
    A → Δ

Conditional lever:
    (C ∧ A) → Δ
```

Then the proposer can discover:

```text
ACTION5
```

has no unconditional effect,

but:

```text
distance(bucket, block) == 1
```

is a candidate precondition.

This is much more powerful than simply increasing exploration.

---

# 11. Your treatment of the LLM should therefore change slightly

Don't make the LLM the "goal finder."

Make it the **hypothesis generator over a constrained scientific interface**.

That's a subtle but important difference.

I'd structure its job as:

### Layer 1: perception

Deterministic, conservative.

### Layer 2: relational state

Deterministic / statistical.

### Layer 3: transition evidence

Observed causal relationships.

### Layer 4: hypothesis generation

LLM + enumerator.

### Layer 5: experiment selection

Agent decides which hypothesis is most worth testing.

### Layer 6: verification

Deterministic.

### Layer 7: planning

Once a hypothesis is sufficiently confirmed.

This makes the LLM a **scientist**, not a controller.

That is a much stronger research story.

---

# 12. There is another major thing missing: predictive world models

Right now much of your representation is retrospective:

> "What happened?"

You have good answers to that.

But the real jump is:

> "What will happen if I do X?"

The current architecture has some prediction implicitly:

```text
learned_moves
blocked moves
route_expected_position
```

but this is mostly for spatial movement.

You need a generalized prediction interface:

```python
predict(state, action) -> predicted_state / predicted_transition
```

Initially it can be tiny:

```text
predict:
    entity displacement
    colour change
    size change
    appearance/disappearance
    relation change
```

Then your verification loop becomes much more principled:

```text
Observed:
    ACTION5 → part_size_diff decreases 4

Model:
    ACTION5 → part_size_diff decreases 4

Prediction error:
    0
```

That gives you a real world model without needing to build a complete simulator.

---

# 13. The "brief" is good, but I think it's currently too human-semantic

This is subtle.

Your ~45-line brief is elegant, but you're making it readable for a hypothetical proposer.

That is good.

However, I would strongly consider maintaining **two representations**:

### Machine state

Rich structured representation:

```python
entities
relations
transition_statistics
hypotheses
uncertainties
history
```

### Cognitive brief

Compressed projection:

```text
THINGS
CONTROL
RELATIONS
FALLING
OPEN
RECENT
...
```

Then explicitly test:

> Does the brief preserve the information necessary for selecting the next useful intervention?

You are already beginning to do this with your recall tests, which is excellent. 

But I would make the test stronger:

### Don't only test whether the goal is mentioned.

Test whether the **optimal next experiment is recoverable from the brief**.

For example:

> Given this brief, can a model select the same diagnostic action as an oracle with access to the full state?

That is a much better information bottleneck test.

---

# 14. Your "oracle read" experiment is good, but I'd upgrade it

You currently test:

> "state the goal and first three moves."

That's useful, but it conflates two things:

1. Can the representation communicate the goal?
2. Can the model plan?

Separate them.

I'd run three tests:

### Test A: State reconstruction

Given the brief:

> What entities/relations exist?

### Test B: Goal inference

Given the brief:

> What states appear desirable?

### Test C: Action selection

Given the brief + available actions:

> Which action should be taken next, and why?

The third one is the most important.

And ideally:

### Test D: counterfactual selection

> If ACTION3 had instead been pressed, what would you expect?

That directly tests whether the representation supports a world model rather than merely a description.

---

# 15. You are underestimating temporal structure

This is probably your second-largest technical gap after goal inference.

You currently have:

> recent eight steps

That's useful as a log.

But a log isn't a temporal model.

Consider:

```text
A → B → C
```

versus:

```text
A → B
A → C
```

The same individual transitions can appear in both.

What matters is **conditional structure**.

I would introduce a minimal event grammar:

```text
event:
    action
    pre-state predicates
    transition
    post-state predicates
```

Then learn rules such as:

```text
IF R1
AND action=A
THEN R2
```

and eventually:

```text
IF R1
THEN A
THEN B
```

Don't build a giant temporal logic system.

Start with **one-step conditional transitions**.

If that works, extend to two-step dependencies.

---

# 16. Your "kinds" mechanism is interesting, but I would deprioritize it

This is one place where I would be more ruthless.

The idea:

> same palette + same part structure → same kind → transfer knowledge

is plausible.

But it is currently much less important than:

* conditional transitions
* goal discovery
* experiment selection
* action preconditions
* predictive modeling
* click hypotheses

You have limited development time.

I would rank your remaining work roughly:

### Tier 1: do immediately

1. **Conditional action effects**
2. **Hypothesis exploration / never-tried-action problem**
3. **Predictive transition model**
4. **Goal inference**
5. **Action/experiment selection**
6. **Click-driven hypotheses**

### Tier 2

7. Temporal multi-step rules
8. Better planner
9. Hypothesis memory / confidence
10. Kind transfer

### Tier 3

11. More elaborate ontology
12. More sophisticated geometric relations
13. More object descriptors
14. Additional grouping mechanisms

This is consistent with your own empirical lesson that representation which nobody consumes doesn't improve score. 

---

# 17. The click problem is bigger than it looks

I would elevate this.

You currently have a good click mechanism:

> where should I click?

But your hypothesis interface apparently doesn't yet support:

> **what coordinate should I test?**

That is a serious asymmetry.

For discrete actions you have:

```text
action → effect
```

For click you need:

```text
(action, coordinate) → effect
```

That's effectively a **continuous/large discrete action space**.

Your current salience/interest map is not enough because, as you've correctly discovered:

> where change occurs ≠ where the goal is.

The solution I'd investigate is **coordinate-conditioned causal mapping**.

Instead of:

```text
ACTION6 → click
```

learn:

```text
ACTION6(x,y) → Δ
```

and represent spatial regions hierarchically:

```text
screen
 ↓
candidate regions
 ↓
object
 ↓
boundary / centroid / cells
 ↓
specific coordinate
```

Then a hypothesis could be:

```text
click(object A)
    → object B changes
```

rather than:

```text
click(x=31,y=42)
    → something changed
```

That is far more transferable.

---

# 18. Another subtle issue: your architecture is extremely conservative

This is both its strength and its weakness.

Your principle is essentially:

> Don't believe anything until evidence supports it.

Excellent.

But ARC-3 also requires **inductive bias**.

The official benchmark isn't designed to reward an agent that has literally zero assumptions. It is designed around environments using core knowledge priors and human-solvable abstractions. ([arXiv][4])

Humans absolutely bring priors:

* objects tend to persist
* identical shapes may have identical functions
* spatial proximity often matters
* repeated structures often share rules
* actions usually have consistent effects
* symmetry is meaningful
* containment can matter
* simpler explanations are preferable

Your system currently seems worried about all of these becoming ontology leakage.

I think you're slightly overcorrecting.

The better distinction is:

> **A prior is acceptable if it biases hypothesis search without being promoted to fact.**

For example:

```text
prior:
    similar objects may behave similarly

evidence:
    object A and B respond identically twice

hypothesis:
    transfer A's rule to B

verification:
    test B
```

That's much more powerful than banning the prior altogether.

---

# 19. This is where MDL / simplicity could help you

I would seriously consider adding an explicit:

> **simplicity prior over hypotheses**

Not as a hardcoded game ontology.

Something like:

```text
score(H) =
    evidence_fit
    - λ * complexity(H)
```

where complexity penalizes:

* number of conditions
* number of entities
* number of temporal steps
* number of exceptions
* arbitrary coordinates
* arbitrary constants

This is very ARC-like.

And it has a beautiful interaction with your philosophy:

> You don't need to know which abstraction is correct.

You generate several explanations and prefer the one that explains the observations with the least machinery.

Recent ARC-AGI-3 work has independently explored model simplification/MDL-like pressure, although the empirical picture is nuanced and verification appears especially important. ([arXiv][5])

---

# 20. Your experimental methodology is one of the strongest parts of the project

Honestly, this is unusually good.

The following are exactly the habits I'd preserve:

### Frozen-tree A/B testing

Absolutely.

### n=30 rather than n=3

Absolutely.

### Median rather than mean

Absolutely, given your heavy-tailed score distribution. Your measured variance floor makes that decision defensible. 

### Seed pairing

Excellent.

### Testing affected games separately

Very important.

You correctly discovered that an effect on four games can disappear into the aggregate 25-game score. 

### Measuring representation separately from score

Excellent.

### Synthetic tests when real examples don't exist

Good engineering practice.

### Recording failures rather than deleting them

Excellent research hygiene.

I would keep all of this.

---

# 21. One methodological improvement: distinguish three kinds of evidence

Right now your experiments sometimes blur:

### A. Representation validity

> Does the detector correctly describe what happened?

### B. Predictive validity

> Does the representation predict what happens next?

### C. Behavioral utility

> Does using it improve score?

These are different.

I'd formalize the experiment table:

| Layer       | Question                           | Metric              |
| ----------- | ---------------------------------- | ------------------- |
| Perception  | Did we identify the event?         | precision/recall    |
| State       | Is identity stable?                | ID switches         |
| World model | Can we predict transition?         | prediction error    |
| Hypothesis  | Does proposed rule survive tests?  | verification rate   |
| Goal        | Does target predict level advance? | advance attribution |
| Planner     | Does plan reach target?            | action efficiency   |
| Policy      | Does it improve game score?        | RHAE                |

This will make the project much easier to reason about.

---

# 22. You also need a "negative result taxonomy"

This would be extremely useful.

Suppose a hypothesis fails.

There are at least five possibilities:

```text
H failed because:

1. perception was wrong
2. entity identity was wrong
3. hypothesis was wrong
4. action was correct but precondition wasn't met
5. action was correct but target was wrong
6. hypothesis was correct but execution/planning failed
7. hypothesis was correct but goal inference was wrong
```

Right now these can collapse into:

> "hypothesis falsified."

That's dangerous.

A failed experiment is itself evidence about **which layer is deficient**.

I'd make the verifier return:

```text
SUPPORTED
FALSIFIED
INCONCLUSIVE
PRECONDITION_UNMET
EXECUTION_FAILURE
OBSERVATION_FAILURE
```

That could dramatically improve learning efficiency.

---

# 23. Your supervisor is promising, but there is a danger in using level transitions as the primary teacher

The level boundary is your only genuinely certified reward signal.

That's good.

But:

> "what was falling immediately before success"

doesn't necessarily mean:

> "what caused success."

This is classic temporal credit-assignment ambiguity.

Suppose:

```text
A
B
C
D
E  ← level transition
```

and:

```text
C
```

was the actual causal trigger.

Your system may identify:

```text
D → falling residual
E → falling residual
```

and conclude incorrectly that D/E are important.

You need some form of **counterfactual validation** where possible.

For example:

> "If this residual is truly the objective, does deliberately moving away from it cause failure?"

or:

> "If this action is truly the goal action, does repeating it under equivalent conditions reproduce progress?"

This is another reason the hypothesis/verifier architecture is so important.

---

# 24. I would change your concept of "goal"

I don't think the agent should necessarily maintain:

```text
the goal
```

as a single object.

Instead:

```text
candidate goals:
    G1
    G2
    G3
```

with confidence.

Something like:

```text
G1:
    shape_diff(template, block) → 0
    evidence: 4
    actionability: high
    simplicity: high

G2:
    distance(bucket, block) → 0
    evidence: 2
    actionability: medium
```

Then the planner chooses among candidate goals.

This is important because early in an ARC game **goal inference is itself uncertain**.

The benchmark explicitly calls out goal-setting as a separate capability. ([ARC Prize][1])

Your architecture currently treats hypothesis generation as the main uncertainty mechanism, but I think you need uncertainty at the **goal level** too.

---

# 25. This also fixes a philosophical tension in your architecture

You say:

> game type is an output, never an architectural input.

I agree.

But you don't need:

```text
game type
```

to get:

```text
strategy family
```

You can infer a **policy affordance**:

```text
movement affordance
matching affordance
collection affordance
avoidance affordance
construction affordance
sequencing affordance
```

without naming the game.

The agent doesn't need to conclude:

> "This is a Sokoban-like game."

It can conclude:

> "I have a controllable object, static barriers, and a residual whose minimum requires moving the controllable object."

That's enough to activate navigation.

Similarly:

> "I have two spatially related structures and one action changes their correspondence."

activates matching.

That's not semantic game classification.

It's **decision-relevant abstraction**.

I think this is the sweet spot for your architecture.

---

# 26. Your architecture currently has too many "views" and not enough "models"

This is perhaps my strongest architectural criticism.

You have:

* entities
* beliefs
* relations
* groups
* kinds
* brief
* interest
* control
* constraints
* supervisor

These are increasingly sophisticated **views over observations**.

What you're missing is a central object that says:

> **Here is my current causal model of this environment.**

Not necessarily a giant `WorldState`.

Something like:

```text
WorldModel
    entities
    relations
    transition_rules
    candidate_goals
    action_models
    uncertainties
    history
```

Importantly, this isn't the old semantic `WorldState` you rejected.

It is a **hypothesis-bearing causal model**.

That distinction matters.

Your current architecture has a very good epistemology but lacks a sufficiently explicit place where the agent says:

> "Here is what I currently believe will happen if I do X."

---

# 27. I would therefore make your architecture look more like this

```text
                 ┌────────────────────────┐
                 │     RAW OBSERVATION    │
                 └───────────┬────────────┘
                             ↓
                 ┌────────────────────────┐
                 │       PERCEPTION       │
                 │ events / entities      │
                 └───────────┬────────────┘
                             ↓
                 ┌────────────────────────┐
                 │      WORLD MODEL       │
                 │ relations              │
                 │ action effects         │
                 │ transition rules       │
                 │ uncertainties          │
                 └───────────┬────────────┘
                             ↓
             ┌───────────────┴────────────────┐
             ↓                                ↓
      Candidate goals                  Candidate hypotheses
             │                                │
             └───────────────┬────────────────┘
                             ↓
                  ┌─────────────────────┐
                  │ EXPERIMENT SELECTOR │
                  │                     │
                  │ progress            │
                  │ information gain    │
                  │ cost                │
                  │ risk                │
                  └──────────┬──────────┘
                             ↓
                          ACTION
                             ↓
                         OBSERVATION
                             │
                             └──────────→ verify / update
```

That is where I think your project should go.

---

# 28. And the LLM sits in one very specific place

I'd put the LLM here:

```text
                 WORLD MODEL
                      │
             ┌────────┴────────┐
             │                 │
        enumerator          LLM proposer
             │                 │
             └────────┬────────┘
                      ↓
                hypotheses
                      ↓
               deterministic
               experimenter
```

The LLM should **not** directly select actions whenever possible.

Its job is to propose abstractions that your deterministic machinery can test.

This also makes the system much more scientifically interesting than "Qwen plays ARC."

---

# 29. One important reality check from the current competition

The public competition landscape is already telling you something interesting.

The current leaderboard has substantially higher-scoring systems than the kind of handcrafted symbolic agent you are building, and public writeups describe approaches using local VLMs/coding agents with persistent world-model notes and tool access. ([Kaggle][6])

Tufa Labs' Duck, for example, uses a local Qwen model, a Python REPL, persistent world-model notes, segmentation tooling, and deliberate context management. ([Kaggle][7])

That means I would **not** recommend trying to beat those systems by making your hand-coded perception stack endlessly more elaborate.

Your comparative advantage is elsewhere:

> **Build a compact, verifiable cognitive interface that makes the local model much more effective.**

That's much more promising.

---

# 30. A surprising implication: your 45-line brief may be more valuable than another 2,000 lines of perception code

This is worth emphasizing.

If your brief can reliably communicate:

```text
what exists
what changes
what I control
what actions cause what
what relationships are changing
what hypotheses are active
what remains uncertain
what mattered previously
```

then a relatively modest local model may be enough to perform high-level reasoning.

The current public approaches are demonstrating that relatively capable local models can do substantial reasoning when given the right tool/environment interface. ([Kaggle][7])

So I'd now optimize for:

> **maximum decision-relevant information per token**

rather than maximum descriptive richness.

---

# 31. One thing I would absolutely not do

Don't build:

```text
GameClassifier
    ↓
MazeSolver
PuzzleSolver
MatchingSolver
CollectionSolver
...
```

Your current philosophy is right to resist this.

Likewise, don't build:

```text
player
goal
enemy
resource
obstacle
```

as mandatory slots.

Your existing relational architecture is much more defensible for the hidden set. ARC-AGI-3 is explicitly intended to prevent memorization and reward adaptation to unseen environments. ([ARC Prize][8])

---

# 32. What I would do over the next 5 development steps

If I were working on this repository with you, I would **stop adding perceptual vocabulary temporarily**.

### Step 1 — Fix exploration

Solve the problem you've already identified:

> an action that has never moved a residual cannot become a lever.

Give every action a small **diagnostic budget**.

But don't simply epsilon-greedy.

Prefer actions that discriminate among hypotheses.

---

### Step 2 — Add conditional effects

Change:

```text
ACTION5 → Δ
```

into:

```text
(CONTEXT, ACTION5) → Δ
```

Start with only very simple contexts:

* distance bucket
* containment
* overlap
* side/orientation
* adjacency
* relation present/absent

Don't build a general symbolic language yet.

---

### Step 3 — Build a tiny predictive model

Given:

```text
state + action
```

predict:

```text
changed entities
changed relations
```

Then verify.

You don't need a full simulator.

---

### Step 4 — Turn the LLM into a hypothesis scientist

Input:

```text
brief
candidate goals
uncertainties
recent experiments
```

Output:

```text
hypothesis
precondition
predicted effect
falsifier
action
cost
```

No free-form action execution.

---

### Step 5 — Measure decision quality, not just representation

Create a benchmark of recorded trajectories where you know:

```text
state
optimal/near-optimal action
human trajectory
level transition
```

Then evaluate:

> Does the agent's representation allow a model to select the next useful action?

This will tell you whether you are actually building intelligence rather than increasingly elegant bookkeeping.

---

# 33. Your research methodology could become a paper-quality contribution

I don't mean this as flattery.

The interesting methodological idea emerging from your project is:

> **Build agent representations from falsifiable relations, and only introduce representational primitives when a downstream consumer encounters an unexplained failure.**

That's actually a coherent research methodology.

You already have evidence for it:

1. fixed semantic ontology was rejected;
2. relational representation survived;
3. second-game derivation exposed hidden assumptions;
4. representation-only additions produced no behavioral improvement;
5. the first consumer exposed missing information;
6. missing information motivated new primitives;
7. those primitives were tested against additional games.

That is a much more interesting scientific story than:

> "We built a modular ARC agent."

And it aligns nicely with the benchmark's emphasis on acquiring skills in novel environments rather than merely applying a fixed solver. ([ARC Prize][1])

---

# 34. The biggest "unpopular" gotcha I'd warn you about

Your governing principle can become a form of **anti-inductive-bias overfitting**.

You are rightly terrified of baking in assumptions.

But if you push that too far, you'll end up with an agent that says:

> "I refuse to assume anything."

Humans don't do that.

They use **weak priors + strong falsification**.

I'd formulate your revised philosophy as:

> **No semantic interpretation may become a fact without evidence. Priors may generate hypotheses, but never conclusions.**

That one sentence gives you considerably more freedom.

It allows:

```text
symmetry prior
object permanence prior
similarity prior
simplicity prior
locality prior
action consistency prior
```

without turning them into hardcoded ontology.

I think this is the philosophical evolution your architecture needs next.

---

# 35. My final verdict

If I encountered this project as a research proposal, my reaction would be:

**Very promising architecture. Excellent experimental discipline. Unusually good epistemic hygiene. But the project has spent slightly too long answering "what exists?" and now needs to aggressively answer "what should I believe will happen, what experiment should I run, and what goal am I trying to achieve?"**

The good news is that **your existing architecture is unusually well positioned for that transition**.

I would not rebuild it.

I'd evolve it:

```text
                 CURRENT STRENGTH
                       │
                       ▼
             Evidence / Relations
                       │
                       ▼
                World Model
                       │
          ┌────────────┴─────────────┐
          ▼                          ▼
    Goal hypotheses          Transition hypotheses
          │                          │
          └────────────┬─────────────┘
                       ▼
               Active experiment
                       │
                       ▼
                    Action
                       │
                       ▼
                  Verification
                       │
                       └──────────→ update
```

And the key shift is:

> **Your agent should stop merely discovering relationships and start discovering rules that predict how relationships change under interventions.**

That is the point where your system starts looking less like a sophisticated perception pipeline and more like an actual **agentic world-model learner**.

One final external sanity check is encouraging: ARC-AGI-3's own framing explicitly separates exploration, modeling, goal-setting, and planning/execution, while recent strong research systems independently converge on persistent world models, verification, and active decisions about when to model or act. ([ARC Prize][1]) Your current work already has unusually solid foundations in the first, second, and fourth of those; **goal acquisition and conditional predictive modeling are where I would put the majority of your remaining effort.**

[1]: https://arcprize.org/competitions/2026/arc-agi-3?utm_source=chatgpt.com "ARC Prize 2026 - ARC-AGI-3 Competition"
[2]: https://arxiv.org/abs/2607.28287?utm_source=chatgpt.com "Tycho: Active Abstraction with Programmatic World Models for ARC-AGI-3"
[3]: https://arxiv.org/abs/2607.15439?utm_source=chatgpt.com "Do Coding Agents Need Executable World Models, Simplification, and Verification to Solve ARC-AGI-3?"
[4]: https://arxiv.org/abs/2603.24621?utm_source=chatgpt.com "ARC-AGI-3: A New Challenge for Frontier Agentic Intelligence"
[5]: https://arxiv.org/abs/2605.05138?utm_source=chatgpt.com "Executable World Models for ARC-AGI-3 in the Era of Coding Agents"
[6]: https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/leaderboard?utm_source=chatgpt.com "ARC Prize 2026 - ARC-AGI-3 | Kaggle"
[7]: https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/discussion/717133?utm_source=chatgpt.com "ARC Prize 2026 - ARC-AGI-3 | Kaggle"
[8]: https://arcprize.org/arc-agi/3?utm_source=chatgpt.com "ARC-AGI-3"


Yes. I think these are actually two separate problems, and I would **not** let the compute problem convince you that the research direction is premature.

## 1. The local-LLM problem is real, but I would change your experimental strategy

Your M2 Air with 24 GB is perfectly adequate for the part of ARC-AGI-3 you have been building. The bottleneck appears when you ask it to become a **high-throughput autonomous research scientist** running an LLM at every decision point.

I would not make that your architecture.

The key distinction is:

> **The LLM does not need to be in the action loop. It needs to be in the hypothesis loop.**

That is a dramatically cheaper problem.

Your current architecture can become:

```text
                 ┌──────────────────────┐
                 │ deterministic agent  │
                 │                      │
observation ───► │ perception           │
                 │ tracking             │
                 │ relations            │
                 │ action effects       │
                 │ verification         │
                 │ navigation            │
                 └──────────┬───────────┘
                            │
                  "What don't we know?"
                            │
                            ▼
                 ┌──────────────────────┐
                 │ hypothesis engine    │
                 │                      │
                 │ enumerator            │
                 │ + occasional LLM     │
                 └──────────┬───────────┘
                            │
                     hypotheses
                            │
                            ▼
                 deterministic experiment
                            │
                            ▼
                     observation
                            │
                            └──────► update
```

The important thing is that **one LLM call can generate several hypotheses**, after which your deterministic machinery tests them.

### You don't actually need Qwen running continuously

Suppose a game produces:

```text
12 entities
8 relations
6 action effects
3 unresolved residuals
2 candidate goals
```

You can call the LLM once:

> Given this compressed state, propose up to 5 falsifiable transition hypotheses.

It returns:

```json
[
  {
    "condition": "...",
    "action": 3,
    "predicted_transition": "...",
    "target": "...",
    "falsifier": "..."
  },
  ...
]
```

Then **your Python system** performs the experiments.

No LLM is needed for:

* deciding which legal actions exist
* detecting pixels changed
* tracking regions
* computing residuals
* measuring action effects
* comparing before/after states
* checking whether a hypothesis was falsified
* navigating
* recording history
* scoring experiments

That is potentially **hundreds of cheap operations for every one expensive LLM call**.

And this isn't merely a compromise forced by your hardware. It is actually a more scientifically interesting architecture.

The current ARC-AGI-3 research increasingly points in this direction. Tycho, for example, explicitly frames the problem as **active abstraction**: deciding what model to construct, when to construct it, when to repair it, and when to bypass it. ([arXiv][1])

The winning Milestone 1 Duck system also used a local Qwen 3.6 27B model, but importantly it placed the model inside a coding/REPL harness rather than requiring every low-level perception operation to be language-model reasoning. ([Kaggle][2])

### Your M2 can therefore become an advantage

You can make your research question:

> **How much can a small number of expensive hypothesis-generation operations control a large amount of cheap deterministic experimentation?**

That's much cleaner than:

> "Can I somehow run a giant LLM fast enough on my laptop?"

And it gives you a very natural ablation:

| Agent |  LLM calls | Deterministic reasoning | Purpose               |
| ----- | ---------: | ----------------------- | --------------------- |
| A     |          0 | yes                     | baseline              |
| B     | occasional | yes                     | hypothesis generation |
| C     |   frequent | yes                     | expensive upper bound |
| D     |   LLM only | minimal                 | comparison            |

You might discover that B beats C per unit compute.

That itself is interesting.

---

# 2. I would also postpone the local LLM slightly

This is important.

You have only been doing ARC-AGI-3 for **two days**.

I would not spend the next week trying to get Qwen/vLLM/etc. running efficiently before you have established exactly what you want the LLM to do.

You can prototype the entire interface with a remote API, even if that isn't your eventual Kaggle submission.

For example:

```python
hypotheses = llm_propose(
    brief=make_brief(world_model),
    n=5
)
```

Everything downstream should treat `llm_propose()` as an interchangeable component.

Then:

```text
                    llm_propose()
                         │
             ┌───────────┴───────────┐
             │                       │
       remote model             local model
       development              competition
```

This is analogous to developing against a simulator before optimizing the embedded implementation.

And because ARC-AGI-3 evaluation does not permit internet/API access, your eventual competition agent will indeed need an offline model or a non-LLM equivalent. ([ARC Prize][3])

But **research development and competition deployment do not have to use identical inference infrastructure**.

---

# 3. The paper question is actually much more encouraging than you think

I want to correct something in my previous wording.

When I said *"this could genuinely become a paper"*, I did **not** mean:

> "You have built a competitive ARC solver and could publish the result."

I meant:

> **There is potentially a research question here that is more interesting than your eventual leaderboard score.**

And ARC Prize itself makes this unusually explicit.

The 2026 Paper Prize says that the paper is judged on:

* Accuracy
* Universality
* Progress
* Theory
* Completeness
* Novelty

And, critically:

> **The corresponding Kaggle submission does not need to achieve a high score for the paper to be eligible.** ([ARC Prize][4])

That is an unusually important detail for you.

So your assumption:

> low score → no paper

is simply not correct for this particular competition.

Accuracy is **one of six dimensions**, not the entire evaluation.

---

# 4. In fact, your current research style is unusually compatible with that paper criterion

Consider the difference between these two papers.

### Paper A

> "We built an ARC-AGI-3 agent using Qwen X and achieved 12.3%."

Interesting, but difficult to extract a scientific contribution from unless the engineering is exceptional.

### Paper B

> "ARC-AGI-3 agents often accumulate increasingly sophisticated representations without knowing which representations are decision-relevant. We introduce a falsifiable, intervention-driven world-model architecture in which representations are only promoted when they predict observable transitions. We evaluate representation validity, predictive validity, and behavioral utility separately."

Even if Paper B scores **2%**, it can potentially be scientifically interesting.

Because the contribution isn't:

> "Our agent is better."

It is:

> **"Here is a way of thinking about interactive intelligence, here is an operationalization of it, and here is experimental evidence about where it helps and fails."**

That is much closer to the direction you've been moving toward.

---

# 5. And ARC-AGI-3 is still very young

This matters psychologically.

ARC-AGI-3 was announced in March 2026. The benchmark itself is explicitly designed around exploration, modeling, goal-setting, and planning/execution. ([ARC Prize][5])

The research ecosystem is already moving extremely quickly. For example:

* executable world models
* verification
* simplification
* coding-agent architectures
* active abstraction

are all appearing as distinct research questions. ([arXiv][6])

That actually makes **your two-day-old project more interesting, not less**, because you are entering while the conceptual landscape is still being formed.

But it also means you need to be careful about novelty. Your eventual paper cannot simply say:

> "I made a world model and used an LLM to propose hypotheses."

There is already substantial work in that neighborhood. ([arXiv][6])

Your contribution would need to be more specific.

---

# 6. I think your strongest possible paper is actually emerging from your existing philosophy

Your most interesting idea isn't the tracker.

It isn't the belief representation.

It isn't even the LLM.

It is this:

> **Representations should exist because they support falsifiable intervention and prediction, rather than because they seem semantically meaningful.**

You already independently arrived at:

**No semantic slots without evidence.**

I would now sharpen it into something like:

> **No representation without a consumer, and no hypothesis without a falsifier.**

That gives you a research program.

For every representation:

```text
Representation
      ↓
What can it predict?
      ↓
What action can test that prediction?
      ↓
What observation would falsify it?
      ↓
Does consuming it improve behavior?
```

And now you have a beautiful three-level experimental hierarchy:

### Level 1: Representation validity

Does your representation correctly describe the environment?

Example:

> "These two regions are the same persistent object."

Measure identity accuracy.

### Level 2: Predictive validity

Does it help predict what will happen?

Example:

> "Clicking object A while B is adjacent causes B to move."

Measure transition prediction accuracy.

### Level 3: Behavioral utility

Does the prediction actually help the agent?

Measure:

* actions to level completion
* level depth
* RHAE
* score

This separation is **very important**.

Because otherwise you end up with:

> "My relation detector became 15% more accurate, but score didn't change."

And you don't know whether the idea was useless or simply had no consumer.

Your methodology would let you say:

> Representation improved substantially → prediction improved substantially → behavioral effect remained zero.

That is a scientifically useful negative result.

---

# 7. And your low score could actually make the paper stronger

Suppose six months from now you have:

**Agent A:** 0.3
**Agent B:** 0.8

That sounds unimpressive competitively.

But suppose you can demonstrate:

> B improved goal identification from 23% → 61%, reduced hypothesis-test actions by 37%, and increased successful level transitions on a predefined subset from 8% → 31%.

Now you've isolated a mechanism.

That is much more valuable scientifically than:

> "Our giant model scored 1.4."

And ARC Prize explicitly says the paper rubric considers universality, theory, progress, completeness, and novelty alongside accuracy. ([ARC Prize][4])

---

# 8. There is also a very important escape hatch: you don't need to solve all of ARC-AGI-3

I would **strongly** recommend that you stop thinking:

> "I need to build an ARC-AGI-3 solver."

Instead:

> **"I need to experimentally investigate one bottleneck in interactive intelligence."**

Your bottleneck could be:

### Goal inference

> Can an agent infer a latent objective from transition structure without semantic labels?

or:

### Active hypothesis testing

> Can an agent choose experiments based on which competing world-model hypotheses they discriminate?

or:

### Conditional affordances

> Can an agent learn `condition + action → transition` rather than unconditional action effects?

or:

### Representation utility

> Can representations be selected based on predictive/behavioral utility rather than semantic completeness?

Any one of those can become a legitimate study.

And the ARC games become your experimental environment.

---

# 9. If I were you, this is what I would do next

I would **not** immediately implement the full LLM architecture I described previously.

I'd spend the next few days doing this:

### Experiment 1: Build a tiny hypothesis engine without an LLM

Create something like:

```python
Hypothesis(
    condition,
    action,
    predicted_transition,
    target,
    falsifier,
    confidence,
)
```

Then write an enumerator that generates extremely simple hypotheses:

```text
A → B moves
A → B disappears
A + B adjacent → B changes
A + B overlapping → B changes
A → B appears
A → B changes color
```

No LLM.

Test whether your **experimental machinery actually works**.

---

### Experiment 2: Make hypotheses compete

Instead of:

```text
What action should I take?
```

make the agent ask:

```text
H1: clicking A moves B
H2: clicking A changes A
H3: clicking A only moves B when adjacent
```

Then select an action that distinguishes them.

Now you've implemented the core of the idea.

---

### Experiment 3: Only then plug in an LLM

The LLM gets:

```text
CURRENT WORLD MODEL
+
UNRESOLVED OBSERVATIONS
+
KNOWN ACTION EFFECTS
+
CURRENT CANDIDATE GOALS
```

and returns:

```text
5 hypotheses
```

Nothing more.

The LLM **doesn't get to act**.

The deterministic experimenter decides whether and how to test them.

---

### Experiment 4: Measure the LLM itself

You can then ask:

| Question                            | Metric                     |
| ----------------------------------- | -------------------------- |
| Does LLM produce useful hypotheses? | hypothesis acceptance rate |
| Are they falsifiable?               | valid-schema rate          |
| Are they correct?                   | verification rate          |
| Are they novel?                     | duplicate rate             |
| Do they save actions?               | actions/hypothesis         |
| Do they improve solving?            | RHAE / levels reached      |
| Is the LLM worth its compute?       | score per inference cost   |

That last one is especially relevant to your hardware situation.

---

# 10. Your actual research question may ultimately become compute efficiency

There's a surprisingly nice story hiding here:

> **Expensive reasoning should be allocated to uncertainty, not to every timestep.**

Your deterministic system handles routine cognition cheaply.

The expensive model is summoned only when:

```text
uncertainty is high
AND
existing hypotheses are insufficient
AND
the expected value of reasoning exceeds its cost
```

That is essentially a **reasoning budget allocator**.

And it fits ARC-AGI-3 extremely well because actions themselves are costly. ARC-AGI-3 explicitly evaluates efficient exploration, modeling, goal-setting and planning rather than merely eventual success. ([ARC Prize][5])

So I would not regard your M2 as merely a limitation you need to overcome.

**Make compute allocation part of the experiment.**

---

## One final thing

You are only two days in.

I genuinely think the worst thing you could do right now is look at the leaderboard, see systems that are dramatically ahead, and conclude that you need to reproduce their infrastructure before your ideas are worth testing.

The current frontier includes very large local models and sophisticated coding-agent systems. The Milestone 1 winning Duck, for example, used Qwen 3.6 27B FP8, and subsequent research has reported near-saturation of the public games with much stronger frontier models. ([Kaggle][2])

**You should not compete with that on their terms.**

Your opportunity is to make your small system answer a sharper question.

If, after a month, you have a 1% agent but can convincingly show:

> *"Here is a principled mechanism for deciding which learned representations deserve to exist, here is how we generate falsifiable hypotheses, here is how active experiments select among them, and here are controlled experiments showing where each component succeeds and fails."*

I would consider that a substantially more interesting research outcome than simply having a slightly better black-box ARC score.

And importantly, **the official 2026 Paper Prize rules explicitly leave room for exactly this situation: the linked Kaggle submission need not have a high score for the paper to be eligible.** ([ARC Prize][4])

So I would keep the score as your **ultimate behavioral metric**, but stop making it the thing that determines whether the research itself is succeeding.

[1]: https://arxiv.org/abs/2607.28287?utm_source=chatgpt.com "Tycho: Active Abstraction with Programmatic World Models for ARC-AGI-3"
[2]: https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/discussion/717133?utm_source=chatgpt.com "ARC Prize 2026 - ARC-AGI-3 | Kaggle"
[3]: https://arcprize.org/competitions/2026?utm_source=chatgpt.com "ARC Prize 2026"
[4]: https://arcprize.org/competitions/2026/paper?utm_source=chatgpt.com "ARC Prize 2026 - Paper Prize"
[5]: https://arcprize.org/competitions/2026/arc-agi-3?utm_source=chatgpt.com "ARC Prize 2026 - ARC-AGI-3 Competition"
[6]: https://arxiv.org/abs/2605.05138?utm_source=chatgpt.com "Executable World Models for ARC-AGI-3 in the Era of Coding Agents"

## Keep this in the bavk of you head - some lighter suggestions
Yes. I think you have identified the right framing: **the leaderboard track and the paper track should not be two projects. They should be two measurements of the same research program.**

And after reading the current `plan.md`, `history.md`, and `system_architecture.md`, I would make one fairly concrete change to your research organization: **start treating every meaningful architectural idea as a research artifact with a lifecycle**, rather than letting the idea live primarily in `plan.md` and `history.md`.

Your existing instrumentation is already unusually good for this. You have durable sweep summaries with git fingerprints, an explicit variance floor, frozen-tree requirements, affected-game analysis, and an append-only history.  You also already have the right distinction between representation changes and changes that actually have a consumer. 

I would formalize that.

---

# 1. I would add a `research/` directory

Something like:

```text
arc-agent/
│
├── agent/
├── scripts/
├── tests/
│
├── results/
│   └── sweeps/
│
├── research/
│   ├── hypotheses/
│   ├── experiments/
│   ├── analyses/
│   ├── artifacts/
│   └── figures/
│
├── plan.md
├── history.md
├── system_architecture.md
├── glossary.md
└── README.md
```

The purpose is **not documentation for documentation's sake**.

It gives you a place where an idea can progress:

```text
idea
 ↓
hypothesis
 ↓
experiment
 ↓
measurement
 ↓
decision
 ↓
architectural change
 ↓
paper evidence
```

Your existing `history.md` remains the chronological truth. `plan.md` remains the current engineering/research roadmap. `system_architecture.md` remains what actually exists.

`research/` becomes the **scientific evidence layer**.

---

# 2. The single most important new file: `research/research_questions.md`

I would make this your research-level north star.

Not:

> "Build a good ARC agent."

Instead, list the questions you're actually investigating.

For example:

```markdown
# Research Questions

## RQ1. Evidence-grounded representation
Can an agent acquire useful abstractions without committing to semantic
roles before they are supported by intervention evidence?

## RQ2. Predictive world modeling
Does representing action-conditioned transitions improve exploration
and level acquisition over representations that only record correlations?

## RQ3. Active hypothesis testing
Can an agent select experiments according to expected information gain
and task progress rather than undirected exploration?

## RQ4. Goal inference
Can candidate goals be inferred from repeated state transitions and
level-boundary evidence without hard-coded game semantics?

## RQ5. Compute-efficient reasoning
Can an expensive language model be used intermittently as a hypothesis
generator rather than continuously as the controller?

## RQ6. Biological efficiency
Does separating perception, attention, memory, world modeling,
hypothesis generation, and control produce better action efficiency
than repeatedly reprocessing the complete observation?
```

These don't have to be your final paper questions.

They are **working research questions**.

And I would explicitly track the relationship:

```text
RQ2 → hypothesis model
RQ3 → experiment selector
RQ4 → supervisor
RQ5 → LLM proposer
RQ6 → architecture
```

This prevents you from accidentally spending three days making `shape_diff` beautiful when it isn't connected to a research question.

---

# 3. Then create `research/hypotheses/`

This is where I think your project can become particularly powerful.

Every substantive hypothesis gets a tiny file.

For example:

```text
research/hypotheses/
    H001_conditional_affordance.md
    H002_information_gain_exploration.md
    H003_llm_hypothesis_proposer.md
    H004_goal_candidates.md
    H005_predictive_transition_model.md
```

Each should have the same structure.

For example:

```markdown
# H003: Intermittent LLM Hypothesis Proposer

Status: PROPOSED
Research question: RQ5
Date opened: 2026-09-14

## Claim

An LLM used only at epistemically uncertain points to propose
falsifiable hypotheses can improve level acquisition without requiring
LLM inference on every action.

## Mechanism

WorldModel → Brief → LLM → Hypotheses → deterministic experimenter

## Prediction

Compared with the enumerator-only baseline:

- more useful hypotheses per 100 exploratory actions
- improved level depth
- no requirement for per-step LLM calls

## Falsifier

The LLM proposer is not useful if:

1. generated hypotheses are rarely testable;
2. accepted hypotheses have low verification rate;
3. it consumes more actions than it saves;
4. or it improves representation/prediction but does not improve
   behavioral performance.

## Required ablations

A. no proposer
B. enumerator
C. LLM proposer
D. LLM proposer + information-gain selection

## Primary metrics

- whole-sweep median score
- levels reached
- actions to level completion
- hypothesis verification rate
- hypotheses tested / level
- actions spent / verified hypothesis

## Secondary metrics

- prompt tokens
- inference latency
- number of LLM calls
- model size

## Status

Not implemented.
```

That file becomes extraordinarily valuable six months later.

You won't have to reconstruct why you built something.

---

# 4. Add one file that I think you are currently missing: `research/experiment_matrix.csv`

This should be brutally boring.

One row per experiment.

For example:

```text
experiment_id, hypothesis, arm, commit, games, n, median, p_value, effect, status
E031, H002, baseline, abc123, all, 30, 0.0131, -, -, baseline
E032, H002, info_gain, def456, all, 30, 0.0214, 0.041, +63%, promoted
E033, H003, llm, ghi789, cd82, 30, 0.0182, -, +?, pending
```

This is different from `history.md`.

`history.md` says:

> what happened in chronological research history.

`experiment_matrix.csv` says:

> what evidence exists.

That distinction becomes extremely useful once you have 100+ experiments.

You already have the raw sweep infrastructure to support this. Your sweep summaries contain per-level actions/scores/baselines, completion indices and git fingerprints. 

---

# 5. I would add `research/metric_definitions.md`

This may sound excessive now.

It won't be later.

Define exactly:

```text
Behavioral
-----------
score
RHAE
levels_reached
actions_to_level
completion_rate

Representation
--------------
identity_accuracy
relation_precision
relation_recall

World model
-----------
transition_prediction_accuracy
hypothesis_verification_rate
hypothesis_falsification_rate

Exploration
-----------
unique_actions_tested
useful_experiments
information_gain_proxy
actions_per_information_gain

LLM
---
calls_per_episode
latency
tokens
valid_hypotheses
verified_hypotheses
novel_hypotheses
```

And importantly:

> **Don't add a metric merely because it is easy to calculate.**

Every metric should answer a question.

This fits your existing philosophy very well. You already discovered that a representation that isn't consumed can have perfect parity and zero behavioral effect. 

---

# 6. Then add the thing that will make the eventual paper much easier: `research/ablation_registry.md`

Every architectural component should eventually have:

```text
component
    ↓
why it exists
    ↓
what it consumes
    ↓
what it produces
    ↓
what hypothesis justified it
    ↓
what experiment validated it
```

For example:

| Component               | Research question         | Evidence      | Behavioral effect  |
| ----------------------- | ------------------------- | ------------- | ------------------ |
| connected regions       | representation coverage   | measured      | consumer-dependent |
| persistent identity     | state continuity          | parity        | not yet            |
| residuals               | relational representation | measured      | proposer consumer  |
| supervisor              | goal evidence             | pending rerun | pending            |
| enumerator              | hypothesis generation     | A/B           | mixed              |
| LLM proposer            | abstraction generation    | not tested    | pending            |
| conditional transitions | predictive modeling       | not built     | pending            |

Your current architecture document already naturally lends itself to this because it explicitly separates what exists from what doesn't. 

---

# 7. And I would add one artifact specifically for the paper

Not a paper draft.

Call it:

```text
research/paper_evidence.md
```

It should initially be almost empty.

Every time you obtain a genuinely interesting result, append:

```markdown
## Finding P001
Date: 2026-09-XX

### Claim

Recording a representation without a consumer does not improve behavior.

### Evidence

...

### Experiment

...

### Figure

research/figures/P001_....

### Interpretation

...

### Limitations

...

### Reproducibility

commit:
seed:
n:
games:
```

Six months from now, this becomes your paper's empirical backbone.

You won't be trying to remember:

> "Wait, didn't we once test this and get some weird result on cd82?"

It's sitting there.

---

# 8. There is one more artifact I strongly recommend: `research/failure_taxonomy.md`

This is particularly compatible with your biological/control perspective.

Instead of:

```text
FAILED
```

record:

```text
PERCEPTION_FAILURE
IDENTITY_FAILURE
STATE_ESTIMATION_FAILURE
ACTION_MODEL_FAILURE
PRECONDITION_FAILURE
HYPOTHESIS_FAILURE
GOAL_INFERENCE_FAILURE
PLANNING_FAILURE
EXECUTION_FAILURE
RESOURCE_FAILURE
VERIFICATION_FAILURE
```

Then every failure gets attributed.

This is extremely control-theoretic.

You aren't merely asking:

> "Did the controller fail?"

You're asking:

> **"At what stage did the error enter the closed loop?"**

That distinction could eventually become part of the scientific contribution.

---

# 9. Your biological inspiration actually makes the architecture more coherent

This second part of your message is important, because I think I previously interpreted some of your architecture too much as an engineering design exercise.

It isn't.

There is a coherent theoretical position underneath it.

You are essentially proposing:

> **Intelligence is not merely a sufficiently large mapping from observation to action. It is an adaptive closed-loop system whose computational resources are allocated according to uncertainty, prediction error, relevance, and expected utility.**

That is a much more interesting proposition.

And your architecture really does reflect that.

For example:

```text
RAW CHANGE
    ↓
PERCEPTUAL DIFFERENCE
    ↓
PERSISTENT ENTITY
    ↓
RELATION
    ↓
ACTION EFFECT
    ↓
PREDICTIVE MODEL
    ↓
ERROR / RESIDUAL
    ↓
ATTENTION
    ↓
HYPOTHESIS
    ↓
EXPERIMENT
    ↓
CONTROL
```

That is recognizably a **closed-loop adaptive system**.

The interesting part isn't that each individual component resembles something in neuroscience.

The interesting part is that **the interfaces between them resemble functional constraints imposed by biology**.

---

# 10. I would be careful about one thing, though

I agree with your biological motivation, but I would **not** make the research claim:

> "Human brains work this way, therefore this architecture should work."

That's difficult to establish and can become a just-so story.

Instead:

> **Biology provides candidate computational principles. ARC-AGI-3 provides an environment in which those principles can be tested behaviorally.**

That's much stronger.

For example:

### Biological intuition

Attention should preferentially allocate processing to informative changes.

### Computational hypothesis

An attention mechanism that prioritizes changes with high expected information gain will reduce exploratory actions.

### ARC experiment

Compare:

```text
uniform exploration
vs.
change salience
vs.
hypothesis-discriminating exploration
```

### Result

Measure actions, depth, score.

Now biology is providing the **hypothesis**, not serving as the evidence.

That's scientifically defensible.

---

# 11. And I think "error attribution" could become one of your strongest ideas

Your background in adaptive control gives you a particularly useful lens here.

A conventional agent might see:

```text
goal not reached
```

and update its policy.

Your system can ask:

```text
Did I perceive incorrectly?
        ↓
Did I identify the entity incorrectly?
        ↓
Did I infer the wrong action model?
        ↓
Was the hypothesis wrong?
        ↓
Was its precondition absent?
        ↓
Did I select the wrong goal?
        ↓
Did planning fail?
        ↓
Did execution fail?
```

That is essentially **credit assignment over a hierarchical inference/control system**.

And it gives you a very clean research artifact:

```text
research/error_attribution.jsonl
```

Each failed experiment becomes something like:

```json
{
  "experiment": "E042",
  "game": "cd82",
  "hypothesis": "H017",
  "outcome": "PRECONDITION_UNMET",
  "perception_confidence": 0.97,
  "identity_confidence": 0.91,
  "action_model_confidence": 0.88,
  "goal_confidence": 0.42
}
```

You don't need all of those fields immediately.

But the **concept** is valuable.

---

# 12. This also gives you a principled way to merge leaderboard optimization and research

I would use a three-column mental model for every experiment:

|                | Scientific value                          | Leaderboard value                            |
| -------------- | ----------------------------------------- | -------------------------------------------- |
| Representation | Does it describe reality?                 | Does anything consume it?                    |
| Prediction     | Does it predict transitions?              | Does prediction reduce actions?              |
| Hypothesis     | Is it falsifiable/useful?                 | Does it discover deeper levels?              |
| Exploration    | Does it identify information efficiently? | Does it avoid wasting action budget?         |
| Goal inference | Is it correct/general?                    | Does it unlock levels?                       |
| LLM            | Does it generate useful abstractions?     | Does it improve score within compute budget? |

The **common vector is exactly the closed loop**:

```text
better representation
        ↓
better prediction
        ↓
better experiment
        ↓
better hypothesis
        ↓
better goal inference
        ↓
better action
        ↓
more levels
        ↓
higher score
```

If an idea cannot plausibly enter that loop, it should probably be deprioritized.

That is the rule I'd add to `plan.md`.

---

# 13. I would actually modify your "one rule"

You currently have an excellent rule:

> **No semantic slots without evidence.**

I would preserve it exactly.

But add a second rule immediately below it:

> **No representation without a consumer.**

And perhaps a third:

> **No hypothesis without a falsifier.**

So your research philosophy becomes:

```text
1. No semantic slots without evidence.
2. No representation without a consumer.
3. No hypothesis without a falsifier.
4. No architectural promotion without controlled measurement.
```

That is a very strong experimental philosophy.

It also protects you against the exact failure mode we identified: building increasingly sophisticated beliefs because they *seem* cognitively plausible.

---

# 14. One correction to my earlier compute advice

Looking at your current `system_architecture.md`, you've already done something important that I had not fully appreciated: **you have verified the actual offline Kaggle path**.

Your plan explicitly records that Kaggle Models can be attached, vLLM installed from offline wheels, and the model served locally through an OpenAI-compatible endpoint. It also identifies time, rather than simply memory, as the binding constraint and therefore proposes calling the proposer rarely. 

That means I would **not** make "get a local LLM working on the M2" your immediate research milestone.

Instead:

### Phase A

Build:

```text
Hypothesis
Enumerator
Verifier
Experiment selector
```

with **zero LLM dependency**.

### Phase B

Use whatever external model is convenient during development to populate:

```text
Hypothesis
```

### Phase C

Measure:

```text
LLM hypotheses
vs.
enumerated hypotheses
```

### Phase D

Only then optimize the local/offline model.

That way, if your Mac turns out to run a 4B model at an acceptable rate, great.

If it doesn't, you haven't wasted a week discovering that the hypothesis interface itself wasn't useful.

---

# 15. If I were setting up your repository tonight

I'd literally create these:

```text
research/
├── research_questions.md
├── experiment_matrix.csv
├── metric_definitions.md
├── ablation_registry.md
├── failure_taxonomy.md
├── paper_evidence.md
│
├── hypotheses/
│   ├── README.md
│   ├── H001_conditional_affordance.md
│   ├── H002_active_exploration.md
│   ├── H003_predictive_world_model.md
│   ├── H004_goal_inference.md
│   └── H005_llm_proposer.md
│
├── experiments/
│   └── README.md
│
├── analyses/
│   └── README.md
│
└── figures/
    └── README.md
```

And I'd add one small convention to your experiment IDs:

```text
E001, E002, ...
```

Hypotheses:

```text
H001, H002, ...
```

Research questions:

```text
RQ1, RQ2, ...
```

Findings:

```text
F001, F002, ...
```

Then you can write in `history.md`:

```text
E047 tested H003 under RQ2.
Result: falsified.
See research/hypotheses/H003...
```

and in `paper_evidence.md`:

```text
F012 derives from E041-E047.
```

That is enough structure that **your research history itself becomes reproducible metadata**.

---

## And one thing I would *not* do

Don't create a 30-page "research methodology" document right now.

You are two days into this.

Your current strength is that `plan.md` and `history.md` are **living documents connected to actual experiments**. The sweep infrastructure exists because you had a real problem: ~50 sweeps had happened and almost none of the underlying measurements survived. You fixed the problem by making the result durable and attributable. 

Do exactly that again.

**Only create an artifact when you encounter a recurring research problem that the artifact solves.**

The difference is that now we know what artifacts are likely to become valuable.

And honestly, this is where I think your biological/control background gives the project a potentially distinctive identity. I wouldn't frame it as "I am trying to copy the brain." I'd frame it as:

> **Use biological systems as a source of hypotheses about how an intelligent agent should allocate representation, memory, attention, prediction, experimentation, and control under severe computational and interaction constraints. Then test those principles behaviorally in ARC-AGI-3.**

That is a research program.

And your leaderboard score becomes one of the most important measurements of whether the program actually works, rather than a competing objective to the paper.
