#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <limits>
#include <map>
#include <queue>
#include <set>
#include <stdexcept>
#include <tuple>
#include <utility>
#include <vector>

namespace confluence {
constexpr int INF = 100000000;

// Small reusable binary min-heap. Compare returns true when a precedes b.
template<class T, class Compare = std::less<T>> class MinHeap {
    std::vector<T> data;
    Compare before;
public:
    bool empty() const { return data.empty(); }
    std::size_t size() const { return data.size(); }
    void push(T value) {
        data.push_back(std::move(value));
        std::size_t i=data.size()-1;
        while(i && before(data[i],data[(i-1)/2])) {
            std::swap(data[i],data[(i-1)/2]); i=(i-1)/2;
        }
    }
    T pop() {
        if(empty()) throw std::out_of_range("empty heap");
        T result=std::move(data[0]);
        data[0]=std::move(data.back()); data.pop_back();
        std::size_t i=0;
        for(;;) {
            auto left=i*2+1, right=left+1, smallest=i;
            if(left<data.size() && before(data[left],data[smallest])) smallest=left;
            if(right<data.size() && before(data[right],data[smallest])) smallest=right;
            if(smallest==i) break;
            std::swap(data[i],data[smallest]); i=smallest;
        }
        return result;
    }
};

struct Grid {
    int width=0,height=0;
    std::vector<int> cells; // -1 unknown, 0 free, 1 blocked
    Grid()=default;
    Grid(int w,int h,int fill=-1):width(w),height(h),cells(w*h,fill){}
    int size() const { return width*height; }
    bool free(int p) const { return p>=0 && p<size() && cells[p]==0; }
    std::vector<int> neighbors(int p) const {
        std::vector<int> out;
        if(p<0 || p>=size()) return out;
        const int x=p%width,y=p/width;
        if(y) out.push_back(p-width);
        if(x+1<width) out.push_back(p+1);
        if(y+1<height) out.push_back(p+width);
        if(x) out.push_back(p-1);
        return out;
    }
    int manhattan(int a,int b) const {
        return std::abs(a%width-b%width)+std::abs(a/width-b/width);
    }
};
struct SearchResult {
    std::vector<int> path;
    int expanded=0;
    bool exhausted=false;
};
// Optimistic sensor footprint: unknown may be free, but known walls occlude.
inline std::vector<int> estimated_sensor_footprint(const Grid& known,int start,int radius) {
    std::vector<int> result;if(!known.free(start))return result;
    std::queue<std::pair<int,int>> open;std::set<int> seen;open.push({start,0});seen.insert(start);
    while(!open.empty()){auto [cell,depth]=open.front();open.pop();result.push_back(cell);
        if(depth==radius||known.cells[cell]==1)continue;
        for(int next:known.neighbors(cell))if(seen.insert(next).second)open.push({next,depth+1});
    }return result;
}
inline std::vector<int> distances(const Grid& g,int start) {
    std::vector<int> d(g.size(),INF);
    if(!g.free(start)) return d;
    std::queue<int> q; q.push(start); d[start]=0;
    while(!q.empty()) {
        int u=q.front();q.pop();
        for(int v:g.neighbors(u)) if(g.free(v) && d[v]==INF) {
            d[v]=d[u]+1;q.push(v);
        }
    }
    return d;
}
inline int component_count(const Grid& g) {
    std::vector<bool> seen(g.size());int count=0;std::queue<int> queue;
    for(int p=0;p<g.size();++p)if(g.free(p)&&!seen[p]){++count;seen[p]=true;queue.push(p);
        while(!queue.empty()){int u=queue.front();queue.pop();for(int v:g.neighbors(u))if(g.free(v)&&!seen[v]){seen[v]=true;queue.push(v);}}
    }return count;
}
inline SearchResult search(const Grid& g,int start,int goal,bool astar=true) {
    SearchResult out;
    if(!g.free(start)||!g.free(goal)) return out;
    std::vector<int> d(g.size(),INF),parent(g.size(),-1);
    if(!astar){
        std::queue<int> queue;queue.push(start);d[start]=0;
        while(!queue.empty()){
            int u=queue.front();queue.pop();++out.expanded;
            if(u==goal){for(int p=u;p!=-1;p=parent[p])out.path.push_back(p);std::reverse(out.path.begin(),out.path.end());return out;}
            for(int v:g.neighbors(u))if(g.free(v)&&d[v]==INF){d[v]=d[u]+1;parent[v]=u;queue.push(v);}
        }return out;
    }
    MinHeap<std::tuple<int,int,int>> open;
    d[start]=0;open.push({astar?g.manhattan(start,goal):0,0,start});
    while(!open.empty()) {
        auto [f,c,u]=open.pop();
        if(c!=d[u]) continue;
        ++out.expanded;
        if(u==goal) {
            for(int v=u;v!=-1;v=parent[v]) out.path.push_back(v);
            std::reverse(out.path.begin(),out.path.end());return out;
        }
        for(int v:g.neighbors(u)) if(g.free(v)&&c+1<d[v]) {
            d[v]=c+1;parent[v]=u;
            open.push({d[v]+(astar?g.manhattan(v,goal):0),d[v],v});
        }
    }
    return out;
}

inline std::vector<std::vector<int>> frontiers(const Grid& g) {
    std::vector<char> frontier(g.size()),seen(g.size());
    for(int u=0;u<g.size();++u) if(g.free(u))
        for(int v:g.neighbors(u)) if(g.cells[v]==-1) frontier[u]=true;
    std::vector<std::vector<int>> result;
    for(int u=0;u<g.size();++u) if(frontier[u]&&!seen[u]) {
        std::vector<int> group;std::queue<int> q;q.push(u);seen[u]=true;
        while(!q.empty()) {
            int v=q.front();q.pop();group.push_back(v);
            for(int n:g.neighbors(v)) if(frontier[n]&&!seen[n]) {seen[n]=true;q.push(n);}
        }
        std::sort(group.begin(),group.end());result.push_back(std::move(group));
    }
    return result;
}

// Rectangular primal-dual Hungarian; rows <= columns, integer costs.
inline std::vector<int> hungarian(const std::vector<std::vector<int64_t>>& cost) {
    const int n=static_cast<int>(cost.size());
    if(!n) return {};
    const int m=static_cast<int>(cost[0].size());
    if(m<n) throw std::invalid_argument("Hungarian requires rows <= columns");
    for(const auto& row:cost) if(static_cast<int>(row.size())!=m) throw std::invalid_argument("ragged cost matrix");
    std::vector<int64_t> u(n+1),v(m+1);
    std::vector<int> p(m+1),way(m+1);
    for(int i=1;i<=n;++i) {
        p[0]=i;int j0=0;
        std::vector<int64_t> slack(m+1,std::numeric_limits<int64_t>::max()/4);
        std::vector<char> used(m+1);
        do {
            used[j0]=true;int i0=p[j0],j1=0;
            int64_t delta=std::numeric_limits<int64_t>::max()/4;
            for(int j=1;j<=m;++j) if(!used[j]) {
                auto current=cost[i0-1][j-1]-u[i0]-v[j];
                if(current<slack[j]) {slack[j]=current;way[j]=j0;}
                if(slack[j]<delta) {delta=slack[j];j1=j;}
            }
            for(int j=0;j<=m;++j) {
                if(used[j]) {u[p[j]]+=delta;v[j]-=delta;}
                else slack[j]-=delta;
            }
            j0=j1;
        } while(p[j0]);
        do {int j1=way[j0];p[j0]=p[j1];j0=j1;} while(j0);
    }
    std::vector<int> assignment(n,-1);
    for(int j=1;j<=m;++j) if(p[j]) assignment[p[j]-1]=j-1;
    return assignment;
}

struct Constraint { int agent,time,from,to; }; // from=-1 means vertex at time
struct Reservations {
    std::set<std::pair<int,int>> vertices; // time,cell
    std::set<std::tuple<int,int,int>> edges; // time,from,to
    void reserve(const std::vector<int>& path,int horizon) {
        if(path.empty()) return;
        for(int t=0;t<=horizon;++t) {
            int p=path[std::min(t,static_cast<int>(path.size())-1)];vertices.insert({t,p});
            if(t) edges.insert({t,path[std::min(t-1,static_cast<int>(path.size())-1)],p});
        }
    }
};
inline SearchResult space_time(const Grid& g,int start,int goal,int horizon,
    const Reservations& reservations={},const std::vector<Constraint>& constraints={},
    int agent=-1,int budget=100000,bool allow_prefix=false) {
    SearchResult out;
    if(!g.free(start)||!g.free(goal)||horizon<0) return out;
    // Exact known-graph distances keep rolling prefixes moving around long detours.
    const auto remaining=distances(g,goal);
    if(remaining[start]==INF)return out;
    auto forbidden=[&](int t,int from,int to) {
        if(reservations.vertices.count({t,to})||reservations.edges.count({t,to,from})) return true;
        for(const auto& c:constraints) if(c.agent==agent && c.time==t && c.to==to && (c.from<0||c.from==from)) return true;
        return false;
    };
    if(forbidden(0,start,start)) return out;
    auto index=[&](int t,int p){return static_cast<int64_t>(t)*g.size()+p;};
    std::map<int64_t,int64_t> parent;
    MinHeap<std::tuple<int,int,int>> open;open.push({remaining[start],0,start});
    parent[index(0,start)]=-1;
    int endtime=-1,endcell=-1;
    while(!open.empty()) {
        auto [f,t,u]=open.pop();
        if(out.expanded>=budget) {out.exhausted=true;return out;}
        ++out.expanded;
        bool can_stay=u==goal;
        if(can_stay) for(int future=t+1;future<=horizon;++future)
            if(forbidden(future,goal,goal)) {can_stay=false;break;}
        if(can_stay) {endtime=t;endcell=u;break;}
        if(t==horizon) {
            if(allow_prefix) {endtime=t;endcell=u;break;}
            continue;
        }
        auto ns=g.neighbors(u);ns.push_back(u);
        for(int v:ns) if(g.free(v)&&!forbidden(t+1,u,v)) {
            auto key=index(t+1,v);
            if(!parent.count(key)) {parent[key]=index(t,u);open.push({t+1+remaining[v],t+1,v});}
        }
    }
    if(endtime<0) return out;
    for(auto key=index(endtime,endcell);key!=-1;key=parent.at(key)) out.path.push_back(static_cast<int>(key%g.size()));
    std::reverse(out.path.begin(),out.path.end());return out;
}

struct Conflict { int a=-1,b=-1,time=0,a0=0,a1=0,b0=0,b1=0;bool edge=false; };
inline Conflict first_conflict(const std::vector<std::vector<int>>& paths) {
    std::size_t length=0;for(const auto& p:paths) length=std::max(length,p.size());
    auto at=[&](int a,int t){return paths[a][std::min(t,static_cast<int>(paths[a].size())-1)];};
    for(int t=0;t<static_cast<int>(length);++t) for(int a=0;a<static_cast<int>(paths.size());++a)
        for(int b=a+1;b<static_cast<int>(paths.size());++b) {
            int a1=at(a,t),b1=at(b,t),a0=at(a,std::max(0,t-1)),b0=at(b,std::max(0,t-1));
            if(a1==b1) return {a,b,t,a0,a1,b0,b1,false};
            if(t&&a0==b1&&b0==a1) return {a,b,t,a0,a1,b0,b1,true};
        }
    return {};
}
struct CBSResult {std::vector<std::vector<int>> paths;std::vector<Constraint> constraintTrace;int high=0,low=0,constraintsConsidered=0;bool exhausted=false;};
inline CBSResult cbs(const Grid& g,const std::vector<int>& starts,const std::vector<int>& goals,
    int horizon=64,int high_budget=5000,int low_budget=100000,const std::vector<Grid>* agent_graphs=nullptr) {
    CBSResult result;
    if(starts.size()!=goals.size()||starts.empty()) return result;
    if(std::set<int>(goals.begin(),goals.end()).size()!=goals.size()) return result;
    struct Node {int cost=0,id=0;std::vector<Constraint> constraints;std::vector<std::vector<int>> paths;};
    struct Before {bool operator()(const Node& a,const Node& b)const{return std::tie(a.cost,a.id)<std::tie(b.cost,b.id);}};
    MinHeap<Node,Before> open;Node root;
    for(int a=0;a<static_cast<int>(starts.size());++a) {
        const auto& graph=agent_graphs?agent_graphs->at(a):g;
        auto p=space_time(graph,starts[a],goals[a],horizon,{}, {},a,low_budget);result.low+=p.expanded;
        if(p.path.empty()) {result.exhausted=p.exhausted;return result;}
        root.cost+=static_cast<int>(p.path.size())-1;root.paths.push_back(std::move(p.path));
    }
    open.push(root);int next=1;
    while(!open.empty() && result.high<high_budget) {
        Node n=open.pop();++result.high;auto c=first_conflict(n.paths);
        if(c.a<0) {result.paths=std::move(n.paths);return result;}
        for(int agent:{c.a,c.b}) {
            Node child=n;child.id=next++;
            child.constraints.push_back({agent,c.time,c.edge?(agent==c.a?c.a0:c.b0):-1,agent==c.a?c.a1:c.b1});
            ++result.constraintsConsidered;if(result.constraintTrace.size()<512)result.constraintTrace.push_back(child.constraints.back());
            const auto& graph=agent_graphs?agent_graphs->at(agent):g;
            auto p=space_time(graph,starts[agent],goals[agent],horizon,{},child.constraints,agent,low_budget);
            result.low+=p.expanded;
            if(p.exhausted) {result.exhausted=true;return result;}
            if(p.path.empty()) continue;
            child.cost-=static_cast<int>(child.paths[agent].size())-1;
            child.cost+=static_cast<int>(p.path.size())-1;child.paths[agent]=std::move(p.path);open.push(std::move(child));
        }
    }
    result.exhausted=!open.empty();return result;
}

// Safety arbiter, deliberately separate from all allocation decisions.
inline std::vector<int> arbitrate(const Grid& truth,const std::vector<int>& positions,
    std::vector<int> intents,const std::vector<bool>& active,int priority=0) {
    int n=static_cast<int>(positions.size());
    for(int i=0;i<n;++i) if(!active[i]||!truth.free(intents[i])||truth.manhattan(positions[i],intents[i])>1) intents[i]=positions[i];
    for(int offset=0;offset<n;++offset) {
        int a=(priority+offset)%n;
        for(int other=offset+1;other<n;++other) {
            int b=(priority+other)%n;
            if(intents[a]==intents[b]) {
                if(intents[b]==positions[b]) intents[a]=positions[a];else intents[b]=positions[b];
            }
            if(intents[a]==positions[b]&&intents[b]==positions[a]) {intents[a]=positions[a];intents[b]=positions[b];}
        }
    }
    bool changed=true;
    while(changed) {changed=false;
        for(int a=0;a<n;++a) for(int b=0;b<n;++b) if(a!=b&&intents[a]!=positions[a]&&intents[a]==positions[b]&&intents[b]==positions[b]) {
            intents[a]=positions[a];changed=true;
        }
    }
    return intents;
}
}
