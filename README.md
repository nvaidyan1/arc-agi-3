# ARC-AGI-3 — Evidence-Gated Agent

**Latest full sweep (25 games, 400 steps): 2026-09-15 16:08 ET — aggregate score 0.1431** — update this line after every full sweep. Details: [`docs/plan.md`](docs/plan.md), [`docs/history.md`](docs/history.md).

A from-scratch agent for the [ARC Prize 2026 — ARC-AGI-3](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3)
competition, plus a starter-kit toolchain (local play, recap viewer, Kaggle
submit) inherited from the official template. **Governing principle: no
semantic slots without evidence** — every perceptual/semantic read is
produced by a falsifiable test and may return `None`; nothing assumes 2D
space, avatars, or a fixed pixel taxonomy. See [`docs/plan.md`](docs/plan.md)
(top) for the full statement and why.

## Docs — read these, not this file, for how it actually works

| file | what's in it |
|---|---|
| [`docs/plan.md`](docs/plan.md) | Living checklist + governing principles. **Start here.** `START HERE` section at the bottom is the handoff for the next session. |
| [`docs/history.md`](docs/history.md) | Append-only research log — every experiment, hypothesis/observation/inference, including failures. |
| [`docs/system_architecture.md`](docs/system_architecture.md) | How the agent actually works, no code-reading required. |
| [`docs/glossary.md`](docs/glossary.md) | Naming convention for features/modules. |
| [`research/hypotheses/`](research/hypotheses/README.md) | One file per architectural hypothesis: claim, mechanism, prediction, falsifier, status. |

## Setup

```bash
# Python 3.12 required. macOS: brew install python@3.12
mkdir -p .kaggle && echo "KGAT_..." > .kaggle/access_token && chmod 600 .kaggle/access_token
make setup                 # venv, deps, clones the framework
source .venv/bin/activate  # every new terminal, before calling scripts/*.py directly
```

## Commands

| Command | What it does |
|---|---|
| `make play-local` | Run the agent against every game (`GAME=ls20` for one; `RENDER=terminal\|human` to watch) |
| `make verify-local` | 50-step smoke test on 2 games |
| `make test` | Unit tests (perception/control/constraints/hypothesis — no game engine needed) |
| `make recap GAME=cd82` | Step through one run in the browser, per-decision detail (`SEED=`/`STEPS=` to replay an exact run) |
| `make analyse` | Score spread / depth / completion timing across recorded sweeps (`BY_GAME=1` for per-game) |
| `make list-games` | Print every game id |
| `make backfill-summaries` | Rebuild sweep summaries from `recordings/` |
| `make notebook` | Build the Kaggle notebook, no push |
| `make submit` | Build **and** push to Kaggle (uses one of 5 daily submissions only once you click "Submit to Competition" on kaggle.com) |
| `make status` | Check your latest Kaggle run |
| `make clean` | Remove venv, downloads, generated notebook |

Before the first `make submit`: set your username in
[`notebooks/kernel-metadata.json`](notebooks/kernel-metadata.json).
Accelerator (`cpu`/`t4`/`p100`/`rtx6000`) is one line in
[`scripts/build_notebook.py`](scripts/build_notebook.py).

## Game facts (from reading the framework directly)

- Action space: `RESET`, `ACTION1`–`ACTION5`, `ACTION7` (no payload); `ACTION6` takes `x,y` in `0–63`. Legal actions per frame are in `latest_frame.available_actions` — filter against it, don't guess.
- Frame: 64×64 grid, cell values `0–15` (16-color palette).
- `GameState`: `NOT_PLAYED`, `NOT_FINISHED`, `WIN`, `GAME_OVER` (retryable via `RESET`, not terminal).
- Score per level: `(human_baseline_actions / actions_taken)² × 100`, capped at 100, 0 if not completed. Game score is the **level-index-weighted** average over all levels — level 1 of a 7-level game is worth 1/28. Depth dominates speed.
- Jargon: **game** (contains **levels**), one observation is a **frame**, no episode boundary (`GAME_OVER → RESET` is a retry within the same run).

## Project layout

```
agent/            The agent — my_agent.py (policy) + perception/control/
                   constraints/attention/navigation/relations/belief/
                   hypothesis/proposer_llm/predictor/supervisor/kinds/brief
docs/              plan.md, history.md, system_architecture.md, glossary.md
research/          hypotheses/ (H001-H00N), council notes
scripts/           play_local.py, recap.py, replay_ablation*.py, analyse_sweeps.py, ...
results/sweeps/    Committed sweep summaries (git is the retention policy)
tests/             Unit tests, no game engine needed
vendor/, .venv/, .kaggle/, environment_files/, recordings/   gitignored
```

## Troubleshooting

- **`python3.12: command not found`** — install Python 3.12.
- **`make submit` → edit kernel-metadata.json** — set your username there first.
- **`make submit` → `401 Unauthorized`** — regenerate your token at [kaggle.com/settings](https://www.kaggle.com/settings), overwrite `.kaggle/access_token`.
- **`make play-local` → "Could not create environment"** — needs internet once, to cache `environment_files/`; offline after that.
