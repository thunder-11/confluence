#pragma once
#include "simulation.hpp"
#include <random>
#include <functional>

namespace confluence {
// Exhaustive joint-state Dijkstra oracle for tiny static MAPF fixtures only.
// Optional zero-cost goal finalization permits passing through a goal before
// the final arrival, while charging every unfinished agent one unit per tick.
inline int tiny_soc_oracle(const Grid& grid,const std::vector<int>& starts,const std::vector<int>& goals) {
    const int n=static_cast<int>(starts.size()),flags=1<<n;
    auto encode=[&](const std::vector<int>& p,int done){int key=0;for(int i=n-1;i>=0;--i)key=key*grid.size()+p[i];return key*flags+done;};
    MinHeap<std::pair<int,int>> open;std::map<int,int> best;int root=encode(starts,0);best[root]=0;open.push({0,root});
    auto relax=[&](int key,int cost){if(!best.count(key)||cost<best[key]){best[key]=cost;open.push({cost,key});}};
    while(!open.empty()){
        auto [cost,key]=open.pop();if(best[key]!=cost)continue;int done=key%flags,code=key/flags;
        if(done==flags-1)return cost;
        std::vector<int> positions(n),next(n);for(int i=0;i<n;++i){positions[i]=code%grid.size();code/=grid.size();}
        int active=0;for(int i=0;i<n;++i)if(!(done&(1<<i))){++active;if(positions[i]==goals[i])relax(encode(positions,done|(1<<i)),cost);}
        std::function<void(int)> enumerate=[&](int agent){
            if(agent==n){relax(encode(next,done),cost+active);return;}
            auto choices=grid.neighbors(positions[agent]);choices.push_back(positions[agent]);
            for(int cell:choices)if(grid.free(cell)&&(!(done&(1<<agent))||cell==positions[agent])){
                bool valid=true;for(int peer=0;peer<agent;++peer)if(next[peer]==cell||(next[peer]==positions[agent]&&cell==positions[peer]))valid=false;
                if(valid){next[agent]=cell;enumerate(agent+1);}
            }
        };enumerate(0);
    }return -1;
}

inline json planner_study() {
    json result={{"studyVersion",1},{"spatial",json::array()},{"cbs",json::array()}};
    for(int size:{16,32,64,128})for(int seed=100;seed<130;++seed){
        std::mt19937 rng(seed*257+size);Grid grid(size,size,0);
        for(auto& cell:grid.cells)cell=(rng()%100<25)?1:0;
        for(int query=0;query<4;++query){int start=rng()%grid.size(),goal=rng()%grid.size();grid.cells[start]=grid.cells[goal]=0;
            auto began=std::chrono::steady_clock::now();auto bfs=search(grid,start,goal,false);double bfsMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-began).count();
            began=std::chrono::steady_clock::now();auto astar=search(grid,start,goal,true);double astarMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-began).count();
            if(bfs.path.size()!=astar.path.size())throw std::runtime_error("spatial shortest-path disagreement");
            result["spatial"].push_back({{"size",size},{"seed",seed},{"query",query},{"start",start},{"goal",goal},{"mapHash",hash_json(grid.cells)},{"cost",bfs.path.empty()?-1:static_cast<int>(bfs.path.size())-1},{"bfsExpanded",bfs.expanded},{"astarExpanded",astar.expanded},{"bfsMs",bfsMs},{"astarMs",astarMs}});
        }
    }
    Grid open(3,3,0),corridor(3,3,1);corridor.cells[3]=corridor.cells[4]=corridor.cells[5]=0;
    auto check=[&](const std::string& name,const Grid& grid,const std::vector<int>& starts,const std::vector<int>& goals,int high=5000){
        auto c=cbs(grid,starts,goals,18,high,100000);int oracle=tiny_soc_oracle(grid,starts,goals),cost=0;
        if(c.paths.empty())cost=-1;else{for(const auto& path:c.paths)cost+=static_cast<int>(path.size())-1;if(first_conflict(c.paths).a>=0||cost!=oracle)throw std::runtime_error("CBS oracle disagreement");}
        result["cbs"].push_back({{"fixture",name},{"starts",starts},{"goals",goals},{"grid",grid.cells},{"oracleCost",oracle},{"cbsCost",cost},{"highExpanded",c.high},{"lowExpanded",c.low},{"constraintsConsidered",c.constraintsConsidered},{"status",c.paths.empty()?(c.exhausted?"BUDGET_EXHAUSTED":"NO_SOLUTION"):"SUCCESS"},{"fallback",c.exhausted?json("reservations"):json(nullptr)}});
    };
    check("crossing",open,{3,5},{5,3});check("opposite_corners",open,{0,8},{8,0});check("three_agents",open,{0,2,8},{8,6,0});check("blocked_corridor",corridor,{3,5},{5,3},100);check("budget_fallback",open,{3,5},{5,3},0);
    return result;
}
}
