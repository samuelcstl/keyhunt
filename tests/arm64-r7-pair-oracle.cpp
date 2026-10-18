// Exact oracle for R7 independent A*B + C*D paired products.
// Unlike R6, operands on the two lanes need not share a denominator.
#include "../secp256k1/field_k1_pair_ilp.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
using Word=std::array<uint64_t,5>;
constexpr uint64_t P0=0xfffffffefffffc2fULL;
extern void field_k1_arm64_mul(uint64_t*,const uint64_t*,const uint64_t*);
static uint64_t rng=0x7017ecc20261018ULL;
static uint64_t next64(){rng^=rng>>12;rng^=rng<<25;rng^=rng>>27;return rng*0x2545F4914F6CDD1DULL;}
static Word random_field(){
  Word r{};
  for(int k=0;k<4;k++)r[k]=next64();
  if(r[3]==UINT64_MAX&&r[2]==UINT64_MAX&&r[1]==UINT64_MAX&&r[0]>=P0){
    r[0]-=P0;r[1]=r[2]=r[3]=0;
  }
  return r;
}
static void check(const Word&a,const Word&b,const Word&c,const Word&d,unsigned test){
  Word ref0{},ref1{},candidate0{},candidate1{},fold0{},fold1{};
  field_k1_arm64_mul(ref0.data(),a.data(),b.data());
  field_k1_arm64_mul(ref1.data(),c.data(),d.data());
  field_k1_arm64_mul2_independent(candidate0.data(),candidate1.data(),
                                   a.data(),b.data(),c.data(),d.data());
  field_k1_arm64_mul2_independent_fold(fold0.data(),fold1.data(),
                                        a.data(),b.data(),c.data(),d.data());
  if(candidate0!=ref0 || candidate1!=ref1 || fold0!=ref0 || fold1!=ref1){
    std::fprintf(stderr,"R7 independent 2-way ECC MUL mismatch at vector %u\n",test);
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
  unsigned cases=0;
  for(const auto&a:edges)for(const auto&b:edges)for(const auto&c:edges){
    const auto& d=edges[(cases*7+3)%edges.size()];
    check(a,b,c,d,cases++);
  }
  for(unsigned i=0;i<50000;i++)check(random_field(),random_field(),
                                      random_field(),random_field(),cases++);
  std::printf("PASS: %u exact independent paired field MUL quadruples\n",cases);
}
