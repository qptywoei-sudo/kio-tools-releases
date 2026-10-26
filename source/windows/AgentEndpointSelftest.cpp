#include "AgentEndpoint.h"
#include <cassert>
#include <iostream>
int main(){using J=nlohmann::json;const std::string id="12345678-1234-1234-1234-123456789abc";
 J health={{"connected",true},{"version","4.6.23"},{"os","Windows"},{"deviceId",id},{"nativeReady",true},{"operations",J::array({"image_process","capture"})}};
 assert(AgentEndpoint::ready(health,id));assert(AgentEndpoint::matches(health,""));
 assert(!AgentEndpoint::matches(health,"00000000-0000-0000-0000-000000000000"));
 for(const auto&key:{"deviceId","nativeReady","operations","version","os","connected"}){auto other=health;other.erase(key);assert(!AgentEndpoint::matches(other,id));}
 auto other=health;other["nativeReady"]=false;assert(AgentEndpoint::matches(other,id)&&!AgentEndpoint::ready(other,id));
 for(auto invalid:{J("true"),J(1),J()}){other=health;other["connected"]=invalid;assert(!AgentEndpoint::matches(other,id));}
 other=health;other["os"]="macOS";assert(!AgentEndpoint::matches(other,id));
 other=health;other["deviceId"]="../fake";assert(!AgentEndpoint::matches(other,id));
 other=health;other["operations"]=J::array();assert(!AgentEndpoint::matches(other,id));
 other=health;other["operations"]=J::array({42,"image_process"});assert(!AgentEndpoint::matches(other,id));
 other=health;other["operations"]=J::array({"creator"});assert(!AgentEndpoint::matches(other,id));
 assert(!AgentEndpoint::matches(J{{"connected",true},{"version","4.6.23"}},id));
 assert((AgentEndpoint::ports==std::array<unsigned short,4>{4323,4324,4325,4321}));
 for(auto port:AgentEndpoint::ports)assert(AgentEndpoint::toolsUrl(port)==L"http://127.0.0.1:"+std::to_wstring(port)+L"/tools/");
 assert(AgentEndpoint::toolsUrl(4322).empty());
 std::cout<<"PASS: existing same-device Windows agent identity, native readiness, foreign service rejection, candidate order and selected URLs\n";
}
