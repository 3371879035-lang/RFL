# v0.4 reproducibility defect — training was PYTHONHASHSEED-dependent

**Status:** found and fixed 2026-09-01, during the frozen 400-seed re-run.
**Impact:** every published v0.4 number was **one hash-order draw**. All v0.4
pilots were re-run after the fix. The v0.3 (`rflnext`) pilots are **not**
affected — verified, see §6.

---

## 1. The defect

`decision_oracle` and `repair_oracle` in `src/rflv04/credit_units.py` iterated
the oracle's repair primitives directly:

```python
prims = best.primitives if best is not None else frozenset()
for prim in prims:          # <-- frozenset of (str, int) tuples
```

`Repair.primitives` is a `frozenset`. Iterating a frozenset of tuples containing
strings follows **string hashing**, and CPython randomises string hashes per
process unless `PYTHONHASHSEED` is fixed. The order was therefore different in
every interpreter.

Order mattered because of a second fact about the code. A `WholeProcess` repair
is `{("unstick", t), ("exec", t)}`, which produces:

| primitive | site emitted | Q table written |
|---|---|---|
| `unstick` | `Site("DECISION", q_key, intent)` | `q.low` |
| `exec` | `Site("EXECUTION", q_key, intent)` | `q.low` |

`Site.key` is `(unit, state, action)`, so the two sites have **different keys and
both survive `dedup()`** — but `updates._write` routes *every* non-PLAN unit to
the same low-level table. They are two successive **relative** writes to one
Q entry. Whichever is applied last decides the stored value, and the two carry
opposing targets.

Determinism was therefore hostage to `PYTHONHASHSEED`.

## 2. Measurement

Arm `Contrastive`, seed `4600000`, `configs/v04_beta.yaml`, four separate
interpreters, `PYTHONHASHSEED` unset (i.e. randomised, as in a normal run):

| process | `q_hash` | `corrections` | `sites_touched` | **`wmd`** |
|---|---|---|---:|---:|---:|
| 1 | `78e4710bd556` | 867 | 3693 | **0.11975** |
| 2 | `450ee8002097` | 871 | 3723 | **0.11191** |
| 3 | `6b868ff4e495` | 860 | 3687 | **0.03604** |
| 4 | `f8d551c12d63` | 872 | 3727 | **0.09104** |

`WithinModuleDamage` — the endpoint the entire v0.4 spec was built around, and
the one that fails Pilot Alpha's screen — varied by **3.3x** purely from hash
order, with identical inputs.

After the fix, five separate interpreters agree exactly:

| process | `q_hash` | `corrections` | `sites_touched` | `wmd` |
|---|---|---|---:|---:|---:|
| 1–5 | `480a369fae6b` | 858 | 3682 | 0.036478 |

## 3. Which arms were affected

Every arm that consults the oracle's primitive set. Measured by running each arm
in two interpreters with `PYTHONHASHSEED=0` and `=999` on the **unfixed** code:

| arm | hash-dependent? |
|---|---|
| `NoCorruption` | no |
| `NoCorrection` | no |
| `ModuleOracle` | no — builds sites directly from the trace |
| `DecisionOracle` | **yes** |
| `RepairOracle` | **yes** |
| `NegativeOnly` | **yes** |
| `PositiveAlternative` | **yes** |
| `Contrastive` | **yes** |
| `CFRevalue` | **yes** |

`NegativeOnly` is worth flagging: a three-process spot check on it happened to
return identical results and it was initially written down as safe. Extending the
check to two *fixed* hash seeds showed it was not. **A passing spot check is not
a reproducibility proof** — the regression test now uses fixed, differing seeds
rather than relying on the default randomisation to differ.

## 4. The fix

Sort the iteration so the write order is canonical:

```python
for prim in sorted(prims):
```

Applied in both `decision_oracle` and `repair_oracle`. This does not change the
*intended* semantics — it selects one consistent order out of the set of orders
that were previously being sampled at random.

Locked in by `tests/test_v04_reproducibility.py`, which compares runs in
**separate interpreters** with different `PYTHONHASHSEED` values. The existing
`tests/test_v04.py::test_training_is_reproducible` could never catch this: both
of its calls run in one process, where the hash seed is constant by construction.
The new test was verified to **fail** on the unfixed loop (`Contrastive`:
`4be7121fe042` vs `e3407e07164a`) and to pass once sorted.

