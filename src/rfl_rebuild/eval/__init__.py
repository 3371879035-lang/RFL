"""Formal evaluator: the metric pipeline used by Oracle and by every real arm."""

from .metrics import (  # noqa: F401
    CAUSES, ECE_BINS, Metrics, N_CAUSES, THRESHOLD, auroc_binary, auprc_binary,
    brier, ece_per_cause, evaluate, mutate_flip_one, mutate_shift_rows,
    mutate_softmax, mutate_swap_PD,
)

__all__ = [
    "CAUSES", "ECE_BINS", "Metrics", "N_CAUSES", "THRESHOLD", "auroc_binary",
    "auprc_binary", "brier", "ece_per_cause", "evaluate", "mutate_flip_one",
    "mutate_shift_rows", "mutate_softmax", "mutate_swap_PD",
]
