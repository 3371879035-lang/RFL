"""Descriptive analysis of actual V170 data only. No native/learner imports."""
from pathlib import Path
from collections import defaultdict
import csv
import json
import math
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ARMS = ("F", "Q-RP", "Q-R", "Q-RP-Replay12")
COLORS = {"F": "#087f8c", "Q-RP": "#b04090", "Q-R": "#d47a08", "Q-RP-Replay12": "#2659b5"}


def write_json(name, value):
    with (HERE / name).open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_csv(name, rows):
    with (HERE / name).open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def delivered(stream, budget):
    rows = [r for r in stream["curve"] if r["steps"] <= budget]
    return sum(r["terminal"] == "SUCCESS" for r in rows), len(rows)


def main():
    evidence = {}
    for phase in ("wiring", "matrix"):
        directory = HERE / ("evidence_" + phase)
        receipt = json.loads((directory / "exit.json").read_text())
        audit = json.loads((directory / "audit_result.json").read_text())
        assert receipt["complete"] and receipt["child_exit_code"] == 0
        assert audit["complete"] and audit["child_exit_code"] == 0
        evidence[phase] = {"native": receipt, "audit": audit}
    streams = json.loads((HERE / "evidence_matrix" / "result.json").read_text())["streams"]
    assert len(streams) == 24 and all(s["main_tasks"] == 48 for s in streams)
    by_case = defaultdict(dict)
    groups, depths, targets, curves = [], [], [], []
    for s in streams:
        by_case[s["case"]][s["arm"]] = s
        t = s["target"]
        index = t["main_index_1based"]
        row = s["curve"][index-1] if index is not None else None
        targets.append({"case": s["case"], "arm": s["arm"], "status": t["status"],
                        "main_index_1based": index, "steps": t["steps"],
                        "ordinary_backups_to_target": row["ordinary_backups"] if row else None,
                        "replay_backups_to_target": row["replay_backups"] if row else None,
                        "later_failures": t["later_failures"]})
        successes = 0
        for i, row in enumerate(s["curve"]):
            successes += row["terminal"] == "SUCCESS"
            curves.append({"case": s["case"], "decision_points": s["decision_points"], "arm": s["arm"],
                           "main_index_1based": i+1, "successes": successes, "failures": i+1-successes,
                           "steps": row["steps"], "ordinary_backups": row["ordinary_backups"],
                           "replay_backups": row["replay_backups"], "fact_field_updates": row["fact_field_updates"]})
    for arm in ARMS:
        ss = [s for s in streams if s["arm"] == arm]
        groups.append({"arm": arm, "main_tasks": sum(s["main_tasks"] for s in ss),
                       "successes": sum(s["main_successes"] for s in ss),
                       "failures": sum(s["main_tasks"]-s["main_successes"] for s in ss),
                       "early12_successes": sum(s["prefix_successes"]["12"] for s in ss),
                       "cold24_successes": sum(s["cold_successes"] for s in ss),
                       "continued24_successes": sum(s["continued_successes"] for s in ss),
                       "steps": sum(s["counts"]["steps"] for s in ss),
                       "target_reached_cases": sum(s["target"]["status"] == "REACHED" for s in ss),
                       "failure_at_exploratory_deviation": sum(s["failure_at_exploratory_deviation"] for s in ss),
                       "ordinary_backups": sum(s["counts"].get("ordinary_backups", 0) for s in ss),
                       "replay_backups": sum(s["counts"].get("replay_backups", 0) for s in ss),
                       "numeric_changes": sum(s["counts"].get("numeric_changes", 0) for s in ss),
                       "fact_field_updates": sum(s["counts"].get("fact_field_updates", 0) for s in ss),
                       "plan_ns": sum(s["plan_ns"] for s in ss), "update_ns": sum(s["update_ns"] for s in ss),
                       "max_snapshot_bytes": max(r["learner_snapshot_bytes"] for s in ss for r in s["curve"])})
        for depth in (1, 3, 5):
            ds = [s for s in ss if s["decision_points"] == depth]
            depths.append({"arm": arm, "decision_points": depth,
                           "successes": sum(s["main_successes"] for s in ds), "main_tasks": 96,
                           "steps": sum(s["counts"]["steps"] for s in ds)})
    comparisons, pairs = [], []
    for qarm in ARMS[1:]:
        per_fraction = defaultdict(lambda: {"F_successes": 0, "Q_successes": 0, "F_tasks": 0, "Q_tasks": 0, "steps": 0})
        for case, arms in by_case.items():
            f, q = arms["F"], arms[qarm]
            budget = min(f["counts"]["steps"], q["counts"]["steps"])
            for percent in (25, 50, 75, 100):
                b = budget*percent//100
                fs, fn = delivered(f, b)
                qs, qn = delivered(q, b)
                pairs.append({"case": case, "Q_arm": qarm, "common_budget_percent": percent,
                              "step_budget": b, "F_successes": fs, "Q_successes": qs,
                              "F_completed_tasks": fn, "Q_completed_tasks": qn})
                row = per_fraction[percent]
                for field, value in (("F_successes", fs), ("Q_successes", qs), ("F_tasks", fn), ("Q_tasks", qn), ("steps", b)):
                    row[field] += value
        comparisons.append({"Q_arm": qarm, "common_step_budgets": dict(per_fraction)})
    # Exact trajectory equality is stronger than aggregate success equality.
    raw_by_arm = defaultdict(dict)
    with (HERE / "evidence_matrix" / "raw.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["tag"] == "EPISODE_COMPLETE":
                raw_by_arm[r["context"]["arm"]][(r["context"]["case"], r["context"]["main_epoch"])] = r["payload"]["steps"]
    exact = {q: {"identical_main_trajectories": sum(value == raw_by_arm[q][k] for k, value in raw_by_arm["F"].items()),
                 "total": 288} for q in ARMS[1:]}
    combined = {k: sum(v["native"]["counts"].get(k, 0) for v in evidence.values()) for k in
                {k for v in evidence.values() for k in v["native"]["counts"]}}
    analysis = {"status": "COMPLETE_LOCAL_FIXED_INTERFACE_BASELINE", "groups": groups, "by_depth": depths,
                "targets": targets, "same_steps": comparisons, "F_pair_trajectory_comparison": exact,
                "combined_counts": combined, "evidence": evidence,
                "all_24_streams_completed_48_tasks": True, "extra_environment_trials": 0,
                "controller_edits": 0, "fresh_science_keys_RNG_formal_collection": 0,
                "scope": "Six fixed deterministic cases and common finite coordinates, not independent seeds. F/model vs Q is a whole-method comparison.",
                "timing_scope": "Instrumented small intervals, includes tracemalloc; no production CPU ranking. Snapshot bytes are serialization size, not RAM."}
    write_json("analysis.json", analysis)
    write_csv("group_summary.csv", groups)
    write_csv("depth_summary.csv", depths)
    write_csv("targets.csv", targets)
    write_csv("failure_curve.csv", curves)
    write_csv("matched_steps.csv", pairs)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="430" viewBox="0 0 1080 430">',
           '<rect width="1080" height="430" fill="#fafafa"/>',
           '<g font-family="Arial,sans-serif" fill="#222">',
           '<text x="30" y="28" font-size="20">V0.5 baseline: cumulative main-task failures (two cases per depth)</text>']
    for j, arm in enumerate(ARMS):
        x = 36+j*250
        dash = ' stroke-dasharray="3 5"' if arm == "Q-RP-Replay12" else ''
        svg += [f'<line x1="{x}" x2="{x+30}" y1="55" y2="55" stroke="{COLORS[arm]}" stroke-width="3"{dash}/>',
                f'<text x="{x+38}" y="60" font-size="14">{arm}</text>']
    for panel, depth in enumerate((1, 3, 5)):
        left, top, width, height = 55+panel*350, 100, 290, 250
        max_y = max(sum(c["failures"] for c in curves if c["arm"] == arm and c["decision_points"] == depth and c["main_index_1based"] == 48) for arm in ARMS)
        scale = max(10, math.ceil(max_y/10)*10)
        svg.append(f'<text x="{left}" y="88" font-size="17">Depth {depth}</text>')
        for tick in range(5):
            value = scale*tick/4
            y = top+height-height*tick/4
            svg += [f'<line x1="{left}" x2="{left+width}" y1="{y}" y2="{y}" stroke="#ddd"/>',
                    f'<text x="{left-8}" y="{y+4}" text-anchor="end" font-size="11">{value:g}</text>']
        for tick in (0, 12, 24, 36, 48):
            x = left+width*tick/48
            svg.append(f'<text x="{x}" y="{top+height+20}" text-anchor="middle" font-size="11">{tick}</text>')
        for arm in ARMS:
            points = [(left, top+height)]
            for e in range(1, 49):
                value = sum(c["failures"] for c in curves if c["arm"] == arm and c["decision_points"] == depth and c["main_index_1based"] == e)
                points.append((left+width*e/48, top+height-height*value/scale))
            pts = " ".join(f"{x:.3f},{y:.3f}" for x,y in points)
            dash = ' stroke-dasharray="3 5"' if arm == "Q-RP-Replay12" else ''
            svg.append(f'<polyline points="{pts}" fill="none" stroke="{COLORS[arm]}" stroke-width="2.4"{dash}/>')
    svg += ['<text x="30" y="406" font-size="13">Overlapping curves are retained. Fixed exploration remains active; these are not independent-seed confidence intervals.</text>', '</g></svg>']
    text = "\n".join(svg)
    ET.fromstring(text)
    with (HERE / "learning_curves.svg").open("x", encoding="utf-8", newline="\n") as f:
        f.write(text+"\n")
    print(json.dumps({"groups": groups, "combined_counts": combined, "trajectory_equality": exact,
                      "same_steps": comparisons, "target_reached": sum(t["status"] == "REACHED" for t in targets)}))


if __name__ == "__main__":
    main()
