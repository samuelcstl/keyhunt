# R2-RIPEMD-ROTATE: Cortex-A76 NEON rotate implementation A/B

Status: **unqualified experimental kernel**, stacked on the R1 branch.
This change is not a modification to `perf/pi5-arm64`, the real
`keyhunt-worker`, or the persistent Keypool campaign.

## Evidence-led hypothesis

In the physical 2026-10-18 control disassembly, the LTO-inlined
`Secp256K1::GetHash160_fromXYParityTarget` function contains many
`shl v*.4s`, `ushr v*.4s` and `orr v*.16b` triplets generated from

```cpp
#define ROL(x,n) vorrq_u32(vshlq_n_u32((x),(n)),vshrq_n_u32((x),32-(n)))
```

RIPEMD160's 160 steps across the two parallel lines include repeated
32-bit word rotates. The intrinsics **`vsliq_n_u32`** and **`vsriq_n_u32`**
encode shift-and-insert and may lower to two A64 instructions (USHR+SLI
or SHL+SRI) instead of three (SHL+USHR+ORR). Both identities are exactly
equal over all 2^32 input words for compile-time shifts 1..31.
This is an instruction-count hypothesis, **not a speedup claim**.

In the previous whole-function profile, ~20.9% of exclusive sampled
cycles were NEON RIPEMD160+exact target compare, while ~69.3% were ECC
and scanning and ~8.5% SHA256. The RIPEMD figure includes its SIMD
gather/transposition and result mask, not only rounds. A 20% speedup
of this entire phase would yield at most ~3.6% end-to-end throughput
if the other phases were unchanged, per Amdahl's law.

## Control and candidates

| Binary | RIPEMD rotate | Otherwise identical |
| --- | --- | --- |
| `keyhunt-r1-all` | original SHL+USHR+ORR expression | R1 combined standalone |
| `keyhunt-r2-ripemd-sli` | USHR + SLI expression | R1 combined standalone |
| `keyhunt-r2-ripemd-sri` | SHL + SRI expression | R1 combined standalone |
| `keyhunt-worker-r1` | original expression | R1 full protocol |
| `keyhunt-worker-r2-ripemd-{sli,sri}` | respective expression | R1 full protocol |

The object files are independently compiled from the same RIPEMD source,
guarded by `KEYHUNT_RIPEMD_ROL_SLI/SRI`. ECC field objects, SHA256
and application objects are **identical linker inputs** in all variants.
No new preparation, private-key handling, target representation or
algorithm shortcuts.

## Gates

1. Build all control/candidates: `make arm64-r2-ripemd`.
2. Correctness: independent RIPEMD160 four-lane digests and target-mask
   vectors; known puzzle #20, synthetic 71/140/256-bit parity and ECC
   vectors; 64-slice exact post-HASH160 Puzzle #20 exhaustive Keypool
   fixture and crash replay. `make arm64-r2-ripemd-test`.
3. Machine code: `python3 tests/arm64-r2-ripemd-asm.py
   keyhunt-r1-all keyhunt-r2-ripemd-sli keyhunt-r2-ripemd-sri`.
   Verify SLI/SRI actually appear in the LTO-linked HASH160 function;
   compare instruction counts, register spills, and PMU cycles/key.
   A nominal two-instruction source change is NOT proof the compiler
   generated fewer instructions.
4. Matched Pi: `bash tests/arm64-r2-ripemd-bench.sh`. This collects
   4-core sustained 120s periods, PMU cycles/instructions/branch metrics,
   thermal and clock samples, and identical disjoint real-worker
   protocol chunks in reverse-order pairs (3 repeats).
5. Keep entire output outside the Git repo, with binary checksums,
   disassemblies and the complete raw measurements. No promotion
   until full worker rate is repeatedly higher, confidence exceeds
   noise, no crash/coverage deviation, clock stable and disassembly
   supports the hypothesis.

**Do not promote even if microbench throughput improves when the full
worker pipeline slows down.** The baseline 7.3 Mkeys/s means a 1%
change is ~73k keys/s; a few percent improvement is meaningful but
small enough to be sensitive to RAM pressure, other daemons and
thermal variance on a busy Pi 5.

## ECC next: distinct investigation

Batched `IntGroup::ModInv()` is already active and uses prefix products,
one field inverse per group and reverse products. `field_k1_arm64.cpp`
already implements 4x64 `mul/umulh` arithmetic, symmetric field
squaring and pseudo-Mersenne reduction. The older Comba field candidate
was measured slower and rejected.

The next CPU optimization should inspect the *actual* 148-instruction
field MUL block, carry/reduction dependency depth (including variable
`while(carry)`), field add/sub branches, data-cache behavior and point
layout. Any new 5x52 or 32-bit SIMD representation must pass full
secp256k1 arithmetic oracle, extreme carries/aliases, modulo canonicality,
nonunit stride, and real-worker throughput. Do not claim an easy ECC
speedup before evidence.

GPU/QPU HASH160 investigation remains deferred; it cannot be equated
with the separate ~14MH/s SHA256d QPU engine.
