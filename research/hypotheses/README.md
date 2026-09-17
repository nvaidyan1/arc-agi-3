# Hypotheses

One file per substantive architectural hypothesis: claim, mechanism,
prediction, falsifier, experiment, metrics, status log. Opened only when a
build is about to test it (reviewer C, 2026-09-14: "only create an artifact
when a recurring research problem demands it"). `history.md` stays the
chronological record; these are the scientific claims it tests.

Each file's own `Status:` header line is kept in sync with this table's right column — added 2026-09-16 after an external reviewer (`docs/expert-reviews/reviewer_g_09_16_2026.md`) proposed H012/H013 as new work that turned out to already be H011 Stage 2 and H007, most likely because several files' headers had drifted to say "OPENED — not built" long after their status logs below recorded a tested result. Read this table first; if a header ever disagrees with it, the table is right and the header is a bug to fix, not a fact to act on.

| id | title | status |
|---|---|---|
| H001 | Conditional affordances — a lever given a precondition | TESTED — falsifier 2 met on cd82 |
| H002 | An intermittent LLM as hypothesis scientist, not controller | IN PROGRESS — no model attached |
| H003 | A predictive transition model from the evidence already held | IN PROGRESS |
| H004 | Competing transition hypotheses — one press falsifies one | TESTED — mechanism sound, net score down 0.110->0.075 unpaired vs E-7a, not promoted |
| H005 | Conjunctive preconditions — carrying a two-factor rule intact | IN PROGRESS — mechanism confirmed live on cd82; needs a second condition kind (state, not adjacency) |
| H006 | The aliasing is state, not noise — a few history-set variables resolve it | TESTED (Days 1–3) — holds for the meter class: `Z1 = actions since reset` confirmed with repeats on 6 games; mechanic remainder unresolved by the history family |
| H007 | A `state` condition kind — a two-factor rule becomes jointly satisfiable | TESTED (Day 4) — mechanism 3/3 seeds, P1 met 1/3; the walk, not the state, now limits joint satisfiability on cd82 |
| H008 | State in the tallies raises k-step predictive sufficiency, only where state exists | TESTED (Day 5) — Z1 gains 2-7pt at k=10 on 5/10 aliased games, 0 on controls; move-map games separate cleanly at k=10 |
| H009 | cd82's walk fails in the planner's model class, not the representation or the search | CLOSED — reading B; live-episode learning viable on 8-9/10 seeds within budget; the failures trace to the same exploration gap as H007's | 
| H010 | A position-graph transition model closes the gap H009 found | STAGE 2 SHIPPED, mechanism proven (persistence + crash-safety, n=30 clean) — but the cd82 oracle this stage was meant to close still did not close end-to-end; stays open |
| H011 | A novelty term in target selection reaches under-explored cells the salience heuristic misses | SHIPPED — click blend live; strip clicks 1.6% -> 42-52%. n=30 parity gate passed: median score up, named parity games unregressed, one flagged game (lp85) read as noise. |
| H012 | Sighting-count novelty in the frontier tier raises orbit coverage | OPENED — waiting on H011 Stage 2's parity gate before starting |
