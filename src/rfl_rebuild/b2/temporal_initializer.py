"""C3's explicit acquisition initializer; no construction-data reads or layer search."""
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.env.kernel import HORIZON
from rfl_rebuild.learner.store import Edit, LearnerPersistentState, Q, QAddress

INITIALIZER_ID = "c3-temporal-layer-1-v1"
ACQUISITION_CAP = 576


def layer_edits(reference, layer):
    """One optimistic minimum action in every strict-gap row of a fixed layer."""
    if type(layer) is not int or not 0 <= layer < HORIZON:
        raise ProtocolError("the temporal layer must be an integer inside the horizon")
    result = []
    for (s, z, m), row in reference.rows.items():
        if s.t != layer:
            continue
        best, worst = max(row.values()), min(row.values())
        if worst == best:
            continue
        action = min(a for a, value in row.items() if value == worst)
        result.append(Edit(Q, QAddress(s, z, m, action), best + (best - worst)))
    return tuple(result)


def temporal_initializer(q_reference):
    """Fresh full learner per call; only Q is changed and layer 1 is fixed."""
    learner = LearnerPersistentState()
    learner.apply_transaction(layer_edits(q_reference, 1), q_reference=q_reference)
    return learner
