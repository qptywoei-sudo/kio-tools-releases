#pragma once
#include <algorithm>
namespace PdfWorkspace {
struct Layout{int left,gap,usable,column,right,fileHeight,top,footer,totalHeight,pageHeight;};
inline Layout calculate(int width,int height,int dpi,bool advanced,bool manyMergeFiles,float split){auto s=[&](int n){return (n*dpi+48)/96;};Layout r{};r.left=s(18);r.gap=s(12);r.usable=std::max(s(780),width-2*r.left);r.column=std::max(s(420),std::min(r.usable-s(330)-r.gap,(int)(r.usable*split)));r.right=r.left+r.column+r.gap;r.fileHeight=s(manyMergeFiles?104:56);r.top=s(154)+r.fileHeight;r.footer=s(advanced?234:146);r.totalHeight=std::max(height,r.top+s(260)+r.footer);r.pageHeight=r.totalHeight-r.top-r.footer;return r;}
}
