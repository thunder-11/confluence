#pragma once
#include "allocation.hpp"
#include "interfaces.hpp"
#include "json.hpp"
#include <chrono>
#include <deque>
#include <iomanip>
#include <sstream>
#include <string>

namespace confluence {
using json=nlohmann::json;
inline uint64_t mix(uint64_t x) {x+=0x9e3779b97f4a7c15ULL;x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;x=(x^(x>>27))*0x94d049bb133111ebULL;return x^(x>>31);}
inline std::string hash_json(const json& j) {uint64_t h=14695981039346656037ULL;for(unsigned char c:j.dump()){h^=c;h*=1099511628211ULL;}std::ostringstream s;s<<std::hex<<std::setw(16)<<std::setfill('0')<<h;return s.str();}
inline json defaults() {
    return {{"schemaVersion",1},{"seed","42"},{"width",64},{"height",64},{"agentCount",4},{"obstacleDensity",.32},{"targetCount",20},{"sensorRadius",2},{"allowDisconnected",false},{"starts",json::array()},{"chargingStations",json::array()},
        {"communication",{{"rangeCells",256},{"delayMinTicks",1},{"delayMaxTicks",1},{"dropProbability",0.0},{"heartbeatPeriodTicks",5},{"heartbeatTimeoutTicks",15}}},
        {"energy",{{"capacity",100000},{"movementCost",1000},{"sensingCost",100},{"waitingCost",20},{"transmitCostPerByte",1},{"receiveCostPerByte",1},{"chargingRate",5000},{"reserve",10000}}},
        {"maxTicks",10000},{"faultSchedule",json::array()},{"strategy","adaptive"},{"adaptiveCoordinatorEnabled",true},{"planner","reservations"},{"pathfinder","astar"},{"reservationHorizon",16}};
}
struct PeerObservation {int position=0,tick=-1,source=-1;std::string status="ACTIVE";};
struct Knowledge {
    Grid grid;
    std::vector<int> times,sources,targets,priority;
    int revision=0;
    std::map<int,PeerObservation> contacts;
    Knowledge()=default;
    Knowledge(int w,int h):grid(w,h),times(w*h,-1),sources(w*h,-1),targets(w*h),priority(w*h){}
    bool merge(int p,int value,int tick,int source,int target=0,int zone=0) {
        if(p<0||p>=grid.size()||value<0||value>1)return false;
        if(std::pair(tick,source)<=std::pair(times[p],sources[p]))return false;
        bool changed=grid.cells[p]!=value||targets[p]!=target||priority[p]!=zone;
        grid.cells[p]=value;times[p]=tick;sources[p]=source;targets[p]=target;priority[p]=zone;
        if(changed)++revision;
        return changed;
    }
    bool merge_peer(int id,int position,const std::string& status,int tick,int source){
        auto found=contacts.find(id);
        if(found!=contacts.end()&&std::pair(tick,source)<=std::pair(found->second.tick,found->second.source))return false;
        bool changed=found==contacts.end()||found->second.position!=position||found->second.status!=status;
        bool affectsGraph=(status!="ACTIVE")||(found!=contacts.end()&&found->second.status!="ACTIVE");
        contacts[id]={position,tick,source,status};if(changed&&affectsGraph)++revision;return changed;
    }
    Grid planning_grid()const {
        Grid result=grid;
        for(const auto& [id,p]:contacts)if(p.status!="ACTIVE"&&p.position>=0&&p.position<result.size())result.cells[p.position]=1;
        return result;
    }
};
struct Agent {
    int id=0,pos=0,task=-1,assignedAt=-100,lease=0,distance=0,blocked=0,success=0,resolved=0;
    int lastBase=-1000,baseOfferEpoch=-1,lastProgress=0,queueTick=-1;
    int64_t energy=0,spent=0,energyCharged=0;
    int pendingMovementTick=-1;
    std::map<std::string,int64_t> energyLedger;
    std::string status="ACTIVE",activity="IDLE";
    Knowledge knowledge;
    std::vector<int> path;
    std::map<int,int> peerSeen;
    std::map<int,int> peerTasks;
    std::set<int> urgentTasks;
    std::map<int,std::tuple<int,int,int>> claims; // task -> bidder,score,expiry
    std::set<int> committedClaims;
    std::map<int,std::vector<std::pair<int,int>>> sentVersions;
    std::map<int,int> pendingBids;
    std::map<int,int> suspected;
    std::vector<json> decisions;
    std::deque<json> rejections;
    json chosen=json::object();
    json alternatives=json::array();
    int alternativesTick=-1;
    int bidsAt=-1,attempted=0,delivered=0;
    std::map<int,std::pair<int,bool>> communicationWindow;
    std::deque<int> workloadWindow;
    std::vector<std::pair<std::string,std::vector<int>>> regions;
    int regionCounter=0,regionsRevision=-1;
    double reportedCommunication=-1,reportedWorkload=-1;
    bool parking=false;
    int homeStation=-1;
    bool jointAwait=false;
    int jointEpoch=-1,jointStart=-1,jointDeadline=-1,jointGoal=-1;
    std::vector<int> jointPath;
    std::set<int> visitedCells,sensedCells;
    std::deque<int> recentPositions;
    int operationalTicks=0,busyTicks=0;
    int optionalBudgetTick=-1;
    int64_t optionalSpent=0;
    int coordinatorBlockedUntil=-1,pendingOffer=-1,lastCoordinatorResponse=0;
    std::string parkingReason;
};
struct Message {
    int due=0,sender=0,receiver=0,seq=0,bytes=0;
    std::string kind;
    json payload;
};
struct MessageBefore {bool operator()(const Message& a,const Message& b)const{return std::tie(a.due,a.sender,a.seq)<std::tie(b.due,b.sender,b.seq);}};
struct Report {int tick=-1000,pos=0,task=-1,lease=0,success=0,resolved=0,distance=0,attempted=0,delivered=0;int64_t energy=0;std::string status="ACTIVE",activity="IDLE";double communication=.5,workload=0;bool ready=true;};

class Simulation {
    Grid truth;
    std::vector<int> targets,zones,stations,initialReachable;
    std::vector<bool> observed,visited,mapped,observable;
    std::vector<int> discovery;
    std::vector<Agent> agents;
    Knowledge base;
    std::map<int,Report> reports;
    MinHeap<Message,MessageBefore> messages;
    std::map<int,std::tuple<int,int,int>> baseOffers; // agent -> task,epoch,expiry
    std::map<int,std::tuple<int,int,int>> baseClaims; // task -> owner,expiry,acknowledged tick
    std::string jointPhase="IDLE";
    int jointEpoch=0,jointDeadline=0,jointRetry=0;
    std::vector<int> jointMembers;
    std::map<int,json> jointReady;
    std::set<int> jointAcks,jointDone;
    std::vector<std::vector<int>> jointSolution;
    std::map<int,std::map<int,int>> stationRequests;
    std::map<int,int> failures;
    std::map<int,int> failedTasks,detectionDurations,assignmentDurations,progressDurations,recoveryOwners;
    json failureHistory=json::array();
    std::set<int> detectedFailures,reassignedFailures,recoveredFailures;
    mutable std::map<const Knowledge*,std::pair<int,std::vector<int>>> returnCache;
    struct FrontierCache {int revision=-1;std::vector<std::vector<int>> groups;std::vector<int> labels;};
    mutable std::map<const Knowledge*,FrontierCache> frontierCache;
    std::vector<json> faults;
    json config,initialScenario;
    uint64_t seed=42;
    int tick=0,eventSeq=0,messageSeq=0,stagnant=0,finishAt=-1;
    std::string status="READY";
    json events=json::array();
    int64_t totalDistance=0,repeated=0,prevented=0,bytesAttempted=0,bytesDelivered=0,replans=0,expanded=0,cbsExpanded=0,fallbacks=0,churn=0,charged=0;
    int64_t nonproductiveMoves=0,productiveMoves=0,unclassifiedMoves=0,attemptedMessages=0,deliveredMessages=0;
    std::map<std::string,int64_t> attemptedByType,deliveredByType,attemptedBytesByType,deliveredBytesByType;
    std::set<std::pair<int,int>> duplicatePairs;
    int64_t duplicateClaimTicks=0,duplicateClaimEpisodes=0;
    double lastTickMs=0,sensingMs=0,communicationMs=0,allocationMs=0,planningMs=0;

