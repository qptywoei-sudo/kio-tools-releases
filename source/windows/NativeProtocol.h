#pragma once
#include "include/json.hpp"
#include <string>
#include <set>
#include <cmath>
namespace NativeProtocol {
using Json=nlohmann::json;
inline bool uuid(const std::string&s){if(s.size()!=36)return false;for(size_t i=0;i<s.size();++i){if(i==8||i==13||i==18||i==23){if(s[i]!='-')return false;}else if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')||(s[i]>='A'&&s[i]<='F')))return false;}return true;}
inline const std::set<std::string>&operations(){static const std::set<std::string>s={"pair.approve","folder.choose","files.choose","file.open","file.reveal","capture.start","capture.cancel","clipboard.copy","editor.open","record.start","record.stop","record.pause","record.resume","permissions.get","permissions.open","settings.apply","phone.open","phone.status","phone.pair","phone.connect","phone.start","phone.stop","phone.keyboard","native.tools","app.quit"};return s;}
inline bool phoneAddress(const std::string&s){
 if(s.size()>64)return false;auto at=s.find(':');if(at==std::string::npos||s.find(':',at+1)!=std::string::npos)return false;
 unsigned parts[4]={},part=0,number=0,digits=0;
 for(size_t i=0;i<=at;i++){char c=i==at?'.':s[i];if(c>='0'&&c<='9'){if(++digits>3)return false;number=number*10+(c-'0');if(number>255)return false;}else if(c=='.'){if(!digits||part>=4)return false;parts[part++]=number;digits=number=0;}else return false;}
 if(part!=4)return false;unsigned port=0;digits=0;for(size_t i=at+1;i<s.size();i++){if(s[i]<'0'||s[i]>'9'||++digits>5)return false;port=port*10+(s[i]-'0');}if(!port||port>65535)return false;
 return parts[0]==10||parts[0]==127||(parts[0]==172&&parts[1]>=16&&parts[1]<=31)||(parts[0]==192&&parts[1]==168)||(parts[0]==169&&parts[1]==254);
}
inline bool phoneSerial(const std::string&s){if(s.empty()||s.size()>255||s.front()=='-')return false;for(unsigned char c:s)if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-'||c=='.'||c==':'))return false;return true;}
inline bool phoneArguments(const std::string&op,const Json&a){
 if(!a.is_object())return false;std::set<std::string>allowed;
 if(op=="phone.pair")allowed={"address","code"};else if(op=="phone.connect")allowed={"address"};else if(op=="phone.start")allowed={"serial","keyboard","mouse","audio","clipboard"};else if(op=="phone.keyboard")allowed={"serial"};else if(op!="phone.status"&&op!="phone.stop")return false;
 for(auto i=a.begin();i!=a.end();++i)if(!allowed.count(i.key()))return false;
 if(op=="phone.pair"||op=="phone.connect"){if(!a.contains("address")||!a["address"].is_string()||!phoneAddress(a["address"].get<std::string>()))return false;}
 if(op=="phone.pair"){if(!a.contains("code")||!a["code"].is_string())return false;auto code=a["code"].get<std::string>();if(code.size()!=6)return false;for(char c:code)if(c<'0'||c>'9')return false;}
 if(op=="phone.start"||op=="phone.keyboard"){if(!a.contains("serial")||!a["serial"].is_string()||!phoneSerial(a["serial"].get<std::string>()))return false;}
 for(const char*key:{"keyboard","mouse","audio"})if(a.contains(key)){if(!a[key].is_string())return false;auto value=a[key].get<std::string>();if(std::string(key)=="audio"){if(value!="output"&&value!="aac"&&value!="off")return false;}else if(value!="sdk"&&value!="uhid")return false;}
 return !a.contains("clipboard")||a["clipboard"].is_boolean();
}
inline bool captureCancelArguments(const Json&a){
 if(!a.is_object()||a.size()!=1||!a.contains("requestId")||!a["requestId"].is_string())return false;
 auto id=a["requestId"].get<std::string>();if(!uuid(id))return false;
 for(char c:id)if(c>='A'&&c<='F')return false;return true;
}
inline bool captureCancelMatches(const Json&a,const std::string&activeId){return captureCancelArguments(a)&&!activeId.empty()&&a["requestId"].get<std::string>()==activeId;}
inline bool clipboardArguments(const Json&a){
 if(!a.is_object()||a.size()!=1||!a.contains("path")||!a["path"].is_string())return false;
 auto p=a["path"].get<std::string>();return !p.empty()&&p.size()<131040&&p.find_first_of("\r\n") == std::string::npos&&p.find('\0')==std::string::npos;
}
inline bool recordArguments(const Json&a){
 if(!a.is_object())return false;static const std::set<std::string>allowed={"mode","monitor","fps","microphone","systemAudio","width","scale_percent","format"};
 for(auto i=a.begin();i!=a.end();++i)if(!allowed.count(i.key()))return false;
 for(auto key:{"microphone","systemAudio"})if(a.contains(key)&&!a[key].is_boolean())return false;
 for(auto key:{"monitor","fps","width","scale_percent"})if(a.contains(key)&&!a[key].is_number_integer())return false;
 if(a.contains("mode")&&(!a["mode"].is_string()||(a["mode"]!="area"&&a["mode"]!="full"&&a["mode"]!="window")))return false;
 if(a.contains("format")&&(!a["format"].is_string()||a["format"]!="mp4"))return false;
 try{int fps=a.value("fps",30),width=a.value("width",0),scale=a.value("scale_percent",100),monitor=a.value("monitor",0);return fps>=5&&fps<=60&&width>=0&&width<=7680&&(width==0||width>=2)&&scale>=10&&scale<=100&&monitor>=0&&monitor<=255;}catch(...){return false;}
}
inline bool settingsArguments(const Json&a){
 if(!a.is_object())return false;static const std::set<std::string>allowed={"language","autoStart","shortcuts","closeAfterCaptureCopy","openCaptureEditor","captureFormat"};
 for(auto i=a.begin();i!=a.end();++i)if(!allowed.count(i.key()))return false;
 for(auto key:{"autoStart","closeAfterCaptureCopy","openCaptureEditor"})if(a.contains(key)&&!a[key].is_boolean())return false;
 if(a.contains("captureFormat")&&(!a["captureFormat"].is_string()||(a["captureFormat"]!="png"&&a["captureFormat"]!="jpg")))return false;
 return (!a.contains("language")||a["language"].is_string())&&(!a.contains("shortcuts")||a["shortcuts"].is_object());
}
inline std::string validate(const Json&j,const std::string&filenameId,double now){if(!j.is_object()||!j.contains("id")||!j["id"].is_string()||j["id"].get<std::string>()!=filenameId||!uuid(filenameId)||!j.contains("operation")||!j["operation"].is_string()||!j.contains("args")||!j["args"].is_object()||!j.contains("expiresAt")||!j["expiresAt"].is_number())return "invalidRequest";if(!operations().count(j["operation"].get<std::string>()))return "unsupported";double until=j["expiresAt"].get<double>();if(!std::isfinite(until)||until<=now)return "expired";if(until>now+3600)return "invalidRequest";return {};}
}
