# H006: The aliasing is state, not noise — a few history-set variables resolve it

Status: TESTED — holds for the meter class: `Z1 = actions since reset` confirmed with repeats and a null on 6 games; the mechanic remainder (sk48/su15/sc25/g50t) is not resolved by the history-derived family. See the status log below for the day-by-day record; this line is kept in sync with `research/hypotheses/README.md`.
Research question: RQ2 (predictive world modelling)
Date opened: 2026-09-15
Origin: reviewer C, fourth pass (`docs/expert-reviews/reviewer_c_09_15_2026.md`,
§3, §5, §16; second note §4–6), measured before adopting:
`scripts/alias_probe.py` (`docs/history.md` 2026-09-15, "Perceptual
aliasing"). First of three separately-falsifiable claims the week tests —
H006 (is there state?), H007 (can a hypothesis name it?), H008 (does it
predict?). Split on 2026-09-15 so each can fail on its own: state can be
real yet not conditionable in the schema; a condition can be satisfiable
yet not predictive.

## Claim

On the ten games where identical (frame, action) contexts yield different
next frames, the divergence is **hidden state, not stochasticity**: a
small set of variables that are functions of history — an entity's
descriptor set by an earlier action and held, or a simple history feature
— partitions most aliased contexts' outcomes. Where no such variable
exists the divergence is noise, and that is also a finding.

What this is not: no LSTM/LMU/JEPA; no semantic names (`selected_color`,
`mode` — a variable is `Z<n>` with a domain, a value and evidence,
described after the fact); no new perception primitive.

## Mechanism

```
LatentVariable   id Z<n>, domain (values seen), value | None, set_by (action, step),
                 evidence for / against
admit(Z)         only if Z splits >= 1 aliased context's outcomes
                 -- the temporal form of "no slot without evidence": don't
                    retain history unless it changes the predictive distribution
kinds            (a) visible-persistent: an entity's descriptor key, selective
                     under some actions (Belief.effects), held otherwise
                 (b) history-derived: last action that changed entity E; count of
                     action A since level start (mod 2..4); E ever vanished;
                     steps since E last changed
splitter score   for each aliased context, does Z's value partition the outcomes?
                 rank candidates by contexts resolved, per game
```

Built entirely offline over `recordings/` (Days 1–3 of the plan); no
`agent/` change. Day 2's harness (`scripts/latent_probe.py`, extending
`probe_relations.replay` to belief + predictor) also re-keys the aliased
contexts by the existing S_t, so the vocabulary's own contribution is
measured before any new variable is credited.

## Prediction

1. On cd82 one candidate variable resolves >= 50% of the aliased
   contexts.
2. On >= 3 of the 10 aliased games some candidate resolves >= 50%.
3. The 12 games at 0% aliasing admit no variable (nothing to split) —
   the admit rule stays silent where the frame is sufficient.

## Falsifier

- No candidate in either family resolves > 20% of any game's aliased
  contexts: the divergence is stochastic, or the variable families are
  wrong. The hidden-state framing is then unsupported on this data and
  the review's rank-1 bottleneck is not this project's; H007 is built
  for cd82 anyway (its second factor is visible-persistent by
  inspection), H008 is not.
- A candidate resolves contexts on the 0% games: the splitter is fitting
  noise, and the score is too permissive.

## Experiment

Day 1: `alias_probe.py --dump` for cd82, m0r0, sk48, g50t; replay each
aliased context's two outcomes through the recap; classify per game,
state vs stochastic, by eye — a 10-row table here. Day 2: the offline
S_t harness and the pixels-vs-S_t re-key. Day 3: both generators, the
splitter score, the ranking.

## Metrics

Per game: aliased contexts in pixels / in S_t / resolved by the best Z;
the best Z's kind and description.

## Status log

- 2026-09-15 opened. Aliasing measured: 654 / 4,142 repeated contexts
  (15.8%); 12 games at 0%, 10 at 44–84%; cd82's divergence sits on the
  non-paint actions (`docs/history.md`, "Perceptual aliasing").
