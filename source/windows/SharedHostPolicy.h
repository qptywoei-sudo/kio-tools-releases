#pragma once
#include <string>
#include <set>
#include <algorithm>
#include <cmath>
#include "NativeProtocol.h"

namespace SharedHostPolicy {
inline bool category(const std::string&value){
 static const std::set<std::string>allowed={"home","image","pdf","signature","capture","record","web","codes","files","organize","media","phone","settings","ai"};
 return allowed.count(value)!=0;
}
inline std::string shortcut(const std::string&value){
 if(value=="toggleRecording")return "recordToggle";
 return value=="areaCapture"||value=="fullCapture"||value=="webCapture"||value=="recordToggle"||value=="recordArea"||value=="aiTranslate"?value:std::string();
}
inline bool captureShortcut(const std::string&value){return value=="areaCapture"||value=="fullCapture"||value=="webCapture"||value=="aiTranslate";}
inline bool toolsSource(const std::string&uri,const std::string&origin){
 std::string base=origin+"/tools/";
 if(uri.compare(0,base.size(),base)!=0)return false;
 return uri.size()==base.size()||uri[base.size()]=='?'||uri[base.size()]=='#';
}
inline std::string message(const nlohmann::json&value){
 if(!value.is_object()||value.size()!=1||!value.contains("action")||!value["action"].is_string())return {};
 std::string action=value["action"].get<std::string>();
 return action=="desktopReady"||action=="surfaceReady"||action=="driveConnected"||action=="shortcutError"||action=="captureStarted"||action=="captureReady"||action=="captureClosed"||action=="captureCancelled"?action:std::string();
}
inline bool copyText(const nlohmann::json&value){
 if(!value.is_object()||value.size()!=3||!value.contains("action")||!value["action"].is_string()||value["action"]!="copyText"||!value.contains("requestId")||!value["requestId"].is_string()||!NativeProtocol::uuid(value["requestId"].get<std::string>())||!value.contains("text")||!value["text"].is_string())return false;
 const auto&text=value["text"].get_ref<const std::string&>();
 // The native UTF-16 decoder enforces the final 12,000-code-unit bound.
 return text.size()<=48000&&text.find('\0')==std::string::npos;
}
inline bool captureFit(const nlohmann::json&value){
 if(!value.is_object()||value.size()!=4||!value.contains("action")||value["action"]!="captureFit")return false;
 for(auto key:{"width","height","chromeHeight"})if(!value.contains(key)||!value[key].is_number_integer())return false;
 const auto w=value["width"].get<long long>(),h=value["height"].get<long long>(),chrome=value["chromeHeight"].get<long long>();
 return w>0&&w<=64000&&h>0&&h<=64000&&w*h<=64000000&&chrome>=0&&chrome<=600;
}
struct CaptureSize{int width,height;};
inline CaptureSize fitCaptureSize(int imageWidth,int imageHeight,int extraWidth,int extraHeight,int availableWidth,int availableHeight,int minimumWidth,int minimumHeight){
 if(imageWidth<=0||imageHeight<=0||availableWidth<=0||availableHeight<=0)return {0,0};
 const auto scale=std::min({1.,std::max(1,availableWidth-extraWidth)/(double)imageWidth,std::max(1,availableHeight-extraHeight)/(double)imageHeight});
 return {std::min(availableWidth,std::max(minimumWidth,(int)std::ceil(imageWidth*scale)+extraWidth)),std::min(availableHeight,std::max(minimumHeight,(int)std::ceil(imageHeight*scale)+extraHeight))};
}
inline bool credential(const nlohmann::json&value,const nlohmann::json&identity,const std::string&origin,const std::string&version){
 if(!value.is_object()||value.size()!=6)return false;
 for(auto key:{"token","origin","deviceId","ownerId","version","clientName"})if(!value.contains(key)||!value[key].is_string())return false;
 std::string token=value["token"].get<std::string>();
 if(token.size()<32||token.size()>256||token.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")!=std::string::npos)return false;
 if(value["origin"]!=origin||value["version"]!=version||value["ownerId"]!="desktop"||value["clientName"]!="GalaxyControl"||!NativeProtocol::uuid(value["deviceId"].get<std::string>()))return false;
 return identity.is_object()&&identity.contains("deviceId")&&identity["deviceId"]==value["deviceId"];
}
struct CaptureVisibility {
 bool pending=false,wasVisible=false,ready=false;
 bool begin(bool visible){if(pending&&!ready)return false;pending=true;ready=false;wasVisible=visible;return true;}
 // The UI also starts captures directly. A native shortcut may already have
 // remembered visibility, so its matching UI event must not overwrite it.
 void started(bool visible){if(!pending||ready)begin(visible);}
 // Successful copy/save closes the editor; cancellation restores the prior window.
 bool finish(const std::string&action,bool&visible){
  if(!pending)return false;
  if(action=="captureReady"){ready=true;visible=true;return true;}
  if(action!="captureClosed"&&action!="captureCancelled")return false;
  visible=action=="captureCancelled"&&wasVisible;pending=false;wasVisible=false;ready=false;return true;
 }
 // Closing the app window cancels the editor session without restoring or
 // activating it; a later global shortcut must be able to start afresh.
 bool closeWindow(){bool active=pending;reset();return active;}
 void reset(){pending=false;wasVisible=false;ready=false;}
};
}
