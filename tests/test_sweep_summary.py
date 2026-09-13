"""Unit tests for `scripts/sweep_summary.py`.

The summary is the durable record of a sweep — if it is wrong, or if it can
throw and take a 25-game run down with it, the measurement problem it exists
to solve gets worse rather than better. So the tests assert two things:

  1. Completions are counted at the right action index, including the awkward
     cases (a level-up on the final action, two levels in one step).
  2. **The tolerance cases**: a scorecard missing optional fields, or absent
     entirely, still produces a summary. The scorer drops None fields and
     declines to score at all when human baselines are unavailable (which is
     the situation on hidden games), so "degrade, don't raise" is the
     behaviour worth pinning down.

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sweep_summary  # noqa: E402


# --------------------------------------------------------------------------
# completion_indices
# --------------------------------------------------------------------------

def test_completion_index_is_the_action_at_which_the_level_up_appeared():
    # levels_completed sampled before each action; it becomes 1 at index 3.
    assert sweep_summary.completion_indices([0, 0, 0, 1, 1, 1]) == [3]


def test_no_completions_reports_empty_not_zero():
    # The distinction matters: [] means "never completed", [0] would mean
    # "completed on the very first action".
    assert sweep_summary.completion_indices([0, 0, 0]) == []


def test_multiple_completions_are_each_reported():
    assert sweep_summary.completion_indices([0, 1, 1, 2, 3]) == [1, 3, 4]


def test_two_levels_in_one_step_are_not_silently_lost():
    # A jump of 2 is expanded rather than counted once — losing a completion
    # would understate the only outcome that scores.
    assert sweep_summary.completion_indices([0, 0, 2]) == [2, 2]


def test_a_run_that_starts_mid_game_does_not_invent_a_completion():
    # First sample is the baseline, never a level-up, even if it is non-zero.
    assert sweep_summary.completion_indices([3, 3, 4]) == [2]


def test_empty_and_single_sample_are_safe():
    assert sweep_summary.completion_indices([]) == []
    assert sweep_summary.completion_indices([0]) == []


# --------------------------------------------------------------------------
# environment_rows — tolerance of the third-party scorecard
# --------------------------------------------------------------------------

class _Run:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _Env:
    def __init__(self, runs=None, **kw):
        if runs is not None:
            self.runs = runs
        for k, v in kw.items():
            setattr(self, k, v)


class _Card:
    def __init__(self, environments):
        self.environments = environments


def test_rows_are_extracted_from_nested_runs():
    card = _Card([_Env(id="ls20", runs=[_Run(id="ls20", score=1.5,
                                             levels_completed=1, actions=400)])])
    (row,) = sweep_summary.environment_rows(card)
    assert row["game_id"] == "ls20"
    assert row["score"] == 1.5
    assert row["levels_completed"] == 1


def test_missing_optional_fields_become_none_rather_than_raising():
    # The scorecard serialises with exclude_none=True, so absent attributes
    # are normal, not exceptional.
    card = _Card([_Env(id="vc33", runs=[_Run(id="vc33", score=0.0)])])
    (row,) = sweep_summary.environment_rows(card)
    assert row["level_actions"] is None
    assert row["state"] is None


def test_environment_without_runs_is_read_directly():
    card = _Card([_Env(id="sp80", score=2.0, levels_completed=1)])
    (row,) = sweep_summary.environment_rows(card)
    assert row["game_id"] == "sp80"
    assert row["score"] == 2.0


def test_a_scorecard_with_no_environments_yields_no_rows():
    assert sweep_summary.environment_rows(_Card([])) == []
    assert sweep_summary.environment_rows(_Card(None)) == []


# --------------------------------------------------------------------------
# build_summary / write_summary
# --------------------------------------------------------------------------

def _observed():
    return {
        "ls20": {"state": "GAME_OVER", "levels_completed": 0, "actions": 400,
                 "completion_action_indices": []},
        "sp80": {"state": "WIN", "levels_completed": 1, "actions": 400,
                 "completion_action_indices": [185]},
    }


def test_summary_without_a_scorecard_still_records_what_was_observed():
    # The fallback path taken when the scorer cannot be summarised. The
    # observed half is the part that must survive.
    summary = sweep_summary.build_summary(
        run_id="20260913-000000", max_steps=400,
        games=["ls20", "sp80"], observed=_observed(), scorecard=None,
    )
    assert summary["scored"] == []
    assert summary["observed"]["sp80"]["completion_action_indices"] == [185]


def test_summary_carries_the_configuration_fingerprint():
    # Without this a score cannot be attributed to the code that produced it,
    # which is the whole failure being corrected.
    summary = sweep_summary.build_summary(
        run_id="r", max_steps=400, games=["ls20"], observed=_observed(),
        fingerprint={"sha": "abc123", "dirty": False, "subject": "x"},
    )
    assert summary["config"]["git"]["sha"] == "abc123"
    assert summary["config"]["max_steps"] == 400


def test_summary_round_trips_through_json(tmp_path):
    summary = sweep_summary.build_summary(
        run_id="20260913-000000", max_steps=400, games=["ls20"],
        observed=_observed(), aggregate_score=0.063,
    )
    path = sweep_summary.write_summary(summary, tmp_path / "sweeps")
    reloaded = json.loads(path.read_text())
    assert reloaded["aggregate_score"] == 0.063
    assert reloaded["schema_version"] == sweep_summary.SCHEMA_VERSION


def test_git_fingerprint_never_raises_outside_a_repo(tmp_path):
    # It runs at the end of a completed sweep; it must not be able to fail one.
    fingerprint = sweep_summary.git_fingerprint(tmp_path)
    assert set(fingerprint) == {"sha", "dirty", "subject"}
