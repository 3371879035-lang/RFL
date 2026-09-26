# C3 acquisition integration and CF-5 serialization

## 1. Scope and status

This engineering amendment connects the evidenced C3 initializer to the real master
acquisition API. It does not mark F0 VALID, acquire development seeds, select a
horizon, or ratify the persistent-regime P RMST threshold. Document
`20-B2-DEV-PROTOCOL-FREEZE.md` remains the statistical contract; its original
canary/cap block is historical for this proposed C3 profile, not silently overwritten.
Construction evidence and dispositions remain in `26-F0-BASELINE-CONSTRUCTION-RESULTS.md`.

The explicit profile is `c3-temporal-layer-1-v1`, layer 1, alpha 1/2, epsilon 1/10,
production acquisition cap 576 and balanced master bank 1024. The 840 Q edits are
exactly C3's frozen seedless edits. The runtime initializer neither reads the C3
training results nor repeats a layer search. Each seed receives a fresh full learner.
Non-Q stores are healthy. The old initializer remains available as a historical
instrument; the generic acquisition's omitted-initializer default remains healthy
for its existing fixtures. A C3 caller must explicitly pass the named initializer.

## 2. Acquisition semantics

The iterator yields one complete RunMaterial at each seed/episode, in declared seed
order and ascending e=0..cap. The in-memory convenience API consumes that same
iterator. Training uses the existing A91 episode rollout, chronological sweep and
transaction. Full-U2 pre-update traces supply each run's domains, success flags and
incidence, including the state-dependent Controller domain. No return-only cell
cache is reused for eligibility or domain construction. A small evaluation bank
must not narrow the Controller domain. Reusing a mutable learner across seeds is
rejected. Streaming bounds retained record memory to a checkpoint rather than
the complete development matrix; this implementation still computes all U2 traces
per checkpoint and is not yet a measured full-envelope runtime benchmark.

## 3. Concrete serialization

Schema `f0-master-incidence-v1`: an index and one seed-NNNNNN.jsonl.gz file per seed
under the index's same-stem directory. Each canonical JSONL record contains seed,
episode, levels and boolean success flags in bank order; complete ordered credited
domains; incidence; uncontacted flags; and outside-domain audit counts. Site keys
are numeric arrays: D_Q=(x,y,t,kappa,phi,z,m), X=(x,y,t,kappa,phi,command), P=(option).
Incidence is sorted pairs of domain ordinal and strictly increasing scene indices.
Domain order preserves the production enumerator; Controller domains are not replaced
by a fixed healthy or bank-only domain. Empty incidence entries are omitted.

Canonical bytes are UTF-8, sorted object keys, compact separators, finite binary64
JSON values and one LF per record. gzip uses mtime=0 and no embedded filename.
The normative SHA-256 is over uncompressed canonical bytes, never gzip bytes.
The ordered-shard aggregate hashes the canonical list of [seed, shard_sha256].
Pair counts count stored (credited site, scene) incidence pairs over all channels.
The index records schema, role, seed/episode axes, bank size/digest, constants,
execution provenance, shard descriptors, aggregate digest and total counts.

An index is written exclusively only after all declared records arrive and no
extra record remains. Existing outputs are refused. Interrupted shards are preserved
without an index; there is no implicit resume or overwrite. Validation checks every
hash, canonical encoding, record order, complete fixed D_Q/P domains, duplicate
sites, legal site types, incidence bounds/order, boolean fields, finite values,
counts, and path confinement before any selector receives values. The read pass
checks hashes again; a future selector must complete it before publishing a lock.
These checks establish integrity and structural sufficiency, not independent proof
that each Controller site was visited; full-U2 construction and trajectory tests
provide that separate provenance.

## 4. Predeclared integration rehearsal

Reserved operational keys 940001 and 940002, cap 2, master bank 1024. These keys
join the permanent exclusion set for scientific sampling. Cap 2 is a wiring
fixture, not a shortened scientific envelope, a convergence sample or a replacement
for C3's 576-episode construction. No scientific seed is drawn.

Before acquisition, freeze this document, all rebuild Python sources, both new
scripts, the artifact/convergence regression tests and the statistical/F0/A91
documents by hash and archive. Record the HEAD
commit as context plus the exact working-tree hashes; the commit alone does not
identify these uncommitted changes. All outputs are exclusive under
`experiments/v03r/c3_acquisition_integration/`. Planned commands:

```text
python scripts/f0_acquisition_rehearsal.py --plan
python scripts/f0_acquisition_rehearsal.py --freeze
python scripts/f0_acquisition_rehearsal.py --run
python scripts/inspect_dev_baseline.py --design experiments/v03r/c3_acquisition_integration/baseline.json
```

The run must produce six complete records (two seeds, e=0,1,2), validate every shard,
and match every saved mean bit-for-bit against an independent A91 train_curve replay
from the same initializer. Four acquisition training episodes and four verification
replay episodes are counted separately. The inspection command returns exit 3 for
a valid but non-lockable artifact, exit 2 for an invalid artifact. It computes no
design metric and writes no file. --plan performs no episode and writes no artifact.

## 5. Design-lock readiness

The preflight intentionally identifies readiness separately from data integrity.
Operational records cannot become development data by successful decoding. A full
C3 development artifact would need the declared 1000..1031 keys, 0..576 axis, bank
1024, F0 manifest/stage authorization, smoke gate and exact source provenance.
No run_dev_lock command is represented as complete by this preflight utility.

The complete convergence rule is already frozen in `12` §79.7 (A91), not merely
the shorter wording in `05` §6.1. The main protocol now points to that clarification.
The implementation uses endpoint slope on the real axis, one K-point window tested
once, FlipRate=0 only for a constant window, and an undefined nonconstant zero-pair
window failing. T_conv is the final checkpoint of the first qualifying window.
A local plateau can therefore qualify even if learning later resumes; the code must
not quietly strengthen the frozen rule to require all-future stability.

A91 also fixes censoring: retain the original n and rank ceil(0.9n), require at
least that many uncensored runs and then take that rank among observed times. The
rev-4 "missing T_conv" sentence was ambiguous and is clarified to match A91, not
to drop runs or reject a quantile that A91 identifies. Missing records remain
protocol errors. The horizon applies the exact rational 6/5 ceiling and rejects
T above the cap. Toy fixtures exercise these cases without reading operational
curves to choose a design. This is implementation/clarification of A91, not new
convergence tolerances or post-data horizon selection.

The remaining f_N/f_G/f_C/f_R implementation and combined design/threshold
lock remain outstanding. The independent practical rationale for (P, RMST)=1.5
episodes remains unratified. Neither issue can be solved by labeling a passing
serialization test as F0 VALID or by using operational C3 curves as development data.
