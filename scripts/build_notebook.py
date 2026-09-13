"""Splice every module in `agent/` into `notebooks/submission.ipynb`.

The notebook follows the pattern used by Kaggle's official sample
("ARC3 Sample Submission - Stochastic Goose"):

  Cell 1: install the `arc-agi` wheel from the offline competition dataset.
  Cell 2: create the staging directory.
  Cell 3+: one `%%writefile` cell per module in `agent/`.
  Then:   if running inside the Kaggle competition rerun, wait for the
          gateway sidecar, copy the framework into /kaggle/working/, drop
          every module in as a framework template, register MyAgent, and
          run `python main.py --agent myagent`.
  Last:   otherwise (during commit / save-and-run-all), write a dummy
          submission.parquet so Kaggle accepts the commit.

WHY INLINE RATHER THAN AN ATTACHED DATASET
------------------------------------------
The obvious alternative is to upload `agent/` as a private Kaggle dataset
and `sys.path.append` its mount point. That was considered and rejected
for this repo, for two reasons that both bite only at rerun time — the
one moment we cannot afford a surprise, since a failed rerun costs one of
five daily submissions:

  1. **Version skew is silent.** Two artifacts (notebook + dataset) must
     stay in sync. Forget `kaggle datasets version` and the rerun runs
     stale code that imports perfectly and produces wrong results. A
     crash would be kinder.
  2. **It can't be verified locally.** `/kaggle/input/...` paths don't
     exist here, so the packaging is untestable until it's too late.

Inlining keeps one self-contained artifact whose contents are byte-
identical to what we test locally, and `make verify-packaging` proves the
assembled layout imports before anything is submitted.

You don't normally need to call this directly — `make submit` runs it.
"""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

# ─────────────────────────────────────────────────────────────────────────────
# CHANGE THIS ONE LINE TO PICK YOUR KAGGLE ACCELERATOR
# Options:
#   "cpu"      — no GPU. Good for the random starter or any non-ML agent.
#   "t4"       — Nvidia T4 ×2 (default; matches Kaggle's sample submission).
#   "p100"     — Nvidia P100 (single big-memory GPU).
#   "rtx6000"  — Nvidia RTX 6000 (g4-standard-48). ARC-AGI-3 exclusive,
#                burns GPU quota faster — use only when you're confident.
# ─────────────────────────────────────────────────────────────────────────────
ACCELERATOR = "t4"

# Internal mapping; don't edit unless Kaggle adds new options.
_ACCELERATORS = {
    "cpu":     {"name": "none",            "gpu": False},
    "t4":      {"name": "nvidiaTeslaT4",   "gpu": True},
    "p100":    {"name": "nvidiaTeslaP100", "gpu": True},
    "rtx6000": {"name": "nvidiaRtx6000",   "gpu": True},
}

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
NOTEBOOK_PATH = ROOT / "notebooks" / "submission.ipynb"
METADATA_PATH = ROOT / "notebooks" / "kernel-metadata.json"

# Where modules are staged before being copied into the framework. NOT
# /kaggle/working/ — anything there shows up as a notebook output, and
# the "Submit to Competition" UI would then offer it as a candidate
# submission file alongside submission.parquet, where an unlucky default
# selection rejects the submission.
STAGING = "/tmp/agent_src"


def agent_modules() -> list[Path]:
    """Every module to ship, with my_agent.py last.

    Order is cosmetic — the bootstrap in my_agent.py puts the staging
    directory on sys.path, so imports resolve regardless of which file
    was written first — but reading the notebook top to bottom is nicer
    when the entry point comes last.
    """
    modules = sorted(
        p for p in AGENT_DIR.glob("*.py") if p.name != "my_agent.py"
    )
    entry = AGENT_DIR / "my_agent.py"
    if not entry.exists():
        raise SystemExit(f"Could not find {entry}")
    return modules + [entry]


def code_cell(source: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {"trusted": True},
        "outputs": [],
        "execution_count": None,
        "source": source,
    }


