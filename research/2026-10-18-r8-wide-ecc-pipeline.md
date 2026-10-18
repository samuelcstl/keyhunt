# R8 architectural design: wide ECC producer -> HASH160 consumer

**Status: DESIGN ONLY.** No production worker change, no performance claim. This branch is cleanly based on the validated R3 experimental ECC parent, not the R6/R7 rejected worker code.

## Evidence and precisely what was measured

R5 Pi microkernel measured **15.485M secp256k1 modular field multiplications/s** for the paired + fold implementation against **14.401M MUL/s** for its original 4x64 reference, **+7.53% on the same operation**. This is a single-thread kernel measurement, not a 2x result. Dividing it by 7.3M completed Keyhunt keys/s (four CPU cores) compares different units; a candidate needs multiple modular multiplications, squares, inversion amortization, and HASH160.

R6 substituted just two slope MULs into the old point-generation loop and later regressed -1.88% (0/4 wins) in the real worker. That rejects **that limited integration**, not the principle of exploiting many independent ECC points.

R7 physical archive: r7-ecc-results-20261018T174238Z-949427.tar.gz, SHA256 06c67c856c4f282e79983fdad102dabd3e75806eba75086c8301c56fcd01350c. All **49/49** archived file SHA256s match. Cryptographic correctness, Puzzle20 exhaustive coverage and crash-replay checks PASS.

R7 was too short for reliable throughput qualification: 24 jobs, roughly 3.5s per process, two reverse-order pairs. R7-SCHED paired deltas +1.77%, -2.14%; R7-PAIR -1.95%, +1.66%; R7-FOLD +8.28%, +0.23%. The +8.28% comparison had an anomalously low R3 control. Do not claim R7-FOLD +4.25% sustained from its two-pair median.

More useful: R7 instrumented timing for one 1024-key batch, per thread, excluding some center/administrative work:

| Stage | Approx microseconds/batch | Fraction | Estimated one-core phase-only service rate |
| --- | ---: | ---: | ---: |
| dx and batch inverse | 119.3 | 21.7% | 8.58 M candidates/s |
| Point construction X and Y | 254.8 | 46.3% | 4.02 M candidates/s |
| SHA256 + RIPEMD160 + match | 176.1 | 32.0% | 5.82 M candidates/s |
| Sum | 550.3 | 100% | 1.86 M candidates/s per core |

These are *timed phases inside a monolithic worker*, not independently saturated capacity measurements or cycle counts. We must measure producer and consumer in isolation.

## True available parallelism, beyond two products

IntGroup::ModInv currently computes a 513-element batch of denominators, 512 **dependent** prefix products, one modular inversion, and about 1024 suffix/reverse multiplications in a serial recurrence. This is a separate candidate for a parallel prefix/suffix algorithm but not the first R8 implementation.

After inversion, the regular 511 positive/negative point pairs are **mutually independent within a 1024-key group**. The current code computes all 1024 points and stores them, then starts a separate four-lane SHA256/NEON-RIPEMD160 pass. It has not exposed the cross-pair independence as a wide stage and does not stream ready quartets directly into hash workers.

Crucial: positive and negative points are generated at *mirrored scalar offsets* around the group center, not in sorted candidate-index order. Index tracking cannot be inferred from output position.

The hash engine **already has a four-way SIMD path**: the next task is sustaining it with accurately indexed packets, not reinventing an assumed scalar SHA256/RIPMED160 tail.

## Proposed stages and contracts

Work scheduler: (chunk_id, start_scalar, count, stride, configuration_token)
    -> ECC batch preparation (center, 513 inverse denominators)
    -> Wide ECC point engine W = 1, 2, 4, 8, 16 independent products
    -> Bounded SPSC/MPMC point-packet ring, cached/aligned reusable slabs
    -> 4-lane SHA256 + NEON RIPEMD160 + target comparison
    -> Verified-hit + exact completed-index ACK and durable chunk commit

The **arithmetic width W** is independent from the number of cores/workers and the **HASH160 width 4**. First test W through independently scheduled ARM64 scalar MUL/UMULH dependency chains, not imaginary SIMD 64x64->128 lanes. Only after measurement consider 10x26/16x16 NEON limb representations.

