"""日志 I/O：episode JSONL（learner / evaluator 分区）与 CSV 聚合。"""

from __future__ import annotations

import gzip
import json
import os


class EpisodeLogger:
    def __init__(self, path: str, events_path: str | None = None) -> None:
        self.path = path
        self.events_path = events_path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._f = open(path, "w", encoding="utf-8")
        self._ef = None
        if events_path:
            os.makedirs(os.path.dirname(events_path) or ".", exist_ok=True)
            self._ef = gzip.open(events_path, "wt", encoding="utf-8")

    def write_episode(self, record: dict) -> None:
        self._f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def write_events(self, record: dict) -> None:
        if self._ef is not None:
            self._ef.write(json.dumps(record, ensure_ascii=False) + "\n")

    def close(self) -> None:
        self._f.close()
        if self._ef is not None:
            self._ef.close()


def build_episode_record(
    *,
    run_id: str,
    schema_version: str,
    seed: int,
    scenario_id: str,
    experiment: str,
    algorithm: str,
    condition: str,
    trace,
    observed_feedback: str,
    feedback_is_false: bool,
    learner: dict,
    evaluator_only: dict,
    metrics: dict,
    compute: dict,
) -> dict:
    """按 SPEC 的 episode JSON 结构组装记录（learner / evaluator 分区）。"""
    return {
        "schema_version": schema_version,
        "run_id": run_id,
        "seed": seed,
        "scenario_id": scenario_id,
        "experiment": experiment,
        "algorithm": algorithm,
        "condition": condition,
        "environment": {
            "noise_tape_hash": trace.noise_tape.sha256() if trace.noise_tape else None,
            "monster_start_lane": (
                trace.noise_tape.monster_start_lane if trace.noise_tape else None
            ),
            "horizon": len(trace.transitions),
        },
        "factual": {
            "option": trace.option,
            "terminal_type": trace.terminal_type,
            "discounted_return": round(trace.total_return, 6),
        },
        "feedback": {
            "observed": observed_feedback,
            "is_false": feedback_is_false,
        },
        "learner": learner,
        "evaluator_only": evaluator_only,
        "metrics": metrics,
        "compute": compute,
    }
