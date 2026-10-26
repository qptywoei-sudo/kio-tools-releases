#include "CapturePixels.h"
#include <cassert>
#include <iostream>
using namespace CapturePixels;
int main(){
 Image transparent{6,5,std::vector<uint32_t>(30,0)};Image original=transparent;fillRect(transparent,{1,1,3,2},0xffe05040);assert(transparent.pixels[7]==0xffe05040&&transparent.pixels[15]==0xffe05040&&transparent.pixels[0]==0&&transparent.pixels[16]==0);assert(original.pixels[7]==0);
 Image backgroundFill=original;fillRect(backgroundFill,{-1,2,4,4},0xffffffff);assert(backgroundFill.pixels[12]==0xffffffff&&backgroundFill.pixels[26]==0xffffffff&&backgroundFill.pixels[27]==0&&backgroundFill.pixels[6]==0);backgroundFill=original;assert(backgroundFill.pixels[12]==0);
 Image m{2,2,{0xff000000,0xff640000,0xff006400,0xff000064}};mosaic(m,{0,0,2,2},2);for(auto p:m.pixels)assert(p==0xff191919);
 Image b{3,1,{0xff000000,0xff646464,0xffc8c8c8}};blur(b,{0,0,3,1},1);assert(b.pixels[0]==0xff323232&&b.pixels[1]==0xff646464&&b.pixels[2]==0xff969696);
 Image square{4,4,std::vector<uint32_t>(16,0xffabcdef)};auto cut=polygonCut(square,{{0,0},{4,0},{0,4}});assert(cut.w==4&&cut.h==4);assert(cut.pixels[0]==0xffabcdef);assert(cut.pixels[15]==0);
 Image background{5,5,std::vector<uint32_t>(25,0xffffffff)};for(int y=1;y<4;y++)for(int x=1;x<4;x++)background.pixels[y*5+x]=0xff000000;background.pixels[12]=0xffffffff;assert(removeCornerBackground(background,10)==16);assert(background.pixels[12]==0xffffffff);assert(background.pixels[0]==0);
 Image roi{3,3,std::vector<uint32_t>(9,0xff111111)};roi.pixels[4]=0xffeeeeee;mosaic(roi,{1,1,1,1},10);assert(roi.pixels[0]==0xff111111&&roi.pixels[4]==0xffeeeeee);
 assert(clamp({-2,-2,5,5},4,4).w==3);std::cout<<"PASS: mosaic averages, blur edges, polygon alpha, border background flood, ROI bounds\n";
}
