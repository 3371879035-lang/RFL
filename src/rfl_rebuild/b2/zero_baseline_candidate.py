"""Isolated C2 construction. Full zero effective Q, with exact cell factorization."""
from __future__ import annotations

import math
from fractions import Fraction

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.training import episode_rollout, sweep_edits
from rfl_rebuild.env.kernel import (HORIZON, REWARD_SUCCESS, REWARD_FAILURE_A,
                                    STEP_COST, SemanticTape)
from rfl_rebuild.learner.store import Edit, Q, QAddress, LearnerPersistentState


def cell_of(address):
    return (address.state.kappa, address.state.phi, address.z)


def zero_edits(q_reference):
    return tuple(Edit(Q, QAddress(s, z, m, a), 0.0)
                 for (s, z, m), row in q_reference.rows.items() for a in row)


def zero_initializer(*, q_reference):
    learner = LearnerPersistentState()
    learner.apply_transaction(zero_edits(q_reference), q_reference=q_reference)
    return learner


def envelope(q_reference):
    cells = sorted({cell_of(e.address) for e in zero_edits(q_reference)})
    scale = abs(REWARD_SUCCESS - REWARD_FAILURE_A) + HORIZON * abs(STEP_COST)
    halvings = math.ceil(math.log2(scale / 0.001))
    return {"cells": len(cells), "horizon": HORIZON, "return_range": scale,
            "precision_scale": 0.001, "halvings": halvings,
            "cap": len(cells) * HORIZON * halvings}


class PartitionedZeroLearner:
    """A product of ordinary LearnerPersistentState objects; no alternative update law."""

    def __init__(self, q_reference):
        self.reference = q_reference
        grouped = {}
        for edit in zero_edits(q_reference):
            grouped.setdefault(cell_of(edit.address), []).append(edit)
        self.parts = {}
        for cell, edits in sorted(grouped.items()):
            learner = LearnerPersistentState()
            learner.apply_transaction(edits, q_reference=q_reference)
            self.parts[cell] = learner
        self._returns = {cell: self.evaluate_cell(cell) for cell in self.parts}

    def evaluate_cell(self, cell):
        kappa, phase, option = cell
        learner = self.parts[cell]
        if learner.decision_overrides or learner.process_overrides or learner.controller_overrides:
            raise ProtocolError("C2 factorization is restricted to Q-only learners")
        return learned_rollout(learner, kappa=kappa, tape=SemanticTape(phase, 0, 0),
                               base_option=option, q_reference=self.reference).return_value

    def train(self, episode, *, protocol):
        cell = (episode.kappa, episode.tape.phase, episode.proposal)
        if cell not in self.parts:
            raise ProtocolError("episode outside C2 cell support")
        learner = self.parts[cell]
        trace = episode_rollout(learner, episode, protocol=protocol, q_reference=self.reference)
        edits = sweep_edits(learner, trace, episode, protocol=protocol, q_reference=self.reference)
        if any(e.store != Q or cell_of(e.address) != cell for e in edits):
            raise ProtocolError("A91 edit crossed a C2 cell boundary")
        changed = any(learner.q_overrides.get(e.address, self.reference.value(e.address))
                      != e.value for e in edits)
        if edits:
            learner.apply_transaction(edits, q_reference=self.reference)
        self._returns[cell] = self.evaluate_cell(cell)
        return changed

    def bank_values(self, bank):
        return tuple(self._returns[(u.kappa, u.phase, u.base_option)] for u in bank)

    def bank_mean(self, bank):
        return mean(self.bank_values(bank))

    def validate_cache(self, bank):
        # Real read-only rollouts, bypassing the return cache; verify all cells.
        if {cell: self.evaluate_cell(cell) for cell in self.parts} != self._returns:
            raise ProtocolError("C2 return cache differs from fresh rollouts")
        # All tape variants in the bank, not only the representative tape.
        for unit, expected in zip(bank, self.bank_values(bank)):
            cell = (unit.kappa, unit.phase, unit.base_option)
            actual = learned_rollout(self.parts[cell], kappa=unit.kappa, tape=unit.tape,
                                     base_option=unit.base_option, q_reference=self.reference).return_value
            if actual != expected:
                raise ProtocolError("C2 tape grouping changed an evaluation return")

    def materialized_overrides(self):
        result = {}
        for cell, learner in self.parts.items():
            for address, value in learner.q_overrides.items():
                if cell_of(address) != cell:
                    raise ProtocolError("C2 partition contains another cell's address")
                result[address] = value
        return result
