#include "simulation.hpp"
#include "planner_study.hpp"
#include <iostream>
using namespace confluence;
int main(int argc,char** argv) {
    if(argc==2&&std::string(argv[1])=="--planner-study"){std::cout<<planner_study().dump()<<std::endl;return 0;}
    Simulation simulation;std::string line;bool initialized=false;
    while(std::getline(std::cin,line)) {
        json request;std::string id;
        try {
            if(line.size()>32*1024*1024)throw std::invalid_argument("protocol line too large");
            request=json::parse(line);id=request.value("requestId","");
            if(request.value("protocolVersion",0)!=1)throw std::invalid_argument("unsupported protocol version");
            auto type=request.at("type").get<std::string>();auto payload=request.value("payload",json::object());
            if(type!="initialize"&&type!="shutdown"&&!initialized)throw std::invalid_argument("initialize the engine before issuing commands");
            json response={{"protocolVersion",1},{"requestId",id}};
            if(type=="initialize"){initialized=false;simulation.initialize(payload);initialized=true;response["type"]="ready";response["scenario"]=simulation.scenario();}
            else if(type=="advance"){int count=payload.value("ticks",1);if(count<1||count>10)throw std::invalid_argument("advance ticks must be 1..10");response["measurements"]=json::array();for(int i=0;i<count&&(simulation.state_status()=="READY"||simulation.state_status()=="RUNNING");++i){simulation.advance();response["measurements"].push_back(simulation.tick_measurement());}response["type"]=(simulation.state_status()=="READY"||simulation.state_status()=="RUNNING")?"tick_delta":"terminal";}
            else if(type=="queue_fault"){simulation.queue_fault(payload);response["type"]="ack";}
            else if(type=="snapshot")response["type"]="snapshot";
            else if(type=="shutdown"){std::cout<<json({{"protocolVersion",1},{"requestId",id},{"type","ack"}}).dump()<<std::endl;break;}
            else throw std::invalid_argument("unknown engine command");
            response["snapshot"]=simulation.snapshot();response["events"]=simulation.take_events();
            std::cout<<response.dump()<<std::endl;
        }catch(const std::invalid_argument& e){std::cout<<json({{"protocolVersion",1},{"requestId",id},{"type","error"},{"error",{{"code","INVALID_INPUT"},{"message",e.what()},{"details",json::object()}}}}).dump()<<std::endl;}
        catch(const std::exception& e){std::cout<<json({{"protocolVersion",1},{"requestId",id},{"type","error"},{"error",{{"code","ENGINE_ERROR"},{"message",e.what()},{"details",json::object()}}}}).dump()<<std::endl;}
    }
}
