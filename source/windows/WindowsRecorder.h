#pragma once
#include <windows.h>
#include <string>
namespace Recording {
constexpr UINT FinishedMessage=WM_APP+70,StartedMessage=WM_APP+71;
struct Result{bool ok;HRESULT error;std::wstring path;DWORD frames;};
bool Start(HWND owner,RECT region,const std::wstring&path,int fps=20,int width=0,int scalePercent=100);
void Stop();bool Pause();bool Resume();bool Paused();bool Active();ULONGLONG Elapsed();void WaitForFinish();
void ClearIndicator();
}
