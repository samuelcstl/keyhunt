// Two independent secp256k1 field products, 4x64 scalar A64.
// R5 microbench PASS: independent Python bigint modulo p chains.
// Kept isolated from production and only linked to R6 experimental worker.
#include "field_k1_pair_ilp.h"
#include <cstdint>
#include <climits>
#if !defined(__aarch64__)
#error "R6 4x64 ILP field experiment requires AArch64"
#endif
namespace {
using U128=unsigned __int128;
constexpr uint64_t C=0x1000003d1ULL;
constexpr uint64_t P0=0xfffffffefffffc2fULL;
static inline void finish(uint64_t out[5],const uint64_t t[8],bool early){
  uint64_t z[4];U128 carry=0;
  for(unsigned k=0;k<4;k++){
    const U128 v=U128(t[4+k])*C+t[k]+carry;
    z[k]=uint64_t(v);carry=v>>64;
  }
  // Compare regular dynamic fold vs always executing the first fold.
  // The remaining fallback is exact for any inputs; no skipped carries.
  if(early){
    U128 v=U128(uint64_t(carry))*C+z[0];
    z[0]=uint64_t(v);carry=v>>64;
    for(unsigned k=1;k<4;k++){
      v=U128(z[k])+carry;z[k]=uint64_t(v);carry=v>>64;
    }
  }
  while(carry){
    U128 v=U128(uint64_t(carry))*C+z[0];
    z[0]=uint64_t(v);carry=v>>64;
    for(unsigned k=1;k<4;k++){
      v=U128(z[k])+carry;z[k]=uint64_t(v);carry=v>>64;
    }
  }
  if(z[3]==UINT64_MAX&&z[2]==UINT64_MAX&&z[1]==UINT64_MAX&&z[0]>=P0){
    z[0]-=P0;z[1]=z[2]=z[3]=0;
  }
  for(unsigned k=0;k<4;k++)out[k]=z[k];
  out[4]=0;
}
static void mul2(uint64_t plus_out[5],uint64_t minus_out[5],
                 const uint64_t plus[5],const uint64_t minus[5],
                 const uint64_t common[5],bool early){
  uint64_t ta[8]={},tb[8]={};
  for(unsigned i=0;i<4;i++){
    U128 ca=0,cb=0;
    for(unsigned j=0;j<4;j++){
      U128 va=U128(plus[j])*common[i]+ta[i+j]+ca;
      U128 vb=U128(minus[j])*common[i]+tb[i+j]+cb;
      ta[i+j]=uint64_t(va);ca=va>>64;
      tb[i+j]=uint64_t(vb);cb=vb>>64;
    }
    ta[i+4]=uint64_t(ca);
    tb[i+4]=uint64_t(cb);
  }
  finish(plus_out,ta,early);
  finish(minus_out,tb,early);
}
}
void field_k1_arm64_mul2(uint64_t out_plus[5],uint64_t out_minus[5],
                         const uint64_t plus[5],const uint64_t minus[5],
                         const uint64_t denominator_inverse[5]){
  mul2(out_plus,out_minus,plus,minus,denominator_inverse,false);
}
void field_k1_arm64_mul2_fold(uint64_t out_plus[5],uint64_t out_minus[5],
                              const uint64_t plus[5],const uint64_t minus[5],
                              const uint64_t denominator_inverse[5]){
  mul2(out_plus,out_minus,plus,minus,denominator_inverse,true);
}
