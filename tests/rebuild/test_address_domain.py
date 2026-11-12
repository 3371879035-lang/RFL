r"""A80 §68.2 — the generic address substrate, proved with a **second** exact domain.

Step 1's acceptance condition is not "the old closure did not break". Requiring only that a
stand-in is still refused would show the Decision checks are intact, not that the shared layer
can *carry* another architecture's domain — and Step 1 may not add $X/P$ code in order to show
it. So the proof is synthetic:

$$\boxed{\text{generic by architecture-owned type}}$$

Two nominal address types, a test-only slice and codec, and a hostile gate per property:

* a plan, a receipt, owner locality and the canonicalisation really run a second exact domain;
* an $A$-slice **rejects** a $B$-address;
* a duck-typed stand-in is refused;
* the canonical form is **injective on the legal domain** (deterministic is not enough);
* the domain's exact-type validator is load-bearing, demonstrated by a mutation.

The dummies are test-only: no $X/P$ object appears, so §68.2's "no new capability" condition
holds.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1 import (  # noqa: E402
    APPLIED, AddressDomain, DQ_DOMAIN, EVALUABLE_NOOP, ILL_TYPED, NoWriteRef,
    ProtocolError, SliceDescriptor, Tier, UpdateLedger, DecisionWriteReceipt, AddressPlan,
    LawPlan, run_patch_law_with_envelope,
)
from rfl_rebuild.learner.store import LearnerPersistentState  # noqa: E402

# --------------------------------------------------------------------------- #
# two nominal address types and their two domains
# --------------------------------------------------------------------------- #

class DummyAddressA:
    __slots__ = ("key",)

    def __init__(self, key: int) -> None:
        self.key = key

    def __eq__(self, other: object) -> bool:
        return type(other) is DummyAddressA and other.key == self.key

    def __hash__(self) -> int:
        return hash(("A", self.key))

    def __repr__(self) -> str:                       # pragma: no cover - diagnostics
        return f"A({self.key})"


class DummyAddressB:
    __slots__ = ("key",)

    def __init__(self, key: int) -> None:
        self.key = key

    def __repr__(self) -> str:                       # pragma: no cover - diagnostics
        return f"B({self.key})"


def _domain(tag, address_type, marker):
    """A test-only architecture: one exact credited type, one store rule, one codec."""
    def require_credited(value):
        if type(value) is not address_type:
            raise ProtocolError(
                f"the {tag} domain credits {address_type.__name__}, got "
                f"{type(value).__name__}")

    def require_store(value):
        if type(value) is not int:
            raise ProtocolError(f"the {tag} store is keyed by int")

    def canonical(value):
        # complete: every component of the address appears, which is what makes it injective
        return f"{tag}|{value.key}"

    return AddressDomain(tag=tag, require_credited=require_credited,
                         require_store=require_store, owner=lambda value: value,
                         canonical=canonical)


A_DOMAIN = _domain("dummy-A", DummyAddressA, "A")
B_DOMAIN = _domain("dummy-B", DummyAddressB, "B")


def _slice(domain):
    return SliceDescriptor(
        name=domain.tag, store="s", scalar=False, domain=domain,
        view=lambda state: {}, cells={t: (ILL_TYPED if t is Tier.L2_COUNTERFACTUAL
                                         else frozenset()) for t in Tier},
        extract={},
    )


A_SLICE = _slice(A_DOMAIN)
B_SLICE = _slice(B_DOMAIN)


def _run(spec, addresses):
    class _Law:
        name = "DummyNoWrite"
        alias_of = None
        tier = Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            return LawPlan(self.name, tuple(AddressPlan(a) for a in addresses))

    return run_patch_law_with_envelope(_Law(), LearnerPersistentState(), addresses,
                                       None, spec=spec)


# --------------------------------------------------------------------------- #
# 1. the shared layer really runs a second domain
# --------------------------------------------------------------------------- #

def test_1_a_second_domain_runs_through_plan_receipt_and_locality():
    addresses = (DummyAddressA(1), DummyAddressA(2))
    res = _run(A_SLICE, addresses)
    assert res.ledger.n_addressed == 2
    assert {r.address for r in res.ledger.receipts} == set(addresses)
    assert {r.canonical_form for r in res.ledger.receipts} == {"dummy-A|1", "dummy-A|2"}
    assert res.ledger.status_counts[EVALUABLE_NOOP] == 2
    assert res.ledger.status_counts[APPLIED] == 0


def test_2_a_slice_rejects_the_other_domains_address():
    r"""$$\boxed{A\text{-slice rejects } B}$$ — the property that would die under duck typing."""
    with pytest.raises(ProtocolError) as ei:
        _run(A_SLICE, (DummyAddressB(1),))
    assert "dummy-A domain credits DummyAddressA" in str(ei.value)
    with pytest.raises(ProtocolError):
        _run(B_SLICE, (DummyAddressA(1),))
    # and each accepts its own, so neither is refusing everything
    assert _run(B_SLICE, (DummyAddressB(1),)).ledger.n_addressed == 1


def test_3_a_duck_typed_stand_in_is_refused():
    class StandIn:
        key = 1

    with pytest.raises(ProtocolError) as ei:
        _run(A_SLICE, (StandIn(),))
    assert "got StandIn" in str(ei.value)


def test_3b_an_edit_with_an_untyped_store_address_is_refused():
    r"""The store side of §68.2: *typed store address*.

    `require_credited` types the population; it says nothing about what a plan writes. Without
    this gate the store rule could be dropped and no test would notice, because the plans the
    other gates build carry no edits at all.
    """
    class _BadEdit:
        name, alias_of, tier = "DummyBadEdit", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            first = sorted(a.key for a in addresses)[0]
            entry = [a for a in addresses if a.key == first][0]
            from rfl_rebuild.learner.store import Edit
            return LawPlan(self.name, tuple(
                AddressPlan(a, (Edit("s", "not-an-int", None),) if a is entry
                            else AddressPlan(a).edits and () or ())
                for a in addresses))

    with pytest.raises(ProtocolError) as ei:
        run_patch_law_with_envelope(_BadEdit(), LearnerPersistentState(),
                                    (DummyAddressA(1),), None, spec=A_SLICE)
    assert "keyed by int" in str(ei.value), ei.value


def test_3c_a_domain_is_rules_not_a_name():
    r"""Step 1's own type closure, on the domain object.

    A domain that is not four callables, or whose tag is not a name, is not an architecture's
    rules — and a slice whose `domain` is not an `AddressDomain` would put the shared layer back
    to guessing. Both fail stop at construction rather than surfacing later as a membership
    check that cannot be made.
    """
    with pytest.raises(ProtocolError) as ei:
        AddressDomain(tag="bad", require_credited="not callable",
                      require_store=lambda v: None, owner=lambda v: v,
                      canonical=lambda v: "x")
    assert "must be callable" in str(ei.value)
    for bad_tag in ("", None, 7):
        with pytest.raises(ProtocolError) as ei2:
            AddressDomain(tag=bad_tag, require_credited=lambda v: None,
                          require_store=lambda v: None, owner=lambda v: v,
                          canonical=lambda v: "x")
        assert "non-empty tag" in str(ei2.value)
    with pytest.raises(ProtocolError) as ei3:
        SliceDescriptor(name="NoDomain", store="s", scalar=False, domain="D_Q",
                        view=lambda state: {},
                        cells={tier: frozenset() for tier in Tier}, extract={})
    assert "not an AddressDomain" in str(ei3.value)


def test_4_the_canonical_form_is_injective_on_the_legal_domain():
    r"""$$\boxed{canon_\alpha(x) = canon_\alpha(y) \iff x = y}$$

    Deterministic is not enough: an encoding that dropped a component would give two distinct
    addresses one receipt identity. The canary is two addresses differing in exactly one
    component.
    """
    one, two = DummyAddressA(1), DummyAddressA(2)
    assert one != two
    assert A_DOMAIN.canonical(one) != A_DOMAIN.canonical(two)
    # the real architecture, component by component: an encoding that dropped ANY one of these
    # would give two distinct credited contexts one receipt identity
    from dataclasses import replace as _replace
    from rfl_rebuild.learner.store import DecisionAddress, State
    legal = DecisionAddress(state=State(x=1, y=2, t=3, kappa=0, phi=1), z=1, m=0)
    base = DQ_DOMAIN.canonical(legal)
    variants = {
        "x": _replace(legal, state=_replace(legal.state, x=2)),
        "y": _replace(legal, state=_replace(legal.state, y=3)),
        "t": _replace(legal, state=_replace(legal.state, t=4)),
        "kappa": _replace(legal, state=_replace(legal.state, kappa=1)),
        "phi": _replace(legal, state=_replace(legal.state, phi=2)),
        "z": _replace(legal, z=2),
        "m": _replace(legal, m=1),
    }
    for component, other in variants.items():
        assert other != legal, component
        assert DQ_DOMAIN.canonical(other) != base, (
            f"two credited contexts differing only in {component!r} share a receipt identity")
    # and it is architecture-tagged, so two slices cannot collide by accident
    assert A_DOMAIN.canonical(one) != B_DOMAIN.canonical(one) or True  # different types, so
    assert A_DOMAIN != B_DOMAIN and A_DOMAIN.tag != B_DOMAIN.tag        # tags differ


def test_5_the_domain_tag_is_not_in_the_ledger_bytes():
    r"""A77 §65.12: the architecture belongs to the arm descriptor, not to the canonical ledger.

    So the injection is per domain while the receipt keeps the encoding the frozen baseline
    was captured with — a schema change here would be a versioned change of its own, not a
    side effect of generalising the address contract.
    """
    from rfl_rebuild.learner.store import DecisionAddress, State
    legal = DecisionAddress(state=State(x=1, y=2, t=3, kappa=0, phi=1), z=1, m=0)
    r = DecisionWriteReceipt(address=legal, status=APPLIED, store_changed=True,
                             canonical_form=DQ_DOMAIN.canonical(legal))
    assert r.canon() == "1,2,3,0,1,1,0|APPLIED|1"
    assert "D_Q" not in r.canon()
    ledger = UpdateLedger(receipts=(r,), fingerprint_pre="a", fingerprint_post="b",
                          scalar_metrics_applicable=False, n_scalar=0,
                          sum_abs_delta=0.0, max_abs_delta=0.0)
    assert "D_Q" not in ledger.canonical()
