#ifndef GALAXY_CAPTURE_PIXELS_H
#define GALAXY_CAPTURE_PIXELS_H
#include <vector>
#include <algorithm>
#include <cstdint>
#include <cmath>
namespace CapturePixels {
struct Point { double x,y; };
struct Image { int w=0,h=0; std::vector<uint32_t> pixels; };
struct Rect { int x,y,w,h; };
inline Rect clamp(Rect r,int w,int h) { int x=std::max(0,std::min(w,r.x)),y=std::max(0,std::min(h,r.y)); int right=std::max(x,std::min(w,r.x+r.w)),bottom=std::max(y,std::min(h,r.y+r.h));return {x,y,right-x,bottom-y}; }
inline void fillRect(Image&image,Rect area,uint32_t color){if(image.w<=0||image.h<=0||image.pixels.size()!=(size_t)image.w*image.h)return;area=clamp(area,image.w,image.h);for(int y=area.y;y<area.y+area.h;y++)std::fill_n(image.pixels.begin()+(size_t)y*image.w+area.x,area.w,color);}
inline uint32_t pack(unsigned a,unsigned r,unsigned g,unsigned b) { return (a<<24)|(r<<16)|(g<<8)|b; }
inline void mosaic(Image &image,Rect area,int block) {
 area=clamp(area,image.w,image.h);block=std::max(2,block);
 for(int y=area.y;y<area.y+area.h;y+=block) for(int x=area.x;x<area.x+area.w;x+=block){
  int ex=std::min(x+block,area.x+area.w),ey=std::min(y+block,area.y+area.h);uint64_t a=0,r=0,g=0,b=0,n=0;
  for(int yy=y;yy<ey;yy++)for(int xx=x;xx<ex;xx++){uint32_t p=image.pixels[yy*image.w+xx];a+=p>>24;r+=(p>>16)&255;g+=(p>>8)&255;b+=p&255;n++;}
  uint32_t avg=pack((unsigned)(a/n),(unsigned)(r/n),(unsigned)(g/n),(unsigned)(b/n));
  for(int yy=y;yy<ey;yy++)for(int xx=x;xx<ex;xx++)image.pixels[yy*image.w+xx]=avg;
 }
}
inline void blur(Image &image,Rect area,int radius) {
 area=clamp(area,image.w,image.h);if(area.w<1||area.h<1)return;radius=std::max(1,std::min(100,radius));
 std::vector<uint32_t> horizontal((size_t)area.w*area.h);
 for(int y=0;y<area.h;y++){
  uint64_t a=0,r=0,g=0,b=0;int left=0,right=-1;
  for(int x=0;x<area.w;x++){
   int wantLeft=std::max(0,x-radius),wantRight=std::min(area.w-1,x+radius);
   while(right<wantRight){uint32_t p=image.pixels[(area.y+y)*image.w+area.x+(++right)];a+=p>>24;r+=(p>>16)&255;g+=(p>>8)&255;b+=p&255;}
   while(left<wantLeft){uint32_t p=image.pixels[(area.y+y)*image.w+area.x+(left++)];a-=p>>24;r-=(p>>16)&255;g-=(p>>8)&255;b-=p&255;}
   unsigned n=(unsigned)(right-left+1);horizontal[y*area.w+x]=pack((unsigned)(a/n),(unsigned)(r/n),(unsigned)(g/n),(unsigned)(b/n));
  }
 }
 for(int x=0;x<area.w;x++){
  uint64_t a=0,r=0,g=0,b=0;int top=0,bottom=-1;
  for(int y=0;y<area.h;y++){
   int wantTop=std::max(0,y-radius),wantBottom=std::min(area.h-1,y+radius);
   while(bottom<wantBottom){uint32_t p=horizontal[(++bottom)*area.w+x];a+=p>>24;r+=(p>>16)&255;g+=(p>>8)&255;b+=p&255;}
   while(top<wantTop){uint32_t p=horizontal[(top++)*area.w+x];a-=p>>24;r-=(p>>16)&255;g-=(p>>8)&255;b-=p&255;}
   unsigned n=(unsigned)(bottom-top+1);image.pixels[(area.y+y)*image.w+area.x+x]=pack((unsigned)(a/n),(unsigned)(r/n),(unsigned)(g/n),(unsigned)(b/n));
  }
 }
}
inline bool inside(const std::vector<Point>&p,double x,double y){bool yes=false;for(size_t i=0,j=p.size()-1;i<p.size();j=i++)if(((p[i].y>y)!=(p[j].y>y))&&(x<(p[j].x-p[i].x)*(y-p[i].y)/(p[j].y-p[i].y)+p[i].x))yes=!yes;return yes;}
inline Image polygonCut(const Image &image,const std::vector<Point>&points){
 if(points.size()<3)return image;double x1=points[0].x,y1=points[0].y,x2=x1,y2=y1;
 for(auto p:points){x1=std::min(x1,p.x);x2=std::max(x2,p.x);y1=std::min(y1,p.y);y2=std::max(y2,p.y);}
 Rect box=clamp({(int)std::floor(x1),(int)std::floor(y1),(int)std::ceil(x2)-(int)std::floor(x1),(int)std::ceil(y2)-(int)std::floor(y1)},image.w,image.h);
 Image out;out.w=box.w;out.h=box.h;out.pixels.resize((size_t)out.w*out.h);
 for(int y=0;y<out.h;y++)for(int x=0;x<out.w;x++)if(inside(points,box.x+x+0.5,box.y+y+0.5))out.pixels[y*out.w+x]=image.pixels[(box.y+y)*image.w+box.x+x];
 return out;
}
inline size_t removeCornerBackground(Image&image,int tolerance=48){
 if(image.pixels.empty() || (image.pixels[0] >> 24) == 0)return 0;uint32_t key=image.pixels[0];int kr=(key>>16)&255,kg=(key>>8)&255,kb=key&255;size_t removed=0;
 std::vector<unsigned char> seen(image.pixels.size(),0);std::vector<size_t> todo;todo.reserve(image.pixels.size()/4+1);
 auto add=[&](size_t n){if(seen[n])return;seen[n]=1;uint32_t p=image.pixels[n];int dr=((p>>16)&255)-kr,dg=((p>>8)&255)-kg,db=(p&255)-kb;if((p>>24)==0||dr*dr+dg*dg+db*db<=tolerance*tolerance)todo.push_back(n);};
 for(int x=0;x<image.w;x++){add(x);add((image.h-1)*image.w+x);}for(int y=0;y<image.h;y++){add(y*image.w);add(y*image.w+image.w-1);}
 for(size_t i=0;i<todo.size();i++){size_t n=todo[i];if(image.pixels[n]>>24){image.pixels[n]=0;removed++;}int x=(int)(n%image.w),y=(int)(n/image.w);if(x)add(n-1);if(x+1<image.w)add(n+1);if(y)add(n-image.w);if(y+1<image.h)add(n+image.w);}
 return removed;
}
}
#endif
