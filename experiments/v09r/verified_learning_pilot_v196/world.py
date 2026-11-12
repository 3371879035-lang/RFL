"""V09 local pursuit kernel. No old RFL module, SDK, or learner oracle calls."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import numpy as np

DIR = np.array([(1, 0), (1, -1), (0, -1), (-1, -1),
                (-1, 0), (-1, 1), (0, 1), (1, 1)], dtype=np.int16)
MAP_IDS = tuple(range(90101, 90113))
HORIZON = 256


def seed_for(*parts):
    return int.from_bytes(hashlib.blake2b(('V09|'+'|'.join(map(str, parts))).encode(),
                                        digest_size=8).digest(), 'little')


def rng_for(*parts):
    return np.random.default_rng(seed_for(*parts))


def make_map(map_id):
    rng = rng_for('map', map_id)
    roads = np.zeros((64, 64), np.uint8)
    edges, visited, stack = set(), {0}, [0]
    neighbors = lambda i: [j for j in (i-9, i+9, i-1, i+1)
                           if 0 <= j < 81 and abs(i//9-j//9)+abs(i%9-j%9) == 1]
    while stack:
        i = stack[-1]
        opts = [j for j in neighbors(i) if j not in visited]
        if not opts:
            stack.pop()
            continue
        j = int(rng.choice(opts))
        edges.add(tuple(sorted((i, j))))
        visited.add(j)
        stack.append(j)
    for i in range(81):
        for j in neighbors(i):
            if j > i and (i, j) not in edges and rng.random() < .25:
                edges.add((i, j))
    for i in range(81):
        x, z = 4+7*(i % 9), 4+7*(i//9)
        roads[z-1:z+2, x-1:x+2] = 1
    for i, j in sorted(edges):
        x, z = 4+7*(i % 9), 4+7*(i//9)
        xx, zz = 4+7*(j % 9), 4+7*(j//9)
        roads[min(z, zz)-1:max(z, zz)+2, min(x, xx)-1:max(x, xx)+2] = 1
    roads[[0, -1], :] = 0
    roads[:, [0, -1]] = 0
    return roads


def legal_neighbor(roads, x, z, a):
    dx, dz = map(int, DIR[a])
    xx, zz = x+dx, z+dz
    if not (0 <= xx < 64 and 0 <= zz < 64 and roads[zz, xx]):
        return False
    return not (dx and dz) or bool(roads[z, xx] or roads[zz, x])


def prepare_maps(directory):
    """Complete, outcome-independent map census. Distance arrays belong to kernel only."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import shortest_path
    directory = Path(directory)
    directory.mkdir(exist_ok=False)
    inventory = []
    for map_id in MAP_IDS:
        roads = make_map(map_id)
        z, x = np.where(roads)
        coords = np.stack((x, z), axis=1).astype(np.int16)
        index = np.full((64, 64), -1, np.int16)
        index[z, x] = np.arange(len(coords), dtype=np.int16)
        neighbor = np.full((len(coords), 8), -1, np.int16)
        rows, cols = [], []
        for i, (xx, zz) in enumerate(coords):
            for a, (dx, dz) in enumerate(DIR):
                if legal_neighbor(roads, int(xx), int(zz), a):
                    j = int(index[zz+dz, xx+dx])
                    neighbor[i, a] = j
                    rows.append(i)
                    cols.append(j)
        graph = csr_matrix((np.ones(len(rows), np.uint8), (rows, cols)),
                           shape=(len(coords), len(coords)))
        distances = shortest_path(graph, directed=False, unweighted=True, method='D')
        assert np.isfinite(distances).all(), 'Map construction must be connected'
        np.savez(directory/f'{map_id}.npz', roads=roads, index=index,
                 coords=coords, neighbor=neighbor)
        np.save(directory/f'{map_id}.dist.npy', distances.astype(np.int16))
        inventory.append(dict(map_id=map_id, passable=int(roads.sum()),
                              road_sha256=hashlib.sha256(roads.tobytes()).hexdigest(),
                              kernel_edges=len(rows)))
    (directory/'inventory.json').write_text(json.dumps(inventory, indent=2)+'\n', encoding='utf-8')
    return inventory


