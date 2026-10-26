#ifndef UNICODE
#define UNICODE
#endif
#define NOMINMAX
#include <windows.h>
#include <commctrl.h>
#include <shlobj.h>
#include <fstream>
#include <atomic>
#include <vector>
#include <map>
#include "include/json.hpp"
#include "I18N.h"
#include "LanguagePolicy.h"
#include <set>
using std::wstring;static nlohmann::json catalog;static std::atomic<int>selected(1);static wstring config;static const char*codes[]={"vi","en","ko","ja","zh-TW","zh-CN"};static bool manualLanguage=false;static wstring preference;static std::map<std::pair<HMENU,int>,wstring>menus;
static std::string utf8(const wstring&s){int n=WideCharToMultiByte(CP_UTF8,0,s.c_str(),(int)s.size(),nullptr,0,nullptr,nullptr);std::string r(n,0);if(n)WideCharToMultiByte(CP_UTF8,0,s.c_str(),(int)s.size(),r.data(),n,nullptr,nullptr);return r;}static wstring wide(const std::string&s){int n=MultiByteToWideChar(CP_UTF8,0,s.c_str(),(int)s.size(),nullptr,0);wstring r(n,0);if(n)MultiByteToWideChar(CP_UTF8,0,s.c_str(),(int)s.size(),r.data(),n);return r;}
static std::string osLanguage(){
 ULONG count=0,size=0;GetUserPreferredUILanguages(MUI_LANGUAGE_NAME,&count,nullptr,&size);
 if(size>1&&size<65536){std::vector<wchar_t> languages(size);if(GetUserPreferredUILanguages(MUI_LANGUAGE_NAME,&count,languages.data(),&size)&&languages[0])return KioLanguage::normalize(utf8(languages.data()));}
 wchar_t locale[LOCALE_NAME_MAX_LENGTH]={};if(GetUserDefaultLocaleName(locale,LOCALE_NAME_MAX_LENGTH))return KioLanguage::normalize(utf8(locale));return {};
}
void I18NInit(){
 wchar_t path[32768]={},data[MAX_PATH]={};DWORD length=GetModuleFileNameW(nullptr,path,32768);if(!length||length>=32768)path[0]=0;
 wstring base=path;auto n=base.find_last_of(L"\\/");if(n!=wstring::npos)base.resize(n);
 std::ifstream in((base+L"\\tools\\i18n\\locales.json").c_str(),std::ios::binary);try{in>>catalog;}catch(...){catalog=nlohmann::json::object();}
 SHGetFolderPathW(nullptr,CSIDL_LOCAL_APPDATA,nullptr,SHGFP_TYPE_CURRENT,data);wstring dir=wstring(data)+L"\\GalaxyControl";SHCreateDirectoryExW(nullptr,dir.c_str(),nullptr);
 config=dir+L"\\Language.ini";preference=dir+L"\\Agent\\language-preference.json";
 std::string chosen;try{nlohmann::json saved;std::ifstream file(preference.c_str());file>>saved;if(saved.value("source","")=="user")chosen=KioLanguage::normalize(saved.value("language",""));}catch(...){}
 // Old numeric indices retain their original meaning after the list is reordered.
 if(chosen.empty()){wchar_t saved[32]={};GetPrivateProfileStringW(L"ui",L"code",L"",saved,32,config.c_str());chosen=KioLanguage::normalize(utf8(saved));
  if(chosen.empty()){int legacy=GetPrivateProfileIntW(L"ui",L"language",-1,config.c_str());const char*old[]={"ko","en","vi","ja","zh-CN"};if(legacy>=0&&legacy<5)chosen=old[legacy];}}
 manualLanguage=!chosen.empty();if(chosen.empty())chosen=osLanguage();selected=KioLanguage::index(chosen.empty()?"en":chosen);
}
int I18NSelectedLanguage(){return selected.load();}
const char*I18NLanguage(){return codes[selected.load()];}
const char*I18NLanguageSource(){return manualLanguage?"user":"system";}
void I18NSetLanguage(int value){
 if(value<0||value>=6)return;selected=value;manualLanguage=true;
 wstring dir=preference.substr(0,preference.find_last_of(L"\\/"));SHCreateDirectoryExW(nullptr,dir.c_str(),nullptr);
 nlohmann::json saved={{"schemaVersion",1},{"language",codes[value]},{"source","user"}};
 wstring temp=preference+L".native.tmp";{std::ofstream file(temp.c_str(),std::ios::binary);file<<saved.dump();}
 if(!MoveFileExW(temp.c_str(),preference.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))OutputDebugStringW(L"KIO i18n: preferenceWriteFailed\n");
 WritePrivateProfileStringW(L"ui",L"code",wide(codes[value]).c_str(),config.c_str());
 // Also retain the legacy index for older installations sharing this profile.
 const int legacy[]={2,1,0,3,4,4};wchar_t b[12];swprintf(b,12,L"%d",legacy[value]);WritePrivateProfileStringW(L"ui",L"language",b,config.c_str());
}
static bool translateExact(const wstring&input,wstring&output,const std::string&lang){auto key=utf8(input);if(catalog.contains(key)&&catalog[key].is_object()&&catalog[key].contains(lang)&&catalog[key][lang].is_string()){output=wide(catalog[key][lang].get<std::string>());return true;}return false;}
extern "C" const wchar_t*GalaxyTr(const wchar_t*s){thread_local wstring results[16];thread_local int next=0;wstring&out=results[(next++)%16];out=s?s:L"";wstring source=out;std::string lang=I18NLanguage();if(translateExact(source,out,lang))return out.c_str();size_t colon=source.find(L": ");if(colon!=wstring::npos){wstring translated;if(translateExact(source.substr(0,colon+2),translated,lang)){out=translated+source.substr(colon+2);return out.c_str();}}
 for(auto prefix:{L"모니터 ",L"페이지 ",L"● 녹화 중 ",L"자동 저장 완료: ",L"녹화 완료: ",L"저장 위치: "}){size_t length=wcslen(prefix);wstring translated;if(source.compare(0,length,prefix)==0&&translateExact(prefix,translated,lang)){out=translated+source.substr(length);return out.c_str();}}
 if(source.find(L"\r\n\r\n")!=wstring::npos){out.clear();size_t at=0;while(at<source.size()){size_t end=source.find(L"\r\n\r\n",at);size_t length=end==wstring::npos?source.size()-at:end-at+4;wstring part=source.substr(at,length),translated;if(translateExact(part,translated,lang))out+=translated;else if(end!=wstring::npos&&translateExact(source.substr(at,end-at),translated,lang))out+=translated+L"\r\n\r\n";else out+=part;at+=length;}}
 if(out==source){wstring fallback;if(translateExact(source,fallback,"en"))out=fallback;else{static std::set<wstring>missing;if(missing.insert(source).second)OutputDebugStringW(L"KIO i18n: missingTranslation\n");}}
 return out.c_str();}

