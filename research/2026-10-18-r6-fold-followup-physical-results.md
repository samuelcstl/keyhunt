# R6 pair + fold: four-pair physical Pi5 follow-up, 18 October 2026

## Decision: STOP / DO NOT MERGE R6 speed optimization

The latest repeated worker comparison **rejects the R6 paired native
field-multiplication + early-fold implementation as a throughput winner**.
Compared with the identical R3-SCHED worker, R6 was slower in **all four**
reversed-order paired runs, **-1.8845% median**.

This supersedes the earlier inconclusive two-pair R6 screen where pair+fold
appeared +1.43% (2/2 wins). The later four-pair result and baseline drift
show that positive short-run result was not reproducible. The R5
field-MUL microbenchmark +7.53% did NOT translate to faster Keyhunt.

R6 stays draft/research evidence, should NOT be promoted into the
default Keyhunt worker or the live SQLite Puzzle 71 campaign.
Prioritize bigger ECC dependencies, field reduction or group inverse next.

## Reproducible evidence and integrity

User-provided archive
`r6-fold-followup-results-20261018T171711Z-887879.tar.gz`.
SHA256:
`9a3ea9f2159410f7bc5713d385fe7e885891cf13c1812b611dd358419a096e81`.
Inner `SHA256SUMS`: **29/29 OK**, no mismatches.
Includes full disassemblies, original source snapshots, exact compiled
ELF worker binaries, binary SHA256, TSV/JSON benchmark data,
host/process observations and run status.
Run `20261018T171711Z-887879` finished with status `completed`,
exit code 0. Tested commit:
`c2957e73ad9897e7e725ba128149bdf9289f08cd`.
GCC 14.2.0, Linux `6.18.50+rpt-rpi-2712`, Raspberry Pi 5
4×A76. Binary worker digests are recorded in
`worker/paired/provenance.json`.
An unchanged 51,000-triplet exact native ECC multiplication oracle PASS
was re-run.

## Real persistent four-core worker

Each treatment completes exactly **67,108,864 candidate keys**
(64 × 2^20) through the real four-job prefetch JSON-worker protocol.
Identical preselected synthetic chunk ordinals, scratch directories,
no persistent production campaign. Four *paired* repetitions, with
alternating control/candidate order (ABBA-like order over pairs).
All eight observations succeeded.

| Pair | R3-SCHED Mkeys/s | R6 pair+fold Mkeys/s | Candidate vs control |
| --- | ---: | ---: | ---: |
| 1 | 7.389550 | 7.373734 | **-0.2140%** |
| 2 | 7.409430 | 7.277578 | **-1.7795%** |
| 3 | 7.337756 | 7.191775 | **-1.9895%** |
| 4 | 7.374590 | 7.210288 | **-2.2279%** |

**Paired median: -1.8844866% (0/4 wins)**. Across all observations
R3 control median 7.382070 Mkeys/s and candidate median
7.243933 Mkeys/s (not directly interchangeable with paired median).

Control varies by **0.97% peak-to-peak / average**; R6 candidate
by **2.51%**, suggesting a candidate more sensitive to workload,
scheduling or process noise. These observations cannot attribute
the cause. They do establish sufficient practical evidence to park
this candidate rather than spend on expensive qualification.

Frequent `vcgencmd` before/after samples were ~2.4 GHz on ARM,
temperature ~49.9–59.8 C during the eight observations,
`throttled=0x0` throughout. Per-core PMU/occupancy
and continuous clock records were NOT collected.
Other node, mining pool and system services continued running;
CPU isolation was not proven.

## Machine code verification

Exact compiled worker disassembly:

| Static (not dynamic) instruction count | R3-SCHED | R6 pair+fold |
| --- | ---: | ---: |
| `thread_process(void*)` | 6040 | 6025 |
| `field_k1_arm64_mul` | 148 | 148 |
| `field_k1_arm64_square` | 140 | 140 |
| `GetHash160_fromXYParityTarget` | 1863 | 1863 |

`thread_process` still contains 188 static `MUL` and
188 static `UMULH` instructions in both versions.
Thus R6 did not skip ECC work or change the hash algorithm.
**15 fewer static instructions in the large function is not
proof of a lower executed instruction count or shorter dependency
chain.** The genuine paired reduction may lengthen hot-path latency,
alter inlining/register pressure, or introduce overhead; identifying
the exact cause would require focused PMU + perf annotate, not justified
for a consistently losing low-gain candidate.

## Proposed engineering transition

- Stop the R6 optimization branch at draft; preserve source, tests,
  negative results and archive provenance, **do not merge**.
- Keep R3-SCHED as best currently qualified ECC control, with R2-SRI
  rotation and all existing correctness/Keypool invariants.
- R7 should profile `IntGroup::ModInv()` and `Int::ModMulK1()` in the
  actual batch generation, **including** the prefix/suffix product
  passes and one inversion. Measure share of cycles, field MULs and
  dependency depth before implementing a redesign.
- Screen improvements for 1–2 seconds in isolated kernels and for
  15–30 seconds in whole worker; automatically archive all files.
  Demand actual completed candidate keys/s wins, not only field
  MUL/s wins, before production promotion.
