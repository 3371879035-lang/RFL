# Rev-5 runtime launch snapshot

Recorded 2026-09-27 21:27 China Standard Time. This is a launch record, not a
completion claim; consult the eventual runtime and verification receipts.

- Instrument commit: `e3dcf1bc482d85a7562d968d37e0972cf0e0d4d0`.
- Exact inventory: 292 files; digest
  `be88fc35d70ced51b8cda0a32e9b969eb11a473e22f0a5c70886f182ac01a3ea`.
- Benchmark process: PID 50000; one-shot completion helper: PID 43072. Both
  were alive when checked at 21:27; process identity includes start-time ticks
  in `runtime_rev5_launch.json`, so PIDs alone are not durable identities.
- New output: `../f0_runtime_rev5/`; old `../f0_runtime/` is preserved.
- C3 layer 1, cap 576, 1024-scene bank, 5 smoke-shaped operational runs and 32
  serialized operational runs; independent keys 970001-970037.
- Current phase at launch verification: frozen six-gate preflight suite. No
  runtime/index or raw shard was complete yet. No scientific stage was started.
- Prior full timing took about 7 h 38 min plus about 30 min for full raw-shard
  verification. This is a rough planning comparison, not a guaranteed finish
  time or evidence for the new instrument.

The hidden completion helper waits on the exact benchmark process, verifies
source/commit identity, key assignment, gate digests and all raw shards, and then
attempts to create `f0_manifest_rev5.json` using the source-bound review. Failure
leaves a refusal/error record; it does not retry, overwrite an output, commit a
manifest, or launch scientific stages. The candidate must subsequently be
reviewed and committed before a stage can use it.

The source inventory must stay unchanged during measurement. Reports and
launch metadata outside that inventory may be committed without retiming it.
