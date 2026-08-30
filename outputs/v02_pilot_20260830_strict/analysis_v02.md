# RFL-CausalChase v0.2 seed-level analysis

- Statistical unit: `seed`; no episode-level p-values.
- Paired sign-flip permutations: `10000`.
- Paired bootstrap resamples: `10000`.
- Holm family: `H-A, H-U, H-K, H-L`.

| Endpoint | n seeds | Mean Δ | 95% paired CI | sign-flip p | Holm p | d_z | Decision |
|---|---:|---:|---|---:|---:|---:|---|
| ΔAE | 12 | -0.2753 | [-0.3046, -0.2461] | 0.0007 | 0.0021 | -5.057 | PASS |
| ΔF1U | 12 | 0.4806 | [0.4781, 0.4842] | 0.0004 | 0.0016 | 82.21 | PASS |
| ΔCKD (high protection, H module) | 12 | -0.154 | [-0.154, -0.1539] | 0.0007 | 0.0021 | -1527 | PASS |
| RecoveryEpisodes (Full - 0.8×Immediate) | 12 | 68.87 | [6.2, 100.2] | 0.0321 | 0.0321 | 0.6345 | FAIL |
| WUR | 12 | -0.01553 | [-0.04831, 0.01972] | 0.4099 |  | -0.246 | descriptive |
| CF cost | 12 | -295.3 | [-296.6, -293.9] | 0.0003 |  | -116 | descriptive |
| Update precision | 0 |  |  |  |  |  | invalid_input |
| Update recall | 12 | 0.4681 | [0.4661, 0.471] | 0.0006 |  | 99.95 | descriptive |
| WKR | 12 | -0.07973 | [-0.07993, -0.07942] | 0.0003 |  | -156.2 | descriptive |
| CF cost | 12 | -244.3 | [-246.4, -242.4] | 0.0003 |  | -66.93 | descriptive |
| Update F1 | 12 | 0.9342 | [0.9323, 0.9357] | 0.0006 |  | 299 | descriptive |
| CKD | 12 | 8.237e+06 | [7.687e+06, 8.787e+06] | 0.0006 |  | 8.286 | descriptive |
| WKR | 12 | 8.237e+06 | [7.687e+06, 8.787e+06] | 0.0003 |  | 8.286 | descriptive |
| CF cost | 12 | -245.1 | [-245.8, -244.3] | 0.0004 |  | -168.7 | descriptive |
| AUC_success,0:500 | 12 | 0 | [0, 0] | 1 |  | 0 | FAIL |
| AUC_success,0:3000 | 12 | -0.002972 | [-0.03706, 0.03722] | 0.893 |  | -0.04308 | descriptive |
| EpisodesTo90 (3 checkpoints) | 12 | -58.33 | [-333.3, 200] | 0.7309 |  | -0.1198 | descriptive |
| FinalSuccess non-inferiority | 12 | -0.008333 | [-0.04, 0.01833] | 0.6977 |  | -0.1576 | PASS |

Primary gate: FAIL

Unavailable/invalid rows are not null results. Their exact data-integrity reason is in `analysis_v02.json`.
