"""H007 Day 4: the cd82 oracle with a STATE condition, live.

`H005` Stage 3 (`scripts/h005_cd82_oracle.py`) carried a two-condition
hypothesis through a live cd82 game and found the second condition —
adjacency to a swatch — almost never jointly satisfiable with the first,
because "adjacent to the swatch" is the wrong proxy for "the swatch is
selected". `H007` adds the condition kind that can say it: `state:<token>`
on an entity, met when that entity currently looks like the token, and
satisfied when unmet by *acting* (the action that put it into that state
before, from `MyAgent._setters`) rather than by walking.

What the traces show about cd82 (`recordings/latent/seed8/cd82.jsonl`,
the one recorded click on the swatch strip): clicking a swatch moves a
5-cell marker within the strip entity (its id persists, its shape
changes) and recolours the bucket's fill (which the tracker files as a
new entity, since it matches by colour). So the visible, persistent
state of "which colour is selected" is the STRIP's state token.

The experiment, per seed:

  1. play normally to step 20 (entities confirmed live, ids identical
     across seeds 1–3 at this step — same method as H001/H005);
  2. record the strip's token K0 (marker at the initially selected
     swatch); force three clicks — the other swatch, the original, the
     other again — so the agent's own `_setters` learns both transitions
     from its own observations (nothing is injected into that memory),
     and the strip ends in K1 ≠ K0;
  3. inject the hypothesis: H001's first condition (adjacent, side −x —
     on the BLOCK, see `ADJ_MEMBER`) AND `state:K0` on the strip. The state
     condition is unmet at injection by construction, so the first thing
     the agent must do is act to restore K0 — the mechanism under test;
  4. read: jointly-met steps out of the budget (H007 P1: >= 3 of 8,
     against 0–1 of 8 for H005 Stage 3's adjacency pair), whether the
     acting route fired, and what the residual did.

Usage:
    .venv/bin/python scripts/h007_cd82_oracle.py --seed 1
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "agent"))

os.environ["ARC_PROPOSER"] = "1"

VENDOR = ROOT / "vendor" / "ARC-AGI-3-Agents"
sys.path.insert(0, str(VENDOR))

import arc_agi  # noqa: E402
from arc_agi import OperationMode  # noqa: E402
from arcengine import GameAction  # noqa: E402

import hypothesis as _hypothesis  # noqa: E402
import relations as _relations  # noqa: E402
from play_local import load_my_agent_class  # noqa: E402

TEMPLATE_MEMBER = 0      # one entity of the {0,1,5,6} template group
# H001's `adjacent:-x` lever was tallied relative to the pair's nearest
# NON-CONTROL member, which for (template, block) is the block the bucket
# orbits — not the template, which sits at the board's left edge where a
# -x side is off screen. H005 Stage 3 carried its first condition on the
# template (0-1 of 8 met); the same condition on the block is the one
# the tally actually described.
ADJ_MEMBER = 10          # the block (colour 0, 100 cells at level 0)
STRIP = 2                # the swatch strip: its marker is the selection state
SWATCH_A = (37, 4)       # centre of swatch #3 (fill colour 0)
SWATCH_B = (43, 4)       # centre of swatch #4 (fill colour 15, selected at start)
ACTION = "ACTION5"
import os as _os
# H010 Stage 2 retest (2026-09-16): overridable via env, since H009's own
# live-viability curve found the position graph barely covered this early
# (1 of 10 seeds usable by decision 25) -- a later injection is a fairer
# test of whether the wired router can use it once it has warmed up.
INJECT_AFTER_CALLS = int(_os.environ.get("H007_INJECT_AFTER", "20"))
FORCED_CLICKS = (SWATCH_A, SWATCH_B, SWATCH_A)   # K0 -> K1 -> K0 -> K1


def _block_key(agent):
    """The template-vs-block residual, whichever unit key holds it now."""
    for key, rec in list(agent.relations.group_records.items()) + list(agent.relations.records.items()):
        rel, a, b = key
        if rel != "part_size_diff":
            continue
        sides = [set(x) if isinstance(x, tuple) else {x} for x in (a, b)]
        if {0, 1, 5, 6} in sides and any(10 in s for s in sides) and rec.residual:
            return key, rec
    return None, None


def force_click(agent, xy):
    action = GameAction.ACTION6
    action.set_data({"x": xy[0], "y": xy[1]})
    action.reasoning = f"oracle: forced click at {xy}"
    agent._last_click = xy
    agent._last_action = action
    return action


def run(seed: int, max_steps: int = 200, verbose: bool = False):
    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
    Cls = load_my_agent_class()
    Cls.MAX_ACTIONS = max_steps
    Cls.SEED = seed
    env = arc.make("cd82")
    agent = Cls(card_id="h007-oracle", game_id="cd82", agent_name="h007.cd82",
                ROOT_URL="http://localhost", record=False, arc_env=env, tags=["h007-oracle"])

    st = {"calls": 0, "k0": None, "tokens": [], "h": None, "acted": 0, "met_steps": []}
    real_choose = agent.choose_action

    def strip_token():
        if STRIP in agent.regions.live and STRIP in agent.regions._tracked:
            return _relations.state_key(*agent.regions._tracked[STRIP])
        return None

    def wrapped(frames, latest_frame):
        action = real_choose(frames, latest_frame)
        st["calls"] += 1
        n = st["calls"]
        if n == INJECT_AFTER_CALLS:
            st["k0"] = strip_token()
            print(f"[step {n}] strip #{STRIP} token K0={st['k0']}")
        if INJECT_AFTER_CALLS < n <= INJECT_AFTER_CALLS + len(FORCED_CLICKS):
            st["tokens"].append(strip_token())
            return force_click(agent, FORCED_CLICKS[n - INJECT_AFTER_CALLS - 1])
        if n == INJECT_AFTER_CALLS + len(FORCED_CLICKS) + 1:
            st["tokens"].append(strip_token())
            print(f"[step {n}] strip tokens through the forced clicks: {st['tokens']}")
            print(f"[step {n}] agent's own setters for #{STRIP}: {agent._setters.get(STRIP)}")
            missing = [m for m in (ADJ_MEMBER, STRIP) if m not in agent.regions.live]
            if missing:
                raise SystemExit(f"entities {missing} not live at injection; re-probe ids for this seed.")
            key, rec = _block_key(agent)
            if key is None:
                raise SystemExit("no template-vs-block part_size_diff record at injection.")
            h = _hypothesis.Hypothesis(
                key=key, action=ACTION, lift=0.0, start=rec.residual,
                precondition=(("adjacent:-x", ADJ_MEMBER), (f"state:{st['k0']}", STRIP)),
                source="oracle_h007", confidence=1.0, predicted="down",
                falsifier=f"part_size_diff{key[1:]} does not fall after budget presses of {ACTION} "
                          f"with the controlled thing adjacent on side -x of #{ADJ_MEMBER} "
                          f"AND #{STRIP} in state {st['k0']}",
            )
            agent.hypothesis = h
            st["h"] = h
            print(f"[inject] {h.describe()}")
            # Re-decide this step under the injected bet: the choice already
            # made above was made without it.
            action = agent._hypothesis_action(agent._legal_actions(latest_frame)) or action
        h = st["h"]
        if h is not None and h.status == _hypothesis.LIVE:
            why = getattr(action, "reasoning", "")
            tier = agent._decision.get("tier")
            if verbose and n >= INJECT_AFTER_CALLS:
                pos = agent.moves.displacement
                print(f"[step {n}] tier={tier} action={action.name} pos={pos} why={str(why)[:70]}")
            if isinstance(why, str) and "acting to put" in why:
                st["acted"] += 1
            if isinstance(why, str) and why.startswith("hypothesis:"):
                st["met_steps"].append((n, action.name, agent._precondition_met(h)))
        return action

    agent.choose_action = wrapped
    agent.main()

    h = st["h"]
    final = agent.frames[-1]
    sc = arc.get_scorecard()
    score = float(sc.score if hasattr(sc, "score") else sc)
    print(f"\nseed={seed}  levels_completed={final.levels_completed}  actions={agent.action_counter}  score={score:.4f}")
    if h is None:
        print("oracle never injected -- episode ended before the injection step.")
        return
    jointly = sum(1 for m in h.mets if m)
    print(f"oracle status={h.status}  spent={h.spent}/{h.budget}  unmet={h.unmet}  "
          f"jointly met={jointly}  acting-route steps={st['acted']}  history={h.history}  outcomes={h.outcomes}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-steps", type=int, default=200)
    ap.add_argument("--verbose", action="store_true", help="print every step taken under the oracle")
    a = ap.parse_args()
    run(a.seed, a.max_steps, a.verbose)
