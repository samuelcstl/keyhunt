// R8 EXPERIMENT: REAL ECC POINT PRODUCER -> BOUNDED RING -> 4-LANE HASH160.
// One producer thread, one consumer thread; W independent 4x64 field
// products across slope and Y stages, independent from hash SIMD width 4.
// No production worker or SQLite campaign; optional independent full oracle.
#include "../secp256k1/SECP256k1.h"
#include "../secp256k1/IntGroup.h"
#include <array>
#include <vector>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <iostream>
#include <iomanip>
#include <stdexcept>
#include <string>
#include <limits>

using Clock=std::chrono::steady_clock;
using Ns=std::chrono::nanoseconds;
using U128=unsigned __int128;
static constexpr int GROUP=1024,HALF=512,MAX_W=16,MAX_LANES=32;
static constexpr uint64_t C=0x1000003d1ULL,P0=0xfffffffefffffc2fULL;
static constexpr uint64_t START=0xD2C55ULL-512; // known Puzzle20 scalar in first batch
static uint64_t nano(Clock::time_point a,Clock::time_point b){
  return std::chrono::duration_cast<Ns>(b-a).count();
}
static void reduce(uint64_t dst[5],const uint64_t t[8]){
  uint64_t z[4];
  U128 carry=0;
  for(int k=0;k<4;k++){
    U128 v=U128(t[4+k])*C+t[k]+carry;
    z[k]=uint64_t(v);carry=v>>64;
  }
  // R5 winning first-fold scheduling, exact fallback for remaining carry.
  U128 v=U128(uint64_t(carry))*C+z[0];
  z[0]=uint64_t(v);carry=v>>64;
  for(int k=1;k<4;k++){v=U128(z[k])+carry;z[k]=uint64_t(v);carry=v>>64;}
  while(carry){
    v=U128(uint64_t(carry))*C+z[0];
    z[0]=uint64_t(v);carry=v>>64;
    for(int k=1;k<4;k++){v=U128(z[k])+carry;z[k]=uint64_t(v);carry=v>>64;}
  }
  if(z[3]==UINT64_MAX&&z[2]==UINT64_MAX&&z[1]==UINT64_MAX&&z[0]>=P0){
    z[0]-=P0;z[1]=z[2]=z[3]=0;
  }
  for(int k=0;k<4;k++)dst[k]=z[k];
  dst[4]=0;
}
// Integer instruction-level parallelism: round-robin schoolbook products
// across n independent 4x64 products, not SIMD 64x64 (unavailable on NEON).
// All products return the exact canonical secp256k1 field residue.
static void mul_many(Int*output,const Int*left,const Int*right,int n,int width){
  if(width==1){for(int l=0;l<n;l++)output[l].ModMulK1(const_cast<Int*>(&left[l]),
                                                       const_cast<Int*>(&right[l]));return;}
  std::array<std::array<uint64_t,8>,MAX_LANES> t{};
  std::array<U128,MAX_LANES> carry{};
  for(int i=0;i<4;i++){
    for(int l=0;l<n;l++)carry[l]=0;
    for(int j=0;j<4;j++){
      for(int l=0;l<n;l++){
        U128 v=U128(left[l].bits64[j])*right[l].bits64[i]
                +t[l][i+j]+carry[l];
        t[l][i+j]=uint64_t(v);carry[l]=v>>64;
      }
    }
    for(int l=0;l<n;l++)t[l][i+4]=uint64_t(carry[l]);
  }
  for(int l=0;l<n;l++)reduce(output[l].bits64,t[l].data());
}
struct Packet{
  uint64_t start_key=0;
  uint64_t x[4][5]{};
  uint16_t offset[4]{};
  uint8_t odd[4]{};
  uint8_t mask=0;
  int group=-1;
};
struct Stats{
  uint64_t produced=0,consumed=0,hashed=0,hits=0;
  uint64_t prep_ns=0,xy_ns=0,hash_ns=0,blocked_ns=0,idle_ns=0;
  uint64_t packets=0,max_queue=0;
  uint64_t seen_fail=0;
};
struct Queue{
  std::vector<Packet> slots;
  std::mutex m;
  std::condition_variable ready,space;
  size_t rd=0,wr=0,occupancy=0,max_occupancy=0;
  bool done=false;
  uint64_t blocked_ns=0,idle_ns=0;
  explicit Queue(int capacity):slots(size_t(capacity)){}
  void push(const Packet&p){
    std::unique_lock<std::mutex>lock(m);
    auto begin=Clock::now();
    space.wait(lock,[&]{return occupancy<slots.size();});
    blocked_ns+=nano(begin,Clock::now());
    slots[wr]=p;wr=(wr+1)%slots.size();occupancy++;
    max_occupancy=std::max(max_occupancy,occupancy);
    ready.notify_one();
  }
  bool pop(Packet&p){
    std::unique_lock<std::mutex>lock(m);
    auto begin=Clock::now();
    ready.wait(lock,[&]{return occupancy||done;});
    idle_ns+=nano(begin,Clock::now());
    if(!occupancy)return false;
    p=slots[rd];rd=(rd+1)%slots.size();occupancy--;
    space.notify_one();
    return true;
  }
  void close(){
    std::lock_guard<std::mutex>lock(m);
    done=true;ready.notify_all();
  }
};
struct Engine{
  Secp256K1 secp;
  std::array<Point,HALF> generator;
  std::array<Int,HALF> minus_y;
  Point twice_g;
  uint8_t target[20]{};
  Engine(){
    secp.Init();
    generator[0]=secp.G;
    generator[1]=secp.DoubleDirect(generator[0]);
    for(int i=2;i<HALF;i++)generator[i]=secp.AddDirect(generator[i-1],secp.G);
    twice_g=secp.DoubleDirect(generator[HALF-1]);
    Int k;k.SetInt64(0xD2C55);
    Point pub=secp.ComputePublicKey(&k);
    secp.GetHash160(P2PKH,true,pub,target);
  }
  // After 511 symmetric point pairs, one remaining boundary point (offset 0)
  // is added explicitly. Center is offset 512. No omissions or duplicate keys.
  void produce_batch(uint64_t start,int W,Queue&queue,Stats&st,bool verify){
    const auto begin=Clock::now();
    Int k;k.SetInt64(start+HALF);
    Point center=secp.ComputePublicKey(&k);
    std::array<Int,HALF+1> dx;
    for(int i=0;i<HALF;i++)dx[i].ModSub(&generator[i].x,&center.x);
    dx[HALF].ModSub(&twice_g.x,&center.x);
    IntGroup grp(HALF+1);grp.Set(dx.data());grp.ModInv();
    const auto invdone=Clock::now();st.prep_ns+=nano(begin,invdone);
    std::array<Packet,4> assembling{};
    for(auto& p:assembling)p.group=-1;
    std::array<uint8_t,GROUP>seen{};
    auto emit=[&](uint16_t idx,Point&pt){
      if(verify){
        if(seen[idx]++)throw std::runtime_error("duplicate candidate in producer");
        Int scalar;scalar.SetInt64(start+idx);
        Point expected=secp.ComputePublicKey(&scalar);
        if(!pt.x.IsEqual(&expected.x)||!pt.y.IsEqual(&expected.y))
          throw std::runtime_error("ECC point mismatch at logical offset "+std::to_string(idx));
      }
      const int g=idx/4,lane=idx%4;
      Packet&pkt=assembling[size_t(g)%assembling.size()];
      if(pkt.group!=g){
        if(pkt.mask)throw std::runtime_error("partial packet collision");
        pkt=Packet{};pkt.group=g;pkt.start_key=start;
      }
      if(pkt.mask&(1u<<lane))throw std::runtime_error("duplicate lane in packet");
      pkt.mask|=uint8_t(1u<<lane);
      pkt.offset[lane]=idx;
      for(int j=0;j<5;j++)pkt.x[lane][j]=pt.x.bits64[j];
      pkt.odd[lane]=pt.y.IsOdd();
      st.produced++;
      if(pkt.mask==15){
        queue.push(pkt);
        st.packets++;pkt=Packet{};
        pkt.group=-1;
      }
    };
    auto xybegin=Clock::now();
    emit(HALF,center);
    std::array<Int,MAX_LANES>aa{},bb{},slopes{},yy_a{},yy_b{},yy_out{};
    std::array<Point,MAX_W>plus{},minus{};
    std::array<Int,MAX_W>sqplus{},sqminus{};
    for(int i0=0;i0<HALF-1;i0+=W){
      const int count=std::min(W,HALF-1-i0);
      for(int lane=0;lane<count;lane++){
        const int i=i0+lane;
        aa[2*lane].ModSub(&generator[i].y,&center.y);
        aa[2*lane+1].ModSub(&minus_y[i],&center.y);
        bb[2*lane].Set(&dx[i]);
        bb[2*lane+1].Set(&dx[i]);
      }
      mul_many(slopes.data(),aa.data(),bb.data(),2*count,W);
      for(int lane=0;lane<count;lane++){
        const int i=i0+lane;
        sqplus[lane].ModSquareK1(&slopes[2*lane]);
        sqminus[lane].ModSquareK1(&slopes[2*lane+1]);
        plus[lane]=center;minus[lane]=center;
        plus[lane].x.ModSub(&sqplus[lane],&center.x);
        plus[lane].x.ModSub(&generator[i].x);
        minus[lane].x.ModSub(&sqminus[lane],&center.x);
        minus[lane].x.ModSub(&generator[i].x);
        yy_a[2*lane].ModSub(&generator[i].x,&plus[lane].x);
        yy_a[2*lane+1].ModSub(&generator[i].x,&minus[lane].x);
        yy_b[2*lane].Set(&slopes[2*lane]);
        yy_b[2*lane+1].Set(&slopes[2*lane+1]);
      }
      mul_many(yy_out.data(),yy_a.data(),yy_b.data(),2*count,W);
      for(int lane=0;lane<count;lane++){
        const int i=i0+lane;
        plus[lane].y.Set(&yy_out[2*lane]);
        plus[lane].y.ModSub(&generator[i].y);
        minus[lane].y.Set(&yy_out[2*lane+1]);
        minus[lane].y.ModAdd(&generator[i].y);
        emit(uint16_t(HALF+i+1),plus[lane]);
        emit(uint16_t(HALF-i-1),minus[lane]);
      }
    }
    // Explicit last negative point at offset 0.
    Int dy,s,ss;
    Point negative=center;
    dy.ModSub(&minus_y[HALF-1],&center.y);
    s.ModMulK1(&dy,&dx[HALF-1]);
    ss.ModSquareK1(&s);
    negative.x.ModSub(&ss,&center.x);
    negative.x.ModSub(&generator[HALF-1].x);
    negative.y.ModSub(&generator[HALF-1].x,&negative.x);
    negative.y.ModMulK1(&s);
    negative.y.ModAdd(&generator[HALF-1].y);
    emit(0,negative);
    if(verify){
      for(int i=0;i<GROUP;i++)if(seen[i]!=1)
        throw std::runtime_error("missing source candidate "+std::to_string(i));
    }
    for(const auto&p:assembling)if(p.mask)
      throw std::runtime_error("unflushed point packet");
    st.xy_ns+=nano(xybegin,Clock::now());
  }
  void init_minus(){
    for(int i=0;i<HALF;i++){
      minus_y[i].Set(&generator[i].y);
      minus_y[i].ModNeg();
    }
  }
  void consume(Queue&q,Stats&st,bool verify,int batch_limit){
    Packet p;
    std::vector<std::array<uint8_t,GROUP>> all_seen;
    if(verify)all_seen.resize(size_t(batch_limit));
    while(q.pop(p)){
      if(p.mask!=15)throw std::runtime_error("consumer got incomplete packet");
      Point points[4];
      for(int lane=0;lane<4;lane++){
        if(p.offset[lane]!=p.group*4+lane)
          throw std::runtime_error("packet lane mapping invalid");
        for(int j=0;j<5;j++)points[lane].x.bits64[j]=p.x[lane][j];
        points[lane].y.SetInt32(p.odd[lane]?1:0);
        if(verify){
          int batch=int((p.start_key-START)/GROUP);
          if(batch<0||batch>=batch_limit||all_seen[batch][p.offset[lane]]++)
            throw std::runtime_error("consumer duplicate/out-of-range index");
        }
      }
      const auto h0=Clock::now();
      uint8_t mask=secp.GetHash160_fromXYParityTarget(P2PKH,
        &points[0],&points[1],&points[2],&points[3],target);
      st.hash_ns+=nano(h0,Clock::now());
      for(int lane=0;lane<4;lane++)if(mask&(1u<<lane)){
        if(p.start_key+p.offset[lane]!=0xD2C55ULL)
          throw std::runtime_error("incorrect HASH160 match");
        st.hits++;
      }
      st.consumed+=4;st.hashed+=4;
    }
    if(verify)for(int batch=0;batch<batch_limit;batch++)
      for(int idx=0;idx<GROUP;idx++)if(all_seen[batch][idx]!=1)
        throw std::runtime_error("consumer missed a key");
  }
};
struct RunResult{Stats producer,consumer;uint64_t elapsed_ns=0;size_t peak=0;
  uint64_t blocked=0,idle=0;};
