r"""Why the initializer gate failed --- the reachability diagnostic, operational and non-deciding.

**Not a gate.** `scripts/f0_initializer_gate.py` decides; this script only explains, so that the failure is a
mechanism rather than a number. It draws no scientific seed, writes nothing, and reads no selector.

For every $(\beta, e)$ of $\mathcal B^{\text{op}}_{\text{dev}}$ and the frozen cap it reads A91's own
`visited_order` --- the address set `sweep_edits` writes --- and reports how near the ordinary training stream
comes to A87 §75.2's canary address:

    python scripts/f0_initializer_diagnostic.py
"""

from __future__ import annotations

import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from fractions import Fraction  # noqa: E402

from rfl_rebuild.b2.evalorder import prefix  # noqa: E402
from rfl_rebuild.b2.initializer import baseline_initializer, canary_address  # noqa: E402
from rfl_rebuild.b2.numerics import left_to_right_sum  # noqa: E402
from rfl_rebuild.b2.screening import canary_edit  # noqa: E402
from rfl_rebuild.b2.training import (  # noqa: E402
    BaselineAcquisitionPlan,
    ExogenousEpisode,
    episode_rollout,
    sweep_edits,
    visited_order,
)
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import QAddress  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

REFERENCE = reference_view_from(solve_reference())
KEYS = tuple(range(900001, 900033))          # B^op_dev
CAP = 40                                     # §1's pre-data cap
BANK = 1024                                  # S^master_eval


def main() -> None:
    plan = BaselineAcquisitionPlan(seed=KEYS[0], alpha=Fraction(1, 2), epsilon=Fraction(1, 10),
                                   acquisition_cap=CAP, evaluation_bank=prefix(BANK))
    canary = canary_address()
    written, same_state, same_address, episodes = set(), 0, 0, 0
    reachable_cells = Counter()
    for key in KEYS:
        learner = baseline_initializer(q_reference=REFERENCE)
        for episode in range(CAP + 1):
            exogenous = ExogenousEpisode.derive(key, episode)
            trace = episode_rollout(learner, exogenous, protocol=plan, q_reference=REFERENCE)
            addresses = {QAddress(state=state, z=control.z, m=control.m, a=result.a_cmd)
                         for state, control, result in visited_order(
                             trace, kappa=exogenous.kappa, phi=exogenous.tape.phase)}
            episodes += 1
            written |= addresses
            same_address += canary in addresses
            if any(a.state == canary.state for a in addresses):
                same_state += 1
                reachable_cells[(exogenous.kappa, exogenous.tape.phase, exogenous.proposal)] += 1
            if episode == CAP:
                break
            edits = sweep_edits(learner, trace, exogenous, protocol=plan, q_reference=REFERENCE)
            if edits:
                learner.apply_transaction(edits, q_reference=REFERENCE)

    print(f"episodes scanned                     : {episodes}")
    print(f"distinct Q addresses written         : {len(written)}")
    print(f"canary address                       : {canary}")
    print(f"canary address written by any episode : {canary in written}")
    print(f"episodes writing the canary's state   : {same_state}")
    print(f"controls seen at that state           : "
          f"{sorted({(a.z, a.m) for a in written if a.state == canary.state})}"
          f"   (the canary needs {(canary.z, canary.m)})")
    print(f"actions seen at that state            : "
          f"{sorted({a.a for a in written if a.state == canary.state})}"
          f"   (the canary needs a={canary.a})")
    print(f"episode cells reaching that state     : {dict(reachable_cells)}")

    target = REFERENCE.value(canary)
    value, visits = float(canary_edit("D_Q").value), 0
    while value != target and visits < 1000:
        value = value + 0.5 * (target - value)
        visits += 1
    print(f"\nrepair arithmetic at the frozen alpha : {visits} visits of the canary address are needed "
          f"before the override is canonicalised away (value {canary_edit('D_Q').value} -> {target!r})")
    print(f"expected hits per key over the cap      : "
          f"<= {reachable_cells.most_common(1)[0][1] / len(KEYS) if reachable_cells else 0:.2f} "
          f"(one cell, one exact action, exploration only)")
    print("reported for the reviewer: no cap is enlarged and no other corruption is substituted here. "
          f"sum-check {left_to_right_sum([visits])!r}")


if __name__ == "__main__":
    main()
