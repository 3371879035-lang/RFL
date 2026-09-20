r"""A80 §68.2 — the credited/store address domain, generalised by type.

The shared B1 layer used to assume every credited address was a `DecisionAddress`: the plan,
the receipt and its canonicalisation, and the slice's owner resolver all named that type. The
$X$ and $P$ paths need addresses that are not decision addresses ($\rho_X$ yields a site handle,
$\rho_P$ an integer), so the contract has to stop assuming one type — **without** becoming
`address: Any`.

$$\boxed{\text{the shared layer can CARRY per-architecture domains without absorbing them}}$$

The mechanism is an **addressed value**: the shared objects hold the address together with the
domain that admits it, and never interpret the payload themselves. Every question about an
address is a question to its domain:

| question | asked of |
|---|---|
| is this a legal **credited** address? | `domain.require_credited` |
| is this a legal **store** address? | `domain.require_store` |
| which credited address owns this store address? | `domain.owner` ($owner_\alpha$) |
| what is its canonical receipt form? | `domain.canonical` |

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

__all__ = ["AddressDomain", "CreditedAddress"]


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


@dataclass(frozen=True, slots=True)
class CreditedAddress:
    r"""A credited address **together with the domain that admits it**.

    The shared plan, receipt and locality layer holds these and never looks inside. Validation
    happens once, here, at construction — so a value that reaches a plan has already been
    admitted by its architecture's own predicate, and a stand-in cannot get in by exposing a
    matching attribute.

    $\texttt{CreditedAddress}(A, v)$ and $\texttt{CreditedAddress}(B, v)$ are **different
    addresses** even when $v$ is the same object, because a credited address is only meaningful
    relative to the architecture that credits it.
    """

    domain: AddressDomain
    value: Any

    def __post_init__(self) -> None:
        if not isinstance(self.domain, AddressDomain):
            raise ProtocolError(
                f"credited address domain is {self.domain!r}, not an AddressDomain; the domain "
                "is the architecture's own rules and cannot be a stand-in")
        self.domain.require_credited(self.value)

    @property
    def tag(self) -> str:
        return self.domain.tag

    def canonical(self) -> str:
        """The receipt's canonical form, byte-identical to the pre-refactor encoding."""
        return self.domain.canonical(self.value)

    def owner(self):
        """$owner_\\alpha$ of the *store* address that this credited address owns."""
        return self.domain.owner(self.value)

    def __repr__(self) -> str:                       # pragma: no cover - diagnostics
        return f"<credited {self.domain.tag} {self.value!r}>"
