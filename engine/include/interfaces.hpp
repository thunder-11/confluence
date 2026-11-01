#pragma once
#include "allocation.hpp"

namespace confluence {
using AgentId = int;
enum class ResultStatus { SUCCESS, NO_PATH, INFEASIBLE, BUDGET_EXHAUSTED, INVALID_INPUT };

// These interfaces deliberately contain no environment handle or truth storage.
struct AgentView {AgentId id;int position;int64_t energy;const Grid& localMap;};
struct CoordinatorView {const Grid& deliveredMap;};
struct PlanningView {const Grid& knownGraph;};
struct PathRequest {int start,goal;bool astar=true;};
struct PathResult {ResultStatus status=ResultStatus::INVALID_INPUT;std::vector<int> path;int expanded=0;};
inline PathResult plan(const PlanningView& view,const PathRequest& request) {
    if(request.start<0||request.goal<0||request.start>=view.knownGraph.size()||request.goal>=view.knownGraph.size())return {};
    auto result=search(view.knownGraph,request.start,request.goal,request.astar);
    return {result.path.empty()?ResultStatus::NO_PATH:ResultStatus::SUCCESS,std::move(result.path),result.expanded};
}
struct AllocationInput {const std::vector<std::vector<Candidate>>& rows;std::string strategy;};
struct AllocationResult {ResultStatus status=ResultStatus::INVALID_INPUT;std::vector<int> assignments;};
inline AllocationResult allocate(const AllocationInput& input) {
    if(input.strategy!="greedy"&&input.strategy!="hungarian"&&input.strategy!="adaptive")return {};
    if(!input.rows.empty())for(const auto& row:input.rows)if(row.size()!=input.rows.front().size())return {};
    auto assignments=match(input.rows,input.strategy);bool useful=false;for(int task:assignments)if(task>=0)useful=true;
    return {useful?ResultStatus::SUCCESS:ResultStatus::INFEASIBLE,std::move(assignments)};
}
}
