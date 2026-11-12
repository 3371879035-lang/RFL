"""Closed external outcome projection, separate from the audit/cost record.

Only the actual owned producer's completed opaque curve may enter. This is an
in-process audited constructor boundary, not a hostile-Python security sandbox.
"""
from types import MappingProxyType
from weakref import WeakKeyDictionary

from rfl_rebuild.b1.errors import ProtocolError
import v104_different_stream_curve as owned_curve

FIELDS = ("future_rewards", "future_outcomes", "future_trajectories",
          "future_actions", "future_observations")
_VIEWS = WeakKeyDictionary()


class ExternalCurveView:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise ProtocolError("requires actual owned external observations")


def _project(checkpoints):
    fields = {name: [] for name in FIELDS}
    times, means = [], []
    for e, traces, mean in checkpoints:
        checkpoint_values = {name: [] for name in FIELDS}
        for trace in traces:
            steps = trace.steps
            checkpoint_values["future_rewards"].append(tuple(float(s.reward) for s in steps))
            checkpoint_values["future_outcomes"].append(tuple(s.outcome for s in steps))
            checkpoint_values["future_trajectories"].append(tuple(s.state for s in steps))
            checkpoint_values["future_actions"].append(tuple(int(s.a_cmd) for s in steps))
            checkpoint_values["future_observations"].append(tuple(getattr(s, "obs", None) for s in steps))
        for name in FIELDS:
            fields[name].append(tuple(checkpoint_values[name]))
        times.append(e)
        means.append(mean)
    return MappingProxyType({k: tuple(v) for k, v in fields.items()}), tuple(times), tuple(means)


def build(handle):
    checkpoints, pre_level, t_max = owned_curve._external_material(handle)
    fields, times, means = _project(checkpoints)
    payload = MappingProxyType({"fields": fields,
                                "episodes": times, "values": means,
                                "pre_level": pre_level, "t_max": t_max})
    view = object.__new__(ExternalCurveView)
    _VIEWS[view] = (handle, payload)
    return view


def read(view):
    if type(view) is not ExternalCurveView or view not in _VIEWS:
        raise ProtocolError("nominal issued external view required")
    handle, payload = _VIEWS[view]
    checkpoints, pre_level, t_max = owned_curve._external_material(handle)
    fields, times, means = _project(checkpoints)
    if (set(payload) != {"fields", "episodes", "values", "pre_level", "t_max"} or
        payload["fields"] != fields or payload["episodes"] != times or
        payload["values"] != means or
        payload["pre_level"] != pre_level or payload["t_max"] != t_max):
        raise ProtocolError("external curve differs from its own observed records")
    return payload
