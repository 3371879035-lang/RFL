r"""Is the controller channel a shortcut around the option contract?

`rollout` accepts ``controller: Mapping[ControllerSite, Action]`` and forwards it to
``step``, where it is read as

    site = ControllerSite(state, a_eff)
    u = controller[site]        # baseline controller, priority below fault and do

and ``u`` becomes ``a_realized`` (absent a plant fault). **``u`` is never checked
against the option's admissible set.** Only ``a_cmd`` is checked, in ``rollout``:

    allowed = option_actions(control.z, control, state)
    if a_cmd not in allowed: raise MalformedIntervention / OptionViolation

So a write into the controller channel can make the *realized* action leave
``A_z(m, s)`` without triggering MALFORMED. That matters for V0.3R because a
learner-owned persistent ``C_X^L`` would be injected through exactly that channel.

Two facts are measured here, and the first is itself a finding:

1. **The exact reference DP does not define a value for actions outside the
   option.** ``ReferenceSolution.q[(s, z, m)]`` is keyed only over
   ``option_actions(z, m, s)``; asking for an outside action raises ``KeyError``.
   The evaluator therefore cannot even score "what would leaving ``A_z`` be
   worth". That is recorded, not worked around.

2. A **routing proxy** for whether the contract costs anything: at how many
   ``(s, z, m)`` does some legal action outside ``A_z`` reach a cell strictly
   closer to the goal than every admissible action does? This is a proxy, not a
   value computation -- it asks whether the option ever forces a longer route, and
   deliberately does not claim what such a deviation would be worth.

Read-only: reads the kernel and the solver.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

INF = float("inf")


def main() -> int:
    sol = solve_reference()
    dist = K._bfs_distance_to_goal()
    n = 0
    n_equal_sets = 0
    n_outside_exists = 0
    n_outside_closer = 0
    by_z = Counter()
    worst = None
    q_key_error = None

    for (s, z, m) in list(sol.q):
        adm = K.option_actions(z, K.ControlState(z=z, m=m), s)
        legal = K.legal_actions(s)
        if not adm:
            continue
        n += 1
        outside = [a for a in legal if a not in adm]
        if not outside:
            n_equal_sets += 1
            continue
        n_outside_exists += 1

        best_adm = min(dist.get(K._enter(a, s), INF) for a in adm)
        best_out = min(dist.get(K._enter(a, s), INF) for a in outside)
        if best_out < best_adm:
            n_outside_closer += 1
            by_z[z] += 1
            if worst is None or (best_adm - best_out) > worst[0]:
                worst = (best_adm - best_out, s, z, m, best_adm, best_out)

    # fact 1: does the exact solution define values outside the option?
    probe = None
    for (s, z, m) in list(sol.q):
        adm = K.option_actions(z, K.ControlState(z=z, m=m), s)
        legal = K.legal_actions(s)
        out = [a for a in legal if a not in adm]
        if out:
            probe = (s, z, m, out[0])
            break
    if probe is not None:
        s, z, m, a = probe
        try:
            sol.q_value(s, z, m, a)
            q_key_error = False
        except KeyError:
            q_key_error = True

    checks = {
        "dp_was_readable": n > 0,
        "no_legal_action_outside_the_option_reaches_a_closer_cell":
            n_outside_closer == 0,
    }
    ok = all(checks.values())

    print(f"controller-channel shortcut probe over {n:,} (s, z, m) entries\n")
    print(f"  entries with a non-empty admissible set      : {n:,}")
    print(f"  entries where A_z(m,s) == all legal actions  : {n_equal_sets:,}")
    print(f"  entries with a legal action OUTSIDE A_z      : {n_outside_exists:,}")
    print(f"  ...where an outside action reaches a STRICTLY")
    print(f"     closer cell than every admissible action  : {n_outside_closer:,}")
    if by_z:
        print(f"  closer-outside entries by option             : "
              f"{dict(sorted(by_z.items()))}")
    if worst:
        d, s, z, m, ba, bo = worst
        print(f"  worst: s={s} z={z} m={m} adm_dist={ba} outside_dist={bo} "
              f"closer_by={d}")
    print(f"\n  exact DP defines a value for an outside action: "
          f"{'no (KeyError) -- the evaluator cannot score the deviation' if q_key_error else 'yes'}")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    verdict = ("no routing advantage found: at every (s,z,m) the option's admissible "
               "set already contains an action reaching a closest cell"
               if n_outside_closer == 0 else
               "ROUTING ADVANTAGE EXISTS: at some (s,z,m) a legal action outside "
               "A_z reaches a strictly closer cell, and the controller channel "
               "would let a learner write it in unchecked")
    print(f"\ncontroller channel: {verdict}")

    out = ROOT / "experiments" / "v02r" / "controller_channel_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "n_entries_with_admissible_set": n,
        "n_entries_admissible_equals_legal": n_equal_sets,
        "n_entries_with_outside_legal_action": n_outside_exists,
        "n_entries_outside_reaches_closer_cell": n_outside_closer,
        "closer_by_option": dict(by_z),
        "dp_defines_outside_action_value": (not q_key_error) if q_key_error is not None else None,
        "checks": checks,
        "status": "PASS" if ok else "FAIL",
        "verdict": verdict,
        "why_it_matters": ("rollout checks a_cmd against option_actions but never "
                           "checks the controller channel's output u, which becomes "
                           "a_realized. A V0.3R learner-owned persistent C_X^L would "
                           "be injected through exactly that channel"),
        "proxy_caveat": ("the closer-cell test is a routing proxy, not a value "
                         "computation: it asks whether the option ever forces a "
                         "longer route, and does not claim what a deviation would "
                         "be worth. It is used because the exact DP cannot score an "
                         "outside action at all"),
        "note": ("no caller in the repository passes a non-None controller mapping "
                 "today; the channel is a latent extension point"),
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
