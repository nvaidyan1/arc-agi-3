"""Unit tests for `agent/attention.py`'s click-target blend (H011).

Run with:  .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from attention import ClickTargeting, InterestMap  # noqa: E402


def grid_of(background: int, marks: dict) -> list[list[int]]:
    """An 8x8 grid of `background`, with `marks[(x, y)] = value` set."""
    g = [[background] * 8 for _ in range(8)]
    for (x, y), v in marks.items():
        g[y][x] = v
    return g


def test_an_untried_cell_beats_a_heavily_revisited_one_of_the_same_tier():
    """Two cells in the SAME tier (plain non-background, no interest, not
    recent): the untried one must have a strictly higher score, so a
    weighted draw favours it — the novelty term doing exactly its job."""
    c = ClickTargeting()
    grid = grid_of(0, {(2, 2): 5, (6, 6): 5})
    for _ in range(20):
        c.observe_click((6, 6), changed=[(6, 6)])   # heavily tried, has an effect (not spent)
    interest = InterestMap()
    hits = {(2, 2): 0, (6, 6): 0}
    for _ in range(200):
        x, y, _why = c.pick(grid, interest)
        hits[(x, y)] += 1
    assert hits[(2, 2)] > hits[(6, 6)]


def test_a_higher_tier_still_wins_when_novelty_is_equal():
    """Two equally-untried cells, one in the interest tier (0) and one
    only ever non-background (tier 3): with novelty tied, salience alone
    must make the interest cell the near-certain winner."""
    c = ClickTargeting()
    grid = grid_of(0, {(1, 1): 5, (6, 6): 5})
    interest = InterestMap()
    interest.bump([(1, 1)], weight=10.0)
    hits = {(1, 1): 0, (6, 6): 0}
    for _ in range(200):
        x, y, _why = c.pick(grid, interest)
        hits[(x, y)] += 1
    assert hits[(1, 1)] > hits[(6, 6)]


def test_habituation_still_excludes_a_spent_cell_regardless_of_novelty():
    """A cell clicked before with zero effect must never be picked, no
    matter how little tried it looks by count alone — the blend must not
    reopen the habituation gap H007's own history fixed."""
    c = ClickTargeting()
    grid = grid_of(0, {(3, 3): 5})
    c.observe_click((3, 3), changed=[])   # one try, zero effect -> spent
    interest = InterestMap()
    for _ in range(50):
        x, y, why = c.pick(grid, interest)
        assert (x, y) != (3, 3), why


def test_a_cell_that_has_an_effect_is_never_spent_however_often_tried():
    c = ClickTargeting()
    grid = grid_of(0, {(3, 3): 5})
    for _ in range(100):
        c.observe_click((3, 3), changed=[(3, 3)])
    assert not c._is_spent((3, 3))


def test_pick_returns_a_visible_candidate_when_any_exist():
    c = ClickTargeting()
    grid = grid_of(0, {(4, 4): 7})
    interest = InterestMap()
    x, y, why = c.pick(grid, interest)
    assert (x, y) == (4, 4)
    assert "novelty-weighted" in why


def test_pick_falls_back_when_the_frame_is_entirely_background():
    c = ClickTargeting()
    grid = grid_of(0, {})
    interest = InterestMap()
    x, y, why = c.pick(grid, interest)
    assert 0 <= x <= 63 and 0 <= y <= 63
    assert why == "random fallback"


def test_pick_reports_no_frame_yet_on_an_empty_grid():
    c = ClickTargeting()
    interest = InterestMap()
    x, y, why = c.pick([], interest)
    assert why == "no frame yet"


def test_remote_acting_locality_skips_the_recently_active_plus_nonbg_tier():
    """`acts_locally is False` drops the "recent AND non-background" tier
    entirely (aiming at the effect, not the cause, is a category error) —
    the blend must preserve that exclusion, not just the ranking."""
    c = ClickTargeting()
    c._local, c._remote = 0, 5   # acts_locally -> False
    assert c.acts_locally is False
    grid = grid_of(0, {(2, 2): 5})
    c._recent.append([(2, 2)])   # recently changed AND non-background
    interest = InterestMap()
    # Under acts_locally is False the tiers are [interest, non-bg-at-a-
    # distance, recent] -- (2,2) is reachable via tier 1 or 2 either way,
    # so this only proves the branch runs without error and still finds
    # the cell; the exclusion itself is structural (ranked never contains
    # the combined tier), asserted by inspecting `why`.
    _, _, why = c.pick(grid, interest)
    assert "recently active + non-background" not in why
