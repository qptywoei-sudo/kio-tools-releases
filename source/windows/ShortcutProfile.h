#pragma once
#include <windows.h>
#include "ShortcutModel.h"
namespace ShortcutProfile {
inline std::vector<ShortcutModel::Key> read(const std::wstring&path){
 const wchar_t*names[]={L"areaCapture",L"fullCapture",L"webCapture",L"recordToggle",L"aiTranslate",L"recordArea"};
 std::vector<ShortcutModel::Key> keys(6);
 for(int i=0;i<6;++i){
  wchar_t value[256];GetPrivateProfileStringW(L"shortcuts",names[i],i==0?L"__legacy__":i==4?L"Control+Shift+T":L"",value,256,path.c_str());
  std::string text;for(auto ch:std::wstring(value))text+=(char)ch;
  if(i==0&&text=="__legacy__"){
   ShortcutModel::Key old{(unsigned)GetPrivateProfileIntW(L"shortcut",L"modifiers",6,path.c_str()),(unsigned)GetPrivateProfileIntW(L"shortcut",L"key",0x78,path.c_str()),true};
   if(!ShortcutModel::parse(ShortcutModel::normalized(old),keys[0]))ShortcutModel::parse("Control+Shift+F9",keys[0]);
   keys[0].enabled=GetPrivateProfileIntW(L"shortcut",L"enabled",1,path.c_str())!=0;
  }else if(!ShortcutModel::parse(text,keys[i])){
   if(i==0)ShortcutModel::parse("Control+Shift+F9",keys[i]);
   else keys[i]={};
  }
 }
 return keys;
}
}
