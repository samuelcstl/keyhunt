# Physical Pi 5 R5 ECC native ILP and resident-NEON results, 2026-10-18

**Outcome:** native 4×64 paired multiplication is a genuine promising
microkernel candidate; **+7.53%** for paired/first-fold and **+6.71%**
for paired/standard fold in the 8-MUL, 2-independent-chain screen.
**No direct claim of +7.5% completed Bitcoin Puzzle keys/s.**

## Forensic evidence

User-submitted `r5-ecc-results-20261018T163146Z-777466.tar.gz`,
SHA256 `5361814388235fdc930ba628d8dedd79e31b2327a52138d3005c46b4b1becac5`.
All **18/18** in-archive `SHA256SUMS` entries verified, and binary
SHA was captured. Source commit
`f27840108dfd4913fd9e21cef2a54d1d13d70057`.
Run status `completed`, exit 0.
GCC 14.2.0, AArch64 Cortex-A76, Linux `6.18.50+rpt-rpi-2712`,
`-O3 -mcpu=cortex-a76 -flto`.

Correctness:
- 2,100 differential pairs of 8-deep field chains PASS, five variants.
- 2,560 independent Python bigint modulo-p 8×MUL chains PASS.
- Source and linked ARM64 disassembly archived.

## One-second matched, reverse-order field arithmetic runs

Two lanes × eight dependent multiplications, 2 passes per kernel.

| Variant | Pass 1 mul/s | Pass 2 mul/s | Median mul/s | vs 4x64-ref |
| --- | ---: | ---: | ---: | ---: |
| 4x64-ref | 14,457,495 | 14,344,066 | **14,400,781** | reference |
| 4x64-fold | 14,554,190 | 14,591,197 | **14,572,694** | **+1.19%** |
| 4x64-pair-ilp | 15,355,315 | 15,378,253 | **15,366,784** | **+6.71%** |
| 4x64-pair-fold | 15,445,172 | 15,525,215 | **15,485,194** | **+7.53%** |
| 10x26-resident | 10,874,049 | 10,804,906 | **10,839,478** | **-24.73%** |

Pairs remain in the same radix throughout all eight operations. The
NEON experiment avoids intermediate radix conversions yet remains
slower than scalar 4×64. Compared to R4's single-conversion-per-MUL
reference-style design, this is a more meaningful test of residency,
but it is **not** an optimized ECC point-inversion/SoA implementation.

The scalar pair winner performs two independent 4×64 row products
with their carry chains **interleaved**; both still use native
`MUL/UMULH` instructions. First-fold specialization alone provides
only +1.19% on Pi, despite previous CI runner's different +5.34% short
screen. This difference is why physical evidence matters.

## Measurement limitations

- 1 second × 2 is a **directional screen**, not a confidence interval
  for a 1–2% improvement.
- Initial `vcgencmd measure_clock arm` showed **1.90 GHz** at
  idle/start; post-run sampled **2.40 GHz**. No per-variant frequency
  logging exists in this short script, so **clock constancy during every
  observation is not proven**, despite no throttling flags.
- Start/end temperature 47.2/49.9°C, `throttled=0x0`.
- Other bitcoind, ckpool, alt nodes, system daemons were running at
  low sampled utilization. CPU affinity and current contention
  not controlled.
- No `perf stat` PMU counts; entire linked assembly preserved but
  attribution of saved cycles is not independently established.
- Field MULs/s is not full Keyhunt completed keys/s. The Hot ECC path
  has other field SQR, adds, batch inversion and SHA/HASH160 overhead.
- Native original `field_k1_arm64_mul` and tested R5 paired
  product are not identical compilers' entry/inline circumstances;
  the full-worker A/B is essential.

## Next gate, now implemented separately

A draft R6 worker integration branch experiments ONLY on the two
independent +/- affine slopes already adjacent in the R3 SCHED point
loop, with paired 4×64 multiplication and paired/first-fold variants.
It retains the same R2 SRI hashing and R3 point structure.
Before throughput:
- Different native ARM64 binary and isolated object names
- 51,000 exact native modular product triples with boundary cases
- Puzzle20 solved fixtures, 71/140/256 bit parities
- Scratch SQLite 524,288-key exhaustive coverage, crash replay
- Real four-thread persistent worker JSON same synthetic-seeded
  key chunks with short **32-job × 2 reversed** paired A/B.
- Automatic failure-safe tar.gz and SHA256 checksum.
- No production Keypool, worker, nodes, or pools touched.

**Accept the R5 ILP idea as worth full-worker testing; do not promote
R5/R6 based on 7.53% isolated field throughput.**
