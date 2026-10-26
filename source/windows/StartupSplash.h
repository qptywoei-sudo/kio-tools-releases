#pragma once
#include <gdiplus.h>
#include "I18N.h"
#include <shlwapi.h>
#include <memory>
#include <vector>

namespace KioStartup {
inline constexpr UINT timer=847;
inline IStream* stream=nullptr;
inline std::unique_ptr<Gdiplus::Image> image;
inline UINT frame=0,count=1;
inline std::vector<UINT> delays;
inline bool reduced=false;
inline void load(HINSTANCE instance){
 if(image)return;
 BOOL motion=TRUE;SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION,0,&motion,0);reduced=!motion;
 auto resource=FindResourceW(instance,MAKEINTRESOURCEW(203),RT_RCDATA);
 if(!resource)return;
 auto bytes=(const BYTE*)LockResource(LoadResource(instance,resource));auto size=SizeofResource(instance,resource);
 if(!bytes||!size||size>256*1024)return;
 HGLOBAL storage=GlobalAlloc(GMEM_MOVEABLE,size);if(!storage)return;void* memory=GlobalLock(storage);if(!memory){GlobalFree(storage);return;}memcpy(memory,bytes,size);GlobalUnlock(storage);if(FAILED(CreateStreamOnHGlobal(storage,TRUE,&stream))){GlobalFree(storage);stream=nullptr;return;}
 image.reset(Gdiplus::Image::FromStream(stream,FALSE));
 if(!image||image->GetLastStatus()!=Gdiplus::Ok){image.reset();stream->Release();stream=nullptr;return;}
 count=std::max(1u,std::min(60u,image->GetFrameCount(&Gdiplus::FrameDimensionTime)));
 delays.assign(count,80);
 UINT length=image->GetPropertyItemSize(PropertyTagFrameDelay);
 if(length>=sizeof(Gdiplus::PropertyItem)&&length<4096){
  std::vector<BYTE> property(length);auto value=(Gdiplus::PropertyItem*)property.data();
  if(image->GetPropertyItem(PropertyTagFrameDelay,length,value)==Gdiplus::Ok&&value->length>=count*sizeof(UINT)){
   for(UINT n=0;n<count;n++)delays[n]=std::max(40u,std::min(500u,((UINT*)value->value)[n]*10));
  }
 }
}
inline void resume(HWND window){if(image&&!reduced&&count>1)SetTimer(window,timer,delays[frame],nullptr);}
inline void tick(HWND window){
 if(image&&IsWindowVisible(window)&&!reduced){frame=(frame+1)%count;image->SelectActiveFrame(&Gdiplus::FrameDimensionTime,frame);InvalidateRect(window,nullptr,FALSE);SetTimer(window,timer,delays[frame],nullptr);}
}
inline void paint(HWND window){
 PAINTSTRUCT ps;HDC dc=BeginPaint(window,&ps);RECT r;GetClientRect(window,&r);
 const float dpi=GetDpiForWindow(window)/96.f,w=(float)r.right,h=(float)r.bottom;
 HDC buffer=CreateCompatibleDC(dc);HBITMAP bitmap=CreateCompatibleBitmap(dc,std::max(1L,r.right),std::max(1L,r.bottom));auto old=SelectObject(buffer,bitmap);
 {
  Gdiplus::Graphics g(buffer);g.Clear(Gdiplus::Color(255,255,250,246));g.SetInterpolationMode(Gdiplus::InterpolationModeHighQualityBicubic);g.SetTextRenderingHint(Gdiplus::TextRenderingHintAntiAliasGridFit);
  float size=std::min(240.f*dpi,std::max(120.f*dpi,std::min(w*.7f,h*.46f))),top=(h-(size+82*dpi))/2;
  if(image)g.DrawImage(image.get(),Gdiplus::RectF((w-size)/2,top,size,size));
  Gdiplus::StringFormat format;format.SetAlignment(Gdiplus::StringAlignmentCenter);format.SetLineAlignment(Gdiplus::StringAlignmentNear);
  Gdiplus::Font title(L"Segoe UI",26*dpi,Gdiplus::FontStyleBold,Gdiplus::UnitPixel),hint(L"Segoe UI",13*dpi,Gdiplus::FontStyleRegular,Gdiplus::UnitPixel);
  Gdiplus::SolidBrush ink(Gdiplus::Color(255,52,43,38)),muted(Gdiplus::Color(255,120,91,72));
  g.DrawString(GalaxyTr(L"Bogo Tools를 준비하고 있어요"),-1,&title,Gdiplus::RectF(12*dpi,top+size+10*dpi,w-24*dpi,38*dpi),&format,&ink);
  g.DrawString(GalaxyTr(L"잠시만 기다려 주세요"),-1,&hint,Gdiplus::RectF(12*dpi,top+size+48*dpi,w-24*dpi,24*dpi),&format,&muted);
 }
 BitBlt(dc,0,0,r.right,r.bottom,buffer,0,0,SRCCOPY);SelectObject(buffer,old);DeleteObject(bitmap);DeleteDC(buffer);EndPaint(window,&ps);
}
inline void close(HWND window){KillTimer(window,timer);image.reset();if(stream){stream->Release();stream=nullptr;}frame=0;count=1;delays.clear();}
}


