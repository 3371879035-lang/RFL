"""Directly observed finite-horizon measurements, never rewards or TD targets."""
import numpy as np
import torch
from torch import nn

HORIZONS = (1, 4, 16, 64)

class MeasurementHead(nn.Module):
    def __init__(self):
        super().__init__()
        self.value = nn.Linear(64, len(HORIZONS)*2)
        self.advantage = nn.Linear(64, 16*len(HORIZONS)*2)
        # No invented optimistic outcomes before real experience.
        nn.init.zeros_(self.value.weight)
        nn.init.zeros_(self.value.bias)
        nn.init.zeros_(self.advantage.weight)
        nn.init.zeros_(self.advantage.bias)

    def forward(self, hidden):
        value = self.value(hidden).unsqueeze(-2)
        advantage = self.advantage(hidden).reshape(*hidden.shape[:-1], 16, len(HORIZONS)*2)
        output = value+advantage-advantage.mean(-2, keepdim=True)
        return output.reshape(*hidden.shape[:-1], 16, len(HORIZONS), 2)


def observed_labels(episode_rows, terminal):
    """Only labels whose window has arrived, or whose real episode has ended.

    Steps include the action at the source record. After actual task termination,
    further task steps/pickups are zero. An unfinished prefix is NOT termination.
    """
    n = len(episode_rows)
    pickups = np.r_[0, np.cumsum([r[1] for r in episode_rows], dtype=np.int64)]
    labels = []
    for k, horizon in enumerate(HORIZONS):
        starts = []
        if n >= horizon:
            starts.append(n-horizon)
        if terminal:
            starts.extend(range(max(0,n-horizon+1), n))
        for start in starts:
            steps = n-start
            count = int(pickups[n]-pickups[start])
            labels.append((episode_rows[start][0], k, steps, count))
    return labels


def goal_scores(prediction):
    """Public task goal only at action selection, not an optimization label.

    Limited to the next64 task steps; a disclosed horizon revision, not an
    unchanged full-episode objective. No additional capture punishment.
    """
    steps = prediction[..., -1, 0].clamp(0,1)*HORIZONS[-1]
    pickups = prediction[..., -1, 1].clamp(0,10)
    return .015*steps+pickups
