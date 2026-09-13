# Glossary

Naming convention: when a feature we build already corresponds to a named
concept in cognitive science / ML / RL literature, use that name — in code
comments, docstrings, `plan.md` items, and commit messages — instead of an
ad-hoc description. This keeps history legible as it grows and makes the
work easier to describe to someone outside this repo. Add an entry here
whenever a new feature earns one.

This is about *naming things we build* after the concept they implement —
not about restructuring the code itself around a cognition metaphor (e.g.
a `memory.last_action` namespace). That idea was raised and deliberately
shelved: it would fight against plain, readable Python for a mapping that
isn't load-bearing. Revisit only if it turns out to earn its keep.

| Term | Definition | Source | Where implemented |
|---|---|---|---|
| **Affordance** | The set of actions an environment "offers" at a given state | J.J. Gibson, *The Ecological Approach to Visual Perception*, 1979 | `latest_frame.available_actions` filtering in `agent/my_agent.py` |
| **Contingency detection** (sensorimotor contingency) | Learning which of your actions reliably produce a sensory change | O'Regan & Noë, "A sensorimotor account of vision," 2001 | per-action tries/changes bandit in `agent/my_agent.py` |
| **Salience map** | A representation ranking locations in a scene by how much they stand out / draw attention | Itti & Koch, "A model of saliency-based visual attention," 1998 | `_pick_coordinate`'s "recently active + non-background cell" ranking |
| **Habituation** | Decreased response to a stimulus after repeated exposure with no effect | Thompson & Spencer, "Habituation: a model phenomenon," 1966 | `_region_is_dead` — coarse grid regions that absorb clicks with zero effect get avoided |
| **Epsilon-greedy** | Mostly exploit the best-known option, occasionally explore at random | Sutton & Barto, *Reinforcement Learning: An Introduction* | `EXPLORATION_EPSILON` in `agent/my_agent.py` |
| **Go-Explore** / "first return, then explore" | Remember the best trajectory reached so far, deterministically return to it, then explore further from that frontier | Ecoffet et al., "First return, then explore," *Nature*, 2021 | built and reverted — the engine already checkpoints level progress, so there's no frontier to return to; see `plan.md` "Tried and reverted" |
| **Contingency awareness** | Learning which parts of the observation are under the agent's own control, by detecting what covaries with its actions | Bellemare, Veness & Bowling, "Investigating Contingency Awareness Using Atari 2600 Games," AAAI 2012 | `acts_locally` + per-cell click memory in `agent/my_agent.py` — the start of the representation layer |
| **Common fate** | Gestalt grouping principle: elements that change together are perceived as one object — grouping by shared *change* rather than shared appearance | Gestalt psychology (Wertheimer) | Not implemented; the intended basis for deriving objects without assuming they are contiguous colored blobs |
| **Self–other distinction via contingency** | Bootstrapping "self" vs "world" by noticing some sensory consequences are reliably contingent on one's own actions and others are not | Developmental psychology (Watson) | Not implemented; the conceptual target for "the thing I control" vs "the thing I affect" |
| **Efference copy / forward model** | Predict the sensory consequences of your own action; what matches is self, what mismatches is world | von Holst & Mittelstaedt | Not implemented |
| **Empowerment** | Information-theoretic measure of how much an agent's actions influence future states — controllability with no spatial assumption | Klyubin, Polani & Nehaniv | Not implemented |
| **Compact symbolic modeling** | Convert raw observations into a small domain-specific symbolic state representation, then plan over that rather than over raw pixels | Standard principle in classical / neurosymbolic planning | Not implemented; guiding philosophy for the next steps — see `plan.md` |
| **Incentive salience** | A location or cue gains "wanting" through association with reward/change, separately from whether it is itself pleasant — the *attention-grabbing* effect of a learned association | Berridge & Robinson, "What is the role of dopamine in reward: hedonic impact, reward learning, or incentive salience?", *Brain Research Reviews*, 1998 | `_interest` / `_bump_interest` / `_decay_interest` in `agent/my_agent.py` — the region-of-interest map, fed by residual change, vanish sites, and level-ups; consumed by `_pick_coordinate` |
| **Clark-Evans nearest-neighbour index** | Ratio of observed mean nearest-neighbour distance to the value expected under complete spatial randomness; R<1 clustered, R≈1 random, R>1 dispersed | Clark & Evans, "Distance to nearest neighbor as a measure of spatial relationships in populations," *Ecology*, 1954 | `scripts/roi_probe.py` — used to test whether residual/vanish sites cluster before building the salience map on top of them |
