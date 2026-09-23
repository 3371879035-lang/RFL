r"""Construction-time size measurement for $F_0$ §3's artifact --- operational, no seed, writes nothing.

**Not** a gate, and not part of the frozen suite of §7: it exists so the sizes quoted in the $F_0$
construction notes are re-derivable rather than transcribed. It draws no seed and mounts no artifact --- the
learner is the healthy state and the solve is the frozen one --- so it cannot become development data.

$$\text{measured} \neq \text{acquired}$$

What it answers, for the frozen envelope ($\lvert \mathcal S_{\text{dev}}\rvert = 32$,
`ACQUISITION_CAP` $= 40$, $N_{\max} = 1024$):

* each architecture's production credited domain of A89 §77.4, and therefore the size of the *finished*
  per-$(A,\sigma,e,c,r)$ sufficient-statistic family;
* the incidence the artifact actually stores --- distinct sites consulted by the bank, and the
  (site, scene) pairs --- and therefore the size of the form §3 permits as the alternative;
* the cost of one $(\sigma,e)$ unit, which is what §8's bound has to contain.
"""

from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.unaffected import CHANNELS, REFINEMENTS, credited_domain, pre_update_traces, scene_domain
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference

BANK = 1024
DEV_SEEDS = 32
CAP = 40


def main() -> None:
    reference = reference_view_from(solve_reference())
    healthy = LearnerPersistentState()
    bank = prefix(BANK)

    start = time.perf_counter()
    bank_traces = pre_update_traces(learner=healthy, q_reference=reference, domain=bank)
    bank_s = time.perf_counter() - start
    start = time.perf_counter()
    full_traces = pre_update_traces(learner=healthy, q_reference=reference, domain=scene_domain())
    full_s = time.perf_counter() - start
    print(f"bank({BANK}) traces          {bank_s:8.3f} s")
    print(f"full-U2 traces             {full_s:8.3f} s")

    domains = {channel: credited_domain(channel, full_traces) for channel in CHANNELS}
    print("production credited domains (A89 §77.4): "
          + ", ".join(f"{channel} = {len(domains[channel])}" for channel in CHANNELS))

    pairs = 0
    print("\nbank incidence over the master bank:")
    for channel in CHANNELS:
        contacted, pair_count = set(), 0
        for scene in bank:
            consulted = bank_traces.consulted(channel, scene)
            pair_count += len(consulted)
            contacted.update(consulted)
        pairs += pair_count
        outside = len(contacted - set(domains[channel]))
        print(f"  {channel}: distinct sites {len(contacted):6d}, (site, scene) pairs {pair_count:7d}, "
              f"consulted sites outside the run's domain {outside}")
    print(f"  total per (sigma, e): {pairs}")

    runs = DEV_SEEDS * (CAP + 1)
    triples = sum(len(domains[channel]) for channel in CHANNELS) * len(REFINEMENTS) * runs
    print(f"\nfinished sufficient statistics, c over the production domain: {triples:,} triples")
    for channel in CHANNELS:
        print(f"  {channel}: {len(domains[channel]) * len(REFINEMENTS) * runs:,}")
    print(f"incidence form actually stored: {pairs * runs:,} pairs")
    print(f"\none (sigma, e) unit (full-U2 traces + incidence inversion): "
          f"{full_s:.3f} s -> development envelope {full_s * runs / 60:.1f} min")


if __name__ == "__main__":
    main()
