#ifndef UNICODE
#define UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>
#include <shlwapi.h>
#include <objbase.h>
#include <commctrl.h>
#include <string>
#include <algorithm>
#include <set>
#include "webview2/WebView2.h"
#include "SharedHost.h"
#include "AgentEndpoint.h"
#include "NativeBridge.h"
#include "I18N.h"
#include "AppIcon.h"
#include "TaskbarBranding.h"
#include "UxShell.h"
#include "SharedHostPolicy.h"
#include "CaptureBackdrop.h"
#include "StartupSplash.h"
using std::wstring;
using J=nlohmann::json;
static HWND host,notice,retryButton,runtimeButton;
static HINSTANCE app;
static HMODULE loader;
static ICoreWebView2Controller*controller;
static ICoreWebView2*core;
static unsigned generation=0;
static unsigned short agentPort=0;
static bool pageReady=false,uiReady=false,creating=false,navigationStarted=false;
static SharedHostPolicy::CaptureVisibility captureVisibility;
static WINDOWPLACEMENT capturePlacement={sizeof(WINDOWPLACEMENT)};
static bool capturePlacementSaved=false;
static int restoreShowCmd=SW_RESTORE;
static ULONGLONG lastShortcutTick=0;static double shortcutStartedAt=0;
static std::string lastShortcutName;
static std::string queuedCategory,queuedShortcut;
static HFONT hostFont;

