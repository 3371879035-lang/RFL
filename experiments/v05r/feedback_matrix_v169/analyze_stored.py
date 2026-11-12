"""Compute the prospectively named V0.5 metrics from stored native records only."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import math

HERE = Path(__file__).resolve().parent


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def key(*x):
    return json.dumps(x, separators=(",", ":"))


def svg_chart(path, panels, labels, colors, dashed, *, x_label, y_label, ymax=None):
    width, height, left, top, panel_w, plot_h = 1200, 430, 65, 45, 320, 285
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="1200" height="430" fill="white"/>',
             '<g font-family="Arial,sans-serif" font-size="12" fill="#263238">']
    global_y = ymax or max(1, max(y for p in panels for points in p["series"] for _, y in points))
    global_y = max(1, global_y)
    for pi, panel in enumerate(panels):
        x0 = left + pi * 395
        xmax = max(1, max(x for points in panel["series"] for x, _ in points))
        parts.append(f'<text x="{x0 + panel_w / 2}" y="22" text-anchor="middle" font-size="16">{panel["title"]}</text>')
        for j in range(6):
            yy = top + plot_h * j / 5
            val = global_y * (5 - j) / 5
            parts.append(f'<path d="M{x0},{yy} H{x0 + panel_w}" stroke="#e4e8eb" fill="none"/>')
            parts.append(f'<text x="{x0 - 8}" y="{yy + 4}" text-anchor="end">{val:.0f}</text>')
        for j in range(5):
            xx = x0 + panel_w * j / 4
            parts.append(f'<text x="{xx}" y="{top + plot_h + 20}" text-anchor="middle">{xmax*j/4:.0f}</text>')
        parts.append(f'<path d="M{x0},{top} V{top+plot_h} H{x0+panel_w}" stroke="#455a64" fill="none"/>')
        for si, points in enumerate(panel["series"]):
            pts = ' '.join(f'{x0 + panel_w*x/xmax:.3f},{top+plot_h-plot_h*y/global_y:.3f}' for x, y in points)
            dash = ' stroke-dasharray="6 4"' if dashed[si] else ''
            parts.append(f'<polyline points="{pts}" stroke="{colors[si]}" stroke-width="2" fill="none"{dash}/>')
        parts.append(f'<text x="{x0+panel_w/2}" y="{top+plot_h+43}" text-anchor="middle">{x_label}</text>')
    parts.append(f'<text x="16" y="190" transform="rotate(-90 16 190)" text-anchor="middle">{y_label}</text>')
    for i, label in enumerate(labels):
        x = 95 + i * (1010 / max(1, len(labels)))
        dash = ' stroke-dasharray="6 4"' if dashed[i] else ''
        parts.append(f'<path d="M{x},404 h25" stroke="{colors[i]}" stroke-width="2"{dash}/><text x="{x+31}" y="408">{label}</text>')
    parts.append('</g></svg>')
    path.write_text('\n'.join(parts) + '\n', encoding="utf-8")


def main():
    assert not (HERE / "analysis.json").exists(), "analysis output is exclusive"
    matrix = json.loads((HERE / "evidence_matrix/result.json").read_text())
    review = json.loads((HERE / "evidence_matrix/audit_result_v2.json").read_text())
    wiring = json.loads((HERE / "evidence_wiring/audit_result.json").read_text())
    assert review["complete"] and wiring["complete"]
    streams = matrix["streams"]
    arms = ["P-RP", "S-RP", "P-R", "S-R", "P-F", "S-F"]
    per_extra = { (s["case"], s["arm"]): Counter() for s in streams }
    before, truths, begins = {}, {}, {}
    timing_violations = []
    with (HERE / "evidence_matrix/raw.jsonl").open(encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            p, ctx = e["payload"], e["context"]
            sid = (ctx.get("case"), ctx.get("arm"))
            if e["tag"] == "STREAM_INITIAL":
                before[sid] = p["learner"]
                truths[sid] = p["case"]
            elif e["tag"] == "EPISODE_BEGIN":
                begins[p["uid"]] = p
                if p["kind"] == "trial":
                    maps = {(r,c):x for r,c,x in p["controller"]["mappings"]}
                    for r,c,x in truths[sid]["controller_mappings"]:
                        if r < truths[sid]["decision_points"] and x == truths[sid]["passable_exits"][r] and c != x and (r,c) not in maps:
                            per_extra[sid]["trial_deletions_of_beneficial_remap"] += 1
            elif e["tag"] == "EPISODE_COMPLETE":
                b = begins[p["uid"]]
                if p["terminal"] != "SUCCESS":
                    if b["kind"] == "trial":
                        per_extra[sid]["trial_failures"] += 1
                    else:
                        last = p["steps"][-1]
                        old_edge = before[sid]["edges"].get(key(last["room"], last["executed"]))
                        known_edge = bool(old_edge and old_edge["outcome"] == "COLLISION")
                        known_command = before[sid]["commands"].get(key(last["room"], last["revision"], last["command"])) == last["executed"]
                        per_extra[sid]["repeated_physical_failure"] += known_edge
                        per_extra[sid]["predictable_command_failure"] += known_edge and known_command
                        per_extra[sid]["failed_step_exploration_flag"] += bool(b["coins"][last["room"]][0])
            elif e["tag"] == "LEARN":
                before[sid] = p["after"]
            elif e["tag"] == "COMMIT":
                for r,c in p["removals"]:
                    src = {(rr,cc):x for rr,cc,x in truths[sid]["controller_mappings"]}
                    if src[r,c] == truths[sid]["passable_exits"][r] and c != src[r,c]:
                        per_extra[sid]["committed_beneficial_remap_deletions"] += 1
            elif e["tag"] == "MAIN_CHECKPOINT":
                if p["wall_seconds"] < p["cpu_seconds"] * .90:
                    timing_violations.append({"seq": e["seq"], "context": ctx, "wall_seconds": p["wall_seconds"], "cpu_seconds": p["cpu_seconds"]})
    total_fields = ["main_tasks", "main_successes", "main_failures", "trial_rollouts", "cold_successes", "continued_successes", "cache_hits"]
    summaries = []
    for arm in arms:
        group = [s for s in streams if s["arm"] == arm]
        row = {"arm": arm, **{k: sum(s[k] for s in group) for k in total_fields}}
        row["prefix_successes"] = {str(n): sum(s["prefix_successes"][str(n)] for s in group) for n in (12,24,48)}
        row["counts"] = {k: sum(s["counts"][k] for s in group) for k in group[0]["counts"]}
        row["target_reached_cases"] = sum(s["target"]["status"] == "REACHED" for s in group)
        row["later_failures_after_target"] = sum(s["later_failures"] or 0 for s in group)
        row["other_metrics"] = dict(sum((per_extra[s["case"],s["arm"]] for s in group), Counter()))
        row["final_24_successes"] = sum(s["continued_successes"] for s in group)
        summaries.append(row)
    depth_rows = []
    for d in (1,3,5):
        for arm in arms:
            group = [s for s in streams if s["arm"] == arm and s["decision_points"] == d]
            depth_rows.append({"decision_points": d, "arm": arm, "main_successes": sum(s["main_successes"] for s in group),
                               "main_tasks": 96, "trials": sum(s["trial_rollouts"] for s in group),
                               "steps": sum(s["counts"]["steps"] for s in group),
                               "prefix_successes": {str(n): sum(s["prefix_successes"][str(n)] for s in group) for n in (12,24,48)},
                               "target_reached": sum(s["target"]["status"] == "REACHED" for s in group)})
    targets = [{"case": s["case"], "arm": s["arm"], "status": s["target"]["status"],
                "main_index_1based": s["target"]["main_index_1based"],
                "rollouts": s["target"]["cost"]["rollouts"] if s["target"]["cost"] else None,
                "steps": s["target"]["cost"]["steps"] if s["target"]["cost"] else None,
                "trials": s["target"]["cost"]["trials_so_far"] if s["target"]["cost"] else None,
                "controller_transactions": s["target"]["cost"]["controller_transactions"] if s["target"]["cost"] else None,
                "cpu_seconds": s["target"]["cost"]["cpu_seconds"] if s["target"]["cost"] else None,
                "wall_seconds": s["target"]["cost"]["wall_seconds"] if s["target"]["cost"] else None,
                "later_failures": s["later_failures"]} for s in streams]
    matched = []
    cost_curves = []
    for channel in ("RP", "R", "F"):
        cases = sorted({s["case"] for s in streams})
        budgets = {}
        for case in cases:
            p, s = [next(x for x in streams if x["case"] == case and x["arm"] == m+'-'+channel) for m in ("P","S")]
            b = min(p["counts"]["steps"], s["counts"]["steps"])
            budgets[case] = b
            delivered = lambda x: sum(r["terminal"] == "SUCCESS" for r in x["curve"] if r["steps"] <= b)
            matched.append({"case": case,"channel": channel,"shared_step_budget": b,"P_deliveries": delivered(p),"S_deliveries": delivered(s)})
        for fraction in range(101):
            row = {"channel":channel,"fraction_percent":fraction,"steps":sum((b*fraction)//100 for b in budgets.values())}
            for mode in ("P","S"):
                row[mode] = sum(sum(r["terminal"] == "SUCCESS" for r in x["curve"] if r["steps"] <= (budgets[x["case"]]*fraction)//100)
                                for x in streams if x["arm"] == mode+'-'+channel)
            cost_curves.append(row)
    failures = []
    for d in (1,3,5):
        for arm in arms:
            group = [s for s in streams if s["decision_points"] == d and s["arm"] == arm]
            for e in range(49):
                failures.append({"decision_points":d,"arm":arm,"main_tasks_per_stream":e,
                                 "cumulative_failures":sum(sum(r["terminal"] != "SUCCESS" for r in s["curve"][:e]) for s in group)})
    wiring_exit=json.loads((HERE/'evidence_wiring/exit.json').read_text())
    matrix_exit=json.loads((HERE/'evidence_matrix/exit.json').read_text())
    combined={k:wiring_exit['counts'].get(k,0)+matrix_exit['counts'].get(k,0) for k in set(wiring_exit['counts'])|set(matrix_exit['counts'])}
    raw_bytes=sum((HERE/p/'raw.jsonl').stat().st_size for p in ('evidence_wiring','evidence_matrix'))
    assert combined['rollouts']<=2166 and combined['steps']<=25992 and raw_bytes<=134217728
    assert wiring_exit['wall_seconds']+matrix_exit['wall_seconds']<=1200
    analysis={"schema":"V169_EXECUTED_MATRIX_ANALYSIS","scope":"Six fixed mirrored engineering cases; no independent seed inference",
              "summaries":summaries,"by_depth":depth_rows,"targets":targets,"matched_cost":matched,
              "matched_cost_rule":"At each case/channel use the common completed work range B=min(P_final_steps,S_final_steps); compare deliveries at the same step budget. Sum descriptions, not independent samples.",
              "combined_actual_counts":combined,"combined_instrumented_native_wall_seconds":wiring_exit['wall_seconds']+matrix_exit['wall_seconds'],
              "combined_capture_bytes":raw_bytes,"matrix_records":review['records'],"wiring_records":wiring['records'],
              "timing_check_failure":{"old_matrix_audit_exit":1,"counterexamples":len(timing_violations),"first_examples":timing_violations[:4],
                                      "explanation":"Per-stream GetProcessTimes readings exhibited 0.015625-second quantization; paired wall/CPU reads are not a valid strict ordering invariant at these short intervals. No production speed ranking is based on these clocks.",
                                      "correction":"New audit_stored_v2.py only removes the 90%-wall ordering assumption and uses a new output filename; nonnegative and monotonic timing checks retained; original audit and error preserved; native not rerun."},
              "boundaries":["Pure feedback retains task goal and visible outcome labels; it is not goal-free or prior-free.",
                            "F uses a model-based categorical planner while RP/R use Q heads; cross-family results are whole-method comparisons.",
                            "S uses a hand-declared experiment-order rule plus a learned current-source query index, not a trained general causal/value model.",
                            "Exact query reuse is valid in this deterministic unchanged world; stochastic settings require a new contract.",
                            "Both command outcomes are reachable in the initial swap; all groups have the same local repair capability.",
                            "Increased depth also lengthens propagation from the same terminal reward rule; not a separate causal identification of every kind of complexity.",
                            "After-24 observations reuse the same environment; not unseen-family transfer.",
                            "Runtime is instrumented local CPU with capture/tracemalloc; Python traced heap is not full process RSS; no all-resource dominance claim."]}
    write_json(HERE/'analysis.json',analysis)
    for name, data in [('group_summary.csv',[{**{k:v for k,v in s.items() if not isinstance(v,dict)},'steps':s['counts']['steps'],'rollouts':s['counts']['rollouts']} for s in summaries]),
                       ('targets.csv',targets),('matched_cost.csv',matched),('cost_curve.csv',cost_curves),('failure_curve.csv',failures)]:
        with (HERE/name).open('x',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    panels=[]
    for d in (1,3,5):
        panels.append({'title':f'{d} decision points','series':[[ (r['main_tasks_per_stream'],r['cumulative_failures']) for r in failures if r['decision_points']==d and r['arm']==arm] for arm in arms]})
    svg_chart(HERE/'learning_curves.svg',panels,arms,['#2b6cb0','#2b6cb0','#c05621','#c05621','#2f855a','#2f855a'],[True,False,True,False,True,False],x_label='Main tasks per stream',y_label='Cumulative main failures (two cases)')
    panels=[]
    for c in ('RP','R','F'):
        panels.append({'title':c+' signal channel','series': [[(r['steps'],r[m]) for r in cost_curves if r['channel']==c] for m in ('P','S')]})
    svg_chart(HERE/'matched_cost_curves.svg',panels,['P: fixed practice','S: structured feedback'],['#718096','#805ad5'],[True,False],x_label='Common environment-step budget',y_label='Successful main deliveries (six cases)',ymax=288)
    print(json.dumps({'summaries':summaries,'by_depth':depth_rows,'matched_cost_totals':{c:{'P':sum(x['P_deliveries'] for x in matched if x['channel']==c),'S':sum(x['S_deliveries'] for x in matched if x['channel']==c)} for c in ('RP','R','F')},'combined_actual':combined},ensure_ascii=False))


if __name__=='__main__':
    main()
