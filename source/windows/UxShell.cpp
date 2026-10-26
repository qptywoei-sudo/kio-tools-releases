#ifndef UNICODE
#define UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>
#include <commctrl.h>
#include <objbase.h>
#include <objidl.h>
#include <propidl.h>
#include <gdiplus.h>
#include <map>
#include <string>
#include "UxShell.h"
#include "I18N.h"
#include "AppIcon.h"
using namespace Gdiplus;using std::wstring;
static bool trayAdded=false;static HWND owner,tip;static HINSTANCE app;static int displayDpi;static NOTIFYICONDATAW tray={};static std::map<HWND,HICON>icons;static std::map<HWND,wstring>tips,translatedTips;
static KioLoginStartup::Store startupStore;
bool UxStartupEnabled(){return startupStore.requested();}
const char* UxStartupStatus(){return startupStore.status(KioLoginStartup::executable());}
void UxReconcileStartup(){startupStore.reconcile(KioLoginStartup::executable());}
bool UxReadStartupSnapshot(KioLoginStartup::Snapshot&snapshot){return startupStore.snapshot(snapshot);}
bool UxRestoreStartupSnapshot(const KioLoginStartup::Snapshot&snapshot){return startupStore.restore(snapshot);}
bool UxSetStartup(bool enabled){return startupStore.set(enabled,KioLoginStartup::executable());}
bool UxToggleStartup(){if(UxSetStartup(!UxStartupEnabled()))return true;GalaxyMessageBox(owner,L"로그인 자동 시작 설정을 저장하지 못했습니다. 회사 PC의 사용자 정책을 확인하세요.",L"로그인 자동 시작",MB_OK|MB_ICONWARNING);return false;}
static HICON icon(int kind){int n=MulDiv(28,displayDpi,96);Bitmap image(n,n,PixelFormat32bppARGB);Graphics g(&image);g.Clear(Color(0,0,0,0));g.ScaleTransform(n/28.f,n/28.f);g.SetSmoothingMode(SmoothingModeAntiAlias);Pen p(Color(255,252,117,1),2.2f);SolidBrush blue(Color(255,252,117,1));
 if(kind==0){PointF a[]={PointF(7,3),PointF(7,23),PointF(12,18),PointF(16,25),PointF(20,23),PointF(16,16),PointF(24,16)};g.FillPolygon(&blue,a,7);}
 else if(kind==1)g.DrawRectangle(&p,5.f,5.f,18.f,18.f);
 else if(kind==2)g.DrawEllipse(&p,4.f,6.f,20.f,16.f);
 else if(kind==3){g.DrawLine(&p,4,23,24,4);g.DrawLine(&p,14,4,24,4);g.DrawLine(&p,24,4,24,14);}
 else if(kind==4){PointF a[]={PointF(4,21),PointF(9,8),PointF(14,20),PointF(20,5),PointF(24,17)};g.DrawLines(&p,a,5);}
 else if(kind==5){g.DrawLine(&p,5,5,23,5);g.DrawLine(&p,14,5,14,24);g.DrawLine(&p,10,24,18,24);}
 else if(kind==6){for(int y=0;y<3;y++)for(int x=0;x<3;x++){SolidBrush b(Color(255,40+x*35,80+y*35,155+x*20));g.FillRectangle(&b,4+x*7,4+y*7,6,6);}}
 else if(kind==7){for(int r=10;r>0;r-=2){SolidBrush b(Color(45,252,117,1));g.FillEllipse(&b,14.f-r,14.f-r,2.f*r,2.f*r);}}
 else if(kind==12){g.DrawLine(&p,7,3,7,21);g.DrawLine(&p,3,7,21,7);g.DrawLine(&p,21,7,21,25);g.DrawLine(&p,7,21,25,21);}
 else if(kind==100){g.DrawRectangle(&p,3.f,7.f,22.f,16.f);g.DrawEllipse(&p,9.f,10.f,10.f,10.f);g.DrawLine(&p,9,7,11,3);g.DrawLine(&p,11,3,18,3);}
 else if(kind==101){g.DrawRectangle(&p,3.f,8.f,22.f,15.f);g.DrawLine(&p,3,8,3,4);g.DrawLine(&p,3,4,12,4);}
 else if(kind==102){g.DrawRectangle(&p,3.f,5.f,15.f,15.f);g.DrawRectangle(&p,10.f,12.f,15.f,13.f);g.DrawLine(&p,17,15,17,23);g.DrawLine(&p,13,19,21,19);}
 else if(kind==103){g.DrawRectangle(&p,3.f,3.f,16.f,17.f);g.DrawRectangle(&p,10.f,10.f,15.f,15.f);}
 else if(kind==104){g.DrawRectangle(&p,4.f,3.f,20.f,22.f);g.DrawRectangle(&p,8.f,3.f,12.f,8.f);g.DrawRectangle(&p,8.f,16.f,12.f,9.f);}
 else if(kind==105||kind==106){if(kind==106){g.TranslateTransform(28,0);g.ScaleTransform(-1,1);}g.DrawArc(&p,6,8,18,16,190,210);g.DrawLine(&p,5,15,5,5);g.DrawLine(&p,5,15,14,14);}
 else if(kind==108){PointF a[]={PointF(5,10),PointF(23,10),PointF(14,20)};g.FillPolygon(&blue,a,3);}
 else if(kind==107){SolidBrush b(Color(255,225,80,70));g.FillEllipse(&b,4.f,4.f,20.f,20.f);}
 else{g.DrawRectangle(&p,5.f,5.f,18.f,18.f);}HICON out=nullptr;image.GetHICON(&out);return out;}
