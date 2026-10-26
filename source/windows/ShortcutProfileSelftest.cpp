#include "ShortcutProfile.h"
#include "UnicodeProfile.h"
#include <cassert>
#include <iostream>
int main(){
 wchar_t dir[MAX_PATH],file[MAX_PATH];GetTempPathW(MAX_PATH,dir);GetTempFileNameW(dir,L"KIO",0,file);assert(EnsureUnicodeProfile(file));
 auto write=[&](const wchar_t*section,const wchar_t*key,const wchar_t*value){assert(WritePrivateProfileStringW(section,key,value,file));WritePrivateProfileStringW(nullptr,nullptr,nullptr,file);};
 // Legacy Win combinations must migrate without reverting to Ctrl+Shift+F9.
 write(L"shortcut",L"modifiers",L"10");write(L"shortcut",L"key",L"75");
 assert(ShortcutModel::normalized(ShortcutProfile::read(file)[0])=="Control+Win+K");
 write(L"shortcut",L"modifiers",L"8");write(L"shortcut",L"key",L"119");
 assert(ShortcutModel::normalized(ShortcutProfile::read(file)[0])=="Win+F8");
 write(L"shortcut",L"enabled",L"0");assert(!ShortcutProfile::read(file)[0].enabled);
 const wchar_t*names[]={L"areaCapture",L"fullCapture",L"webCapture",L"recordToggle",L"aiTranslate",L"recordArea"};
 const wchar_t*values[]={L"Control+Shift+G",L"Alt+Win+J",L"Control+Shift+F7",L"Control+Shift+F8",L"Control+Shift+T",L"Shift+Alt+R"};
 for(int i=0;i<6;i++)write(L"shortcuts",names[i],values[i]);
 auto keys=ShortcutProfile::read(file);for(int i=0;i<6;i++){std::wstring wide=values[i];assert(ShortcutModel::normalized(keys[i])==std::string(wide.begin(),wide.end()));}
 write(L"shortcuts",L"areaCapture",L"");assert(!ShortcutProfile::read(file)[0].enabled);
 write(L"shortcuts",L"areaCapture",L"Control+K");assert(ShortcutModel::normalized(ShortcutProfile::read(file)[0])=="Control+Shift+F9");
 DeleteFileW(file);std::cout<<"Shortcut profile legacy/new/disabled/Win restart loading passed\n";
}
