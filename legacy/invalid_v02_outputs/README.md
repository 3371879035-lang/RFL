# Quarantined v0.2 outputs

These files are retained as Git history/evidence, not as current experimental
results.  They are deliberately outside `outputs/` so no execution or analysis
entry point can discover them as a fresh v0.2 run.

| Former directory | Why it is invalid for v0.2 closeout |
|---|---|
| `v02_pilot_a` | A partial/older update output; it is not the frozen strict 12-seed panel. |
| `v02_pilot_b` | Synthetic high-Q initialization and a linear recovery surrogate, not a common learned checkpoint. |
| `v02_pilot_b_final` | Pretraining gate failure and synthetic transfer path; shocks are not confirmatory evidence. |
| `v02_pilot_b_real2` | Incomplete/non-strict B transfer attempt; it lacks the required full protocol artifacts. |
| `v02_pilot_online` | Standard-only online output, not the nine-algorithm panel. |
| `v02_smoke` | Pre-repair smoke artifacts whose B measurement semantics contradict the closeout protocol. |

The retained `outputs/v02_pilot_20260830_strict` directory is not moved: its
raw files have a SHA-256 manifest and a `STATUS.json` that marks H-L as
`invalid_probe_semantics` and confirmatory as not run.
