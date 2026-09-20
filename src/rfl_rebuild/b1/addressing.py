r"""A80 §68.2 — the credited/store address domain, generalised by type.

The shared B1 layer used to assume every credited address was a `DecisionAddress`: the plan,
the receipt and its canonicalisation, and the slice's owner resolver all named that type. The
$X$ and $P$ paths need addresses that are not decision addresses ($\rho_X$ yields a site handle,
$\rho_P$ an integer), so the contract has to stop assuming one type — **without** becoming
`address: Any`.

$$\boxed{\text{the shared layer can CARRY per-architecture domains without absorbing them}}$$

The mechanism is a **domain object the slice owns**: the shared layer keeps the raw address and
asks the architecture's domain every question about it, at the boundary, before any arm plans.
An earlier revision of this step wrapped every credited address in an addressed-value type; it
satisfied the same contract while churning every receipt comparison and hand-built plan in the
evidence suite for no extra strength, and it was replaced by boundary validation. Its type is
gone rather than kept beside this one, so the source describes a single contract.

There is deliberately **no shared ``is_an_address`` predicate**. A generic membership test is
exactly the duck typing this step forbids: it would let one architecture's addresses satisfy
another's slice, which is the property §68.2 requires to survive.

**Domain identity is the tag**, and the tag is on the *domain*, not in the ledger: A77 §65.12
freezes that the tier lives in the arm descriptor rather than in the canonical ledger, and moving
anything into that schema is a versioned change of its own. So the canonical receipt keeps its
existing bytes (§68.2's injectivity requirement is per domain), while distinctness between
architectures is carried by the domain tag and checked at the slice boundary.

**Injectivity is required, determinism is not enough:**

$$\boxed{canon_\alpha(x) = canon_\alpha(y) \iff x = y \quad \text{on the legal domain}}$$

An $X$ canonical form that omitted $a^{cmd}$ would give two distinct credited sites one receipt
identity. This project has already paid for that omission once, when the legacy controller site
left out a key address component, so the requirement is stated rather than rediscovered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from rfl_rebuild.b1.errors import ProtocolError

__all__ = ["AddressDomain"]


@dataclass(frozen=True)
class AddressDomain:
    r"""One architecture's address rules.

    A struct of the four questions above, supplied by the architecture. Equality and hashing are
    by ``tag`` alone: two constructions of the same architecture's domain are the same domain,
    which is what lets credited addresses be compared and deduplicated, while a *different*
    architecture's domain never compares equal — so a slice can refuse an address that belongs
    to another one.
    """

    tag: str
    require_credited: Callable[[Any], None] = field(compare=False, repr=False)
    require_store: Callable[[Any], None] = field(compare=False, repr=False)
    owner: Callable[[Any], Any] = field(compare=False, repr=False)
    canonical: Callable[[Any], str] = field(compare=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.tag, str) or not self.tag:
            raise ProtocolError("an address domain needs a non-empty tag")
        for name in ("require_credited", "require_store", "owner", "canonical"):
            if not callable(getattr(self, name)):
                raise ProtocolError(
                    f"address domain {self.tag!r}: {name} must be callable; a domain is the "
                    "architecture's own rules, not a name")
