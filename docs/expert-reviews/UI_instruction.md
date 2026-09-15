Yes. I looked at the **actual current recap implementation**, not just the description of it, and I think the UI has a much bigger opportunity than simply "make the panels prettier."

The important thing is that your current backend is actually **better organized than the UI makes it appear**. The snapshot already captures frame, perception, masks, beliefs, brief, action evidence, decision tier/candidates/weights/reasoning, etc. ([GitHub][1])

The problem is that the UI currently presents these as a collection of debugging widgets rather than as **one coherent story of cognition**.

That is exactly what I would fix.

---

# The design principle I would adopt

I would make the new UI answer one question from left to right:

> **"What did the agent see → what did it infer → what does it currently believe → what did it predict → what did it decide to do → what happened → how did that change its model?"**

That should be the organizing principle of the entire interface.

Not:

> "Here are 14 internal modules. Let's give each one a box."

Your architecture has 14 modules, but **the student shouldn't experience 14 modules**. They should experience one reasoning loop. Your own architecture documentation describes the system as perception → entities → control/constraints/relations/belief → brief → hypothesis → supervisor → navigation → decision, which is precisely the chain the UI should make visible. ([GitHub][2])

---

# 1. First: I would completely change the page geometry

Your current layout is:

```text
┌──────────────┬──────────────────┬──────────────┐
│ Frame        │ Live Bet         │ Perceptions  │
│              │                  │              │
│ Forward      │ Entity Matrix    │ Event Log    │
│ Model        │                  │              │
└──────────────┴──────────────────┴──────────────┘
```

That's a **dashboard**.

I don't think you want a dashboard.

You want an **observability environment**.

I'd make it:

```text
┌─────────────────────────────────────────────────────────────┐
│ GAME / LEVEL / STEP / STATE / SCORE                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    CURRENT WORLD                            │
│                                                             │
│              [ 64 × 64 FRAME ]                             │
│                                                             │
├───────────────────────┬─────────────────────────────────────┤
│ WHAT THE AGENT SEES   │ WHAT THE AGENT BELIEVES             │
│                       │                                     │
│ Objects               │ Entities / roles                    │
│ Changes               │ Relations                           │
│ Spatial structure     │ Latent state                        │
│                       │ Uncertainty                         │
├───────────────────────┴─────────────────────────────────────┤
│                     DECISION                               │
│                                                             │
│ Goal → Hypothesis → Prediction → Candidate actions → Action │
├─────────────────────────────────────────────────────────────┤
│                 WHAT HAPPENED                               │
│                                                             │
│ Predicted → Observed → Surprise → Belief update             │
├─────────────────────────────────────────────────────────────┤
│ HISTORY / TRAJECTORY                                        │
│ ────────────────●────●────●────●────●──────────────        │
└─────────────────────────────────────────────────────────────┘
```

**That is the UI I would build.**

The current masks become supporting visualizations rather than primary panels.

---

# 2. Make the central object the FRAME, not the mask

Your current UI has a `Frame` card and then a separate `Perceptions` card with a mask canvas. 

I would change this fundamentally.

Have one large **World View**.

Inside it:

### Base layer

Actual observed 64×64 frame.

### Toggleable overlays

* Entities
* Entity IDs
* Movement
* Interest
* Controlled
* Affect
* Click
* Obstacles
* Route
* Goal candidate
* Predicted change
* Latent state, eventually

But **never display more than one or two overlays by default**.

The current UI gives the user a collection of mask tabs, but that makes each mask feel like a separate truth. 

Instead:

```text
WORLD VIEW

[Observed] [Entities] [Relations] [Action effect] [Prediction]

             ┌─────────────┐
             │             │
             │   FRAME     │
             │             │
             └─────────────┘
```

And clicking an entity should become a major interaction.

---

# 3. Entity selection should be the bridge between spatial and symbolic reasoning

This is one of the biggest missed opportunities.

Suppose I click entity `#7`.

The UI should immediately show:

