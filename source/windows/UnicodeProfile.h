#pragma once
#include <windows.h>
#include <string>
#include <vector>
// Profile APIs preserve Unicode values only for UTF-16 profile files. Preserve
// existing comments/sections while migrating their legacy system-codepage text.
inline bool EnsureUnicodeProfile(const std::wstring&path){
 std::vector<BYTE>bytes;HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);bool existed=file!=INVALID_HANDLE_VALUE;
 if(existed){LARGE_INTEGER length;bool valid=GetFileSizeEx(file,&length)&&length.QuadPart>=0&&length.QuadPart<=1000000;DWORD read=0;if(valid){bytes.resize((size_t)length.QuadPart);valid=bytes.empty()||(ReadFile(file,bytes.data(),(DWORD)bytes.size(),&read,nullptr)&&read==bytes.size());}CloseHandle(file);if(!valid)return false;}
 else if(GetLastError()!=ERROR_FILE_NOT_FOUND)return false;
 if(bytes.size()>=2&&bytes[0]==0xff&&bytes[1]==0xfe)return true;
 UINT codepage=CP_ACP;size_t skip=0;if(bytes.size()>=3&&bytes[0]==0xef&&bytes[1]==0xbb&&bytes[2]==0xbf){codepage=CP_UTF8;skip=3;}std::wstring text;
 if(bytes.size()>skip){int n=MultiByteToWideChar(codepage,0,(char*)bytes.data()+skip,(int)(bytes.size()-skip),nullptr,0);if(n<=0)return false;text.resize(n);if(!MultiByteToWideChar(codepage,0,(char*)bytes.data()+skip,(int)(bytes.size()-skip),text.data(),n))return false;}
 std::wstring temp=path+L".unicode-"+std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(GetTickCount64());file=CreateFileW(temp.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);if(file==INVALID_HANDLE_VALUE)return false;BYTE bom[]={0xff,0xfe};DWORD written=0;bool ok=WriteFile(file,bom,2,&written,nullptr)&&written==2;if(ok&&!text.empty())ok=WriteFile(file,text.data(),(DWORD)(text.size()*sizeof(wchar_t)),&written,nullptr)&&written==text.size()*sizeof(wchar_t);if(ok)ok=FlushFileBuffers(file)!=FALSE;CloseHandle(file);if(ok)ok=MoveFileExW(temp.c_str(),path.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=FALSE;if(!ok)DeleteFileW(temp.c_str());WritePrivateProfileStringW(nullptr,nullptr,nullptr,path.c_str());return ok;
}
