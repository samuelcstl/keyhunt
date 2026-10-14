# Keyhunt Puzzle #71: production and research roadmap

**Reviewed:** 2026-10-14 · **Working branch:** `perf/pi5-arm64` / draft PR #1 · **Status:** planning and audit; this document does NOT enable a service or alter the existing campaign.  
**Objective:** begin durable unattended Pi 5 scanning with safe discovery handling, while running evidence-driven optimization and creator-origin research separately.

## Actual baseline and invariants

- Four-core standalone NEON engine: **7.337 M scalar attempts/s (not globally deduplicated with standalone random mode)**, sustained twice on Pi 5 (October 11). A later diagnostic during idle Pi conditions again observed ~7.317 M/s (October 14). The pipelined Keypool A/B/C test after fixing background CPU contention remains to be run.
- Verified existing Puzzle #71 campaign: **520 completed chunks**, **545,259,520 unique completed keys**, **0 recorded recovery restarts**, **no hit** at October 14 test. Preserve its SQLite DB, Feistel seed, immutable config and ordinal cursor; never rerun `init` to resume.
- Domain `[2^70,2^71)`, chunk `2^20`, `2^50` chunks, scrambled by bijective seeded Feistel; within chunk, scalar step 1, true compressed Y parity. **Disjoint internally** does not mean disjoint against other miners.
- Four-job C++ bounded queue, continuous four-thread slice claims, ordered results, SQLite checkpoint; at most four uncommitted prefetched jobs may replay after a crash. Both single-window and four-window interrupted Puzzle #20 exhaustive coverage cases passed GitHub ARM64 and actual Pi testing, as of October 14.
- All node/pool services remain disabled by default. Do not merge PR #1 or activate systemd services without the owner's explicit approval. Never expose candidate private keys in dashboard, alerts, logs or Git.
- Never report raw hash counts (including two-parity or transformed-out-of-range hashes) as distinct in-range scalar coverage. Separate campaign progress from speculative/replayed computation.

## Gate P0: safe start (required before unattended operation)

| Deliverable | Current state | Acceptance |
|---|---|---|
| Pipeline sustained speed | Unconfirmed at normal idle Pi load | Repeat 512-job 60s A/B/C benchmark, log environment, compare SQLite end-to-end completed keys/s to standalone; target <5% slowdown |
| Crash/reboot correctness | Synthetic/fault-injection passed, Pi reboot/power loss not tested | On disposable DB test SIGINT, SIGTERM, SIGKILL, worker death, restart and full reboot at 1/4-job windows. Never lose or count uncommitted work; document maximum replay |
| Stable disabled-by-default user service | Example `pool/keypoold.service.example`, not tested live | Install only by explicit action; verify manual start/stop/status, clean shutdown, watchdog/restarts, process group cleanup, idle scheduling, log bounds, no orphan worker, and behavior after reboot with service still disabled |
| Real-time process health | DB `status` provides only cursor/inflight/found/restart count | Lightweight local read-only heartbeat: controller alive, worker PID, last completed job timestamp, 1m/15m/24h *unique completed* keys/s, committed/queued work, stall/timeout and last error, temperature/frequency and remaining disk |
| Reliable hit handling | Independent HASH160 recheck + `FOUND.private` 0600 implemented | Re-test atomic private-file creation + fsync of directory, idempotent restart, no key in stderr/stdout/systemd/email/dashboard. Gracefully stop all prefetch and freeze campaign on a verified match |
| Notifications | Not implemented | Send phone push: found, daemon stopped/stalled, repeated crash, campaign target spent, persistent health degradation. **No secret, candidate range or signed raw transaction in alert**. Retry idempotently until acknowledged. Test with solved Puzzle #20 and simulated failure |
| Monitor target | Manually checked status | Poll public Puzzle #71 balance/UTXO and pubkey-reveal status cautiously; stop/switch strategy if prize spent or public key exposed. Cached/verified chain data, not a single explorer source |

**Release criterion:** after these P0 tests, start the real `run` campaign manually under a supervised, disabled-by-default unit and soak 24–72h. Preserve main/old standalone binary for immediate rollback; confirm committed cursor monotonicity, no new worker log secret, bounded RAM/log/disk, no interference with other Pi node/pool services.

