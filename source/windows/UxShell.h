#pragma once
#include <windows.h>
#include <string>
#include "LoginStartup.h"
constexpr UINT UX_TRAY_MESSAGE=WM_APP+31;
constexpr int UX_OPEN=3101,UX_CAPTURE=3102,UX_EXIT=3103,UX_STARTUP=3104,UX_SHARED=3105;
void UxInit(HWND,HINSTANCE,int);bool UxTrayAvailable();void UxRestoreTray();void UxDestroy();void UxTrayMenu();bool UxTrayEvent(LPARAM);bool UxStartupEnabled();bool UxToggleStartup();bool UxSetStartup(bool);
void UxSetIcon(HWND,int);void UxTooltip(HWND);void UxRefreshTooltips();

void UxReconcileStartup();const char* UxStartupStatus();
bool UxReadStartupSnapshot(KioLoginStartup::Snapshot&);bool UxRestoreStartupSnapshot(const KioLoginStartup::Snapshot&);
