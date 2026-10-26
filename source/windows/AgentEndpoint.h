#pragma once
#include "NativeProtocol.h"
#include <array>
#include <string>

namespace AgentEndpoint {
inline constexpr std::array<unsigned short,4> ports={4323,4324,4325,4321};
inline bool validPort(unsigned short port){for(auto candidate:ports)if(candidate==port)return true;return false;}
inline std::wstring toolsUrl(unsigned short port){return validPort(port)?L"http://127.0.0.1:"+std::to_wstring(port)+L"/tools/":std::wstring();}
// An unrelated localhost service must never be mistaken for our agent.
inline bool matches(const nlohmann::json&value,const std::string&deviceId){
 try {
  if(!value.is_object()||!value.contains("connected")||!value["connected"].is_boolean()||!value["connected"].get<bool>()||
     value.value("version",std::string())!="4.6.23"||value.value("os",std::string())!="Windows"||
     !value.contains("deviceId")||!value["deviceId"].is_string()||!NativeProtocol::uuid(value["deviceId"].get<std::string>())||
     (!deviceId.empty()&&value["deviceId"].get<std::string>()!=deviceId)||
     !value.contains("nativeReady")||!value["nativeReady"].is_boolean()||
     !value.contains("operations")||!value["operations"].is_array()||value["operations"].empty()||value["operations"].size()>128)return false;
  bool image=false;
  for(const auto&operation:value["operations"]){if(!operation.is_string()||operation.get_ref<const std::string&>().empty()||operation.get_ref<const std::string&>().size()>128)return false;image|=operation=="image_process";}
  return image;
 } catch(...){return false;}
}
inline bool ready(const nlohmann::json&value,const std::string&deviceId){return matches(value,deviceId)&&value["nativeReady"].get<bool>();}
}
