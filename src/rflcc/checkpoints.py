"""Common-checkpoint persistence for B-Transfer."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from .qtables import QTables


CHECKPOINT_SCHEMA = "rflcc-checkpoint-0.2"


def _key(value):
    return repr(value)


def save_checkpoint(q_tables: QTables, path: str | Path, *, seed: int, episodes: int, config_hash: str = "") -> dict:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CHECKPOINT_SCHEMA,
        "seed": int(seed),
        "episodes": int(episodes),
        "config_hash": config_hash,
        "q_hash": q_tables.deep_hash(),
        "n_actions": q_tables.n_actions,
        "options": list(q_tables.options),
        "low": [[_key(k), list(v)] for k, v in q_tables.low.items()],
        "high": [[_key(k), {str(a): float(x) for a, x in v.items()}] for k, v in q_tables.high.items()],
    }
    (path / "checkpoint.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_checkpoint(path: str | Path, *, expected_config_hash: str | None = None) -> tuple[QTables, dict]:
    payload = json.loads((Path(path) / "checkpoint.json").read_text(encoding="utf-8"))
    if payload.get("schema_version") != CHECKPOINT_SCHEMA:
        raise ValueError("checkpoint schema version mismatch")
    if expected_config_hash is not None and payload.get("config_hash") != expected_config_hash:
        raise ValueError("checkpoint config hash mismatch")
    q = QTables(n_actions=int(payload["n_actions"]), options=tuple(payload["options"]))
    q.low = {ast.literal_eval(k): list(v) for k, v in payload.get("low", [])}
    q.high = {ast.literal_eval(k): {int(a): float(x) for a, x in v.items()} for k, v in payload.get("high", [])}
    if q.deep_hash() != payload.get("q_hash"):
        raise ValueError("checkpoint Q hash mismatch")
    return q, payload