## Gate P1: claim and private submission route (important before relying on any lucky discovery)

There is no central "submit solution" API guaranteeing payout: claiming Puzzle #71 requires spending the actual Bitcoin UTXOs. A public legacy-P2PKH spend reveals the pubkey and can be outbid/replaced. Normal Bitcoin Core `sendrawtransaction` announces a transaction to peers; `submitpackage` is **not a private miner submission path**.

1. Prepare a cold receiving address and offline-safe transaction template containing **no secret**: documented target UTXOs (txids/vouts/value/script), current fee policy, destination, change policy (prefer sweeping all spendable target UTXOs), anti-RBF/race decision and fee bounds.
2. Build restricted local signing capability that converts the verified private scalar to the correct compressed key/WIF **inside a protected process**; sign only intended puzzle UTXOs; verify signed inputs, destination and fees; do not put WIF in command-line arguments, logs or remote APIs. Offline/private regtest simulation first.
3. Test `testmempoolaccept` policy against a representative non-secret regtest transaction, then end-to-end with a fresh synthetic funded regtest P2PKH wallet. Avoid broadcasting any actual key or puzzle transaction during tests.
4. Investigate actual **direct miner/private relay** access, pricing and availability before calling it an option; fail explicitly if no verifiable private path exists. A normal public broadcast remains a risk, never promise sniping prevention.
5. Decide explicitly whether signed broadcast is automatic or requires owner confirmation; whichever is chosen, the machine must handle a verified hit immediately and persist evidence of the action **without exposing secrets**. Don't block safe detection/notification on a third-party service.

## Gate P2: operations dashboard (phone-first, read-only)

Reuse the Pi's existing Grafana + InfluxDB installation where useful, or a lightweight static/status JSON endpoint bound only to loopback/Tailscale. Never expose RPC or the dashboard publicly, and don't put `FOUND.private` into metrics.

- Live service/worker state; job queue occupancy; last-job timestamp; unique committed Mkeys/s (instant, 15m, 24h), attempted/replayed estimate separately.
- Total committed chunks/keys, absolute and percentage coverage (tiny percent; use scientific notation), Feistel campaign ID/version (not seed), operational uptime, restarts, lost/stale heartbeat.
- CPU clock/load/temp/throttle; disk free and SQLite integrity-check age; software commit/version; expected next check/last backups.
- Hit banner and action state only, without key. For mobile display, four primary indicators: RUNNING / LAST COMMIT / 15m KEYS/s / ALERT.
- Verify read-only endpoints do not delay hashing or lock the writer; sample no faster than needed.

## Gate P3: other hunters and search-space allocation

- **Not a mathematical optimization:** avoiding verified external work can only reduce known overlap. The source at `btcpuzzle.info/puzzle/71` reported ~332,375 / 33,554,432 very large ranges (~0.99%) on 2026-10-14, **self-reported and not independently audited**. Other miners are unknowable.
- Investigate exact public export/bitmap or authenticated APIs and range semantics from btcpuzzle.info, btc-puzzle.com and other coordinators. Read-only by default; never submit private key, campaign seed, or own candidate ranges.
- Only exclude ranges that have dated, source-specific *machine-readable bounds* and credible coverage evidence. External "scanned" must be tracked separately from **our own** completed keys, never silently added to `unique_completed_keys`.
- Our permuted `2^20` chunks subdivide third-party `2^45` ranges. Mapping is straightforward by numeric intervals but requires a separate versioned external-exclusions layer and a migration test. **Do not alter seed, current cursor, or mark skipped intervals internally as hashed**.
- Optional coordination via a cooperative pool requires explicit privacy/proof/reward trust analysis and a decision to opt in. Proactive collision avoidance is impossible for private independent hunters. Unknown global coverage remains unknown.
- Design long-term choice with a quantified gain estimate vs complexity: ~1% of known externally declared space alone is not worth jeopardizing checkpoint truth.

## Gate R: research and acceleration, independent of production

