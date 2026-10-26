#define UNICODE
#define NOMINMAX
#include "CaptureBackdrop.h"
#include <cstdio>
int main(){
 SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
 WNDCLASSW wc={};wc.hInstance=GetModuleHandleW(nullptr);wc.lpfnWndProc=DefWindowProcW;wc.lpszClassName=L"KIOCaptureBackdropFixture";wc.hbrBackground=CreateSolidBrush(RGB(32,190,90));RegisterClassW(&wc);
 HWND background=CreateWindowExW(WS_EX_TOPMOST|WS_EX_TOOLWINDOW,wc.lpszClassName,L"KIO capture rendering test",WS_POPUP|WS_VISIBLE,60,80,640,400,nullptr,nullptr,wc.hInstance,nullptr);
 WNDCLASSW fg=wc;fg.lpszClassName=L"KIOCaptureOccluderFixture";fg.hbrBackground=CreateSolidBrush(RGB(230,30,180));RegisterClassW(&fg);
 HWND app=CreateWindowExW(WS_EX_TOPMOST|WS_EX_TOOLWINDOW,fg.lpszClassName,L"KIO capture occluder",WS_POPUP,80,100,500,280,nullptr,nullptr,wc.hInstance,nullptr);
 UpdateWindow(background);DwmFlush();int failures=0;
 for(int i=0;i<12;i++){
  ShowWindow(app,SW_SHOWNOACTIVATE);SetWindowPos(app,HWND_TOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);UpdateWindow(app);DwmFlush();Sleep(25);
  if(!CaptureBackdrop::hide({app}))failures++;
  HDC screen=GetDC(nullptr);for(int y=120;y<340;y+=31)for(int x=100;x<550;x+=41)if(GetPixel(screen,x,y)!=RGB(32,190,90))failures++;ReleaseDC(nullptr,screen);
 }
 DestroyWindow(app);DestroyWindow(background);DeleteObject(wc.hbrBackground);DeleteObject(fg.hbrBackground);
 std::printf("capture compositor hide: 12 repetitions, %d unexpected pixels/visibility failures\n",failures);return failures?1:0;
}
