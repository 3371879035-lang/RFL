r"""B2's **test-only** fixture mint for future evidence.

$$\boxed{\text{production modules may not import this module}}$$

B2-2a moved provenance into a mint: `FutureRollout`s are sealed, and only
`rfl_rebuild.b2.producer` can build one in production. That leaves the fixtures needing a
sanctioned way to mint a clean rollout, and the honest way to provide one is a module that is
**named as test-only** and kept out of the production chain by a gate:

`assert_modules_are_closed` refuses a production module that imports `rfl_rebuild.b2.testing`.

This module is also the one **explicitly acknowledged** holder of the mint capability outside
`producer.py`: it is test-only, and production may not import it, so the capability stays inside
`producer.py` for everything the audit covers.

Nothing here is a sampled run, a seed, or a development-stage choice: `toy_environment` and
`toy_rollout` are deterministic fixtures, and the numbers in them are arbitrary on purpose.
"""

from __future__ import annotations

from rfl_rebuild.b2.producer import LearnerEnvironment, _mint_rollout
from rfl_rebuild.b2.view import EvidenceOrigin

__all__ = ["toy_environment", "toy_rollout", "toy_records"]


def toy_records(horizon: int = 3) -> tuple:
    """Five sequences of one horizon. Deterministic, and deliberately trivial."""
    return (
        tuple(0.25 * (i + 1) for i in range(horizon)),
        tuple(i % 2 for i in range(horizon)),
        tuple((i, i + 1) for i in range(horizon)),
        tuple(i % 3 for i in range(horizon)),
        tuple((i, i * i) for i in range(horizon)),
    )


class _ToyEnvironment(LearnerEnvironment):
    """A learner-visible environment stand-in for fixtures: records in, records out."""

    __slots__ = ("_horizon",)

    def __init__(self, horizon: int = 3) -> None:
        self._horizon = horizon

    def future_records(self, state) -> tuple:
        return toy_records(self._horizon)


def toy_environment(horizon: int = 3) -> LearnerEnvironment:
    return _ToyEnvironment(horizon)


def toy_rollout(horizon: int = 3, origin: EvidenceOrigin = EvidenceOrigin.LEARNER_FUTURE_ROLLOUT):
    """A sealed rollout for gates that need one without a producer.

    It is minted through the same seal as production, which is the point of a test-only module:
    the fixtures exercise the *real* construction path rather than a bypass of it.
    """
    return _mint_rollout(origin, toy_records(horizon), tuple(range(horizon)))
