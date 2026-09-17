"""H013: can our state-selection machinery discover the variables that
disambiguate an unseen mechanic?

H006 left ~72 pixel-aliased contexts unresolved on su15 / sk48 / sc25 / g50t
-- the "mechanic remainder", where its history-derived family was refuted or
below null. It named two requirements: more repeats (at ~2 visits a splitter
can only be REFUTED, never confirmed), and a candidate family that references
the controlled thing's RELATION to the clicked or moved entity.

This does both, and asks the larger question rather than hunting one more
variable: **for each unresolved alias, which FAMILY of candidate splits, if
any, produces a repeatable split above the null?**

    A temporal             actions since reset, event history
    B spatial              absolute / relative position of the controlled thing
    C relational           controlled entity <-> clicked/moved entity
    D interaction history  which object has been touched / activated
    E configuration        arrangement, occupancy, cardinality
    F unexplained          nothing above null

A is `latent_splitter.py`'s existing family (Z1 and friends) and is reused
from it unchanged, so this is a strict extension, not a reimplementation.

Schema, verified against the traces before writing:
    record['state_t']['entities'] -> [{id, colour, size, bbox, desc, role, control}]
    record['state_t']['displacement'] -> [dx, dy]
    record['data'] -> {'x','y'} for ACTION6;  record['frame'] -> grid[y][x]

Usage:
    .venv/bin/python scripts/h013_family_splitter.py \
        --game su15,sk48,sc25,g50t --null-draws 5
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import latent_splitter as ls  # noqa: E402  (family A, and the scoring machinery)

FAMILY = {}          # candidate name -> family letter


def _ctrl(st):
    for e in st.get("entities", []) or []:
        if e.get("control"):
            return e
    return None


def _centre(bbox):
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def extra_candidates(steps: list[dict]) -> dict[str, list]:
    """Families B-E. Family A comes from latent_splitter.candidates_for."""
    n = len(steps)
    f: dict[str, list] = collections.defaultdict(lambda: [None] * n)
    touched: set = set()            # entity ids ever clicked-on
    activated: set = set()          # entity ids that ever changed after a click
    last_click_xy = None
    prev_desc: dict = {}
    since_change = 0                # steps since the frame last changed
    changer_hist: list = []         # actions that changed the frame, in order
    since_action: dict = {a: 99 for a in ls.ACTIONS}
    for i, s in enumerate(steps):
        st = s.get("state_t") or {}
        ents = st.get("entities", []) or []
        c = _ctrl(st)
        prev = steps[i - 1] if i else None
        if prev is not None and (prev["action"] == "RESET"
                                 or s["levels_completed"] != prev["levels_completed"]):
            touched, activated, last_click_xy = set(), set(), None

        # --- B: spatial -------------------------------------------------
        disp = st.get("displacement")
        f["B_disp"][i] = tuple(disp) if disp else None
        if c:
            cx, cy = _centre(c["bbox"])
            f["B_ctrl_cell"][i] = (int(cx) // 8, int(cy) // 8)     # coarse board cell
            f["B_ctrl_bbox"][i] = tuple(c["bbox"])
            f["B_ctrl_quadrant"][i] = (ls._sign(cx - 32), ls._sign(cy - 32))

        # --- C: relational (controlled <-> clicked / moved entity) -------
        if c and last_click_xy is not None:
            cx, cy = _centre(c["bbox"])
            f["C_ctrl_to_click_sign"][i] = (ls._sign(last_click_xy[0] - cx),
                                            ls._sign(last_click_xy[1] - cy))
            f["C_ctrl_to_click_dist"][i] = int(abs(last_click_xy[0] - cx)
                                               + abs(last_click_xy[1] - cy)) // 8
        if c:
            # nearest OTHER entity, and the direction to it
            others = [e for e in ents if e["id"] != c["id"]]
            if others:
                cx, cy = _centre(c["bbox"])
                near = min(others, key=lambda e: abs(_centre(e["bbox"])[0] - cx)
                           + abs(_centre(e["bbox"])[1] - cy))
                nx, ny = _centre(near["bbox"])
                f["C_nearest_id"][i] = near["id"]
                f["C_nearest_dir"][i] = (ls._sign(nx - cx), ls._sign(ny - cy))
                f["C_nearest_touching"][i] = (abs(nx - cx) + abs(ny - cy)) < 12

        # --- D: interaction history -------------------------------------
        f["D_touched_set"][i] = tuple(sorted(touched))
        f["D_activated_set"][i] = tuple(sorted(activated))
        f["D_n_touched"][i] = len(touched)

        # --- E: configuration -------------------------------------------
        f["E_n_entities"][i] = len(ents)
        f["E_colour_multiset"][i] = tuple(sorted(collections.Counter(
            e["colour"] for e in ents).items()))
        f["E_size_signature"][i] = tuple(sorted(e["size"] for e in ents))
        f["E_desc_multiset"][i] = tuple(sorted(e["desc"] for e in ents))

        # --- G: ORDERED / SEQUENCE (added 2026-09-17 for the g50t remainder) --
        # The reviewer's list, made explicit, BEFORE any appeal to an LMU: if a
        # plain n-gram or time-since variable separates the residual aliases,
        # generic temporal compression is not needed.
        acts = [steps[j]["action"] for j in range(max(0, i - 3), i)]
        f["G_ngram2"][i] = tuple(acts[-1:]) if acts else None
        f["G_ngram3"][i] = tuple(acts[-2:]) if len(acts) >= 2 else None
        f["G_ngram4"][i] = tuple(acts[-3:]) if len(acts) >= 3 else None
        f["G_since_change"][i] = since_change
        f["G_last2_changers"][i] = tuple(changer_hist[-2:]) if changer_hist else None
        for act, k in since_action.items():
            f[f"G_since_{act[-1]}"][i] = min(k, 12)      # capped: far is far

        # fold this step forward
        if s["action"] == "ACTION6" and s.get("data"):
            last_click_xy = (s["data"]["x"], s["data"]["y"])
            for e in ents:
                x0, y0, x1, y1 = e["bbox"]
                if x0 <= last_click_xy[0] <= x1 and y0 <= last_click_xy[1] <= y1:
                    touched.add(e["id"])
        for e in ents:
            if e["id"] in prev_desc and prev_desc[e["id"]] != e["desc"] and e["id"] in touched:
                activated.add(e["id"])
        changed_now = bool(prev_desc) and any(
            e["id"] in prev_desc and prev_desc[e["id"]] != e["desc"] for e in ents)
        since_change = 0 if changed_now else since_change + 1
        if changed_now and prev is not None:
            changer_hist.append(prev["action"])
        for act in since_action:
            since_action[act] = 0 if s["action"] == act else since_action[act] + 1
        prev_desc = {e["id"]: e["desc"] for e in ents}

    for k in f:
        FAMILY[k] = k[0]
    return dict(f)



def _diff_cells(a: str, b: str) -> list:
    """Cells differing between two 64-row frame hashes' source grids."""
    return [(x, y) for y, (ra, rb) in enumerate(zip(a, b))
            for x, (ca, cb) in enumerate(zip(ra, rb)) if ca != cb]


