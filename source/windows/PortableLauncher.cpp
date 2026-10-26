// Customer-facing single icon. The audited ZIP payload is appended at build time.
// Windows 10 (1803+) includes the system tar.exe used here; no shell or downloads.
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shlobj.h>
#include <bcrypt.h>
#include <string>
#include <vector>
#include <cstdio>
#ifndef KIO_PAYLOAD_SHA256
#error Build with the SHA-256 of the audited payload
#endif
#ifndef KIO_RELEASE
#error Build with the matching release version
#endif
static void fail() {
    const wchar_t* text=L"Bogo Tools could not start. Check free disk space and extract the ZIP again. Windows 10 (1803) or later is required.";
    LANGID language=GetUserDefaultUILanguage();
    switch(PRIMARYLANGID(language)) {
    case LANG_KOREAN:text=L"Bogo Tools를 시작하지 못했습니다. 디스크 여유 공간을 확인하고 ZIP 압축을 다시 풀어 주세요. Windows 10 (1803) 이상이 필요합니다.";break;
    case LANG_VIETNAMESE:text=L"Không thể mở Bogo Tools. Kiểm tra dung lượng trống và giải nén lại ZIP. Cần Windows 10 (1803) trở lên.";break;
    case LANG_JAPANESE:text=L"Bogo Toolsを起動できませんでした。空き容量を確認し、ZIPをもう一度展開してください。Windows 10 (1803)以降が必要です。";break;
    case LANG_CHINESE:text=(SUBLANGID(language)==SUBLANG_CHINESE_TRADITIONAL||SUBLANGID(language)==SUBLANG_CHINESE_HONGKONG||SUBLANGID(language)==SUBLANG_CHINESE_MACAU)
        ? L"無法啟動 Bogo Tools。請確認磁碟可用空間並重新解壓縮 ZIP。需要 Windows 10 (1803) 或更新版本。"
        : L"无法启动 Bogo Tools。请检查磁盘可用空间并重新解压 ZIP。需要 Windows 10 (1803) 或更高版本。";break;
    }
    MessageBoxW(nullptr,text,L"Bogo Tools",MB_OK|MB_ICONERROR);
}
static bool plainDirectory(const std::wstring& path) {
    DWORD a=GetFileAttributesW(path.c_str());
    if(a==INVALID_FILE_ATTRIBUTES) return CreateDirectoryW(path.c_str(),nullptr)!=0;
    return (a&FILE_ATTRIBUTE_DIRECTORY) && !(a&FILE_ATTRIBUTE_REPARSE_POINT);
}
static std::wstring quote(const std::wstring& s) { return L"\""+s+L"\""; }
static bool run(const std::wstring& executable,std::wstring args,DWORD* exitCode=nullptr) {
    std::wstring command=quote(executable)+L" "+args;
    STARTUPINFOW si{};si.cb=sizeof(si);PROCESS_INFORMATION pi{};
    if(!CreateProcessW(executable.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&si,&pi)) return false;
    CloseHandle(pi.hThread);
    if(!exitCode) { CloseHandle(pi.hProcess);return true; }
    WaitForSingleObject(pi.hProcess,INFINITE);GetExitCodeProcess(pi.hProcess,exitCode);CloseHandle(pi.hProcess);return *exitCode==0;
}
static bool payload(const std::wstring& self,const std::wstring& output) {
    FILE* in=_wfopen(self.c_str(),L"rb");if(!in)return false;
    unsigned long long length=0;char magic[8];
    if(_fseeki64(in,-16,SEEK_END)!=0||fread(&length,8,1,in)!=1||fread(magic,1,8,in)!=8||memcmp(magic,"KIOTOOLS",8)||length<1000||length>2ULL*1024*1024*1024) { fclose(in);return false; }
    auto end=_ftelli64(in);if(length>static_cast<unsigned long long>(end-16)||_fseeki64(in,end-16-length,SEEK_SET)!=0){fclose(in);return false;}
    BCRYPT_ALG_HANDLE algorithm=nullptr;BCRYPT_HASH_HANDLE hash=nullptr;
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0){fclose(in);return false;}
    if(BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0)<0){BCryptCloseAlgorithmProvider(algorithm,0);fclose(in);return false;}
    FILE* out=_wfopen(output.c_str(),L"wb");bool ok=out!=nullptr;std::vector<unsigned char> buffer(1024*1024);
    while(ok&&length){size_t n=static_cast<size_t>(length<buffer.size()?length:buffer.size());ok=fread(buffer.data(),1,n,in)==n&&fwrite(buffer.data(),1,n,out)==n&&BCryptHashData(hash,buffer.data(),static_cast<ULONG>(n),0)>=0;length-=n;}
    unsigned char digest[32]{};ok=ok&&BCryptFinishHash(hash,digest,32,0)>=0;
    if(out&&fclose(out)!=0)ok=false;fclose(in);BCryptDestroyHash(hash);BCryptCloseAlgorithmProvider(algorithm,0);
    char hex[65];for(int i=0;i<32;i++)sprintf(hex+2*i,"%02x",digest[i]);hex[64]=0;
    return ok&&!strcmp(hex,KIO_PAYLOAD_SHA256);
}
int WINAPI wWinMain(HINSTANCE,HINSTANCE,PWSTR,int) {
    wchar_t path[32768];DWORD n=GetModuleFileNameW(nullptr,path,32768);if(!n||n>=32768)return 1;std::wstring self(path,n);
    PWSTR local=nullptr;if(FAILED(SHGetKnownFolderPath(FOLDERID_LocalAppData,KF_FLAG_CREATE,nullptr,&local)))return 1;
    std::wstring parent=std::wstring(local)+L"\\KIO Tools";CoTaskMemFree(local);
    std::wstring root=parent+L"\\" KIO_RELEASE, app=root+L"\\KIO-Control-Windows", marker=root+L"\\ready";
    HANDLE mutex=CreateMutexW(nullptr,FALSE,L"Local\\KIOToolsSingleIconExtract");if(!mutex)return 1;
    DWORD waited=WaitForSingleObject(mutex,INFINITE);if(waited!=WAIT_OBJECT_0&&waited!=WAIT_ABANDONED){CloseHandle(mutex);return 1;}
    bool ok=plainDirectory(parent)&&plainDirectory(root);
    DWORD marked=GetFileAttributesW(marker.c_str());
    if(ok&&marked==INVALID_FILE_ATTRIBUTES){
        std::wstring archive=root+L"\\payload.zip";ok=payload(self,archive);
        if(ok){UINT count=GetSystemDirectoryW(path,32768);DWORD result=1;ok=count&&count<32768&&run(std::wstring(path)+L"\\tar.exe",L"-xf "+quote(archive)+L" -C "+quote(root),&result);}
        DeleteFileW(archive.c_str());
        if(ok){HANDLE ready=CreateFileW(marker.c_str(),GENERIC_WRITE,0,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);ok=ready!=INVALID_HANDLE_VALUE;if(ok){FlushFileBuffers(ready);CloseHandle(ready);}}
    }
    if(ok)ok=plainDirectory(app)&&GetFileAttributesW((app+L"\\KIOControl.exe").c_str())!=INVALID_FILE_ATTRIBUTES;
    if(!ok)DeleteFileW(marker.c_str());
    ReleaseMutex(mutex);CloseHandle(mutex);
    if(ok)ok=run(app+L"\\KIOControl.exe",L"");
    if(!ok){
        // English fallback is available on all supported systems, before the UI starts.
        fail();return 1;
    }
    return 0;
}
