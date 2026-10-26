#include "LoginStartup.h"
#include <iostream>
#include <cstdlib>
using namespace KioLoginStartup;
static int checks=0;
static void check(bool condition,const char*message){++checks;if(!condition){std::cerr<<"FAIL: "<<message<<"\n";std::exit(1);}}
static bool same(const Value&a,const Value&b){return a.exists==b.exists&&a.type==b.type&&a.data==b.data;}
int main(){
 std::wstring base=L"Software\\KIO\\Tools\\StartupSelftest-"+std::to_wstring(GetCurrentProcessId());
 Locations paths{base+L"\\Run",base+L"\\Approved",base+L"\\Preferences",L"GalaxyControlPersonal"};
 struct Cleanup{std::wstring path;~Cleanup(){RegDeleteTreeW(HKEY_CURRENT_USER,path.c_str());}}cleanup{base};
 Store store(paths);std::wstring first=L"C:\\Users\\테스트 사용자\\KIO Tools\\KIOControl.exe",moved=L"D:\\내 프로그램\\KIOControl.exe";
 check(!store.requested(),"fresh install does not opt in");
 check(store.reconcile(first),"fresh disabled preference migrates");
 check(std::string(store.status(first))=="disabled","fresh status disabled");
 check(store.set(true,first),"explicit enable succeeds");
 check(Store(paths).requested(),"on preference survives a new store instance");
 check(std::string(Store(paths).status(first))=="enabled","registration matches Unicode spaced path");
 Value registered;std::wstring value;check(read(paths.run,paths.name.c_str(),registered)&&text(registered,value)&&value==L"\""+first+L"\" --background","quoted background command exact");
 check(store.reconcile(moved),"moved portable path repaired");
 check(store.requested()&&std::string(store.status(moved))=="enabled","move preserves on choice");
 Value disabled;disabled.exists=true;disabled.type=REG_BINARY;disabled.data.assign(12,0);disabled.data[0]=3;disabled.data[4]=99;
 check(write(paths.approval,paths.name.c_str(),disabled),"simulate Windows Startup Apps disable");
 check(write(paths.approval,L"AnotherApplication",disabled),"seed unrelated Windows startup decision");
 check(store.requested()&&std::string(store.status(moved))=="blocked","blocked Windows decision does not erase requested on preference");
 check(store.reconcile(first),"startup can repair path while Windows-disabled");
 Value observed;check(read(paths.approval,paths.name.c_str(),observed)&&same(observed,disabled),"ordinary startup preserves Windows opt out byte for byte");
 check(std::string(store.status(first))=="blocked","ordinary startup never pretends blocked registration is effective");
 check(store.set(true,first),"explicit repair clears only own Windows decision");
 check(std::string(store.status(first))=="enabled","explicit repair verified enabled");
 check(read(paths.approval,L"AnotherApplication",observed)&&same(observed,disabled),"other startup apps untouched");
 Snapshot before;check(store.snapshot(before),"capture rollback snapshot");
 check(store.set(false,first)&&!store.requested(),"explicit disable saves off");
 check(store.reconcile(moved)&&std::string(store.status(moved))=="disabled","off survives restart and a moved app");
 check(read(paths.run,paths.name.c_str(),observed)&&!observed.exists,"off removes registration");
 check(store.restore(before),"failed outer settings transaction can restore complete startup snapshot");
 Snapshot after;check(store.snapshot(after)&&same(before.run,after.run)&&same(before.approval,after.approval)&&same(before.preference,after.preference),"rollback restores exact registry bytes");
 check(!store.set(true,L"C:\\Other.exe"),"reject unrelated executable target");
 check(!store.set(true,L"C:\\KIOControl.exe\" injected"),"reject malformed command target");
 check(!store.set(true,L"C:\\"+std::wstring(260,L'x')+L"\\KIOControl.exe"),"reject a command longer than Windows Run can launch");
 check(store.requested(),"invalid target does not reset persisted preference");
 check(write(paths.preference,L"StartAtLogin",{}),"remove preference to simulate old version");
 check(write(paths.run,paths.name.c_str(),textValue(command(first))),"seed legacy moved Run registration");
 check(write(paths.approval,paths.name.c_str(),disabled),"seed legacy Windows-disabled item");
 check(store.reconcile(moved)&&store.requested(),"legacy enabled setting migrates independently of old location");
 check(std::string(store.status(moved))=="blocked","legacy migration respects Windows-disabled state");
 check(store.set(false,moved),"save off before foreign-value test");
 check(write(paths.run,paths.name.c_str(),textValue(L"\"C:\\Other.exe\" --background")),"seed unexpected own-name value");
 check(!store.reconcile(moved),"automatic repair refuses unexpected executable");
 check(read(paths.run,paths.name.c_str(),observed)&&text(observed,value)&&value==L"\"C:\\Other.exe\" --background","unexpected value preserved");
 auto invalid=flagValue(true);invalid.data[0]=9;check(write(paths.preference,L"StartAtLogin",invalid),"seed malformed preference");
 check(!store.reconcile(moved)&&std::string(store.status(moved))=="error","corrupt preference reported rather than overwritten");
 std::cout<<checks<<" isolated startup registry checks passed\n";
}
