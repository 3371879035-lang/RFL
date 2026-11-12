r"""$F_0$ §3's balanced master evaluation ordering, as code.

$$\boxed{\forall N \in \mathcal C_{N_{\text{eval}}}:\ \text{prefix}(N) \text{ covers every } \kappa,\
\phi, \texttt{error\_flag}, z_{\text{base}} \text{ and all } 60 \text{ cause ranks}}$$

The order is built to cover the strata at *every* prefix, which A88's canonical lexicographic enumeration
does not: with $\kappa$ leading, all of its first $1024$ units have $\kappa = 0$. The construction is

* the $96$ cells of $(\kappa, \phi, \texttt{error\_flag}, z_{\text{base}})$ visited round-robin;
* writing $n = 96q + r$ with $0 \le r < 96$, unit $n + 1$ is the $r$-th cell (0-based, ascending) carrying
  $\texttt{cause\_rank} = (7q + 37r) \bmod 60$ --- both strides coprime with $60$.

It is a **bijection** on $n = 0, \ldots, 5759$, and the prefix-coverage claim above was verified before it
was frozen (A88 §76.2's canonical order remains what `scene_domain()` returns; this is the *evaluation*
order, and the two are deliberately different objects).
"""

from __future__ import annotations

import hashlib
import itertools

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.unaffected import EvaluationScene, PHASE_DOMAIN, TAPE_CAUSE_SUPPORT, TAPE_ERROR_SUPPORT
from rfl_rebuild.env.kernel import option_ids

__all__ = ["CELL_STRIDE", "CAUSE_STRIDE", "balanced_units", "prefix", "prefix_digest", "coverage"]

#: The two strides. Both are coprime with 60, which is what makes the cause rank rotate through its whole
#: support and the 96 cells cover every residue.
CAUSE_STRIDE = 7
CELL_STRIDE = 37

_KAPPA = (0, 1)


def balanced_units() -> tuple:
    r"""The whole order, as `EvaluationScene` units, indexed $u_1, \ldots, u_{5760}$ in $F_0$'s notation."""
    cells = tuple(itertools.product(_KAPPA, PHASE_DOMAIN, TAPE_ERROR_SUPPORT, option_ids()))
    causes = len(TAPE_CAUSE_SUPPORT)
    out = []
    for n in range(len(cells) * causes):
        kappa, phase, error, base = cells[n % len(cells)]
        q, r = divmod(n, len(cells))
        cause = (CAUSE_STRIDE * q + CELL_STRIDE * r) % causes
        out.append(EvaluationScene(kappa=kappa, phase=phase, error_flag=error, cause_rank=cause,
                                   base_option=base))
    if len(set(out)) != len(out):                              # pragma: no cover - construction guard
        raise ProtocolError("the balanced ordering is not injective; the strides must be coprime with 60")
    return tuple(out)


def prefix(n: int, *, units=None) -> tuple:
    r"""$\mathcal S_{\text{eval}}(n)$: the first $n$ units of the one master order."""
    units = balanced_units() if units is None else units
    if not 0 < n <= len(units):
        raise ProtocolError(f"a prefix of {n} units is outside 1..{len(units)}")
    return tuple(units[:n])


def prefix_digest(n: int, *, units=None) -> str:
    """A digest of the prefix's keys, so a re-ordering of either enumerator is visible."""
    return hashlib.sha256(repr(tuple(u.key for u in prefix(n, units=units))).encode("utf-8")).hexdigest()


def coverage(n: int, *, units=None) -> dict:
    """The prefix's stratum coverage counts --- what makes the balance claim checkable, not asserted."""
    chosen = prefix(n, units=units)
    return {
        "kappa": len({u.kappa for u in chosen}),
        "phase": len({u.phase for u in chosen}),
        "error_flag": len({u.error_flag for u in chosen}),
        "cause_rank": len({u.cause_rank for u in chosen}),
        "base_option": len({u.base_option for u in chosen}),
        "distinct": len(set(chosen)),
    }