```text
ENTITY #7

Observed
  colour: 15
  cells: 42
  centroid: (31, 27)
  live: yes

Identity
  first seen: t=3
  observations: 18
  last moved: t=21

Belief
  role: CONTROL
  confidence: 87%

Actions associated
  ACTION1   ████████
  ACTION2   ████████
  ACTION3   ████████
  ACTION4   ████████

Relations
  #7 → #12
      distance: 14
      drift: -3
  #7 → #15
      containment: ...
```

Then the spatial object and symbolic object are visibly the **same thing**.

That's pedagogically enormous.

A student can literally follow:

> "This blob on the screen became entity #7. The tracker maintains its identity. The belief system says it is CONTROL because of these observations. That belief then affects action selection."

That is the end-to-end story you want.

---

# 4. Kill the "Event Log" as the main explanation

Your instinct about the lower-right text is correct.

The current UI parses the `RECENT` section of the brief and displays things like:

> `t=14 ACTION2: distance(#0,#4) 22->26`

The code is literally doing this text-log rendering. 

That's useful for debugging.

It's **terrible as the primary teaching interface**.

Because a student has to reconstruct causality from prose.

Instead make the current timestep a **causal card**:

```text
STEP 14

OBSERVATION
Bucket moved +5,+0

        ↓

INTERPRETATION
Entity #7 translated

        ↓

BELIEF UPDATE
#7 remains CONTROL
confidence 82% → 87%

        ↓

RELATION CHANGES
distance(#7,#12)
26 → 21

        ↓

HYPOTHESIS
Drive distance(#7,#12) toward 0

        ↓

DECISION
ACTION4

        ↓

OUTCOME
Predicted: +5,+0
Observed:  +5,+0

✓ prediction confirmed
```

That is infinitely more useful.

---

# 5. Introduce a first-class "Reasoning Loop"

This should probably be the **most important new component**.

I'd put it directly beneath the world view.

```text
┌───────────────────────────────────────────────────────────────┐
│ REASONING LOOP                                                │
│                                                               │
│ OBSERVE → REPRESENT → BELIEVE → HYPOTHESIZE → PREDICT → ACT  │
│    ✓          ✓          ✓          ●             ●       →    │
│                                                               │
│                         ACTION4                               │
│                           ↓                                   │
│                     OBSERVATION                               │
│                           ↓                                   │
│                  PREDICTION MATCHED                           │
└───────────────────────────────────────────────────────────────┘
```

Each node is clickable.

Click **REPRESENT**:

```text
Regions
Entities
Motion
Recolour
...
```

Click **BELIEVE**:

```text
#7 CONTROL 0.87
#12 AFFECT 0.74
...
```

Click **HYPOTHESIZE**:

```text
H17
distance(#7,#12): 26 → 0
lever: ACTION4
budget: 8
```

Click **PREDICT**:

```text
Expected:
    #7 moves +5,+0
    distance: 26 → 21
```

Click **ACT**:

```text
ACTION4
```

This is how you turn the UI into something you can teach from.

---

# 6. I would make uncertainty visually fundamental

This is especially important given your architecture.

Your philosophy is:

> unknown is `None`, never false.

That should be visible.

Don't make the interface:

```text
TRUE / FALSE
```

Make it:

```text
CONFIRMED
LIKELY
HYPOTHESIS
UNKNOWN
CONTRADICTED
```

And use **one consistent visual language**.

For example:

| State         | Visual             |
| ------------- | ------------------ |
| Confirmed     | solid              |
| Strong belief | solid + confidence |
| Hypothesis    | dashed             |
| Unknown       | muted / `?`        |
| Contradicted  | struck / red       |
| Predicted     | outlined           |
| Observed      | filled             |

This would be incredibly useful for students because it makes your epistemic discipline visible.

---

# 7. Do not show confidence as just a percentage

This is a subtle UI issue.

You currently display things like `87%` for belief strength. 

I would keep the number, but put **evidence underneath it**.

Instead of:

```text
#7 CONTROL        87%
```

show:

```text
#7  CONTROL       87%
    ├─ ACTION1 moves it       +++
    ├─ ACTION2 moves it       +++
    ├─ ACTION3 moves it       +++
    └─ deterministic response +++
```

