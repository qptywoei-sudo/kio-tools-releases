#ifndef UNICODE
#define UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <objbase.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <vector>
#include <algorithm>
#include "WindowsRecorder.h"
#include "RecorderModel.h"
namespace Recording {
static HANDLE stopEvent=nullptr,resumeEvent=nullptr,threadHandle=nullptr;static HWND ownerWindow;static LONG active;static SRWLOCK clockLock=SRWLOCK_INIT;static RecorderModel::Timeline clock;
static HWND indicator=nullptr;
static LRESULT CALLBACK indicatorProc(HWND window,UINT message,WPARAM w,LPARAM l){
 if(message==WM_NCHITTEST)return HTTRANSPARENT;
 if(message==WM_PAINT){PAINTSTRUCT paint;HDC dc=BeginPaint(window,&paint);RECT bounds;GetClientRect(window,&bounds);HBRUSH brush=CreateSolidBrush(Paused()?RGB(239,68,68):RGB(34,197,94));FillRect(dc,&bounds,brush);DeleteObject(brush);EndPaint(window,&paint);return 0;}
 return DefWindowProcW(window,message,w,l);
}
void ClearIndicator(){if(indicator){DestroyWindow(indicator);indicator=nullptr;}}
static void showIndicator(RECT rect){
 ClearIndicator();HINSTANCE instance=GetModuleHandleW(nullptr);WNDCLASSW type={};type.lpfnWndProc=indicatorProc;type.hInstance=instance;type.lpszClassName=L"KIORecordingBorder";RegisterClassW(&type);
 int width=rect.right-rect.left,height=rect.bottom-rect.top,border=4;
 indicator=CreateWindowExW(WS_EX_TOPMOST|WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE|WS_EX_TRANSPARENT,type.lpszClassName,L"Bogo Tools 녹화 영역",WS_POPUP,rect.left,rect.top,width,height,nullptr,nullptr,instance,nullptr);
 if(!indicator)return;HRGN outer=CreateRectRgn(0,0,width,height),inner=CreateRectRgn(border,border,std::max(border,width-border),std::max(border,height-border));CombineRgn(outer,outer,inner,RGN_DIFF);DeleteObject(inner);if(!SetWindowRgn(indicator,outer,FALSE))DeleteObject(outer);
 SetWindowDisplayAffinity(indicator,0x11);ShowWindow(indicator,SW_SHOWNOACTIVATE);UpdateWindow(indicator);
}
struct Work{RECT rect;std::wstring path;int fps,width,height;};
static void freezeClock(){AcquireSRWLockExclusive(&clockLock);clock.stop(GetTickCount64());ReleaseSRWLockExclusive(&clockLock);}
struct MediaAPI{
 HMODULE platform=nullptr,readwrite=nullptr;
 decltype(&MFStartup) startup=nullptr;decltype(&MFShutdown) shutdown=nullptr;
 decltype(&MFCreateAttributes) attributes=nullptr;decltype(&MFCreateMediaType) type=nullptr;
 decltype(&MFCreateMemoryBuffer) buffer=nullptr;decltype(&MFCreateSample) sample=nullptr;
 decltype(&MFCreateSinkWriterFromURL) writer=nullptr;
 bool load(){platform=LoadLibraryExW(L"mfplat.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);readwrite=LoadLibraryExW(L"mfreadwrite.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
 #define RESOLVE(member,symbol,module) member=(decltype(member))GetProcAddress(module,#symbol)
 if(platform){RESOLVE(startup,MFStartup,platform);RESOLVE(shutdown,MFShutdown,platform);RESOLVE(attributes,MFCreateAttributes,platform);RESOLVE(type,MFCreateMediaType,platform);RESOLVE(buffer,MFCreateMemoryBuffer,platform);RESOLVE(sample,MFCreateSample,platform);}if(readwrite)RESOLVE(writer,MFCreateSinkWriterFromURL,readwrite);
 #undef RESOLVE
 return startup&&shutdown&&attributes&&type&&buffer&&sample&&writer;}
 ~MediaAPI(){if(readwrite)FreeLibrary(readwrite);if(platform)FreeLibrary(platform);}
};
template<class T>static void release(T*&p){if(p){p->Release();p=nullptr;}}
static HRESULT media(MediaAPI&api,IMFMediaType**t,const GUID&sub,int w,int h,int fps,bool output){HRESULT hr=api.type(t);if(FAILED(hr))return hr;
#define SET(call) if(SUCCEEDED(hr))hr=(call)
SET((*t)->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video));SET((*t)->SetGUID(MF_MT_SUBTYPE,sub));SET((*t)->SetUINT32(MF_MT_INTERLACE_MODE,MFVideoInterlace_Progressive));SET(MFSetAttributeSize(*t,MF_MT_FRAME_SIZE,w,h));SET(MFSetAttributeRatio(*t,MF_MT_FRAME_RATE,fps,1));SET(MFSetAttributeRatio(*t,MF_MT_PIXEL_ASPECT_RATIO,1,1));if(output){SET((*t)->SetUINT32(MF_MT_AVG_BITRATE,std::max(2000000,std::min(16000000,w*h*4))));SET((*t)->SetUINT32(MF_MT_MPEG2_PROFILE,77));}else SET((*t)->SetUINT32(MF_MT_DEFAULT_STRIDE,w*4));
#undef SET
return hr;}
static DWORD WINAPI worker(void*data){
 Work*work=(Work*)data;int w=work->width,h=work->height,sourceWidth=work->rect.right-work->rect.left,sourceHeight=work->rect.bottom-work->rect.top;
 HRESULT hr=CoInitializeEx(nullptr,COINIT_MULTITHREADED);bool com=SUCCEEDED(hr);MediaAPI api;if(api.load())hr=api.startup(MF_VERSION,MFSTARTUP_FULL);else hr=HRESULT_FROM_WIN32(ERROR_MOD_NOT_FOUND);bool mf=SUCCEEDED(hr);
 IMFSinkWriter*writer=nullptr;IMFMediaType*out=nullptr,*in=nullptr;IMFAttributes*attributes=nullptr;DWORD stream=0,frames=0;
 if(SUCCEEDED(hr))hr=api.attributes(&attributes,1);if(SUCCEEDED(hr))hr=attributes->SetUINT32(MF_READWRITE_ENABLE_HARDWARE_TRANSFORMS,TRUE);
 if(SUCCEEDED(hr))hr=api.writer(work->path.c_str(),nullptr,attributes,&writer);if(SUCCEEDED(hr))hr=media(api,&out,MFVideoFormat_H264,w,h,work->fps,true);
 if(SUCCEEDED(hr))hr=writer->AddStream(out,&stream);if(SUCCEEDED(hr))hr=media(api,&in,MFVideoFormat_RGB32,w,h,work->fps,false);
 if(SUCCEEDED(hr))hr=writer->SetInputMediaType(stream,in,nullptr);if(SUCCEEDED(hr))hr=writer->BeginWriting();
 HDC screen=GetDC(nullptr),memory=screen?CreateCompatibleDC(screen):nullptr;BITMAPINFO info={};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
 info.bmiHeader.biWidth=w;info.bmiHeader.biHeight=-h;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
 void*pixels=nullptr;HBITMAP bitmap=memory?CreateDIBSection(screen,&info,DIB_RGB_COLORS,&pixels,nullptr,0):nullptr;HGDIOBJ old=bitmap?SelectObject(memory,bitmap):nullptr;
 if(!bitmap||!old||old==HGDI_ERROR)hr=E_OUTOFMEMORY;if(memory){SetStretchBltMode(memory,HALFTONE);SetBrushOrgEx(memory,0,0,nullptr);}
 ULONGLONG initialVideoTime=Elapsed();
 while(SUCCEEDED(hr)&&WaitForSingleObject(stopEvent,0)!=WAIT_OBJECT_0){
  if(Paused()){HANDLE events[]={stopEvent,resumeEvent};WaitForMultipleObjects(2,events,FALSE,INFINITE);continue;}
  ULONGLONG frameStart=GetTickCount64(),videoTime=Elapsed()-initialVideoTime;
  BOOL copied=(w==sourceWidth&&h==sourceHeight)?BitBlt(memory,0,0,w,h,screen,work->rect.left,work->rect.top,SRCCOPY|CAPTUREBLT):StretchBlt(memory,0,0,w,h,screen,work->rect.left,work->rect.top,sourceWidth,sourceHeight,SRCCOPY|CAPTUREBLT);
  if(!copied){DWORD error=GetLastError();hr=error?HRESULT_FROM_WIN32(error):E_FAIL;break;}
  IMFMediaBuffer*buffer=nullptr;IMFSample*sample=nullptr;BYTE*target=nullptr;hr=api.buffer(w*h*4,&buffer);if(SUCCEEDED(hr))hr=buffer->Lock(&target,nullptr,nullptr);
  if(SUCCEEDED(hr)){memcpy(target,pixels,(size_t)w*h*4);buffer->Unlock();hr=buffer->SetCurrentLength(w*h*4);}if(SUCCEEDED(hr))hr=api.sample(&sample);
  if(SUCCEEDED(hr))hr=sample->AddBuffer(buffer);if(SUCCEEDED(hr))hr=sample->SetSampleTime(videoTime*10000);if(SUCCEEDED(hr))hr=sample->SetSampleDuration(10000000/work->fps);
  if(SUCCEEDED(hr))hr=writer->WriteSample(stream,sample);release(sample);release(buffer);if(SUCCEEDED(hr)){frames++;if(frames==1)PostMessageW(ownerWindow,StartedMessage,0,0);}
  if(SUCCEEDED(hr)){DWORD used=(DWORD)(GetTickCount64()-frameStart),interval=RecorderModel::frameInterval(frames,work->fps);if(used<interval)WaitForSingleObject(stopEvent,interval-used);}
 }
 freezeClock();if(writer){HRESULT finalized=writer->Finalize();if(SUCCEEDED(hr))hr=finalized;}
 if(old&&old!=HGDI_ERROR)SelectObject(memory,old);if(bitmap)DeleteObject(bitmap);if(memory)DeleteDC(memory);if(screen)ReleaseDC(nullptr,screen);
 release(writer);release(out);release(in);release(attributes);if(mf)api.shutdown();if(com)CoUninitialize();bool ok=SUCCEEDED(hr)&&frames>0;
 if(!ok)DeleteFileW(work->path.c_str());auto result=new Result{ok,hr,work->path,frames};delete work;InterlockedExchange(&active,0);
 if(!PostMessageW(ownerWindow,FinishedMessage,0,(LPARAM)result))delete result;return 0;
}
static void closeEvents(){if(stopEvent){CloseHandle(stopEvent);stopEvent=nullptr;}if(resumeEvent){CloseHandle(resumeEvent);resumeEvent=nullptr;}}
bool Start(HWND owner,RECT rect,const std::wstring&path,int fps,int width,int scalePercent){
 if(fps<5||fps>60||Active())return false;auto size=RecorderModel::outputSize(rect.right-rect.left,rect.bottom-rect.top,width,scalePercent);if(!size.valid)return false;
 if(threadHandle){CloseHandle(threadHandle);threadHandle=nullptr;}closeEvents();
 HANDLE reserved=CreateFileW(path.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);if(reserved==INVALID_HANDLE_VALUE)return false;CloseHandle(reserved);
 stopEvent=CreateEventW(nullptr,TRUE,FALSE,nullptr);resumeEvent=CreateEventW(nullptr,TRUE,TRUE,nullptr);if(!stopEvent||!resumeEvent){closeEvents();DeleteFileW(path.c_str());return false;}
 ownerWindow=owner;AcquireSRWLockExclusive(&clockLock);clock.start(GetTickCount64());ReleaseSRWLockExclusive(&clockLock);InterlockedExchange(&active,1);
 auto work=new Work{rect,path,fps,size.width,size.height};threadHandle=CreateThread(nullptr,0,worker,work,0,nullptr);
 if(!threadHandle){DeleteFileW(path.c_str());delete work;freezeClock();InterlockedExchange(&active,0);closeEvents();return false;}showIndicator(rect);return true;
}
void Stop(){if(stopEvent)SetEvent(stopEvent);freezeClock();if(resumeEvent)SetEvent(resumeEvent);if(indicator)ShowWindow(indicator,SW_HIDE);}
bool Pause(){if(!Active())return false;AcquireSRWLockExclusive(&clockLock);bool ok=!clock.stopped;if(ok){clock.pause(GetTickCount64());if(resumeEvent)ResetEvent(resumeEvent);}ReleaseSRWLockExclusive(&clockLock);if(indicator)RedrawWindow(indicator,nullptr,nullptr,RDW_INVALIDATE|RDW_UPDATENOW);return ok;}
bool Resume(){if(!Active())return false;AcquireSRWLockExclusive(&clockLock);bool ok=!clock.stopped;if(ok){clock.resume(GetTickCount64());if(resumeEvent)SetEvent(resumeEvent);}ReleaseSRWLockExclusive(&clockLock);if(indicator)RedrawWindow(indicator,nullptr,nullptr,RDW_INVALIDATE|RDW_UPDATENOW);return ok;}
bool Paused(){AcquireSRWLockShared(&clockLock);bool paused=clock.paused;ReleaseSRWLockShared(&clockLock);return paused;}
bool Active(){return InterlockedCompareExchange(&active,0,0)!=0;}
ULONGLONG Elapsed(){AcquireSRWLockShared(&clockLock);auto elapsed=clock.elapsed(GetTickCount64());ReleaseSRWLockShared(&clockLock);return elapsed;}
void WaitForFinish(){Stop();if(threadHandle){WaitForSingleObject(threadHandle,INFINITE);CloseHandle(threadHandle);threadHandle=nullptr;}closeEvents();ClearIndicator();}
}
