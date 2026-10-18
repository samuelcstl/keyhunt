// Independent field multiplication oracle for experimental +/- 4x64 kernel.
#include "../secp256k1/field_k1_pair_ilp.h"
#include <cstdint>
#include <array>
#include <cstdio>
#include <cstdlib>
using Word=std::array<uint64_t,5>;
static constexpr uint64_t P0=0xfffffffefffffc2fULL;
extern void field_k1_arm64_mul(uint64_t*,const uint64_t*,const uint64_t*);
static uint64_t state=0x61a7dEadBEefULL;
static uint64_t next64(){state^=state>>12;state^=state<<25;state^=state>>27;return state*0x2545F4914F6CDD1DULL;}
static Word random_field(){
  Word x{};
  for(unsigned k=0;k<4;k++)x[k]=next64();
  if(x[3]==UINT64_MAX&&x[2]==UINT64_MAX&&x[1]==UINT64_MAX&&x[0]>=P0){
    x[0]-=P0;x[1]=x[2]=x[3]=0;
  }
  return x;
}
static void check(const Word&plus,const Word&minus,const Word&common,unsigned id){
  Word refp{},refm{},ilpp{},ilpm{},foldp{},foldm{};
  field_k1_arm64_mul(refp.data(),plus.data(),common.data());
  field_k1_arm64_mul(refm.data(),minus.data(),common.data());
  field_k1_arm64_mul2(ilpp.data(),ilpm.data(),plus.data(),minus.data(),common.data());
  field_k1_arm64_mul2_fold(foldp.data(),foldm.data(),plus.data(),minus.data(),common.data());
  if(ilpp!=refp||ilpm!=refm||foldp!=refp||foldm!=refm){
    std::fprintf(stderr,"FAIL: ECC paired MUL oracle #%u\n",id);
    std::exit(1);
  }
}
int main(){
  const std::array<Word,10> edges={{
    {{0,0,0,0,0}},{{1,0,0,0,0}},{{2,0,0,0,0}},
    {{P0-1,UINT64_MAX,UINT64_MAX,UINT64_MAX,0}},
    {{P0-2,UINT64_MAX,UINT64_MAX,UINT64_MAX,0}},
    {{UINT64_MAX,0,0,0,0}},{{0,1,0,0,0}},
    {{0,0,1,0,0}},{{0,0,0,1,0}},{{0,0,0,1ull<<63,0}}
  }};
  unsigned tests=0;
  for(const auto&a:edges)for(const auto&b:edges)for(const auto&c:edges)
    check(a,b,c,tests++);
  for(unsigned i=0;i<50000;i++)check(random_field(),random_field(),random_field(),tests++);
  std::printf("PASS: %u paired native field MUL triples, exact canonical results\n",tests);
}
