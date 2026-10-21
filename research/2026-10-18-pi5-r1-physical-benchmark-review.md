# Pi 5 Keyhunt CPU R1: physical run evidence review

**Observed:** 2026-10-18, one named Raspberry Pi 5, four Cortex-A76 cores,
~2.4 GHz, GCC 14.2.0, Debian kernel 6.18.50+rpt-rpi-2712.
**Code SHA:** `f4ccc59cf4094dfc16a4df8fb965bcc357a1c206`.
**Archive:** `20261018T065018Z-3568484.tar.gz`,
SHA256 `57c98425222f1bb65d0b369980f499cc23c91f7f563a87300603c1fb2432d293`
(user-held private evidence, not added to the repository).
**Status:** correctness PASS, performance **promising / UNQUALIFIED**.
No original Keypool Puzzle #71 database changed.

## Correctness

Four independent standalone R1 flag combinations recovered the known public
Puzzle #20 key, passed independent 71/140/256-bit ECC/parity vectors and solved
fixture checks. `keyhunt-worker-r1` passed strict range handling and recoverable
job protocol. End-to-end exhaustive Puzzle #20 fixture: **512 groups, 524,288
post-SHA256+RIPEMD160 unique candidates**, verified disjoint scrambled scheduling,
the known key, and bounded precommit crash replay. All passed.

## Real four-thread JSON worker throughput (256 × 2^20 keys per observation)

| Round | Control Mkeys/s | R1 Mkeys/s | Paired change |
| --- | ---: | ---: | ---: |
| 1 | 7.10518 | 7.19464 | +1.259% |
| 2 (reverse order) | 7.01941 | 7.16337 | +2.051% |
| 3 | 7.07515 | 7.20734 | +1.868% |

**Median paired gain +1.868%, 3 of 3 wins.** Identical synthetic-seeded,
disjoint key chunks; full JSON worker completions over elapsed wall time,
not inferred from the standalone 5-second counters.
Absolute rates were less than historical uncontended October 14 results,
so do not translate +1.868% into a validated new peak number.

## Standalone 4-core source-attribution results (120 s, reversed AB...BA)

| Variant | Median Mkeys/s | Paired rate median vs control | Approx cycles/key | Approx insns/key |
| --- | ---: | ---: | ---: | ---: |
| Control | 7.15185 | reference | 1253.4 | 1768.1 |
| Hoist 4×stride | 7.08400 | -0.939% (0/2 wins) | 1254.2 | 1765.1 |
| Precompute negative Gn Y | 7.15256 | +0.022% (1/2 wins) | 1239.6 | 1735.0 |
| Zero-mask scalar bypass | 7.09407 | -0.799% (1/2 wins) | 1247.2 | 1749.1 |
| All three | 7.23244 | +1.140% (1/2 wins) | 1224.8 | 1704.9 |

Control-to-combined delta is **-2.283% cycles/attempt**, **-3.579%
instructions/attempt**, **-3.073% mispredicted branches/attempt**,
from approximate full-perf-window normalization against 5 s counters.
Although raw branch-miss *percentage* increases ~4.18% -> 4.53%,
absolute misses per 1000 candidate keys decrease ~2885 -> ~2797.
These different denominators must not be confused.

The first cold control run drifted **-2.47%** from early to late windows
(51.6 -> 60.4°C); control at end ran 7.076 Mkeys/s.
R1-all ran near 7.22/7.25 Mkeys/s at ~64°C and remained stable.
Standalone 2-pair data are too noisy to qualify individual flags.
No thermal throttling was reported (`throttled=0x0`), and ARM clock
remained ~2.4 GHz. Other blockchain node/pool services were running,
which can perturb contention and reproducibility despite low average CPU use.

## Actual codegen, not a source-level guess

- `-O3 -mcpu=cortex-a76 -flto` used throughout; direct hardware
  SHA256 instructions, NEON and `mul/umulh` remain present.
- From the saved full `objdump -drwC` files, the
  `field_k1_arm64_mul(...)` compiled body contains 148 A64 instructions
  and its **encoded opcode sequence matches identically** across all
  standalone and worker R1 variants. Hence the observed R1 gain did not
  come from a changed prime-field multiplication microkernel.
- The combined R1 machine code includes a one-time 20,480-byte generator
  negative-Y table allocation/init and a hoisted four-stride multiply;
  its hot scan still executes full parity-correct HASH160 for every key.
- CPU profile for control: `field_k1_arm64_mul` ~31.48% exclusive,
  `thread_process` ~34.85% exclusive (contains inlined point work),
  `GetHash160_fromXYParityTarget` ~22.21% exclusive, SHA2 function
  ~8.46% exclusive. The MUL attribution includes ~18.54% via
  `IntGroup::ModInv` and ~12.95% direct from the scan. Samples are
  not an exact additive accounting of source-level stages.
- Profile for combined is directionally similar: field MUL ~31.56%,
  thread ~35.05%, HASH160 ~23.26%, SHA2 ~8.21%.
  Most meaningful next targets are **ECC field arithmetic / inversion
  batches, point generation and memory**, then fixed-message hashing.

### Known instrumentation gap

`perf record` captured 8,932 and 8,959 samples, and `perf report`
found valid symbol distributions, but both output `perf annotate --symbol`
artifacts say **"data has no samples"**. The old command selected bare C++
function names, which may not match the fully demangled symbols in the data.
The extra `tests/arm64-r1-reannotate.sh` now tries exact full signatures
on retained `perf.data` (no mining rerun) and explicitly marks failure.
Its effectiveness on the Pi has **not yet been verified**.

The evidence archive recorded full instruction disassembly and executable SHA256,
but did **not** include the binary contents. A later tooling-only update copies
binaries into future evidence for offline symbol resolution. This update must not
change cryptographic source or R1 binary semantics.

### Compiler mismatch and next A/B

Repeated GCC/LTO warnings say `-mcpu=cortex-a76` conflicts with
`-march=armv8.2-a+sha2` on the special SHA2 translation unit.
GCC 14.2 documents that mixed architecture/tune options affect generated
code. This warning is **not proof of a throughput loss**; the entire R1
comparison used the same flags. Test an independent, explicitly identified
compile-flag variant (e.g. `-mcpu=cortex-a76+sha2` without the conflicting
`-march`, if the local GCC accepts it) and compare disassembly,
correctness, PMU and actual worker throughput. No flag changes in R1 control.

## Engineering decision

1. **Retain** `keyhunt-worker-r1` as an experimental candidate, not a production replacement.
2. **Reject or defer** isolated stride hoist based on present evidence;
   revisit only if specialized codegen demonstrates an actual win.
3. **Keep investigating** negative-Y and zero-mask effects, which save
   cycles/instructions but lack independent wall-throughput proof.
4. **Re-run focused warmed-up worker ABBA/AABB with more repetitions** under
   improved process/CPU isolation; qualify performance on completed keys,
   not percentage alone. Retain exact binary hashes and tests.
5. **Recover perf annotation** from the existing `perf.data`.
6. **R2 research**: field multiplication/reduction dependence chains,
   inversion group scheduling, branchy modular arithmetic, and specialized
   compact point layout. GPU/QPU postponed until CPU analysis matures.

Do not merge PR #2, overwrite `keyhunt-worker`, enable services, or
advance the durable production campaign as part of this assessment.
