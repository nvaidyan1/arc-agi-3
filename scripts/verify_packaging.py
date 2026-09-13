"""Prove the submission's module layout imports, before spending a submission.

This exists because of one asymmetry: the agent only ever runs under
`KAGGLE_IS_COMPETITION_RERUN`, so a packaging mistake — a missing module,
a bad import, a name that resolves locally but not inside the framework
package — passes every local test AND the Kaggle commit, and fails only
during the rerun. That costs one of five daily submissions to discover,
and tells you almost nothing about what broke.

So this reproduces the rerun's layout exactly and imports through it:

  1. Extract every `%%writefile` cell from the built notebook — the real
     shipped bytes, not the files on disk, so a stale notebook is caught.
  2. Copy the vendored framework into a temp dir.
  3. Drop the modules into `agents/templates/`, exactly as the notebook's
     `cp` does.
  4. Rewrite `agents/__init__.py` the way the notebook does.
  5. Import `agents` from a clean interpreter and instantiate MyAgent.

Step 5 runs as a subprocess with a fresh `sys.path` on purpose: importing
in-process would let modules already loaded by the test runner mask a
missing one.

Usage:  make verify-packaging
        .venv/bin/python scripts/verify_packaging.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "submission.ipynb"
VENDOR = ROOT / "vendor" / "ARC-AGI-3-Agents"

# Mirrors the notebook's rewritten agents/__init__.py. Kept in sync by
# eye; if the notebook's version changes, change this too — a mismatch
# here would make this check pass while the real thing fails.
INIT_BODY = """from typing import Type
from .agent import Agent, Playback
from .templates.my_agent import MyAgent

AVAILABLE_AGENTS: dict[str, Type[Agent]] = {
    'myagent': MyAgent,
}
"""

PROBE = """
import sys
sys.path.insert(0, {framework!r})
from agents import AVAILABLE_AGENTS
cls = AVAILABLE_AGENTS['myagent']
assert cls.__name__ == 'MyAgent', cls
# Touch the attributes the framework relies on, so a broken class body
# fails here rather than mid-game.
assert isinstance(cls.MAX_ACTIONS, int)
assert callable(cls.choose_action) and callable(cls.is_done)
print('OK', cls.__module__, 'MAX_ACTIONS=%d' % cls.MAX_ACTIONS)
"""


def writefile_cells(notebook: dict) -> dict[str, str]:
    """Filename -> body, for every `%%writefile` cell in the notebook."""
    out: dict[str, str] = {}
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell["source"]
        if isinstance(source, list):
            source = "".join(source)
        if not source.startswith("%%writefile "):
            continue
        first, _, body = source.partition("\n")
        out[Path(first[len("%%writefile "):].strip()).name] = body
    return out


def main() -> None:
    if not NOTEBOOK.exists():
        raise SystemExit(
            f"No notebook at {NOTEBOOK}. Run `make submit` or "
            f"`python scripts/build_notebook.py` first."
        )
    if not VENDOR.exists():
        raise SystemExit(f"Framework not found at {VENDOR}. Run `make setup`.")

    modules = writefile_cells(json.loads(NOTEBOOK.read_text()))
    if "my_agent.py" not in modules:
        raise SystemExit(
            "The notebook ships no my_agent.py — the build is broken."
        )

    on_disk = {p.name for p in (ROOT / "agent").glob("*.py")}
    missing = on_disk - set(modules)
    if missing:
        raise SystemExit(
            f"Notebook is stale: {sorted(missing)} exist in agent/ but are "
            f"not shipped. Re-run scripts/build_notebook.py."
        )

    with tempfile.TemporaryDirectory() as tmp:
        framework = Path(tmp) / "ARC-AGI-3-Agents"
        shutil.copytree(VENDOR, framework, ignore=shutil.ignore_patterns("__pycache__"))

        templates = framework / "agents" / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        for name, body in modules.items():
            (templates / name).write_text(body)

        (framework / "agents" / "__init__.py").write_text(INIT_BODY)

        result = subprocess.run(
            [sys.executable, "-c", PROBE.format(framework=str(framework))],
            capture_output=True, text=True, cwd=tmp,
        )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(
            "PACKAGING BROKEN — the submission would fail during the Kaggle "
            "rerun, after spending one of 5 daily submissions. Fix before "
            "submitting."
        )

    print(f"[verify-packaging] shipped {len(modules)} modules: "
          f"{', '.join(sorted(modules))}")
    print(f"[verify-packaging] {result.stdout.strip()}")
    print("[verify-packaging] the Kaggle layout imports and MyAgent loads.")


if __name__ == "__main__":
    main()
