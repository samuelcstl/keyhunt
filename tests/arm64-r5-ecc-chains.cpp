// R5 isolated secp256k1 field chains, no production entry points.
// Tests two independent residues over CHAIN=8 successive MUL operations.
// Baseline 4x64, paired row-wise ILP, paired ILP with a first-fold
// reduction specialization, and persistent 10x26 NEON across all 8 MULs.
// Every kernel includes output canonicalization and must match 4x64.
#include <arm_neon.h>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <chrono>
#include <algorithm>
#include <string>
#include <vector>
#include <iostream>
#include <iomanip>
using U128=unsigned __int128;
using Word=std::array<uint64_t,5>;
using Two=std::array<Word,2>;
static constexpr uint64_t C=0x1000003d1ULL;
static constexpr uint64_t P0=0xfffffffefffffc2fULL;
static constexpr uint64_t M26=(1ull<<26)-1;
static constexpr uint64_t M22=(1ull<<22)-1;
static constexpr int CHAIN=8;
extern void field_k1_arm64_mul(uint64_t*,const uint64_t*,const uint64_t*);

static inline void canonical(uint64_t z[5]){
  if(z[3]==UINT64_MAX&&z[2]==UINT64_MAX&&z[1]==UINT64_MAX&&z[0]>=P0){
    z[0]-=P0;z[1]=z[2]=z[3]=0;
  }
  z[4]=0;
}
// Preserves the native prime reduction, against which a shorter fold
// specialization can be tested without changing any field logic.
static inline void reduce_native(uint64_t out[5],const uint64_t t[8]){
  uint64_t z[5]={};U128 carry=0;
  for(unsigned k=0;k<4;k++){
    U128 v=U128(t[4+k])*C+t[k]+carry;
    z[k]=uint64_t(v);carry=v>>64;
  }
  while(carry){
    U128 v=U128(uint64_t(carry))*C+z[0];
    z[0]=uint64_t(v);carry=v>>64;
    for(unsigned k=1;k<4;k++){
      v=U128(z[k])+carry;z[k]=uint64_t(v);carry=v>>64;
    }
  }
  canonical(z);for(int k=0;k<5;k++)out[k]=z[k];
}
static inline void reduce_early_fold(uint64_t out[5],const uint64_t t[8]){
  uint64_t z[5]={};U128 carry=0;
  for(unsigned k=0;k<4;k++){
    U128 v=U128(t[4+k])*C+t[k]+carry;
    z[k]=uint64_t(v);carry=v>>64;
  }
  // Usually a nonzero first fold; pull the expected second fold out of
  // the while loop. Keep a general checked fallback for pathological carries.
  U128 v=U128(uint64_t(carry))*C+z[0];
  z[0]=uint64_t(v);carry=v>>64;
  for(unsigned k=1;k<4;k++){
    v=U128(z[k])+carry;z[k]=uint64_t(v);carry=v>>64;
  }
  while(carry){
    v=U128(uint64_t(carry))*C+z[0];
    z[0]=uint64_t(v);carry=v>>64;
    for(unsigned k=1;k<4;k++){
      v=U128(z[k])+carry;z[k]=uint64_t(v);carry=v>>64;
    }
  }
  canonical(z);for(int k=0;k<5;k++)out[k]=z[k];
}
static inline void row_product(uint64_t t[8],const uint64_t a[5],const uint64_t b[5]){
  for(int i=0;i<8;i++)t[i]=0;
  for(int i=0;i<4;i++){
    U128 carry=0;
    for(int j=0;j<4;j++){
      U128 v=U128(a[j])*b[i]+t[i+j]+carry;
      t[i+j]=uint64_t(v);carry=v>>64;
    }
    t[i+4]=uint64_t(carry);
  }
}
static void paired_product(Two&out,const Two&a,const Two&b,bool early){
  uint64_t ta[8]={},tb[8]={};
  // Two independent 4x64 carry chains; issue products from both
  // before feeding each chain's next dependent addition.
  for(int i=0;i<4;i++){
    U128 ca=0,cb=0;
    for(int j=0;j<4;j++){
      U128 va=U128(a[0][j])*b[0][i]+ta[i+j]+ca;
      U128 vb=U128(a[1][j])*b[1][i]+tb[i+j]+cb;
      ta[i+j]=uint64_t(va);ca=va>>64;
      tb[i+j]=uint64_t(vb);cb=vb>>64;
    }
    ta[i+4]=uint64_t(ca);tb[i+4]=uint64_t(cb);
  }
  if(early){
    reduce_early_fold(out[0].data(),ta);
    reduce_early_fold(out[1].data(),tb);
  }else{
    reduce_native(out[0].data(),ta);
    reduce_native(out[1].data(),tb);
  }
}
static void scalar_fold(Word&out,const Word&a,const Word&b){
  uint64_t t[8];row_product(t,a.data(),b.data());
  reduce_early_fold(out.data(),t);
}

