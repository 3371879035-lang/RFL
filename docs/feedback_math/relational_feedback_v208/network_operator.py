"""Frozen, domain-neutral conjunction lift and factual-distribution readout.

This is an executable mathematical operator, not an environment or an agent.
No random initialization, optimizer, reward-head training, or game imports.
Counts are explicit caller-supplied state, never neural Parameters.
"""
from itertools import product
import hashlib
import torch
from torch import nn
from torch.nn import functional as F


class RelationalFacts(nn.Module):
    def __init__(self, cardinalities, structures):
        super().__init__()
        self.cardinalities = tuple(cardinalities)
        self.structures = tuple(tuple(s) for s in structures)
        if not self.cardinalities or any(c < 1 for c in self.cardinalities):
            raise ValueError('Positive finite categorical cardinalities required')
        offsets = [0]
        for c in self.cardinalities:
            offsets.append(offsets[-1] + c)
        self.offsets = tuple(offsets)
        weights, biases, cells, blocks = [], [], [], []
        for structure in self.structures:
            if not structure or len(set(structure)) != len(structure):
                raise ValueError('Each structure must contain distinct field indices')
            if any(j < 0 or j >= len(self.cardinalities) for j in structure):
                raise ValueError('Field index outside declared input schema')
            begin = len(cells)
            for values in product(*(range(self.cardinalities[j]) for j in structure)):
                row = [0.] * offsets[-1]
                for j, value in zip(structure, values):
                    row[offsets[j] + value] = 1.
                weights.append(row)
                biases.append(1. - len(structure))
                cells.append((structure, values))
            blocks.append((begin, len(cells)))
        if not cells:
            raise ValueError('At least one relation structure required')
        self.cells, self.blocks = tuple(cells), tuple(blocks)
        self.weight = nn.Parameter(torch.tensor(weights, dtype=torch.float64), requires_grad=False)
        self.bias = nn.Parameter(torch.tensor(biases, dtype=torch.float64), requires_grad=False)
        self.eval()

    def encode(self, rows):
        x = torch.zeros((len(rows), self.offsets[-1]), dtype=torch.float64)
        for b, row in enumerate(rows):
            if len(row) != len(self.cardinalities):
                raise ValueError('A value, including an explicit missing category, is needed per field')
            for j, value in enumerate(row):
                if not isinstance(value, int) or not 0 <= value < self.cardinalities[j]:
                    raise ValueError('Category outside declared field')
                x[b, self.offsets[j] + value] = 1.
        return x

    def forward(self, encoded):
        # Exact conjunction on valid categorical one-hot inputs, not arbitrary soft embeddings.
        return torch.relu(F.linear(encoded, self.weight, self.bias))

    def factual_distribution(self, encoded, counts):
        """Return [batch, structure, action, outcome], support, mass.

        Unsupported entries have a zero storage placeholder AND support=False.
        They must not be evaluated as if a zero-sum vector were a probability law.
        """
        if counts.ndim != 3 or counts.shape[0] != len(self.cells) or bool((counts < 0).any()):
            raise ValueError('Expected nonnegative [relation_cell, action, outcome] state')
        phi = self(encoded)
        distributions, supports, masses = [], [], []
        for lo, hi in self.blocks:
            numerator = torch.einsum('br,rao->bao', phi[:, lo:hi], counts[lo:hi])
            mass = numerator.sum(-1)
            supported = mass > 0
            denominator = torch.where(supported, mass, torch.ones_like(mass))
            distributions.append(numerator / denominator[..., None])
            supports.append(supported)
            masses.append(mass)
        return torch.stack(distributions, 1), torch.stack(supports, 1), torch.stack(masses, 1)

    def parameter_digest(self):
        result = hashlib.sha256()
        for name, param in self.named_parameters():
            result.update(name.encode())
            result.update(param.detach().cpu().numpy().tobytes())
        return result.hexdigest()