Because otherwise a student naturally asks:

> "87% according to what?"

Your whole project is about evidence-gated inference.

The UI should answer that question.

---

# 8. The action panel should become much more sophisticated

Your current gamepad is actually a decent start. It already maps learned movement offsets onto the buttons, displays candidate weights, and highlights the selected action. 

But I would change its meaning.

Don't call it:

> Forward Model (Decision & Controls)

Make it:

## **ACTION SPACE**

Then every action gets a compact status:

```text
ACTION1
────────────────
Known effect
Move: (-5, 0)
Evidence: 8
Candidate: no
────────────────

ACTION2
────────────────
Known effect
Move: (+5, 0)
Evidence: 9
Candidate: YES
Weight: 0.72
────────────────

ACTION5
────────────────
Unknown effect
Evidence: 1
Candidate: YES
────────────────
```

This is much more educational.

And hovering ACTION2 should simultaneously highlight:

* entity #7
* its predicted movement
* the relevant relation
* the hypothesis using it

You already have a rudimentary version of this: hovering the action buttons filters entity rows based on action evidence. 

**Expand that idea to the entire UI.**

---

# 9. Make the UI cross-linked, not panel-linked

This is probably my strongest UI recommendation.

Everything should be an **object you can follow**.

Example:

You click:

```text
ACTION5
```

Then the entire screen subtly updates:

```text
WORLD
  affected cells highlighted

ENTITIES
  #12 highlighted

RELATIONS
  palette_missing(#12,#17)
  part_size_diff(#12,#17)

HYPOTHESIS
  H23 highlighted

PREDICTION
  expected recolour

HISTORY
  previous ACTION5 events highlighted
```

Similarly, click:

```text
ENTITY #12
```

and the entire UI becomes about #12.

This is much more powerful than adding more panels.

---

# 10. Your timeline should become a real timeline

Right now you have a range slider and keyboard shortcuts. That's useful but primitive. 

I would replace the single scrubber with:

```text
LEVEL 1
────────────────────────────────────────────────────────
  0    5    10   15   20   25   30   35   40
  │    │         │    │         │
  ●────●────●────●────●─────────●─────────────●
       ↑              ↑
     death          hypothesis
```

Different event types get different markers:

```text
● normal action
◆ hypothesis started
× hypothesis falsified
✓ prediction confirmed
▲ level advance
! surprise
↻ reset
```

Then you can click directly on a meaningful event.

This is **much better than "press v to find next vanish."**

Keep the keyboard shortcuts, but don't make them the UI.

---

# 11. Add a "story mode"

This is the feature I think would make it genuinely useful for teaching.

A button:

## `Explain this step`

Then the UI generates a human-readable causal explanation from the actual state:

```text
STEP 27

The agent observed that entity #4 moved after ACTION2.

Because this happened consistently across 6 previous observations,
the control model currently considers ACTION2 → (+5, 0) confirmed.

This movement changed the distance between #4 and #9
from 18 to 13.

The current hypothesis is that reducing this distance is useful.

The agent therefore selected ACTION2.

Prediction:
  distance should decrease by ~5.

Observed:
  distance decreased from 13 to 8.

Result:
  prediction confirmed.
```

Notice what this does:

**It doesn't replace the model with an explanation.**

It is a projection of the model's actual state.

That's essential.

---

# 12. And eventually the latent state gets its own visual language

This is where your decision not to build the UI completely yet is correct.

I would reserve a large section for:

# WORLD MODEL

Eventually:

```text
┌───────────────────────────────────────────────┐
│ LATENT STATE                                  │
│                                               │
│ selected_colour       RED       0.84          │
│ mode                  PAINT     0.71          │
│ phase                 2         0.93          │
│ target                #17       0.67          │
│ switch_A              ON        0.91          │
│                                               │
│ ───────────────────────────────────────────── │
│                                               │
│ PREDICTIVE STATE                              │
│                                               │
│ current state      Zₜ                         │
│ action             ACTION5                    │
│ predicted state    Zₜ₊₁                       │
│                                               │
│ prediction confidence                         │
│ ████████████████░░░░ 78%                     │
└───────────────────────────────────────────────┘
```