def markdown_cell(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def build() -> dict:
    modules = agent_modules()

    install_cell = code_cell(
        "!pip install --no-index --find-links \\\n"
        "    /kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels \\\n"
        "    arc-agi python-dotenv"
    )

    mkdir_cell = code_cell(f"!mkdir -p {STAGING}")

    # One cell per module. `%%writefile` must be the first line of its own
    # cell, so each module gets its own.
    write_cells = [
        code_cell(f"%%writefile {STAGING}/{path.name}\n" + path.read_text())
        for path in modules
    ]

    run_cell_source = dedent(
        """\
        import os

        if os.getenv('KAGGLE_IS_COMPETITION_RERUN'):
            # Wait for the gateway sidecar to be ready.
            !curl --fail --retry 999 --retry-all-errors --retry-delay 5 \\
                  --retry-max-time 600 http://gateway:8001/api/games

            # Copy the framework into a writable location.
            !cp -r /kaggle/input/competitions/arc-prize-2026-arc-agi-3/ARC-AGI-3-Agents \\
                   /kaggle/working/ARC-AGI-3-Agents

            # Drop every agent module in as framework templates. They sit
            # side by side, and my_agent.py's sys.path bootstrap makes its
            # own directory importable so the siblings resolve here just
            # as they do locally.
            !cp /tmp/agent_src/*.py \\
                /kaggle/working/ARC-AGI-3-Agents/agents/templates/

            # Register MyAgent in the framework's agent registry. We rewrite
            # __init__.py because the upstream version eagerly imports
            # templates with deps we don't ship (langgraph, smolagents, etc.).
            with open('/kaggle/working/ARC-AGI-3-Agents/agents/__init__.py', 'w') as f:
                f.write(\"\"\"from typing import Type
        from dotenv import load_dotenv
        from .agent import Agent, Playback
        from .swarm import Swarm
        from .templates.random_agent import Random
        from .templates.my_agent import MyAgent

        load_dotenv()

        AVAILABLE_AGENTS: dict[str, Type[Agent]] = {
            'random': Random,
            'myagent': MyAgent,
        }
        \"\"\")

            # Point the framework at the gateway sidecar.
            with open('/kaggle/working/ARC-AGI-3-Agents/.env', 'w') as f:
                f.write(\"\"\"SCHEME=http
        HOST=gateway
        PORT=8001
        ARC_API_KEY=test-key-123
        ARC_BASE_URL=http://gateway:8001/
        OPERATION_MODE=online
        ENVIRONMENTS_DIR=
        RECORDINGS_DIR=/kaggle/working/server_recording
        \"\"\")

            # Run it. The gateway records every action and emits submission.parquet.
            !cd /kaggle/working/ARC-AGI-3-Agents && \\
                MPLBACKEND=agg \\
                python main.py --agent myagent
        """
    )
    run_cell = code_cell(run_cell_source)

    dummy_submission_cell = code_cell(
        dedent(
            """\
            import os
            if not os.getenv('KAGGLE_IS_COMPETITION_RERUN'):
                # Save-and-run-all (commit) mode: emit a dummy submission so the
                # commit succeeds. The real submission.parquet is produced by the
                # gateway during competition rerun.
                import pandas as pd
                submission = pd.DataFrame(
                    data=[['1_0', '1', True, 1]],
                    columns=['row_id', 'game_id', 'end_of_game', 'score'])
                submission.to_parquet('/kaggle/working/submission.parquet', index=False)
                submission.head()
            """
        )
    )

    if ACCELERATOR not in _ACCELERATORS:
        raise SystemExit(
            f"Unknown ACCELERATOR={ACCELERATOR!r}. Pick one of: "
            f"{sorted(_ACCELERATORS)}"
        )
    accel = _ACCELERATORS[ACCELERATOR]

    notebook = {
        "metadata": {
            "kernelspec": {
                "language": "python",
                "display_name": "Python 3",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "mimetype": "text/x-python",
                "file_extension": ".py",
                "pygments_lexer": "ipython3",
            },
            "kaggle": {
                "accelerator": accel["name"],
                "isInternetEnabled": False,
                "isGpuEnabled": accel["gpu"],
                "language": "python",
                "sourceType": "notebook",
            },
        },
        "nbformat_minor": 4,
        "nbformat": 4,
        "cells": [
            markdown_cell(
                "# ARC Prize 2026 — ARC-AGI-3 Submission\n\n"
                "Built from `agent/*.py` via `scripts/build_notebook.py` "
                f"({len(modules)} modules: "
                f"{', '.join(p.name for p in modules)}).\n\n"
                "Do not edit cells directly — edit the source files and "
                "re-run `make submit`."
            ),
            install_cell,
            mkdir_cell,
            *write_cells,
            run_cell,
            dummy_submission_cell,
        ],
    }
    return notebook


def main() -> None:
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTEBOOK_PATH.write_text(json.dumps(build(), indent=1))
    shipped = [p.name for p in agent_modules()]
    print(f"[build_notebook] Wrote {NOTEBOOK_PATH.relative_to(ROOT)}  "
          f"(accelerator: {ACCELERATOR})")
    print(f"[build_notebook] Shipped {len(shipped)} modules: "
          f"{', '.join(shipped)}")

    # Keep notebooks/kernel-metadata.json in sync so the user never has to
    # edit it just to flip CPU ↔ GPU.
    if METADATA_PATH.exists():
        meta = json.loads(METADATA_PATH.read_text())
        wanted = _ACCELERATORS[ACCELERATOR]["gpu"]
        if meta.get("enable_gpu") != wanted:
            meta["enable_gpu"] = wanted
            METADATA_PATH.write_text(json.dumps(meta, indent=2) + "\n")
            print(f"[build_notebook] Synced enable_gpu={wanted} in "
                  f"{METADATA_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
