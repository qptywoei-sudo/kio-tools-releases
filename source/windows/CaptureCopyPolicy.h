#pragma once
#include <cstddef>
#include <cstdint>
namespace CaptureCopyPolicy {
constexpr bool defaultCloseAfterCaptureCopy=true;
inline bool boundedPng(const unsigned char*bytes,size_t length){
 static const unsigned char header[]={137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82};
 if(!bytes||length<33||length>320000000)return false;for(size_t i=0;i<sizeof(header);++i)if(bytes[i]!=header[i])return false;
 auto big=[&](size_t i){return (uint32_t(bytes[i])<<24)|(uint32_t(bytes[i+1])<<16)|(uint32_t(bytes[i+2])<<8)|bytes[i+3];};
 uint32_t width=big(16),height=big(20);return width>0&&height>0&&width<=20000&&height<=20000&&uint64_t(width)*height<=80000000;
}
inline bool clipboardCommitted(bool emptied,bool png,bool dibV5,bool dib,bool closed){return emptied&&closed&&(png||dibV5||dib);}
inline bool nativeEditor(bool captureDocument,bool enabled,bool bridgeRequest){return !captureDocument||(enabled&&!bridgeRequest);}
inline bool closeEditor(bool enabled,bool copied,bool captureDocument){return enabled&&copied&&captureDocument;}
}