And next to it:

```text
Zₜ ── ACTION5 ──→ Zₜ₊₁
       │
       └── predicted:
           block.color = RED
```

Eventually this becomes the centerpiece of the UI.

But **don't fake it now**.

Just architect the interface so that this panel can slot into the same reasoning loop later.

---

# 13. I would distinguish three kinds of "space"

This is particularly important given our previous discussion.

Your UI should eventually make these visually distinct:

### Physical / observed space

```text
64 × 64 pixels
```

### Relational space

```text
entity #4
     ↓ distance 18
entity #9
```

### Latent / dynamical space

```text
Z_t
  selected_color = RED
  mode = PAINT
  phase = 2
```

And then:

### Time

```text
Z0 → Z1 → Z2 → Z3 → Z4
```

So the student can literally see:

> **pixels → structured state → latent state → dynamics → action → new observation**

That is the architecture.

---

# 14. I would remove most of the masks

Not all of them.

But your current `LAYERS` list contains:

* Entities
* Controlled
* Interest
* Affect
* Clicked

and the snapshot itself has even more spatial signals. ([GitHub][1])

That is exactly the problem you identified.

I'd classify every visualization as one of:

### Primary

Always meaningful:

* observed frame
* entities
* predicted effect
* actual effect

### Diagnostic

Available on demand:

* interest
* clicked
* obstacles
* route
* action effect history

### Deprecated

Remove entirely if no longer consumed by the model.

The UI should **not preserve dead representations just because the code once produced them**.

That's actually an important research hygiene principle.

---

# 15. I would add an explicit "Why did you do that?" panel

This should be the bottom-right or central panel.

For the selected action:

```text
WHY ACTION4?

1. Candidate generation
   └─ ACTION4 can change relation R17

2. Relevant hypothesis
   └─ H12: reduce distance(#4,#9)

3. Evidence
   ├─ ACTION4 changed distance 7 times
   ├─ mean change: −5
   └─ no contradictory observations

4. Alternatives
   ACTION1   0.21
   ACTION2   0.18
   ACTION4   0.72  ← selected

5. Prediction
   distance: 26 → 21

6. Verification
   pending
```

This is **the bridge between the model and teaching**.

A student can ask the most important question:

> "Why did it do that?"

and the answer comes directly from the architecture.

---

# 16. Then after the action, turn that into "Did you learn?"

This is the other half.

After advancing one step:

```text
WHY ACTION4?
        ↓
WHAT HAPPENED?
        ↓
DID THE PREDICTION HOLD?
        ↓
WHAT CHANGED IN THE MODEL?
```

Example:

```text
PREDICTION
distance 26 → 21

OBSERVED
distance 26 → 21

✓ CONFIRMED

MODEL UPDATE
ACTION4 confidence
0.72 → 0.86

BELIEF UPDATE
#4 remains CONTROL

HYPOTHESIS
H12 continues
step 2/8
```

Or:

```text
✕ FALSIFIED

Prediction:
distance should decrease

Observed:
distance increased

MODEL UPDATE
H12 discarded

ACTION4
removed from H12's candidate set
```

That would make the **scientific loop** visible.

---

# 17. The UI should explicitly show "what the agent does NOT know"

This is another place where your project can teach something valuable.

Have a little section:

```text
UNKNOWN

Goal              ?
Selected object   ?
ACTION5 effect    ?
Entity #13 role   ?

The agent is not assuming these.
```

And when something becomes known:

```text
UNKNOWN
ACTION5 effect
       ↓
confirmed
       ↓
AFFECT: #12
```

That would be much more faithful to your actual philosophy than a conventional AI dashboard.

---

# 18. I would have a "Model Map" view separate from the live debugger

This is probably the second major screen.

### Screen 1: **Run**

"What is happening right now?"

### Screen 2: **Model**

"What does the agent currently believe about the game?"

The model view could look like:

```text
                       GAME MODEL

             ┌──────────────┐
             │   ENTITY #4  │
             │   CONTROL    │
             └──────┬───────┘
                    │ moves
                    ▼
             ┌──────────────┐
             │ ACTION2/4    │
             └──────┬───────┘
                    │ changes
                    ▼
             ┌──────────────┐
             │ RELATION R7  │
             │ distance     │
             └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │ HYPOTHESIS   │
             │ reduce R7    │
             └──────────────┘
```

Later:

```text
             LATENT VARIABLE
                    │
           ┌────────┴────────┐
           ▼                 ▼
      ACTION5             ACTION6
           │                 │
           ▼                 ▼
       state update      observation
```

This becomes the **architecture teaching screen**.

---

# 19. I'd actually make the UI reflect your module boundaries

Not as 14 cards, but as a visual pipeline:

```text
PERCEPTION
   ↓
ENTITY
   ↓
RELATION
   ↓
BELIEF
   ↓
WORLD MODEL
   ↓
HYPOTHESIS
   ↓
PREDICTION
   ↓
DECISION
   ↓
ACTION
   ↓
OBSERVATION
```

Each stage gets a small status indicator:

```text
PERCEPTION     ● 12 entities
ENTITY         ● 12 tracked
RELATION       ● 18 relations
BELIEF         ● 3 roles
WORLD MODEL    ○ not implemented
HYPOTHESIS     ● H17 active
PREDICTION     ● 82%
DECISION       ● ACTION4
```

That would be *fantastic* for teaching.

It also gives you a debugging superpower:

> "Where did the reasoning chain break?"

Instead of hunting through panels.

---

# 20. A concrete V1 I would actually implement

Don't wait for the latent model.

I'd build **UI V2 now**, with placeholders for the future.

### Top

```text
ARC-AGI-3 / cd82

Level 2 · Step 43 / 400 · 1 level completed
RUNNING · seed 12345

Timeline ────────────────────────●────────────
```

### Main world

```text
┌─────────────────────────────┐
│ WORLD                       │
│                             │
│                             │
│          64 × 64            │
│                             │
│                             │
└─────────────────────────────┘
```

### Beneath it

```text
OBSERVE          BELIEVE             PREDICT
────────         ───────             ───────
12 entities      #4 CONTROL 87%      dist 26→21
3 relations      #9 AFFECT 74%        move +5
2 changes        goal ?               confidence 81%
```

### Decision

```text
CURRENT HYPOTHESIS

H12
Reduce distance(#4,#9)
using ACTION4

Evidence: 7 observations
Progress: 26 → 21
Test: 2 / 8
```

### Action

```text
ACTION SPACE

       ACTION1
          ↑
ACTION3 ←   → ACTION4 ★
          ↓
       ACTION2

ACTION5   ACTION6   ACTION7
```

### Result

```text
PREVIOUS PREDICTION        OBSERVED

#4 moves +5,+0             #4 moved +5,+0
distance → 21              distance = 21

                         ✓ MATCH
```

### Bottom

```text
HISTORY

●──●──●──◆──●──●──✓──●──●──▲
        H12                 LEVEL UP
```

That is already an enormous improvement without requiring latent space.

---

# 21. Then V3 when temporal latent state exists

You add one new section:

```text
WORLD MODEL

                 Zₜ
                  │
             ACTION4
                  │
                  ▼
                 Zₜ₊₁
                  │
                  ▼
             observation
```

And:

```text
LATENT VARIABLES

selected_color       RED     84%
mode                 PAINT   71%
phase                2       93%
target               #17     67%
```

Then your UI has genuinely evolved with the architecture rather than needing to be redesigned again.

---

# 22. One architectural change I'd make *before* touching the frontend

This is important.

Right now `snapshot()` is already deliberately designed to capture "everything worth knowing at one decision point." ([GitHub][1])

I'd formalize that into a **UI-facing `TraceFrame` schema** rather than having the HTML know about your internal Python objects.

Something conceptually like:

```text
TraceFrame
├── observation
├── perception
├── entities
├── relations
├── belief
├── latent_state          # future
├── hypotheses
├── predictions
├── decision
├── action
├── outcome
├── belief_update         # future
└── history_context
```

Then the UI consumes **that**.

This is important because otherwise your UI becomes coupled to internals again.

