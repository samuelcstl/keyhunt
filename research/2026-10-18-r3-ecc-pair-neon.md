# R3 ECC: expose independent point work, qualify NEON arithmetic

Status: **ARM64 correctness PASS; physical Pi throughput not measured / UNQUALIFIED**.
ARM64 runner [workflow 39133677194](https://github.com/samuelcstl/keyhunt/actions/runs/39133677194)
completed successfully after fixing a test-only stdlib symbol naming conflict.
Validation: **53,854 independently checked paired modular-subtraction oracle cases**,
full 71/140/256-bit key/parity vectors, known Puzzle #20 recovery,
upstream solved fixtures, persistent JSON-worker protocol, and exhaustive
524,288-key Puzzle #20 Keypool coverage with crash replay for both ECC
variants. No costly throughput benchmarks ran in CI.
Branch is stacked on R2 RIPEMD160 SRI, itself stacked on R1. Do not merge
without parent verification and review.

## What our current Pi5 ECC already implements

- `CPU_GRP_SIZE=1024`: compute the center point once, then affine
  `P+iG` and `P-iG` from precomputed `Gn` generator offsets.
- A single batch inversion over ~513 denominators, then roughly two
  independent point additions per generator offset. This is not naive
  key-by-key scalar multiplication. There are already four OS threads
  on four physical cores.
- Field multiply uses 4 × 64-bit limbs, 16 scalar `MUL/UMULH` products,
  pseudo-Mersenne `2^256 = 2^32+977 mod p` reduction, and an optimized
  symmetric square (10 distinct limb products). A measured Comba
  alternative was slower in earlier Pi experiments.
- The hot ECC section is ~69% of whole-worker sample cycles; that is
  inclusive of `thread_process`'s inlined arithmetic. No proof that
  all these cycles are SIMD-vectorizable.

## ARM NEON capabilities and limitations

Cortex-A76 supports 128-bit Advanced SIMD, with four independent 32-bit
lanes or two independent 64-bit lanes for add/sub/logic. **It does not
provide 64×64→128 unsigned multiplication per SIMD lane**. Scalar
AArch64 `mul` + `umulh` are still valuable for field products.
NEON `umull` provides 32×32→64 for narrow limbs, but adopting 8×32
representation means changing carry/reduction code and likely costs
extra shuffle and carry traffic. It is not automatic acceleration.

The present experiment is deliberately modest: isolate *instruction-level
parallelism* (ILP) between the two slopes, and separately expose a genuine
two-lane NEON modular subtraction. The NEON candidate does not change
field multiplication or hashing.

## Three comparable variants (same R2 SRI hash and all other objects)

| Binary | ECC point-loop scheduling | Denominator numerators |
| --- | --- | --- |
| `keyhunt-r2-ripemd-sri` | original sequential +/− slope and square | `Int::ModSub` twice |
| `keyhunt-r3-ecc-sched` | compute +/− slopes then both squares | `Int::ModSub` twice |
| `keyhunt-r3-ecc-neon` | same schedule | one `ecc_modsub_2_neon` two-lane invocation |

Persistent workers share these names with prefix `keyhunt-worker-`.
Source changes are behind `KEYHUNT_ECC_PAIR_SCHED` and
`KEYHUNT_ECC_NEON_SUB2`, keeping all existing worker defaults unchanged.
The experiment reuses R1's precomputed `-Gn.y` table.

## Two-lane subtraction correctness

Field prime `p = 2^256 - C`, `C=2^32+977`. For a/b both canonical,
the 256-bit wrapped subtraction `D=(a-b) mod 2^256` is canonical if
a>=b. When a<b, the correct reduced residue is `D-C`. Compute each
limb subtraction and borrow across two independent 64-bit NEON lanes,
then apply C correction on only those lanes with full-width borrow.
This is an *exact* specialized modular subtraction with no cryptographic
shortcuts. It presumes non-aliasing output buffers and canonical inputs.

Oracle `tests/arm64-ecc-neon-sub2-check.cpp` compares against
`Int::ModSub` for all 9^3=729 combinations of boundary points and
50,000 pseudo-random canonical triples, plus additional swapped inputs.
The exhaustive Puzzle #20 and synthetic 71/140/256-bit tests must pass
for each candidate, with the same crash-replay protocol checks.

## Manual proof on Pi

```bash
cd ~/BITCOIN_ANALYSIS/bitcoin-puzzle/keyhunt
git fetch origin experiment/pi5-ecc-paired-neon-20261018
git worktree add -b pi5-r3-ecc ../keyhunt-ecc \
  origin/experiment/pi5-ecc-paired-neon-20261018
cd ../keyhunt-ecc
bash tests/arm64-r3-ecc-bench.sh
```

Runs tests, captures binary hashes and full ARM64 disassembly, then
balanced sustained whole-key throughput and PMU (4 core by default,
120-second intervals twice per binary), clocks/temp, and 3 real
4-thread worker protocol rounds each against a fixed R2-SRI control.
Evidence is outside repository under `../runs/arm64-r3-ecc/`.
No SQLite production campaign or default service is opened.
To shorten optional screening, pass
`KEYHUNT_R3_SECONDS=30 KEYHUNT_R3_WORKER_JOBS=64`; **do not use
short screening trials for promotion decisions.**

Expected outcomes:
- Sched outperforms both baseline and NEON: instruction scheduling
  wins, NEON overhead too costly, do not promote NEON.
- NEON outperforms sched: vector subtraction is useful, inspect
  `objdump`/PMU to confirm and keep the isolated helper.
- Neither improves: preserve measured rejection, investigate field
  carry chains and batch inversion before restructuring the field.

## Candidate next rounds, **not implemented here**

1. Reduce critical-path length for field MUL and pseudo-Mersenne folding,
   avoid uncontrolled dependent carry propagation; compare actual
   `mul/umulh` and `adcs` instruction interleaving.
2. Reorganize prefixes/suffixes in `IntGroup::ModInv` for independent
   chains and lower memory traffic. A latency-hiding gain must exceed
   any extra field multiplications and synchronization.
3. Prototype a 4x32-bit NEON 2-way or 4-way multiply in a **microkernel**
   *only after* verifying layout/ABI, carry-propagation and end-to-end
   A/B against the proven 4x64 scalar path.
4. If practical, compare one batch size and split point computation from
   serialization/HASH160 for same-thread software pipelining; avoid
   inter-thread queue costs before measuring.

No “easy 2× ECC” claim is warranted. Amdahl's law says a 20% faster
ECC-only stage with a 69% time share would produce ~+13.1% whole-worker
rate if all other stages remain unchanged, but that is a hypothetical.
