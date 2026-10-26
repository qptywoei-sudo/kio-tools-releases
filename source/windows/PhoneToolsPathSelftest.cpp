#include "PhoneToolsPath.h"
#include <cassert>
#include <set>
#include <string>
#include <iostream>
using std::wstring;
static int exists(const wchar_t *p, void *ctx) {
    return static_cast<std::set<wstring>*>(ctx)->count(p) != 0;
}
static void populate(std::set<wstring>& paths, const wstring& folder) {
    for (auto name : GalaxyPhoneToolFiles) paths.insert(folder + L"\\" + name);
}
int main() {
    wchar_t out[32768]; std::set<wstring> paths;
    wstring root = L"C:\\Users\\홍길동\\Desktop\\GalaxyControl-20261005T014041Z-1-001\\GalaxyControl\\Windows";
    wstring tools = root + L"\\tools\\scrcpy";
    populate(paths, tools);
    assert(GalaxyFindPhoneTools(root.c_str(), out, 32768, exists, &paths));
    assert(out == tools);
    paths.erase(tools + L"\\scrcpy-server");
    assert(!GalaxyFindPhoneTools(root.c_str(), out, 32768, exists, &paths));
    assert(!out[0]);
    populate(paths, tools); paths.erase(tools + L"\\SDL3.dll");
    assert(!GalaxyFindPhoneTools(root.c_str(), out, 32768, exists, &paths));
    paths.clear(); populate(paths, L"D:\\GalaxyControl\\Windows\\tools\\scrcpy");
    assert(GalaxyFindPhoneTools(L"D:\\GalaxyControl", out, 32768, exists, &paths));
    assert(wstring(out) == L"D:\\GalaxyControl\\Windows\\tools\\scrcpy");
    assert(GalaxyFindPhoneTools(L"D:\\GalaxyControl\\Windows\\tools\\scrcpy", out, 32768, exists, &paths));
    wchar_t small[8] = {L'X'};
    assert(!GalaxyJoinToolPath(small, 8, L"C:\\folder", L"adb.exe") && !small[0]);
    assert(GalaxyJoinToolPath(out, 32768, L"C:\\folder\\", L"adb.exe"));
    assert(wstring(out) == L"C:\\folder\\adb.exe");
    wstring longRoot = L"C:\\" + wstring(290,L'a');
    assert(GalaxyJoinToolPath(out,32768,longRoot.c_str(),L"tools\\scrcpy\\scrcpy-server"));
    assert(wstring(out) == longRoot + L"\\tools\\scrcpy\\scrcpy-server");
    assert(!GalaxyJoinToolPath(out,260,longRoot.c_str(),L"adb.exe") && !out[0]);
    std::cout << "Phone tool path fixtures passed: moved Unicode folder, full root, direct scrcpy, missing server, missing DLL, trailing separator, bounded and long paths.\n";
}
