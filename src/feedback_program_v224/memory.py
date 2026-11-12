"""Canonical facts; behavior propensity is audit metadata, not a state feature."""
from feedback_program_v223.memory import MemoryBank as PreviousBank, Event, Schema


class MemoryBank(PreviousBank):
    def view(self, stop=None):
        result = super().view(stop)
        result['features'][..., -2] = 0.  # Retain the original propensity in Event.
        return result