// 10x26 resident SoA, 2 lanes, canonical inputs and outputs; state never
// converted back to 4x64 during the CHAIN multiplications.
using Resident=std::array<uint64x2_t,10>;
static Resident from_words(const Two&w){
  Resident r{};
  for(unsigned j=0;j<10;j++){
    uint32_t d[2];
    for(int l=0;l<2;l++){
      unsigned pos=j*26,idx=pos/64,shift=pos%64;
      uint64_t bits=w[l][idx]>>shift;
      if(shift>38&&idx+1<4)bits|=w[l][idx+1]<<(64-shift);
      d[l]=uint32_t(bits&M26);
    }
    r[j]=vcombine_u64(vcreate_u64(d[0]),vcreate_u64(d[1]));
  }
  return r;
}
static void to_words(const Resident&r,Two&out){
  out={};
  for(int lane=0;lane<2;lane++){
    for(int j=0;j<10;j++){
      unsigned pos=j*26,idx=pos/64,shift=pos%64;
      uint64_t digit=lane?vgetq_lane_u64(r[j],1):vgetq_lane_u64(r[j],0);
      out[lane][idx]|=digit<<shift;
      if(shift>38&&idx+1<4)out[lane][idx+1]|=digit>>(64-shift);
    }
    canonical(out[lane].data());
  }
}
static inline uint64x2_t mul977(uint64x2_t x){
  // 977 = 1024 - 32 - 16 + 1, no general 64x64 SIMD multiplication.
  return vaddq_u64(vsubq_u64(vsubq_u64(vshlq_n_u64(x,10),
                     vshlq_n_u64(x,5)),vshlq_n_u64(x,4)),x);
}
static Resident resident_mul(const Resident&a,const Resident&b){
  std::array<uint64x2_t,20> t{};
  uint64x2_t carry=vdupq_n_u64(0);
  const uint64x2_t mask=vdupq_n_u64(M26);
  for(unsigned k=0;k<20;k++){
    uint64x2_t sum=carry;
    for(unsigned i=0;i<10;i++)if(i<=k&&k-i<10){
      uint32x2_t aa=vmovn_u64(a[i]),bb=vmovn_u64(b[k-i]);
      sum=vaddq_u64(sum,vmull_u32(aa,bb));
    }
    t[k]=vandq_u64(sum,mask);
    carry=vshrq_n_u64(sum,26);
  }
  if(vgetq_lane_u64(carry,0)||vgetq_lane_u64(carry,1))std::abort();
  // 2^260 = 2^4 * 2^256 = 16*C (mod p)
  // and 16*C = 15632 + 1024 * 2^26.
  for(int k=19;k>=10;k--){
    auto v=t[k];
    t[k]=vdupq_n_u64(0);
    auto scaled=vaddq_u64(vsubq_u64(vsubq_u64(
      vshlq_n_u64(v,14),vshlq_n_u64(v,9)),
      vshlq_n_u64(v,8)),vshlq_n_u64(v,4));
    t[k-10]=vaddq_u64(t[k-10],scaled);
    t[k-9]=vaddq_u64(t[k-9],vshlq_n_u64(v,10));
  }
  // Normalize to <2^256; 2^256 = C mod p. Carry folding is
  // repeated until both lanes are in range. Canonical p subtraction
  // is delayed to the final consumer and is not needed between MULs.
  bool done=false;
  for(unsigned iteration=0;iteration<8;iteration++){
    carry=vdupq_n_u64(0);
    for(int k=0;k<9;k++){
      auto v=vaddq_u64(t[k],carry);
      t[k]=vandq_u64(v,mask);
      carry=vshrq_n_u64(v,26);
    }
    auto top=vaddq_u64(t[9],carry);
    auto overflow=vshrq_n_u64(top,22);
    t[9]=vandq_u64(top,vdupq_n_u64(M22));
    if(!vgetq_lane_u64(overflow,0)&&!vgetq_lane_u64(overflow,1)){
      done=true;break;
    }
    t[0]=vaddq_u64(t[0],mul977(overflow));
    t[1]=vaddq_u64(t[1],vshlq_n_u64(overflow,6));
  }
  if(!done)std::abort();
  Resident r{};
  for(int k=0;k<10;k++)r[k]=t[k];
  return r;
}
static void chain(const std::string& name,const Two&initial,
                  const Two&factors,Two&out){
  if(name=="10x26-resident"){
    auto x=from_words(initial);
    auto y=from_words(factors);
    for(int i=0;i<CHAIN;i++)x=resident_mul(x,y);
    to_words(x,out);
  }else{
    Two x=initial,y{};
    for(int i=0;i<CHAIN;i++){
      if(name=="4x64-ref"){
        for(int l=0;l<2;l++)field_k1_arm64_mul(y[l].data(),x[l].data(),factors[l].data());
      }else if(name=="4x64-pair-ilp"){
        paired_product(y,x,factors,false);
      }else if(name=="4x64-pair-fold"){
        paired_product(y,x,factors,true);
      }else if(name=="4x64-fold"){
        for(int l=0;l<2;l++)scalar_fold(y[l],x[l],factors[l]);
      }else{std::fprintf(stderr,"Unknown candidate %s\n",name.c_str());std::abort();}
      x=y;
    }
    out=x;
  }
}
static const std::vector<std::string>& names(){
  static const std::vector<std::string> n={"4x64-ref","4x64-fold",
         "4x64-pair-ilp","4x64-pair-fold","10x26-resident"};
  return n;
}
static uint64_t rng=0x512a20261018ULL;
static uint64_t next64(){rng^=rng>>12;rng^=rng<<25;rng^=rng>>27;return rng*0x2545F4914F6CDD1DULL;}
static void random_field(Word&w){
  for(int i=0;i<4;i++)w[i]=next64();
  w[4]=0;canonical(w.data());
}
static Two make_pair(){Two r{};for(auto&w:r)random_field(w);return r;}
static void verify(unsigned trials){
  const std::vector<Word> boundary={
    {0,0,0,0,0},{1,0,0,0,0},{2,0,0,0,0},
    {P0-1,UINT64_MAX,UINT64_MAX,UINT64_MAX,0},
    {P0-2,UINT64_MAX,UINT64_MAX,UINT64_MAX,0},
    {UINT64_MAX,0,0,0,0},{0,1,0,0,0},{0,0,1,0,0},
    {0,0,0,1,0},{0,0,0,1ull<<63,0}
  };
  unsigned cases=0;
  auto check=[&](const Two&start,const Two&factor){
    Two ref{};chain("4x64-ref",start,factor,ref);
    for(const auto&name:names()){
      Two got{};chain(name,start,factor,got);
      if(got!=ref){
        std::cerr<<"FAIL: "<<name<<" chain case="<<cases<<"\n";
        for(int k=0;k<2;k++){
          for(int i=3;i>=0;i--)std::fprintf(stderr,"%016llx",(unsigned long long)got[k][i]);
          std::fprintf(stderr," != ");
          for(int i=3;i>=0;i--)std::fprintf(stderr,"%016llx",(unsigned long long)ref[k][i]);
          std::fprintf(stderr,"\n");
        }
        std::exit(1);
      }
    }
    ++cases;
  };
  for(const auto&a:boundary)for(const auto&b:boundary)
    check(Two{a,b},Two{b,a});
  for(unsigned i=0;i<trials;i++)check(make_pair(),make_pair());
  std::cout<<"PASS: "<<cases<<" paired chains of "<<CHAIN<<" field MULs/lane"
           <<" match native reference for every R5 variant\n";
}
static double bench(const std::string&name,double seconds,uint64_t&checksum){
  std::array<Two,64> starts{},factors{};
  for(unsigned i=0;i<64;i++){starts[i]=make_pair();factors[i]=make_pair();
    for(int lane=0;lane<2;lane++){
      starts[i][lane][3]&=0x7fffffffffffffffULL;
      factors[i][lane][3]&=0x7fffffffffffffffULL;
    }
  }
  auto run=[&](double duration){
    volatile uint64_t sink=0;uint64_t done=0;
    auto begin=std::chrono::steady_clock::now();
    double elapsed=0;
    do {
      for(unsigned i=0;i<64;i++){
        // Different actual operands on every loop, prevent compiler hoisting.
        for(int lane=0;lane<2;lane++){
          starts[i][lane][0]+=0x9e3779b97f4a7c15ULL;
          factors[i][lane][0]^=(starts[i][lane][0]>>13)|1ULL;
        }
        Two out{};
        chain(name,starts[i],factors[i],out);
        sink=sink^(out[0][0]+out[1][1]);
      }
      done+=64*2*CHAIN;
      elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
    }while(elapsed<duration);
    checksum^=sink;
    return double(done)/elapsed;
  };
  run(.08);
  return run(seconds);
}
static void hex_word(const Word&w){
  for(int i=3;i>=0;i--)
    std::printf("%016llx",(unsigned long long)w[i]);
}
int main(int argc,char**argv){
  if(argc>1&&std::string(argv[1])=="--oracle-vectors"){
    unsigned n=argc>2?std::stoul(argv[2]):128;
    std::printf("variant,lane,start,factor,result\n");
    for(unsigned i=0;i<n;i++){
      Two a=make_pair(),b=make_pair();
      for(const auto&name:names()){
        Two out{};
        chain(name,a,b,out);
        for(int lane=0;lane<2;lane++){
          std::printf("%s,%d,",name.c_str(),lane);
          hex_word(a[lane]);std::printf(",");
          hex_word(b[lane]);std::printf(",");
          hex_word(out[lane]);std::printf("\n");
        }
      }
    }
    return 0;
  }
  if(argc>1&&std::string(argv[1])=="--verify"){
    verify(argc>2?std::stoul(argv[2]):2000);return 0;
  }
  double seconds=1;int repeats=2;
  for(int i=1;i<argc;i++){
    std::string x(argv[i]);
    if(x=="--seconds"&&i+1<argc)seconds=std::stod(argv[++i]);
    else if(x=="--repeats"&&i+1<argc)repeats=std::stoi(argv[++i]);
    else{std::cerr<<"usage: --verify [trials] | --seconds 1 --repeats 2\n";return 2;}
  }
  if(seconds<.10||seconds>30||repeats<1||repeats>12)return 2;
  std::cout<<"repeat,variant,muls_per_second,million_muls_per_second,seconds,chain_length\n";
  uint64_t sum=0;
  for(int r=0;r<repeats;r++){
    auto order=names();
    if(r%2)std::reverse(order.begin(),order.end());
    for(const auto&n:order){
      double rate=bench(n,seconds,sum);
      std::cout<<r+1<<","<<n<<","<<std::fixed<<std::setprecision(0)<<rate
               <<","<<std::setprecision(5)<<rate/1e6
               <<","<<seconds<<","<<CHAIN<<"\n"<<std::flush;
    }
  }
  std::cerr<<"checksum="<<std::hex<<sum<<std::dec<<"\n";
}
