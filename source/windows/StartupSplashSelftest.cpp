#define UNICODE
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <objidl.h>
#include <algorithm>
#include <cassert>
#include <iostream>
#include <set>
#include "StartupSplash.h"
extern "C" const wchar_t*GalaxyTr(const wchar_t*s){return s;}
int main(){
 HRESULT initialized=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);assert(SUCCEEDED(initialized));
 Gdiplus::GdiplusStartupInput input;ULONG_PTR token=0;assert(Gdiplus::GdiplusStartup(&token,&input,nullptr)==Gdiplus::Ok);
 KioStartup::load(GetModuleHandleW(nullptr));assert(KioStartup::image&&KioStartup::stream);
 GUID format={};assert(KioStartup::image->GetRawFormat(&format)==Gdiplus::Ok&&IsEqualGUID(format,Gdiplus::ImageFormatPNG));
 assert(KioStartup::count==1&&KioStartup::frame==0&&KioStartup::delays.size()==1);
 assert(KioStartup::image->GetWidth()==240&&KioStartup::image->GetHeight()==240);
 BOOL motion=TRUE;SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION,0,&motion,0);assert(KioStartup::reduced==!motion);
 auto loaded=KioStartup::image.get();KioStartup::load(GetModuleHandleW(nullptr));assert(KioStartup::image.get()==loaded&&KioStartup::count==1);
 {Gdiplus::Bitmap bitmap(240,240,PixelFormat32bppARGB);assert(bitmap.GetLastStatus()==Gdiplus::Ok);
 {Gdiplus::Graphics g(&bitmap);assert(g.Clear(Gdiplus::Color(0,0,0,0))==Gdiplus::Ok);assert(g.DrawImage(KioStartup::image.get(),0,0,240,240)==Gdiplus::Ok);}
 Gdiplus::BitmapData data;Gdiplus::Rect r(0,0,240,240);assert(bitmap.LockBits(&r,Gdiplus::ImageLockModeRead,PixelFormat32bppARGB,&data)==Gdiplus::Ok);
 unsigned visible=0;std::set<unsigned> colors;
 for(int y=0;y<240;y++)for(int x=0;x<240;x++){auto pixel=(BYTE*)data.Scan0+y*data.Stride+x*4;if(pixel[3]){visible++;colors.insert((unsigned(pixel[3])<<24)|(unsigned(pixel[2])<<16)|(unsigned(pixel[1])<<8)|pixel[0]);}}
 assert(bitmap.UnlockBits(&data)==Gdiplus::Ok);assert(visible>0&&colors.size()>1);}
 KioStartup::close(nullptr);assert(!KioStartup::image&&!KioStartup::stream&&KioStartup::frame==0&&KioStartup::count==1&&KioStartup::delays.empty());
 Gdiplus::GdiplusShutdown(token);CoUninitialize();std::cout<<"Native PNG: static 240x240 resource decoded and rendered; reduced-motion preference retained; resources released\n";
}
