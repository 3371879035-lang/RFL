import pytest

from rflcc.checkpoints import save_checkpoint, load_checkpoint
from rflcc.qtables import QTables


def test_checkpoint_round_trip_and_hash_guard(tmp_path):
    q = QTables()
    q.high[0] = {0: 0.6, 1: 0.0}
    q.low[(1, 2)] = [0.1, 0.2, 0.0, 0.0, 0.0]
    save_checkpoint(q, tmp_path, seed=1, episodes=10, config_hash="x")
    restored, meta = load_checkpoint(tmp_path, expected_config_hash="x")
    assert restored.deep_hash() == q.deep_hash()
    assert meta["q_hash"] == q.deep_hash()
    with pytest.raises(ValueError):
        load_checkpoint(tmp_path, expected_config_hash="bad")
