r"""A76 §63 — the B1 contract layer: status taxonomy, receipts, ledger, fingerprints.

Four statuses, frozen in A76 §63.3 and used here verbatim:

$$\{\texttt{APPLIED},\ \texttt{EVALUABLE\_NOOP},\
\texttt{NO\_VALID\_ALTERNATIVE},\ \texttt{PROTOCOL\_ERROR}\}$$

``APPLIED`` is **architecture-neutral**: the transaction committed and persistent
learner state changed at at least one credited store address. It is never decided by
scalar accounting — a patch store is value-free, so ``N_scalar`` is 0 for every patch
law and could not decide anything.

``PROTOCOL_ERROR`` is **not** a scientific no-write outcome: it is a fail-stop that
invalidates the run rather than being recorded as $\Delta W = 0$ for an arm.

The learner-state fingerprint is an explicit deterministic encoding, never Python's
``hash()`` and never dict iteration order.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from rfl_rebuild.learner.store import DecisionAddress

__all__ = [
    "APPLIED",
    "EVALUABLE_NOOP",
    "NO_VALID_ALTERNATIVE",
    "PROTOCOL_ERROR",
    "DecisionWriteReceipt",
    "ProtocolError",
    "UpdateLedger",
    "fingerprint",
]

APPLIED = "APPLIED"
EVALUABLE_NOOP = "EVALUABLE_NOOP"
NO_VALID_ALTERNATIVE = "NO_VALID_ALTERNATIVE"
PROTOCOL_ERROR = "PROTOCOL_ERROR"

STATUSES = (APPLIED, EVALUABLE_NOOP, NO_VALID_ALTERNATIVE, PROTOCOL_ERROR)


class ProtocolError(Exception):
    """A76 §63.3 ``PROTOCOL_ERROR``: an invariant failed; the run is invalidated.

    **Deliberately a separate hierarchy** from ``method.credit.ProtocolError`` (a
    typing violation) and from ``learner.store.StoreTransactionError`` (a substrate
    atomicity error). The same reasoning the kernel applies to
    ``LearnerContractViolation``: an old handler that catches a typing error must not
    silently swallow a benchmark-invalidating failure.

    It must never be turned into a normal result and scored by B2.
    """


def _canon_decision(overrides: Mapping) -> str:
    rows = []
    for addr, a in overrides.items():
        s = addr.state
        rows.append(f"D:{s.x},{s.y},{s.t},{s.kappa},{s.phi},{addr.z},{addr.m},{a}")
    return "\n".join(sorted(rows))


def _canon_process(overrides: Mapping) -> str:
    return "\n".join(sorted(f"P:{z},{v}" for z, v in overrides.items()))


def _canon_controller(overrides: Mapping) -> str:
    rows = []
    for site, a in overrides.items():
        s = site.state
        rows.append(f"X:{s.x},{s.y},{s.t},{s.kappa},{s.phi},{site.cmd},{a}")
    return "\n".join(sorted(rows))


def fingerprint(state) -> str:
    r"""$\text{SHA256}(\text{canon}(P_D^L) \Vert \text{canon}(C_P^L) \Vert
    \text{canon}(C_X^L))$ over lexicographically sorted, explicitly expanded rows.

    Sorted and explicit so the value cannot depend on dict iteration order, and
    SHA256 so it cannot depend on process salting. This is the ledger canary:

    $$\texttt{EVALUABLE\_NOOP} \Rightarrow fp_{\text{pre}} = fp_{\text{post}},
    \qquad
    \texttt{APPLIED} \Rightarrow fp_{\text{pre}} \neq fp_{\text{post}}$$
    """
    h = hashlib.sha256()
    h.update(_canon_decision(state.decision_overrides).encode("utf-8"))
    h.update(b"\x00")
    h.update(_canon_process(state.process_overrides).encode("utf-8"))
    h.update(b"\x00")
    h.update(_canon_controller(state.controller_overrides).encode("utf-8"))
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class DecisionWriteReceipt:
    """One addressed store context's outcome.

    Carries only what the substrate and the law can know. It deliberately holds **no**
    truth, no regime, no fire pattern and no scenario identity: the reporting layer
    joins those back on afterwards, so a metric cannot read them through a receipt.
    """

    address: DecisionAddress
    status: str
    store_changed: bool

    def canon(self) -> str:
        s = self.address.state
        return (f"{s.x},{s.y},{s.t},{s.kappa},{s.phi},{self.address.z},"
                f"{self.address.m}|{self.status}|{int(self.store_changed)}")


@dataclass(frozen=True, slots=True)
class UpdateLedger:
    r"""Per-address receipts plus the aggregate A75 §62.9 requires.

    For a **value-free** patch store the scalar accounting is defined to be zero and
    is explicitly marked inapplicable, so that "APPLIED but scalar delta = 0" cannot
    be misread as a no-op.
    """

    receipts: tuple[DecisionWriteReceipt, ...]
    fingerprint_pre: str
    fingerprint_post: str
    scalar_metrics_applicable: bool = False
    n_scalar: int = 0
    sum_abs_delta: float = 0.0
    max_abs_delta: float = 0.0

    @property
    def n_addressed(self) -> int:
        return len(self.receipts)

    @property
    def n_changed_addresses(self) -> int:
        return sum(1 for r in self.receipts if r.store_changed)

    @property
    def status_counts(self) -> Mapping[str, int]:
        counts = {s: 0 for s in STATUSES}
        for r in self.receipts:
            counts[r.status] = counts.get(r.status, 0) + 1
        return MappingProxyType(counts)

    @property
    def store_changed(self) -> bool:
        return self.fingerprint_pre != self.fingerprint_post

    def canonical(self) -> str:
        """Order-independent serialization: receipts are sorted by address."""
        payload = {
            "receipts": [r.canon() for r in
                         sorted(self.receipts, key=lambda r: r.canon())],
            "fingerprint_pre": self.fingerprint_pre,
            "fingerprint_post": self.fingerprint_post,
            "scalar_metrics_applicable": self.scalar_metrics_applicable,
            "n_scalar": self.n_scalar,
            "sum_abs_delta": self.sum_abs_delta,
            "max_abs_delta": self.max_abs_delta,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def check_fingerprint_invariants(self) -> None:
        r"""The ledger canary, enforced rather than merely reported."""
        if not self.store_changed:
            bad = [r.canon() for r in self.receipts if r.status == APPLIED]
            if bad:
                raise ProtocolError(
                    f"APPLIED receipt(s) but the learner-state fingerprint did not "
                    f"change: {bad}")
        else:
            for r in self.receipts:
                if r.status != APPLIED and r.store_changed:
                    raise ProtocolError(
                        f"receipt {r.canon()} reports {r.status} yet its address "
                        "changed")