The current recap is already halfway there, but it mixes architectural state, viewer-computed diagnostics, and presentation-oriented data. For example, `action_signature` is explicitly computed by the viewer rather than being agent state. ([GitHub][1])

That's fine for a prototype.

For the teaching UI, I'd make the distinction explicit:

```text
AGENT STATE
what the model actually knew

DERIVED VIEW
what the UI calculated to help visualize it
```

Put a tiny `DERIVED` label on the latter.

That preserves epistemic honesty.

---

# 23. The most important UI rule I'd give whoever implements this

I would put this in `recap_template.html` as a design rule:

> **Every visual element must answer one of four questions:**
>
> 1. What did the agent observe?
> 2. What does the agent currently believe?
> 3. What does the agent predict will happen?
> 4. Why did the agent choose its action?

If something doesn't answer one of those:

**hide it by default.**

This would eliminate probably 60% of the current clutter.

---

# 24. And there's a fifth question for the future

Once the temporal model exists:

> **How did the agent's internal state change because of the observation?**

That gives you:

```text
OBSERVE
   ↓
BELIEF BEFORE
   ↓
NEW EVIDENCE
   ↓
BELIEF AFTER
```

That's going to be one of the most educational parts of the entire system.

Imagine showing a student:

```text
Before ACTION5

selected_colour
  RED      0.51
  BLUE     0.49

       ↓ ACTION5

Observation:
block becomes RED

       ↓

After

selected_colour
  RED      0.96
  BLUE     0.04
```

Now they can **see learning happen**.

That is far more powerful than another text log.

---

## My recommended implementation sequence

I would therefore do this in **three UI passes**, deliberately decoupled from the research architecture:

### Pass 1 — "Cognitive debugger"

Do **now**.

* Replace three-column dashboard with reasoning-loop layout.
* Make world/frame dominant.
* Remove dead masks.
* Turn masks into overlays.
* Replace event log with structured current-step causal explanation.
* Make entities clickable.
* Cross-link entity ↔ action ↔ relation ↔ hypothesis.
* Build proper timeline with event markers.
* Add `WHY THIS ACTION?`.
* Add `PREDICTION → OBSERVATION → RESULT`.
* Keep raw brief and raw diagnostics behind an "Engineering" drawer.

### Pass 2 — "World-model debugger"

When latent state exists.

Add:

* latent variables
* uncertainty
* `Z_t`
* predicted `Z_t+1`
* multi-step rollout
* belief update
* hidden-state history
* observationally equivalent histories

### Pass 3 — "Teaching mode"

Once Pass 2 is stable.

Add:

* guided walkthrough
* "Explain this step"
* architecture map
* toggle between **student view** and **researcher view**
* side-by-side "what the world did / what the agent thought would happen"
* replay of successful and failed reasoning
* maybe eventually an interactive "pause and predict what the agent will do next" mode

That last one could be genuinely excellent for teaching.

---

And I think **"student mode" versus "researcher mode" is the right long-term answer to your compression problem**.

The researcher needs:

```text
raw masks
raw residuals
action tallies
JSON
confidence
internal state
```

The student needs:

```text
What did it see?
What did it think?
Why?
What did it predict?
What happened?
What did it learn?
```

Those are **not the same UI**.

Don't try to make one screen satisfy both. Make the underlying trace identical, but give it two projections.

Your current recap already has an unusually good foundation for this because it captures the live agent state at every decision rather than reconstructing it afterward. ([GitHub][1]) The next step is to stop treating that snapshot as "data to populate panels" and start treating it as a **cognitive trace from which multiple views can be rendered**.

That is the conceptual change I would make before writing another pixel of frontend code.

[1]: https://github.com/nvaidyan1/arc-agi-3/blob/main/scripts/recap.py "arc-agi-3/scripts/recap.py at main · nvaidyan1/arc-agi-3 · GitHub"
[2]: https://github.com/nvaidyan1/arc-agi-3/blob/main/docs/system_architecture.md "arc-agi-3/docs/system_architecture.md at main · nvaidyan1/arc-agi-3 · GitHub"
