#pragma once
#include "algorithms.hpp"
#include <cmath>
#include <string>

namespace confluence {
struct Features {
    double gain=0,priority=0,reliability=.5,communication=.5,distance=0,energy=0,uncertainty=0,workload=0,bytes=0,switching=0;
};
inline int adaptive_score(const Features& f) {
    return static_cast<int>(std::lround(10000*(.25*f.gain+.15*f.priority+.10*f.reliability+.10*f.communication
        -.15*f.distance-.10*f.energy-.05*f.uncertainty-.04*f.workload-.03*f.bytes-.03*f.switching)));
}
struct Candidate {
    int cell=-1,region=0,distance=INF,gain=0,energy=0,score=0;
    Features features;
    bool feasible=false;
};
inline std::vector<int> match(const std::vector<std::vector<Candidate>>& rows,const std::string& strategy) {
    int n=static_cast<int>(rows.size());if(!n)return {};
    int m=static_cast<int>(rows[0].size());std::vector<int> result(n,-1);
    if(strategy=="greedy") {
        std::vector<std::tuple<int,int,int>> pairs;
        for(int i=0;i<n;++i)for(int j=0;j<m;++j)if(rows[i][j].feasible)pairs.push_back({rows[i][j].distance,i,j});
        std::sort(pairs.begin(),pairs.end());std::set<int> used;
        for(auto [d,i,j]:pairs)if(result[i]<0&&!used.count(j)){result[i]=j;used.insert(j);}
        return result;
    }
    std::vector<std::vector<int64_t>> costs(n,std::vector<int64_t>(m+n,0));
    for(int i=0;i<n;++i) {
        for(int j=0;j<m;++j)costs[i][j]=!rows[i][j].feasible?1000000000:
            (strategy=="adaptive"?-rows[i][j].score:rows[i][j].distance);
        if(strategy!="adaptive")for(int j=m;j<m+n;++j) costs[i][j]=1000000;
    }
    auto assignment=hungarian(costs);
    for(int i=0;i<n;++i)if(assignment[i]<m&&rows[i][assignment[i]].feasible)result[i]=assignment[i];
    return result;
}
}
