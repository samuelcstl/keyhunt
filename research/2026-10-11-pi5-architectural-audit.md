# Pi 5 Puzzle #71 architectural waste audit
**Date:** 2026-10-11  
**Status:** source audit / ranked experiments; **no search-engine changes**  
**Control:** `keyhunt-arm64-sha2-neon-su2-center-parity-field-point-direct1-neon`  
**Measured sustained rate:** 7,337,325 and 7,336,683 scanned candidates/s in two 120-second 4-core runs, `get_throttled=0x0`.

## What the counters actually mean
The one-target NEON comparator reduced measured instructions/candidate and cycles/candidate relative to the full-digest control. The branch-miss *percentage* increased, but mispredicted branches **per candidate** dropped to approximately 2.79. Reduced IPC is not proof of a regression. Absolute per-candidate PMU values are estimates because the `perf stat` window and the last Keyhunt throughput snapshot end at different times.

A CPU-clock symbol profile cannot identify wasted work, unpredicted branches, dependency stalls, power efficiency, or distinct globally covered keys. Validate architectural changes by end-to-end 120-second parity-correct Puzzle #71 rate, branch misses/key, cycles/key, clocks, thermals and recovered-key fixtures.

## Highest-confidence avoidable work (not yet optimized)

### 1. Repeated scalar multiplication of an invariant 4*stride inside the hash loop
**Source:** `keyhunt.cpp` at the four-lane scan tail (~3176-3180):

```cpp
count += 4;
temp_stride.SetInt32(4);
temp_stride.Mult(&stride);
key_mpz.Add(&temp_stride);
```

**Problem:** `stride` is constant for the entire worker. The expression `4*stride` is recomputed once **per four scanned keys** (256 times per 1,024-key ECC group). `Int::Mult(Int*)` calls the general fixed-width `Int::Mult(Int*,Int*)`, which has a 5-limb nested partial-product accumulation (`secp256k1/Int.cpp` ~562 and ~615). Thus ~256 unnecessarily repeated general multiplications/group, despite an invariant value. For the common stride=1 case this work is particularly gratuitous.

**Safe experiment:** compute `Int stride4` once on worker initialization with the exact existing multiplication semantics, and replace each `SetInt32(4); Mult(&stride)` with `key_mpz.Add(&stride4)`. Keep every other key/range operation unchanged. This should preserve arbitrary positive user-supplied strides, not assume stride=1. Test chunk boundaries, high-bit keys, nonunit strides and solved fixtures. This is the **best first implementation candidate**, no asserted speedup until physical Pi benchmark.

### 2. Recompute negative generator Y coordinates once per ECC group
**Source:** `keyhunt.cpp` ~2679-2682 and ~2741-2744:

```cpp
dyn.Set(&Gn[i].y);
dyn.ModNeg();
dyn.ModSub(&pn.y);
```

**Problem:** each `Gn[i]` is generated once by `init_generator()` (~4498-4511) and is immutable during scanning, whereas its negative Y coordinate is reconstructed once for each minus-point calculation in every group. In group size 1,024 this is ~512 modular negations/group, plus copies. `Int::ModNeg` calls `Neg()` and adds the modulus; `Neg()` uses a volatile carry variable.

**Safe experiment:** precompute canonical negative generator Y `-Gn[i].y (mod p)` once after `init_generator`, use `dyn.ModSub(&negGnY[i],&pn.y)`, including the boundary point. Initialize this table only for appropriate point-search paths; do not change generator semantics. Test compressed parity, high-bit keys and nonunit strides.

### 3. NEON zero-hit case still enters four scalar loop iterations
**Source:** `keyhunt.cpp` ~2776-2890. `GetHash160_fromXYParityTarget` returns four exact target-mask bits; for Puzzle #71 essentially all masks are zero. The code still enters `for (k=0;k<4;k++)`, then executes its per-lane `if (!(neon_target_matches & (1u << k))) continue;` four times.