- 2026-09-15 **Day 1 done — the aliasing classified by eye and by two
  checks** (`alias_probe.py --explain`, plus scratch probes recorded in
  `docs/history.md` "Day 1: most of the aliasing is a quantised meter").
  Every aliased context's two outcomes were diffed; a context is *meter*
  when the diff lies entirely on a line that fills or drains
  monotonically within an attempt, *mechanic* otherwise.

  | game | aliased | meter (line) | mechanic | meter = f(actions since reset)? | mechanic reading |
  |---|---|---|---|---|---|
  | cd82 | 35 | 35 (row 63) | 0 | yes — 101/101 n-values, one length each | none: the swatch state is visible, H007 needs no hidden variable |
  | m0r0 | 76 | 76 (rows 0, 63) | 0 | yes — 152/152 | none |
  | ka59 | 26 | 26 (row 63) | 0 | yes — 101/101 | none |
  | wa30 | 39 | 39 (row 63) | 0 | yes — 201/201 | none |
  | g50t | 122 | 114 (row 63) | 8 | yes — 131/131 | 8 contexts, 24–48-cell diffs; last-click / press-count features leave all 8 unresolved |
  | cn04 | 32 | 32 (row 0) | 0 | per level — rate differs between L0 and L1 | none |
  | dc22 | 46 | 46 (row 63) | 0 | yes, modulo a 1-cell offset after RESET (the probe's start snapshot, not the game) | none |
  | sk48 | 96 | 76 (row 53) | 20 | **no** — up to 8 lengths per n; ticks on something else (candidate: moves of the CONTROL thing — needs S_t) | ACTION7 swaps two tile blocks in a direction the frame does not show; last click resolves 1, 16 still aliased |
  | sc25 | 137 | 124 (cols 62–63) | 13 | **no** — drains 2 cells on some moves, not per action (needs S_t) | 13 unresolved |
  | su15 | 31 | 0 | 31 | — | ACTION7 moves or jumps a 3×3 block; two consecutive presses from one frame differ (a no-op, then a move); clicks around the block precede; presses-since-click leaves 8 still aliased |

  **568 of 640 (89%) are quantised meters**: the hidden variable is the
  sub-cell remainder of a resource counter, and on five games it is
  exactly *actions since reset* — real, deterministic, history-derived
  (kind b), and goal-irrelevant. The agent already reads these lines as
  stamina / CONTEXT; what it lacks is the counter that makes their next
  tick predictable. **Mechanic remainder: 72 contexts on three games**,
  almost all with two visits, so a splitter can only be refuted on this
  data, not confirmed by repeats (the re-key control: nearly every
  feature made contexts singletons). **cd82 has no mechanic aliasing**:
  its frame is sufficient, and its second factor is visible-persistent —
  H007's condition kind, with no dependence on H006.

  P1 and P2 as written are met — by the meter variable, which is
  vacuous for the goal. Amended, not rewritten: the live question is
  the mechanic remainder, and it needs (i) S_t from Step 2 for the
  candidate features that reference the controlled thing (sk48's and
  sc25's meter functions too), and (ii) **more repeats** — a targeted
  non-LLM sweep of su15, sk48, g50t, sc25 (10 seeds, ~30 s each) to
  raise visits per context before Day 3's splitter can confirm anything.
  Gate outcome: the history-derived family stays (it is what resolves
  the meters); the Day-3 target narrows to the 72.
- 2026-09-15 **Days 2–3 done — S_t traces and the splitter, ten seeds.**
  `scripts/latent_probe.py trace` taps the real agent at `_select` and
  writes S_t per step (entities with ids / roles / descriptor keys /
  bboxes, the residual vector, displacement, stamina fraction, the
  previous forecast's score); its action stream matched the
  `play_local.py` recording of the same seed step for step (su15, seed
  1, 401 steps) — the replay harness's determinism claim, now free on
  every trace. Traced the ten aliased games plus sp80, ls20, ar25 as
  controls, seeds 1–10, 400 steps (`recordings/latent/seed*/`, gitignored).
  `scripts/latent_splitter.py` scores history-derived candidates on every
  pixel-aliased context: resolved (repeats, one outcome per value) /
  singleton (re-key made the visits unique — vacuous) / still (refuted),
  with a shuffle null.

  **Step 2 — what S_t already resolves.** Keyed by S_t, nearly every
  pixel-aliased context becomes a singleton (ids and the residual vector
  differ between visits), so S_t *confirms* almost nothing; what it leaves
  **still aliased with identical agent state** is the honest core: sk48
  56, m0r0 39, cn04 28, g50t 18, su15 15, cd82 4, ka59 1, wa30 1, dc22 0,
  sc25 0 (162 of 1,252). Adding actions-since-reset to the key drives
  every one of those to zero — but as singletons, not resolutions (the
  counter is strictly increasing within an attempt), so this is
  consistency, not confirmation. One-step forecast accuracy on the
  aliased contexts is within a few points of the all-steps accuracy on
  every game (largest gaps su15 75 vs 84, wa30 77 vs 84 on the entity
  layer): the aliasing costs the forecast little, because the meter is
  the CONTEXT layer where "unchanged" is already the majority forecast.

  **Step 3 — the splitter.** `n_reset` (actions since the attempt began)
  is confirmed *with repeats, above null, with zero contradictions* on
  every meter game: cd82 82 resolved / 0 still (null 3.8), m0r0 118 / 0
  (2.6), dc22 325 / 0 (4.8), ka59 52 / 0 (0.2), wa30 147 / 0 (2.8), cn04
  13 / 0 (1.0); g50t 229 resolved but 102 still (its meter is not a pure
  function of n; `n_level` leaves 45). On the mechanic games nothing in
  the family holds: sk48 best candidate 19 resolved vs null 21 (noise);
  sc25 60 vs 31 (weak, 87 still); su15 `n_moved` 10 vs 1.8 with 23 still
  (suggestive of a phase tied to how often the controlled thing has
  moved — not confirmed).

  **Verdict so far.** Claim (state, not noise) **holds for the meter
  class** — one history-derived variable, `Z1 = actions since reset`,
  admitted on six games by the admit rule with repeats and a null. For
  the mechanic remainder (sk48's ACTION7 swap, su15's ACTION7 heading,
  sc25's drain, g50t's residue) the family is refuted or below null:
  P1/P2 are met only by the nuisance variable. H007 is unaffected (cd82's
  second factor is visible). H008 gains one cheap, certain improvement —
  the counter makes the meter's next tick predictable — and should not
  expect more from H006. What would move the mechanic remainder: a
  candidate family that references the controlled thing's *relation* to
  the clicked or moved entity (needs S_t, now available), and more visits
  per context on su15/sk48 specifically; both are week-2 items, not this
  week's.
