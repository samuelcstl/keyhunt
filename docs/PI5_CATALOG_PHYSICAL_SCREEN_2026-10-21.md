# Pi 5 physical catalog screening, 21 October 2026

## Provenance and integrity

- Archive: `arm64-catalog-results-20261021T141530Z-2532681-all.tar.gz`.
- Archive SHA256:
  `461a34d4a16e3b8d803436c6e08d4d0a27edb342b2533f88d8801b18ed19204a`.
- Captured source commit:
  `93718885348b4aaf1d3ac91d4e8f66e3fc237f96` (PR #14).
- Complete run, `exit_code=0`, `status=completed`;
  completed UTC 2026-10-21 14:25:43.
- SHA256SUMS: **93/93 pass** on the included files.
- Provenance includes per-binary SHA256 for all 23 executables, but
  **the executables themselves are not included** in this compact TAR.
  Therefore their bytes cannot be reverified from this archive alone;
  hashes remain useful for checking against binaries retained on the Pi.
- Raspberry Pi 5, aarch64 Debian, GCC 14.2.0, clock sampled near 2.4 GHz,
  `throttled=0x0` on all sampled observations; measured temperatures
  55.4–64.2 C. Blockchain nodes, ckpool and Chromium remained active.
- All 23 catalog entries have two observations. `results.tsv` has
  74 lines of data: 28 worker throughput rows, 12 pipeline rows and
  34 field/microbenchmark subvariant rows. All 46 catalog
  entry × repeat combinations completed.

## Ranked full Keypool workers, instrumentation OFF

Each throughput number is in **millions of completed Puzzle71 candidates
per second**, average of **two** 64 × 2^20-key runs; *not* a sustained
production rate, and not a statistically robust ranking.

| Variant | Pass 1 | Pass 2 | Mean |
|---|---:|---:|---:|
| R7-PAIR-OFF | 7.18252 | 7.31563 | **7.24908** |
| R2-SRI | 7.27534 | 7.11578 | 7.19556 |
| R6-FOLD | 7.22099 | 7.14848 | 7.18473 |
| R3-NEON | 7.12209 | 7.18819 | 7.15514 |
| R7-SCHED-OFF | 6.98667 | 7.29566 | 7.14116 |
| R7-FOLD-OFF | 7.22255 | 7.01032 | 7.11644 |
| R2-SLI | 6.90666 | 7.13523 | 7.02095 |
| R1-ALL | 6.97793 | 6.99916 | 6.98854 |
| R3-SCHED | 7.17706 | 6.77652 | 6.97679 |
| R6-PAIR | 7.03036 | 6.92298 | 6.97667 |
| R0 baseline | 6.79461 | 6.85548 | 6.82505 |

**Do not change production selection based on these 2-pass rankings.**
The order effect is substantial: R7-PAIR is below R7-FOLD on pass 1
but ahead by 4.36% on pass 2; R3-SCHED falls to 6.77652 M/s
on the second pass. These variations are larger than the proposed
sub-2% improvements. Earlier sustained physical R7-FOLD vs
R3-SCHED Gate 1 and scratch SQLite 150% Gate 2 remain valid, but
the new short screen suggests **R7-PAIR-OFF and R2-SRI** deserve
inclusion in a final focused matched-chunk head-to-head.

## Explicit profiling ON/OFF

Four R7 stage timing rows were emitted per profiled observation;
non-profiled worker observations have zero `R7_STAGES` rows.

| Algorithm | Profile ON | Profile OFF | OFF vs ON increase |
|---|---:|---:|---:|
| R7-SCHED | 7.18539 | 7.14116 | −0.62% |
| R7-PAIR | 7.14224 | 7.24908 | +1.50% |
| R7-FOLD | 7.18131 | 7.11644 | −0.90% |
| R8 pipeline (width 16) | 2.18758 | 2.45740 | **+12.33%** |
| R9 pipeline (2 ECC producers, width 16) | 2.71171 | 3.21777 | **+18.66%** |
| R10 pipeline (3 producers / 2 consumers, width 16) | 2.68727 | 3.43500 | **+27.82%** |

The pipeline improvement direction appears in both individual repeats,
supporting substantial instrumentation overhead when clocks are used
in the producer/consumer/queue hot path. The R7 stage-profiled
ON/OFF differences are inconsistent (two profiled builds show
higher rates), so do not claim profiling *improves* R7 or compute
a precise stage overhead from this two-repeat screen.

R8/9/10 are **standalone experimental engines**, not Keypool JSON
workers. Their Mhash/s and Keypool completed keys/s should not be
ranked against each other as production choices.

## Arithmetic-only findings

- R4 fastest field multiplication: native 4x64,
  **15.61985 million field products/s**. No direct production
  Keypool gain is inferred.
- R5 paired field chain: `4x64-pair-fold` about
  **15.48556 million MUL-equivalents/s**, against
  `4x64-ref` around **14.35332 million/s** in that
  standalone microbench. This is algorithm-specific;
  it does not predict the complete worker's throughput.
- R8 segmented inversion scan: best tested segment width 2,
  **5.13655 million denominators/s**; the variants
  span approximately 5.00–5.14 million. No convincing
  system-level breakthrough from this isolated measure.

## Next engineering decision

Preserve all variants and the explicit `--worker` selector. Keep
the catalog and profiled/unprofiled executable pairs. Run **one
focused physical paired round-robin** of R7-PAIR-OFF,
R7-FOLD-OFF, R2-SRI and R3-SCHED on identical Puzzle71 chunks
with reversed/randomized order and longer windows, ideally under
the intended production CPU quota using scratch SQLite.
Record exact ELF hashes and do not overwrite the live Keypool campaign.

This is a **successful screening and instrumentation audit**, not a
production-worker promotion verdict.
