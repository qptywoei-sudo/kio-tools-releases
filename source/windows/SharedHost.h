#pragma once
#include <windows.h>
#include <string>
bool SharedHostOpen(HWND,HINSTANCE,const std::wstring&profile,unsigned short port,bool showWindow=true);
bool SharedHostWarm(HWND,HINSTANCE,const std::wstring&profile,bool showWindow=false);
void SharedHostShowLoading(HWND,HINSTANCE);
HWND SharedHostWindow();
bool SharedHostCapturePending();
void SharedHostShowMessage(HWND,HINSTANCE,const wchar_t*,bool runtimeRequired=false);
bool SharedHostNavigate(const std::string&category);
bool SharedHostShortcut(const std::string&name);
void SharedHostShutdown();

void SharedHostAISelected();