class MapBank:
    def __init__(self, directory):
        self.maps = {}
        for i in MAP_IDS:
            d = np.load(Path(directory)/f'{i}.npz')
            self.maps[i] = {k: d[k] for k in d.files}
            self.maps[i]['distances'] = np.load(Path(directory)/f'{i}.dist.npy', mmap_mode='r')


@dataclass
class Observation:
    image: np.ndarray
    scalar: np.ndarray
    legal: np.ndarray
    hero: tuple
    monster_visible: np.ndarray
    monster_positions: np.ndarray
    local_roads: np.ndarray


@dataclass(frozen=True)
class Fact:
    steps: int
    pickup: int
    captured: bool
    completed: bool
    buff_pickup: int


def scenario(seed, phase, episode):
    if phase == 'train':
        order = rng_for(seed, 'train-source-order', episode//16).permutation(16)
        k = int(order[episode % 16])
        return 90101+k//2, k % 2
    j = episode
    heldout, mode = j % 2, (j//2) % 2
    maps = MAP_IDS[8:] if heldout else MAP_IDS[:8]
    return maps[(j//4) % len(maps)], mode


class World:
    def __init__(self, bank, seed, phase, episode):
        self.map_id, self.mode = scenario(seed, phase, episode)
        data = bank.maps[self.map_id]
        self.roads, self.index = data['roads'], data['index']
        self.coords, self.neighbor = data['coords'], data['neighbor']
        self.distances = data['distances']
        rng = rng_for(seed, phase, episode, 'environment')
        source_indices = rng.choice(len(self.coords), 13, replace=False)
        self.hero = self.coords[source_indices[0]].copy()
        self.treasures = self.coords[source_indices[1:11]].copy()
        self.treasure_alive = np.ones(10, bool)
        self.buffs = self.coords[source_indices[11:13]].copy()
        self.buff_ready = np.zeros(2, np.int16)
        delta = np.max(np.abs(self.coords-self.hero), axis=1)
        candidates = np.flatnonzero(delta == 10)
        if not len(candidates):
            candidates = np.flatnonzero(delta >= 8)
        self.monsters = np.full((2, 2), -1, np.int16)
        self.monsters[0] = self.coords[int(rng.choice(candidates))]
        self.uniform = rng.random((256, 2, 2, 2))
        self.source_uniforms = 2048
        self.t = self.cooldown = self.buff_left = self.collected = self.buff_collected = 0
        self.trajectory = [self.hero.copy()]
        self.done = False

    def speed(self):
        return 2 if self.mode and self.t >= 160 else 1

    def caught(self):
        existing = self.monsters[:, 0] >= 0
        return bool(np.any(np.max(np.abs(self.monsters[existing]-self.hero), axis=1) <= 1))

    def _collect(self, p):
        take = self.treasure_alive & np.all(self.treasures == p, axis=1)
        n = int(take.sum())
        self.treasure_alive[take] = False
        self.collected += n
        b = np.flatnonzero(np.all(self.buffs == p, axis=1) & (self.buff_ready <= self.t))
        if len(b):
            self.buff_left = 50
            self.buff_ready[b] = self.t+100
            self.buff_collected += len(b)
        return n, len(b)

    def step(self, action):
        assert not self.done and 0 <= action < 16
        assert action < 8 or self.cooldown == 0
        x, z = map(int, self.hero)
        dx, dz = map(int, DIR[action % 8])
        path = []
        if action >= 8:
            distance = 8 if dx and dz else 10
            for k in range(distance, 0, -1):
                xx, zz = x+k*dx, z+k*dz
                if 0 <= xx < 64 and 0 <= zz < 64 and self.roads[zz, xx]:
                    path = [(x+j*dx, z+j*dz) for j in range(1, k+1)]
                    self.hero[:] = xx, zz
                    break
            self.cooldown = 32
        else:
            for _ in range(2 if self.buff_left else 1):
                xx, zz = map(int, self.hero)
                if not legal_neighbor(self.roads, xx, zz, action):
                    break
                self.hero += DIR[action]
                path.append(tuple(self.hero))
        pickups = buffs = 0
        for p in path:
            n, b = self._collect(p)
            pickups += n
            buffs += b
        captured = self.caught()
        # The t=96 spawn uses the actual position at the t=86 checkpoint.
        if self.mode and self.t == 96:
            self.monsters[1] = self.trajectory[self.t-10]
            captured = captured or self.caught()
        target = int(self.index[tuple(self.hero[::-1])])
        if not captured:
            for m in range(2):
                if self.monsters[m, 0] < 0:
                    continue
                for sub in range(self.speed()):
                    p = int(self.index[tuple(self.monsters[m, ::-1])])
                    neighbors = self.neighbor[p]
                    valid = neighbors[neighbors >= 0]
                    if len(valid):
                        u, v = self.uniform[self.t, m, sub]
                        if u < .9:
                            d = self.distances[valid, target]
                            reducing = valid[d < self.distances[p, target]]
                            if len(reducing):
                                md = self.distances[reducing, target]
                                valid = reducing[md == md.min()]
                            else:
                                valid = np.empty(0, np.int16)
                        if len(valid):
                            self.monsters[m] = self.coords[valid[min(int(v*len(valid)), len(valid)-1)]]
                    if self.caught():
                        captured = True
                        break
                if captured:
                    break
        self.t += 1
        self.cooldown = max(0, self.cooldown-1)
        self.buff_left = max(0, self.buff_left-1)
        self.trajectory.append(self.hero.copy())
        completed = self.t == 256 and not captured
        self.done = captured or completed
        return self.observe(), Fact(1, pickups, captured, completed, buffs)

    def observe(self):
        x, z = map(int, self.hero)
        image = np.zeros((5, 21, 21), np.uint8)
        x0, x1, z0, z1 = max(0, x-10), min(64, x+11), max(0, z-10), min(64, z+11)
        image[0, z0-z+10:z1-z+10, x0-x+10:x1-x+10] = self.roads[z0:z1, x0:x1]
        for channel, points, flags in [(1, self.treasures, self.treasure_alive),
                                       (2, self.buffs, self.buff_ready <= self.t)]:
            for (xx, zz), active in zip(points, flags):
                if active and abs(int(xx)-x) <= 10 and abs(int(zz)-z) <= 10:
                    image[channel, zz-z+10, xx-x+10] = 1
        scalar = np.zeros(32, np.float32)
        scalar[:6] = x/63, z/63, self.t/256, self.cooldown/32, self.buff_left/50, (2 if self.buff_left else 1)/2
        visible = np.zeros(2, bool)
        public_positions = np.full((2, 2), -1, np.int16)
        for m, (xx, zz) in enumerate(self.monsters):
            if xx < 0:
                continue
            delta = np.array([int(xx)-x, int(zz)-z])
            visible[m] = bool(np.max(np.abs(delta)) <= 10)
            distance_bucket = min(5, int(np.linalg.norm(delta)//15))
            if visible[m]:
                public_positions[m] = xx, zz
                image[3+m, zz-z+10, xx-x+10] = 1
                relative = delta/10
            else:
                relative = np.sign(delta)*(distance_bucket+1)/6
            scalar[6+m*6:12+m*6] = [1, visible[m], relative[0], relative[1], self.speed()/2, distance_bucket/5]
        scalar[18:20] = self.collected/10, self.buff_collected/20
        for a, (dx, dz) in enumerate(DIR):
            scalar[20+a] = image[0, 10+dz, 10+dx]
        legal = np.ones(16, bool)
        legal[8:] = self.cooldown == 0
        return Observation(image, scalar, legal, (x, z), visible, public_positions, image[0].copy())

    def audit(self):
        return dict(map_id=self.map_id, mode=self.mode, t=self.t,
                    hero=self.hero.tolist(), monsters=self.monsters.tolist(),
                    treasures=self.collected, buff_collected=self.buff_collected,
                    cooldown=self.cooldown, buff_left=self.buff_left,
                    score=1.5*self.t+100*self.collected)