static bool local(const wchar_t*uri){
 if(!uri||!AgentEndpoint::validPort(agentPort))return false;
 for(auto name:{L"127.0.0.1",L"localhost"}){
  wstring prefix=L"http://"+wstring(name)+L":"+std::to_wstring(agentPort)+L"/";
  if(wcsncmp(uri,prefix.c_str(),prefix.size())==0)return true;
 }
 return false;
}
static bool trustedTools(const wchar_t*uri){
 if(!uri||!AgentEndpoint::validPort(agentPort))return false;
 wstring value=uri;for(wchar_t c:value)if(c>127)return false;
 return SharedHostPolicy::toolsSource(std::string(value.begin(),value.end()),"http://127.0.0.1:"+std::to_string(agentPort));
}
static bool external(const wchar_t*uri){return uri&&(wcsncmp(uri,L"https://",8)==0||wcsncmp(uri,L"http://",7)==0);}
template<class I>class Handler:public I{
 volatile LONG refs=1;const IID&id;
 public:
 Handler(const IID&i):id(i){}
 HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void**out)override{
  if(!out)return E_POINTER;*out=nullptr;
  if(IsEqualIID(iid,IID_IUnknown)||IsEqualIID(iid,id)){*out=static_cast<I*>(this);AddRef();return S_OK;}
  return E_NOINTERFACE;
 }
 ULONG STDMETHODCALLTYPE AddRef()override{return InterlockedIncrement(&refs);}
 ULONG STDMETHODCALLTYPE Release()override{ULONG n=InterlockedDecrement(&refs);if(!n)delete this;return n;}
 virtual ~Handler()=default;
};
static int chrome(int n){return MulDiv(n,host?GetDpiForWindow(host):96,96);}
static void bounds(){
 if(!host)return;RECT r;GetClientRect(host,&r);
 int width=std::min<int>(chrome(500),std::max(1L,r.right-chrome(40))),left=(r.right-width)/2,top=std::min(r.bottom-chrome(140),r.bottom/2+chrome(170));
 if(notice)MoveWindow(notice,left,top,width,chrome(62),TRUE);
 if(retryButton)MoveWindow(retryButton,(r.right-chrome(130))/2,top+chrome(70),chrome(130),chrome(38),TRUE);
 if(runtimeButton)MoveWindow(runtimeButton,(r.right-chrome(210))/2,top+chrome(114),chrome(210),chrome(38),TRUE);
 if(controller)controller->put_Bounds(r);
}
static void rememberCapturePlacement(){
 if(capturePlacementSaved||!host)return;capturePlacement.length=sizeof(capturePlacement);
 capturePlacementSaved=GetWindowPlacement(host,&capturePlacement)!=FALSE;
 if(capturePlacementSaved&&!IsWindowVisible(host)&&restoreShowCmd==SW_SHOWMAXIMIZED)capturePlacement.showCmd=SW_SHOWMAXIMIZED;
}
static void restoreCapturePlacement(bool visible){
 if(!capturePlacementSaved||!host)return;
 restoreShowCmd=capturePlacement.showCmd==SW_SHOWMAXIMIZED?SW_SHOWMAXIMIZED:SW_RESTORE;
 auto placement=capturePlacement;placement.showCmd=visible?(restoreShowCmd==SW_SHOWMAXIMIZED?SW_SHOWMAXIMIZED:SW_SHOWNOACTIVATE):SW_HIDE;
 SetWindowPlacement(host,&placement);capturePlacementSaved=false;
}
static void fitCaptureWindow(const J&value){
 if(!captureVisibility.pending||!host||!SharedHostPolicy::captureFit(value))return;
 rememberCapturePlacement();MONITORINFO monitor={sizeof(MONITORINFO)};
 if(!GetMonitorInfoW(MonitorFromWindow(host,MONITOR_DEFAULTTONEAREST),&monitor))return;
 RECT frame={0,0,0,0};AdjustWindowRectExForDpi(&frame,(DWORD)GetWindowLongPtrW(host,GWL_STYLE),FALSE,(DWORD)GetWindowLongPtrW(host,GWL_EXSTYLE),GetDpiForWindow(host));
 const int margin=chrome(16),extraWidth=frame.right-frame.left+chrome(24),extraHeight=frame.bottom-frame.top+chrome(value["chromeHeight"].get<int>());
 const auto size=SharedHostPolicy::fitCaptureSize(chrome(value["width"].get<int>()),chrome(value["height"].get<int>()),extraWidth,extraHeight,monitor.rcWork.right-monitor.rcWork.left-margin*2,monitor.rcWork.bottom-monitor.rcWork.top-margin*2,chrome(420),chrome(260));
 if(size.width<=0||size.height<=0)return;
 if(IsZoomed(host))ShowWindow(host,SW_RESTORE);
 SetWindowPos(host,nullptr,monitor.rcWork.left+(monitor.rcWork.right-monitor.rcWork.left-size.width)/2,monitor.rcWork.top+(monitor.rcWork.bottom-monitor.rcWork.top-size.height)/2,size.width,size.height,SWP_NOZORDER|SWP_NOACTIVATE);
}
static void show(){if(host&&IsWindow(host)){I18NLocalizeTree(host);ShowWindow(host,captureVisibility.pending?SW_RESTORE:restoreShowCmd);if(!captureVisibility.pending)restoreShowCmd=SW_RESTORE;SetForegroundWindow(host);if(controller)controller->MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);}}
static void failed(const wchar_t*text=L"프로그램 화면을 열지 못했습니다. 다시 시도해 주세요.",bool runtime=false){
 pageReady=false;uiReady=false;creating=false;navigationStarted=false;
 if(!host||!IsWindow(host))return;
 if(controller)controller->put_IsVisible(FALSE);
 GalaxySetText(notice,text);ShowWindow(notice,SW_SHOW);ShowWindow(retryButton,SW_SHOW);ShowWindow(runtimeButton,runtime?SW_SHOW:SW_HIDE);bounds();KioStartup::resume(host);InvalidateRect(host,nullptr,FALSE);
}
static void completeCapture(const std::string&action){
 if(action=="captureStarted"){rememberCapturePlacement();captureVisibility.started(host&&IsWindowVisible(host));CaptureBackdrop::hide({host});return;}
 bool visible=false;if(!captureVisibility.finish(action,visible))return;
 if(action=="captureReady"){show();return;}
 if(host&&IsWindow(host)){ShowWindow(host,visible?SW_SHOWNOACTIVATE:SW_HIDE);restoreCapturePlacement(visible);}
}
static bool categoryAllowed(const std::string&s){
 return SharedHostPolicy::category(s);
}
static bool shortcutAllowed(const std::string&s){return !SharedHostPolicy::shortcut(s).empty();}
static void emitJson(const wchar_t*event,const J&value){
 if(!core||!pageReady||!uiReady)return;
 std::string json=value.dump();
 wstring script=L"window.dispatchEvent(new CustomEvent('"+wstring(event)+L"',{detail:"+wstring(json.begin(),json.end())+L"}));";
 core->ExecuteScript(script.c_str(),nullptr);
}
static void emit(const wchar_t*event,const char*key,const std::string&value){emitJson(event,J{{key,value}});}
static bool copyUnicodeText(const std::string&text){
 int count=text.empty()?0:MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),(int)text.size(),nullptr,0);
 if((!text.empty()&&count<=0)||count>12000)return false;
 HGLOBAL memory=GlobalAlloc(GMEM_MOVEABLE,((size_t)count+1)*sizeof(wchar_t));if(!memory)return false;
 auto content=(wchar_t*)GlobalLock(memory);if(!content){GlobalFree(memory);return false;}
 bool decoded=!count||MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),(int)text.size(),content,count)==count;
 content[count]=0;GlobalUnlock(memory);if(!decoded){GlobalFree(memory);return false;}
 if(!OpenClipboard(host)){GlobalFree(memory);return false;}
 bool copied=EmptyClipboard()&&SetClipboardData(CF_UNICODETEXT,memory)!=nullptr;
 CloseClipboard();if(!copied)GlobalFree(memory);return copied;
}
static void flushCommands(){
 if(!core||!pageReady||!uiReady)return;
 if(!queuedCategory.empty()){std::string category=queuedCategory;queuedCategory.clear();emit(L"galaxycontrol:navigate","category",category);}
 if(!queuedShortcut.empty()){std::string shortcut=queuedShortcut;queuedShortcut.clear();emitJson(L"galaxycontrol:shortcut",J{{"name",shortcut},{"startedAt",shortcutStartedAt}});}
}
class Navigation:public Handler<ICoreWebView2NavigationStartingEventHandler>{
 public:Navigation():Handler(IID_ICoreWebView2NavigationStartingEventHandler){}
 HRESULT STDMETHODCALLTYPE Invoke(ICoreWebView2*,ICoreWebView2NavigationStartingEventArgs*a)override{
  LPWSTR uri=nullptr;BOOL user=FALSE;a->get_Uri(&uri);a->get_IsUserInitiated(&user);
  if(!local(uri)){a->put_Cancel(TRUE);if(user&&external(uri))ShellExecuteW(host,L"open",uri,nullptr,nullptr,SW_SHOWNORMAL);}
  else if(trustedTools(uri)){pageReady=false;uiReady=false;}
  CoTaskMemFree(uri);return S_OK;
 }
};
class NavigationDone:public Handler<ICoreWebView2NavigationCompletedEventHandler>{
 unsigned epoch;
 public:NavigationDone(unsigned g):Handler(IID_ICoreWebView2NavigationCompletedEventHandler),epoch(g){}
 HRESULT STDMETHODCALLTYPE Invoke(ICoreWebView2*,ICoreWebView2NavigationCompletedEventArgs*a)override{
  if(epoch!=generation||!IsWindow(host))return S_OK;
  BOOL ok=FALSE;a->get_IsSuccess(&ok);creating=false;if(!ok){failed();return S_OK;}
  pageReady=true;NativeAgent::StartupStage("navigationReady");if(controller)controller->put_IsVisible(TRUE);KillTimer(host,KioStartup::timer);ShowWindow(notice,SW_HIDE);ShowWindow(retryButton,SW_HIDE);ShowWindow(runtimeButton,SW_HIDE);if(uiReady)flushCommands();return S_OK;
 }
};
class NewWindow:public Handler<ICoreWebView2NewWindowRequestedEventHandler>{
 public:NewWindow():Handler(IID_ICoreWebView2NewWindowRequestedEventHandler){}
 HRESULT STDMETHODCALLTYPE Invoke(ICoreWebView2*,ICoreWebView2NewWindowRequestedEventArgs*a)override{
  LPWSTR uri=nullptr;BOOL user=FALSE;a->get_Uri(&uri);a->get_IsUserInitiated(&user);a->put_Handled(TRUE);
  if(user&&external(uri))ShellExecuteW(host,L"open",uri,nullptr,nullptr,SW_SHOWNORMAL);
  CoTaskMemFree(uri);return S_OK;
 }
};
class MessageReceived:public Handler<ICoreWebView2WebMessageReceivedEventHandler>{
 public:MessageReceived():Handler(IID_ICoreWebView2WebMessageReceivedEventHandler){}
 HRESULT STDMETHODCALLTYPE Invoke(ICoreWebView2*,ICoreWebView2WebMessageReceivedEventArgs*a)override{
  LPWSTR source=nullptr,payload=nullptr;a->get_Source(&source);bool trusted=trustedTools(source);CoTaskMemFree(source);
  if(!trusted||FAILED(a->get_WebMessageAsJson(&payload))||!payload)return S_OK;
  size_t count=wcslen(payload);if(count>100000){CoTaskMemFree(payload);return S_OK;}
  int size=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,payload,(int)count,nullptr,0,nullptr,nullptr);
  std::string json(size>0?(size_t)size:0,0);if(size>0)WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,payload,(int)count,json.data(),size,nullptr,nullptr);
  CoTaskMemFree(payload);if(size<=0)return S_OK;J value=J::parse(json,nullptr,false);
  if(value.is_object()&&value.contains("action")&&value["action"].is_string()&&value["action"]=="copyText"){
   if(!value.contains("requestId")||!value["requestId"].is_string()||!NativeProtocol::uuid(value["requestId"].get<std::string>()))return S_OK;
   bool copied=SharedHostPolicy::copyText(value)&&copyUnicodeText(value["text"].get<std::string>());
   emitJson(L"galaxycontrol:clipboard-result",{{"requestId",value["requestId"]},{"copied",copied}});return S_OK;
  }
  if(count>256)return S_OK;
  if(value.is_object()&&value.size()==2&&value.value("action",std::string())=="aiPin"&&value.contains("enabled")&&value["enabled"].is_boolean()){SetWindowPos(host,value["enabled"].get<bool>()?HWND_TOPMOST:HWND_NOTOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);return S_OK;}
  if(SharedHostPolicy::captureFit(value)){fitCaptureWindow(value);return S_OK;}
  std::string action=SharedHostPolicy::message(value);
  if(action=="surfaceReady"){NativeAgent::StartupStage("uiPaintReady");}
  else if(action=="desktopReady"){uiReady=true;flushCommands();}
  else if(action=="shortcutError"){captureVisibility.reset();restoreCapturePlacement(true);show();}
  else if(action=="driveConnected"){
   show();
   // Windows may deny foreground focus while another app is active. Still show
   // the connected account in the taskbar without synthesizing user input.
   if(host&&GetForegroundWindow()!=host){FLASHWINFO flash={sizeof(FLASHWINFO),host,FLASHW_TRAY,3,0};FlashWindowEx(&flash);}
  }
  else if(!action.empty())completeCapture(action);
  return S_OK;
 }
};
static J privateJson(const wstring&path){
 HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
 if(file==INVALID_HANDLE_VALUE)return {};
 BY_HANDLE_FILE_INFORMATION info={};LARGE_INTEGER length={};
 bool valid=GetFileInformationByHandle(file,&info)&&!(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))&&GetFileSizeEx(file,&length)&&length.QuadPart>0&&length.QuadPart<=4096;
 std::string bytes(valid?(size_t)length.QuadPart:0,0);DWORD count=0;
 valid=valid&&ReadFile(file,bytes.data(),(DWORD)bytes.size(),&count,nullptr)&&count==bytes.size();CloseHandle(file);
 return valid?J::parse(bytes,nullptr,false):J();
}
// The app-state credential has no HTTP route and never enters another origin,
// ADMIN page, extension document, or iframe.
static wstring desktopBootstrap(){
 J value=privateJson(NativeAgent::StateDir()+L"\\desktop-session.json");if(!value.is_object())return {};
 std::string origin="http://127.0.0.1:"+std::to_string(agentPort);
 J identity=privateJson(NativeAgent::StateDir()+L"\\device.json");
 if(!SharedHostPolicy::credential(value,identity,origin,"4.6.23"))return {};
 std::string json=value.dump(),encodedOrigin=J(origin).dump();
 std::string code="if(window.top===window&&location.origin==="+encodedOrigin+"&&location.pathname==='/tools/'){Object.defineProperty(globalThis,'__galaxyDesktopSession',{value:"+json+",writable:false,configurable:false});}";
 return wstring(code.begin(),code.end());
}
class BootstrapReady:public Handler<ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler>{
 unsigned epoch;
 public:BootstrapReady(unsigned g):Handler(IID_ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler),epoch(g){}
 HRESULT STDMETHODCALLTYPE Invoke(HRESULT hr,LPCWSTR)override{
  if(epoch!=generation||!core||!IsWindow(host))return S_OK;
  if(FAILED(hr)){failed();return S_OK;}core->Navigate(AgentEndpoint::toolsUrl(agentPort).c_str());return S_OK;
 }
};
static void navigateWhenReady(){
 if(navigationStarted||!core||!AgentEndpoint::validPort(agentPort)||!IsWindow(host))return;
 wstring bootstrap=desktopBootstrap();
 if(bootstrap.empty()){failed(L"프로그램 연결을 준비하지 못했습니다. 다시 시도해 주세요.");return;}
 navigationStarted=true;
 auto completed=new BootstrapReady(generation);HRESULT result=core->AddScriptToExecuteOnDocumentCreated(bootstrap.c_str(),completed);completed->Release();if(FAILED(result))failed();
}
class ControllerReady:public Handler<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>{
 unsigned epoch;
 public:ControllerReady(unsigned g):Handler(IID_ICoreWebView2CreateCoreWebView2ControllerCompletedHandler),epoch(g){}
 HRESULT STDMETHODCALLTYPE Invoke(HRESULT hr,ICoreWebView2Controller*c)override{
  if(epoch!=generation||!IsWindow(host))return S_OK;
  if(FAILED(hr)||!c){failed();return S_OK;}controller=c;c->AddRef();if(FAILED(c->get_CoreWebView2(&core))){failed();return S_OK;}
  ICoreWebView2Settings*settings=nullptr;if(SUCCEEDED(core->get_Settings(&settings))){settings->put_AreDevToolsEnabled(FALSE);settings->put_IsStatusBarEnabled(FALSE);settings->Release();}
  EventRegistrationToken t={};auto nav=new Navigation;core->add_NavigationStarting(nav,&t);nav->Release();auto done=new NavigationDone(epoch);core->add_NavigationCompleted(done,&t);done->Release();auto nw=new NewWindow;core->add_NewWindowRequested(nw,&t);nw->Release();auto message=new MessageReceived;core->add_WebMessageReceived(message,&t);message->Release();
  NativeAgent::StartupStage("webviewControllerReady");bounds();c->put_IsVisible(FALSE);navigateWhenReady();return S_OK;
 }
};
class EnvironmentReady:public Handler<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>{
 unsigned epoch;
 public:EnvironmentReady(unsigned g):Handler(IID_ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler),epoch(g){}
 HRESULT STDMETHODCALLTYPE Invoke(HRESULT hr,ICoreWebView2Environment*e)override{
  if(epoch!=generation||!IsWindow(host))return S_OK;if(FAILED(hr)||!e){failed();return S_OK;}NativeAgent::StartupStage("webviewEnvironmentReady");
  auto handler=new ControllerReady(epoch);HRESULT result=e->CreateCoreWebView2Controller(host,handler);handler->Release();if(FAILED(result))failed();return S_OK;
 }
};
static LRESULT CALLBACK hostProc(HWND h,UINT m,WPARAM w,LPARAM l){
 switch(m){
  case WM_CREATE:
   KioStartup::load(app);KioStartup::resume(h);
   notice=CreateWindowW(L"STATIC",L"",WS_CHILD|SS_CENTER,28,48,760,126,h,(HMENU)3,app,nullptr);
   retryButton=CreateWindowW(L"BUTTON",L"다시 시도",WS_CHILD|WS_TABSTOP,28,190,130,38,h,(HMENU)10,app,nullptr);
   runtimeButton=CreateWindowW(L"BUTTON",L"WebView2 설치 안내",WS_CHILD|WS_TABSTOP,174,190,210,38,h,(HMENU)11,app,nullptr);
   hostFont=CreateFontW(-chrome(16),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Segoe UI");
   for(HWND ctl:{notice,retryButton,runtimeButton})SendMessageW(ctl,WM_SETFONT,(WPARAM)hostFont,TRUE);I18NLocalizeTree(h);return 0;
  case WM_GETMINMAXINFO:{auto info=reinterpret_cast<MINMAXINFO*>(l);MONITORINFO monitor={sizeof(MONITORINFO)};GetMonitorInfoW(MonitorFromWindow(h,MONITOR_DEFAULTTONEAREST),&monitor);info->ptMinTrackSize.x=std::min(chrome(captureVisibility.pending?420:680),(int)(monitor.rcWork.right-monitor.rcWork.left));info->ptMinTrackSize.y=std::min(chrome(captureVisibility.pending?300:560),(int)(monitor.rcWork.bottom-monitor.rcWork.top));return 0;}
  case WM_SIZE:bounds();InvalidateRect(h,nullptr,FALSE);return 0;
  case WM_ERASEBKGND:return 1;
  case WM_PAINT:KioStartup::paint(h);return 0;
  case WM_TIMER:if(w==KioStartup::timer){KioStartup::tick(h);return 0;}break;
  case WM_CTLCOLORSTATIC:SetBkMode((HDC)w,TRANSPARENT);SetTextColor((HDC)w,RGB(52,43,38));return (LRESULT)GetStockObject(NULL_BRUSH);
  case WM_SETFOCUS:if(controller&&IsWindowVisible(h))controller->MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);return 0;
  case WM_DPICHANGED:{auto r=reinterpret_cast<const RECT*>(l);SetWindowPos(h,nullptr,r->left,r->top,r->right-r->left,r->bottom-r->top,SWP_NOZORDER|SWP_NOACTIVATE);bounds();return 0;}
  case WM_COMMAND:
   if(LOWORD(w)==10)NativeAgent::OpenTools();
   else if(LOWORD(w)==11)ShellExecuteW(h,L"open",L"https://developer.microsoft.com/microsoft-edge/webview2/",nullptr,nullptr,SW_SHOWNORMAL);
   return 0;
  case WM_CLOSE:if(captureVisibility.closeWindow()){queuedShortcut.clear();queuedCategory="capture";flushCommands();restoreCapturePlacement(false);}if(UxTrayAvailable())ShowWindow(h,SW_HIDE);else show();return 0;
  case WM_DESTROY:KioStartup::close(h);host=nullptr;notice=nullptr;retryButton=nullptr;runtimeButton=nullptr;if(hostFont){DeleteObject(hostFont);hostFont=nullptr;}return 0;
 }
 return DefWindowProcW(h,m,w,l);
}
static bool createHost(HWND,HINSTANCE instance){
 app=instance;if(host&&IsWindow(host))return true;
 WNDCLASSW c={};c.lpfnWndProc=hostProc;c.hInstance=app;c.lpszClassName=L"GalaxyControlSharedTools";c.hCursor=LoadCursorW(nullptr,IDC_ARROW);c.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);c.hIcon=GalaxyAppIcon(app);RegisterClassW(&c);
 RECT area;SystemParametersInfoW(SPI_GETWORKAREA,0,&area,0);int width=std::min(1360,(int)(area.right-area.left)),height=std::min(960,(int)(area.bottom-area.top));
 host=CreateWindowW(c.lpszClassName,L"Bogo Tools",WS_OVERLAPPEDWINDOW,area.left+(area.right-area.left-width)/2,area.top+(area.bottom-area.top-height)/2,width,height,nullptr,nullptr,app,nullptr);if(!host)return false;
 KioTaskbar::apply(host);SendMessageW(host,WM_SETICON,ICON_BIG,(LPARAM)GalaxyAppIcon(app,GetSystemMetrics(SM_CXICON)));SendMessageW(host,WM_SETICON,ICON_SMALL,(LPARAM)GalaxyAppIcon(app,GetSystemMetrics(SM_CXSMICON)));return true;
}
void SharedHostShowMessage(HWND original,HINSTANCE instance,const wchar_t*text,bool runtime){if(createHost(original,instance)){failed(text,runtime);show();}}
static bool prepareView(const wstring&profile){
 if(pageReady&&core)return true;
 if(core&&controller){navigateWhenReady();return true;}
 if(creating)return true;
 if(!loader){wchar_t path[32768];DWORD n=GetModuleFileNameW(nullptr,path,32768);if(n&&n<32768){PathRemoveFileSpecW(path);wstring base=path;for(auto p:{base+L"\\tools\\webview2\\WebView2Loader.dll",base+L"\\webview2\\WebView2Loader.dll"}){loader=LoadLibraryExW(p.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);if(loader)break;}}}
 if(!loader){failed(L"프로그램 구성 파일이 없습니다. Bogo Tools 폴더 전체를 다시 설치해 주세요.");return true;}
 auto version=(decltype(&GetAvailableCoreWebView2BrowserVersionString))GetProcAddress(loader,"GetAvailableCoreWebView2BrowserVersionString");auto create=(decltype(&CreateCoreWebView2EnvironmentWithOptions))GetProcAddress(loader,"CreateCoreWebView2EnvironmentWithOptions");
 LPWSTR v=nullptr;bool installed=version&&SUCCEEDED(version(nullptr,&v))&&v;CoTaskMemFree(v);
 if(!installed||!create){failed(L"이 프로그램을 사용하려면 Microsoft WebView2 런타임이 필요합니다. 설치 후 다시 시도해 주세요.",true);return true;}
 ShowWindow(notice,SW_HIDE);ShowWindow(retryButton,SW_HIDE);ShowWindow(runtimeButton,SW_HIDE);KioStartup::resume(host);creating=true;++generation;
 auto handler=new EnvironmentReady(generation);HRESULT hr=create(nullptr,profile.c_str(),nullptr,handler);handler->Release();if(FAILED(hr))failed();return true;
}
void SharedHostShowLoading(HWND original,HINSTANCE instance){
 if(!createHost(original,instance))return;
 if(controller)controller->put_IsVisible(FALSE);
 ShowWindow(notice,SW_HIDE);ShowWindow(retryButton,SW_HIDE);ShowWindow(runtimeButton,SW_HIDE);
 KioStartup::resume(host);InvalidateRect(host,nullptr,FALSE);show();
}
bool SharedHostWarm(HWND original,HINSTANCE instance,const wstring&profile,bool showWindow){
 if(!createHost(original,instance))return false;
 NativeAgent::StartupStage("hostWarm");
 if(showWindow)SharedHostShowLoading(original,instance);
 return prepareView(profile);
}
bool SharedHostOpen(HWND original,HINSTANCE instance,const wstring&profile,unsigned short port,bool showWindow){
 if(!AgentEndpoint::validPort(port))return false;
 if(agentPort&&agentPort!=port&&host&&IsWindow(host))SharedHostShutdown();agentPort=port;
 if(!createHost(original,instance))return false;
 if(showWindow){if(captureVisibility.pending&&!captureVisibility.ready){captureVisibility.reset();restoreCapturePlacement(true);}show();}
 return prepareView(profile);
}
HWND SharedHostWindow(){return host;}
bool SharedHostCapturePending(){return captureVisibility.pending;}
bool SharedHostNavigate(const std::string&category){if(!categoryAllowed(category)||!host||!IsWindow(host))return false;queuedCategory=category;show();flushCommands();return true;}
bool SharedHostShortcut(const std::string&name){
 if(!AgentEndpoint::validPort(agentPort)||!shortcutAllowed(name)||!host||!IsWindow(host)||(!pageReady&&!creating))return false;
 std::string normalized=SharedHostPolicy::shortcut(name);
 std::string destination=NativeAgent::ShortcutDestination(normalized);
 if(destination=="web")return true;
 if(destination!="desktop"){show();return true;}
 ULONGLONG tick=GetTickCount64();if(normalized==lastShortcutName&&tick-lastShortcutTick<400)return true;
 if(SharedHostPolicy::captureShortcut(normalized)){
  if(captureVisibility.pending&&!captureVisibility.ready)return true;
  const bool includeHost=IsWindowVisible(host)&&GetAncestor(GetForegroundWindow(),GA_ROOT)==host;
  // Freeze a deliberately focused KIO window before any UI transition. For other
  // foreground apps, the native capture freezes only after KIO is fully hidden.
  if(!NativeServices::PrepareShortcutCapture(normalized!="webCapture"&&includeHost))return true;
  if(!captureVisibility.begin(IsWindowVisible(host)!=FALSE))return true;
  rememberCapturePlacement();CaptureBackdrop::hide({host});
 }
 // ExecuteScript works with a hidden host. Resume the renderer without showing
 // or focusing the app; only a result or an explicit navigation shows it.
 if(controller)controller->put_IsVisible(TRUE);
 ICoreWebView2_3*resumable=nullptr;
 if(core&&SUCCEEDED(core->QueryInterface(IID_ICoreWebView2_3,(void**)&resumable))){resumable->Resume();resumable->Release();}
 lastShortcutName=normalized;lastShortcutTick=tick;
 FILETIME fileTime;GetSystemTimeAsFileTime(&fileTime);ULARGE_INTEGER stamp;stamp.HighPart=fileTime.dwHighDateTime;stamp.LowPart=fileTime.dwLowDateTime;shortcutStartedAt=stamp.QuadPart/10000.0-11644473600000.0;queuedShortcut=normalized;flushCommands();return true;
}
void SharedHostShutdown(){
 ++generation;pageReady=false;uiReady=false;creating=false;navigationStarted=false;captureVisibility.reset();capturePlacementSaved=false;restoreShowCmd=SW_RESTORE;lastShortcutName.clear();lastShortcutTick=0;queuedCategory.clear();queuedShortcut.clear();
 if(core){core->Release();core=nullptr;}if(controller){controller->Close();controller->Release();controller=nullptr;}if(host)DestroyWindow(host);
 // Keep the loader mapped: late runtime callbacks can still reference it.
}

void SharedHostAISelected(){completeCapture("captureReady");fitCaptureWindow(J{{"action","captureFit"},{"width",470},{"height",450},{"chromeHeight",70}});emit(L"galaxycontrol:ai-selected","stage","uploading");}
