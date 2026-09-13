# History

A dated log of what's been done and why, including how AI assistance was
used at each step. Kept honestly, not retroactively cleaned up — the ARC
Prize Foundation's Paper Prize track and the Grand Prize's "Solution
Writeup" criteria reward transparent, genuine methodological contribution
over an unexplained leaderboard number, so however AI is used in building
this, it should show up here plainly.

Entries are append-only; append a new one per work session, don't edit old
entries except to fix factual errors.

---

## 2026-09-13 — Environment setup and repo bootstrap

Worked with Claude Code (Sonnet 5) to go from a fresh clone to a working
local dev loop. Claude: installed Python 3.12 via Homebrew (missing on this
machine), ran `make setup` (venv, deps, framework clone), created the
project-local `.kaggle/access_token` file from a token the user provided
directly in chat, and verified `make verify-local` passes. Claude also
renamed the original `origin` remote to `upstream` and added a new `origin`
pointing at a GitHub repo the user created and asked to be used
(`github.com/nvaidyan1/arc-agi-3`), then pushed. The user set explicit
ground rules up front: never run `make submit` / touch Kaggle submissions
autonomously (5-per-day budget, user-only), and never commit without being
asked.

## 2026-09-13 — Game mechanics orientation

User asked introductory questions about the action/observation space
(action count, grid size, pixel depth) after watching the random-baseline
agent play. Claude answered by reading the actual `arcengine`/`arc_agi`
source (not guessing or relying on prior knowledge) via a research
sub-agent, confirming: 8 actions (`RESET`, `ACTION1`-`5`, `ACTION7` simple,
`ACTION6` complex with `x,y` in `0-63`), 64×64 frames, values 0-15 (16-color
palette), and the 4-value `GameState` enum. This was folded into
`README.md` under "Game mechanics reference" (an earlier draft lived in a
separate `docs/game-mechanics.md`, moved into the README per the user's
call that a separate file would go stale before submission).

## 2026-09-13 — First non-random agent strategy

User chose, from four options Claude proposed (generic exploration
heuristic / per-game hardcoding / model-based-learning / minimal
non-zero-score patch), the **generic exploration heuristic** direction —
explicitly to match the competition's stated generalization goal rather
than overfitting to the ~25 locally-visible games. Claude implemented it in
`agent/my_agent.py`:
- filter candidate actions to `latest_frame.available_actions` (discovered
  mid-implementation that games declare a legal-action subset, e.g. `ls20`
  → `[1,2,3,4]`, `vc33` → `[6]` — this wasn't known going in),
- an epsilon-greedy bandit over "does this action change the frame",
- salience-based coordinate picking for the complex click action.

Verified locally: ran against all 25 games with `make play-local
--max-steps 30`, no exceptions, `ls20` confirmed to only ever pick from
`ACTION1`-`4` as expected. Score remains 0.0 (expected — exploration alone
doesn't solve levels). Not committed yet; user reviews and commits
explicitly.

Also added `RENDER=terminal` / `RENDER=human` / `RENDER=terminal-fast`
support to `scripts/play_local.py` and the `Makefile` — the underlying
`arc_agi` package already shipped these renderers but the local script only
exposed one of them.
