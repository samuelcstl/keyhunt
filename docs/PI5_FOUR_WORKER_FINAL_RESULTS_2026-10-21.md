# Final four-worker Pi5 comparison, 21 October 2026

## Verified archive and provenance

- Archive: `four-worker-final-results-20261021T151713Z-29832.tar.gz`.
- Whole archive SHA256: `d94d133661f291e59944a8024a36420118ceae9a17db80bfa759eb571bdb580c`.
- **123/123 SHA256SUMS files PASS**, source commit
  `ccd612348e2adfc1ee9e41a18779d58c74cc3fec`;
  run completed at 2026-10-21T15:26:50Z, exit code 0.
- **20/20 scratch SQLite databases PRAGMA quick_check=ok**: four warmups
  at `next_i=8`, 16 measured observations at `next_i=96`; all
  `inflight=NULL`, `reissued=0`, `found=0`, and identical synthetic
  128-bit Feistel seed. Only 16 runs count toward performance.
- Genuine cgroup `cpu.max=150000 100000` (=150% CPU), four Pi5 A76
  cores, four worker processes in turn. ARM clock sampled near 2.4GHz,
  `throttled=0x0`. No thermal throttle.
- Production SQLite was **not opened by the qualification script**.
  Stat-only comparisons show unchanged size 8192 bytes and
  mtime 1791918358370048515 ns before/after. This is not a proof
  against concurrent external access.
- The host was running concurrent workloads during testing. Their CPU
  demand varied across rounds, so small throughput differences may
  reflect normal scheduling noise.
- Each measured observation completed 96 × 2^20 = 100,663,296
  distinct Puzzle71 candidate scalars in a fresh SQLite. Each variant
  revisited the **same synthetic subset**, so these results must not
  be summed to claim new unique Puzzle71 search coverage.

## Actual performance, full Keypool / SQLite at 150% CPU

| Worker | Mean Mkeys/s | Median Mkeys/s | Paired median vs R3 | Wins vs R3 |
|---|---:|---:|---:|---:|
| R3-SCHED | 2.876314 | 2.876240 | reference | — |
| R7-PAIR-OFF | **2.897459** | **2.902530** | +0.560% | 3/4 |
| R7-FOLD-OFF | 2.891093 | 2.896172 | +1.058% | 3/4 |
| R2-SRI | 2.847175 | 2.843092 | −0.807% | 1/4 |

Paired R7-PAIR vs R7-FOLD changes per round were:
**+0.312%, −1.293%, +0.147%, +1.738%**; median **+0.230%**,
3/4 wins. This is too small and noisy to claim PAIR outperforms FOLD
in production. Both R7 variants are credible, but FOLD has previously
passed additional six-pair direct worker testing (+0.614% median
vs R3) and a separate scratch SQLite 150% quota A/B (+1.422%
median vs R3).

## Proposed production decision

Select **R7-FOLD non-instrumented** initially at 150% CPU, with
R7-PAIR-OFF as an easy alternate and R3-SCHED as fallback.
Avoid more benchmarking before first production activation.
Record the exact built binary's SHA256 on Pi. The FOLD executable in
this archive is reported as
`603133623f8a9aaa841041ccad40626f8f2a33308c381a8cf8ed7e75206ef959`;
the archive includes a copied ELF, so check its SHA256 when deploying.
Do not overwrite any live program or start the systemd service during
main-branch consolidation.

Critically: **the first real deployment is separate from this research
merge**. It must pin code and ELF artifacts, use a configurable
`--worker`, preserve the existing campaign's seed and cursor,
protect any discovered secret, and have a reversible user-systemd
unit disabled by default until manual post-deploy validation.
