#ifndef UNICODE
#define UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <winhttp.h>
#include <sddl.h>
#include <aclapi.h>
#include <shlobj.h>
#include <shlwapi.h>
#include <shellapi.h>
#include <commdlg.h>
#include <objbase.h>
#include <algorithm>
#include <vector>
#include <set>
#include <memory>
#include <thread>
#include <mutex>
#include "NativeBridge.h"
#include "UxShell.h"
#include "NativeProtocol.h"
#include "AgentEndpoint.h"
#include "WindowsCommandLine.h"
#include "SharedHost.h"
#include "WindowsRecorder.h"
#include "I18N.h"
#include "ToolHub.h"
#include "PhoneControl.h"
#include "UxShell.h"
using std::wstring;using J=nlohmann::json;
namespace NativeAgent {
static ULONGLONG startupTick=GetTickCount64();static J startupTimes=J::object();static std::mutex startupLock;
static HWND owner;static HINSTANCE app;static wstring state,base,requests,responses,signals,processing,uiDir;static HANDLE agentJob=nullptr,agentProcess=nullptr,startThread=nullptr;static LONG shutting=0,backendJobs=0,checkingHealth=0,agentPort=0;static bool ready=false,openPending=false,startHome=true,dispatching=false;static ULONGLONG lastBeat=0;static J captureRequest,recordRequest,stopRequest;static wstring captureDocument;static std::string pendingCategory,initialShortcut;
static wstring wide(const std::string&s){if(s.empty())return {};int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.data(),(int)s.size(),nullptr,0);if(!n)return {};wstring out(n,0);MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.data(),(int)s.size(),out.data(),n);return out;}
static std::string utf8(const wstring&s){int n=WideCharToMultiByte(CP_UTF8,0,s.data(),(int)s.size(),nullptr,0,nullptr,nullptr);std::string out(n,0);if(n)WideCharToMultiByte(CP_UTF8,0,s.data(),(int)s.size(),out.data(),n,nullptr,nullptr);return out;}
static double now(){FILETIME t;GetSystemTimeAsFileTime(&t);ULARGE_INTEGER v;v.HighPart=t.dwHighDateTime;v.LowPart=t.dwLowDateTime;return v.QuadPart/10000000.0-11644473600.0;}
static bool plainFile(const wstring&p){DWORD a=GetFileAttributesW(p.c_str());return a!=INVALID_FILE_ATTRIBUTES&&!(a&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT));}
static bool secureDir(const wstring&p){DWORD a=GetFileAttributesW(p.c_str());if(a==INVALID_FILE_ATTRIBUTES){if(!CreateDirectoryW(p.c_str(),nullptr))return false;}else if(!(a&FILE_ATTRIBUTE_DIRECTORY)||(a&FILE_ATTRIBUTE_REPARSE_POINT))return false;HANDLE token=nullptr;if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token))return false;DWORD size=0;GetTokenInformation(token,TokenUser,nullptr,0,&size);std::vector<BYTE>b(size);bool ok=GetTokenInformation(token,TokenUser,b.data(),size,&size)!=FALSE;CloseHandle(token);if(!ok)return false;LPWSTR sid=nullptr;if(!ConvertSidToStringSidW(((TOKEN_USER*)b.data())->User.Sid,&sid))return false;wstring sddl=L"D:P(A;OICI;FA;;;"+wstring(sid)+L")";LocalFree(sid);PSECURITY_DESCRIPTOR descriptor=nullptr;if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(),SDDL_REVISION_1,&descriptor,nullptr))return false;ok=SetFileSecurityW(p.c_str(),DACL_SECURITY_INFORMATION|PROTECTED_DACL_SECURITY_INFORMATION,descriptor)!=FALSE;LocalFree(descriptor);return ok;}
static std::string guid(){GUID g;if(FAILED(CoCreateGuid(&g)))return {};wchar_t b[40];StringFromGUID2(g,b,40);std::string id=utf8(wstring(b+1,36));for(char&c:id)if(c>='A'&&c<='F')c+=('a'-'A');return id;}
static bool atomicJson(const wstring&path,const J&value){wstring temp=path+L"."+wide(guid())+L".tmp";HANDLE h=CreateFileW(temp.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);if(h==INVALID_HANDLE_VALUE)return false;std::string data=value.dump();DWORD done=0;bool ok=WriteFile(h,data.data(),(DWORD)data.size(),&done,nullptr)&&done==data.size()&&FlushFileBuffers(h);CloseHandle(h);if(ok)ok=MoveFileExW(temp.c_str(),path.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=FALSE;if(!ok)DeleteFileW(temp.c_str());return ok;}
void StartupStage(const char*stage){
 static const std::set<std::string> allowed={"nativeInit","agentStarting","backendReady","hostWarm","webviewEnvironmentReady","webviewControllerReady","navigationReady","uiPaintReady"};
 if(!stage||!allowed.count(stage))return;
 std::lock_guard<std::mutex> guard(startupLock);
 if(!startupTimes.contains(stage))startupTimes[stage]=GetTickCount64()-startupTick;
 if(!state.empty())atomicJson(state+L"\\startup-performance.json",{{"version","4.6.23"},{"clock","native-process-monotonic-ms"},{"stagesMs",startupTimes}});
}
static J readJson(const wstring&p){if(!plainFile(p))return {};HANDLE h=CreateFileW(p.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);if(h==INVALID_HANDLE_VALUE)return {};BY_HANDLE_FILE_INFORMATION info={};LARGE_INTEGER n;bool valid=GetFileInformationByHandle(h,&info)&&!(info.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)&&GetFileSizeEx(h,&n)&&n.QuadPart>0&&n.QuadPart<=65536;std::string bytes(valid?(size_t)n.QuadPart:0,0);DWORD got=0;bool ok=valid&&ReadFile(h,bytes.data(),(DWORD)bytes.size(),&got,nullptr)&&got==bytes.size();CloseHandle(h);return ok?J::parse(bytes,nullptr,false):J();}
static void respond(const J&r,bool ok,const J&data=J::object(),const char*error=""){if(!r.is_object()||!r.contains("id"))return;std::string id=r["id"].get<std::string>();if(!NativeProtocol::uuid(id))return;atomicJson(responses+L"\\"+wide(id)+L".json",{{"id",id},{"ok",ok},{"data",data},{"errorCode",error}});DeleteFileW((processing+L"\\"+wide(id)+L".json").c_str());}
static void complete(J&r,bool ok,const J&data=J::object(),const char*err=""){if(r.is_object())respond(r,ok,data,err);r=J();}
static wstring quote(const wstring&s){return WindowsCommandLine::quote(s);}
static unsigned short currentPort(){return (unsigned short)InterlockedCompareExchange(&agentPort,0,0);}
static std::string ownDeviceId(){J device=readJson(state+L"\\device.json");try{std::string id=device.value("deviceId",std::string());return NativeProtocol::uuid(id)?id:std::string();}catch(...){return {};}}
static J probe(unsigned short port){
 HINTERNET session=WinHttpOpen(L"GalaxyControl/4.6.23",WINHTTP_ACCESS_TYPE_NO_PROXY,nullptr,nullptr,0);if(!session)return {};
 WinHttpSetTimeouts(session,300,300,500,500);HINTERNET connection=WinHttpConnect(session,L"127.0.0.1",port,0);
 HINTERNET request=connection?WinHttpOpenRequest(connection,L"GET",L"/health",nullptr,WINHTTP_NO_REFERER,WINHTTP_DEFAULT_ACCEPT_TYPES,0):nullptr;
 J result;
 if(request){DWORD redirect=WINHTTP_OPTION_REDIRECT_POLICY_NEVER;WinHttpSetOption(request,WINHTTP_OPTION_REDIRECT_POLICY,&redirect,sizeof(redirect));wstring origin=L"Origin: http://127.0.0.1:"+std::to_wstring(port)+L"\r\n";WinHttpAddRequestHeaders(request,origin.c_str(),(DWORD)-1,WINHTTP_ADDREQ_FLAG_ADD|WINHTTP_ADDREQ_FLAG_REPLACE);}
 if(request&&WinHttpSendRequest(request,WINHTTP_NO_ADDITIONAL_HEADERS,0,WINHTTP_NO_REQUEST_DATA,0,0,0)&&WinHttpReceiveResponse(request,nullptr)){
  DWORD code=0,n=sizeof(code);
  if(WinHttpQueryHeaders(request,WINHTTP_QUERY_STATUS_CODE|WINHTTP_QUERY_FLAG_NUMBER,WINHTTP_HEADER_NAME_BY_INDEX,&code,&n,WINHTTP_NO_HEADER_INDEX)&&code==200){
   std::string body;DWORD available=0;bool complete=true;ULONGLONG deadline=GetTickCount64()+1500;
   while(WinHttpQueryDataAvailable(request,&available)&&available){if(GetTickCount64()>deadline||body.size()+available>65536){complete=false;break;}size_t at=body.size();body.resize(at+available);DWORD got=0;if(!WinHttpReadData(request,body.data()+at,available,&got)||!got){complete=false;break;}body.resize(at+got);}
   if(complete)result=J::parse(body,nullptr,false);
  }
 }
 if(request)WinHttpCloseHandle(request);if(connection)WinHttpCloseHandle(connection);WinHttpCloseHandle(session);return result;
}
std::string ShortcutDestination(const std::string&action){
 unsigned short port=currentPort();if(!AgentEndpoint::validPort(port))return "login";
 J credential=readJson(state+L"\\desktop-session.json");std::string token;
 try{if(credential.value("deviceId",std::string())!=ownDeviceId()||credential.value("origin",std::string())!="http://127.0.0.1:"+std::to_string(port))return "login";token=credential.value("token",std::string());}catch(...){return "login";}
 if(token.size()<32||token.size()>256||token.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")!=std::string::npos)return "login";
 HINTERNET session=WinHttpOpen(L"KIOControl",WINHTTP_ACCESS_TYPE_NO_PROXY,nullptr,nullptr,0);if(!session)return "login";
 WinHttpSetTimeouts(session,500,500,3000,8000);HINTERNET connection=WinHttpConnect(session,L"127.0.0.1",port,0);
 HINTERNET http=connection?WinHttpOpenRequest(connection,L"POST",L"/desktop/dispatch",nullptr,WINHTTP_NO_REFERER,WINHTTP_DEFAULT_ACCEPT_TYPES,0):nullptr;
 std::string destination="login",body=J{{"action",action}}.dump();
 if(http){DWORD policy=WINHTTP_OPTION_REDIRECT_POLICY_NEVER;WinHttpSetOption(http,WINHTTP_OPTION_REDIRECT_POLICY,&policy,sizeof(policy));
  wstring headers=L"Origin: http://127.0.0.1:"+std::to_wstring(port)+L"\r\nContent-Type: application/json\r\nX-Local-Agent-Token: "+wide(token)+L"\r\n";
  if(WinHttpSendRequest(http,headers.c_str(),(DWORD)-1,body.data(),(DWORD)body.size(),(DWORD)body.size(),0)&&WinHttpReceiveResponse(http,nullptr)){
   DWORD code=0,n=sizeof(code);if(WinHttpQueryHeaders(http,WINHTTP_QUERY_STATUS_CODE|WINHTTP_QUERY_FLAG_NUMBER,WINHTTP_HEADER_NAME_BY_INDEX,&code,&n,WINHTTP_NO_HEADER_INDEX)&&code==200){
    char buffer[4097]={};DWORD got=0;if(WinHttpReadData(http,buffer,4096,&got)){J result=J::parse(std::string(buffer,got),nullptr,false);if(result.is_object()){auto value=result.value("destination",std::string());if(value=="desktop"||value=="web"||value=="login")destination=value;}}
   }
  }SecureZeroMemory(headers.data(),headers.size()*sizeof(wchar_t));WinHttpCloseHandle(http);
 }SecureZeroMemory(token.data(),token.size());if(connection)WinHttpCloseHandle(connection);WinHttpCloseHandle(session);return destination;
}
static bool health(int*jobs=nullptr){unsigned short port=currentPort();if(!AgentEndpoint::validPort(port))return false;std::string identity=ownDeviceId();if(identity.empty())return false;J result=probe(port);bool ok=AgentEndpoint::ready(result,identity);if(ok&&jobs){try{*jobs=std::max(0,result.value("activeJobs",0));}catch(...){return false;}}return ok;}
static DWORD WINAPI checkHealth(void*){int jobs=0;if(health(&jobs))InterlockedExchange(&backendJobs,jobs);else InterlockedExchange(&backendJobs,agentProcess&&WaitForSingleObject(agentProcess,0)!=WAIT_OBJECT_0?-1:0);InterlockedExchange(&checkingHealth,0);return 0;}
static void closeOwnedAgent(){if(agentJob){CloseHandle(agentJob);agentJob=nullptr;}if(agentProcess){WaitForSingleObject(agentProcess,1000);CloseHandle(agentProcess);agentProcess=nullptr;}}
static SOCKET reservePort(unsigned short port){SOCKET socketHandle=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);if(socketHandle==INVALID_SOCKET)return INVALID_SOCKET;BOOL exclusive=TRUE;sockaddr_in address={};address.sin_family=AF_INET;address.sin_port=htons(port);address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);if(setsockopt(socketHandle,SOL_SOCKET,SO_EXCLUSIVEADDRUSE,(const char*)&exclusive,sizeof(exclusive))==SOCKET_ERROR||bind(socketHandle,(sockaddr*)&address,sizeof(address))==SOCKET_ERROR){closesocket(socketHandle);return INVALID_SOCKET;}return socketHandle;}
static bool waitReady(){for(int i=0;i<32&&!InterlockedCompareExchange(&shutting,0,0);i++){if(health())return true;if(agentProcess&&WaitForSingleObject(agentProcess,0)==WAIT_OBJECT_0)return false;Sleep(250);}return false;}
static DWORD WINAPI startAgent(void*){
 StartupStage("agentStarting");bool ok=health();
 if(!ok&&!InterlockedCompareExchange(&shutting,0,0)){
  bool canStart=true;
  if(agentProcess){if(WaitForSingleObject(agentProcess,0)==WAIT_OBJECT_0)closeOwnedAgent();else {ok=waitReady();canStart=false;}}
  if(canStart){
   bool existing=false;std::string identity=ownDeviceId();
   // Reuse only an agent that belongs to this private user state.
   if(!identity.empty())for(auto port:AgentEndpoint::ports){if(InterlockedCompareExchange(&shutting,0,0))break;J result=probe(port);if(AgentEndpoint::matches(result,identity)){InterlockedExchange(&agentPort,port);existing=true;ok=AgentEndpoint::ready(result,identity)||waitReady();break;}}
   if(!existing&&!InterlockedCompareExchange(&shutting,0,0)){
    wstring python,script;for(auto path:{base+L"\\tools\\python\\python.exe",base+L"\\engine\\runtimes\\win64\\python.exe",base+L"\\tools\\engine\\runtimes\\win64\\python.exe"})if(plainFile(path)){python=path;break;}
    for(auto path:{base+L"\\tools\\engine\\agent\\server.py",base+L"\\engine\\agent\\server.py"})if(plainFile(path)){script=path;break;}
    WSADATA sockets={};bool socketsReady=WSAStartup(MAKEWORD(2,2),&sockets)==0;
    if(socketsReady&&!python.empty()&&!script.empty())for(auto port:AgentEndpoint::ports){
     if(InterlockedCompareExchange(&shutting,0,0))break;
     SOCKET reservation=reservePort(port);if(reservation==INVALID_SOCKET)continue;
     wstring command=quote(python)+L" -I "+quote(script)+L" --state-dir "+quote(state)+L" --ui-dir "+quote(uiDir)+L" --port "+std::to_wstring(port);
     STARTUPINFOW startup={sizeof(startup)};startup.dwFlags=STARTF_USESHOWWINDOW;startup.wShowWindow=SW_HIDE;PROCESS_INFORMATION process={};HANDLE job=CreateJobObjectW(nullptr,nullptr);JOBOBJECT_EXTENDED_LIMIT_INFORMATION limit={};limit.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE|JOB_OBJECT_LIMIT_BREAKAWAY_OK;
     bool jobOk=job&&SetInformationJobObject(job,JobObjectExtendedLimitInformation,&limit,sizeof(limit));
     if(jobOk&&CreateProcessW(python.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW|CREATE_SUSPENDED,nullptr,base.c_str(),&startup,&process)){
      if(AssignProcessToJobObject(job,process.hProcess)){agentJob=job;agentProcess=process.hProcess;InterlockedExchange(&agentPort,port);closesocket(reservation);reservation=INVALID_SOCKET;ResumeThread(process.hThread);}
      else{TerminateProcess(process.hProcess,1);CloseHandle(process.hProcess);CloseHandle(job);}
      CloseHandle(process.hThread);
     }else if(job)CloseHandle(job);
     if(reservation!=INVALID_SOCKET)closesocket(reservation);
     if(agentProcess){ok=waitReady();if(ok)break;closeOwnedAgent();}
    }
    if(socketsReady)WSACleanup();
   }
  }
 }
 if(!InterlockedCompareExchange(&shutting,0,0))PostMessageW(owner,ReadyMessage,ok,0);return 0;
}
static HWND promptOwner(){HWND h=SharedHostWindow();return h&&IsWindowVisible(h)?h:owner;}
static J phoneState(){GalaxyPhoneState state={};GalaxyPhoneReadState(&state);J devices=J::array();for(int i=0;i<state.count;i++){auto&d=state.devices[i];devices.push_back({{"serial",utf8(d.serial)},{"label",utf8(d.label)},{"transport",d.wireless?"wifi":"usb"},{"status",utf8(d.status)}});}return {{"devices",devices},{"running",state.running!=0},{"activeSerial",utf8(state.activeSerial)},{"available",state.available!=0},{"options",{{"keyboard",state.keyboardSdk?"sdk":"uhid"},{"mouse",state.mouseUhid?"uhid":"sdk"},{"audio",state.audioMode==2?"off":state.audioMode==1?"aac":"output"},{"clipboard",state.clipboard!=0}}}};}
struct PhonePending{J request;bool status;};
static void phoneComplete(void*context,int success,const char*error){std::unique_ptr<PhonePending>pending((PhonePending*)context);if(pending->request.value("expiresAt",0.0)<=now()){respond(pending->request,false,J::object(),"expired");return;}respond(pending->request,success!=0,success?(pending->status?phoneState():J{{"success",true}}):J::object(),success?"":error);}
static void dispatchPhone(const J&r){auto op=r.at("operation").get<std::string>();const auto&a=r.at("args");if(!NativeProtocol::phoneArguments(op,a)){respond(r,false,J::object(),"invalidRequest");return;}GalaxyPhoneRequest request={};request.operation=op=="phone.status"?GP_STATUS:op=="phone.pair"?GP_PAIR:op=="phone.connect"?GP_CONNECT:op=="phone.start"?GP_START:op=="phone.stop"?GP_STOP:GP_KEYBOARD;request.clipboard=a.value("clipboard",true);request.keyboardSdk=a.value("keyboard",std::string("uhid"))=="sdk";request.mouseUhid=a.value("mouse",std::string("uhid"))=="uhid";auto audio=a.value("audio",std::string("output"));request.audioMode=audio=="off"?2:audio=="aac"?1:0;auto assign=[](wchar_t*to,size_t cap,const wstring&value){wcsncpy(to,value.c_str(),cap-1);to[cap-1]=0;};assign(request.serial,256,wide(a.value("serial",std::string())));assign(request.address,256,wide(a.value("address",std::string())));assign(request.code,7,wide(a.value("code",std::string())));auto pending=new PhonePending{J{{"id",r.at("id")},{"expiresAt",r.at("expiresAt")}},op=="phone.status"};const char*error="phoneUnavailable";bool ok=GalaxyPhoneSubmit(&request,phoneComplete,pending,&error)!=0;SecureZeroMemory(&request,sizeof(request));if(!ok){delete pending;respond(r,false,J::object(),error);}else DeleteFileW((processing+L"\\"+wide(r.at("id").get<std::string>())+L".json").c_str());}
static J chooseFolder(const J&a,double expires){std::string purpose=a.value("purpose",std::string());if(purpose!="search"&&purpose!="save")throw std::runtime_error("invalidRequest");BROWSEINFOW b={};b.hwndOwner=promptOwner();b.ulFlags=BIF_RETURNONLYFSDIRS|BIF_NEWDIALOGSTYLE;b.lpszTitle=GalaxyTr(purpose=="save"?L"저장할 폴더 선택":L"찾을 폴더 선택");PIDLIST_ABSOLUTE item=SHBrowseForFolderW(&b);if(!item)return {{"cancelled",true},{"path",""}};wchar_t path[32768]={};bool ok=SHGetPathFromIDListEx(item,path,32768,GPFIDL_DEFAULT)!=FALSE;CoTaskMemFree(item);if(now()>=expires)throw std::runtime_error("expired");if(ok&&purpose=="save"&&!NativeServices::SetSaveFolder(path))throw std::runtime_error("settingsFailed");return {{"cancelled",!ok},{"path",ok?utf8(path):""}};}
static J chooseFiles(const J&a){std::string kind=a.value("kind",std::string("any"));if(kind!="image"&&kind!="pdf"&&kind!="video"&&kind!="any")throw std::runtime_error("invalidRequest");std::vector<wchar_t>buf(65536,0);wstring filter;auto addFilter=[&](const wchar_t*name,const wchar_t*pattern){filter+=GalaxyTr(name);filter+=L'\0';filter+=pattern;filter+=L'\0';};if(kind=="image")addFilter(L"이미지",L"*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.tif;*.tiff");else if(kind=="pdf")addFilter(L"PDF",L"*.pdf");else if(kind=="video")addFilter(L"동영상",L"*.mp4;*.mov;*.avi;*.mkv;*.webm;*.gif");else addFilter(L"파일",L"*.*");if(kind!="pdf")addFilter(L"모든 파일",L"*.*");filter+=L'\0';OPENFILENAMEW f={sizeof(f)};f.hwndOwner=promptOwner();f.lpstrFile=buf.data();f.nMaxFile=(DWORD)buf.size();f.lpstrFilter=filter.c_str();f.Flags=OFN_FILEMUSTEXIST|OFN_EXPLORER|OFN_NOCHANGEDIR|(a.value("multiple",false)?OFN_ALLOWMULTISELECT:0);if(!GetOpenFileNameW(&f))return {{"paths",J::array()},{"cancelled",true}};J paths=J::array();wstring first=buf.data();const wchar_t*p=buf.data()+first.size()+1;if(*p){while(*p){paths.push_back(utf8(first+L"\\"+p));p+=wcslen(p)+1;}}else paths.push_back(utf8(first));return {{"paths",paths},{"cancelled",false}};}
static bool localPath(const wstring&p){return p.size()>2&&p.size()<32760&&((p[1]==L':'&&(p[2]==L'\\'||p[2]==L'/'))||(p[0]==L'\\'&&p[1]==L'\\'))&&p.find_first_of(L"\r\n")==wstring::npos;}
static bool openable(const wstring&p){wstring e=PathFindExtensionW(p.c_str());for(auto&c:e)c=towlower(c);static const std::set<wstring>allowed={L".png",L".jpg",L".jpeg",L".webp",L".gif",L".bmp",L".tif",L".tiff",L".pdf",L".mp4",L".mov",L".avi",L".mkv",L".webm",L".mp3",L".wav",L".txt",L".csv",L".docx",L".xlsx",L".pptx",L".zip"};return allowed.count(e)!=0;}
static void writeStatus();
static void dispatch(const J&r){const J&a=r.at("args");std::string op=r.at("operation").get<std::string>();std::string error;try{if(op=="pair.approve"){std::string origin=a.value("origin",std::string()),client=a.value("clientName",std::string("GalaxyControl"));if(origin.empty()||origin.size()>2048||client.size()>256||origin.find_first_of("\r\n")!=std::string::npos||client.find_first_of("\r\n")!=std::string::npos||!(origin.rfind("http://",0)==0||origin.rfind("https://",0)==0||origin.rfind("chrome-extension://",0)==0)){respond(r,false,J::object(),"invalidRequest");return;}wstring text=wstring(GalaxyTr(L"이 도구 화면이 이 컴퓨터의 파일과 캡처 기능을 사용하도록 허용할까요?"))+L"\r\n\r\n"+wide(client)+L"\r\n"+wide(origin);bool allow=GalaxyMessageBox(promptOwner(),text.c_str(),L"로컬 도구 연결 승인",MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2|MB_SETFOREGROUND)==IDYES;respond(r,true,{{"approved",allow}});}
else if(op=="folder.choose")respond(r,true,chooseFolder(a,r.at("expiresAt").get<double>()));else if(op=="files.choose")respond(r,true,chooseFiles(a));
else if(op=="file.open"||op=="file.reveal"){wstring p=wide(a.value("path",std::string()));DWORD attr=GetFileAttributesW(p.c_str());if(!localPath(p)||attr==INVALID_FILE_ATTRIBUTES){respond(r,false,J::object(),"invalidPath");return;}bool ok=false;if(op=="file.open"){if((attr&FILE_ATTRIBUTE_DIRECTORY)||!openable(p)){respond(r,false,J::object(),"unsupported");return;}ok=(INT_PTR)ShellExecuteW(promptOwner(),L"open",p.c_str(),nullptr,nullptr,SW_SHOWNORMAL)>32;}else{PIDLIST_ABSOLUTE item=nullptr;if(SUCCEEDED(SHParseDisplayName(p.c_str(),nullptr,&item,0,nullptr))){if(attr&FILE_ATTRIBUTE_DIRECTORY)ok=SUCCEEDED(SHOpenFolderAndSelectItems(item,0,nullptr,0));else{PIDLIST_ABSOLUTE parent=ILCloneFull(item);if(parent&&ILRemoveLastID(parent)){PCUITEMID_CHILD child=ILFindLastID(item);ok=SUCCEEDED(SHOpenFolderAndSelectItems(parent,1,&child,0));}if(parent)CoTaskMemFree(parent);}CoTaskMemFree(item);}}respond(r,ok,J::object(),ok?"":"openFailed");}
else if(op=="clipboard.copy"){if(!NativeProtocol::clipboardArguments(a)){respond(r,false,J::object(),"invalidRequest");return;}wstring path=wide(a["path"].get<std::string>());bool ok=localPath(path)&&NativeServices::CopyClipboardImage(path,error);respond(r,ok,ok?J{{"copied",true}}:J::object(),ok?"":(error.empty()?"invalidPath":error.c_str()));}
else if(op=="capture.start"){if(captureRequest.is_object()){respond(r,false,J::object(),"busy");return;}captureRequest=r;captureDocument.clear();if(!NativeServices::Capture(a,error,r.at("id").get<std::string>()))complete(captureRequest,false,J::object(),error.c_str());}
else if(op=="capture.cancel"){if(!NativeProtocol::captureCancelArguments(a)){respond(r,false,J::object(),"invalidRequest");return;}std::string id=a["requestId"].get<std::string>();bool matches=captureRequest.is_object()&&NativeProtocol::captureCancelMatches(a,captureRequest.value("id",std::string()));bool cancelled=matches&&NativeServices::CancelCapture(id);if(cancelled){complete(captureRequest,false,J::object(),"cancelled");captureDocument.clear();}respond(r,true,{{"cancelledCapture",cancelled}});}
else if(op=="record.start"){if(recordRequest.is_object()||Recording::Active()){respond(r,false,J::object(),"busy");return;}recordRequest=r;if(!NativeServices::Record(a,error))complete(recordRequest,false,J::object(),error.c_str());}
else if(op=="record.pause"||op=="record.resume"){if(!a.empty()){respond(r,false,J::object(),"invalidRequest");return;}bool ok=op=="record.pause"?Recording::Pause():Recording::Resume();writeStatus();respond(r,ok,ok?J{{"recording",true},{"paused",Recording::Paused()}}:J::object(),ok?"":"notRecording");}
else if(op=="record.stop"){if(stopRequest.is_object()){respond(r,false,J::object(),"busy");return;}if(!Recording::Active()){respond(r,false,J::object(),"notRecording");return;}stopRequest=r;Recording::Stop();}
else if(op=="editor.open"){wstring p=wide(a.value("path",std::string()));bool ok=localPath(p)&&NativeServices::Editor(p,error);respond(r,ok,J::object(),ok?"":(error.empty()?"invalidPath":error.c_str()));}
else if(op=="app.quit"){if(!a.empty()){respond(r,false,J::object(),"invalidRequest");return;}respond(r,true,{{"quitting",true}});PostMessageW(owner,WM_COMMAND,UX_EXIT,0);}
else if(op=="permissions.get")respond(r,true,{{"screenCapture","available"},{"accessibility","available"},{"files","available"}});
else if(op=="permissions.open"){std::string p=a.value("permission",std::string());if(p!="screenCapture"&&p!="accessibility"&&p!="files"){respond(r,false,J::object(),"invalidRequest");return;}GalaxyMessageBox(promptOwner(),L"Windows에서는 별도 화면 기록 승인을 켤 필요가 없습니다. 회사 보안 정책으로 캡처가 차단되면 관리자에게 확인하세요. 파일 접근은 폴더 선택 창에서 직접 허용합니다.",L"Windows 권한",MB_OK|MB_ICONINFORMATION);respond(r,true);}
else if(op=="settings.apply"){bool ok=NativeServices::ApplySettings(a,error);if(ok)writeStatus();respond(r,ok,ok?J{{"applied",true},{"settings",NativeServices::Settings()}}:J::object(),ok?"":error.c_str());}
else if(op=="phone.open"){NativeServices::ShowTool("phone");respond(r,true);}else if(op.rfind("phone.",0)==0)dispatchPhone(r);else if(op=="native.tools"){std::string tool=a.value("tool",std::string());if(tool!="image"&&tool!="pdf"&&tool!="capture"&&tool!="record"&&tool!="codes"&&tool!="phone"){respond(r,false,J::object(),"invalidRequest");return;}NativeServices::ShowTool(tool);respond(r,true);}}
catch(const std::runtime_error&e){const char*key=!strcmp(e.what(),"settingsFailed")?"settingsFailed":!strcmp(e.what(),"expired")?"expired":"invalidRequest";respond(r,false,J::object(),key);}catch(...){respond(r,false,J::object(),"invalidRequest");}}
static BOOL CALLBACK statusMonitor(HMONITOR monitor,HDC,LPRECT,LPARAM data){MONITORINFOEXW info={};info.cbSize=sizeof(info);if(GetMonitorInfoW(monitor,&info)){auto&list=*(J*)data;list.push_back({{"id",list.size()},{"name",utf8(info.szDevice)},{"x",info.rcMonitor.left},{"y",info.rcMonitor.top},{"width",info.rcMonitor.right-info.rcMonitor.left},{"height",info.rcMonitor.bottom-info.rcMonitor.top},{"primary",(info.dwFlags&MONITORINFOF_PRIMARY)!=0}});}return TRUE;}
static void writeStatus(){if(!state.empty()){J monitors=J::array();EnumDisplayMonitors(nullptr,nullptr,statusMonitor,(LPARAM)&monitors);atomicJson(state+L"\\bridge\\status.json",{{"version",1},{"pid",GetCurrentProcessId()},{"requestWindow",(uint64_t)(uintptr_t)owner},{"updatedAt",now()},{"os","Windows"},{"agentPort",currentPort()},{"recording",Recording::Active()},{"paused",Recording::Paused()},{"monitors",monitors},{"phoneControl",true},{"settings",NativeServices::Settings()}});}}
static void poll(){
 if(captureRequest.is_object()&&captureRequest.value("expiresAt",0.0)<=now()){std::string id=captureRequest.value("id",std::string());complete(captureRequest,false,J::object(),"expired");captureDocument.clear();NativeServices::CancelCapture(id);}
 for(J*r:{&recordRequest,&stopRequest})if(r->is_object()&&r->value("expiresAt",0.0)<=now())complete(*r,false,J::object(),"expired");
 WIN32_FIND_DATAW f;HANDLE find=FindFirstFileW((requests+L"\\*.json").c_str(),&f);if(find==INVALID_HANDLE_VALUE)return;int count=0;
 do{if(count>=12)break;if(f.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))continue;wstring file=f.cFileName;if(file.size()!=41)continue;std::string id=utf8(file.substr(0,36));if(!NativeProtocol::uuid(id))continue;wstring from=requests+L"\\"+file,to=processing+L"\\"+file;
  // Window selection pumps this timer inside its modal loop. Keep other queued
  // requests untouched while allowing only a UUID-scoped capture cancellation.
  if(dispatching){J peek=readJson(from);if(!peek.is_object()||!peek.contains("operation")||!peek["operation"].is_string()||peek["operation"]!="capture.cancel")continue;}
  ++count;if(!MoveFileExW(from.c_str(),to.c_str(),MOVEFILE_WRITE_THROUGH))continue;J r=readJson(to);std::string error=NativeProtocol::validate(r,id,now());if(!error.empty()){respond({{"id",id}},false,J::object(),error.c_str());continue;}std::string operation=r.value("operation",std::string());if(!NativeServices::CanDispatch()&&operation!="capture.cancel"&&operation!="record.stop"&&operation!="record.pause"&&operation!="record.resume"&&operation!="permissions.get"&&operation!="phone.status"&&operation!="phone.stop"){respond(r,false,J::object(),"busy");continue;}
  bool previousDispatching=dispatching;dispatching=true;bool modal=operation=="pair.approve"||operation=="folder.choose"||operation=="files.choose"||operation=="permissions.open";bool enabled=IsWindowEnabled(owner)!=FALSE;if(modal)EnableWindow(owner,FALSE);dispatch(r);if(modal&&enabled&&IsWindow(owner))EnableWindow(owner,TRUE);dispatching=previousDispatching;
 }while(FindNextFileW(find,&f));FindClose(find);
}
void Init(HWND hwnd,HINSTANCE h){StartupStage("nativeInit");owner=hwnd;app=h;wchar_t p[32768];DWORD n=GetModuleFileNameW(nullptr,p,32768);if(!n||n>=32768)return;PathRemoveFileSpecW(p);base=p;wchar_t local[32768];if(FAILED(SHGetFolderPathW(nullptr,CSIDL_LOCAL_APPDATA,nullptr,SHGFP_TYPE_CURRENT,local)))return;wstring parent=wstring(local)+L"\\GalaxyControl";SHCreateDirectoryExW(nullptr,parent.c_str(),nullptr);if(GetFileAttributesW(parent.c_str())&FILE_ATTRIBUTE_REPARSE_POINT)return;state=parent+L"\\Agent";processing=state+L"\\bridge\\processing";requests=state+L"\\bridge\\requests";responses=state+L"\\bridge\\responses";signals=state+L"\\bridge\\signals";for(auto path:{state,state+L"\\bridge",requests,responses,signals,processing,state+L"\\WebViewProfile"})if(!secureDir(path)){state.clear();return;}for(auto path:{base+L"\\resources\\tools-ui",base+L"\\tools-ui",base+L"\\tools\\tools-ui"})if(GetFileAttributesW((path+L"\\index.html").c_str())!=INVALID_FILE_ATTRIBUTES){uiDir=path;break;}if(uiDir.empty())uiDir=base+L"\\resources\\tools-ui";SetTimer(owner,PollTimer,250,nullptr);startThread=CreateThread(nullptr,0,startAgent,nullptr,0,nullptr);SharedHostWarm(owner,app,state+L"\\WebViewProfile",startHome);}
void SetInitialHome(bool b){startHome=b;}
bool Handle(UINT m,WPARAM w,LPARAM){
 if(m==ReadyMessage){
  ready=w!=0;
  if(ready){
   StartupStage("backendReady");if(!initialShortcut.empty())SharedHostOpen(owner,app,state+L"\\WebViewProfile",currentPort(),false);
   else if(openPending||startHome)OpenTools();
   else SharedHostOpen(owner,app,state+L"\\WebViewProfile",currentPort(),!UxTrayAvailable());
   if(!initialShortcut.empty()){std::string shortcut=initialShortcut;initialShortcut.clear();if(!SharedHostShortcut(shortcut))OpenTools();}
  }else if(startHome||openPending){
   SharedHostShowMessage(owner,app,L"프로그램을 시작하지 못했습니다. 폴더 전체를 다시 설치하거나 다시 시도해 주세요.");
  }
  openPending=false;return true;
 }
 if(((m==WM_TIMER&&w==PollTimer)||m==WM_APP+121)&&!state.empty()){
  ULONGLONG tick=GetTickCount64();
  if(tick-lastBeat>=2000){lastBeat=tick;if(ready&&InterlockedCompareExchange(&checkingHealth,1,0)==0){HANDLE thread=CreateThread(nullptr,0,checkHealth,nullptr,0,nullptr);if(thread)CloseHandle(thread);else InterlockedExchange(&checkingHealth,0);}writeStatus();}
  poll();return true;
 }
 return false;
}
void OpenTools(bool){
 NativeServices::CancelSelectionForOpen();
 if(!ready){
  if(state.empty()){SharedHostShowMessage(owner,app,L"프로그램 연결을 준비하지 못했습니다. 사용자 폴더의 접근 권한을 확인해 주세요.");return;}
  openPending=true;SharedHostShowLoading(owner,app);
  if(!startThread||WaitForSingleObject(startThread,0)==WAIT_OBJECT_0){if(startThread)CloseHandle(startThread);startThread=CreateThread(nullptr,0,startAgent,nullptr,0,nullptr);}
  return;
 }
 if(SharedHostOpen(owner,app,state+L"\\WebViewProfile",currentPort())){
  ShowWindow(owner,SW_HIDE);
  if(!pendingCategory.empty()){std::string category=pendingCategory;pendingCategory.clear();SharedHostNavigate(category);}
 }else SharedHostShowMessage(owner,app,L"프로그램 화면을 열지 못했습니다. 다시 시도해 주세요.");
}
void OpenCategory(const std::string&category){pendingCategory=category;OpenTools();}
void SetInitialShortcut(const std::string&shortcut){initialShortcut=shortcut;}
void RunShortcut(const std::string&shortcut){
 if(SharedHostShortcut(shortcut))return;
 initialShortcut=shortcut;
 if(ready){SharedHostOpen(owner,app,state+L"\\WebViewProfile",currentPort(),false);if(SharedHostShortcut(shortcut))initialShortcut.clear();}
 else if(!state.empty()&&(!startThread||WaitForSingleObject(startThread,0)==WAIT_OBJECT_0)){
  if(startThread)CloseHandle(startThread);startThread=CreateThread(nullptr,0,startAgent,nullptr,0,nullptr);
 }
}
void PrepareQuit(){if(ready&&InterlockedCompareExchange(&checkingHealth,1,0)==0){HANDLE thread=CreateThread(nullptr,0,checkHealth,nullptr,0,nullptr);if(thread)CloseHandle(thread);else InterlockedExchange(&checkingHealth,0);}}
void Shutdown(){InterlockedExchange(&shutting,1);KillTimer(owner,PollTimer);SharedHostShutdown();for(J*r:{&captureRequest,&recordRequest,&stopRequest})complete(*r,false,J::object(),"cancelled");if(startThread){WaitForSingleObject(startThread,10000);CloseHandle(startThread);startThread=nullptr;}if(!state.empty())DeleteFileW((state+L"\\bridge\\status.json").c_str());if(agentJob){CloseHandle(agentJob);agentJob=nullptr;}if(agentProcess){CloseHandle(agentProcess);agentProcess=nullptr;}}
bool Busy(){return InterlockedCompareExchange(&checkingHealth,0,0)>0||InterlockedCompareExchange(&backendJobs,0,0)!=0||dispatching||captureRequest.is_object()||recordRequest.is_object()||stopRequest.is_object();}
void Signal(const char*op){writeStatus();if(state.empty()||(strcmp(op,"web.capture")&&strcmp(op,"record.toggle")&&strcmp(op,"record.stop")))return;std::string id=guid();if(id.empty())return;atomicJson(signals+L"\\"+wide(id)+L".json",{{"id",id},{"operation",op},{"args",J::object()},{"createdAt",now()}});}
bool CaptureRequestLive(){return captureRequest.is_object()&&captureRequest.value("expiresAt",0.0)>now();}
bool RecordRequestLive(){return recordRequest.is_object()&&recordRequest.value("expiresAt",0.0)>now();}
void CaptureAccepted(const wstring&name){if(captureRequest.is_object())captureDocument=name;}
void CaptureOverlayShown(){if(captureRequest.is_object()&&captureRequest["args"].value("ephemeral",false))captureRequest["overlayShownAt"]=now()*1000;}
void CaptureImageAsync(std::function<std::vector<BYTE>()> encode){
 if(!captureRequest.is_object())return;
 J request=captureRequest;captureRequest=J();captureDocument.clear();const double selectedAt=now()*1000;const unsigned short port=currentPort();
 SharedHostAISelected();
 std::thread([request,encode=std::move(encode),selectedAt,port](){
  bool ok=false;std::vector<BYTE> bytes;
  try{
   std::string ident=request["args"].value("aiJobId",std::string());J sessionData=readJson(state+L"\\desktop-session.json");
   if(!NativeProtocol::uuid(ident)||!AgentEndpoint::validPort(port)||!sessionData.is_object())throw 1;
   std::string token=sessionData.value("token",std::string());if(token.empty()||token.size()>256)throw 1;
   bytes=encode();if(bytes.empty()||bytes.size()>16*1024*1024)throw 1;
   HINTERNET session=WinHttpOpen(L"KIOControl/4.6.23",WINHTTP_ACCESS_TYPE_NO_PROXY,nullptr,nullptr,0);
   if(session){
    WinHttpSetTimeouts(session,1500,1500,5000,5000);HINTERNET connection=WinHttpConnect(session,L"127.0.0.1",port,0);
    wstring path=L"/ai/frame/"+wide(ident);HINTERNET http=connection?WinHttpOpenRequest(connection,L"POST",path.c_str(),nullptr,WINHTTP_NO_REFERER,WINHTTP_DEFAULT_ACCEPT_TYPES,0):nullptr;
    if(http){
     DWORD policy=WINHTTP_OPTION_REDIRECT_POLICY_NEVER;WinHttpSetOption(http,WINHTTP_OPTION_REDIRECT_POLICY,&policy,sizeof(policy));
     wstring headers=L"Content-Type: image/png\r\nOrigin: http://127.0.0.1:"+std::to_wstring(port)+L"\r\nX-Local-Agent-Token: "+wide(token)+L"\r\n";
     if(WinHttpSendRequest(http,headers.c_str(),(DWORD)-1,bytes.data(),(DWORD)bytes.size(),(DWORD)bytes.size(),0)&&WinHttpReceiveResponse(http,nullptr)){DWORD code=0,n=sizeof(code);ok=WinHttpQueryHeaders(http,WINHTTP_QUERY_STATUS_CODE|WINHTTP_QUERY_FLAG_NUMBER,WINHTTP_HEADER_NAME_BY_INDEX,&code,&n,WINHTTP_NO_HEADER_INDEX)&&code==200;}
     SecureZeroMemory(headers.data(),headers.size()*sizeof(wchar_t));WinHttpCloseHandle(http);
    }
    if(connection)WinHttpCloseHandle(connection);WinHttpCloseHandle(session);
   }
   SecureZeroMemory(token.data(),token.size());
  }catch(...){ok=false;}
  if(!bytes.empty())SecureZeroMemory(bytes.data(),bytes.size());
  respond(request,ok,ok?J{{"selectedAt",selectedAt},{"overlayShownAt",request.value("overlayShownAt",selectedAt)}}:J::object(),ok?"":"aiInvalidImage");
 }).detach();
}
void CaptureSaved(const wstring&name,const wstring&path,bool ok){if(captureRequest.is_object()&&name==captureDocument){complete(captureRequest,ok,ok?J{{"paths",J::array({utf8(path)})}}:J::object(),ok?"":"saveFailed");captureDocument.clear();}}
void CaptureCancelled(const char*error){complete(captureRequest,false,J::object(),error);complete(recordRequest,false,J::object(),error);captureDocument.clear();}
void RecordStarted(bool ok){writeStatus();complete(recordRequest,ok,ok?J{{"recording",true}}:J::object(),ok?"":"recordFailed");}
void RecordFinished(bool ok,const wstring&path){writeStatus();if(recordRequest.is_object())complete(recordRequest,false,J::object(),"recordFailed");complete(stopRequest,ok,ok?J{{"paths",J::array({utf8(path)})}}:J::object(),ok?"":"recordFailed");}
const wstring&StateDir(){return state;}
}
