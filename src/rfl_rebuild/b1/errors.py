r"""The B1 layer's failure type, kept below everything that raises it.

A80 §68.2 put the address domain in its own module, and the domain raises
:class:`ProtocolError` while the receipt carries a credited address — so the type had to stop
living in the same module as the receipt, or the two would import each other. `contract.py`
re-exports it, so every existing ``from rfl_rebuild.b1.contract import ProtocolError`` keeps
working: this is a module boundary, not a contract change.
"""

from __future__ import annotations

__all__ = ["ProtocolError"]


class ProtocolError(Exception):
    """A76 §63.3 ``PROTOCOL_ERROR``: an invariant failed; the run is invalidated.

    **Deliberately a separate hierarchy** from ``method.credit.ProtocolError`` (a
    typing violation) and from ``learner.store.StoreTransactionError`` (a substrate
    atomicity error). The same reasoning the kernel applies to
    ``LearnerContractViolation``: an old handler that catches a typing error must not
    silently swallow a benchmark-invalidating failure.

    It must never be turned into a normal result and scored by B2.
    """


