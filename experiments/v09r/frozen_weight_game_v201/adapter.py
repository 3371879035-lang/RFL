"""Public observation encoding only; no hidden world, planner, or learned weights.

Six context numbers and six candidate numbers are a lossy interface, not a
claim that V200 understands a 64 x 64 map. Nothing here chooses an action.
"""
import numpy as np


def encode(observation, directions):
    scalar, image = observation.scalar, observation.image
    targets = np.argwhere(image[1] != 0)
    if len(targets):
        offsets = targets[:, ::-1].astype(np.float32) - 10.
        treasure = offsets[np.argmin((offsets * offsets).sum(axis=1))]
        treasure_distance = float(np.linalg.norm(treasure))
        treasure_bearing = treasure / max(treasure_distance, 1.)
        treasure_distance /= np.sqrt(200.)
    else:
        treasure_bearing, treasure_distance = np.zeros(2), 1.

    # The kernel already exposes a coarse bearing/distance for unseen monsters.
    # We use that public signal, not the true unseen position or distance table.
    monsters = []
    for i in (6, 12):
        exists, visible, dx, dz, speed, bucket = scalar[i:i + 6]
        if exists:
            relative = np.array([dx, dz], dtype=np.float32)
            distance = (float(np.linalg.norm(relative)) * 10. if visible
                        else (float(bucket) * 5. + 1.) * 15.)
            monsters.append((distance, relative, float(visible)))
    if monsters:
        distance, relative, visible = min(monsters, key=lambda x: x[0])
        monster_bearing = relative / max(float(np.linalg.norm(relative)), 1e-12)
        monster_distance = min(distance / 90., 1.)
    else:
        monster_bearing, monster_distance, visible = np.zeros(2), 1., 0.

    context = np.array([scalar[2], scalar[3], scalar[4], monster_distance,
                        visible, treasure_distance], dtype=np.float32)
    candidates = []
    for action in range(16):
        dx, dz = map(int, directions[action % 8])
        unit = np.array([dx, dz], dtype=np.float32) / np.hypot(dx, dz)
        # This is the observed adjacent geometry for both walk and blink. It is
        # NOT a prediction of blink landing, and it never removes a legal move.
        adjacent_open = bool(image[0, 10 + dz, 10 + dx])
        if dx and dz:
            adjacent_open &= bool(image[0, 10, 10 + dx] or image[0, 10 + dz, 10])
        candidates.append([dx, dz, float(action >= 8), float(adjacent_open),
                           float(unit @ monster_bearing), float(unit @ treasure_bearing)])
    return context, np.array(candidates, dtype=np.float32)
