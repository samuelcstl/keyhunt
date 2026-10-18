# R4 ECC: fast radix arithmetic screening (Cortex-A76 / Pi 5)

Status: **experimental, field microkernels only; NOT a Keyhunt point-generator
or production worker replacement.**

## Hypothesis and fair limitations

A single secp256k1 field multiplication computes `a*b mod p`,
`p=2^256-2^32-977`. The present optimized 4×64 implementation
uses scalar A64 `MUL/UMULH`. R4 tests alternate limb representations:

| Name | Representation | Products | SIMD architecture |
| --- | --- | --- | --- |
| 4x64 | 4 × 64-bit scalar control | 16 products | scalar MUL/UMULH |
| 5x52 | 5 × 52-bit | 25 products | scalar uint128 intermediate |
| 10x26 | 10 × 26-bit | 100 products | scalar uint64 intermediate |
| neon10x26 | 10 × 26-bit for TWO independent residues | 100 per residue | 2 × 32→64 via NEON UMULL |
| 16x16 | 16 × 16-bit | 256 products | scalar uint64 intermediate |
| neon16x16 | 16 × 16-bit for FOUR independent residues | 256 per residue | 4 × 16→32 NEON UMULL, widened to 64 |

Each kernel does exact carry propagation and the pseudo-Mersenne reduction
to a **canonical 4×64 result**. No probabilistic or skipped candidates.
The purpose is to test whether vector lanes overcome additional
partial products and data rearrangement. Exact common output layout is
required for this first apples-to-apples *drop-in* screen, but penalizes
alternative formats relative to a hypothetical all-resident-limb ECC
implementation. If all lose, that rejects **these prototypes only**,
not NEON field arithmetic in all possible layouts.

R4 does not attempt to accelerate individual full scalar multiplications,
claim faster Keyhunt candidates/s or modify R3 worker binaries.

## Fast decision cycle

```bash
cd ~/BITCOIN_ANALYSIS/bitcoin-puzzle/keyhunt
git fetch origin experiment/pi5-r4-ecc-radix-screen-20261018
git worktree add -b pi5-r4-ecc ../keyhunt-r4 \
  origin/experiment/pi5-r4-ecc-radix-screen-20261018
cd ../keyhunt-r4
bash tests/arm64-r4-ecc-screen.sh
```

Defaults:
- Build only a standalone field-kernel executable, not the six full
  Keyhunt worker executables.
- Exact match for **20k random field products**, plus 484 boundary
  cases (11×11×4), for all candidates including actual NEON paths.
  The 4×64 native field has previously passed independent Python
  bigint vectors, alias, SQR and MUL variants in prior rounds.
- Quick warmup 0.1 s per variant; 2-second sustained run per variant;
  two repetitions in reversed variant order, 6 variants. Total field
  measurements ~24 seconds plus builds/oracles.
- Automatic `$HOME/r4-ecc-results-<timestamp>-<pid>.tar.gz`
  including independent source snapshot, exact binary, objdump,
  build/correctness logs, CSV rates, process/clock/thermal evidence,
  complete SHA256SUMS and sibling `.sha256`.
- On test failure, the EXIT trap still archives completed partial
  evidence, with nonzero exit code and `run-status.txt`.
- To screen still faster without editing source:
  `KEYHUNT_R4_SECONDS=1 bash tests/arm64-r4-ecc-screen.sh`
  (12 seconds active measurement + brief warmups and test/build time).
- To investigate one candidate after passing fast screen, compare
  direct worker and full-chain rates with the fixed parent control,
  15- to 30-second crossover per treatment. **Do not use screening
  to qualify production!**

## Acceptance hierarchy

1. ARM64 CI with separate NEON correctness oracle PASS; independent
   previously validated 4×64 reference. No unsound integer overflow
   or unhandled limb carry.
2. Physical Pi field multiplication `mul/s` comparison:
   early rejection on large negative results; shortlist only sustained
   >=5% advantage over 4×64 in repeat-order short screen.
3. Codegen and PMU analysis of shortlist, tune carry/packing and
   memory representation independently.
4. Integrate shortlist behind compile-time flags and run 15-30-second
   actual ECC→SHA256→RIPEMD160 / worker A/B with the *same* crypto
   oracles, before claiming completed keys/s improvement.
5. Longer qualification and scratch SQLite throughput only for a
   surviving integrated winner. Original production Keypool untouched.

The short screen measures *field multiplications/sec* and must never
be labeled `Mkeys/s`.
