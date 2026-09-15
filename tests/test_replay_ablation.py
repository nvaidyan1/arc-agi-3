"""The replay-ablation harness's extraction logic (agent behaviour side is
covered by manual smoke checks against real sweep summaries -- see the
script's own docstring; this file is fast and needs no game engine).

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402
from replay_ablation import load_recorded_replies  # noqa: E402


def write_summary(tmp_path, observed):
    path = tmp_path / "summary.json"
    path.write_text(json.dumps({
        "config": {"seed": 42, "max_steps": 200, "games_requested": list(observed)},
        "observed": observed,
    }))
    return path


def entry(**over):
    base = {"state": "GameState.NOT_FINISHED", "levels_completed": 1, "actions": 150,
            "llm_trace": [{"raw_reply": "{}", "model": "gemma3:4b"},
                          {"raw_reply": "{\"hypotheses\": []}", "model": "gemma3:4b"}]}
    base.update(over)
    return base


def test_extracts_the_ordered_raw_replies_and_the_run_metadata(tmp_path):
    path = write_summary(tmp_path, {"cd82": entry()})
    meta, replies = load_recorded_replies(path, "cd82")
    assert replies == ["{}", "{\"hypotheses\": []}"]
    assert meta["seed"] == 42 and meta["max_steps"] == 200 and meta["n_calls"] == 2
    assert meta["original"]["levels_completed"] == 1


def test_a_failed_call_in_the_trace_is_skipped_not_replayed(tmp_path):
    # A failed call's trace entry has no "raw_reply" (agent/proposer_llm.py
    # never sets it on the error path) -- replaying "" would be a lie
    # about what was actually said.
    path = write_summary(tmp_path, {"cd82": entry(llm_trace=[{"raw_reply": "{}"}, {"error": "timed out"}])})
    _meta, replies = load_recorded_replies(path, "cd82")
    assert replies == ["{}"]


def test_missing_game_raises_with_the_available_games_named(tmp_path):
    path = write_summary(tmp_path, {"cd82": entry()})
    with pytest.raises(SystemExit, match=r"cd82"):
        load_recorded_replies(path, "sp80")


def test_no_trace_at_all_raises(tmp_path):
    path = write_summary(tmp_path, {"cd82": entry(llm_trace=None)})
    with pytest.raises(SystemExit, match="llm_trace"):
        load_recorded_replies(path, "cd82")


def test_every_call_failed_raises(tmp_path):
    path = write_summary(tmp_path, {"cd82": entry(llm_trace=[{"error": "timed out"}])})
    with pytest.raises(SystemExit, match="failed"):
        load_recorded_replies(path, "cd82")