PointPacket carries batch_id, chunk_id, four logical key offsets (not implicit sequential order), four canonical X coordinates (32 bytes), four Y parity values, a valid_lane_mask and target/config generation. Small fixed-size aligned packets, bounded queue, no allocation per candidate. Last packet may be partial. Every candidate index must appear **exactly once**. The hit path independently reconstructs and verifies the true scalar; no candidate-private-key leakage in logs.

Queue backpressure must never drop work or commit an ECC-produced but unhashed candidate. On stop/crash, replay only uncommitted chunks, and allow rehashed bounded windows only when explicitly accounted for. The existing production Puzzle71 SQLite DB and cursor are untouched by experiments.

The ECC producer retains the next-center point dependency and batches inverse across 513 denominators. After this inverse it may emit arbitrary ready quartets (carrying their actual offsets), instead of waiting for all 1024 points. HASH consumers can run on other hardware or dynamically scheduled CPU tasks. Do not split inverse into another permanent CPU worker until the stage model and dependencies justify it.

## Critical same-Pi resource constraint

From the measured timed stages:
- ECC prepare + point generation: ~374.1 microseconds/1024 points = ~2.74M keys/s single-core **estimated stage-only capacity**.
- HASH160: ~176.1 microseconds/1024 points = ~5.82M keys/s single-core estimated stage-only capacity.

For unchanged kernels on four shared A76 cores:
- Fixed three ECC cores + one HASH core: bottleneck min(3 x 2.74, 1 x 5.82) = **5.82M keys/s**, less than R3's ~7.3M keys/s.
- Fixed two ECC + two HASH: bottleneck min(2 x 2.74, 2 x 5.82) = **5.48M keys/s**.

These estimates illustrate **work conservation**. Inserting a queue does not create CPU cycles. R8 must use flexible scheduling/stealing (approximately 68% ECC CPU work / 32% HASH work before overhead), better ILP/larger W, new core capacity or heterogeneous offload. This is why Pi-only stage workers pinned rigidly are likely to underperform. With more CPUs, specialized accelerator hardware or distributed nodes, capacity balancing becomes decisive.

At 7.3M candidates/s, streaming only canonical X+Y-parity (33 bytes each) generates **~241 MB/s**, exceeding practical 1-Gbit networking. Local RAM handoffs are much cheaper; external service design needs real transfer measurements and often >=10-Gbit/s networking or stage fusion. Central database should track chunk state/results, not store every point individually.

## Experimental gates, not 3.5-second worker scoring

1. **Correctness first.** Differential point X/Y and HASH160 against R3 for W in {1,2,4,8,16}, Puzzle20 full 524288-key coverage and parity vectors, exact key-offset mapping under mirrored plus/minus generation, partial packets, stop/replay and lost/duplicate ACK injection. Never touch production campaign.
2. **Independent, stable stage-capacity curves.** Warm up 10-15 s; measure **at least 60 s** per width/variant on physical Pi. ECC-only produced-valid-points/s including inverse and center advance; HASH-only consumed-and-verified-packets/s on precomputed real points; and queue-only transfer bytes/s. Report PMU cycles/key, field MULs/s, IPC, spills, cache misses and overall stage waiting/backpressure fraction. Close candidates require three reverse/random-order repeats.
3. **First integrated architecture.** Bounded in-process ECC -> four-lane hash pipeline, with dynamic work sharing across cores. Measure queue depth, starvation vs backpressure vs runnable CPU, per-stage total work and wall-clock output.
4. **Production-like qualification only for winners.** Prewarm at least 30 s and collect at least 120 s sustained per variant, >=3 paired reverse-order trials, actual *verified* candidate keys/s, stage capacity and CPU/energy cost. Full known-key oracle and recovery checks before promotion.
5. **Scalability.** Sweep arithmetic W 1/2/4/8/16, queue capacity 8/32/128 packets, CPU topology 1/2/3/4 cores, and later multi-host transport. Separate microkernel capacity results from full pipeline benchmark result.

Next executable scope is **a standalone ECC-producer + HASH-consumer capacity harness and packet correctness oracle**, not another replace-two-MULs tweak in Keyhunt. Preserve binary/source/log/SHA256 tar.gz on success **and** failure.

This is a new architecture experiment with a clean R3 parent. No production worker, service defaults or live nodes/pools changed.
