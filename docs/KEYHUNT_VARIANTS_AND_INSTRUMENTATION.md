# Keyhunt Pi 5: workers, experiments and production selection

Status: consolidated **research + qualification** branch, 21 October 2026.
Fork: `samuelcstl/keyhunt`. Everything is disabled until deliberately run.
The existing `keyhunt-worker`, SQLite schema/seed/cursor and default
`pool/keypoold.py --worker` path remain untouched.

## One tree, independent executables

The research PR chains diverged after R3. This branch contains BOTH:
R4→R5→R6→R7 and R8→R9→R10, plus the R3-vs-R7 physical qualification
from draft PR #12. Reusing an old benchmark does not make it a
production-compatible binary.

| Build target | Keypool JSON worker? | R7 stage counters compiled? | Evidence / role |
|---|---|---|---|
| `keyhunt-worker` | Yes | No | Unchanged default/rollback |
| `keyhunt-worker-r1` | Yes | No | R1 experimental |
| `keyhunt-worker-r2-ripemd-sri` / `-sli` | Yes | No | R1+R2 |
| `keyhunt-worker-r3-ecc-sched` | Yes | No | R1+R2-SRI+R3; reference |
| `keyhunt-worker-r3-ecc-neon` | Yes | No | R3 NEON, head-to-head −0.307% paired median against SCHED |
| `keyhunt-worker-r6-ecc-pair` / `-fold` | Yes | No | R6 hot-path experiment, NOT promoted |
| `keyhunt-worker-r7-ecc-sched` / `-pair` / `-fold` | Yes | **Yes** | Historical **profiled** binaries only; do NOT throughput-rank versus unprofiled workers |
| `keyhunt-worker-r7-ecc-sched-unprofiled` | Yes | **No** | New equivalent for fair comparison, physical throughput pending |
| `keyhunt-worker-r7-ecc-pair-unprofiled` | Yes | **No** | New equivalent for fair comparison, physical throughput pending |
| `keyhunt-worker-r7-ecc-fold-unprofiled` | Yes | **No** | Best measured R7 candidate, small positive worker and SQLite A/B |
| `build/arm64/ecc-radix-screen` / `ecc-r5-chains` | **No** | N/A | R4/R5 microbench only |
| `build/arm64/r8-affine-batchscan` | **No** | N/A | ECC inversion research only |
| `build/arm64/r8-ecc-hash-pipeline` | **No** | Dedicated timing counters | R8 producer/consumer benchmark |
| `build/arm64/r9-multi-pipeline` | **No** | Dedicated timing counters | R9 producer scaling benchmark |
| `build/arm64/r10-oversub-pipeline` | **No** | Dedicated timing counters | R10 oversubscription benchmark |

**Instrumentation caveat:** the historical R7 workers were compiled
with `KEYHUNT_R7_STAGE_STATS`; setting
`KEYHUNT_R7_STAGE_PROFILE=0` only suppresses output, NOT timers, since
the code checks whether the environment variable exists. Therefore
historical R7-SCHED and R7-PAIR negative A/Bs against uninstrumented R3
must NOT be used to rank variants. R7 FOLD was retested with the
unprofiled binary. R8–R10 measure queue and stage timings in their
**standalone benchmark executables** by design; these are not Keypool
workers. The resulting R10 ~2.9M/s cannot be directly ranked against
the full 4-core Keypool worker (~7.3M/s).

## Safe compilation and correctness checks on Raspberry Pi 5

```bash
make -j2 arm64-r3-ecc arm64-r6-ecc arm64-r7-unprofiled-variants
make arm64-r7-unprofiled-variants-test
make -j2 arm64-r8-affine arm64-r8-pipeline arm64-r9-pipeline arm64-r10-pipeline
make arm64-r8-affine-test arm64-r8-pipeline-test arm64-r9-pipeline-test arm64-r10-pipeline-test
```

Build products remain separate. The default `keyhunt-worker` target
is not aliased to R7, and building the new targets does not launch a
Keypool search or any blockchain service.

### Explicit production selection, with rollback

Keypool already supports `--worker`. **Do not initialize a second
real campaign or edit the existing SQLite cursor**. Future service
`ExecStart` should use the **absolute path** to a locally verified
worker and a pinned source commit / ELF SHA256 in its deployment notes:

```bash
# INSPECTION ONLY: see the binary hash and immutable DB state.
sha256sum ./keyhunt-worker-r7-ecc-fold-unprofiled
python3 pool/keypoold.py status

# Example of the future explicit invocation, NOT a command to start now:
# python3 pool/keypoold.py run --db ~/.local/state/keypool/campaign.sqlite3 \
#   --worker /absolute/path/keyhunt-worker-r7-ecc-fold-unprofiled
```

The `status` command reports campaign progress, NOT the currently
selected worker. To know which binary is in use, inspect the process
command line / systemd `ExecStart`, the absolute file SHA256, and
build provenance. Merely having a binary in the repository does not
make it active. Before unattended activation, qualify the final linked
binary for Puzzle20, graceful shutdown/crash recovery and rollback;
keep systemd units **disabled by default**.

## Physical evidence

- 18 Oct R3 standalone: NEON 7.421 vs SCHED 7.375 Mkeys/s; the
  8-pair *real-worker* head-to-head favored SCHED 7/8.
- 21 Oct R7-FOLD **unprofiled** worker: 6/6 positive pairs against
  R3-SCHED, +0.614% paired median (256 × 2^20 keys per observation).
- 21 Oct real `keypoold` on **separate scratch SQLite databases**
  under actual 150% CPU quota: R7-FOLD 3/4 positive pairs, +1.422%
  paired median (128 × 2^20 committed keys per observation).
- This is a small and still noisy performance advantage; no universal
  speedup claim. See `docs/PI5_R7_PRODUCTION_QUALIFICATION_2026-10-21.md`.
- R7-SCHED and R7-PAIR **unprofiled** have not yet been measured on
  the physical Pi; keep as candidates.
