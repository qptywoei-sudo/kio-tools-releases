#include "CaptureOverlayModel.h"
#include "CaptureCopyPolicy.h"
#include "NativeProtocol.h"
#include <cassert>
#include <iostream>
#include <vector>
using J=nlohmann::json;
int main(){
 using namespace CaptureOverlayModel;
 auto point=localPoint({-1800,150},-1920,-200,5760,2360);assert(point.x==120&&point.y==350);
 point=localPoint({99999,-99999},-1920,-200,5760,2360);assert(point.x==5760&&point.y==0);
 auto reversed=selection({500,400},{101,103});assert(reversed.left==101&&reversed.top==103&&reversed.right==500&&reversed.bottom==400);
 auto even=selection({500,400},{101,103},true);assert(even.right-even.left==398&&even.bottom-even.top==296);
 auto changed=dirty({0,0,100,100},{90,90,200,200},5760,2360);assert(changed.left==0&&changed.top==0&&changed.right==203&&changed.bottom==203);
 auto edge=dirty({5758,2358,5760,2360},{5750,2340,5760,2360},5760,2360);assert(edge.right==5760&&edge.bottom==2360&&edge.left==5747);
 // Both shrink and reverse drags must restore every pixel of the old selection.
 auto shrink=dirty({100,100,900,900},{110,110,150,150},1000,1000);assert(shrink.left<=100&&shrink.top<=100&&shrink.right>=900&&shrink.bottom>=900);
 assert(frameIntervalMs==16);
 using namespace CaptureCopyPolicy;assert(defaultCloseAfterCaptureCopy);
 for(unsigned mask=0;mask<8;++mask){bool ok=clipboardCommitted(true,mask&1,mask&2,mask&4,true);assert(ok==(mask!=0));assert(!clipboardCommitted(false,mask&1,mask&2,mask&4,true));assert(!clipboardCommitted(true,mask&1,mask&2,mask&4,false));}
 assert(nativeEditor(true,true,false));assert(!nativeEditor(true,true,true));assert(!nativeEditor(true,false,false));assert(nativeEditor(false,false,true));
 assert(closeEditor(true,true,true));assert(!closeEditor(false,true,true));assert(!closeEditor(true,false,true));assert(!closeEditor(true,true,false));
 std::vector<unsigned char> png(33,0);unsigned char header[]={137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82};for(size_t i=0;i<sizeof(header);++i)png[i]=header[i];png[18]=3;png[19]=0xc0;png[22]=2;png[23]=0x1c;assert(boundedPng(png.data(),png.size()));assert(!boundedPng(png.data(),24));png[16]=255;assert(!boundedPng(png.data(),png.size()));png[16]=0;png[0]=0;assert(!boundedPng(png.data(),png.size()));assert(!boundedPng(nullptr,0));
 assert(NativeProtocol::clipboardArguments(J{{"path","C:\\capture.png"}}));assert(!NativeProtocol::clipboardArguments(J{{"path",123}}));assert(!NativeProtocol::clipboardArguments(J{{"path","C:\\capture.png"},{"command","shell"}}));assert(!NativeProtocol::clipboardArguments(J{{"path",std::string("a\0b",3)}}));
 assert(NativeProtocol::settingsArguments(J{{"closeAfterCaptureCopy",false}}));assert(NativeProtocol::settingsArguments(J::object()));assert(NativeProtocol::settingsArguments(J{{"openCaptureEditor",false},{"captureFormat","jpg"}}));assert(!NativeProtocol::settingsArguments(J{{"openCaptureEditor",0}}));assert(!NativeProtocol::settingsArguments(J{{"captureFormat","jpeg"}}));assert(!NativeProtocol::settingsArguments(J{{"captureFormat",true}}));assert(!NativeProtocol::settingsArguments(J{{"closeAfterCaptureCopy","false"}}));assert(!NativeProtocol::settingsArguments(J{{"closeAfterCaptureCopy",0}}));assert(!NativeProtocol::settingsArguments(J{{"unknown",true}}));
 std::string id="12345678-1234-1234-1234-123456789abc";J request={{"id",id},{"operation","clipboard.copy"},{"args",J{{"path","C:\\capture.png"}}},{"expiresAt",1100}};assert(NativeProtocol::validate(request,id,1000).empty());
 std::cout<<"PASS: negative-origin physical coordinates, reverse/even drag, old/new dirty coverage; clipboard ownership/result close guards and default/OFF; bounded PNG headers; copy/settings argument allowlists\n";
}
