#ifndef GALAXY_PHONE_TOOLS_PATH_H
#define GALAXY_PHONE_TOOLS_PATH_H
#include <stddef.h>
#include <wchar.h>

/* Joining never returns a truncated path. Shared by the native Windows panel
 * and host fixtures for moved folders, Unicode names and missing dependencies. */
static int GalaxyJoinToolPath(wchar_t *out, size_t cap, const wchar_t *root,
                             const wchar_t *suffix) {
    size_t a = wcslen(root), b = wcslen(suffix);
    while (a && (root[a-1] == L'\\' || root[a-1] == L'/')) --a;
    if (!cap || a + b + 1 >= cap) { if (cap) out[0] = 0; return 0; }
    wmemcpy(out, root, a); out[a] = L'\\';
    wmemcpy(out + a + 1, suffix, b + 1); return 1;
}
typedef int (*GalaxyToolFileCheck)(const wchar_t *, void *);
static const wchar_t *const GalaxyPhoneToolFiles[] = {
    L"adb.exe", L"scrcpy.exe", L"scrcpy-server", L"AdbWinApi.dll",
    L"AdbWinUsbApi.dll", L"SDL3.dll", L"avcodec-62.dll", L"avformat-62.dll",
    L"avutil-60.dll", L"swresample-6.dll", L"libusb-1.0.dll"
};
static int GalaxyPhoneToolsComplete(const wchar_t *folder, GalaxyToolFileCheck check,
                                   void *context) {
    wchar_t path[32768];
    for (size_t i = 0; i < sizeof(GalaxyPhoneToolFiles)/sizeof(*GalaxyPhoneToolFiles); ++i)
        if (!GalaxyJoinToolPath(path, sizeof(path)/sizeof(*path), folder, GalaxyPhoneToolFiles[i]) ||
            !check(path, context)) return 0;
    return 1;
}
static int GalaxyFindPhoneTools(const wchar_t *root, wchar_t *out, size_t cap,
                               GalaxyToolFileCheck check, void *context) {
    const wchar_t *suffixes[] = { L"tools\\scrcpy", L"Windows\\tools\\scrcpy", L"scrcpy" };
    for (size_t i = 0; i < sizeof(suffixes)/sizeof(*suffixes); ++i)
        if (GalaxyJoinToolPath(out, cap, root, suffixes[i]) &&
            GalaxyPhoneToolsComplete(out, check, context)) return 1;
    if (wcslen(root) < cap && GalaxyPhoneToolsComplete(root, check, context)) {
        wcscpy(out, root); return 1;
    }
    if (cap) out[0] = 0;
    return 0;
}
#endif
