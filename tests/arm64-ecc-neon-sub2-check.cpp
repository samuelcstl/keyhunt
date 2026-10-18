// Differential oracle for NEON two-way modular subtraction over secp256k1.
// Runs on AArch64 and compares every lane against existing Int::ModSub.
#include "../secp256k1/Int.h"
#include "../secp256k1/field_k1_neon_pair.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstdint>

static uint64_t state=0x7c50e36d995aULL;
static uint64_t next_random64() {
  state ^= state >> 12;
  state ^= state << 25;
  state ^= state >> 27;
  return state * 0x2545F4914F6CDD1DULL;
}
static void random_field(Int& x,Int& p) {
  for (int i=0;i<4;i++) x.bits64[i]=next_random64();
  x.bits64[4]=0;
  if (x.IsGreaterOrEqual(&p)) x.Sub(&p);
}
static void check(Int& a0,Int& a1,Int& b, int n) {
  Int r0,r1,expect0,expect1;
  expect0.ModSub(&a0,&b);
  expect1.ModSub(&a1,&b);
  ecc_modsub_2_neon(&r0,&r1,&a0,&a1,&b);
  if (!r0.IsEqual(&expect0) || !r1.IsEqual(&expect1)) {
    std::fprintf(stderr,"ECC NEON SUB2 mismatch at vector %d\n",n);
    std::exit(1);
  }
  // Outputs must be canonical with an unsigned zero fifth limb.
  Int *p=Int::GetFieldCharacteristic();
  if(r0.bits64[4] || r1.bits64[4] ||
     r0.IsGreaterOrEqual(p) || r1.IsGreaterOrEqual(p)) {
    std::fprintf(stderr,"ECC NEON SUB2 noncanonical output at vector %d\n",n);
    std::exit(1);
  }
}
int main() {
  Int p;
  p.SetBase16("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F");
  Int::SetupField(&p);
  Int zero,one,two,pm1,pm2,c,cm1,cp1,mid;
  zero.SetInt32(0); one.SetInt32(1); two.SetInt32(2);
  pm1.Set(&p);pm1.SubOne();
  pm2.Set(&pm1);pm2.SubOne();
  c.SetInt64(uint64_t(0x1000003d1ULL));
  cm1.Set(&c);cm1.SubOne();
  cp1.Set(&c);cp1.AddOne();
  mid.SetBase16("7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF7FFFFE17");
  std::array<Int*,9> boundary={&zero,&one,&two,&pm1,&pm2,&c,&cm1,&cp1,&mid};
  int n=0;
  for (Int *a : boundary)
    for (Int *d : boundary)
      for (Int *b : boundary) check(*a,*d,*b,n++);
  for (int i=0;i<50000;i++) {
    Int a0,a1,b;
    random_field(a0,p);random_field(a1,p);random_field(b,p);
    check(a0,a1,b,n++);
    if ((i & 15)==0) check(b,a1,a0,n++);
  }
  std::printf("PASS: %d secp256k1 NEON dual-lane subtraction oracle cases\n",n);
  return 0;
}