static RunResult run(Engine&engine,int width,int queue_capacity,
                     double seconds,bool verify){
  Queue q(queue_capacity);
  RunResult result{};
  auto started=Clock::now();
  std::exception_ptr ep=nullptr;
  std::thread consumer([&]{
    try{engine.consume(q,result.consumer,verify,verify?1:0);}
    catch(...){ep=std::current_exception();}
  });
  try{
    uint64_t batch=0;
    do{
      engine.produce_batch(START+batch*GROUP,width,q,result.producer,verify);
      batch++;
    }while(!verify&&nano(started,Clock::now())<seconds*1e9);
  }catch(...){
    // Queue will be drained; error rethrown after joining.
    q.close();consumer.join();throw;
  }
  q.close();consumer.join();
  if(ep)std::rethrow_exception(ep);
  result.elapsed_ns=nano(started,Clock::now());
  result.peak=q.max_occupancy;result.blocked=q.blocked_ns;
  result.idle=q.idle_ns;
  if(result.producer.produced!=result.consumer.consumed||
     result.producer.produced!=result.consumer.hashed)
    throw std::runtime_error("ECC->HASH160 queue lost keys");
  if(verify&&result.consumer.hits!=1)
    throw std::runtime_error("expected Puzzle20 target hit exactly once");
  return result;
}
int main(int argc,char**argv){
  int width=4,queue_capacity=32;
  double seconds=60;bool verify=false;
  for(int i=1;i<argc;i++){
    std::string arg=argv[i];
    if(arg=="--verify")verify=true;
    else if(arg=="--width"&&i+1<argc)width=std::atoi(argv[++i]);
    else if(arg=="--queue"&&i+1<argc)queue_capacity=std::atoi(argv[++i]);
    else if(arg=="--seconds"&&i+1<argc)seconds=std::atof(argv[++i]);
    else {std::cerr<<"usage: --width 1|2|4|8|16 --queue 32 --seconds 60 [--verify]\n";return 2;}
  }
  if(!(width==1||width==2||width==4||width==8||width==16)||
     queue_capacity<2||queue_capacity>1024||seconds<.1||seconds>600)return 2;
  try{
    Engine engine;engine.init_minus();
    RunResult r=run(engine,width,queue_capacity,seconds,verify);
    const double elapsed=r.elapsed_ns/1e9;
    std::cout<<"width,queue,mode,elapsed_s,produced_keys,hashed_keys,"
                "hashed_Mkeys_s,producer_inverse_ms,producer_points_ms,"
                "consumer_hash_ms,queue_full_ms,queue_empty_ms,peak_packets,hits\n";
    std::cout<<width<<","<<queue_capacity<<","<<(verify?"verify":"bench")<<","
             <<std::fixed<<std::setprecision(4)<<elapsed<<","
             <<r.producer.produced<<","<<r.consumer.hashed<<","
             <<std::setprecision(6)<<r.consumer.hashed/elapsed/1e6<<","
             <<std::setprecision(3)<<r.producer.prep_ns/1e6<<","
             <<r.producer.xy_ns/1e6<<","<<r.consumer.hash_ns/1e6<<","
             <<r.blocked/1e6<<","<<r.idle/1e6<<","<<r.peak<<","
             <<r.consumer.hits<<"\n";
    if(verify)std::cerr<<"PASS: all 1024 ECC points match independent scalar multiplication; "
                         "all indexed packets hashed once and Puzzle20 target recovered\n";
    return 0;
  }catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}
}