extern "C" void GalaxyRegisterText(HWND h,const wchar_t*s){if(!h||!s||GetDlgCtrlID(h)==600)return;wchar_t cls[32];GetClassNameW(h,cls,32);if(!wcscmp(cls,L"Edit")&&!(GetWindowLongPtrW(h,GWL_STYLE)&ES_READONLY))return;auto old=(wstring*)RemovePropW(h,L"GalaxyOriginalText");delete old;SetPropW(h,L"GalaxyOriginalText",new wstring(s));}
extern "C" void GalaxySetText(HWND h,const wchar_t*s){GalaxyRegisterText(h,s);wchar_t cls[32];GetClassNameW(h,cls,32);bool user=!wcscmp(cls,L"Edit")&&!(GetWindowLongPtrW(h,GWL_STYLE)&ES_READONLY);SetWindowTextW(h,user?s:GalaxyTr(s));}
extern "C" const wchar_t* GalaxyFileFilter(const wchar_t*source){thread_local wstring buffers[4];thread_local int next=0;auto&out=buffers[(next++)%4];out.clear();if(source)for(const wchar_t*p=source;*p;p+=wcslen(p)+1){out+=GalaxyTr(p);out.push_back(0);}out.push_back(0);return out.c_str();}
extern "C" void GalaxyCueBanner(HWND h,const wchar_t*s){delete (wstring*)RemovePropW(h,L"GalaxyOriginalCue");SetPropW(h,L"GalaxyOriginalCue",new wstring(s?s:L""));SendMessageW(h,EM_SETCUEBANNER,TRUE,(LPARAM)GalaxyTr(s));}
static BOOL CALLBACK tree(HWND h,LPARAM){if(GetDlgCtrlID(h)==600)return TRUE;wchar_t cls[40];GetClassNameW(h,cls,40);if(!wcscmp(cls,L"ComboBox")){wchar_t parentClass[64];GetClassNameW(GetParent(h),parentClass,64);if(GetDlgCtrlID(h)==108&&!wcscmp(parentClass,L"GalaxyControlPortable"))return TRUE;auto originals=(std::vector<wstring>*)GetPropW(h,L"GalaxyOriginalItems");if(!originals){originals=new std::vector<wstring>;int n=(int)SendMessageW(h,CB_GETCOUNT,0,0);for(int i=0;i<n;i++){int len=(int)SendMessageW(h,CB_GETLBTEXTLEN,i,0);wstring s(len+1,0);SendMessageW(h,CB_GETLBTEXT,i,(LPARAM)s.data());s.resize(len);originals->push_back(s);}SetPropW(h,L"GalaxyOriginalItems",originals);}int at=(int)SendMessageW(h,CB_GETCURSEL,0,0);SendMessageW(h,CB_RESETCONTENT,0,0);for(auto&s:*originals)SendMessageW(h,CB_ADDSTRING,0,(LPARAM)GalaxyTr(s.c_str()));SendMessageW(h,CB_SETCURSEL,at,0);}
else if(!wcscmp(cls,WC_TABCONTROLW)){auto originals=(std::vector<wstring>*)GetPropW(h,L"GalaxyOriginalItems");if(!originals){originals=new std::vector<wstring>;for(int i=0;i<TabCtrl_GetItemCount(h);i++){wchar_t b[256];TCITEMW t={};t.mask=TCIF_TEXT;t.pszText=b;t.cchTextMax=256;TabCtrl_GetItem(h,i,&t);originals->push_back(b);}SetPropW(h,L"GalaxyOriginalItems",originals);}for(size_t i=0;i<originals->size();i++){TCITEMW t={};t.mask=TCIF_TEXT;t.pszText=(LPWSTR)GalaxyTr((*originals)[i].c_str());TabCtrl_SetItem(h,i,&t);}}
else{auto cue=(wstring*)GetPropW(h,L"GalaxyOriginalCue");if(cue)SendMessageW(h,EM_SETCUEBANNER,TRUE,(LPARAM)GalaxyTr(cue->c_str()));auto original=(wstring*)GetPropW(h,L"GalaxyOriginalText");if(!original){int n=GetWindowTextLengthW(h);wstring s(n+1,0);GetWindowTextW(h,s.data(),n+1);s.resize(n);GalaxyRegisterText(h,s.c_str());original=(wstring*)GetPropW(h,L"GalaxyOriginalText");}if(original)SetWindowTextW(h,GalaxyTr(original->c_str()));}return TRUE;}
void I18NLocalizeTree(HWND root){tree(root,0);EnumChildWindows(root,tree,0);I18NLocalizeMenu(GetMenu(root));DrawMenuBar(root);}
extern "C" void GalaxyLocalizeWindow(HWND root){I18NLocalizeTree(root);}
void I18NLocalizeMenu(HMENU m){if(!m)return;int n=GetMenuItemCount(m);for(int i=0;i<n;i++){auto key=std::make_pair(m,i);MENUITEMINFOW info={};wchar_t text[512];info.cbSize=sizeof(info);info.fMask=MIIM_STRING|MIIM_SUBMENU;info.dwTypeData=text;info.cch=512;GetMenuItemInfoW(m,i,TRUE,&info);if(!menus.count(key))menus[key]=text;MENUITEMINFOW update={};update.cbSize=sizeof(update);update.fMask=MIIM_STRING;update.dwTypeData=(LPWSTR)GalaxyTr(menus[key].c_str());SetMenuItemInfoW(m,i,TRUE,&update);I18NLocalizeMenu(info.hSubMenu);}}

