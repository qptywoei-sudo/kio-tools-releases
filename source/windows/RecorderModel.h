#pragma once
#include <algorithm>
#include <cstdint>
namespace RecorderModel {
struct Size{int width=0,height=0;bool valid=false;};
inline Size outputSize(int sourceWidth,int sourceHeight,int width=0,int scalePercent=100){
 if(sourceWidth<2||sourceHeight<2||uint64_t(sourceWidth)*sourceHeight>80000000||width<0||width>7680||(width>0&&width<2)||scalePercent<10||scalePercent>100)return {};
 int outWidth=width?std::min(width,sourceWidth):int(int64_t(sourceWidth)*scalePercent/100);outWidth-=outWidth%2;
 int outHeight=outWidth?int(int64_t(sourceHeight)*outWidth/sourceWidth):0;outHeight-=outHeight%2;
 if(outWidth<2||outHeight<2||uint64_t(outWidth)*outHeight>16000000)return {};return {outWidth,outHeight,true};
}
inline unsigned frameInterval(unsigned frame,int fps){return frame&&fps>=5&&fps<=60?unsigned(uint64_t(frame)*1000/fps-uint64_t(frame-1)*1000/fps):0;}
// Clock input is monotonic milliseconds. Pauses disappear from encoded timestamps.
struct Timeline{
 uint64_t started=0,pausedAt=0,pausedTotal=0,finalDuration=0;bool paused=false,stopped=false;
 void start(uint64_t now){started=now;pausedAt=pausedTotal=finalDuration=0;paused=stopped=false;}
 uint64_t elapsed(uint64_t now)const{return stopped?finalDuration:(paused?pausedAt:now)-started-pausedTotal;}
 void pause(uint64_t now){if(!paused&&!stopped){pausedAt=now;paused=true;}}
 void resume(uint64_t now){if(paused&&!stopped){pausedTotal+=now-pausedAt;paused=false;}}
 void stop(uint64_t now){if(!stopped){finalDuration=elapsed(now);stopped=true;paused=false;}}
};
}
