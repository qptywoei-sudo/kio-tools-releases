#include "RecorderModel.h"
#include "NativeProtocol.h"
#include <cassert>
#include <iostream>
using J=nlohmann::json;
int main(){
 using namespace RecorderModel;
 auto size=outputSize(3840,2160);assert(size.valid&&size.width==3840&&size.height==2160);
 size=outputSize(3840,2160,1920);assert(size.valid&&size.width==1920&&size.height==1080);
 size=outputSize(3840,2160,0,50);assert(size.valid&&size.width==1920&&size.height==1080);
 size=outputSize(1921,1081,1280);assert(size.valid&&size.width==1280&&size.height==720);
 size=outputSize(1280,720,7680);assert(size.valid&&size.width==1280&&size.height==720);
 assert(!outputSize(100,50,1).valid);assert(!outputSize(100,50,8000).valid);assert(!outputSize(100,50,0,9).valid);
 assert(!outputSize(100,50,0,101).valid);assert(!outputSize(100000,100000).valid);assert(!outputSize(7680,4320).valid);
 assert(outputSize(7680,4320,3840).valid);
 unsigned sum=0;for(unsigned frame=1;frame<=60;++frame)sum+=frameInterval(frame,60);assert(sum==1000);assert(frameInterval(1,5)==200&&frameInterval(1,4)==0);
 Timeline clock;clock.start(1000);assert(clock.elapsed(1200)==200);clock.pause(1300);assert(clock.elapsed(9000)==300);
 clock.pause(9000);assert(clock.elapsed(9500)==300);clock.resume(10000);assert(clock.elapsed(10200)==500);
 clock.resume(11000);assert(clock.elapsed(11200)==1500);clock.pause(11300);clock.stop(20000);assert(clock.elapsed(90000)==1600&&!clock.paused);
 clock.resume(99999);assert(clock.elapsed(100000)==1600);clock.start(200000);assert(clock.elapsed(200010)==10&&!clock.stopped);
 assert(NativeProtocol::recordArguments(J::object()));assert(NativeProtocol::recordArguments(J{{"width",1920},{"fps",60},{"scale_percent",50},{"format","mp4"},{"microphone",false}}));
 assert(!NativeProtocol::recordArguments(J{{"fps",4}}));assert(!NativeProtocol::recordArguments(J{{"fps",61}}));assert(!NativeProtocol::recordArguments(J{{"fps",30.5}}));
 assert(!NativeProtocol::recordArguments(J{{"width",1}}));assert(!NativeProtocol::recordArguments(J{{"scale_percent",101}}));assert(!NativeProtocol::recordArguments(J{{"format","avi"}}));
 assert(!NativeProtocol::recordArguments(J{{"systemAudio","false"}}));assert(!NativeProtocol::recordArguments(J{{"unknown",true}}));
 assert(NativeProtocol::operations().count("record.pause")&&NativeProtocol::operations().count("record.resume"));
 std::cout<<"PASS: even aspect-preserving downscale/no upscale and output memory bounds; pause/resume repeated controls, stopped-paused timeline and restart; record argument/operation contracts\n";
}