void UxSetIcon(HWND h,int kind){auto i=icons.find(h);if(i!=icons.end())DestroyIcon(i->second);HICON value=icon(kind);icons[h]=value;SendMessageW(h,BM_SETIMAGE,IMAGE_ICON,(LPARAM)value);}
void UxTooltip(HWND h){wchar_t text[512];GetWindowTextW(h,text,512);auto source=(wstring*)GetPropW(h,L"GalaxyOriginalText");tips[h]=source?*source:text;TOOLINFOW info={sizeof(info)};info.uFlags=TTF_IDISHWND|TTF_SUBCLASS;info.hwnd=owner;info.uId=(UINT_PTR)h;translatedTips[h]=GalaxyTr(tips[h].c_str());info.lpszText=translatedTips[h].data();SendMessageW(tip,TTM_ADDTOOLW,0,(LPARAM)&info);}
void UxRefreshTooltips(){for(auto&item:tips){TOOLINFOW info={sizeof(info)};info.hwnd=owner;info.uId=(UINT_PTR)item.first;translatedTips[item.first]=GalaxyTr(item.second.c_str());info.lpszText=translatedTips[item.first].data();SendMessageW(tip,TTM_UPDATETIPTEXTW,0,(LPARAM)&info);}}
void UxTrayMenu(){HMENU menu=CreatePopupMenu();AppendMenuW(menu,MF_STRING,UX_SHARED,GalaxyTr(L"Bogo Tools 열기"));AppendMenuW(menu,MF_STRING,UX_OPEN,GalaxyTr(L"설정"));AppendMenuW(menu,MF_STRING,UX_CAPTURE,GalaxyTr(L"영역 캡처"));AppendMenuW(menu,MF_STRING|(UxStartupEnabled()?MF_CHECKED:0),UX_STARTUP,GalaxyTr(L"로그인 때 자동 시작"));AppendMenuW(menu,MF_SEPARATOR,0,nullptr);AppendMenuW(menu,MF_STRING,UX_EXIT,GalaxyTr(L"완전히 종료"));POINT p;GetCursorPos(&p);SetForegroundWindow(owner);UINT choice=TrackPopupMenu(menu,TPM_RETURNCMD|TPM_RIGHTBUTTON,p.x,p.y,0,owner,nullptr);DestroyMenu(menu);if(choice)PostMessageW(owner,WM_COMMAND,choice,0);PostMessageW(owner,WM_NULL,0,0);}
bool UxTrayEvent(LPARAM l){UINT event=LOWORD(l);if(event==WM_CONTEXTMENU||event==WM_RBUTTONUP){UxTrayMenu();return true;}if(event==WM_LBUTTONUP||event==WM_LBUTTONDBLCLK||event==NIN_SELECT||event==NIN_KEYSELECT){PostMessageW(owner,WM_COMMAND,UX_SHARED,0);return true;}return false;}
void UxInit(HWND h,HINSTANCE a,int dpi){owner=h;app=a;displayDpi=dpi;tip=CreateWindowExW(WS_EX_TOPMOST,TOOLTIPS_CLASSW,nullptr,WS_POPUP|TTS_ALWAYSTIP|TTS_NOPREFIX,0,0,0,0,owner,nullptr,app,nullptr);SendMessageW(tip,TTM_SETMAXTIPWIDTH,0,500);tray.cbSize=sizeof(tray);tray.hWnd=owner;tray.uID=1;tray.uFlags=NIF_ICON|NIF_MESSAGE|NIF_TIP;tray.uCallbackMessage=UX_TRAY_MESSAGE;tray.hIcon=GalaxyAppIcon(app,GetSystemMetrics(SM_CXSMICON));wcscpy(tray.szTip,L"Bogo Tools 4.6.23");UxRestoreTray();}
bool UxTrayAvailable(){return trayAdded;}
void UxRestoreTray(){tray.uVersion=0;trayAdded=Shell_NotifyIconW(NIM_ADD,&tray)!=FALSE;if(!trayAdded)trayAdded=Shell_NotifyIconW(NIM_MODIFY,&tray)!=FALSE;if(trayAdded){tray.uVersion=NOTIFYICON_VERSION_4;Shell_NotifyIconW(NIM_SETVERSION,&tray);}}
void UxDestroy(){if(trayAdded)Shell_NotifyIconW(NIM_DELETE,&tray);trayAdded=false;for(auto&i:icons)DestroyIcon(i.second);icons.clear();tips.clear();translatedTips.clear();if(tip)DestroyWindow(tip);}
