# tests/semantic — the semantic gate suite

This directory is declared by `docs/rebuild/04-SEMANTIC-INVARIANTS.md` §3. It is
**empty on purpose**: the specification is frozen before the implementation, and
this file marks the slot the suite will occupy so that the audit
(`scripts/spec_audit.py`) can verify the declared path exists.

Nothing here is a result, and nothing here may be written to satisfy a test.

---

## What belongs here

Two kinds of check, both against the **implementation**, not the design:

| kind | scope | when it runs |
|---|---|---|
| invariants I1–I6 | every episode of every run | continuously, not only in the suite |
| cases C0–C8 | hand-constructed episodes with known truth | before seed collection, as a gate |

They are deliberately **not** ordinary unit tests. The legacy project had 177
passing unit tests while shipping a training loop that wrote two nominally
distinct units into one Q entry, an Oracle that reconstructed decision faults
from realized actions, and a "ceiling" arm that reinforced the action it was
supposed to repair. Passing unit tests is not evidence of semantic correctness.

## The artifact this directory must produce

`experiments/<version>/semantic_gate.json`, with per-case PASS/FAIL and the
observed values, plus the run's source fingerprint.

## The rule

$$\boxed{\text{Any FAIL blocks seed collection for every version until fixed.}}$$

And, from the statistical protocol §10: if a failure is found *after* seeds have
been collected, the seed set is **void** and collection restarts from $N = 0$. A
failed case is a bug, never a result.