## 5. What this means for results already published

Every v0.4 number reported at 6, 12, 100, 200 or 300 seeds — in
`docs/V0_4_RESULTS.md`, `docs/SEED_AUDIT_200.md` and the pilot logs — is a single
draw from this distribution. They are not reproducible as written, and the
`wmd` columns in particular carry a spread of up to 3.3x on top of genuine seed
variation.

They are **retained on disk and not overwritten**, because how far they move once
the defect is removed is itself a result. But they are superseded: only the
post-fix 400-seed runs under `docs/SEED_BLOCK_PROTOCOL.md` are evidence.

This defect is a second, independent reason the seed-count conclusions kept
moving. It was not the only reason — the zero-inflation and heavy tails
documented in `docs/ROBUSTNESS_AUDIT.md` are real and separate — but any
comparison between two runs made in *different processes* was comparing two
hash-order draws as well as two seed sets.

## 6. The v0.3 pilots are unaffected — verified

`src/rflnext/` contains no iteration over a `frozenset` of primitives. Confirmed
empirically on real data rather than by inspection alone: the 300-seed Stage 5 run
and the first 300 seeds of the 400-seed run were produced by **separate
processes**, and all 1,800 `(setting, seed)` pairs match bit-for-bit.

```
setting            300-run   400-run[0:300]   exact match
base_h8_a01            300              400   yes
base_h8_a03            300              400   yes
base_h8_a10            300              400   yes
tight_h5_a03           300              400   yes
tight_h5_a10           300              400   yes
tight_h6_a10           300              400   yes
```

So the v0.3 results — including the Stage 5 difficulty sweep and its three
recorded reversals — stand as measured, and those reversals are attributable to
the statistical fragility analysed in `docs/ROBUSTNESS_AUDIT.md`, not to this
defect.

## 7. A second, still-open problem: the collision itself

Sorting removes the *nondeterminism*. It does not remove the underlying
modelling defect, which is that the oracle's `DECISION` and `EXECUTION` units are
**nominally distinct but physically the same Q entry**. A canonical coin flip is
still a coin flip.

This is now surfaced rather than hidden. `Site.write_key` collapses the two onto
the entry they actually share, and `Credit.collisions()` returns the groups that
write one entry more than once. It is counted and reported; it is not silently
resolved, because choosing a winner would be a semantic decision that the current
evidence does not support.

## 8. Related defects found by the candidate-ledger audit

Reported by the ledger build (`scripts/v04_ledger.py`, `outputs/v04_ledger/`);
**listed here as open, not fixed** — the 400-seed runs were launched against
frozen semantics, and changing behaviour mid-run would confound the protocol.

| # | location | defect | status |
|---|---|---|---|
| 1 | `credit_units.py` | frozenset iteration → hash-order dependence | **fixed**, §4 |
| 2 | `oracle.py:157` `scene_from_trace` | locates the critical decision using the **realized** action, although `env.py` deliberately records intent and realized separately so that execution faults are never mistaken for bad decisions. Exec-fault scenes gain a decision fault at the same `t`, so no size-1 `exec` repair can suffice. Measured: `Execution` is 0.36% of failures while 56% carry an execution fault — **`WholeProcess` at 68.4% is inflated by reconstruction, not by genuinely multi-fault episodes** | open |
| 3 | `oracle.py` `enumerate_sufficient` | stops at the first size yielding any sufficient intervention, so `minimal` is `True` for all 7,083 candidates and carries no information | open |
| 4 | `oracle.py` `classify` | returns family `"CLEAN"` for episodes that **failed** but whose reconstruction is reference-solvable — 83 rows (1.2%) with empty candidate sets, silently skipped by `train.py` | open |
| 5 | `oracle.py` `Repair.describe` | `"exec:(2,)"` is used as a tie-break key, so for `t >= 10` the lexicographic order puts `exec:(10,)` before `exec:(2,)`. Latent: `HORIZON = 4` | latent |

Defect 2 is the most consequential of the four open items: it means the
`WholeProcess` family — which the spec singles out as the case that makes
credit assignment hard — is substantially an artifact of how the failing episode
is reconstructed, not a population of genuinely multi-fault episodes.

Confirmed in the same audit: **`WholeProcess == (minimal_size > 1)` holds**,
7,137/7,137 rows, 0 disagreements. The spec's operational definition is correct;
what is in doubt is how many real episodes belong to the family.
