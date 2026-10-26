#pragma once
#include <string>
#include <vector>
#include <algorithm>
namespace ShortcutModel {
struct Key {unsigned mods=0,key=0;bool enabled=false;};
inline std::string upper(std::string s){for(char&c:s)if(c>='a'&&c<='z')c-='a'-'A';return s;}
inline bool parse(const std::string&s,Key&out){out={};if(s.empty())return true;std::vector<std::string>parts;size_t start=0;while(start<=s.size()){auto end=s.find('+',start);parts.push_back(upper(s.substr(start,end==std::string::npos?s.size()-start:end-start)));if(end==std::string::npos)break;start=end+1;}if(parts.size()<2)return false;for(size_t i=0;i+1<parts.size();i++){unsigned bit=parts[i]=="ALT"?1:parts[i]=="CONTROL"||parts[i]=="CTRL"?2:parts[i]=="SHIFT"?4:parts[i]=="WIN"?8:0;if(!bit||(out.mods&bit))return false;out.mods|=bit;}auto key=parts.back();if(key.size()==1&&key[0]>='A'&&key[0]<='Z')out.key=key[0];else if(key.size()>=2&&key[0]=='F'){unsigned n=0;for(size_t i=1;i<key.size();i++){if(key[i]<'0'||key[i]>'9')return false;n=n*10+key[i]-'0';if(n>24)return false;}if(!n)return false;out.key=0x6f+n;}else if(key=="PRINTSCREEN")out.key=0x2c;else if(key=="SPACE")out.key=0x20;else return false;int count=((out.mods&1)?1:0)+((out.mods&2)?1:0)+((out.mods&4)?1:0)+((out.mods&8)?1:0);if((out.key>=65&&out.key<=90||out.key==0x20)&&count<2)return false;if(out.mods==6&&out.key==0x79)return false;out.enabled=true;return true;}
template<class Register> inline std::vector<bool> recover(const std::vector<Key>&desired,std::vector<bool> active,Register add){
 active.resize(desired.size(),false);
 for(size_t i=0;i<desired.size();++i)if(desired[i].enabled&&!active[i])active[i]=add(i,desired[i]);
 return active;
}
inline bool validSet(const std::vector<Key>&keys){for(size_t i=0;i<keys.size();i++)if(keys[i].enabled)for(size_t n=0;n<i;n++)if(keys[n].enabled&&keys[n].mods==keys[i].mods&&keys[n].key==keys[i].key)return false;return true;}
inline std::string normalized(const Key&k){if(!k.enabled)return {};std::string s;if(k.mods&2)s+="Control+";if(k.mods&4)s+="Shift+";if(k.mods&1)s+="Alt+";if(k.mods&8)s+="Win+";if(k.key>=0x70&&k.key<=0x87)s+="F"+std::to_string(k.key-0x6f);else if(k.key==0x20)s+="Space";else if(k.key==0x2c)s+="PrintScreen";else s+=(char)k.key;return s;}
}
