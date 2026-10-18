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
#include <memory>
#include <exception>

using Clock=std::chrono::steady_clock;
using Ns=std::chrono::nanoseconds;
using U128=unsigned __int128;
static constexpr int GROUP=1024,HALF=512,MAX_W=16,MAX_LANES=32;
static constexpr uint64_t C=0x1000003d1ULL,P0=0xfffffffefffffc2fULL;
static constexpr uint64_t START=0xD2C55ULL-512; // known Puzzle20 scalar in first batch
static constexpr uint64_t PRODUCER_RANGE=uint64_t(1)<<32; // disjoint producer identities
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
    space.wait(lock,[&]{return done||occupancy<slots.size();});
    blocked_ns+=nano(begin,Clock::now());
    if(done)throw std::runtime_error("queue closed during producer push");
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
    done=true;ready.notify_all();space.notify_all();
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
  void produce_batch(uint64_t start,Point&center,int W,Queue&queue,Stats&st,bool verify){
    const auto begin=Clock::now();
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
      // Positive and negative point groups have MIRRORED indices.
      // Mapping slots by group_id modulo ring size collides even when
      // only two partial groups exist. Use a tiny associative packetizer.
      Packet* slot=nullptr;
      for(auto& candidate:assembling)
        if(candidate.group==g){slot=&candidate;break;}
      if(!slot){
        for(auto& candidate:assembling)
          if(candidate.group==-1){slot=&candidate;break;}
        if(!slot)throw std::runtime_error("more than four unfinished quartets");
        *slot=Packet{};slot->group=g;slot->start_key=start;
      }
      Packet&pkt=*slot;
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
    // Exactly as in Keyhunt's incremental-center hot path: advance by
    // 1024*G using the already inverted dx[512], NOT a new scalar multiply.
    Int next_dy,next_s,next_sq;
    next_dy.ModSub(&twice_g.y,&center.y);
    next_s.ModMulK1(&next_dy,&dx[HALF]);
    next_sq.ModSquareK1(&next_s);
    Point next_center=center;
    next_center.x.ModSub(&next_sq,&center.x);
    next_center.x.ModSub(&twice_g.x);
    next_center.y.ModSub(&twice_g.x,&next_center.x);
    next_center.y.ModMulK1(&next_s);
    next_center.y.ModSub(&twice_g.y);
    center=next_center;
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
  void consume(Queue&q,Stats&st,bool verify,int batch_limit,int producer_count){
    Packet p;
    std::vector<std::array<uint8_t,GROUP>> all_seen;
    if(verify)all_seen.resize(size_t(batch_limit)*size_t(producer_count));
    while(q.pop(p)){
      if(p.mask!=15)throw std::runtime_error("consumer got incomplete packet");
      Point points[4];
      for(int lane=0;lane<4;lane++){
        if(p.offset[lane]!=p.group*4+lane)
          throw std::runtime_error("packet lane mapping invalid");
        for(int j=0;j<5;j++)points[lane].x.bits64[j]=p.x[lane][j];
        points[lane].y.SetInt32(p.odd[lane]?1:0);
        if(verify){
          if(p.start_key<START)
            throw std::runtime_error("invalid producer start");
          uint64_t relative=p.start_key-START;
          uint64_t producer=relative/PRODUCER_RANGE;
          uint64_t batch=(relative%PRODUCER_RANGE)/GROUP;
          uint64_t slot=producer*uint64_t(batch_limit)+batch;
          if(producer>=uint64_t(producer_count)||
             batch>=uint64_t(batch_limit)||
             (relative%GROUP)!=0||
             all_seen[slot][p.offset[lane]]++)
            throw std::runtime_error("consumer duplicate/out-of-range index");
        }
      }
      const auto h0=Clock::now();
      uint8_t mask=secp.GetHash160_fromXYParityTarget(P2PKH,
        &points[0],&points[1],&points[2],&points[3],target);
      st.hash_ns+=nano(h0,Clock::now());
      if(verify){
        uint8_t actual[4][20]{},reference[20]{};
        secp.GetHash160_fromXYParity(P2PKH,&points[0],&points[1],
                                      &points[2],&points[3],
                                      actual[0],actual[1],actual[2],actual[3]);
        for(int lane=0;lane<4;lane++){
          Int scalar;scalar.SetInt64(p.start_key+p.offset[lane]);
          Point pub=secp.ComputePublicKey(&scalar);
          secp.GetHash160(P2PKH,true,pub,reference);
          if(std::memcmp(reference,actual[lane],20)!=0)
            throw std::runtime_error("HASH160 digest mismatch at key offset "+
                                     std::to_string(p.offset[lane]));
          const bool match=std::memcmp(reference,target,20)==0;
          if(match!=bool(mask&(1u<<lane)))
            throw std::runtime_error("HASH160 target mask mismatch");
        }
      }
      for(int lane=0;lane<4;lane++)if(mask&(1u<<lane)){
        if(p.start_key+p.offset[lane]!=0xD2C55ULL)
          throw std::runtime_error("incorrect HASH160 match");
        st.hits++;
      }
      st.consumed+=4;st.hashed+=4;
    }
    if(verify)for(int batch=0;batch<batch_limit*producer_count;batch++)
      for(int idx=0;idx<GROUP;idx++)if(all_seen[batch][idx]!=1)
        throw std::runtime_error("consumer missed a key");
  }
};
struct RunResult{Stats producer,consumer;uint64_t elapsed_ns=0;size_t peak=0;
  uint64_t blocked=0,idle=0;};
