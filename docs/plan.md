# Plan

Living document — the current state of the work and what's next. Update
this in place as decisions change; don't append dated entries here, that's
what `history.md` is for.

## Current state (2026-09-13)

- Environment is set up: Python 3.12 venv, framework cloned, Kaggle token
  configured, `make verify-local` / `make play-local` confirmed working
  against all 25 locally-visible games.
- Repo is pushed to `origin` (`github.com/nvaidyan1/arc-agi-3`), with the
  original starter kept as `upstream` for pulling future updates.
- `agent/my_agent.py` has moved past the random baseline to a first
  **game-agnostic exploration heuristic**:
  - filters to `latest_frame.available_actions` instead of guessing across
    all 7 actions,
  - tracks per-action "did this change the frame" rate and biases sampling
    toward actions that do something (epsilon-greedy, ε=0.25),
  - for the one complex action (`ACTION6`, a grid click), targets a cell
    that differs from the frame's most common color instead of a random
    coordinate.
  - Verified: runs cleanly across all 25 games with no exceptions. Score is
    still 0.0 — expected, since this is exploration, not puzzle-solving.
- Game mechanics reference (action space, observation space, scoring,
  jargon) lives in `README.md` under "Game mechanics reference", not a
  separate doc — keep it there so it stays next to the rest of the
  operating instructions.

## Next

- Decide what "solving" looks like on top of exploration — e.g. detecting
  when a frame change correlates with `levels_completed` increasing (a
  reward signal), and reusing successful action sequences.
- No official submission has been made yet (0 of 5 daily submissions
  used). Submissions are only run by the user, never autonomously.

## Open questions / decisions pending

- None right now — strategy direction (generic exploration over per-game
  hardcoding or a full model-based approach) was chosen by the user; see
  `history.md` for when/why.
