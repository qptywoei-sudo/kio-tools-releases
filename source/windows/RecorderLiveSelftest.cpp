#ifndef UNICODE
#define UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <string>
#include "WindowsRecorder.h"
static std::wstring output;static bool success=false,borderValid=true;static unsigned ticks=0;
static void verifyBorder(bool paused){
 HWND border=FindWindowW(L"KIORecordingBorder",nullptr);DWORD affinity=0;RECT rect={};bool valid=border&&IsWindowVisible(border)&&GetWindowRect(border,&rect)&&GetWindowDisplayAffinity(border,&affinity)&&affinity==0x11;
 if(valid){HDC dc=GetDC(border);COLORREF color=GetPixel(dc,1,1);ReleaseDC(border,dc);valid=color==(paused?RGB(239,68,68):RGB(34,197,94));HRGN region=CreateRectRgn(0,0,0,0);GetWindowRgn(border,region);valid=valid&&PtInRegion(region,1,1)&&!PtInRegion(region,(rect.right-rect.left)/2,(rect.bottom-rect.top)/2);DeleteObject(region);}
 borderValid=borderValid&&valid;std::printf("border %s=%s\n",paused?"red":"green",valid?"PASS":"FAIL");
}
static LRESULT CALLBACK testProc(HWND window,UINT message,WPARAM w,LPARAM l){
 if(message==Recording::StartedMessage){std::puts("started");verifyBorder(false);SetTimer(window,1,1000,nullptr);return 0;}
 if(message==WM_TIMER){++ticks;if(ticks==1){std::printf("pause=%d\n",Recording::Pause());verifyBorder(true);}if(ticks==2){std::printf("resume=%d\n",Recording::Resume());verifyBorder(false);}if(ticks==4){Recording::Stop();KillTimer(window,1);}return 0;}
 if(message==Recording::FinishedMessage){auto result=(Recording::Result*)l;success=result->ok&&result->frames>3&&borderValid;std::printf("finished ok=%d hr=0x%08lx frames=%lu elapsed=%llu\n",result->ok,(unsigned long)result->error,result->frames,Recording::Elapsed());delete result;Recording::ClearIndicator();PostQuitMessage(success?0:2);return 0;}
 return DefWindowProcW(window,message,w,l);
}
int wmain(int argc,wchar_t**argv){
 if(argc<2)return 64;output=argv[1];SetProcessDPIAware();WNDCLASSW type={};type.lpfnWndProc=testProc;type.hInstance=GetModuleHandleW(nullptr);type.lpszClassName=L"KIORecorderLiveSelftest";RegisterClassW(&type);HWND window=CreateWindowW(type.lpszClassName,L"KIO recorder test",0,0,0,0,0,HWND_MESSAGE,nullptr,type.hInstance,nullptr);
 RECT rect={40,40,680,520};if(argc>2){MONITORINFO monitor={sizeof(monitor)};GetMonitorInfoW(MonitorFromPoint(POINT{0,0},MONITOR_DEFAULTTOPRIMARY),&monitor);rect=monitor.rcMonitor;}
 if(!Recording::Start(window,rect,output,20)){std::puts("start failed");return 1;}
 MSG msg;while(GetMessageW(&msg,nullptr,0,0)>0){TranslateMessage(&msg);DispatchMessageW(&msg);}Recording::WaitForFinish();DestroyWindow(window);return success?0:2;
}
