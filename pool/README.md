# Keypool KISS v1 (experimental)

Local Puzzle #71 search controller. **Nothing is installed or started by cloning/building.**

- `keyhunt-worker`: dedicated ARM64/NEON executable, one persistent process, four CPU threads, exact bounded jobs over stdin/stdout JSON.
- `pool/keypoold.py`: one seeded 50-bit Feistel schedule and **one SQLite campaign row**. One job in flight; acknowledgement advances the cursor atomically. A crash replays at most that job.
- No API, network listeners, untrusted workers, payouts, GPU support or dashboards. The legacy Keyhunt binaries remain intact.

## Pi 5 first check

From the working `perf/pi5-arm64` branch:

```bash
make arm64-worker-test
python3 tests/keypool-controller.py
python3 tests/keypool-integration.py
```

The worker test scans synthetic bounded ranges and recovers **solved Puzzle #20**. It checks protocol purity, match handling and slice allocation. Controller tests run against a deliberately failing fake worker to prove uncommitted-job replay.

### Full solved-puzzle coverage audit

```bash
make arm64-worker
python3 tests/keypool-puzzle20-exhaustive.py
```

This is deliberately **isolated from the real Puzzle #71 campaign**. It creates and deletes a temporary SQLite database and target file. A fixed 6-bit seeded Feistel permutation dispatches all 64 disjoint 8,192-key chunks of solved Puzzle #20 (`[2^19,2^20)`). The known key is deliberately scheduled for the last chunk so all 524,288 candidate scalars must be processed.

The test captures per-ECC-group trace markers **after the SHA256/RIPEMD160 work**, compares the 512 completed 1,024-key groups with an independent exact-coverage oracle and checks all 256 thread slice assignments. It intentionally interrupts after one complete but **uncommitted** job, then checks that *only that one chunk* is replayed, no other key ranges overlap and the checkpoint ultimately records the solved key. The trace is enabled for this test only and must **not** be used for performance benchmarking.

The test is also part of ARM64 CI. Your existing `~/.local/state/keypool/campaign.sqlite3` cursor, seed and worker logs are untouched.

Only after those tests pass:

```bash
python3 pool/keypoold.py init
python3 pool/keypoold.py status
python3 pool/keypoold.py run --max-jobs 8
python3 pool/keypoold.py status
```

`init` is one-time and refuses to replace an existing campaign. It requires the expected #71 address to be present in `~/BITCOIN_ANALYSIS/bitcoin-puzzle/runs/bench71/target.txt`. The default DB is `~/.local/state/keypool/campaign.sqlite3`. Its parent directory has owner-only permissions. Jobs run in a low-level subprocess; no systemd unit is installed or enabled in v1.

For subsequent searches, invoke `run` again; the same seed and completion index are retained. Omit `--max-jobs` for continuous scanning after Pi validation. The controller rejects a second instance through a lock.

## Wire contract

Worker executable command (already started by the controller):

```bash
./keyhunt-worker -m address -f /path/to/target.txt -l compress -t 4 -n 0x40000 -q -s 0
```

stdin, one line per job, hex interval end **exclusive**:

```json
{"id":7,"start":"0xd0000","end_exclusive":"0xe0000"}
```

stdout, one line per response:

```json
{"type":"complete","id":7,"count":65536}
```

A verified match produces `type=hit` and a private key field on the **local pipe**. The controller independently verifies the compressed address before storing `FOUND.private` with `0600` permissions. Never forward this response into general logs. Other startup diagnostics and optional allocation traces go to stderr. `KEYHUNT_WORKER_TRACE=1` is for tests only.

## Limitations and gates

- No production guarantee before CI and physical Pi validation. Source-level range allocation traces establish slice partitioning; cryptographic hit tests and crash-injection tests are mandatory checks, not substitutes for exhaustive independent scalar traces on tiny intervals.
- SQLite confirms completed **jobs**, assuming the local validated worker scans every assigned scalar. It is not proof-of-work against a dishonest remote worker.
- Owner must check whether #71 is still unsolved and whether its public key remains unknown before prolonged execution.
- Existing `-R` research searches are **not** incorporated into this campaign ledger. No retroactive unique-coverage claim.
- For unattended deployment, add a manually controlled unprivileged `systemd` service only after sustained Pi 5 and graceful-stop tests. Service must remain disabled by default.

Authoritative limits and criteria: [production search specification](../docs/PRODUCTION_SEARCH_POLICY.md).
