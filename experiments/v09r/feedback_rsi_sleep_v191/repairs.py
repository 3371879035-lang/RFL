"""Repairs with explicit targets: distinct bootstrap data and zero-preserving successors."""
import numpy as np
import torch
from torch.nn import functional as F
from world import seed_for


def bootstrap_mask(uids, head, seed):
    x = np.asarray(uids, dtype=np.uint64) ^ np.uint64(seed_for(seed, 'fact-bootstrap-v183', head))
    # uint64 wraparound is the specified SplitMix64 integer arithmetic.
    x = (x ^ (x >> 30)) * np.uint64(0xbf58476d1ce4e5b9)
    x = (x ^ (x >> 27)) * np.uint64(0x94d049bb133111eb)
    x = x ^ (x >> 31)
    return ((x % np.uint64(7)) < 5).astype(np.float32)


def successor(h, delta):
    return (h + .1*delta).clamp(-1, 1)


def transition_loss(h, observed_next, delta, valid, boot, legal_next, q_layer):
    # Learn the predictor, not an easier encoder/Q target that conceals model error.
    base, target = h.detach(), observed_next.detach()
    prediction = successor(base, delta)
    weights = valid*boot
    latent_error = ((prediction-target)**2).mean(-1)
    identity_error = ((base-target)**2).mean(-1)
    value_error = torch.zeros_like(latent_error)
    if q_layer is not None:
        w, b = q_layer.weight.detach(), q_layer.bias.detach()
        predicted_q = F.linear(prediction, w, b)
        target_q = F.linear(target, w, b)
        values = F.smooth_l1_loss(predicted_q, target_q, reduction='none')
        value_error = (values*legal_next).sum(-1)/legal_next.sum(-1).clamp_min(1)
    total = ((latent_error+value_error)*weights).sum()/weights.sum().clamp_min(1)
    statistics = dict(weight=float(weights.sum().detach()),
        model_mse_sum=float((latent_error*weights).sum().detach()),
        identity_mse_sum=float((identity_error*weights).sum().detach()),
        value_loss_sum=float((value_error*weights).sum().detach()))
    return total, statistics
