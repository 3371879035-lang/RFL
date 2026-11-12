r"""A80 §68.5 — the $P$ cell's evidence: $\rho_P$, the assisted input, and the $L_1$ envelope.

$$\rho_P(\texttt{ProcessCommit},\ z^{\text{proposal}}) = z^{\text{proposal}}, \qquad
\boxed{C_P^L(z^{\text{proposal}}) \leftarrow z^{\text{proposal}}}$$

Three things live here, and the separation between them is the point:

1. **resolution** — the static credit unit plus the **allowed assisted input** becomes a store
   address. This is A76 §63.10's $\rho_P$, a cell-construction fact rather than a law's business,
   and it is the one $\rho_A$ that needs an assisted input:

$$\boxed{\text{credit unit} + \text{allowed assisted input} \xrightarrow{\rho_P}
\text{resolved B1 address } z^{\text{proposal}}}$$

   The reason is structural rather than a choice of placement: the factual rows carry
   $z^{\text{in-force}}$ and **never** $z^{\text{proposal}}$, so the key cannot be computed from
   $L_0$ information. That is why $P_{id} \in L_1$ and not $L_0$ (A76 §63.1, §63.9);

2. **the assisted input** — a nominal carrier, and the **only** sanctioned source of the proposal.
   It is not a convenience: the fact that some kernel or state object can *reach* a proposal does
   not license the cell, so the proposal is handed over explicitly and the resolver may use it to
   construct a legal store address **and for nothing else**. Extending it into additional law
   information would be assisted-input laundering by another route (A80 §68.5);

3. **the $L_1$ envelope** — $\{z^{\text{proposal}}\}$, delivered identically to the treatment and
   its same-tier reference through the same field-set mechanism every other cell uses, so
   "same cell $\Rightarrow$ same envelope" holds here too (A77 §65.2).

$$\boxed{P_{id} \text{ at } L_0 \Longrightarrow \texttt{PROTOCOL\_ERROR}}$$

The operation depends only on the resolved address, $\texttt{Edit}(\texttt{PROCESS}, z, z)$, which
is what lets the $L_3$ alias reuse **the same plan function** while its own delivery stays
$\varnothing$.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.domain import is_true_int

__all__ = [
    "AssistedInput",
    "ProcessTarget",
    "build_process_envelope",
    "require_process_option",
    "require_process_unit",
    "resolve_process_addresses",
    "validate_process_envelope",
]

#: The static credit unit of this architecture. `ProcessCommit` is not indexed (A69): it names the
#: process decision itself, and its *address* is the assisted proposal.
PROCESS_UNIT = "ProcessCommit"


def require_process_unit(unit: object) -> str:
    """The credited unit of the $P$ path, typed **before** anything matches it.

    A non-string must not reach the comparison, and another family must not pass for this one: a
    `Decision_<x>_<y>_<t>_<cmd>`, a `ControllerSite_<x>_<y>_<t>_<cmd>` or a `Strategy` credit is a
    different unit with a different resolver (A69, A76 §63.10).
    """
    if not isinstance(unit, str):
        raise ProtocolError(
            f"credit unit {unit!r} is not a string; the process credit unit is written "
            f"'{PROCESS_UNIT}'")
    if unit != PROCESS_UNIT:
        raise ProtocolError(
            f"{unit!r} is not a process credit unit; expected {PROCESS_UNIT!r}, which is the "
            "static family A69 froze for this architecture (A76 §63.10 gives it its own "
            "resolver, rho_P, and its own assisted input)")
    return unit


def require_process_option(value: object) -> int:
    r"""The resolved process address: **exact integer first, then option-domain membership**.

    $$\boxed{\text{exact } int \rightarrow \text{domain membership}}$$

    The order is the point, and it is A78 §66.5's lesson at this key: `True == 1` and `1.0 == 1`
    with equal hashes, so a boolean or a float that is *value-equal* to a legal option id would
    otherwise be credited as that option and reach the store, which persists option ids.
    """
    if not is_true_int(value):
        raise ProtocolError(
            f"the resolved process address {value!r} has type {type(value).__name__}, not int; "
            "Python folds True, 1.0 and 1 into one key, so a value-equal alias would otherwise "
            "be credited as this option (A78 §66.5)")
    if value not in K.option_ids():
        raise ProtocolError(
            f"the resolved process address {value!r} is not an option id; the process store is "
            f"keyed by z in {K.option_ids()!r} and an entry outside that domain would be "
            "unreachable by the read path while still moving the fingerprint")
    return value


@dataclass(frozen=True, slots=True)
class AssistedInput:
    r"""$P$'s one **allowed assisted input**: $z^{\text{proposal}}$ (A80 §68.5).

    A carrier type rather than a bare integer, so that "the cell was handed the proposal" is a
    fact about an object that had to be constructed for this purpose, and not an inference from
    the caller already having a number. Its field is deliberately the only one: the resolver may
    use it to construct a legal store address and for nothing else, and a type that could carry
    more would be the first step of laundering the assisted input into law information.
    """

    z_proposal: object


@dataclass(frozen=True, slots=True)
class ProcessTarget:
    r"""$P$'s $L_1$ record: the assisted proposal that the cell delivers.

    Only $z^{\text{proposal}}$ is delivered (A80 §68.5), and it is the same value the address
    carries -- the runner checks that agreement rather than assuming it, exactly as the $X$ path
    checks its $L_0$ delivery against the credited site.
    """

    z_proposal: int


def require_assisted(assisted: object) -> AssistedInput:
    """The assisted input is nominal, and checked by type rather than duck-typed.

    A stand-in carrying `z_proposal` would be accepted by `getattr` and would reopen exactly what
    the substrate's nominal closure closed: the cell would take its assisted input from anything
    that happens to look like one, including an object built by the code under test.
    """
    if type(assisted) is not AssistedInput:
        raise ProtocolError(
            f"the assisted input {assisted!r} has type {type(assisted).__name__}, not "
            "AssistedInput; the proposal must be handed over explicitly (A80 §68.5)")
    return assisted


def resolve_process_addresses(credited_units, assisted: object) -> tuple:
    r"""$\rho_P(\texttt{ProcessCommit}, z^{\text{proposal}}) = z^{\text{proposal}}$.

    Cell construction, and therefore **before any arm planning**: the address-plan and the receipt
    take this resolved true-integer option key as their locality unit, and the $L_3$ alias uses
    the same upstream resolution while delivering nothing itself.

    Fail-stop, in this order, and each step for its own reason:

    * the unit is typed and checked against the static family before anything matches it
      (`require_process_unit`) — another family is a different architecture's credit, not this
      one's;
    * a repeat is refused rather than de-duplicated, because de-duplicating silently changes
      $N_{\text{addressed}}$ and the address budget (the lesson `targets.py` already learned for
      $\rho_D$);
    * an empty population is refused: the cell has no address to write, and an empty run is not a
      run of this cell;
    * the assisted input is **nominal** and its proposal passes the exact-integer-first rule.
    """
    seen: set = set()
    for u in credited_units:
        u = require_process_unit(u)
        if u in seen:
            raise ProtocolError(
                f"credited unit {u!r} appears more than once; de-duplicating it would silently "
                "change N_addressed and the address budget")
        seen.add(u)
    if not seen:
        raise ProtocolError(
            "no credited process unit; the P cell has no address to write and an empty run is "
            "not a run of this cell")
    assisted = require_assisted(assisted)
    return (require_process_option(assisted.z_proposal),)


def build_process_envelope(addresses: Sequence, assisted: object) -> Mapping:
    r"""The $L_1$ envelope: $\{z^{\text{proposal}}\}$ for each resolved address.

    Built from the **assisted input** and from nothing else. A version that read the proposal out
    of the persistent state, the kernel or the trace would be the laundering A80 §68.5 forbids:
    the cell not seeing a proposal is not evidence that the cell was not handed one.
    """
    assisted = require_assisted(assisted)
    z = require_process_option(assisted.z_proposal)
    out = {}
    for a in addresses:
        require_process_option(a)
        out[a] = ProcessTarget(z_proposal=z)
    return MappingProxyType(out)


def validate_process_envelope(addresses: Sequence, envelope) -> None:
    r"""The $L_1$ delivery must be exactly the credited addresses, and must agree with them.

    Two rules, both of them the $X$ path's rules at this store:

    * the envelope's key set is **exactly** the credited addresses -- not a superset that happens
      to contain them, and not a subset;
    * each record carries a true-integer option id that **equals its address**. The agreement is
      what makes the operation $\texttt{Edit}(\texttt{PROCESS}, z, z)$ well defined: a delivery
      that disagreed with the address would have the cell write one option while being credited
      at another.
    """
    if envelope is None:
        raise ProtocolError(
            "the P cell at L1 delivers {z_proposal} but no envelope was supplied; the runner "
            "must build the cell's fields from the assisted input before any law in it runs")
    keys = set(envelope)
    expected = set(addresses)
    if keys != expected:
        raise ProtocolError(
            f"the P L1 envelope covers {sorted(keys)!r} but the credited addresses are "
            f"{sorted(expected)!r}; the delivery must be exactly the credited population")
    for a in addresses:
        rec = envelope[a]
        if type(rec) is not ProcessTarget:
            raise ProtocolError(
                f"the P L1 envelope entry for {a!r} has type {type(rec).__name__}, not "
                "ProcessTarget")
        z = require_process_option(rec.z_proposal)
        if z != a:
            raise ProtocolError(
                f"the delivered proposal {z!r} disagrees with the credited process address "
                f"{a!r}; the address is the resolved z^proposal, so a delivery that differs "
                "from it would write one option while being credited at another (A80 §68.5)")
