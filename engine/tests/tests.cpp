#include "simulation.hpp"
#include <cstdlib>
#include <iostream>
#include <random>
using namespace confluence;
int checks=0;
void require(bool condition,const char* message){++checks;if(!condition){std::cerr<<"FAIL: "<<message<<"\n";std::exit(1);}}
int main(){
    std::mt19937 rng(42);MinHeap<int> heap;std::vector<int> reference;
    for(int i=0;i<1000;++i){int v=static_cast<int>(rng()%10000);heap.push(v);reference.push_back(v);}
    std::sort(reference.begin(),reference.end());for(int v:reference)require(heap.pop()==v,"heap order");require(heap.empty(),"heap empty");
    Grid g(5,5,0);
    for(int mask=0;mask<256;++mask){for(int p=1;p<=8;++p)g.cells[p]=(mask>>(p-1))&1;
        auto a=search(g,0,24),b=search(g,0,24,false);require(a.path.size()==b.path.size(),"A* BFS agreement");
        for(std::size_t i=1;i<a.path.size();++i)require(g.free(a.path[i])&&g.manhattan(a.path[i-1],a.path[i])==1,"valid A* path");}
    require(search(g,0,0).path.size()==1,"start equals goal");
    Grid unknown(5,5);unknown.cells[12]=0;require(frontiers(unknown).size()==1,"frontier at unknown boundary");
    Grid full(5,5,0);require(frontiers(full).empty(),"fully known no frontiers");
    for(int n=1;n<=5;++n)for(int test=0;test<30;++test){std::vector<std::vector<int64_t>> c(n,std::vector<int64_t>(n));for(auto& row:c)for(auto& v:row)v=static_cast<int>(rng()%100)-50;
        auto answer=hungarian(c);int64_t actual=0,best=1000000;for(int i=0;i<n;++i)actual+=c[i][answer[i]];
        std::vector<int> perm(n);for(int i=0;i<n;++i)perm[i]=i;do{int64_t cost=0;for(int i=0;i<n;++i)cost+=c[i][perm[i]];best=std::min(best,cost);}while(std::next_permutation(perm.begin(),perm.end()));require(actual==best,"Hungarian exhaustive oracle");}
    auto rectangular=hungarian({{3,1,9},{1,9,2}});require(rectangular[0]==1&&rectangular[1]==0,"rectangular Hungarian");
    require(arbitrate(full,{0,1},{1,0},{true,true})==std::vector<int>({0,1}),"swap rejected");
    require(arbitrate(full,{0,1,2},{1,2,2},{true,true,false})==std::vector<int>({0,1,2}),"stationary rejection cascade");
    require(arbitrate(full,{0,1},{5,5},{true,true})==std::vector<int>({5,1}),"duplicate destination");
    for(int i=0;i<2000;++i){std::vector<int> pos={0,1,5,6},intent=pos;for(int j=0;j<4;++j){auto ns=full.neighbors(pos[j]);ns.push_back(pos[j]);intent[j]=ns[rng()%ns.size()];}
        auto committed=arbitrate(full,pos,intent,{true,true,true,true},i%4);require(std::set<int>(committed.begin(),committed.end()).size()==4,"arbiter unique vertices");
        for(int a=0;a<4;++a)for(int b=a+1;b<4;++b)require(!(committed[a]==pos[b]&&committed[b]==pos[a]),"arbiter no swap");}
    Grid small(3,3,0);auto joint=cbs(small,{3,5},{5,3},12);require(!joint.paths.empty(),"CBS resolves crossing");require(first_conflict(joint.paths).a<0,"CBS conflict free");
    int sum=0;for(auto& p:joint.paths)sum+=static_cast<int>(p.size())-1;require(sum==6,"CBS known optimum");
    auto limited=cbs(small,{3,5},{5,3},12,0);require(limited.exhausted,"CBS budget reported");
    auto lowLimited=cbs(small,{3,5},{5,3},12,5000,3);require(lowLimited.exhausted&&lowLimited.low<=3,"CBS low-level budget applies to complete replan");
    Reservations r;r.reserve({1,1,1},3);auto timed=space_time(small,0,2,6,r);require(!timed.path.empty(),"reservation detour");
    Grid detour(9,9,0);for(int y=0;y<8;++y)detour.cells[y*9+4]=1;
    auto prefix=space_time(detour,3,5,4,{}, {},0,100000,true);
    require(prefix.path.size()==5&&prefix.path[1]==12,"rolling prefix advances around a long wall");
    Knowledge k(3,3);require(k.merge(0,1,3,0),"merge observation");require(!k.merge(0,0,2,2)&&k.grid.cells[0]==1,"stale merge rejected");require(k.merge(0,0,4,1),"obstacle reopening");
    k.merge_peer(2,0,"FAILED",5,0);require(!k.planning_grid().free(0)&&k.grid.free(0),"observed failure blocks planning without corrupting static map");
    k.merge_peer(2,0,"ACTIVE",6,0);require(k.planning_grid().free(0),"observed restoration unblocks planning");
    json cfg={{"width",16},{"height",16},{"seed","123"},{"agentCount",4},{"energy",{{"capacity",10000000}}}};
    Simulation s1,s2;s1.initialize(cfg);s2.initialize(cfg);require(s1.scenario()==s2.scenario(),"map deterministic");
    for(int i=0;i<40;++i){s1.advance();s2.advance();auto a=s1.snapshot(),b=s2.snapshot();require(a["stateHash"]==b["stateHash"],"state deterministic");for(auto& agent:a["agents"])require(agent["energy"].get<int64_t>()>=0,"energy nonnegative");}
    std::cout<<"PASS "<<checks<<" assertions\n";
}