    void event(const std::string& type,json data=json::object(),int id=-1) {
        json e={{"sequence",++eventSeq},{"tick",tick},{"type",type},{"agentId",id<0?json(nullptr):json(id)},{"payload",std::move(data)}};
        events.push_back(std::move(e));
    }
    int at(const json& p) const {int x=p.at("x").get<int>(),y=p.at("y").get<int>();if(x<0||y<0||x>=truth.width||y>=truth.height)throw std::invalid_argument("point outside map");return y*truth.width+x;}
    json point(int p)const {return {{"x",p%truth.width},{"y",p/truth.width}};}
    int e(const char* name)const{return config["energy"][name].get<int>();}
    int64_t queue_buffer()const {
        int netRate=e("chargingRate")-e("chargingRate")/4;
        int64_t serviceTicks=(static_cast<int64_t>(e("capacity"))+netRate-1)/netRate;
        return serviceTicks*std::max(0,static_cast<int>(agents.size())-1)*(static_cast<int64_t>(e("waitingCost"))+e("sensingCost"));
    }
    json recovery_record(int id)const {
        return {{"episodeId",std::to_string(id)+":"+std::to_string(failures.at(id))},{"agentId",id},{"failureTick",failures.at(id)},{"unfinishedTask",failedTasks.at(id)},
            {"detectionTicks",detectionDurations.count(id)?json(detectionDurations.at(id)):json(nullptr)},
            {"assignmentTicks",assignmentDurations.count(id)?json(assignmentDurations.at(id)):json(nullptr)},
            {"progressTicks",progressDurations.count(id)?json(progressDurations.at(id)):json(nullptr)},
            {"measurementStatus",failedTasks.at(id)<0?"NOT_APPLICABLE":progressDurations.count(id)?"MEASURED":"CENSORED"}};
    }
    bool is_frontier(const Knowledge& k,int p)const {
        if(!k.grid.free(p))return false;
        for(int n:k.grid.neighbors(p))if(k.grid.cells[n]<0)return true;
        return false;
    }
    bool available(const Agent& a)const {
        return a.status=="ACTIVE"&&!a.parking&&!a.jointAwait&&a.jointPath.empty()&&a.activity!="CHARGING"&&a.activity!="RETURNING"&&a.activity!="QUEUED";
    }
    bool base_fresh(const Agent& a)const {return !(config["strategy"]=="adaptive"&&!config.value("adaptiveCoordinatorEnabled",true))&&tick>=a.coordinatorBlockedUntil&&tick-a.lastBase<=config["communication"]["heartbeatTimeoutTicks"].get<int>();}
    void receive_claim(Agent& a,int cell,int owner,int score,int expiry,bool confirmed){
        if(expiry<=tick)return;auto old=a.claims.find(cell);bool replace=old==a.claims.end()||std::get<2>(old->second)<=tick;
        if(!replace){
            bool oldConfirmed=a.committedClaims.count(cell);
            if(std::get<0>(old->second)==owner)replace=expiry>=std::get<2>(old->second);
            else if(confirmed!=oldConfirmed)replace=confirmed;
            else replace=score>std::get<1>(old->second)||(score==std::get<1>(old->second)&&owner<std::get<0>(old->second));
        }
        if(replace){a.claims[cell]={owner,score,expiry};if(confirmed)a.committedClaims.insert(cell);else a.committedClaims.erase(cell);}
    }
    std::tuple<int,int,int> claim_winner(const Agent& a,int cell)const {
        std::tuple<int,int,int> result={-1,-INF,0};bool confirmed=false;
        auto same=[&](int p){if(p==cell)return true;for(const auto& [id,cells]:a.regions)if(std::binary_search(cells.begin(),cells.end(),p)&&std::binary_search(cells.begin(),cells.end(),cell))return true;return false;};
        for(const auto& [p,claim]:a.claims)if(std::get<2>(claim)>tick&&same(p)){
            bool c=a.committedClaims.count(p);int owner=std::get<0>(claim),score=std::get<1>(claim);
            if((c&&!confirmed)||(c==confirmed&&(score>std::get<1>(result)||(score==std::get<1>(result)&&(std::get<0>(result)<0||owner<std::get<0>(result)))))){result=claim;confirmed=c;}
        }return result;
    }
    void release_task(Agent& a,const std::string& reason) {
        int cell=a.task,expiry=a.lease;
        if(cell>=0){auto claim=a.claims.find(cell);if(claim!=a.claims.end()&&std::get<0>(claim->second)==a.id){a.claims.erase(claim);a.committedClaims.erase(cell);}
            if(config["strategy"]!="independent")for(int peer=0;peer<static_cast<int>(agents.size());++peer)if(peer!=a.id)send(a.id,peer,"release",{{"task",cell},{"expiry",expiry}});
            event("task_released",{{"task",cell},{"reason",reason}},a.id);
        }
        a.task=-1;a.lease=0;a.pendingBids.clear();if(a.activity=="EXPLORING")a.activity="IDLE";
    }
    json report_payload(Agent& a,int receiver){
        int attempted=0,delivered=0,working=0;for(const auto& [id,p]:a.communicationWindow)if(tick-p.first<50){++attempted;if(p.second)++delivered;}
        for(int work:a.workloadWindow)working+=work;
        json peers=json::array();if(a.activity!="CHARGING")for(const auto& [id,p]:a.knowledge.contacts)peers.push_back({id,p.position,p.status,p.tick,p.source});
        return {{"available",available(a)},{"peerObservations",peers},{"tick",tick},{"pos",a.pos},{"energy",a.energy},{"status",a.status},{"activity",a.activity},{"task",a.task},{"lease",a.lease},{"score",a.chosen.value("score",0)},{"records",a.activity=="CHARGING"?json::array():records(a,receiver)},{"success",a.success},{"resolved",a.resolved},{"distance",a.distance},{"attempted",attempted},{"delivered",delivered},{"communicationQuality",attempted?static_cast<double>(delivered)/attempted:.5},{"workload",a.workloadWindow.empty()?0.0:static_cast<double>(working)/a.workloadWindow.size()}};
    }
    void update_regions(Agent& a) {
        if(a.regionsRevision==a.knowledge.revision)return;
        auto groups=frontier_groups(a.knowledge);std::vector<std::pair<std::string,std::vector<int>>> next;std::set<std::string> used;
        for(auto& group:groups){int overlap=0;std::string id;
            for(const auto& [oldId,old]:a.regions)if(!used.count(oldId)){
                int count=0;for(int p:group)if(std::binary_search(old.begin(),old.end(),p))++count;
                if(count>overlap||(count==overlap&&count>0&&(id.empty()||oldId<id))){overlap=count;id=oldId;}
            }
            if(id.empty())id="a"+std::to_string(a.id)+"-f"+std::to_string(++a.regionCounter);
            used.insert(id);next.push_back({id,std::move(group)});
        }
        a.regions=std::move(next);a.regionsRevision=a.knowledge.revision;
    }
    bool related(const Knowledge& k,int cell,int old)const {
        if(cell==old)return true;
        frontier_groups(k);const auto& labels=frontierCache.at(&k).labels;
        return cell>=0&&old>=0&&cell<k.grid.size()&&old<k.grid.size()&&labels[cell]>=0&&labels[cell]==labels[old];
    }
    const std::vector<std::vector<int>>& frontier_groups(const Knowledge& k)const {
        auto& cached=frontierCache[&k];
        if(cached.revision!=k.revision){cached.revision=k.revision;cached.groups=frontiers(k.grid);cached.labels.assign(k.grid.size(),-1);for(int i=0;i<static_cast<int>(cached.groups.size());++i)for(int cell:cached.groups[i])cached.labels[cell]=i;}
        return cached.groups;
    }
    const std::vector<int>& home_distances(const Knowledge& k)const {
        auto& entry=returnCache[&k];
        if(entry.second.empty()||entry.first!=k.revision){
            auto graph=k.planning_grid();entry.first=k.revision;entry.second.assign(graph.size(),INF);std::queue<int> q;
            for(int p:stations)if(graph.free(p)){entry.second[p]=0;q.push(p);}
            while(!q.empty()){int p=q.front();q.pop();for(int v:graph.neighbors(p))if(graph.free(v)&&entry.second[v]==INF){entry.second[v]=entry.second[p]+1;q.push(v);}}
        }return entry.second;
    }
    bool station(int p)const{return std::find(stations.begin(),stations.end(),p)!=stations.end();}
    bool active(int i)const{return agents[i].status=="ACTIVE";}
    bool spend(Agent& a,int64_t amount,const std::string& action="other") {
        if(amount<0||a.energy<amount)return false;
        a.energy-=amount;a.spent+=amount;a.energyLedger[action]+=amount;return true;
    }
    bool optional_spend(Agent& a,int64_t amount,const std::string& action) {
        if(a.activity=="CHARGING"){
            if(a.optionalBudgetTick!=tick){a.optionalBudgetTick=tick;a.optionalSpent=0;}
            if(a.optionalSpent+amount>e("chargingRate")/4)return false;
            if(!spend(a,amount,action))return false;a.optionalSpent+=amount;return true;
        }
        const auto& home=home_distances(a.knowledge);int d=home[a.pos];
        int64_t floor=d==INF?e("reserve"):static_cast<int64_t>(d)*(e("movementCost")+e("sensingCost"))+e("reserve")+e("sensingCost")+queue_buffer();
        if(a.energy-amount<floor)return false;
        return spend(a,amount,action);
    }
    void decide(Agent& a,const std::string& reason,json data=json::object()) {
        data["tick"]=tick;data["reason"]=reason;a.decisions.push_back(data);
        if(a.decisions.size()>24)a.decisions.erase(a.decisions.begin());
        event("decision",data,a.id);
    }
    void sense(Agent& a,bool charge=true) {
        if(a.status!="ACTIVE"||a.activity=="CHARGING")return;
        // Decide service eligibility from the boundary state before charging replaces sensing.
        if(charge&&station(a.pos)&&a.energy<e("capacity")){
            if(a.activity=="RETURNING"||a.activity=="QUEUED")return;
            if(a.activity=="IDLE"&&a.task<0){
                bool waiting=false;auto requests=stationRequests.find(a.pos);
                if(requests!=stationRequests.end())for(const auto& [id,when]:requests->second)if(id!=a.id&&agents[id].status=="ACTIVE")waiting=true;
                if(!waiting){bool feasible=false;for(const auto& c:candidates(a))if(c.feasible)feasible=true;if(!feasible)return;}
            }
        }
        if(charge&&!spend(a,e("sensingCost"),"sensing"))return;
        int newKnowledge=0;
        std::queue<std::pair<int,int>> q;std::set<int> seen;q.push({a.pos,0});seen.insert(a.pos);
        while(!q.empty()) {
            auto [p,d]=q.front();q.pop();
            a.knowledge.merge(p,truth.cells[p],tick,a.id,targets[p],zones[p]);
            a.sensedCells.insert(p);
            if(!mapped[p])++newKnowledge;mapped[p]=true;
            for(const auto& peer:agents)if(peer.pos==p)a.knowledge.merge_peer(peer.id,p,peer.status,tick,a.id);
            if(!observed[p]&&truth.free(p)) {observed[p]=true;a.lastProgress=tick;
                for(const auto& [failed,when]:failures)if(reassignedFailures.count(failed)&&!recoveredFailures.count(failed)&&recoveryOwners[failed]==a.id&&a.task>=0&&related(a.knowledge,a.task,failedTasks[failed])){
                    recoveredFailures.insert(failed);progressDurations[failed]=tick-when;event("progress_recovery",{{"failedAgent",failed},{"durationTicks",tick-when}},a.id);
                }
            }
            if(targets[p]&&discovery[p]<0){discovery[p]=tick;event("target_discovered",{{"cell",p},{"targetId","target-"+std::to_string(p)}},a.id);}
            if(d>=config["sensorRadius"].get<int>()||!truth.free(p))continue;
            for(int v:truth.neighbors(p))if(!seen.count(v)){seen.insert(v);q.push({v,d+1});}
        }
        if(a.pendingMovementTick>=0){
            if(newKnowledge)++productiveMoves;else ++nonproductiveMoves;
            event("movement_productivity",{{"movementTick",a.pendingMovementTick},{"newTeamCells",newKnowledge},{"productive",newKnowledge>0}},a.id);a.pendingMovementTick=-1;
        }
    }
    bool link(int from,int to)const {
        int p=from<0?stations.front():agents[from].pos,q=to<0?stations.front():agents[to].pos;
        if((from>=0&&!active(from))||(to>=0&&!active(to)))return false;
        if(truth.manhattan(p,q)>config["communication"]["rangeCells"].get<int>())return false;
        for(const auto& f:faults)if(f.value("type","")=="partition"&&tick>=f.value("tick",0)&&tick<f.value("endTick",0)) {
            int split=f.value("split",static_cast<int>(agents.size())/2);
            if((from<split)!=(to<split))return false;
        }
        return true;
    }
    bool send(int from,int to,const std::string& kind,json payload) {
        int serial=++messageSeq;
        const int bytes=static_cast<int>(payload.dump().size())+32;
        if(from>=0&&!optional_spend(agents[from],static_cast<int64_t>(bytes)*e("transmitCostPerByte"),"transmit"))return false;
        bytesAttempted+=bytes;++attemptedMessages;++attemptedByType[kind];attemptedBytesByType[kind]+=bytes;if(from>=0){++agents[from].attempted;if(kind=="report")agents[from].communicationWindow[serial]={tick,false};}
        uint64_t key=mix(seed^mix(tick)^mix(static_cast<uint64_t>(from+2)*97+to+2));
        for(unsigned char c:kind)key=mix(key^c);
        bool drop=static_cast<double>(key%1000000)/1000000.0<config["communication"]["dropProbability"].get<double>();
        if(drop||!link(from,to)){event("message_dropped",{{"kind",kind},{"from",from},{"to",to},{"bytes",bytes}});return false;}
        if(messages.size()>=10000){event("queue_limit",{{"queue","communication"}});return false;}
        int low=config["communication"]["delayMinTicks"],high=config["communication"]["delayMaxTicks"];
        messages.push({tick+low+static_cast<int>(mix(key)%(high-low+1)),from,to,serial,bytes,kind,std::move(payload)});
        return true;
    }
    json records(Agent& a,int receiver) {
        auto& versions=a.sentVersions[receiver];
        if(versions.empty())versions.assign(truth.size(),{-1,-1});
        json out=json::array();
        std::set<int> included;
        auto append=[&](int p){auto version=std::pair(a.knowledge.times[p],a.knowledge.sources[p]);
            if(a.knowledge.grid.cells[p]>=0&&version>versions[p]&&!included.count(p)){
                out.push_back({p,a.knowledge.grid.cells[p],version.first,version.second,a.knowledge.targets[p],a.knowledge.priority[p]});included.insert(p);
            }};
        // Give recent own sensor observations precedence, then use a cyclic scan for anti-entropy.
        int radius=config["sensorRadius"];
        for(int dy=-radius;dy<=radius&&out.size()<96;++dy)for(int dx=-radius;dx<=radius&&out.size()<96;++dx)if(std::abs(dx)+std::abs(dy)<=radius){
            int x=a.pos%truth.width+dx,y=a.pos/truth.width+dy;if(x>=0&&y>=0&&x<truth.width&&y<truth.height)append(y*truth.width+x);
        }
        int start=(tick/5*127)%truth.size();
        for(int k=0;k<truth.size()&&out.size()<128;++k) {
            int p=(start+k)%truth.size();append(p);
        }
        return out;
    }
    void merge_records(Knowledge& k,const json& rec) {
        for(const auto& r:rec)k.merge(r[0],r[1],r[2],r[3],r[4],r[5]);
    }
    void merge_peers(Knowledge& k,const json& payload){
        if(payload.contains("peerObservations"))for(const auto& r:payload["peerObservations"])k.merge_peer(r[0],r[1],r[2],r[3],r[4]);
    }
    void deliver() {
        while(!messages.empty()) {
            auto m=messages.pop();if(m.due>tick){messages.push(std::move(m));break;}
            if(m.receiver>=0 && (!active(m.receiver)||!optional_spend(agents[m.receiver],static_cast<int64_t>(m.bytes)*e("receiveCostPerByte"),"receive")))continue;
            bytesDelivered+=m.bytes;++deliveredMessages;++deliveredByType[m.kind];deliveredBytesByType[m.kind]+=m.bytes;
            event("message_delivered",{{"kind",m.kind},{"from",m.sender},{"to",m.receiver},{"bytes",m.bytes}});
            auto& p=m.payload;
            if(finishAt>=0&&m.kind!="report"&&m.kind!="receipt")continue;
            if(m.kind=="joint_prepare"&&m.receiver>=0){
                auto& a=agents[m.receiver];int epoch=p["epoch"];
                if(a.status=="ACTIVE"&&epoch>=a.jointEpoch&&tick<=p["deadline"].get<int>()){
                    a.jointAwait=true;a.jointEpoch=epoch;a.jointDeadline=p["deadline"];a.jointGoal=a.task>=0&&a.activity!="CHARGING"?a.task:a.pos;
                    auto payload=report_payload(a,-1);payload["epoch"]=epoch;payload["goal"]=a.jointGoal;payload["planningMap"]=a.knowledge.planning_grid().cells;
                    send(a.id,-1,"joint_ready",payload);
                }
            }else if(m.kind=="joint_ready"&&m.receiver<0){
                if(jointPhase=="PREPARING"&&p["epoch"].get<int>()==jointEpoch){jointReady[m.sender]=p;merge_records(base,p["records"]);merge_peers(base,p);}
            } else if(m.kind=="joint_route"&&m.receiver>=0){
                auto& a=agents[m.receiver];auto path=p["path"].get<std::vector<int>>();bool valid=a.jointAwait&&a.jointEpoch==p["epoch"].get<int>()&&!path.empty()&&path.front()==a.pos&&a.jointGoal==p["goal"].get<int>();
                auto graph=a.knowledge.planning_grid();for(int cell:path)if(!graph.free(cell))valid=false;
                if(valid){a.jointPath=std::move(path);a.jointDeadline=p["deadline"];send(a.id,-1,"joint_ack",{{"epoch",a.jointEpoch}});}
                else send(a.id,-1,"joint_nack",{{"epoch",p["epoch"]},{"reason","ROUTE_REJECTED"}});
            } else if(m.kind=="joint_ack"&&m.receiver<0){
                if(jointPhase=="ROUTES"&&p["epoch"].get<int>()==jointEpoch)jointAcks.insert(m.sender);
            } else if(m.kind=="joint_nack"&&m.receiver<0){
                if(p["epoch"].get<int>()==jointEpoch&&jointPhase!="BACKOFF")abort_joint(p.value("reason","ROUTE_REJECTED"));
            } else if(m.kind=="joint_commit"&&m.receiver>=0){
                auto& a=agents[m.receiver];if(a.jointEpoch==p["epoch"].get<int>()&&!a.jointPath.empty()){a.jointStart=p["startTick"];a.jointDeadline=p["deadline"];a.jointAwait=false;}
            } else if(m.kind=="joint_done"&&m.receiver<0){
                if(p["epoch"].get<int>()==jointEpoch)jointDone.insert(m.sender);
            } else if(m.kind=="joint_abort"&&m.receiver>=0){
                auto& a=agents[m.receiver];if(a.jointEpoch==p["epoch"].get<int>()){a.jointAwait=false;a.jointPath.clear();a.jointStart=-1;}
            } else if(m.kind=="report") {
                if(m.receiver<0){merge_records(base,p["records"]);merge_peers(base,p);base.merge_peer(m.sender,p["pos"],p["status"],p["tick"],m.sender);Report r;r.tick=p["tick"];r.pos=p["pos"];r.task=p["task"];r.energy=p["energy"];r.status=p["status"];r.activity=p.value("activity","IDLE");r.lease=p["lease"];r.success=p.value("success",0);r.resolved=p.value("resolved",0);r.distance=p.value("distance",0);r.attempted=p.value("attempted",0);r.delivered=p.value("delivered",0);r.communication=p.value("communicationQuality",.5);r.workload=p.value("workload",0.0);r.ready=p.value("available",true);
                    if(!reports.count(m.sender)||r.tick>=reports[m.sender].tick){reports[m.sender]=r;
                        for(auto it=baseClaims.begin();it!=baseClaims.end();){auto& [owner,expiry,ackTick]=it->second;
                            if(owner==m.sender&&r.tick>ackTick){if(r.status!="ACTIVE"||r.task!=it->first||r.lease<=tick){it=baseClaims.erase(it);continue;}expiry=r.lease;}
                            ++it;
                        }
                    }}
                else {auto& a=agents[m.receiver];merge_records(a.knowledge,p["records"]);merge_peers(a.knowledge,p);a.knowledge.merge_peer(m.sender,p["pos"],p["status"],p["tick"],m.sender);a.peerSeen[m.sender]=tick;a.peerTasks[m.sender]=p["task"];
                    if(p["task"].get<int>()>=0&&p.value("activity","EXPLORING")=="EXPLORING"&&p["lease"].get<int>()>tick){int cell=p["task"];receive_claim(a,cell,m.sender,p.value("score",0),p["lease"].get<int>(),true);}}
                send(m.receiver,m.sender,"receipt",{{"reportSeq",m.seq},{"records",p["records"]}});
            } else if(m.kind=="receipt") {
                if(m.receiver>=0){auto& a=agents[m.receiver];++a.delivered;
                    int reportSeq=p["reportSeq"];if(a.communicationWindow.count(reportSeq))a.communicationWindow[reportSeq].second=true;
                    auto& versions=a.sentVersions[m.sender];if(versions.empty())versions.assign(truth.size(),{-1,-1});
                    for(const auto& r:p["records"]){int cell=r[0];versions[cell]=std::max(versions[cell],std::pair(r[2].get<int>(),r[3].get<int>()));}
                    if(m.sender<0)a.lastBase=tick;
                }
            } else if(m.kind=="offer"&&m.receiver>=0) {
                auto& a=agents[m.receiver];int epoch=p["epoch"];
                if(tick-epoch>3){a.coordinatorBlockedUntil=tick+10;a.lastCoordinatorResponse=tick;event("coordinator_deadline_missed",{{"epoch",epoch}},a.id);continue;}
                if(tick-epoch<=3 && epoch>=a.baseOfferEpoch&&available(a)) {
                    int cell=p["task"];auto candidate=make_candidate(a.knowledge,a.pos,a.energy,cell,0,a);
                    bool hold=config["strategy"]=="adaptive"&&a.task>=0&&a.task!=cell&&is_frontier(a.knowledge,a.task)&&(tick-a.assignedAt<5||candidate.score<make_candidate(a.knowledge,a.pos,a.energy,a.task,0,a).score+500);
                    if(candidate.feasible&&is_frontier(a.knowledge,cell)&&!hold){a.baseOfferEpoch=epoch;a.pendingOffer=epoch;send(a.id,-1,"ack",{{"epoch",epoch},{"task",cell}});a.lastBase=tick;a.lastCoordinatorResponse=tick;}
                    else {send(a.id,-1,"report",report_payload(a,-1));event("offer_rejected",{{"task",cell},{"reason",hold?"COMMITMENT_HELD":"STALE_OR_INFEASIBLE"}},a.id);}
                }
            } else if(m.kind=="ack"&&m.receiver<0) {
                auto it=baseOffers.find(m.sender);
                if(it!=baseOffers.end()&&std::get<1>(it->second)==p["epoch"].get<int>()&&tick-p["epoch"].get<int>()<=3){
                    int cell=p["task"];if(!is_frontier(base,cell)){event("assignment_rejected",{{"task",cell},{"reason","STALE_FRONTIER"}},m.sender);continue;}bool conflict=false;
                    for(const auto& [old,claim]:baseClaims)if(std::get<0>(claim)!=m.sender&&std::get<1>(claim)>tick&&related(base,old,cell))conflict=true;
                    if(conflict){event("assignment_rejected",{{"task",cell},{"reason","ACKNOWLEDGED_DOMAIN_CONFLICT"}},m.sender);continue;}
                    for(auto claim=baseClaims.begin();claim!=baseClaims.end();)if(std::get<0>(claim->second)==m.sender)claim=baseClaims.erase(claim);else ++claim;
                    baseClaims[cell]={m.sender,p["epoch"].get<int>()+18,tick};event("assignment_acknowledged",{{"task",p["task"]},{"epoch",p["epoch"]}},m.sender);
                    send(-1,m.sender,"commit",p);
                }
            } else if(m.kind=="commit"&&m.receiver>=0) {
                auto& a=agents[m.receiver];int epoch=p["epoch"];
                if(epoch==a.baseOfferEpoch&&tick-epoch<=3&&available(a)&&is_frontier(a.knowledge,p["task"])){
                    auto c=make_candidate(a.knowledge,a.pos,a.energy,p["task"],0,a);if(assign(a,c,"coordinator_commit"))a.pendingBids.clear();a.lastBase=tick;a.pendingOffer=-1;a.coordinatorBlockedUntil=-1;a.lastCoordinatorResponse=tick;
                }
            } else if(m.kind=="revoke"&&m.receiver>=0){
                auto& a=agents[m.receiver];if(a.task==p["task"].get<int>()&&a.assignedAt<=p["revocationTick"].get<int>()){
                    release_task(a,p.value("reason","COORDINATOR_REVOKED"));send(a.id,-1,"report",report_payload(a,-1));
                }
            } else if(m.kind=="yield_request"&&m.receiver>=0){
                auto& a=agents[m.receiver];if(tick-p["tick"].get<int>()<=5&&a.task<0&&available(a))stage_for_congestion(a);
            } else if(m.kind=="idle"&&m.receiver>=0){
                auto& a=agents[m.receiver];if(tick-p["epoch"].get<int>()<=3){a.lastCoordinatorResponse=tick;a.lastBase=tick;}
            } else if(m.kind=="release"&&m.receiver>=0){
                auto& a=agents[m.receiver];int cell=p["task"];auto found=a.claims.find(cell);
                if(found!=a.claims.end()&&std::get<0>(found->second)==m.sender&&std::get<2>(found->second)<=p["expiry"].get<int>()){a.claims.erase(found);a.committedClaims.erase(cell);}
            } else if((m.kind=="bid"||m.kind=="claim")&&m.receiver>=0) {
                auto& a=agents[m.receiver];int expiry=p["expiry"];
                if(expiry<=tick)continue;
                int cell=p["task"],score=p["score"];auto it=a.claims.find(cell);
                receive_claim(a,cell,m.sender,score,expiry,m.kind=="claim");
                a.peerSeen[m.sender]=tick;
                if(m.kind=="claim"&&a.task>=0&&related(a.knowledge,a.task,cell)&&std::get<0>(claim_winner(a,a.task))!=a.id){release_task(a,"claim_lost");decide(a,"claim_lost",{{"winner",m.sender}});}
            }
        }
    }
    Candidate make_candidate(const Knowledge& k,int pos,int64_t energy,int cell,int region,const Agent& a,const std::vector<int>* field=nullptr)const {
        Candidate c;c.cell=cell;c.region=region;if(!k.grid.free(cell))return c;
        auto distancesFrom=field?std::vector<int>{}:distances(k.planning_grid(),pos);
        c.distance=field?(*field)[cell]:distancesFrom[cell];if(c.distance==INF)return c;
        int home=home_distances(k)[cell];if(home==INF)return c;
        int64_t cost=static_cast<int64_t>(c.distance+home)*(e("movementCost")+e("sensingCost"))+e("reserve")+e("sensingCost")+queue_buffer();
        if(cost>energy)return c;c.energy=static_cast<int>(cost);c.feasible=true;
        int radius=config["sensorRadius"],maxFoot=1+2*radius*(radius+1),age=0,count=0,priority=0;
        for(int p:estimated_sensor_footprint(k.grid,cell,radius)){
            if(k.grid.cells[p]<0)++c.gain;else{age+=std::max(0,tick-k.times[p]);++count;priority=std::max(priority,k.priority[p]);}
        }
        int attempted=0,acknowledged=0,working=0;for(const auto& [id,observation]:a.communicationWindow)if(tick-observation.first<50){++attempted;if(observation.second)++acknowledged;}
        for(int value:a.workloadWindow)working+=value;
        c.features={std::min(1.0,static_cast<double>(c.gain)/maxFoot),priority/100.0,
            static_cast<double>(a.success+1)/(a.resolved+2),attempted?static_cast<double>(acknowledged)/attempted:(a.attempted?std::min(1.0,static_cast<double>(a.delivered)/a.attempted):.5),
            static_cast<double>(c.distance)/k.grid.size(),std::min(1.0,static_cast<double>(cost)/std::max<int64_t>(1,energy)),
            std::min(1.0,count?static_cast<double>(age)/count/50:0),a.workloadWindow.empty()?std::min(1.0,a.distance/static_cast<double>(std::max(1,tick))):static_cast<double>(working)/a.workloadWindow.size(),.125,
            a.task>=0&&a.task!=cell?1.0:0.0};
        for(int urgent:a.urgentTasks)if(related(k,cell,urgent))c.features.priority=1.0;
        if(a.reportedCommunication>=0)c.features.communication=a.reportedCommunication;
        if(a.reportedWorkload>=0)c.features.workload=a.reportedWorkload;
        c.features.bytes=std::min(1.0,(384.0+96*a.peerSeen.size())/std::max(.1,c.features.communication)/4096.0);
        std::array<double,10> values={c.features.gain,c.features.priority,c.features.reliability,c.features.communication,c.features.distance,c.features.energy,c.features.uncertainty,c.features.workload,c.features.bytes,c.features.switching};
        std::array<const char*,10> names={"gain","priority","reliability","communication","distance","energy","uncertainty","workload","communicationCost","switching"};
        std::array<int,10> weights={2500,1500,1000,1000,-1500,-1000,-500,-400,-300,-300};
        double score=0;for(int i=0;i<10;++i){int weight=weights[i];if(config.contains("adaptiveWeights"))weight=config["adaptiveWeights"].value(names[i],weight);score+=weight*values[i];}
        c.score=static_cast<int>(std::lround(score));return c;
    }
    json features(const Candidate& c)const {
        const auto& f=c.features;
        return {{"gain",f.gain},{"priority",f.priority},{"reliability",f.reliability},{"communication",f.communication},{"distance",f.distance},{"energy",f.energy},{"uncertainty",f.uncertainty},{"workload",f.workload},{"communicationCost",f.bytes},{"switching",f.switching},{"score",c.score},{"estimatedEnergy",c.energy}};
    }
    std::vector<Candidate> candidates(Agent& a,int64_t availableEnergy=-1)const {
        const auto known=a.knowledge.planning_grid();const AgentView view{a.id,a.pos,a.energy,known};
        auto d=distances(view.localMap,view.position);auto groups=frontier_groups(a.knowledge);std::vector<Candidate> out;
        for(int r=0;r<static_cast<int>(groups.size());++r){int cell=-1;
            for(int p:groups[r])if(d[p]<INF&&(cell<0||std::pair(d[p],p)<std::pair(d[cell],cell)))cell=p;
            if(cell>=0)out.push_back(make_candidate(a.knowledge,a.pos,availableEnergy>=0?availableEnergy:a.energy,cell,r,a,&d));
        }
        if(config["strategy"]!="independent"&&!a.urgentTasks.empty()){
            bool urgentFeasible=false;for(const auto& c:out)if(c.feasible)for(int p:a.urgentTasks)if(related(a.knowledge,c.cell,p))urgentFeasible=true;
            if(urgentFeasible)for(auto& c:out){bool relatedUrgency=false;for(int p:a.urgentTasks)if(related(a.knowledge,c.cell,p))relatedUrgency=true;if(!relatedUrgency)c.feasible=false;}
        }
        return out;
    }
    bool assign(Agent& a,const Candidate& c,const std::string& reason) {
        if(!c.feasible||!available(a))return false;
        if(a.task==c.cell){a.lease=tick+15;return true;}
        if(config["strategy"]=="adaptive"&&a.task>=0&&is_frontier(a.knowledge,a.task)&&a.assignedAt+5>tick)return false;
        if(config["strategy"]=="adaptive"&&a.task>=0&&is_frontier(a.knowledge,a.task)){auto old=make_candidate(a.knowledge,a.pos,a.energy,a.task,0,a);if(old.feasible&&c.score<old.score+500)return false;}
        auto options=candidates(a);std::sort(options.begin(),options.end(),[&](const Candidate& x,const Candidate& y){
            if(config["strategy"]=="adaptive"||config["strategy"]=="decentralized")return std::tuple(-x.score,x.distance,x.cell)<std::tuple(-y.score,y.distance,y.cell);
            return std::tuple(x.distance,-x.gain,x.cell)<std::tuple(y.distance,-y.gain,y.cell);
        });
        if(a.task>=0)++churn;a.task=c.cell;a.assignedAt=tick;a.lease=tick+15;a.activity="EXPLORING";a.chosen=features(c);
        a.alternatives=json::array();a.alternativesTick=tick;for(const auto& option:options)if(option.feasible&&a.alternatives.size()<8)a.alternatives.push_back({{"cell",option.cell},{"distance",option.distance},{"features",features(option)}});
        decide(a,reason,{{"task",c.cell},{"features",a.chosen},{"alternatives",a.alternatives}});
        for(const auto& [failed,when]:failures)if(detectedFailures.count(failed)&&!reassignedFailures.count(failed)&&failedTasks[failed]>=0&&related(a.knowledge,c.cell,failedTasks[failed])){
            reassignedFailures.insert(failed);assignmentDurations[failed]=tick-when;recoveryOwners[failed]=a.id;event("assignment_recovery",{{"failedAgent",failed},{"durationTicks",tick-when},{"unfinishedTask",failedTasks[failed]}},a.id);
        }
        return true;
    }
    void coordinator() {
        std::string strategy=config["strategy"];if(strategy=="independent"||strategy=="decentralized"||(strategy=="adaptive"&&!config.value("adaptiveCoordinatorEnabled",true)))return;
        for(auto it=baseClaims.begin();it!=baseClaims.end();)if(std::get<1>(it->second)<=tick)it=baseClaims.erase(it);else ++it;
        const auto& groups=frontier_groups(base);
        std::vector<std::pair<int,std::tuple<int,int,int>>> acknowledged(baseClaims.begin(),baseClaims.end());
        std::sort(acknowledged.begin(),acknowledged.end(),[](const auto& a,const auto& b){return std::tuple(std::get<2>(a.second),std::get<0>(a.second),a.first)<std::tuple(std::get<2>(b.second),std::get<0>(b.second),b.first);});
        std::set<int> occupiedComponents;
        for(const auto& [cell,claim]:acknowledged){int component=-1;for(int g=0;g<static_cast<int>(groups.size());++g)if(std::binary_search(groups[g].begin(),groups[g].end(),cell)){component=g;break;}
            if(component<0||!occupiedComponents.insert(component).second){int owner=std::get<0>(claim);baseClaims.erase(cell);std::string reason=component<0?"FRONTIER_RESOLVED":"FRONTIER_COMPONENT_MERGED";
                send(-1,owner,"revoke",{{"task",cell},{"revocationTick",tick},{"reason",reason}});event("coordinator_claim_released",{{"task",cell},{"reason",reason}},owner);
            }
        }
        if(groups.empty())return;
        std::set<int> orphanTasks;
        for(const auto& [id,r]:reports){auto contact=base.contacts.find(id);bool unavailable=contact!=base.contacts.end()&&contact->second.status!="ACTIVE";
            if(r.task>=0&&(unavailable||(tick-r.tick>15&&r.lease<=tick))&&is_frontier(base,r.task))orphanTasks.insert(r.task);
        }
        if(tick%5&&orphanTasks.empty())return;
        const auto graph=base.planning_grid();const CoordinatorView view{graph};
        std::vector<int> eligible;
        for(const auto& [id,r]:reports)if(tick-r.tick<=15&&r.status=="ACTIVE"&&r.ready&&r.activity!="CHARGING"&&r.activity!="RETURNING"&&r.activity!="QUEUED"&&(strategy=="adaptive"||r.task<0||r.lease<=tick||!is_frontier(base,r.task))){
            auto contact=base.contacts.find(id);if(contact!=base.contacts.end()&&contact->second.status!="ACTIVE")continue;
            auto offer=baseOffers.find(id);if(offer!=baseOffers.end()&&tick-std::get<1>(offer->second)<=3)continue;
            bool held=false;for(const auto& [cell,claim]:baseClaims)if(std::get<0>(claim)==id&&is_frontier(base,cell))held=true;
            if(!held||strategy=="adaptive")eligible.push_back(id);
        }
        std::vector<std::vector<Candidate>> rows;
        for(int id:eligible){const auto& r=reports[id];auto d=distances(view.deliveredMap,r.pos);std::vector<Candidate> row;
            Agent deliveredAgent;deliveredAgent.id=id;deliveredAgent.task=r.task;deliveredAgent.success=r.success;deliveredAgent.resolved=r.resolved;deliveredAgent.distance=r.distance;deliveredAgent.attempted=r.attempted;deliveredAgent.delivered=r.delivered;deliveredAgent.reportedCommunication=r.communication;deliveredAgent.reportedWorkload=r.workload;deliveredAgent.urgentTasks=orphanTasks;
            for(int j=0;j<static_cast<int>(groups.size());++j){int cell=-1;
                for(int p:groups[j])if(d[p]<INF&&(cell<0||std::pair(d[p],p)<std::pair(d[cell],cell)))cell=p;
                auto c=cell<0?Candidate{}:make_candidate(base,r.pos,r.energy,cell,j,deliveredAgent,&d);
                // Preserve live commitments within this delivered-information domain.
                for(const auto& [owner,other]:reports)if(owner!=id&&other.lease>tick&&other.task>=0&&std::binary_search(groups[j].begin(),groups[j].end(),other.task))c.feasible=false;
                for(const auto& [cell,claim]:baseClaims)if(std::get<0>(claim)!=id&&std::get<1>(claim)>tick&&std::binary_search(groups[j].begin(),groups[j].end(),cell))c.feasible=false;
                row.push_back(c);
            }
            if(!orphanTasks.empty()){bool urgentFeasible=false;for(const auto& c:row)if(c.feasible&&c.features.priority>=1)urgentFeasible=true;
                if(urgentFeasible)for(auto& c:row)if(c.features.priority<1)c.feasible=false;
            }
            rows.push_back(row);
        }
        auto assignment=allocate({rows,strategy}).assignments;
        for(int i=0;i<static_cast<int>(eligible.size());++i){int id=eligible[i];if(assignment[i]>=0){const auto& c=rows[i][assignment[i]];
            baseOffers[id]={c.cell,tick,tick+15};send(-1,id,"offer",{{"task",c.cell},{"epoch",tick},{"score",c.score}});
        }else send(-1,id,"idle",{{"epoch",tick}});}
    }
    void publish_claim(Agent& a,int cell,int bid) {
        a.claims[cell]={a.id,bid,tick+15};
        a.committedClaims.insert(cell);
        for(int peer=0;peer<static_cast<int>(agents.size());++peer)if(peer!=a.id)
            send(a.id,peer,"claim",{{"task",cell},{"score",bid},{"expiry",tick+15}});
    }
    void local_allocate(Agent& a) {
        if(!available(a))return;
        const std::string strategy=config["strategy"];
        if(a.pendingOffer>=0&&tick-a.pendingOffer>3){a.pendingOffer=-1;a.coordinatorBlockedUntil=tick+10;event("coordinator_deadline_missed",{{"reason","COMMIT_NOT_RECEIVED"}},a.id);}
        if(a.task<0&&tick-a.lastCoordinatorResponse>15&&strategy!="independent"&&strategy!="decentralized")a.coordinatorBlockedUntil=std::max(a.coordinatorBlockedUntil,tick+5);
        const bool cooperative=strategy=="decentralized"||(strategy=="adaptive"&&!base_fresh(a));
        for(auto it=a.urgentTasks.begin();it!=a.urgentTasks.end();)if(!is_frontier(a.knowledge,*it))it=a.urgentTasks.erase(it);else ++it;
        if(strategy!="independent"&&!a.urgentTasks.empty()&&a.task>=0){bool covers=false;for(int p:a.urgentTasks)if(related(a.knowledge,a.task,p))covers=true;if(!covers)release_task(a,"failure_reallocation");}
        for(auto it=a.claims.begin();it!=a.claims.end();) {
            if(std::get<2>(it->second)<=tick){event("claim_expired",{{"task",it->first}},a.id);a.committedClaims.erase(it->first);it=a.claims.erase(it);}
            else ++it;
        }
        if(a.task>=0) {
            bool frontier=is_frontier(a.knowledge,a.task);
            auto current=make_candidate(a.knowledge,a.pos,a.energy,a.task,0,a);
            if(a.pos==a.task||!frontier||!current.feasible||a.lease<=tick) {
                ++a.resolved;if(a.pos==a.task||!frontier)++a.success;
                release_task(a,!frontier?"frontier_resolved":!current.feasible?"task_infeasible":"task_completed");
                if(strategy!="independent")send(a.id,-1,"report",report_payload(a,-1));
            } else {
                auto winner=claim_winner(a,a.task);
                if(cooperative&&std::get<0>(winner)>=0&&std::get<0>(winner)!=a.id){release_task(a,"claim_conflict");}
                else {
                    if(tick%5==0){a.lease=tick+15;a.chosen=features(current);if(cooperative)publish_claim(a,a.task,strategy=="adaptive"?current.score:static_cast<int>(10000*(current.features.gain-current.features.distance)));}
                    return;
                }
            }
        }
        if(!a.pendingBids.empty()) {
            int cell=a.pendingBids.begin()->first;
            auto winner=claim_winner(a,cell);
            auto c=make_candidate(a.knowledge,a.pos,a.energy,cell,0,a);
            if(!cooperative||!is_frontier(a.knowledge,cell)||!c.feasible||std::get<0>(winner)!=a.id||tick-a.bidsAt>15) {
                if(a.claims.count(cell)&&std::get<0>(a.claims[cell])==a.id){a.claims.erase(cell);a.committedClaims.erase(cell);}
                a.pendingBids.clear();
            } else if(tick-a.bidsAt>=2) {
                int bid=a.pendingBids.begin()->second;
                if(assign(a,c,"auction_won"))publish_claim(a,cell,bid);
                a.pendingBids.clear();return;
            } else return;
        }
        if(strategy!="independent"&&!cooperative&&base_fresh(a))return;
        auto cs=candidates(a);
        auto bid_value=[&](const Candidate& c){return strategy=="adaptive"?c.score:static_cast<int>(10000*(c.features.gain-c.features.distance));};
        std::sort(cs.begin(),cs.end(),[&](const Candidate& x,const Candidate& y){
            if(cooperative)return std::tuple(-bid_value(x),x.distance,x.cell)<std::tuple(-bid_value(y),y.distance,y.cell);
            return std::tuple(x.distance,-x.gain,x.cell)<std::tuple(y.distance,-y.gain,y.cell);
        });
        for(const auto& c:cs)if(c.feasible) {
            if(strategy=="adaptive"&&c.score<0)continue;
            if(!cooperative){assign(a,c,strategy=="independent"?"local_selection":"coordinator_unavailable");return;}
            auto winner=claim_winner(a,c.cell);
            if(std::get<0>(winner)>=0&&std::get<0>(winner)!=a.id)continue;
            int bid=bid_value(c);a.pendingBids[c.cell]=bid;a.bidsAt=tick;a.claims[c.cell]={a.id,bid,tick+15};a.committedClaims.erase(c.cell);
            event("bid",{{"task",c.cell},{"score",bid}},a.id);
            for(int peer=0;peer<static_cast<int>(agents.size());++peer)if(peer!=a.id)send(a.id,peer,"bid",{{"task",c.cell},{"score",bid},{"expiry",tick+15}});
            return;
        }
    }
    void energy_mode(Agent& a) {
        if(a.status!="ACTIVE"&&!(a.status=="DEPLETED"&&station(a.pos)))return;
        if(station(a.pos)&&a.energy<e("capacity")&&(a.activity=="RETURNING"||a.activity=="QUEUED"||a.activity=="CHARGING"||a.status=="DEPLETED")){
            if(a.activity!="CHARGING")event("charge_started",{{"station",a.pos},{"energy",a.energy}},a.id);
            a.activity="CHARGING";a.task=-1;return;
        }
        if(a.activity=="CHARGING") {if(a.energy>=e("capacity")){for(auto& [s,q]:stationRequests)q.erase(a.id);a.activity="IDLE";a.status="ACTIVE";a.homeStation=-1;event("charge_complete",{},a.id);}else return;}
        bool anotherRequest=false;
        if(station(a.pos))for(const auto& [id,when]:stationRequests[a.pos])if(id!=a.id&&agents[id].status=="ACTIVE")anotherRequest=true;
        if(station(a.pos)&&a.task<0&&anotherRequest){
            for(int cell:a.knowledge.grid.neighbors(a.pos))if(a.knowledge.grid.free(cell)){
                bool occupied=false;for(const auto& peer:agents)if(peer.pos==cell)occupied=true;
                if(!occupied){a.parking=true;a.parkingReason="CHARGING_STATION";a.task=cell;a.activity="WAITING";decide(a,"vacate_charging_station",{{"destination",cell}});return;}
            }
        }
        if(a.parking)return;
        if(station(a.pos)&&a.activity=="IDLE"&&a.task<0&&a.energy<e("capacity")&&!anotherRequest){
            bool feasible=false;for(const auto& c:candidates(a))if(c.feasible)feasible=true;
            if(!feasible){a.activity="CHARGING";event("charge_started",{{"station",a.pos},{"energy",a.energy}},a.id);return;}
        }
        auto d=distances(a.knowledge.planning_grid(),a.pos);int home=-1;
        for(int s:stations)if(d[s]<INF&&(home<0||std::pair(d[s],s)<std::pair(d[home],home)))home=s;
        int64_t reserve=home<0?INF:static_cast<int64_t>(d[home])*(e("movementCost")+e("sensingCost"))+e("reserve")+queue_buffer()+5LL*(e("sensingCost")+e("waitingCost"));
        bool noFeasible=false;
        if(a.energy<e("capacity")/2){noFeasible=true;for(const auto& c:candidates(a))if(c.feasible){noFeasible=false;break;}}
        if(a.energy<=reserve||(noFeasible&&a.energy<e("capacity")/2)||a.activity=="RETURNING"||a.activity=="QUEUED"){
            if(home>=0){if(a.activity!="RETURNING"&&a.activity!="CHARGING"&&a.activity!="QUEUED"){if(a.task>=0)release_task(a,"energy_return");decide(a,"energy_return",{{"station",home}});}a.activity="RETURNING";a.task=home;a.homeStation=home;
                for(auto& [s,q]:stationRequests)if(s!=home)q.erase(a.id);
                if(d[home]>config["sensorRadius"].get<int>()+1)return;
                auto& queue=stationRequests[home];if(!queue.count(a.id)){queue[a.id]=tick;event("station_queue_entered",{{"station",home},{"requestTick",tick}},a.id);}
                int first=a.id;for(const auto& [id,when]:queue)if(agents[id].status=="ACTIVE"&&std::pair(when,id)<std::pair(queue[first],first))first=id;
                if(first!=a.id){a.activity="QUEUED";int staging=-1;for(int p:a.knowledge.grid.neighbors(home))if(a.knowledge.grid.free(p)&&d[p]<INF){bool claimed=false;for(const auto& peer:agents)if(peer.id!=a.id&&(peer.pos==p||(peer.activity=="QUEUED"&&peer.task==p&&std::pair(queue.count(peer.id)?queue[peer.id]:INF,peer.id)<std::pair(queue[a.id],a.id))))claimed=true;
                        if(!claimed&&(staging<0||std::pair(d[p],p)<std::pair(d[staging],staging)))staging=p;
                    }a.task=staging>=0?staging:a.pos;}
            }
            else {a.activity="STRANDED";a.task=-1;}
        }
    }
    void apply_faults() {
        // Restore previous episodes before applying new faults at the same logical tick.
        for(auto& f:faults){int restore=f.value("restorationTick",f.value("unblockTick",-1));std::string type=f.value("type","");
            if(type=="partition"&&f.value("applied",false)&&tick>=f.value("endTick",0)&&!f.value("ended",false)){f["ended"]=true;stagnant=0;event("partition_ended");}
            if(f.value("applied",false)&&restore>=0&&tick>=restore&&!f.value("restored",false)){
                if(type=="block_cell"){truth.cells[at(f)]=0;event("obstacle_unblocked",{{"cell",at(f)}});}
                else if(type=="agent_failure"||type=="agent_disable"){int id=f["agentId"];auto& a=agents[id];a.status="ACTIVE";a.activity="IDLE";a.task=-1;a.lease=0;a.path={a.pos};a.parking=false;a.jointAwait=false;a.jointPath.clear();event("agent_restored",{},id);}
                f["restored"]=true;
            }
        }
        double probability=config.value("failureProbabilityPerTick",0.0);
        if(probability>0)for(const auto& a:agents)if(a.status=="ACTIVE"){
            auto draw=mix(seed^mix(static_cast<uint64_t>(tick))^mix(static_cast<uint64_t>(a.id)+0xf001));
            if(static_cast<double>(draw%1000000)/1000000<probability)faults.push_back({{"type","agent_failure"},{"tick",tick},{"agentId",a.id},{"source","seeded_probability"}});
        }
        for(auto& f:faults) {
            const std::string type=f.value("type","");int when=f.value("tick",0);
            if(!f.value("applied",false)&&when<=tick) {
                if(type=="agent_failure"||type=="agent_disable") {
                    int id=f.value("agentId",0);if(id>=0&&id<static_cast<int>(agents.size())){
                        if(agents[id].status!="ACTIVE"){f["applied"]=true;event("fault_ignored",{{"reason","ALREADY_UNAVAILABLE"}},id);continue;}
                        if(failures.count(id))failureHistory.push_back(recovery_record(id));
                        detectedFailures.erase(id);reassignedFailures.erase(id);recoveredFailures.erase(id);detectionDurations.erase(id);assignmentDurations.erase(id);progressDurations.erase(id);recoveryOwners.erase(id);
                        agents[id].status=type=="agent_failure"?"FAILED":"DISABLED";failures[id]=tick;failedTasks[id]=agents[id].task;
                        if(agents[id].task>=0)++agents[id].resolved;
                        agents[id].path={agents[id].pos};agents[id].jointAwait=false;agents[id].jointPath.clear();agents[id].parking=false;
                        for(auto& [s,queue]:stationRequests)queue.erase(id);
                        event(type,{{"unfinishedTask",agents[id].task}},id);
                    }
                } else if(type=="block_cell") {
                    int p=at(f);bool occupied=station(p);for(const auto& a:agents)if(a.pos==p)occupied=true;
                    if(occupied){event("obstacle_postponed",{{"cell",p}});continue;}
                    truth.cells[p]=1;event("obstacle_blocked",{{"cell",p},{"requestedTick",when}});
                } else if(type=="partition")event("partition_started",{{"endTick",f.value("endTick",tick)}});
                f["applied"]=true;
            }
        }
    }
    void heartbeats() {
        int period=config["communication"]["heartbeatPeriodTicks"];
        if(tick%period)return;
        for(auto& a:agents)if(a.status=="ACTIVE"&&a.energy>0){
            send(a.id,-1,"report",report_payload(a,-1));
            for(int offset=0;offset<static_cast<int>(agents.size());++offset){int receiver=(offset+tick/period+a.id)%agents.size();if(receiver!=a.id)send(a.id,receiver,"report",report_payload(a,receiver));}
        }
    }
    void detect() {
        int timeout=config["communication"]["heartbeatTimeoutTicks"];
        for(auto& a:agents)if(a.status=="ACTIVE")for(const auto& [peer,contact]:a.knowledge.contacts)if(peer!=a.id&&contact.status!="ACTIVE"&&!a.suspected.count(peer)){
            a.suspected[peer]=tick;event("peer_unavailable_observed",{{"peer",peer},{"observedStatus",contact.status}},a.id);
            for(auto it=a.claims.begin();it!=a.claims.end();)if(std::get<0>(it->second)==peer){a.committedClaims.erase(it->first);it=a.claims.erase(it);}else ++it;
            if(a.peerTasks.count(peer)&&a.peerTasks[peer]>=0)a.urgentTasks.insert(a.peerTasks[peer]);
            if(failures.count(peer)&&!detectedFailures.count(peer)){detectedFailures.insert(peer);detectionDurations[peer]=tick-failures[peer];event("failure_detection",{{"failedAgent",peer},{"durationTicks",tick-failures[peer]},{"method","OBSERVATION"}},a.id);}
        }
        for(auto& a:agents)if(a.status=="ACTIVE")for(const auto& [peer,last]:a.peerSeen)if(tick-last>timeout&&!a.suspected.count(peer)){
            a.suspected[peer]=tick;event("peer_suspected",{{"peer",peer},{"lastSeen",last}},a.id);
            if(a.peerTasks.count(peer)&&a.peerTasks[peer]>=0)a.urgentTasks.insert(a.peerTasks[peer]);
            if(failures.count(peer)&&!detectedFailures.count(peer)){detectedFailures.insert(peer);detectionDurations[peer]=tick-failures[peer];event("failure_detection",{{"failedAgent",peer},{"durationTicks",tick-failures[peer]}},a.id);}
        }
        for(auto& a:agents)for(auto it=a.suspected.begin();it!=a.suspected.end();)if(a.peerSeen[it->first]>it->second&&(!a.knowledge.contacts.count(it->first)||(a.knowledge.contacts.at(it->first).status=="ACTIVE"&&tick-a.knowledge.contacts.at(it->first).tick<=timeout))){event("peer_reconnected",{{"peer",it->first}},a.id);it=a.suspected.erase(it);}else ++it;
    }
    void abort_joint(const std::string& reason) {
        event("planner_fallback",{{"reason",reason},{"epoch",jointEpoch},{"planner","reservations"}});
        ++fallbacks;jointPhase="BACKOFF";jointRetry=tick+10;
        for(int id:jointMembers)send(-1,id,"joint_abort",{{"epoch",jointEpoch},{"reason",reason}});
    }
    bool joint_paths(std::vector<std::vector<int>>& paths) {
        if(truth.width>32||truth.height>32||agents.size()>8){
            if(tick==1)event("planner_fallback",{{"reason","CBS_ENVELOPE"},{"planner","reservations"}});
            ++fallbacks;return false;
        }
        for(auto& a:agents)if(a.jointAwait&&tick>a.jointDeadline){a.jointAwait=false;a.jointPath.clear();}
        if((jointPhase=="PREPARING"||jointPhase=="ROUTES"||jointPhase=="EXECUTING")&&tick>jointDeadline)abort_joint("COMMUNICATION_OR_EXECUTION_TIMEOUT");
        if(jointPhase=="EXECUTING"&&jointDone.size()==jointMembers.size()){jointPhase="IDLE";jointRetry=tick;}
        if(jointPhase=="BACKOFF"&&tick>=jointRetry)jointPhase="IDLE";
        if(jointPhase=="IDLE"){
            jointMembers.clear();jointReady.clear();jointAcks.clear();jointDone.clear();jointSolution.clear();++jointEpoch;
            for(int id=0;id<static_cast<int>(agents.size());++id){auto contact=base.contacts.find(id);if(contact==base.contacts.end()||contact->second.status=="ACTIVE")jointMembers.push_back(id);}
            if(jointMembers.empty()){abort_joint("NO_AVAILABLE_MEMBERS");return false;}
            jointPhase="PREPARING";jointDeadline=tick+2*config["communication"]["delayMaxTicks"].get<int>()+5;
            for(int id:jointMembers)send(-1,id,"joint_prepare",{{"epoch",jointEpoch},{"deadline",jointDeadline}});
            event("joint_plan_requested",{{"epoch",jointEpoch},{"members",jointMembers}});
        }
        if(jointPhase=="PREPARING"&&jointReady.size()==jointMembers.size()){
            std::vector<int> starts,goals;std::vector<Grid> graphs;
            for(int id:jointMembers){const auto& r=jointReady.at(id);Grid graph(truth.width,truth.height);graph.cells=r["planningMap"].get<std::vector<int>>();graphs.push_back(std::move(graph));starts.push_back(r["pos"]);goals.push_back(r["goal"]);}
            int horizon=config["maxTicks"].get<int>()-tick;
            auto solution=cbs(graphs.front(),starts,goals,horizon,5000,100000,&graphs);
            for(const auto& constraint:solution.constraintTrace)event("cbs_constraint",{{"epoch",jointEpoch},{"agentId",jointMembers[constraint.agent]},{"timeOffset",constraint.time},{"from",constraint.from},{"to",constraint.to}});
            event("cbs_search",{{"epoch",jointEpoch},{"highExpanded",solution.high},{"lowExpanded",solution.low},{"constraintsConsidered",solution.constraintsConsidered},{"traceTruncated",solution.constraintsConsidered>static_cast<int>(solution.constraintTrace.size())}});
            expanded+=solution.low;cbsExpanded+=solution.high;++replans;
            if(solution.paths.empty()){abort_joint(solution.exhausted?"BUDGET_EXHAUSTED":"NO_SOLUTION_WITHIN_HORIZON");return false;}
            jointSolution=std::move(solution.paths);jointPhase="ROUTES";jointDeadline=tick+2*config["communication"]["delayMaxTicks"].get<int>()+5;
            for(int index=0;index<static_cast<int>(jointMembers.size());++index)send(-1,jointMembers[index],"joint_route",{{"epoch",jointEpoch},{"path",jointSolution[index]},{"goal",goals[index]},{"deadline",jointDeadline}});
            event("joint_plan_solved",{{"epoch",jointEpoch},{"highExpanded",solution.high},{"lowExpanded",solution.low}});
        }
        if(jointPhase=="ROUTES"&&jointAcks.size()==jointMembers.size()){
            int start=tick+config["communication"]["delayMaxTicks"].get<int>()+1,maxLength=0;
            for(const auto& path:jointSolution)maxLength=std::max(maxLength,static_cast<int>(path.size()));
            jointPhase="EXECUTING";jointDeadline=start+maxLength+config["communication"]["delayMaxTicks"].get<int>()+5;
            for(int id:jointMembers)send(-1,id,"joint_commit",{{"epoch",jointEpoch},{"startTick",start},{"deadline",jointDeadline}});
            event("joint_plan_committed",{{"epoch",jointEpoch},{"startTick",start}});
        }
        bool controls=false;
        for(auto& a:agents){paths[a.id]={a.pos};
            if(a.jointAwait){controls=true;continue;}
            if(a.jointPath.empty()||a.jointStart<0)continue;
            controls=true;
            if(tick<a.jointStart)continue;
            int index=tick-a.jointStart,last=static_cast<int>(a.jointPath.size())-1;
            int expected=a.jointPath[std::min(index,last)];
            bool goalChanged=a.jointGoal!=a.pos&&(a.task!=a.jointGoal||(a.activity=="EXPLORING"&&!is_frontier(a.knowledge,a.jointGoal)));
            int next=a.jointPath[std::min(index+1,last)];
            if(a.pos!=expected||goalChanged||!a.knowledge.planning_grid().free(next)){
                a.jointPath.clear();a.jointAwait=false;send(a.id,-1,"joint_nack",{{"epoch",a.jointEpoch},{"reason","LOCAL_ROUTE_INVALID"}});continue;
            }
            paths[a.id]=std::vector<int>(a.jointPath.begin()+std::min(index,last),a.jointPath.end());
        }
        return controls;
    }
    bool stage_for_congestion(Agent& a) {
        if(a.status!="ACTIVE"||a.activity=="CHARGING"||a.activity=="RETURNING"||a.activity=="QUEUED"||a.parking)return false;
        auto graph=a.knowledge.planning_grid();const auto& home=home_distances(a.knowledge);
        int best=-1;std::tuple<int,int,int> bestKey;
        for(int cell:graph.neighbors(a.pos))if(graph.free(cell)&&!station(cell)){
            bool occupied=false;for(const auto& [id,p]:a.knowledge.contacts)if(id!=a.id&&p.position==cell&&tick-p.tick<=5)occupied=true;
            if(occupied||home[cell]==INF||a.energy<e("movementCost")+e("sensingCost")+static_cast<int64_t>(home[cell])*(e("movementCost")+e("sensingCost"))+e("reserve")+queue_buffer())continue;
            int degree=0;for(int n:graph.neighbors(cell))if(graph.free(n))++degree;
            int recent=static_cast<int>(std::count(a.recentPositions.begin(),a.recentPositions.end(),cell));
            auto key=std::tuple(-degree,recent,cell);if(best<0||key<bestKey){best=cell;bestKey=key;}
        }
        if(best<0)return false;
        release_task(a,"congestion_staging");a.parking=true;a.parkingReason="CONGESTION";a.task=best;a.activity="WAITING";a.blocked=0;
        event("congestion_yield",{{"destination",best}},a.id);decide(a,"congestion_yield",{{"destination",best}});return true;
    }
    void movement() {
        std::vector<int> positions,intents,goals;std::vector<bool> enabled;
        for(const auto& a:agents){positions.push_back(a.pos);intents.push_back(a.pos);goals.push_back(a.task>=0?a.task:a.pos);enabled.push_back(a.status=="ACTIVE"&&a.activity!="CHARGING"&&a.energy>=e("movementCost"));}
        std::vector<std::vector<int>> paths(agents.size());bool cbsUsed=false;
        if(config["planner"]=="cbs")cbsUsed=joint_paths(paths);
        int horizon=config["reservationHorizon"];
        {std::vector<int> order;for(int i=0;i<static_cast<int>(agents.size());++i)order.push_back((i+tick)%agents.size());
            std::stable_sort(order.begin(),order.end(),[&](int a,int b){return std::pair(agents[a].activity!="RETURNING",-agents[a].blocked)<std::pair(agents[b].activity!="RETURNING",-agents[b].blocked);});
            std::map<int,std::vector<int>> planned;
            if(cbsUsed)for(const auto& a:agents)if(a.jointAwait||!a.jointPath.empty())planned[a.id]=paths[a.id];
            for(int id:order){auto& a=agents[id];if(planned.count(id))continue;if(!enabled[id]){planned[id]={a.pos};paths[id]={a.pos};continue;}
                Reservations r;for(int j=0;j<static_cast<int>(agents.size());++j)if(j!=id)r.reserve(planned.count(j)?planned[j]:std::vector<int>{positions[j]},horizon);
                if(a.task>=0){
                    auto graph=a.knowledge.planning_grid();auto spatial=plan(PlanningView{graph},PathRequest{a.pos,a.task,config["pathfinder"]=="astar"});expanded+=spatial.expanded;
                    if(spatial.path.empty()){a.task=-1;a.parking=false;a.parkingReason.clear();decide(a,"route_invalid");paths[id]={a.pos};}
                    else {auto route=space_time(graph,a.pos,a.task,horizon,r,{},id,100000,true);expanded+=route.expanded;paths[id]=route.path.empty()?std::vector<int>{a.pos}:route.path;}
                    ++replans;
                }else paths[id]={a.pos};planned[id]=paths[id];
            }
        }
        for(int i=0;i<static_cast<int>(agents.size());++i){agents[i].path=paths[i];if(enabled[i]&&paths[i].size()>1)intents[i]=paths[i][1];}
        auto committed=arbitrate(truth,positions,intents,enabled,tick%agents.size());
        for(int i=0;i<static_cast<int>(agents.size());++i){auto& a=agents[i];if(committed[i]!=intents[i]){++prevented;
                std::string reason="ACTION_VETO";
                if(!truth.free(intents[i]))reason="BLOCKED_CELL";
                else for(int peer=0;peer<static_cast<int>(agents.size());++peer)if(peer!=i){
                    if(intents[peer]==intents[i])reason="DESTINATION_CONFLICT";
                    if(intents[peer]==positions[i]&&intents[i]==positions[peer]){reason="EDGE_SWAP";break;}
                    if(intents[i]==positions[peer]&&committed[peer]==positions[peer])reason="OCCUPIED_CELL";
                }
                json rejection={{"tick",tick},{"from",a.pos},{"to",intents[i]},{"reason",reason}};a.rejections.push_back(rejection);if(a.rejections.size()>12)a.rejections.pop_front();event("movement_rejected",rejection,i);
            }
            bool moved=committed[i]!=a.pos;
            if(a.status=="ACTIVE"){++a.operationalTicks;if(moved||a.activity=="EXPLORING")++a.busyTicks;}
            if(moved){if(a.pendingMovementTick>=0)++unclassifiedMoves;a.pendingMovementTick=tick;spend(a,e("movementCost"),"movement");a.pos=committed[i];++a.distance;++totalDistance;if(visited[a.pos])++repeated;visited[a.pos]=true;a.visitedCells.insert(a.pos);a.recentPositions.push_back(a.pos);if(a.recentPositions.size()>100)a.recentPositions.pop_front();a.blocked=0;}
            else if(a.status=="ACTIVE"&&a.activity!="CHARGING"){spend(a,std::min<int64_t>(a.energy,e("waitingCost")),"waiting");if(a.task>=0)++a.blocked;}
            if(a.blocked>=10&&a.parking){a.parking=false;a.parkingReason.clear();release_task(a,"staging_blocked");a.blocked=0;}
            if(a.blocked>=10&&a.activity!="RETURNING"&&a.activity!="QUEUED"){
                if(a.task>=0){auto route=search(a.knowledge.planning_grid(),a.pos,a.task,true);
                    if(route.path.size()>1)for(const auto& [peer,p]:a.knowledge.contacts)if(p.position==route.path[1]&&p.status=="ACTIVE"&&tick-p.tick<=5)send(a.id,peer,"yield_request",{{"tick",tick}});
                }
                if(!stage_for_congestion(a)){release_task(a,"congestion_reallocate");decide(a,"congestion_reallocate");a.blocked=0;}
            }
            if(a.activity=="CHARGING") {int64_t gain=std::min<int64_t>(e("chargingRate"),e("capacity")-a.energy);a.energy+=gain;charged+=gain;a.energyCharged+=gain;a.status="ACTIVE";}
            if(a.energy==0&&a.status=="ACTIVE"&&!station(a.pos)){a.status="DEPLETED";event("energy_depleted",{},i);}
            if(a.task<0&&a.activity=="EXPLORING")a.activity="IDLE";
            if(a.parking&&a.pos==a.task){a.parking=false;a.parkingReason.clear();a.task=-1;a.activity="IDLE";}
            if(!a.jointPath.empty()&&a.jointStart>=0&&tick>=a.jointStart){
                int index=tick-a.jointStart+1,last=static_cast<int>(a.jointPath.size())-1;
                if(a.pos!=a.jointPath[std::min(index,last)]){a.jointPath.clear();send(a.id,-1,"joint_nack",{{"epoch",a.jointEpoch},{"reason","MOVEMENT_VETO"}});}
                else if(index>=last){a.jointPath.clear();a.jointStart=-1;send(a.id,-1,"joint_done",{{"epoch",a.jointEpoch}});}
            }
            a.workloadWindow.push_back(moved||a.activity=="EXPLORING");if(a.workloadWindow.size()>50)a.workloadWindow.pop_front();
            for(auto it=a.communicationWindow.begin();it!=a.communicationWindow.end();)if(tick-it->second.first>=50)it=a.communicationWindow.erase(it);else ++it;
        }
        if(std::set<int>(committed.begin(),committed.end()).size()!=committed.size())throw std::runtime_error("COLLISION_INVARIANT");
    }
    void evaluate_duplicate_claims() {
        std::set<std::pair<int,int>> current;
        if(config["strategy"]!="independent")for(int i=0;i<static_cast<int>(agents.size());++i)for(int j=i+1;j<static_cast<int>(agents.size());++j){
            const auto& a=agents[i];const auto& b=agents[j];
            if(a.status!="ACTIVE"||b.status!="ACTIVE"||a.activity!="EXPLORING"||b.activity!="EXPLORING"||a.task<0||b.task<0||a.lease<=tick||b.lease<=tick)continue;
            bool overlap=a.task==b.task;
            for(const auto& [id,region]:a.regions)if(std::binary_search(region.begin(),region.end(),a.task))for(const auto& [peerId,peerRegion]:b.regions)if(std::binary_search(peerRegion.begin(),peerRegion.end(),b.task)){
                auto x=region.begin(),y=peerRegion.begin();while(x!=region.end()&&y!=peerRegion.end()){if(*x==*y){overlap=true;break;}if(*x<*y)++x;else ++y;}
            }
            if(overlap){current.insert({i,j});if(!duplicatePairs.count({i,j})){++duplicateClaimEpisodes;event("duplicate_claim",{{"agents",{i,j}},{"tasks",{a.task,b.task}}});}}
        }
        duplicateClaimTicks+=current.size();duplicatePairs=std::move(current);
    }
    void generate() {
        int w=config["width"],h=config["height"];truth=Grid(w,h,1);uint64_t rng=seed;
        auto random=[&](int n){rng=mix(rng);return static_cast<int>(rng%std::max(1,n));};
        const int desired=std::max(1,static_cast<int>((w-2)*(h-2)*(1-config["obstacleDensity"].get<double>())));
        std::vector<int> centers,free;
        const int columns=(w-2+7)/8,rows=(h-2+7)/8;
        // Neighboring tiles are visited in a snake. Room and corridor work per tile is bounded.
        for(int index=0;index<rows*columns;++index){
            int by=index/columns,bx=by%2?columns-1-index%columns:index%columns;
            int left=1+bx*8,top=1+by*8,availableW=std::min(8,w-1-left),availableH=std::min(8,h-1-top);
            int rw=std::min(availableW,3+random(4)),rh=std::min(availableH,3+random(4));
            int x=left+random(availableW-rw+1),y=top+random(availableH-rh+1),center=(y+rh/2)*w+x+rw/2;
            std::set<int> carve;
            for(int yy=y;yy<y+rh;++yy)for(int xx=x;xx<x+rw;++xx)if(!truth.free(yy*w+xx))carve.insert(yy*w+xx);
            if(!centers.empty()){
                int p=centers.back();while(p%w!=center%w){if(!truth.free(p))carve.insert(p);p+=p%w<center%w?1:-1;}
                while(p/w!=center/w){if(!truth.free(p))carve.insert(p);p+=p/w<center/w?w:-w;}if(!truth.free(p))carve.insert(p);
            }
            if(static_cast<int>(free.size()+carve.size())>desired){if(!centers.empty())break;carve.clear();carve.insert(center);}
            for(int p:carve){truth.cells[p]=0;free.push_back(p);}centers.push_back(center);
        }
        int attempts=0;
        while(static_cast<int>(free.size())<desired&&attempts++<w*h*20){
            int p=free[random(free.size())];auto ns=truth.neighbors(p);int v=ns[random(ns.size())];int x=v%w,y=v/w;
            if(x>0&&y>0&&x<w-1&&y<h-1&&!truth.free(v)){truth.cells[v]=0;free.push_back(v);}
        }
        // Deterministic bounded completion when random boundary sampling becomes sparse.
        for(std::size_t index=0;index<free.size()&&static_cast<int>(free.size())<desired;++index){
            for(int v:truth.neighbors(free[index])){int x=v%w,y=v/w;
                if(x>0&&y>0&&x<w-1&&y<h-1&&!truth.free(v)){truth.cells[v]=0;free.push_back(v);if(static_cast<int>(free.size())==desired)break;}
            }
        }
        if(static_cast<int>(free.size())<config["agentCount"].get<int>()+config["targetCount"].get<int>())throw std::invalid_argument("not enough free cells for requested agents and targets; lower density or target count");
        config["starts"]=json::array();config["chargingStations"]=json::array();std::set<int> starts;
        for(int a=0;a<config["agentCount"].get<int>();++a){int p=centers[static_cast<std::size_t>(a)*centers.size()/config["agentCount"].get<int>()];while(starts.count(p))p=free[random(free.size())];starts.insert(p);json s=point(p);s["agentId"]=a;config["starts"].push_back(s);
            {json st=point(p);st["id"]="station-"+std::to_string(a);config["chargingStations"].push_back(st);}}
        targets.assign(truth.size(),0);zones.assign(truth.size(),0);
        if(config["targetCount"].get<int>()>static_cast<int>(free.size()-starts.size()))throw std::invalid_argument("not enough free non-start cells for requested targets");
        std::vector<int> targetCells;for(int p:free)if(!starts.count(p))targetCells.push_back(p);
        for(int i=static_cast<int>(targetCells.size())-1;i>0;--i)std::swap(targetCells[i],targetCells[random(i+1)]);
        for(int i=0;i<config["targetCount"].get<int>();++i)targets[targetCells[i]]=1;
        for(int i=0;i<4;++i)zones[free[random(free.size())]]=25*(i+1);
        if(config["faultSchedule"].empty()){
            std::string family=config.value("scenarioFamily","normal");
            int limit=config["maxTicks"],early=std::max(0,std::min(w*h/20,limit/4));
            if(family=="failure")config["faultSchedule"].push_back({{"type","agent_failure"},{"tick",std::min(150,early)},{"agentId",std::min(1,config["agentCount"].get<int>()-1)}});
            if(family=="communication"){
                int begin=std::min(100,early),end=std::min(limit,begin+100);
                config["faultSchedule"].push_back({{"type","partition"},{"tick",begin},{"endTick",std::max(begin+1,end)},{"split",std::max(1,config["agentCount"].get<int>()/2)}});
            }
            if(family=="dynamic"){
                int candidate=-1;
                for(int p:free)if(!starts.count(p)&&!targets[p]){
                    int degree=0;for(int n:truth.neighbors(p))if(truth.free(n))++degree;
                    if(candidate<0||degree==2){candidate=p;if(degree==2)break;}
                }
                if(candidate>=0)config["faultSchedule"].push_back({{"type","block_cell"},{"tick",std::min(120,early)},{"x",candidate%w},{"y",candidate/w},{"unblockTick",std::min(limit,std::min(120,early)+100)}});
            }
        }
    }
public:
    void validate_fault(const json& f)const {
        const auto type=f.at("type").get<std::string>();int when=f.at("tick");
        if(when<0||when>100000)throw std::invalid_argument("invalid fault tick");
        if(type=="agent_failure"||type=="agent_disable"){
            int id=f.at("agentId");if(id<0||id>=config["agentCount"].get<int>())throw std::invalid_argument("fault references missing agent");
            if(type=="agent_disable"&&!f.contains("restorationTick"))throw std::invalid_argument("disable requires restorationTick");
        }else if(type=="block_cell"){int x=f.at("x"),y=f.at("y");if(x<0||y<0||x>=config["width"].get<int>()||y>=config["height"].get<int>())throw std::invalid_argument("fault cell outside map");}
        else if(type=="partition"){if(!f.contains("endTick"))throw std::invalid_argument("partition requires endTick");if(f.contains("split")){int split=f["split"];if(split<1||split>config["agentCount"].get<int>())throw std::invalid_argument("invalid partition split");}}
        else throw std::invalid_argument("unknown fault type");
        for(const char* key:{"restorationTick","unblockTick","endTick"})if(f.contains(key)&&(f[key].get<int>()<=when||f[key].get<int>()>100000))throw std::invalid_argument("invalid fault end tick");
    }
    void initialize(json input) {
        *this=Simulation{};config=defaults();config.merge_patch(input);
        int w=config["width"],h=config["height"],n=config["agentCount"];
        if(w<16||h<16||w>256||h>256||n<1||n>32)throw std::invalid_argument("invalid dimensions or agent count");
        for(const auto& [name,value]:config["energy"].items())if(!value.is_number_integer()||value.get<int64_t>()<0||value.get<int64_t>()>2000000000LL)throw std::invalid_argument("invalid integer energy cost");
        if(e("capacity")<1||e("movementCost")<1||e("chargingRate")<1||e("reserve")>=e("capacity"))throw std::invalid_argument("invalid energy bounds");
        for(const char* name:{"movementCost","sensingCost","waitingCost"})if(e(name)>1000000)throw std::invalid_argument("action cost exceeds supported range");
        if(e("transmitCostPerByte")>100||e("receiveCostPerByte")>100||e("chargingRate")>1000000000||e("reserve")>1000000000)throw std::invalid_argument("energy parameter exceeds supported range");
        if(config["maxTicks"].get<int>()<1||config["maxTicks"].get<int>()>100000||config["sensorRadius"].get<int>()<1||config["sensorRadius"].get<int>()>8)throw std::invalid_argument("invalid time or sensing bounds");
        const auto& communication=config["communication"];
        if(communication["delayMinTicks"].get<int>()<1||communication["delayMaxTicks"].get<int>()>100||communication["delayMinTicks"].get<int>()>communication["delayMaxTicks"].get<int>()||communication["dropProbability"].get<double>()<0||communication["dropProbability"].get<double>()>1)throw std::invalid_argument("invalid communication bounds");
        int64_t net=e("chargingRate")-e("chargingRate")/4;
        int64_t queue=((static_cast<int64_t>(e("capacity"))+net-1)/net)*(n-1)*(static_cast<int64_t>(e("waitingCost"))+e("sensingCost"));
        if(queue+static_cast<int64_t>(w)*h*(static_cast<int64_t>(e("movementCost"))+e("sensingCost"))+e("reserve")>9007199254740991LL)throw std::invalid_argument("derived energy exceeds JSON safe integer range");
        const auto seedText=config["seed"].get<std::string>();if(seedText.empty()||seedText.find_first_not_of("0123456789")!=std::string::npos)throw std::invalid_argument("seed must be an unsigned decimal string");
        try{seed=std::stoull(seedText);}catch(const std::exception&){throw std::invalid_argument("seed outside uint64 range");}
        bool custom=config.contains("map");
        if(custom){
            truth=Grid(w,h);truth.cells=config["map"].get<std::vector<int>>();if(truth.cells.size()!=static_cast<std::size_t>(w*h))throw std::invalid_argument("invalid map size");
            targets=config.value("targets",std::vector<int>(w*h));zones=config.value("zones",std::vector<int>(w*h));
            if(targets.size()!=truth.cells.size()||zones.size()!=truth.cells.size())throw std::invalid_argument("invalid target/zone size");
            for(int p=0;p<w*h;++p)if((truth.cells[p]!=0&&truth.cells[p]!=1)||(targets[p]!=0&&targets[p]!=1)||(targets[p]&&!truth.free(p))||zones[p]<0||zones[p]>100||(zones[p]&&!truth.free(p)))throw std::invalid_argument("invalid custom cell, target, or priority");
            config["targetCount"]=std::count(targets.begin(),targets.end(),1);
        }else generate();
        if(config["starts"].size()!=static_cast<std::size_t>(n)||config["chargingStations"].empty())throw std::invalid_argument("starts and charging stations required");
        std::set<std::string> stationIds;for(const auto& s:config["chargingStations"]){int p=at(s);if(!truth.free(p)||station(p)||!stationIds.insert(s.at("id").get<std::string>()).second)throw std::invalid_argument("stations must occupy distinct free cells and have unique IDs");stations.push_back(p);}
        base=Knowledge(w,h);observed.assign(w*h,false);visited.assign(w*h,false);mapped.assign(w*h,false);observable.assign(w*h,false);discovery.assign(w*h,-1);initialReachable.assign(w*h,0);
        std::set<int> used;
        for(int i=0;i<n;++i){if(config["starts"][i].value("agentId",-1)!=i)throw std::invalid_argument("starts must use ordered contiguous agent IDs");Agent a;a.id=i;a.pos=at(config["starts"][i]);a.energy=e("capacity");a.knowledge=Knowledge(w,h);
            if(!truth.free(a.pos)||!used.insert(a.pos).second)throw std::invalid_argument("invalid or duplicate starts");
            visited[a.pos]=true;a.visitedCells.insert(a.pos);a.recentPositions.push_back(a.pos);auto d=distances(truth,a.pos);for(int p=0;p<w*h;++p)if(d[p]<INF)initialReachable[p]=1;agents.push_back(a);
        }
        for(int p=0;p<w*h;++p)if(initialReachable[p]){observable[p]=true;for(int v:truth.neighbors(p))if(!truth.free(v))observable[v]=true;}
        faults=config["faultSchedule"].get<std::vector<json>>();
        if(faults.size()>1000)throw std::invalid_argument("fault schedule limit reached");for(const auto& fault:faults)validate_fault(fault);
        apply_faults();for(auto& a:agents){sense(a,false);update_regions(a);}
        config["map"]=truth.cells;config["targets"]=targets;config["zones"]=zones;
        initialScenario={{"config",config},{"mapHash",hash_json({{"width",w},{"height",h},{"map",truth.cells},{"targets",targets},{"zones",zones}})},{"generatorVersion",custom?"custom-1":"rooms-2"},{"componentCount",component_count(truth)}};
        event("initialized",{{"mapHash",initialScenario["mapHash"]}});heartbeats();
    }
    void queue_fault(json f){if(faults.size()>=1000)throw std::invalid_argument("fault schedule limit reached");validate_fault(f);faults.push_back(f);event("fault_queued",f);}
    void advance() {
        if(status!="READY"&&status!="RUNNING")return;
        auto start=std::chrono::steady_clock::now();status="RUNNING";++tick;
        auto elapsed=[](auto since){return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-since).count();};
        if(finishAt>=0){
            deliver();for(auto& a:agents)update_regions(a);
            if(messages.empty())status="COMPLETED";else if(tick>=config["maxTicks"].get<int>())status="TIMED_OUT";
            lastTickMs=elapsed(start);sensingMs=allocationMs=planningMs=0;communicationMs=lastTickMs;
            if(status!="RUNNING")event("terminal",{{"reason",status}});
            return;
        }
        int old=static_cast<int>(std::count(observed.begin(),observed.end(),true));
        apply_faults();auto phase=std::chrono::steady_clock::now();deliver();communicationMs=elapsed(phase);
        phase=std::chrono::steady_clock::now();for(auto& a:agents){sense(a);update_regions(a);}detect();sensingMs=elapsed(phase);
        phase=std::chrono::steady_clock::now();for(auto& a:agents)energy_mode(a);coordinator();for(auto& a:agents)local_allocate(a);allocationMs=elapsed(phase);
        phase=std::chrono::steady_clock::now();evaluate_duplicate_claims();movement();planningMs=elapsed(phase);
        phase=std::chrono::steady_clock::now();heartbeats();communicationMs+=elapsed(phase);
        int now=static_cast<int>(std::count(observed.begin(),observed.end(),true));stagnant=old==now?stagnant+1:0;
        bool any=false;for(const auto& a:agents)if(a.status=="ACTIVE"||(a.status=="DEPLETED"&&station(a.pos)))any=true;
        int required=0,known=0;for(int p=0;p<truth.size();++p)if(initialReachable[p]){++required;if(observed[p])++known;}
        bool fullyMapped=true;for(int p=0;p<truth.size();++p)if(observable[p]&&!mapped[p])fullyMapped=false;
        if(known==required&&fullyMapped){finishAt=tick;for(auto& a:agents){a.task=-1;a.lease=0;a.path={a.pos};if(a.status=="ACTIVE")a.activity="IDLE";}
            event("exploration_completed",{{"explorationTick",tick},{"pendingMessages",messages.size()}});
            if(messages.empty())status="COMPLETED";else if(tick>=config["maxTicks"].get<int>())status="TIMED_OUT";
        }
        else if(!any)status="EXHAUSTED";
        else if(tick>=config["maxTicks"].get<int>())status="TIMED_OUT";
        else if(stagnant>200){bool future=false;for(const auto& f:faults)if(!f.value("applied",false)||(!f.value("restored",false)&&f.value("restorationTick",f.value("unblockTick",-1))>tick)||(f.value("type","")=="partition"&&f.value("endTick",0)>tick))future=true;
            if(!future){bool feasible=false;for(auto& a:agents)if(a.status=="ACTIVE"){ for(auto& c:candidates(a,e("capacity")))if(c.feasible)feasible=true;}if(!feasible)status="EXHAUSTED";}}
        lastTickMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        if(status!="RUNNING")event("terminal",{{"reason",status}});
    }
    json scenario()const{return initialScenario;}
    std::string state_status()const{return status;}
    json tick_measurement()const{return {{"tick",tick},{"tickMs",lastTickMs},{"sensingMs",sensingMs},{"communicationMs",communicationMs},{"allocationMs",allocationMs},{"planningMs",planningMs}};}
    json take_events(){json out=events;events=json::array();return out;}
    json snapshot()const {
        json out={{"tick",tick},{"status",status},{"width",truth.width},{"height",truth.height},{"strategy",config["strategy"]},{"planner",config["planner"]},
            {"truth",truth.cells},{"coordinatorMap",base.grid.cells},{"stations",stations},{"targets",json::array()},{"agents",json::array()},{"unionMap",std::vector<int>(truth.size(),-1)}};
        int required=0,known=0,targetCount=0,found=0;int64_t spent=0;
        std::vector<int> team(truth.size(),-1),times(truth.size(),-1),teamZones(truth.size(),0);
        for(const auto& a:agents){spent+=a.spent;for(int p=0;p<truth.size();++p)if(a.knowledge.times[p]>times[p]){times[p]=a.knowledge.times[p];team[p]=a.knowledge.grid.cells[p];teamZones[p]=a.knowledge.priority[p];}
            json claims=json::array();for(const auto& [cell,claim]:a.claims)if(std::get<2>(claim)>tick)claims.push_back({{"cell",cell},{"owner",std::get<0>(claim)},{"score",std::get<1>(claim)},{"expires",std::get<2>(claim)},{"confirmed",a.committedClaims.count(cell)>0}});
            bool recentPeer=false;for(const auto& [id,last]:a.peerSeen)if(tick-last<=config["communication"]["heartbeatTimeoutTicks"].get<int>())recentPeer=true;
            std::string comm=tick-a.lastBase<=config["communication"]["heartbeatTimeoutTicks"].get<int>()?"CONNECTED":(recentPeer?"DEGRADED":"ISOLATED");
            std::vector<int> knownTargets;for(int p=0;p<truth.size();++p)if(a.knowledge.targets[p])knownTargets.push_back(p);
            json regions=json::array();std::string assignedRegion;for(const auto& [id,cells]:a.regions){regions.push_back({{"id",id},{"cells",cells}});if(std::binary_search(cells.begin(),cells.end(),a.task))assignedRegion=id;}
            out["agents"].push_back({{"id",a.id},{"position",a.pos},{"status",a.status},{"activity",a.activity},{"energy",a.energy},{"capacity",e("capacity")},{"distance",a.distance},{"task",a.task},{"lease",a.lease},{"path",a.path},{"map",a.knowledge.grid.cells},{"mapRevision",a.knowledge.revision},{"communication",comm},{"decisions",a.decisions},{"features",a.chosen},{"claims",claims},{"energySpent",a.spent},{"knownTargets",knownTargets},{"regions",regions},{"assignedRegion",assignedRegion}});
        }
        for(int p=0;p<truth.size();++p){if(initialReachable[p]){++required;if(observed[p])++known;}if(targets[p]){++targetCount;if(discovery[p]>=0)++found;out["targets"].push_back({{"cell",p},{"discovered",discovery[p]>=0},{"tick",discovery[p]}});}}
        out["unionMap"]=team;out["allTargetsDiscovered"]=found==targetCount;out["truthZones"]=zones;out["unionZones"]=teamZones;out["coordinatorZones"]=base.priority;
        out["coordinatorTargets"]=json::array();for(int p=0;p<truth.size();++p)if(base.targets[p])out["coordinatorTargets"].push_back(p);
        out["coordinatorAgents"]=json::array();for(const auto& [id,r]:reports)out["coordinatorAgents"].push_back({{"id",id},{"position",r.pos},{"status",r.status},{"observedTick",r.tick},{"task",r.task}});
        out["coordinatorClaims"]=json::array();for(const auto& [cell,claim]:baseClaims)if(std::get<1>(claim)>tick)out["coordinatorClaims"].push_back({{"cell",cell},{"owner",std::get<0>(claim)},{"expiry",std::get<1>(claim)},{"acknowledgedTick",std::get<2>(claim)}});
        out["stationQueues"]=json::array();for(int cell:stations){json queue=json::array();std::vector<std::pair<int,int>> ordered;auto requests=stationRequests.find(cell);if(requests!=stationRequests.end())for(const auto& [id,requestTick]:requests->second)if(agents[id].status=="ACTIVE")ordered.push_back({requestTick,id});std::sort(ordered.begin(),ordered.end());for(const auto& [requestTick,id]:ordered)queue.push_back({{"agentId",id},{"requestTick",requestTick}});out["stationQueues"].push_back({{"cell",cell},{"queue",queue}});}
        for(auto& view:out["agents"]){const auto& a=agents[view["id"].get<int>()];view["knownAgents"]=json::array();for(const auto& [id,c]:a.knowledge.contacts)view["knownAgents"].push_back({{"id",id},{"position",c.position},{"status",c.status},{"observedTick",c.tick}});
            view["taskKind"]=a.task<0?"NONE":a.parking?"PARKING":(a.activity=="RETURNING"||a.activity=="QUEUED")?"CHARGING":"FRONTIER";
            view["parkingReason"]=a.parkingReason;
            view["energyLedger"]=a.energyLedger;
            view["energyCharged"]=a.energyCharged;
            view["recentRejections"]=a.rejections;view["coordinatorAgeTicks"]=a.lastBase<0?json(nullptr):json(tick-a.lastBase);
            view["peerFreshness"]=json::array();for(const auto& [id,last]:a.peerSeen)view["peerFreshness"].push_back({{"agentId",id},{"ageTicks",tick-last},{"suspected",a.suspected.count(id)>0}});
            view["alternatives"]=a.alternatives;view["alternativesTick"]=a.alternativesTick;
            view["coordinationStatus"]=a.jointAwait?"AWAITING_JOINT_PLAN":!a.jointPath.empty()?"EXECUTING_JOINT_PLAN":"LOCAL";
            view["visitedCells"]=a.visitedCells;view["recentPositions"]=a.recentPositions;view["sensedCells"]=a.sensedCells.size();view["utilization"]=a.operationalTicks?100.0*a.busyTicks/a.operationalTicks:0;
            view["knownZones"]=a.knowledge.priority;
        }
        out["jointPlannerPhase"]=jointPhase;
        int reachableTargets=0,reachableFound=0;double restricted=0;
        for(int p=0;p<truth.size();++p)if(targets[p]){restricted+=discovery[p]<0?config["maxTicks"].get<int>():discovery[p];if(initialReachable[p]){++reachableTargets;if(discovery[p]>=0)++reachableFound;}}
        out["reachableTargetsDiscovered"]=reachableTargets==reachableFound;
        out["recovery"]=failureHistory;for(const auto& [id,when]:failures)out["recovery"].push_back(recovery_record(id));
        out["metrics"]={{"coverage",required?100.0*known/required:100},{"observedCells",known},{"reachableCells",required},{"targetsFound",found},{"targetCount",targetCount},{"distance",totalDistance},{"repeatedVisitRatio",totalDistance?static_cast<double>(repeated)/totalDistance:0},{"collisions",0},{"preventedConflicts",prevented},{"energyConsumed",spent},{"energyCharged",charged},{"bytesAttempted",bytesAttempted},{"bytesDelivered",bytesDelivered},{"replanning",replans},{"expandedNodes",expanded},{"cbsExpanded",cbsExpanded},{"plannerFallbacks",fallbacks},{"assignmentChurn",churn}};
        int observableCount=0,mappedCount=0;for(int p=0;p<truth.size();++p)if(observable[p]){++observableCount;if(mapped[p])++mappedCount;}
        out["phase"]=finishAt>=0?"FINALIZING":"EXPLORING";
        out["metrics"]["mappingCoverage"]=observableCount?100.0*mappedCount/observableCount:100;
        int globalFree=0,globalKnown=0,knownObstacles=0;for(int p=0;p<truth.size();++p){if(config["map"][p]==0){++globalFree;if(observed[p])++globalKnown;}if(mapped[p]&&!truth.free(p))++knownObstacles;}
        out["metrics"]["globalCoverage"]=globalFree?100.0*globalKnown/globalFree:100;
        out["metrics"]["globalFreeCells"]=globalFree;out["metrics"]["observedObstacleCells"]=knownObstacles;
        int pending=0;for(const auto& a:agents)if(a.pendingMovementTick>=0)++pending;
        out["metrics"]["nonproductiveMovement"]=nonproductiveMoves;out["metrics"]["productiveMovement"]=productiveMoves;out["metrics"]["unclassifiedMovement"]=unclassifiedMoves+pending;
        out["metrics"]["energyPerObservedFreeCell"]=known?json(static_cast<double>(spent)/known):json(nullptr);
        out["metrics"]["messagesAttempted"]=attemptedMessages;out["metrics"]["messagesDelivered"]=deliveredMessages;
        out["metrics"]["messageDeliveryRatio"]=attemptedMessages?static_cast<double>(deliveredMessages)/attemptedMessages:0;
        out["metrics"]["duplicateClaims"]=duplicatePairs.size();out["metrics"]["duplicateClaimTicks"]=duplicateClaimTicks;out["metrics"]["duplicateClaimEpisodes"]=duplicateClaimEpisodes;
        out["communicationCounters"]={{"attemptedMessages",attemptedByType},{"deliveredMessages",deliveredByType},{"attemptedBytes",attemptedBytesByType},{"deliveredBytes",deliveredBytesByType}};
        out["metrics"]["explorationCompletionTick"]=finishAt>=0?json(finishAt):json(nullptr);
        out["metrics"]["targetDiscoveryRestrictedTicks"]=targetCount?json(restricted/targetCount):json(nullptr);
        out["metrics"]["targetDiscoveryFraction"]=targetCount?static_cast<double>(found)/targetCount:1;
        out["metrics"]["completion"]=status=="COMPLETED"?1:0;
        int busyTicks=0,operationalTicks=0;for(const auto& a:agents){busyTicks+=a.busyTicks;operationalTicks+=a.operationalTicks;}
        out["metrics"]["agentUtilization"]=operationalTicks?100.0*busyTicks/operationalTicks:0;
        auto mean=[&](const char* key)->json {double sum=0;int count=0;for(const auto& episode:out["recovery"])if(!episode[key].is_null()){sum+=episode[key].get<double>();++count;}return count?json(sum/count):json(nullptr);};
        out["metrics"]["failureDetectionTicks"]=mean("detectionTicks");out["metrics"]["assignmentRecoveryTicks"]=mean("assignmentTicks");out["metrics"]["progressRecoveryTicks"]=mean("progressTicks");
        // Canonical hash excludes wall-clock measurements, but includes maps and observable decisions.
        out["stateHash"]=hash_json(out);out["metrics"]["tickMs"]=lastTickMs;
        out["metrics"]["sensingMs"]=sensingMs;out["metrics"]["communicationMs"]=communicationMs;out["metrics"]["allocationMs"]=allocationMs;out["metrics"]["planningMs"]=planningMs;return out;
    }
};
}
