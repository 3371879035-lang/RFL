"""A62 — the global query registry, and its frozen canonical order.

``Q_global`` is fixed before any scene is drawn and is identical for every true
world. It is built from the environment/action/query grammar ONLY: it may not
read the factual trajectory, the feedback, the rows block, or the true world. A
query that only one factual scene could have generated is a query chosen by the
answer, and that is what let the dev_v1 leak back in through a different door.

The order is an EXPLICIT sort key rather than ``repr`` or set iteration, so query
order cannot pick up Python implementation details and Test 8 can compare traces
byte-for-byte across processes:

    proc_audit                          -> (0,)
    audit(t)                            -> (1, t)
    process(z)                          -> (2, z)
    decision(t, a)                      -> (3, t, a)
    execution(x, y, t, kappa, phi, cmd) -> (4, x, y, t, kappa, phi, cmd)
"""

from __future__ import annotations

from typing import Iterable, Sequence

KINDS = ("proc_audit", "audit", "process", "decision", "execution")
_KIND_RANK = {k: i for i, k in enumerate(KINDS)}


def proc_audit() -> tuple:
    return ("proc_audit",)


def audit(t: int) -> tuple:
    return ("audit", int(t))


def process(z: int) -> tuple:
    return ("process", int(z))


def decision(t: int, a: int) -> tuple:
    return ("decision", int(t), int(a))


def execution(x: int, y: int, t: int, kappa: int, phi: int, cmd: int) -> tuple:
    return ("execution", int(x), int(y), int(t), int(kappa), int(phi), int(cmd))


def sort_key(q: tuple) -> tuple:
    """Canonical order. Raises on an unknown kind rather than guessing a rank."""
    k = q[0]
    if k == "proc_audit":
        if len(q) != 1:
            raise ValueError(f"malformed proc_audit spec: {q!r}")
        return (0,)
    if k == "audit":
        if len(q) != 2:
            raise ValueError(f"malformed audit spec: {q!r}")
        return (1, q[1])
    if k == "process":
        if len(q) != 2:
            raise ValueError(f"malformed process spec: {q!r}")
        return (2, q[1])
    if k == "decision":
        if len(q) != 3:
            raise ValueError(f"malformed decision spec: {q!r}")
        return (3, q[1], q[2])
    if k == "execution":
        if len(q) != 7:
            raise ValueError(f"malformed execution spec: {q!r}")
        return (4, q[1], q[2], q[3], q[4], q[5], q[6])
    raise ValueError(f"unknown query kind {k!r}")


def build_registry(*, horizon: int, options: Sequence[int], cells: Iterable,
                   kappas: Sequence[int], phases: Sequence[int],
                   n_actions: int) -> tuple:
    """The static universe. Grammar only -- no world, no scene, no feedback.

    ``cells`` is the geometry of the grid, not the cells any episode visited.
    """
    out = [proc_audit()]
    for t in range(horizon):
        out.append(audit(t))
    for z in options:
        out.append(process(z))
    for t in range(horizon):
        for a in range(n_actions):
            out.append(decision(t, a))
    for (x, y) in sorted(cells):
        for t in range(horizon):
            for kappa in kappas:
                for phi in phases:
                    for cmd in range(n_actions):
                        out.append(execution(x, y, t, kappa, phi, cmd))
    return tuple(sorted(out, key=sort_key))


def canonical_trace(registry: Sequence[tuple], chosen: Sequence[int]) -> tuple:
    """A trace as registry INDICES, so two runs compare byte-for-byte."""
    return tuple(int(i) for i in chosen)


def first_safe(registry: Sequence[tuple], safe) -> int | None:
    """Streaming blind policy: the first safe query in canonical order.

    Deliberately does NOT materialise ``candidate_queries()``. Under the global
    prior a full tuple would evaluate legality across a million worlds for the
    entire registry; this stops at the first hit.
    """
    for i, q in enumerate(registry):
        if safe(q):
            return i
    return None
