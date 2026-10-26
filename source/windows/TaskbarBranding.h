#pragma once
#include <windows.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <propkey.h>
#include <string>

// Version-independent identity groups the editor and the tool host together.
// A content-named ICO avoids Explorer's cached icon for the old EXE path.
namespace KioTaskbar {
inline constexpr const wchar_t* identity = L"KIO.Tools.Desktop";
inline constexpr const wchar_t* artwork = L"\\resources\\bogo-tools-app-6fc46773.ico";
inline std::wstring executable() {
    wchar_t path[32768] = {};
    DWORD size = GetModuleFileNameW(nullptr, path, 32768);
    return size && size < 32768 ? std::wstring(path, size) : std::wstring();
}
inline std::wstring iconResource(const std::wstring& exe) {
    auto slash = exe.find_last_of(L"\\/");
    auto icon = slash == std::wstring::npos ? std::wstring() : exe.substr(0, slash) + artwork;
    DWORD attributes = icon.empty() ? INVALID_FILE_ATTRIBUTES : GetFileAttributesW(icon.c_str());
    return attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY) ? icon + L",0" : exe + L",0";
}
inline HRESULT stringProperty(IPropertyStore* store, REFPROPERTYKEY key, const std::wstring& value) {
    PROPVARIANT property = {};
    property.vt = VT_LPWSTR;
    property.pwszVal = const_cast<wchar_t*>(value.c_str());
    return store->SetValue(key, property);
}
inline bool apply(HWND window) {
    auto exe = executable();
    if (exe.empty()) return false;
    IPropertyStore* store = nullptr;
    if (FAILED(SHGetPropertyStoreForWindow(window, IID_PPV_ARGS(&store)))) return false;
    bool ok = SUCCEEDED(stringProperty(store, PKEY_AppUserModel_RelaunchCommand, L"\"" + exe + L"\""));
    ok = SUCCEEDED(stringProperty(store, PKEY_AppUserModel_RelaunchDisplayNameResource, L"@" + exe + L",-101")) && ok;
    ok = SUCCEEDED(stringProperty(store, PKEY_AppUserModel_RelaunchIconResource, iconResource(exe))) && ok;
    // Set the ID last, after the complete relaunch description is available.
    ok = SUCCEEDED(stringProperty(store, PKEY_AppUserModel_ID, identity)) && ok;
    store->Release();
    return ok;
}
inline bool updateOwnedShortcut(const std::wstring& shortcut, const std::wstring& exe) {
    IShellLinkW* link = nullptr;
    if (FAILED(CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&link)))) return false;
    IPersistFile* file = nullptr;
    IPropertyStore* properties = nullptr;
    bool updated = false;
    if (SUCCEEDED(link->QueryInterface(IID_PPV_ARGS(&file))) && SUCCEEDED(file->Load(shortcut.c_str(), STGM_READWRITE))) {
        wchar_t target[32768] = {};
        // Only links to this exact installed executable may be migrated.
        if (SUCCEEDED(link->GetPath(target, 32768, nullptr, SLGP_RAWPATH)) && !_wcsicmp(target, exe.c_str()) &&
            SUCCEEDED(link->QueryInterface(IID_PPV_ARGS(&properties)))) {
            auto icon = iconResource(exe);
            auto comma = icon.rfind(L',');
            if (comma != std::wstring::npos) icon.resize(comma);
            updated = SUCCEEDED(stringProperty(properties, PKEY_AppUserModel_ID, identity)) &&
                SUCCEEDED(properties->Commit()) && SUCCEEDED(link->SetIconLocation(icon.c_str(), 0)) &&
                SUCCEEDED(link->SetDescription(L"Bogo Tools")) && SUCCEEDED(file->Save(shortcut.c_str(), TRUE));
            if (updated) SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW | SHCNF_FLUSHNOWAIT, shortcut.c_str(), nullptr);
        }
    }
    if (properties) properties->Release();
    if (file) file->Release();
    link->Release();
    return updated;
}
inline void migratePinnedShortcuts(const std::wstring& exe) {
    wchar_t roaming[MAX_PATH] = {};
    if (FAILED(SHGetFolderPathW(nullptr, CSIDL_APPDATA, nullptr, SHGFP_TYPE_CURRENT, roaming))) return;
    std::wstring folder = std::wstring(roaming) + L"\\Microsoft\\Internet Explorer\\Quick Launch\\User Pinned\\TaskBar\\";
    WIN32_FIND_DATAW entry = {};
    HANDLE search = FindFirstFileW((folder + L"*.lnk").c_str(), &entry);
    if (search == INVALID_HANDLE_VALUE) return;
    do {
        if (!(entry.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT)))
            updateOwnedShortcut(folder + entry.cFileName, exe);
    } while (FindNextFileW(search, &entry));
    FindClose(search);
}
inline void initialize() {
    SetCurrentProcessExplicitAppUserModelID(identity);
    auto exe = executable();
    if (exe.empty()) return;
    migratePinnedShortcuts(exe);
    SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW | SHCNF_FLUSHNOWAIT, exe.c_str(), nullptr);
}
}
