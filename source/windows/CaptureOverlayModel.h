#pragma once
#include <algorithm>
namespace CaptureOverlayModel {
struct Point { int x=0,y=0; };
struct Rect { int left=0,top=0,right=0,bottom=0; };
inline Point localPoint(Point physical,int originX,int originY,int width,int height){
 return {std::max(0,std::min(width,physical.x-originX)),std::max(0,std::min(height,physical.y-originY))};
}
inline Rect selection(Point start,Point end,bool even=false){
 Rect r{std::min(start.x,end.x),std::min(start.y,end.y),std::max(start.x,end.x),std::max(start.y,end.y)};
 if(even){r.right-=(r.right-r.left)%2;r.bottom-=(r.bottom-r.top)%2;}return r;
}
inline Rect dirty(Rect previous,Rect next,int width,int height,int margin=3){
 return {std::max(0,std::min(previous.left,next.left)-margin),std::max(0,std::min(previous.top,next.top)-margin),
  std::min(width,std::max(previous.right,next.right)+margin),std::min(height,std::max(previous.bottom,next.bottom)+margin)};
}
// Latest cursor state is coalesced by one Win32 timer before invalidation.
constexpr unsigned frameIntervalMs=16;
}
