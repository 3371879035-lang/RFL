import pytest

from rflcc.qtables import QTables
from rflcc.router import AppliedUpdate, UpdateRouter


def test_apply_uses_scaled_additive_delta_and_returns_receipt():
    q = QTables()
    router = UpdateRouter(alpha_diag=0.1)
    routed = router.route(responsibility={"H": 1.0, "L": 0.0, "E": 0.0}, s_h=0, option=0, last_low=None)
    applied = router.apply(q, routed)
    assert isinstance(applied[0], AppliedUpdate)
    assert applied[0].delta_q == pytest.approx(-0.1)
    assert applied[0].q_before == pytest.approx(0.0)
    assert applied[0].q_after == pytest.approx(-0.1)
