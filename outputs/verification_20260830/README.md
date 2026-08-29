# 2026-08-30 verification rerun

This directory contains the final, isolated rerun outputs retained for reproducibility.

## Included results

- `a_confirmatory_50/`: Experiment A rerun using `configs/confirmatory_a.yaml`, 50 paired seed indices (0-49), 30 H/L/E traces per seed, and the original raw episode/event logs, seed metrics, statistics, and figures.
- `B3_5000/`: B3 sanity-ladder rerun with five standard-agent seeds and 5,000 training episodes each.
- `B4_5000/`: B4 rerun with five seeds each for Standard, Immediate, and Full-RFL, with 5,000 training episodes each.

## Important scope

This is an isolated verification rerun, not a replacement for the pre-existing confirmatory output directory. It was created because the project confirmatory runner refuses the current tracked bytecode-cache changes and would otherwise skip existing seeds. `a_confirmatory_50/replay_meta.txt` records the source commit and configuration hash used for the rerun.

The 3,000-episode B3 smoke attempt and A-smoke diagnostic files are intentionally not included: the Word specification and recorded pilot evidence require 5,000 episodes for B3/B4 learnability checks.