def is_meter_context(frames: list) -> bool:
    """H006's classification: a context is METER when the difference between
    its outcomes lies entirely on ONE row or ONE column -- the quantised
    resource line (cd82 row 63, sk48 row 53, sc25 cols 62-63, g50t row 63).
    Anything else is MECHANIC. H006 found 568 of 640 aliased contexts (89%)
    were meters and goal-irrelevant; the ~72 mechanic ones are H013's actual
    target, so without this filter the temporal family simply re-finds the
    meters H006 already explained.
    """
    for i in range(len(frames)):
        for j in range(i + 1, len(frames)):
            d = _diff_cells(frames[i], frames[j])
            if not d:
                continue
            # <=2 rows or <=2 columns: H006 documented sc25's meter as
            # spanning columns 62-63, so a strict one-line test misses it
            # and wrongly calls every sc25 context mechanic.
            if len({y for _, y in d}) > 2 and len({x for x, _ in d}) > 2:
                return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="su15,sk48,sc25,g50t")
    ap.add_argument("--dirs", default="recordings/latent/seed*/")
    ap.add_argument("--null-draws", type=int, default=5)
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--max-traces", type=int, default=0,
                    help="use only the first N traces -- for the evidence curve: "
                         "at how many repeats does a candidate separate from null?")
    ap.add_argument("--candidate", default=None,
                    help="score only this candidate (evidence-curve mode)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--conjunctions", type=int, default=0,
                    help="also score PAIRS of the top-N single candidates. A "
                         "conjunction is cheaper than a new representation and "
                         "must be ruled out before appealing to one.")
    ap.add_argument("--mechanic-only", action="store_true",
                    help="keep only contexts whose outcomes differ OFF a single "
                         "meter row/column -- H006's mechanic remainder, H013's "
                         "actual target")
    a = ap.parse_args()
    rng = random.Random(0)

    print("families: A temporal (latent_splitter's own) | B spatial | "
          "C relational | D interaction-history | E configuration | F unexplained\n")
    verdicts = {}
    for game in a.game.split(","):
        files = sorted(glob.glob(os.path.join(a.dirs, f"{game}.jsonl")),
                       key=lambda f: int("".join(c for c in os.path.basename(
                           os.path.dirname(f)) if c.isdigit()) or 0))
        if a.max_traces:
            files = files[:a.max_traces]
        if not files:
            print(f"{game}: no traces"); continue

        outcome: dict = {}
        values: dict[str, dict] = collections.defaultdict(dict)
        pix = collections.defaultdict(list)
        grids: dict = {}
        total_steps = 0
        for fp in files:
            steps = ls._load(Path(fp))
            total_steps += len(steps)
            H = [ls._hash(s["frame"]) if s.get("frame") else None for s in steps]
            A = [ls._action_key(s) for s in steps]
            feats = ls.candidates_for(steps)           # family A
            for k in feats:
                FAMILY.setdefault(k, "A")
            feats.update(extra_candidates(steps))       # families B-E
            for i in range(len(steps) - 1):
                if steps[i + 1]["step"] != steps[i]["step"] + 1 or not H[i] or not H[i + 1]:
                    continue
                v = (str(fp), i)
                pix[(H[i], A[i])].append(v)
                outcome[v] = H[i + 1]
                grids.setdefault(H[i + 1], steps[i + 1]["frame"])
                for name, col in feats.items():
                    values[name][v] = col[i]

        # Candidate keys differ between files (a trace where no click ever
        # lands produces no relational candidate at all), so `values[name]`
        # is sparse across files. Fill the union with None before scoring --
        # a missing value is "not applicable here", a legitimate group.
        all_visits = [v for vs in pix.values() for v in vs]
        for name in values:
            for v in all_visits:
                values[name].setdefault(v, None)

        aliased = [vs for vs in pix.values()
                   if len(vs) >= 2 and len({outcome[v] for v in vs}) >= 2]
        if a.mechanic_only:
            contexts = [vs for vs in aliased
                        if not is_meter_context([grids[outcome[v]] for v in vs])]
        else:
            contexts = aliased
        repeated = sum(1 for vs in pix.values() if len(vs) >= 2)
        if not a.quiet:
            print(f"=== {game}: {len(files)} traces, {total_steps} steps, "
                  f"{repeated} repeated, {len(aliased)} aliased"
                  f"{f', {len(contexts)} MECHANIC' if a.mechanic_only else ''} ===")
        if not contexts:
            print("  (nothing aliased)\n"); continue

        visits_all = [v for vs in contexts for v in vs]
        rows = []
        for name, vals in values.items():
            if a.candidate and name != a.candidate:
                continue
            c = ls.score(contexts, outcome, vals)
            nulls = []
            for _ in range(a.null_draws):
                pool = [vals[v] for v in visits_all]
                rng.shuffle(pool)
                shuffled = dict(vals); shuffled.update(zip(visits_all, pool))
                nulls.append(ls.score(contexts, outcome, shuffled)["resolved"])
            null = sum(nulls) / len(nulls)
            rows.append((c["resolved"] - null, c["resolved"], c["singleton"],
                         c["still"], null, name, FAMILY.get(name, "?")))
        rows.sort(reverse=True)

        if not a.quiet:
            print(f"  {'fam':>3} {'candidate':24} {'resolved':>8} {'singleton':>9} "
                  f"{'still':>6} {'null':>6} {'lift':>6}")
            for lift, res, sing, still, null, name, fam in rows[:a.top]:
                print(f"  {fam:>3} {name:24} {res:8} {sing:9} {still:6} {null:6.1f} {lift:+6.1f}")

        if not rows:
            continue
        # --- conjunctions: pairs of the top-N singles -------------------
        if a.conjunctions:
            import itertools
            top_names = [r[5] for r in rows[:a.conjunctions]]
            pair_rows = []
            for n1, n2 in itertools.combinations(top_names, 2):
                v1, v2 = values[n1], values[n2]
                joint = {v: (v1.get(v), v2.get(v)) for v in all_visits}
                c = ls.score(contexts, outcome, joint)
                nulls = []
                for _ in range(a.null_draws):
                    pool = [joint[v] for v in visits_all]
                    rng.shuffle(pool)
                    sh = dict(joint); sh.update(zip(visits_all, pool))
                    nulls.append(ls.score(contexts, outcome, sh)["resolved"])
                nl = sum(nulls) / len(nulls)
                pair_rows.append((c["resolved"] - nl, c["resolved"], c["singleton"],
                                  c["still"], nl, f"{n1} AND {n2}", "x"))
            pair_rows.sort(reverse=True)
            if not a.quiet and pair_rows:
                print(f"  --- conjunctions (top {a.conjunctions} singles, "
                      f"{len(pair_rows)} pairs) ---")
                print(f"  {'':3} {'pair':44} {'resolved':>8} {'still':>6} "
                      f"{'null':>6} {'lift':>7}")
                for lift_, res_, sing_, still_, null_, nm, _f in pair_rows[:5]:
                    print(f"  {'':3} {nm:44} {res_:8} {still_:6} {null_:6.1f} {lift_:+7.1f}")
                best_single = rows[0]
                bp = pair_rows[0]
                gain = bp[1] - best_single[1]
                print(f"  best pair resolves {bp[1]} vs best single {best_single[1]} "
                      f"({gain:+d}); still {bp[3]} vs {best_single[3]}")
                if gain <= 2:
                    print("  -> conjunction adds nothing material: the remainder is")
                    print("     not a missing COMBINATION of what we already enumerate.")
            rows = rows + pair_rows
            rows.sort(reverse=True)

        lift, res, sing, still, null, name, fam = rows[0]
        if a.quiet:
            print(f"{game:>6} traces={len(files):>3} ctx={len(contexts):>5} "
                  f"{name:20} resolved={res:>4} still={still:>4} "
                  f"null={null:>6.1f} lift={lift:+7.1f}")
            continue
        # Wins only with REPEATS and materially above its own shuffle null --
        # H006's bar, which stops a re-key that merely made visits unique.
        win = res >= 2 and lift >= max(3.0, 0.5 * null)
        verdicts[game] = (fam, name, lift) if win else ("F", "-", lift)
        print(f"  -> {('family ' + fam + ' (' + name + ')') if win else 'F: UNEXPLAINED'}"
              f"   lift over null {lift:+.1f}\n")

    print("=" * 66)
    print("VERDICT per game (F = nothing above null):")
    for g, (fam, name, lift) in verdicts.items():
        print(f"  {g:>6}: family {fam}  {name:24} lift {lift:+.1f}")
    fams = collections.Counter(v[0] for v in verdicts.values())
    print(f"\nfamilies that won: {dict(fams)}")
    if verdicts and fams.get("F", 0) == len(verdicts):
        print("\nALL UNEXPLAINED. The machinery did not discover a disambiguating")
        print("  variable on ANY of these games, with 3x the repeats H006 had.")
        print("  -> evidence AGAINST making temporal latent state the immediate")
        print("     architectural priority, and a direct negative for H013's claim.")
    elif fams.get("C", 0) or fams.get("D", 0):
        print("\nRelational / interaction-history families win -> the state-selection")
        print("  machinery CAN find the variable once the candidate family exists.")


if __name__ == "__main__":
    main()
