// R8: one-inversion segmented affine batch preparation.
// 513 independent nonzero secp256k1 denominators, just like Keyhunt's
// IntGroup::ModInv; W independent prefix and suffix chains per batch.
// Does NOT modify Keyhunt and does NOT measure finished keys/HASH160.
#include "../secp256k1/Int.h"
#include "../secp256k1/IntGroup.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iomanip>
#include <string>
#include <vector>

constexpr int N=513;
static const int W_LIST[]={1,2,4,8,16};
static uint64_t rng=0x810320261018abcdULL;
static uint64_t next64(){
  rng^=rng>>12;rng^=rng<<25;rng^=rng>>27;
  return rng*0x2545f4914f6cdd1dULL;
}
static void fill_input(std::array<Int,N>& src,Int& prime){
  for(auto& value:src){
    for(int i=0;i<4;i++)value.bits64[i]=next64();
    value.bits64[4]=0;
    if(value.IsGreaterOrEqual(&prime))value.Sub(&prime);
    if(value.IsZero())value.SetInt32(1);
  }
}
static void original(const std::array<Int,N>& input,std::array<Int,N>& output){
  output=input;
  IntGroup batch(N);batch.Set(output.data());batch.ModInv();
}
// Non-overlapping contiguous segments, W independent prefix recurrences,
// ONE modular inverse of the product of all N denominators.
static void segmented(const std::array<Int,N>& input,std::array<Int,N>& output,int W){
  std::array<Int,N> prefixes;
  std::array<Int,16> totals,groups_inverse;
  std::array<int,16> start{},end{};
  int longest=0;
  for(int g=0;g<W;g++){
    start[g]=(N*g)/W;
    end[g]=(N*(g+1))/W;
    longest=std::max(longest,end[g]-start[g]);
  }
  // Interleave independent prefix chains for compiler/processor ILP.
  for(int step=0;step<longest;step++){
    for(int g=0;g<W;g++){
      const int pos=start[g]+step;
      if(pos>=end[g])continue;
      if(step==0)prefixes[pos].Set(const_cast<Int*>(&input[pos]));
      else prefixes[pos].ModMulK1(&prefixes[pos-1],const_cast<Int*>(&input[pos]));
    }
  }
  for(int g=0;g<W;g++)totals[g].Set(&prefixes[end[g]-1]);
  // Small top-level global prefix and exactly ONE field inverse.
  std::array<Int,16> top_prefix;
  top_prefix[0].Set(&totals[0]);
  for(int g=1;g<W;g++)top_prefix[g].ModMulK1(&top_prefix[g-1],&totals[g]);
  Int total_inverse(&top_prefix[W-1]);total_inverse.ModInv();
  // Montgomery backward propagation across segment totals.
  for(int g=W-1;g>=0;g--){
    if(g==0)groups_inverse[0].Set(&total_inverse);
    else groups_inverse[g].ModMulK1(&top_prefix[g-1],&total_inverse);
    total_inverse.ModMulK1(&totals[g]);
  }
  // Interleave independent suffix inversions, preserving original order.
  for(int step=0;step<longest;step++){
    for(int g=0;g<W;g++){
      const int pos=end[g]-1-step;
      if(pos<start[g])continue;
      if(pos==start[g]){
        output[pos].Set(&groups_inverse[g]);
      }else{
        output[pos].ModMulK1(&prefixes[pos-1],&groups_inverse[g]);
        groups_inverse[g].ModMulK1(const_cast<Int*>(&input[pos]));
      }
    }
  }
}
static void verify(Int&prime){
  std::array<Int,N> input,control,candidate;
  fill_input(input,prime);
  // Force predictable edge values in every batch, never zero.
  input[0].SetInt32(1);
  input[N/2].Set(&prime);input[N/2].SubOne();
  input[N-1].SetInt32(2);
  for(int trial=0;trial<40;trial++){
    if(trial>0)fill_input(input,prime);
    original(input,control);
    for(int W:W_LIST){
      segmented(input,candidate,W);
      for(int k=0;k<N;k++){
        if(!candidate[k].IsEqual(&control[k])){
          std::fprintf(stderr,"FAIL: W=%d trial=%d index=%d, wrong inverse\n",W,trial,k);
          std::exit(1);
        }
        Int product;
        product.ModMulK1(&input[k],&candidate[k]);
        if(!product.IsOne()){
          std::fprintf(stderr,"FAIL: W=%d trial=%d index=%d, inverse check\n",W,trial,k);
          std::exit(1);
        }
      }
    }
  }
  std::printf("PASS: %d full affine batches × 513 denominators × 5 widths, exact field inverses and independent x*x^-1=1\n",40);
}
static double measure(int W,double seconds,std::uint64_t&checksum,Int&prime){
  std::array<Int,N> input,output; fill_input(input,prime);
  volatile uint64_t sink=0;
  std::uint64_t batches=0;
  auto invoke=[&](){
    // Alter a canonical low limb on each run, no repeated invariant values.
    input[0].bits64[0]^=0x9e3779b97f4a7c15ULL;
    if(input[0].IsZero())input[0].SetInt32(1);
    if(W==0)original(input,output);
    else segmented(input,output,W);
    sink^=output[batches%N].bits64[0];
    batches++;
  };
  for(int k=0;k<2;k++)invoke();
  auto start=std::chrono::steady_clock::now();
  double elapsed=0;
  do {
    // Four inversions minimum per clock sample; prevents timer resolution noise.
    for(int k=0;k<4;k++)invoke();
    elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  }while(elapsed<seconds);
  checksum^=sink;
  return double(batches-2)/elapsed;
}
int main(int argc,char**argv){
  Int prime;prime.SetBase16("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F");
  Int::SetupField(&prime);
  if(argc>=2&&std::string(argv[1])=="--verify"){verify(prime);return 0;}
  double seconds=10;int repeats=2;
  for(int i=1;i<argc;i++){
    std::string arg=argv[i];
    if(arg=="--seconds"&&i+1<argc)seconds=std::stod(argv[++i]);
    else if(arg=="--repeats"&&i+1<argc)repeats=std::stoi(argv[++i]);
    else{std::fprintf(stderr,"usage: --verify | --seconds 10 --repeats 2\n");return 2;}
  }
  if(seconds<.1||seconds>60||repeats<1||repeats>8)return 2;
  std::vector<int> widths={0,1,2,4,8,16};
  std::uint64_t checksum=0;
  std::cout<<"repeat,width,batches_per_second,denominators_per_second,microseconds_per_batch,seconds\n";
  for(int rep=0;rep<repeats;rep++){
    if(rep%2)std::reverse(widths.begin(),widths.end());
    for(int width:widths){
      double rate=measure(width,seconds,checksum,prime);
      std::cout<<rep+1<<","<<width<<","<<std::fixed<<std::setprecision(3)
               <<rate<<","<<rate*N<<","<<1e6/rate<<","<<seconds
               <<"\n"<<std::flush;
    }
  }
  std::fprintf(stderr,"batch-affine-checksum=%016llx\n",(unsigned long long)checksum);
  return 0;
}
