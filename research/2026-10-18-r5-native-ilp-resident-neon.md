# R5: native secp256k1 ILP + first-fold specialization vs resident 10x26 NEON

Status: **independent ARM64 correctness PASS; Pi 5 benchmark not yet run;
not integrated with any Keyhunt worker**.

## Why this exists

R4's physical Pi screen established the generic 4×64 field MUL was
much faster than all drop-in radix variants. R4 paid conversions
for every operation. R5 explores the two justified follow-ups with
a **short, isolated, apples-to-apples arithmetic experiment**:

1. Scalar 4×64: break two independent field MUL data-dependency chains
   by interleaving them; try moving the common first carry fold out of
   the reduction's `while(carry)` loop while retaining the exact fallback.
2. Resident two-lane 10×26 NEON: convert two fields once, execute **eight
   consecutive multiplications on native 10×26 lanes**, then convert
   the final residues once to canonical 4×64. This is a real chained
   field arithmetic test, **not** an ECC point-add / inversion kernel.

Five variants share deterministic exact inputs:

| Variant | Arithmetic | Retained radix |
| --- | --- | --- |
| 4x64-ref | existing `field_k1_arm64_mul` | native |
| 4x64-fold | same schoolbook 4×64 product, first modular fold unrolled | native |
| 4x64-pair-ilp | two independent 4×64 row products interleaved | native |
| 4x64-pair-fold | both ILP and first-fold specialization | native |
| 10x26-resident | two independent 10×26 product streams, NEON `UMULL`; `2^260≡16C` folding | native 10×26 for 8 MUL |

All results are canonical modulo `p=2^256-(2^32+977)`.
The resident radix uses base `2^26` with a 22-bit top limb after
modular reduction. Intermediate residues are reduced below `2^256`
but may not always be fully canonical; this is valid because next
multiplication treats them as integers and the final output canonicalizes.

## Correctness gates

The workflow requires:

- 2,100 paired chains in the C++ native-reference differential oracle:
  every lane completes 8 MULs, across five variants and boundary/random
  values. This also tests exact field canonicalization.
- **2,560 independently checked eight-deep chained results** using Python
  arbitrary-precision modular arithmetic. It checks *every variant
  including 4×64 control*, not just equivalence to a possibly wrong
  reference:
  `result = start * pow(factor,8,p) % p`.
- Source/input/output archiving and SHA256, including nonzero failure.
- No Keyhunt worker binaries, no Puzzle #71 campaign, no services.

Native ARM64 CI run [39145093282](https://github.com/samuelcstl/keyhunt/actions/runs/39145093282)
passed all gates. The very short runner smoke (0.12 seconds × 2) showed:
`4x64-fold` **+5.34%**, `4x64-pair-ilp` **+1.02%**,
`4x64-pair-fold` **+1.40%**, and `10x26-resident` **-77.06%**
relative to original 4×64 on the GitHub ARM64 host. The CI host is not
the Pi5 and these values are **not physical performance evidence**.

## Short physical Pi workflow

```bash
cd ~/BITCOIN_ANALYSIS/bitcoin-puzzle/keyhunt
git fetch origin experiment/pi5-r5-ecc-resident-ilp-20261018
git worktree add -b pi5-r5-ecc ../keyhunt-r5 \
  origin/experiment/pi5-r5-ecc-resident-ilp-20261018
cd ../keyhunt-r5
bash tests/arm64-r5-ecc-screen.sh
```

Five variants × 1 second × two reverse-order passes = **10 seconds**
of active measurement, plus 0.08-second per-variant warmup, builds and
correctness tests. The output includes raw CSV `benchmark.csv`,
evaluation `assessment.txt`, exact source snapshot, binary plus
SHA256, full linked objdump, environmental provenance, run-status,
complete SHA256SUMS, and automatic
`$HOME/r5-ecc-results-<runid>.tar.gz` with sibling `.sha256`.
The archive is produced **also if compilation or validation fails**.

For noisy results:
`KEYHUNT_R5_SECONDS=2 KEYHUNT_R5_REPEATS=3 bash tests/arm64-r5-ecc-screen.sh`
(without touching the experiment source). Never report short-screen
field MULs/s as Bitcoin Mkeys/s.

## Important scope cautions

- Unlike full ECC, these are **independent artificial chains of 8 field
  MULs**. The actual Keyhunt stream mixes field adds/subs/squares,
  batch-inversion products, memory access and hashing. A chain winner
  must later pass short 15–30-second real worker A/B and same Puzzle20,
  parity and crash-replay fixtures.
- The NEON path removes all **intermediate conversion**, yet it still
  uses a baseline 10×26 convolution and carries, not an optimized
  handwritten assembly microkernel. A large deficit rejects this
  prototype, not any possible 10×26 SoA production design.
- Native 4×64 fold unrolling keeps the `while(carry)` fallback. It is
  mathematically the same modular reduction with different instruction
  scheduling. Report ASM and PMU before drawing causal conclusions.
- No integration or promotion before physical Pi evidence and full
  worker coverage. Keep old services disabled by default.
