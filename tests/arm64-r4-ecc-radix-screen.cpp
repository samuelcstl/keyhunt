// R4 microkernel SCREEN, never linked to the production Keyhunt worker.
// Measure full 4x64 -> residue cost, including representation conversion.
// Candidate NEON paths vectorize independent field products, not one 256-bit product.
#include <cstdint>
#include <cstdlib>
#include <array>
#include <chrono>
#include <iostream>
#include <iomanip>
#include <algorithm>
#include <string>
#include <vector>
#if defined(__aarch64__)
#include <arm_neon.h>
#endif
using U128 = unsigned __int128;
using Word = std::array<uint64_t,5>;
using Batch = std::array<Word,4>;
static constexpr uint64_t C=0x1000003d1ULL;
static constexpr uint64_t P0=0xfffffffefffffc2fULL;
extern void field_k1_arm64_mul(uint64_t*,const uint64_t*,const uint64_t*);
static void reduce_k1(uint64_t out[5],const uint64_t t[8]){
  uint64_t z[4];U128 carry=0;
  for(unsigned i=0;i<4;i++){U128 v=U128(t[4+i])*C+t[i]+carry;z[i]=uint64_t(v);carry=v>>64;}
  while(carry){
    U128 v=U128(uint64_t(carry))*C+z[0];z[0]=uint64_t(v);carry=v>>64;
    for(unsigned i=1;i<4;i++){v=U128(z[i])+carry;z[i]=uint64_t(v);carry=v>>64;}
  }
  if(z[3]==UINT64_MAX&&z[2]==UINT64_MAX&&z[1]==UINT64_MAX&&z[0]>=P0){
    z[0]-=P0;z[1]=z[2]=z[3]=0;
  }
  for(unsigned i=0;i<4;i++)out[i]=z[i];out[4]=0;
}
template<unsigned Bits,unsigned N,typename Limb>
static void unpack(const uint64_t in[5],Limb out[N]){
  constexpr uint64_t mask=(uint64_t(1)<<Bits)-1;
  for(unsigned i=0;i<N;i++){
    unsigned pos=i*Bits,idx=pos/64,sh=pos%64;
    uint64_t w=idx<5?in[idx]>>sh:0;
    if(sh&&sh+Bits>64&&idx+1<5)w|=in[idx+1]<<(64-sh);
    out[i]=Limb(w&mask);
  }
}
template<unsigned Bits,unsigned N,typename Limb>
static void pack(const Limb in[2*N],uint64_t out[8]){
  for(unsigned i=0;i<8;i++)out[i]=0;
  for(unsigned i=0;i<2*N;i++){
    unsigned pos=i*Bits,idx=pos/64,sh=pos%64;
    if(idx>=8)continue;
    uint64_t w=uint64_t(in[i]);
    out[idx]|=w<<sh;
    if(sh&&sh+Bits>64&&idx+1<8)out[idx+1]|=w>>(64-sh);
  }
}
template<unsigned Bits,unsigned N,typename Sum,typename Limb>
static void scalar(const uint64_t a[5],const uint64_t b[5],uint64_t out[5]){
  Limb x[N],y[N],z[2*N]{};
  unpack<Bits,N>(a,x);unpack<Bits,N>(b,y);
  Sum carry=0;
  for(unsigned k=0;k<2*N;k++){
    Sum v=carry;
    for(unsigned i=0;i<N;i++)if(i<=k&&k-i<N)v+=Sum(x[i])*y[k-i];
    z[k]=Limb(v&((Sum(1)<<Bits)-1));carry=v>>Bits;
  }
  if(carry)std::abort();
  uint64_t t[8];pack<Bits,N>(z,t);reduce_k1(out,t);
}
#if defined(__aarch64__)
static void neon26_pair(const uint64_t a[2][5],const uint64_t b[2][5],uint64_t out[2][5]){
  uint32_t x[2][10],y[2][10],z[2][20]{};
  for(unsigned l=0;l<2;l++){unpack<26,10>(a[l],x[l]);unpack<26,10>(b[l],y[l]);}
  uint64x2_t carry=vdupq_n_u64(0),mask=vdupq_n_u64((1ull<<26)-1);
  for(unsigned k=0;k<20;k++){
    uint64x2_t sum=carry;
    for(unsigned i=0;i<10;i++)if(i<=k&&k-i<10){
      const uint32x2_t vx={x[0][i],x[1][i]},vy={y[0][k-i],y[1][k-i]};
      sum=vaddq_u64(sum,vmull_u32(vx,vy));
    }
    uint64x2_t rem=vandq_u64(sum,mask);
    z[0][k]=uint32_t(vgetq_lane_u64(rem,0));
    z[1][k]=uint32_t(vgetq_lane_u64(rem,1));
    carry=vshrq_n_u64(sum,26);
  }
  if(vgetq_lane_u64(carry,0)||vgetq_lane_u64(carry,1))std::abort();
  for(unsigned l=0;l<2;l++){uint64_t t[8];pack<26,10>(z[l],t);reduce_k1(out[l],t);}
}
static void neon16_quad(const uint64_t a[4][5],const uint64_t b[4][5],uint64_t out[4][5]){
  uint16_t x[4][16],y[4][16],z[4][32]{};
  for(unsigned l=0;l<4;l++){unpack<16,16>(a[l],x[l]);unpack<16,16>(b[l],y[l]);}
  uint64x2_t c01=vdupq_n_u64(0),c23=vdupq_n_u64(0),mask=vdupq_n_u64(65535);
  for(unsigned k=0;k<32;k++){
    uint64x2_t s01=c01,s23=c23;
    for(unsigned i=0;i<16;i++)if(i<=k&&k-i<16){
      const uint16x4_t vx={x[0][i],x[1][i],x[2][i],x[3][i]};
      const uint16x4_t vy={y[0][k-i],y[1][k-i],y[2][k-i],y[3][k-i]};
      uint32x4_t p=vmull_u16(vx,vy);
      s01=vaddq_u64(s01,vmovl_u32(vget_low_u32(p)));
      s23=vaddq_u64(s23,vmovl_u32(vget_high_u32(p)));
    }
    uint64x2_t r01=vandq_u64(s01,mask),r23=vandq_u64(s23,mask);
    z[0][k]=uint16_t(vgetq_lane_u64(r01,0));
    z[1][k]=uint16_t(vgetq_lane_u64(r01,1));
    z[2][k]=uint16_t(vgetq_lane_u64(r23,0));
    z[3][k]=uint16_t(vgetq_lane_u64(r23,1));
    c01=vshrq_n_u64(s01,16);c23=vshrq_n_u64(s23,16);
  }
  if(vgetq_lane_u64(c01,0)||vgetq_lane_u64(c01,1)||
     vgetq_lane_u64(c23,0)||vgetq_lane_u64(c23,1))std::abort();
  for(unsigned l=0;l<4;l++){uint64_t t[8];pack<16,16>(z[l],t);reduce_k1(out[l],t);}
}
#endif
static const std::vector<std::string>& variants(){
  static const std::vector<std::string> v={"4x64","5x52","10x26","neon10x26","16x16","neon16x16"};
  return v;
}
static void batch(const std::string& name,const Batch&a,const Batch&b,Batch&out){
  if(name=="4x64"){
    for(int i=0;i<4;i++)field_k1_arm64_mul(out[i].data(),a[i].data(),b[i].data());
  }else if(name=="5x52"){
    for(int i=0;i<4;i++)scalar<52,5,U128,uint64_t>(a[i].data(),b[i].data(),out[i].data());
  }else if(name=="10x26"){
    for(int i=0;i<4;i++)scalar<26,10,uint64_t,uint32_t>(a[i].data(),b[i].data(),out[i].data());
  }else if(name=="16x16"){
    for(int i=0;i<4;i++)scalar<16,16,uint64_t,uint16_t>(a[i].data(),b[i].data(),out[i].data());
#if defined(__aarch64__)
  }else if(name=="neon10x26"){
    for(int k=0;k<4;k+=2){
      uint64_t x[2][5],y[2][5],z[2][5];
      for(int l=0;l<2;l++)for(int j=0;j<5;j++){x[l][j]=a[k+l][j];y[l][j]=b[k+l][j];}
      neon26_pair(x,y,z);
      for(int l=0;l<2;l++)for(int j=0;j<5;j++)out[k+l][j]=z[l][j];
    }
  }else if(name=="neon16x16"){
    uint64_t x[4][5],y[4][5],z[4][5];
    for(int l=0;l<4;l++)for(int j=0;j<5;j++){x[l][j]=a[l][j];y[l][j]=b[l][j];}
    neon16_quad(x,y,z);
    for(int l=0;l<4;l++)for(int j=0;j<5;j++)out[l][j]=z[l][j];
#endif
  }else{std::cerr<<"Invalid kernel "<<name<<"\n";std::exit(2);}
}
static uint64_t seed=0x71a7bcdfe319ULL;
static uint64_t next64(){seed^=seed>>12;seed^=seed<<25;seed^=seed>>27;return seed*0x2545F4914F6CDD1DULL;}
static void random_field(Word&x){
  for(unsigned i=0;i<4;i++)x[i]=next64();x[4]=0;
  if(x[3]==UINT64_MAX&&x[2]==UINT64_MAX&&x[1]==UINT64_MAX&&x[0]>=P0){
    x[0]-=P0;x[1]=x[2]=x[3]=0;
  }
}
static void verify(unsigned trials){
  const std::vector<Word> edges={
    {0,0,0,0,0},{1,0,0,0,0},{2,0,0,0,0},
    {P0-1,UINT64_MAX,UINT64_MAX,UINT64_MAX,0},
    {P0-2,UINT64_MAX,UINT64_MAX,UINT64_MAX,0},
    {UINT64_MAX,0,0,0,0},{0,1,0,0,0},{0,0,1,0,0},
    {0,0,0,1,0},{0,0,0,1ull<<63,0},
    {0,0,0,0x7fffffffffffffffULL,0}
  };
  unsigned tested=0;
  auto check=[&](const Batch&a,const Batch&b){
    Batch ref{};batch("4x64",a,b,ref);
    for(const auto&name:variants()){
#if !defined(__aarch64__)
      if(name.rfind("neon",0)==0)continue;
#endif
      Batch actual{};batch(name,a,b,actual);
      if(actual!=ref){std::cerr<<"FAIL: "<<name<<" batch="<<tested/4<<"\n";std::exit(1);}
    }
    tested+=4;
  };
  for(const auto&x:edges)for(const auto&y:edges){
    Batch a,b;for(int i=0;i<4;i++){a[i]=x;b[i]=y;}check(a,b);
  }
  for(unsigned n=0;n<trials;n++){
    Batch a,b;for(int i=0;i<4;i++){random_field(a[i]);random_field(b[i]);}check(a,b);
  }
  std::cout<<"PASS: "<<tested<<" field products, all variants match independently-tested native 4x64 field\n";
}
static double measure(const std::string&name,double seconds,uint64_t&checksum){
  constexpr size_t sets=128;
  std::array<Batch,sets> a{},b{};Batch out{};
  for(size_t i=0;i<sets;i++)for(int j=0;j<4;j++){random_field(a[i][j]);random_field(b[i][j]);}
  auto loop=[&](double period)->double{
    volatile uint64_t sink=0;uint64_t done=0;
    auto start=std::chrono::steady_clock::now();double elapsed=0;
    do{
      for(size_t i=0;i<sets;i++){
        batch(name,a[i],b[i],out);
        sink=sink^(out[0][0]+out[1][1]+out[2][2]+out[3][3]);
      }
      done+=sets*4;
      elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    }while(elapsed<period);
    checksum^=sink;
    return double(done)/elapsed;
  };
  loop(0.10);return loop(seconds);
}
int main(int argc,char**argv){
  if(argc>1&&std::string(argv[1])=="--verify"){
    unsigned trials=argc>2?std::stoul(argv[2]):5000;verify(trials);return 0;
  }
  double seconds=2;int repeats=2;
  for(int i=1;i<argc;i++){
    std::string a(argv[i]);
    if(a=="--seconds"&&i+1<argc)seconds=std::stod(argv[++i]);
    else if(a=="--repeats"&&i+1<argc)repeats=std::stoi(argv[++i]);
    else{std::cerr<<"usage: --verify [trials] | --seconds 2 --repeats 2\n";return 2;}
  }
  if(seconds<0.1||seconds>60||repeats<1||repeats>10){std::cerr<<"Invalid bench duration\n";return 2;}
  std::cout<<"repeat,variant,field_muls_per_second,million_field_muls_per_second,seconds\n";
  uint64_t checksum=0;
  for(int r=0;r<repeats;r++){
    auto order=variants();if(r%2)std::reverse(order.begin(),order.end());
    for(const auto&name:order){
#if !defined(__aarch64__)
      if(name.rfind("neon",0)==0)continue;
#endif
      double rate=measure(name,seconds,checksum);
      std::cout<<r+1<<","<<name<<","<<std::fixed<<std::setprecision(0)<<rate
               <<","<<std::setprecision(4)<<rate/1e6<<","<<seconds<<"\n"<<std::flush;
    }
  }
  std::cerr<<"benchmark_checksum="<<std::hex<<checksum<<std::dec<<"\n";
}