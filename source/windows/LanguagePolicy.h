#pragma once
#include <cctype>
#include <algorithm>
#include <string>
#include <vector>
namespace KioLanguage {
inline const char* const codes[] = {"vi","en","ko","ja","zh-TW","zh-CN"};
inline std::string normalize(std::string value) {
 std::transform(value.begin(),value.end(),value.begin(),[](unsigned char c){return c=='_'?'-':(char)std::tolower(c);});
 auto start=value.find_first_not_of(" \t\r\n"),end=value.find_last_not_of(" \t\r\n");if(start==std::string::npos)return {};value=value.substr(start,end-start+1);
 auto base=value.substr(0,value.find('-'));if(base=="vi"||base=="en"||base=="ko"||base=="ja")return base;
 if(base!="zh")return {};
 std::vector<std::string> tags;size_t at=3;while(at<value.size()){auto next=value.find('-',at);tags.push_back(value.substr(at,next-at));if(next==std::string::npos)break;at=next+1;}
 auto has=[&](const char*t){return std::find(tags.begin(),tags.end(),t)!=tags.end();};
 if(has("hant"))return "zh-TW";if(has("hans"))return "zh-CN";
 return has("tw")||has("hk")||has("mo")?"zh-TW":"zh-CN";
}
inline int index(const std::string&value){for(int i=0;i<6;i++)if(value==codes[i])return i;return 1;}
}
