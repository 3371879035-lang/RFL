# 10 — Reproducibility, provenance and operations

**Status:** FROZEN. Applies to every version.

The legacy project shipped results that could not be re-derived: training depended
on `PYTHONHASHSEED` (a 3.3× spread in `WMD` for identical inputs), the confirmatory
runner appended to its CSVs so a re-run would have duplicated seeds 0–49, and the
default branch carried a withdrawn conclusion for a day. Each of those is a
process failure with a mechanical fix, listed here.

---

## 1. Determinism is a tested property, not an aspiration

$$\boxed{\text{Identical inputs} \;\Longrightarrow\; \text{identical outputs, across processes.}}$$

Tested by comparing runs in **separate interpreters** under differing
`PYTHONHASHSEED`, not by calling a function twice in one process — a same-process
comparison passes even when the code is hash-order dependent, which is exactly how
the legacy defect survived 150 unit tests.

Forbidden in `src/rfl_rebuild/`:

* iterating a `set` / `frozenset` / `dict` keyed on strings where order affects
  an outcome — sort first;
* relying on default hash randomisation anywhere in a training path;
* floating-point accumulation whose order depends on a container's iteration
  order.

---

## 2. Source fingerprint

Any change to `src/rfl_rebuild/` between the first and last seed of a run voids
the run (`05` §10). Enforced mechanically:

```bash
python scripts/src_fingerprint.py --record experiments/<version>/PROVENANCE.json
python scripts/src_fingerprint.py --check  experiments/<version>/PROVENANCE.json
```

The fingerprint hashes repo-relative paths and line-ending-normalised contents, so
it is portable across machines and does not raise false alarms under
`core.autocrlf`. It fails when any package differs from the record or when `src/`
has uncommitted changes.

The legacy trees stay in the fingerprint even though they are frozen: their
presence is what allows `legacy-*` tags to remain reproducible.

---

## 3. Runtime calibration

Before a version's seeds are collected, run **5–10 development seeds** and report

$$\text{sec / seed / arm}, \qquad \text{peak memory}, \qquad \text{CF queries per episode}$$

and from those, an estimated wall-clock for the full run.

$$\boxed{\text{Runtime may inform the schedule. It may \textbf{not} inform a scientific hypothesis.}}$$

Shortening $T$, dropping an arm, or reducing $N$ because a run is slow is a design
change and must be made **before** $T$ and the tier are frozen — never after
seeing an interval. The legacy project's single-process throughput number
(66k episodes/s) was measured on a loop with no Oracle enumeration, no CF
rollouts and no evaluation; it is not a valid estimate for any real version, which
is why calibration is per version and empirical.

---

## 4. The update-dynamics ledger

Every run logs, per arm and per episode:

$$N_{\text{writes}},\quad \textstyle\sum|\Delta Q|,\quad \overline{|\Delta Q|},\quad P(\text{clipped}),\quad \overline{|\delta_{TD}|},\quad N(\delta_{TD}<0)$$

and the same quantities broken out by unit (factual / alternative / controller /
process).

Reason: two arms can differ in outcome for reasons that have nothing to do with
their semantics. Reward mode $(+1/-1)$ vs $(+1/0)$ is an affine transform of
expected return and cannot change the optimal policy, yet under a fixed step size
the TD errors differ by 1 and any update clipping bites at different times. Without
the ledger, "reward −1 is better" cannot be separated into *the outcome channel
carries information* versus *the updates were simply larger*.

---

## 5. Seed layout — blocks runnable on separate machines

The rebuild is **CPU-only, single-process**. Multiprocessing is unavailable in the
current environment (named pipes are blocked), and more importantly a
single-process design keeps every run trivially auditable.

Every runner therefore accepts:

```
--seed-start N   --seed-count M   --block-id K
```

and writes **each seed to its own file** the moment it finishes. Blocks
$B_1 \ldots B_4$ are therefore independently runnable, resumable, and — if another
machine ever becomes available — parallelisable without changing experiment code
or splitting a block across distributions.

A partially completed run is not a result. A block is analysed only when its
declared seed count is complete, and blocks from different code fingerprints are
never pooled.

---

## 6. Artifact layout

```
experiments/<version>/
    identifiability.json      gate E/L matrix          (03)
    semantic_gate.json        per-case PASS/FAIL       (04)
    PROVENANCE.json           source fingerprints      (this doc)
    runtime_calibration.json  sec/seed/arm             (§3)
    config.yaml               T, grid, N_eval, Delta_min, B_CF, seeds
    seeds/<seed>.json         one file per seed
    summary.json              pooled + per-block
    analysis/                 four-way verdicts, robustness stats, ledgers
```

Every run writes to a **fresh** directory. Nothing is overwritten. Legacy outputs
are never deleted: how far a number moves under a corrected protocol is itself a
result, and the legacy record is the evidence that the protocol was necessary.

---

## 7. Documentation rules

1. **One confirmatory document per version.** Everything else is marked
   `EXPLORATORY — NOT EVIDENCE` at the top and points at it.
2. **Every number carries its provenance**: $N_{\text{seeds}}$,
   $N_{\text{train}}$, $N_{\text{eval}}$, $\mathcal G_{\text{ckpt}}$, $B_{CF}$,
   $T$, $\Delta_{\min}$, and the source fingerprint.
3. **Withdrawals are recorded, not deleted.** A claim that is withdrawn keeps its
   original wording under a `WITHDRAWN` heading with the reason. The legacy
   project's most useful documents are the ones that record what it got wrong.
4. **A conclusion never appears on the default branch unqualified.** The legacy
   front page propagated a withdrawn claim; the rebuild's default branch points
   only at frozen specs and passed gates.

---

## 8. What "frozen" means here

A frozen document may be changed **only** by:

* a design change forced by a failed gate, recorded as an amendment with its
  reason, **before** any seed of the affected version is collected; or
* a new pre-registered study, which supersedes rather than edits.

A frozen document may **never** be changed after seeing a result it governs.

Amendments are appended, never substituted. The amendment history is the record of
what the design had to learn, and it is the part a reader should trust most,
because it is the only part that could not have been written in advance.