### R1: low-risk exact-coverage performance work (bench one change at a time)
- Hoist invariant `4*stride` multiplication from each four-key inner loop.
- Precompute negative Y of immutable generator points.
- Skip per-lane target-check loop entirely on NEON four-way zero mask.
- Rebenchmark practical job/slice sizes and short-worker wakeups **without sacrificing bounded crash replay or stop latency**.
- Use exact oracle / recovered-key fixtures, PMU counters and 120s repeated Pi A/B; promote only gains beyond noise. Keep proven standalone and worker builds accessible.

### R2: higher-risk mathematics/implementation, still computing every required HASH160
- Profile branch-misses and canonical modular subtraction, test constant-time/masked AArch64 field subtract as an *isolated* kernel (validate aliases and carries).
- Investigate cache/memory movement from full `Point` XY+Z structures; compact affine XY batching, fused SHA256→RIPEMD160 buffering/byte-swaps, new 5x52 or projective/batched-inversion tradeoffs.
- No shortcut from GLV endomorphism or Pollard/BSGS/x-point without a usable target public key. Transformed curve points are mostly outside the bounded 71-bit scalar domain; don't call them distinct Puzzle #71 trials.

### R3: high-upside structural origin research (pre-register hypotheses)
- The puzzle creator's *forum statement* says consecutive keys from a deterministic wallet were masked with leading bits to establish difficulty. That does **not** identify wallet algorithm, seed, or a pattern in post-mask keys. Investigate 2015-era deterministic wallet implementations as an archaeological question: precise KDF, child index, masking operators, software versions and early on-chain evidence.
- Assemble **independently validated** solved-puzzle private keys and target public representations. Train/fit a candidate family only on a subset; reserve unseen solved keys for blinded predictions of their low bits. Compare against a uniform 1-bit-per-puzzle baseline and adjust for multiple hypotheses. Require reproducible predictive evidence *before* targeting any special subrange of #71.
- If source randomness is cryptographically sound, masked outputs reveal only truncated pseudorandom words and are not a realistic seed-recovery shortcut. Search for **specific** weak KDF/PRNG implementations, leaks or derivation reuse, not generic "pattern detection." No fabricated Bayesian advantage from small solved-key datasets.
- Watch the target on-chain: if its public point is revealed but balance remains, new discrete-log algorithms become relevant. Evaluate available cost/correctness then; do not claim Kangaroo now.
- GPU/ASIC/co-processor experiments need apples-to-apples true scalar-HASH160 candidates/s and costs (power, capital, time). Generic bitcoin SHA256d ASICs don't accelerate secp256k1 + HASH160.
- The production Pi runs independently while experiments happen in separate binaries/process priorities. Do not introduce speculative search policies into the durable campaign without formal acceptance.

## Suggested execution order

1. Finish 512-job uncontended benchmark; fix any uncovered throughput gap.
2. Implement safe hit alert + local heartbeat and crash-tested disabled service. Begin monitored real #71 run; no unexpected service autoenable.
3. Prepare and regtest the transaction signing/claim path in parallel, prioritizing reliable ownership of any reward.
4. Add phone-friendly dashboard from existing Pi Grafana/Influx setup; read-only via private access.
5. Research external shared-range data and quantified overlap. Introduce optional versioned exclusion only on strong evidence.
6. Run R1 arithmetic cleanups as reversible A/B experiments; run creator/KDF inference as an independent, high-risk high-upside research stream.

## Primary reference sources (verify freshness)

- [Original repo's search-space audit](../research/2026-10-11-keyhunt-modes-and-search-space.md)
- [Optimization opportunities](../research/2026-10-11-pi5-architectural-audit.md)
- [GPU implementation audit](../research/2026-10-11-gpu-source-audit.md)
- [Current working production contract](PRODUCTION_SEARCH_POLICY.md)
- [Puzzle #71 public status](https://needlespace.com/en/puzzle/71)
- [btcpuzzle.info #71 reported coverage](https://btcpuzzle.info/puzzle/71) and [API documentation](https://btcpuzzle.info/api-documentation)
- [Bitcoin Core `sendrawtransaction`](https://bitcoincore.org/en/doc/26.0.0/rpc/rawtransactions/sendrawtransaction/) and [`testmempoolaccept`](https://bitcoincore.org/en/doc/27.0.0/rpc/rawtransactions/testmempoolaccept/)
- [Original creator wallet-description quoted in BitcoinTalk](https://bitcointalk.org/index.php?topic=1306983.10680)
