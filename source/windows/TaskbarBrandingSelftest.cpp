#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shlwapi.h>
#include <cstdlib>
#include <iostream>
#include "TaskbarBranding.h"
#define CHECK(value) do { if (!(value)) { std::cerr << "FAILED line " << __LINE__ << ": " << #value << "\n"; std::exit(1); } } while (0)

static std::wstring property(IPropertyStore* store, REFPROPERTYKEY key) {
    PROPVARIANT value = {};
    CHECK(SUCCEEDED(store->GetValue(key, &value)));
    CHECK(value.vt == VT_LPWSTR && value.pwszVal);
    std::wstring text = value.pwszVal;
    PropVariantClear(&value);
    return text;
}
static void shortcut(const std::wstring& path, const std::wstring& target) {
    IShellLinkW* link = nullptr;
    IPersistFile* file = nullptr;
    CHECK(SUCCEEDED(CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&link))));
    CHECK(SUCCEEDED(link->SetPath(target.c_str())));
    CHECK(SUCCEEDED(link->SetArguments(L"--background")));
    CHECK(SUCCEEDED(link->SetIconLocation(L"old-icon.ico", 0)));
    CHECK(SUCCEEDED(link->QueryInterface(IID_PPV_ARGS(&file))));
    CHECK(SUCCEEDED(file->Save(path.c_str(), TRUE)));
    file->Release(); link->Release();
}
int wmain(int argc, wchar_t** argv) {
    CHECK(argc == 3 && SUCCEEDED(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED)));
    std::wstring exe = argv[1], folder = argv[2];
    CreateDirectoryW(folder.c_str(), nullptr);
    auto ours = folder + L"\\KIO 테스트.lnk", other = folder + L"\\other.lnk";
    shortcut(ours, exe);
    shortcut(other, L"C:\\Windows\\System32\\notepad.exe");
    CHECK(KioTaskbar::updateOwnedShortcut(ours, exe));
    CHECK(!KioTaskbar::updateOwnedShortcut(other, exe));
    IShellLinkW* link = nullptr; IPersistFile* file = nullptr; IPropertyStore* store = nullptr;
    CHECK(SUCCEEDED(CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&link))));
    CHECK(SUCCEEDED(link->QueryInterface(IID_PPV_ARGS(&file))));
    CHECK(SUCCEEDED(file->Load(ours.c_str(), STGM_READ)));
    wchar_t icon[32768] = {}, target[32768] = {}, args[256] = {}; int index = -1;
    CHECK(SUCCEEDED(link->GetIconLocation(icon, 32768, &index)) && index == 0);
    CHECK(std::wstring(icon) + L",0" == KioTaskbar::iconResource(exe));
    CHECK(SUCCEEDED(link->GetPath(target, 32768, nullptr, SLGP_RAWPATH)) && exe == target);
    CHECK(SUCCEEDED(link->GetArguments(args, 256)) && std::wstring(args) == L"--background");
    CHECK(SUCCEEDED(link->QueryInterface(IID_PPV_ARGS(&store))));
    CHECK(property(store, PKEY_AppUserModel_ID) == KioTaskbar::identity);
    store->Release(); file->Release(); link->Release();
    CHECK(SUCCEEDED(SetCurrentProcessExplicitAppUserModelID(KioTaskbar::identity)));
    PWSTR id = nullptr;
    CHECK(SUCCEEDED(GetCurrentProcessExplicitAppUserModelID(&id)) && std::wstring(id) == KioTaskbar::identity);
    CoTaskMemFree(id);
    HWND window = CreateWindowW(L"STATIC", L"KIO branding test", WS_OVERLAPPEDWINDOW, 0, 0, 1, 1, nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
    CHECK(window && KioTaskbar::apply(window));
    CHECK(SUCCEEDED(SHGetPropertyStoreForWindow(window, IID_PPV_ARGS(&store))));
    CHECK(property(store, PKEY_AppUserModel_ID) == KioTaskbar::identity);
    CHECK(property(store, PKEY_AppUserModel_RelaunchIconResource) == KioTaskbar::iconResource(KioTaskbar::executable()));
    CHECK(property(store, PKEY_AppUserModel_RelaunchCommand) == L"\"" + KioTaskbar::executable() + L"\"");
    CHECK(property(store, PKEY_AppUserModel_RelaunchDisplayNameResource) == L"@" + KioTaskbar::executable() + L",-101");
    store->Release(); DestroyWindow(window);
    wchar_t display[256] = {};
    CHECK(SUCCEEDED(SHLoadIndirectString((L"@" + exe + L",-101").c_str(), display, 256, nullptr)));
    CHECK(std::wstring(display) == L"Bogo Tools");
    // Delete only test-created shortcuts, never the user's pinned items.
    DeleteFileW(ours.c_str()); DeleteFileW(other.c_str()); RemoveDirectoryW(folder.c_str());
    CoUninitialize();
    std::cout << "PASS: stable process/window identity; complete pin relaunch metadata; official ICO; exact-target pin migration; unrelated link excluded; target and arguments retained; display resource resolves\n";
}