struct HelpWindow{HWND edit=nullptr,button=nullptr;HFONT font=nullptr;bool done=false;wstring text;};
static LRESULT CALLBACK helpProc(HWND h,UINT message,WPARAM w,LPARAM l){auto data=(HelpWindow*)GetWindowLongPtrW(h,GWLP_USERDATA);
 if(message==WM_CREATE){data=(HelpWindow*)((CREATESTRUCTW*)l)->lpCreateParams;SetWindowLongPtrW(h,GWLP_USERDATA,(LONG_PTR)data);HDC dc=GetDC(h);int dpi=GetDeviceCaps(dc,LOGPIXELSY);ReleaseDC(h,dc);data->font=CreateFontW(-MulDiv(16,dpi,96),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Segoe UI");data->edit=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",data->text.c_str(),WS_CHILD|WS_VISIBLE|ES_MULTILINE|ES_READONLY|ES_AUTOVSCROLL|WS_VSCROLL|WS_TABSTOP,16,16,700,400,h,(HMENU)1,GetModuleHandleW(nullptr),nullptr);data->button=CreateWindowW(L"BUTTON",GalaxyTr(L"닫기"),WS_CHILD|WS_VISIBLE|BS_DEFPUSHBUTTON|WS_TABSTOP,16,430,110,34,h,(HMENU)2,GetModuleHandleW(nullptr),nullptr);SendMessageW(data->edit,WM_SETFONT,(WPARAM)data->font,TRUE);SendMessageW(data->button,WM_SETFONT,(WPARAM)data->font,TRUE);return 0;}
 if(message==WM_SIZE&&data){RECT r;GetClientRect(h,&r);MoveWindow(data->edit,16,16,std::max(1L,r.right-32),std::max(1L,r.bottom-78),TRUE);MoveWindow(data->button,std::max(16L,r.right-126),r.bottom-50,110,34,TRUE);return 0;}
 if((message==WM_COMMAND&&LOWORD(w)==2)||message==WM_CLOSE){if(data)data->done=true;return 0;}return DefWindowProcW(h,message,w,l);
}
extern "C" int GalaxyMessageBox(HWND owner,const wchar_t*body,const wchar_t*title,UINT flags){wstring translated=GalaxyTr(body),caption=GalaxyTr(title);if(translated.size()<700||(flags&MB_TYPEMASK)!=MB_OK)return MessageBoxW(owner,translated.c_str(),caption.c_str(),flags);
 WNDCLASSW c={};c.hInstance=GetModuleHandleW(nullptr);c.lpfnWndProc=helpProc;c.lpszClassName=L"GalaxyControlHelp";c.hCursor=LoadCursorW(nullptr,IDC_ARROW);c.hbrBackground=GetSysColorBrush(COLOR_WINDOW);RegisterClassW(&c);RECT work;SystemParametersInfoW(SPI_GETWORKAREA,0,&work,0);int width=std::min(820L,work.right-work.left-40),height=std::min(650L,work.bottom-work.top-60);HelpWindow data;data.text=translated;HWND h=CreateWindowExW(WS_EX_DLGMODALFRAME,c.lpszClassName,caption.c_str(),WS_OVERLAPPEDWINDOW,work.left+(work.right-work.left-width)/2,work.top+(work.bottom-work.top-height)/2,width,height,owner,nullptr,c.hInstance,&data);if(!h)return MessageBoxW(owner,translated.c_str(),caption.c_str(),flags);if(owner)EnableWindow(owner,FALSE);ShowWindow(h,SW_SHOW);MSG msg={};while(!data.done&&GetMessageW(&msg,nullptr,0,0)>0){if(msg.message==WM_KEYDOWN&&msg.wParam==VK_ESCAPE){data.done=true;break;}if(!IsDialogMessageW(h,&msg)){TranslateMessage(&msg);DispatchMessageW(&msg);}}DestroyWindow(h);if(data.font)DeleteObject(data.font);if(owner){EnableWindow(owner,TRUE);SetForegroundWindow(owner);}return IDOK;
}