**Safe experiment:** guard the *entire matching loop*, not just each lane, when `parity_search && N==1 && neon_target_matches==0`. Preserve key advances (`count+=4`, `key_mpz+=4*stride`), mode fallbacks and rare-hit verification exactly. Beware that `continue` applied to the wrong loop can silently skip key increments. Independently verify the zero-mask and hit-mask paths, including adjacent lanes. Potential impact is smaller than removing the per-four-key scalar multiplication, but likely straightforward.

## High-leverage possibilities requiring hardware attribution

### 4. Canonical modular subtraction has a data-dependent correction branch
**Source:** `secp256k1/IntMod.cpp` ~81-101:

```cpp
Sub(a);
if (IsNegative())
    Add(&_P);
```

`ModSub(a,b)` has the same condition. The modular-subtract correction depends on randomized field values, making these branches candidates for misprediction. The scan performs several such operations per resulting point, plus the batch-inversion prefix products.

**Do not rewrite blindly.** First sample `branch-misses:u` with instruction addresses/call stacks and `perf annotate` for `thread_process` and `Int::ModSub`, and compare mispredictions/key. If concentrated here, test a **separate AArch64 canonical-field-only** branchless subtraction path using five-limb signed/carry semantics, with a Python bigint oracle for canonical residues and all output aliases. Branchless can lose on A76 if masked-add carry chains outweigh saved misprediction penalties. Leave generic arbitrary-width `Int` code intact until independently proven.

### 5. Affine point and temporary layouts carry unused Z data
**Source:** `secp256k1/Point.h` stores three 5×64-bit `Int` coordinates, 120 bytes/Point; `Point pts[1024]` alone is ~120KiB/worker. `pp=startP` and `pn=startP` copy X,Y,Z each i; the compressed HASH160 path ultimately uses only X and Y. The two endomorphism point arrays are also declared in the same worker despite `FLAGENDOMORPHISM=false` on Puzzle #71.

A compact XY-only point batch could reduce stack/cache traffic; however this is a larger algorithm-facing change. Before doing it, inspect compiler-generated copies, the working-set and `L1-dcache-load-misses`/L2 events (subject to kernel PMU support). Preserve startP/Z behavior for code paths that use projective coordinates, and preserve non-parity modes.

### 6. SHA256/RIPEMD160 formatting still bridges separate APIs
**Source:** `SECP256K1.cpp` `GetHash160_fromXYParityTarget` (~815-830) creates four SHA256 64-byte input buffers and four 32-byte outputs; `hash/hash4_arm_sha2_su2.cpp` `pack_digest`; `hash/ripemd160_neon4.cpp` `transform4<true>` loads the same constant 20-byte target for every four keys.

A fused or specialized pipeline could remove redundant byte swaps and stack traffic and hoist constant target broadcasts. However RIPEMD's actual 160 steps remain necessary and NEON register pressure may dominate. Low priority until compiler assembly and PMU data justify it. Correctness must be tested against full HASH160 including Y parity and the multi-target fallback.

## Search quality and expected reward
Throughput counts attempts/scalars, **not globally unique candidates**. Random `-R` chunk starts can overlap; modest duplication is negligible at current search rate relative to Puzzle #71's enormous range, but a multi-device/long-term deployment needs checkpointing and disjoint chunk partitioning. Exact deduplicated coverage matters more than a headline rate when treating search as a lottery. The `Rand(min,max)` routine uses modulo reduction; any tiny distribution bias at a 70-bit range is not a plausible immediate throughput issue, but random seed/quality and restart behavior merit independent validation for production.

## Decision and measurement order
1. **Best next code experiment:** eliminate repeated `4*stride` scalar multiplications, standalone feature flag; keep current NEON champion unchanged as control.
2. **Second:** precompute `-Gn[i].y` and guard no-hit NEON masks, each independently measured before combining.
3. **Measurement gate:** compare 120s/4-core candidates/s, phase drift, approximate instructions/candidate, cycles/candidate, mispredictions/candidate and clock/temp; use alternating A/B and repeat if within noise.
4. **Only after evidence:** branchless modular subtract; compact XY point representation; fused SHA256/RIPEMD buffering.
5. Keep existing PR draft; no main merge and no assertion of gain before Pi testing.
