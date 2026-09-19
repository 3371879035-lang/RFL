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


def _canon_q(overrides: Mapping) -> str:
    r"""$Q_D^L$'s canonical form: explicit rows, ``float.hex()`` values, sorted.

    ``float.hex()`` rather than ``repr``/``str``: it is exact and round-trippable, and it
    is the encoding A77 §65.4 froze. ``str`` and ``repr`` happen to agree for floats in
    CPython 3, so the choice is made on exactness rather than on a difference that does
    not exist — and it distinguishes the two zeros, which matters because an entry that
    is "changed" with a zero delta is what the ledger canary exists to exclude.
    """
    rows = []
    for addr, v in overrides.items():
        s = addr.state
        rows.append(f"Q:{s.x},{s.y},{s.t},{s.kappa},{s.phi},{addr.z},{addr.m},{addr.a}"
                    f"|{float(v).hex()}")
    return "\n".join(sorted(rows))


def fingerprint(state) -> str:
    r"""$\text{SHA256}(\text{canon}(P_D^L) \Vert \text{canon}(C_P^L) \Vert
    \text{canon}(C_X^L) \Vert \text{canon}(Q_D^L))$ over lexicographically sorted,
    explicitly expanded rows.

    Sorted and explicit so the value cannot depend on dict iteration order, and
    SHA256 so it cannot depend on process salting. This is the ledger canary:

    $$\texttt{EVALUABLE\_NOOP} \Rightarrow fp_{\text{pre}} = fp_{\text{post}},
    \qquad
    \texttt{APPLIED} \Rightarrow fp_{\text{pre}} \neq fp_{\text{post}}$$

    The fourth component arrived with the $Q$ store (A77 §65.4). It changes the digest
    string for every state, an *empty* component included, and no invariant: the ledger
    only ever compares $fp_{\text{pre}}$ with $fp_{\text{post}}$ inside one run, and no
    committed artifact records an absolute learner fingerprint. A77 §65.12 makes that
    encoding change the business of the step that needed the store, which is this one.
    """
    h = hashlib.sha256()
    h.update(_canon_decision(state.decision_overrides).encode("utf-8"))
    h.update(b"\x00")
    h.update(_canon_process(state.process_overrides).encode("utf-8"))
    h.update(b"\x00")
    h.update(_canon_controller(state.controller_overrides).encode("utf-8"))
    h.update(b"\x00")
    h.update(_canon_q(state.q_overrides).encode("utf-8"))
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
        r"""Per-receipt and aggregate invariants, enforced rather than reported.

        $$\boxed{r.\text{status} = \texttt{APPLIED} \iff r.\text{store\_changed}}$$

        checked for **every** receipt, and

        $$\boxed{fp_{\text{pre}} \neq fp_{\text{post}} \iff \exists r:
        r.\text{store\_changed}}$$

        as the aggregate. The first version branched on the **global** fingerprint
        first, so in a scene where A really changed and B was mislabelled
        ``APPLIED, store_changed=False``, the global test took the ``else`` branch and
        B's inconsistency was never looked at. A per-address error needs a per-address
        check.

        ``PROTOCOL_ERROR`` is a fail-stop, never a receipt status in a successful
        ledger, and an unknown status is rejected outright.
        """
        for r in self.receipts:
            if r.status not in (APPLIED, EVALUABLE_NOOP, NO_VALID_ALTERNATIVE):
                raise ProtocolError(
                    f"receipt {r.canon()} carries status {r.status!r}, which is not a "
                    "legal per-address outcome"
                    + (" (PROTOCOL_ERROR is a fail-stop, not a receipt status)"
                       if r.status == PROTOCOL_ERROR else ""))
            if (r.status == APPLIED) != r.store_changed:
                raise ProtocolError(
                    f"receipt {r.canon()} reports status {r.status} with "
                    f"store_changed={r.store_changed}; APPLIED must hold exactly when "
                    "the store at that address changed")

        any_changed = any(r.store_changed for r in self.receipts)
        if any_changed != self.store_changed:
            raise ProtocolError(
                "the learner-state fingerprint change and the per-address changes "
                f"disagree: fingerprint_changed={self.store_changed}, "
                f"any_address_changed={any_changed}")

        if self.scalar_metrics_applicable:
            self._check_scalar_invariants()

    def _check_scalar_invariants(self) -> None:
        r"""A77 §65.10, on a scalar slice.

        $$\boxed{N_{\text{scalar}} = 0 \iff \Sigma = 0 \iff fp_{\text{pre}} =
        fp_{\text{post}}}$$

        The equivalence holds because canonicalisation leaves every genuinely changed entry
        with $q_{\text{post}} \neq Q_D^\ast(e)$ (created), $q_{\text{pre}} \neq Q_D^\ast(e)$
        (deleted) or $q_{\text{pre}} \neq q_{\text{post}}$ (updated), so $\Delta(e) > 0$ in
        all three cases. **That is why the ledger is a canary for the canonicalisation
        rule**: if canonicalisation is ever bypassed, a changed entry with $\Delta = 0$
        appears, this fires, and the store's non-canonical state is caught here rather than
        silently entering a later delta comparison.

        These are checked only when the slice is scalar-valued — they are claims about a
        store with numbers in it, and on a value-free store the three fields are defined to
        be zero rather than measured.
        """
        n = self.n_scalar
        total = self.sum_abs_delta
        largest = self.max_abs_delta
        if min(total, largest) < 0.0:
            raise ProtocolError(
                f"a scalar magnitude is negative: sum={total!r}, max={largest!r}")
        if (n == 0) != (total == 0.0):
            raise ProtocolError(
                f"the scalar count and the summed delta disagree: n_scalar={n}, "
                f"sum_abs_delta={total!r}; with canonicalisation in force every changed "
                "entry has a positive delta, so these are equivalent (A77 §65.10)")
        if (total == 0.0) != (self.fingerprint_pre == self.fingerprint_post):
            raise ProtocolError(
                "the scalar accounting and the fingerprint disagree: "
                f"sum_abs_delta={total!r}, fingerprint_changed={self.store_changed}")
        if (n == 0) != (not self.store_changed):
            raise ProtocolError(
                f"n_scalar={n} but fingerprint_changed={self.store_changed}; the scalar "
                "count is the fingerprint canary made quantitative")
        if n < self.n_changed_addresses:
            raise ProtocolError(
                f"n_scalar={n} is smaller than n_changed_addresses="
                f"{self.n_changed_addresses}; every changed address changed at least one "
                "entry")
        if largest > total:
            raise ProtocolError(
                f"max_abs_delta={largest!r} exceeds sum_abs_delta={total!r}; the maximum "
                "over a set cannot exceed the sum of its magnitudes")
        if (largest > 0.0) != (total > 0.0):
            raise ProtocolError(
                f"max_abs_delta={largest!r} and sum_abs_delta={total!r} disagree about "
                "whether anything changed")
