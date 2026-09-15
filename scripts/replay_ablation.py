"""Replay a recorded run's exact LLM output, offline — no model, no Ollama.

The second review (`docs/expert-reviews/reviewer_c_09_14_2026b.md`, §14)
proposed an ablation ladder to separate LLM *generation* quality from
LLM *integration* quality: replay the exact hypotheses a run actually
generated against a deterministic agent, rather than calling the model
again. `agent/proposer_llm.py`'s `LLMProposer.trace` (added for exactly
this) now saves every call's raw reply in every sweep summary
(`observed[game]["llm_trace"]`); `ScriptedClient` (built for tests, long
before this) already replays a list of canned replies in order. This
script is the small piece of plumbing joining the two.

Two things this proves, in order:

  1. **Reproducibility.** With the exact recorded replies fed back in and
     no model call ever made, does the run reach the same outcome
     (levels_completed, actions, final state) as the original? If yes,
     the pipeline downstream of the model call is genuinely deterministic
     once the model's output is fixed — an assumption `recap.py`'s
     rerun-vs-replay docstring only asserted, never tested. If no,
     something downstream has hidden nondeterminism worth finding.
  2. **The counterfactual power this then buys**, not built here but
     enabled by it: once (1) passes, feed a *different* list of replies
     (only the ones that turned out `held`, a hand-authored oracle, a
     reordering) through the same harness to see what a run would have
     done under different hypothesis quality — fast, free of Ollama,
     deterministic. That is the actual generation-vs-integration
     separation; this script is the harness it needs.

`replay()`'s `drop_sources` param is one instance of (2): the model's raw
replies stay byte-identical (nothing about generation changes), but any
hypothesis `parse_hypotheses` would tag with a source in `drop_sources`
(e.g. `llm_ungrounded`) is stripped before it ever reaches the pool. That
holds generation fixed and only varies integration — a cleaner isolation
than re-sweeping with the model called fresh, where a filtered call
changes the pool, which changes the trajectory, which changes what the
*next* live call even sees (third review,
`docs/expert-reviews/reviewer_c_09_14_2026c.md` §14, case D).

Usage:
    .venv/bin/python scripts/replay_ablation.py \\
        --from results/sweeps/20260914-225014-98208.json --game ar25

Exits non-zero (and says why) if the sweep summary has no LLM trace for
that game, or if the game reached zero LLM calls (nothing to replay).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# Must happen before ANY import below that could transitively pull in
# agent/constants.py (proposer_llm -> hypothesis -> constants does,
# immediately) — constants.py reads these env vars at its own *module*
# import time into plain booleans, never re-read per call, and Python
# caches the module in sys.modules on first import. Setting them inside
# `replay()` instead (tried first) was a silent no-op: this script's own
# `import proposer_llm` below had already imported and cached `constants`
# with USE_LLM_PROPOSER=False by the time `replay()` ran, and
# `load_my_agent_class()`'s later `import constants` inside my_agent.py
# just returned that same stale cached module.
os.environ["ARC_PROPOSER"] = "1"
os.environ["ARC_LLM_PROPOSER"] = "1"

VENDOR = ROOT / "vendor" / "ARC-AGI-3-Agents"
if not VENDOR.exists():
    raise SystemExit(f"Framework not found at {VENDOR}. Run `make setup` first.")
sys.path.insert(0, str(VENDOR))

import arc_agi  # noqa: E402
from arc_agi import OperationMode  # noqa: E402

sys.path.insert(0, str(ROOT / "agent"))
import proposer_llm  # noqa: E402

from play_local import load_my_agent_class  # noqa: E402


def load_recorded_replies(summary_path: Path, game: str) -> tuple[dict, list[str]]:
    """The sweep summary's `observed[game]` entry, and the ordered raw
    replies from its `llm_trace` — the only input this script needs from
    the original run."""
    summary = json.loads(summary_path.read_text())
    config = summary["config"]
    observed = summary.get("observed", {})
    if game not in observed:
        raise SystemExit(f"{summary_path} has no game {game!r}. "
                          f"Games in this summary: {sorted(observed)}")
    entry = observed[game]
    trace = entry.get("llm_trace")
    if not trace:
        raise SystemExit(f"{summary_path}[{game!r}] has no llm_trace — was this run "
                          f"with ARC_LLM_PROPOSER=1, and is it new enough to carry the trace?")
    replies = [call["raw_reply"] for call in trace if "raw_reply" in call]  # skip failed calls
    if not replies:
        raise SystemExit(f"{summary_path}[{game!r}]: every recorded LLM call failed "
                          f"(no successful reply to replay).")
    return {"seed": config["seed"], "max_steps": config["max_steps"],
            "original": entry, "n_calls": len(trace)}, replies


_ORIGINAL_PARSE_HYPOTHESES = proposer_llm.parse_hypotheses


def _filtered_parse_hypotheses(drop_sources: frozenset[str]):
    """Wrap the real parser to drop hypotheses tagged with a source in
    `drop_sources` *after* parsing — generation (the raw reply) is
    untouched; only what gets past parsing into the pool changes."""
    def _parse(text, engine, live, legal, control=frozenset()):
        hyps, rejects = _ORIGINAL_PARSE_HYPOTHESES(text, engine, live, legal, control)
        kept = [h for h in hyps if h.source not in drop_sources]
        return kept, rejects
    return _parse


def replay(game: str, seed: int, max_steps: int, replies: list[str],
           drop_sources: frozenset[str] = frozenset()):
    """Re-run `game` at `seed`, LLM proposer on, but with its client
    replaced by a `ScriptedClient` over the recorded replies — no network
    call is ever made. Returns `(agent, arc)` after `main()` finishes;
    `arc.get_scorecard()` gives this single game's score.

    `drop_sources`: hypothesis sources (e.g. `{"llm_ungrounded"}`) to
    strip after parsing, before they reach the pool — see the module
    docstring's case-D note. Every call sets the module-global parser
    explicitly (rather than restoring it after), since this script only
    ever runs one replay at a time in-process, but a caller doing several
    replays in one process should not assume state carries over silently.

    (Env vars are set at module import time, above — see the comment
    there for why setting them here would already be too late.)
    """
    proposer_llm.parse_hypotheses = (
        _filtered_parse_hypotheses(drop_sources) if drop_sources else _ORIGINAL_PARSE_HYPOTHESES)
    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL)
    Cls = load_my_agent_class()
    Cls.MAX_ACTIONS = max_steps
    Cls.SEED = seed
    env = arc.make(game)
    if env is None:
        raise SystemExit(f"Could not create env for {game!r}.")
    agent = Cls(card_id="replay-ablation", game_id=game, agent_name=f"replay.{game}",
                ROOT_URL="http://localhost", record=False, arc_env=env, tags=["replay-ablation"])
    if agent.llm is None:
        raise SystemExit("Agent built with ARC_LLM_PROPOSER unset — check constants.py picked "
                          "up the env var (it reads it at import time).")
    agent.llm.client = proposer_llm.ScriptedClient(replies)
    agent.main()
    return agent, arc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="summary_path", required=True, type=Path,
                    help="A sweep summary JSON with an ARC_LLM_PROPOSER=1 run for --game.")
    ap.add_argument("--game", required=True, help="Game id, e.g. cd82")
    args = ap.parse_args()

    meta, replies = load_recorded_replies(args.summary_path, args.game)
    print(f"Replaying {args.game} seed={meta['seed']} max_steps={meta['max_steps']}: "
          f"{len(replies)} recorded reply(ies) from {meta['n_calls']} original call(s).")

    agent, _arc = replay(args.game, meta["seed"], meta["max_steps"], replies)

    final = agent.frames[-1]
    orig = meta["original"]
    replayed = {"levels_completed": final.levels_completed, "actions": agent.action_counter,
               "final_state": str(final.state)}
    original = {"levels_completed": orig["levels_completed"], "actions": orig["actions"],
               "final_state": orig["state"]}
    match = replayed == original
    calls_made = agent.llm.stats["calls"]
    replies_exhausted = calls_made > len(replies)

    print(f"\noriginal:  {original}")
    print(f"replayed:  {replayed}")
    print(f"calls made this replay: {calls_made} (had {len(replies)} recorded reply/ies)"
          + ("  ** MORE CALLS THAN RECORDED — replies were reused/repeated, trajectory "
             "diverged before this point **" if replies_exhausted else ""))
    print(f"\n{'MATCH — the pipeline is deterministic given the same model output' if match and not replies_exhausted else 'MISMATCH — see docstring §1 for what this means'}")

    if not match or replies_exhausted:
        sys.exit(1)


if __name__ == "__main__":
    main()
