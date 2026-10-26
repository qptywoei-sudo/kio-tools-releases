#pragma once
#include <windows.h>
#include <string>
#include <vector>
#include <cstring>

// A stable, per-Windows-user preference is separate from the portable executable's path.
// Only an explicit Enable action resets this application's Windows Startup Apps decision.
// Ordinary startup repairs a moved path but preserves a Windows-disabled item.
namespace KioLoginStartup {
struct Value { bool exists=false; DWORD type=REG_NONE; std::vector<BYTE> data; };
struct Snapshot { Value run, approval, preference; };
struct Locations {
    std::wstring run=L"Software\\Microsoft\\Windows\\CurrentVersion\\Run";
    std::wstring approval=L"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\Run";
    std::wstring preference=L"Software\\KIO\\Tools\\Preferences";
    std::wstring name=L"GalaxyControlPersonal";
};
inline bool read(const std::wstring&path,const wchar_t*name,Value&out) {
    out={}; HKEY key=nullptr;
    LONG result=RegOpenKeyExW(HKEY_CURRENT_USER,path.c_str(),0,KEY_QUERY_VALUE,&key);
    if(result==ERROR_FILE_NOT_FOUND)return true;
    if(result!=ERROR_SUCCESS)return false;
    DWORD size=0;
    result=RegQueryValueExW(key,name,nullptr,&out.type,nullptr,&size);
    if(result==ERROR_FILE_NOT_FOUND){RegCloseKey(key);return true;}
    if(result!=ERROR_SUCCESS||size>65536){RegCloseKey(key);return false;}
    out.data.resize(size);
    result=RegQueryValueExW(key,name,nullptr,&out.type,out.data.data(),&size);
    RegCloseKey(key);
    if(result!=ERROR_SUCCESS){out={};return false;}
    out.data.resize(size);out.exists=true;return true;
}
inline bool write(const std::wstring&path,const wchar_t*name,const Value&value) {
    HKEY key=nullptr;
    LONG result=value.exists?RegCreateKeyExW(HKEY_CURRENT_USER,path.c_str(),0,nullptr,0,KEY_SET_VALUE,nullptr,&key,nullptr):RegOpenKeyExW(HKEY_CURRENT_USER,path.c_str(),0,KEY_SET_VALUE,&key);
    if(!value.exists&&result==ERROR_FILE_NOT_FOUND)return true;
    if(result!=ERROR_SUCCESS)return false;
    result=value.exists?RegSetValueExW(key,name,0,value.type,value.data.data(),(DWORD)value.data.size()):RegDeleteValueW(key,name);
    RegCloseKey(key);
    return result==ERROR_SUCCESS||(!value.exists&&result==ERROR_FILE_NOT_FOUND);
}
inline Value textValue(const std::wstring&text) {
    Value out;out.exists=true;out.type=REG_SZ;out.data.resize((text.size()+1)*sizeof(wchar_t));
    std::memcpy(out.data.data(),text.c_str(),out.data.size());return out;
}
inline Value flagValue(bool enabled) {
    Value out;out.exists=true;out.type=REG_DWORD;out.data.resize(sizeof(DWORD));
    DWORD number=enabled?1:0;std::memcpy(out.data.data(),&number,sizeof(number));return out;
}
inline bool text(const Value&value,std::wstring&out) {
    out.clear();if(!value.exists)return true;
    if(value.type!=REG_SZ||value.data.size()<sizeof(wchar_t)||value.data.size()%sizeof(wchar_t))return false;
    std::vector<wchar_t>buffer(value.data.size()/sizeof(wchar_t));std::memcpy(buffer.data(),value.data.data(),value.data.size());
    if(buffer.back()!=0)return false;
    out.assign(buffer.data(),buffer.size()-1);return out.find(L'\0')==std::wstring::npos;
}
inline bool ownedExecutable(const std::wstring&path) {
    auto slash=path.find_last_of(L"\\/");auto name=path.substr(slash==std::wstring::npos?0:slash+1);
    return !_wcsicmp(name.c_str(),L"KIOControl.exe")||!_wcsicmp(name.c_str(),L"GalaxyControl.exe");
}
inline bool ownedCommand(const std::wstring&command) {
    if(command.empty()||command.front()!=L'"')return false;
    auto end=command.find(L'"',1);if(end==std::wstring::npos||!ownedExecutable(command.substr(1,end-1)))return false;
    auto args=command.substr(end+1);auto at=args.find_first_not_of(L" \t");
    return at!=std::wstring::npos&&args.substr(at)==L"--background";
}
inline std::wstring command(const std::wstring&exe) {
    if(exe.empty()||exe.size()>32700||exe.find_first_of(L"\"\r\n")!=std::wstring::npos||!ownedExecutable(exe))return {};
    auto result=L"\""+exe+L"\" --background";
    return result.size()<260?result:std::wstring(); // Windows Run command-line limit, including terminator.
}
inline std::wstring executable() {
    std::vector<wchar_t>buffer(32768);DWORD length=GetModuleFileNameW(nullptr,buffer.data(),(DWORD)buffer.size());
    return length&&length<buffer.size()?std::wstring(buffer.data(),length):std::wstring();
}
class Store {
    Locations locations;
public:
    explicit Store(Locations paths={}):locations(std::move(paths)){}
    bool snapshot(Snapshot&out) const {
        return read(locations.run,locations.name.c_str(),out.run)&&read(locations.approval,locations.name.c_str(),out.approval)&&read(locations.preference,L"StartAtLogin",out.preference);
    }
    bool restore(const Snapshot&state) const {
        bool a=write(locations.run,locations.name.c_str(),state.run);
        bool b=write(locations.approval,locations.name.c_str(),state.approval);
        bool c=write(locations.preference,L"StartAtLogin",state.preference);return a&&b&&c;
    }
    bool desired(const Snapshot&state,bool&enabled) const {
        if(state.preference.exists){
            if(state.preference.type!=REG_DWORD||state.preference.data.size()!=sizeof(DWORD))return false;
            DWORD flag=0;std::memcpy(&flag,state.preference.data.data(),sizeof(flag));if(flag>1)return false;
            enabled=flag!=0;return true;
        }
        std::wstring previous;if(!text(state.run,previous))return false;
        enabled=state.run.exists&&ownedCommand(previous);return true;
    }
    bool requested() const {Snapshot state;bool enabled=false;return snapshot(state)&&desired(state,enabled)&&enabled;}
    static bool blocked(const Value&approval) {
        if(!approval.exists)return false;
        // Unknown Windows states must not be presented as a working registration.
        if(approval.type!=REG_BINARY||approval.data.size()<sizeof(DWORD))return true;
        DWORD flag=0;std::memcpy(&flag,approval.data.data(),sizeof(flag));return flag!=2&&flag!=6;
    }
    const char* status(const std::wstring&exe) const {
        Snapshot state;bool enabled=false;std::wstring registered;
        if(!snapshot(state)||!desired(state,enabled)||!text(state.run,registered))return "error";
        if(!enabled)return "disabled";
        if(blocked(state.approval))return "blocked";
        auto expected=command(exe);
        return !expected.empty()&&!_wcsicmp(registered.c_str(),expected.c_str())?"enabled":"repair";
    }
    bool set(bool enabled,const std::wstring&exe) const {
        auto expected=command(exe);if(enabled&&expected.empty())return false;
        Snapshot before;if(!snapshot(before))return false;
        bool ok=write(locations.run,locations.name.c_str(),enabled?textValue(expected):Value{});
        // Windows may remember an old user-disabled item after its Run value is rewritten.
        // Clear ONLY this application's decision, and ONLY for this explicit Enable action.
        if(ok&&enabled)ok=write(locations.approval,locations.name.c_str(),{});
        if(ok)ok=write(locations.preference,L"StartAtLogin",flagValue(enabled));
        if(!ok)restore(before);
        return ok;
    }
    bool reconcile(const std::wstring&exe) const {
        Snapshot before;bool enabled=false;std::wstring registered;
        if(!snapshot(before)||!desired(before,enabled)||!text(before.run,registered))return false;
        auto expected=command(exe);if(enabled&&expected.empty())return false;
        if(before.run.exists&&!ownedCommand(registered))return false;
        bool ok=true;
        if(enabled&&_wcsicmp(registered.c_str(),expected.c_str()))ok=write(locations.run,locations.name.c_str(),textValue(expected));
        if(ok&&!enabled&&before.run.exists)ok=write(locations.run,locations.name.c_str(),{});
        if(ok&&!before.preference.exists)ok=write(locations.preference,L"StartAtLogin",flagValue(enabled));
        if(!ok)restore(before);
        return ok;
    }
};
}