static RunResult run(Engine&consumer_engine,int width,int queue_capacity,
                     double seconds,bool verify,int verify_batches,int producers){
  // Initialize each ECC source separately before the timed run.
  // Each producer's scalar range is disjoint, separated by 2^32 keys.
  // Within its assigned range it uses the SAME incremental +1024G center.
  std::vector<std::unique_ptr<Engine>> engines;
  std::vector<Point> centers(static_cast<size_t>(producers));
  for(int id=0;id<producers;id++){
    auto src=std::make_unique<Engine>();
    src->init_minus();
    Int first;first.SetInt64(START+uint64_t(id)*PRODUCER_RANGE+HALF);
    centers[size_t(id)]=src->secp.ComputePublicKey(&first);
    engines.push_back(std::move(src));
  }
  Queue q(queue_capacity);
  RunResult result{};
  std::vector<Stats> local_stats(static_cast<size_t>(producers));
  std::mutex error_mutex;
  std::exception_ptr first_error;
  auto fail=[&](){
    {
      std::lock_guard<std::mutex>lock(error_mutex);
      if(!first_error)first_error=std::current_exception();
    }
    q.close();
  };
  auto started=Clock::now();
  std::thread consumer([&]{
    try{
      consumer_engine.consume(q,result.consumer,verify,
                              verify?verify_batches:0,producers);
    }catch(...){fail();}
  });
  std::vector<std::thread> workers;
  for(int id=0;id<producers;id++){
    workers.emplace_back([&,id]{
      try{
        const uint64_t first_key=START+uint64_t(id)*PRODUCER_RANGE;
        uint64_t batch=0;
        do {
          engines[size_t(id)]->produce_batch(first_key+batch*GROUP,
                   centers[size_t(id)],width,q,local_stats[size_t(id)],verify);
          batch++;
        }while(verify?batch<uint64_t(verify_batches):
                       nano(started,Clock::now())<seconds*1e9);
      }catch(...){fail();}
    });
  }
  for(auto&t:workers)t.join();
  q.close();consumer.join();
  if(first_error)std::rethrow_exception(first_error);
  result.elapsed_ns=nano(started,Clock::now());
  result.peak=q.max_occupancy;result.blocked=q.blocked_ns;
  result.idle=q.idle_ns;
  for(const auto&st:local_stats){
    result.producer.produced+=st.produced;
    result.producer.prep_ns+=st.prep_ns;
    result.producer.xy_ns+=st.xy_ns;
    result.producer.packets+=st.packets;
  }
  if(result.producer.produced!=result.consumer.consumed||
     result.producer.produced!=result.consumer.hashed)
    throw std::runtime_error("ECC->HASH160 queue lost keys");
  if(verify&&result.consumer.hits!=1)
    throw std::runtime_error("expected Puzzle20 target hit exactly once");
  return result;
}
int main(int argc,char**argv){
  int width=4,queue_capacity=32,producers=1;
  double seconds=60;bool verify=false;int verify_batches=3;
  for(int i=1;i<argc;i++){
    std::string arg=argv[i];
    if(arg=="--verify")verify=true;
    else if(arg=="--verify-batches"&&i+1<argc)verify_batches=std::atoi(argv[++i]);
    else if(arg=="--width"&&i+1<argc)width=std::atoi(argv[++i]);
    else if(arg=="--producers"&&i+1<argc)producers=std::atoi(argv[++i]);
    else if(arg=="--queue"&&i+1<argc)queue_capacity=std::atoi(argv[++i]);
    else if(arg=="--seconds"&&i+1<argc)seconds=std::atof(argv[++i]);
    else {std::cerr<<"usage: --width 1|2|4|8|16 --queue 32 --seconds 60 [--verify]\n";return 2;}
  }
  if(!(width==1||width==2||width==4||width==8||width==16)||
     queue_capacity<2||queue_capacity>1024||producers<1||producers>3||seconds<.1||seconds>600||
     verify_batches<1||verify_batches>100)return 2;
  try{
    Engine engine;engine.init_minus();
    RunResult r=run(engine,width,queue_capacity,seconds,verify,verify_batches,producers);
    const double elapsed=r.elapsed_ns/1e9;
    std::cout<<"producers,width,queue,mode,elapsed_s,produced_keys,hashed_keys,"
                "hashed_Mkeys_s,producer_inverse_ms,producer_points_ms,"
                "consumer_hash_ms,queue_full_ms,queue_empty_ms,peak_packets,hits\n";
    std::cout<<producers<<","<<width<<","<<queue_capacity<<","<<(verify?"verify":"bench")<<","
             <<std::fixed<<std::setprecision(4)<<elapsed<<","
             <<r.producer.produced<<","<<r.consumer.hashed<<","
             <<std::setprecision(6)<<r.consumer.hashed/elapsed/1e6<<","
             <<std::setprecision(3)<<r.producer.prep_ns/1e6<<","
             <<r.producer.xy_ns/1e6<<","<<r.consumer.hash_ns/1e6<<","
             <<r.blocked/1e6<<","<<r.idle/1e6<<","<<r.peak<<","
             <<r.consumer.hits<<"\n";
    if(verify)std::cerr<<"PASS: "<<(GROUP*verify_batches*producers)
       <<" exact ECC points across "<<verify_batches
       <<" successive centers on "<<producers<<" producers match independent scalar multiplication; "
       "HASH160 digests, all indexed packets and Puzzle20 target PASS\n";
    return 0;
  }catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}
}
