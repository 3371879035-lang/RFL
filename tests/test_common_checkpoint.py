import pytest

from rflcc.checkpoints import save_checkpoint, load_checkpoint
from rflcc.qtables import QTables
from rflcc.router import UpdateRouter


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


def test_clones_start_identical_and_diverge_independently():
    q = QTables()
    q.high[0] = {0: 0.6, 1: 0.0}
    clones = [q.copy() for _ in range(3)]
    assert len({x.deep_hash() for x in clones}) == 1
    routed = UpdateRouter(alpha_diag=0.1).route(
        responsibility={"H": 1.0, "L": 0.0, "E": 0.0}, s_h=0, option=0, last_low=None,
    )
    UpdateRouter(alpha_diag=0.1).apply(clones[0], routed)
    assert clones[1].deep_hash() == q.deep_hash()
    assert clones[0].deep_hash() != clones[1].deep_hash()
