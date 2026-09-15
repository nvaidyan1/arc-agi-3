"""H005 Stage 3: replay a hand-built two-condition cd82 oracle.

`H001`'s Stage-2 oracle (`docs/history.md` 2026-09-15, "Stage 2 of the
replay-ablation") hand-authored a ONE-condition hypothesis -- adjacent to
the template, side -x -- from the project's strongest existing finding,
and it failed on 2 of 3 recorded seeds because the schema had nowhere to
put cd82's real second factor ("which swatch is selected"). `H005` Stage
1 (`research/hypotheses/H005_compositional_preconditions.md`) built the
plumbing to carry a SECOND, conjunctive condition. This script is the
first live exercise of it: it does not attempt to encode "swatch is
selected" correctly (that is a persistent state fact; Stage 1 only
built adjacency-shaped conditions -- see the doc's Scope section, which
predicted this exact gap). It tests something narrower and answerable
now: **does the agent correctly route to and test a hypothesis with two
conditions on two different real entities**, end to end, in a live game?

No LLM involved -- the oracle is a hand-built `Hypothesis`, injected
directly into `agent.hypothesis` after enough steps that its target
entities are live, bypassing the parser entirely (the LLM schema was
deliberately not extended to emit multiple conditions this stage).

Entity ids are hardcoded per-seed rather than discovered generically,
because they were read from an actual run (the same way H001's Stage 2
did) and confirmed identical across seeds 1-3 at this early a step
(`/tmp/h005_probe*.py`, not committed -- scratch): `{0,1,5,6}` the
template, `{2,3,4}` the strip (with `#3` one swatch), `{8,9}` the bucket
(CONTROL, moved by ACTION3/4, painted by ACTION5). If a different seed
mints these differently the injection will raise (ids not live), rather
than silently testing the wrong entities.

Usage:
    .venv/bin/python scripts/h005_cd82_oracle.py --seed 1
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

os.environ["ARC_PROPOSER"] = "1"   # no LLM needed -- the oracle is injected directly

VENDOR = ROOT / "vendor" / "ARC-AGI-3-Agents"
sys.path.insert(0, str(VENDOR))

import arc_agi  # noqa: E402
from arc_agi import OperationMode  # noqa: E402

import hypothesis as _hypothesis  # noqa: E402
from play_local import load_my_agent_class  # noqa: E402

TEMPLATE_MEMBER = 0     # one entity of the {0,1,5,6} template group, side -x (H001)
SWATCH_MEMBER = 3       # one entity of the {2,3,4} strip group (H005's proxy for "selected")
KEY = ("part_size_diff", (0, 1, 5, 6), (8, 9))   # real group key: template vs bucket/block
ACTION = "ACTION5"       # cd82's paint action, per H001/H002
INJECT_AFTER_CALLS = 20  # brief is already rich by level_step ~21 in a real recorded run


def inject_oracle(agent) -> _hypothesis.Hypothesis:
    live = agent.regions.live
    missing = [m for m in (TEMPLATE_MEMBER, SWATCH_MEMBER, 8, 9) if m not in live]
    if missing:
        raise SystemExit(f"Entities {missing} not live at injection time -- this seed "
                          f"minted different ids; re-probe before reusing this script.")
    rec = agent.relations.record(KEY)
    if rec is None:
        raise SystemExit(f"{KEY} has no record at injection time.")
    h = _hypothesis.Hypothesis(
        key=KEY, action=ACTION, lift=0.0, start=rec.residual,
        precondition=(("adjacent:-x", TEMPLATE_MEMBER), ("adjacent", SWATCH_MEMBER)),
        source="oracle_h005", confidence=1.0, predicted="down",
        falsifier=f"part_size_diff{KEY[1:]} does not fall after budget presses of "
                  f"{ACTION} with the controlled thing adjacent to #{TEMPLATE_MEMBER} "
                  f"on side -x AND adjacent to #{SWATCH_MEMBER}",
    )
    agent.hypothesis = h
    print(f"[inject] {h.describe()}")
    return h


def run(seed: int, max_steps: int = 200):
    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
    Cls = load_my_agent_class()
    Cls.MAX_ACTIONS = max_steps
    Cls.SEED = seed
    env = arc.make("cd82")
    agent = Cls(card_id="h005-oracle", game_id="cd82", agent_name="h005.cd82",
                ROOT_URL="http://localhost", record=False, arc_env=env, tags=["h005-oracle"])

    state = {"calls": 0, "injected": None}
    real_choose = agent.choose_action

    def wrapped(frames, latest_frame):
        state["calls"] += 1
        if state["injected"] is None and state["calls"] > INJECT_AFTER_CALLS:
            state["injected"] = inject_oracle(agent)
        return real_choose(frames, latest_frame)

    agent.choose_action = wrapped
    agent.main()

    h = state["injected"]
    final = agent.frames[-1]
    sc = arc.get_scorecard()
    score = float(sc.score if hasattr(sc, "score") else sc)
    print(f"\nseed={seed}  levels_completed={final.levels_completed}  "
          f"actions={agent.action_counter}  score={score:.4f}")
    if h is None:
        print("oracle never injected -- episode ended before step "
              f"{INJECT_AFTER_CALLS} (max_steps too low?).")
        return
    print(f"oracle status={h.status}  spent={h.spent}/{h.budget}  unmet={h.unmet}  "
          f"history={h.history}")
    # Every entry in the log is (key, action, start, end, status, spent, unmet,
    # precondition, exclusive, source) -- confirm the oracle's own entry carries
    # its two-condition precondition intact through close()/logging (P1).
    matches = [entry for entry in agent.proposer.log if entry[9] == "oracle_h005"]
    if matches:
        print(f"logged entry: {matches[-1]}")
    else:
        print("oracle was never closed (still live at episode end, or evicted).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--max-steps", type=int, default=200)
    args = ap.parse_args()
    run(args.seed, args.max_steps)
