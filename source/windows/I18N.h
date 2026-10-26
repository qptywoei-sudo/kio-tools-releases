#pragma once
#include <windows.h>
#include <string>
void I18NInit();void I18NSetLanguage(int);int I18NSelectedLanguage();const char*I18NLanguage();void I18NLocalizeTree(HWND);void I18NLocalizeMenu(HMENU);
extern "C" const wchar_t*GalaxyTr(const wchar_t*);extern "C" void GalaxySetText(HWND,const wchar_t*);extern "C" void GalaxyRegisterText(HWND,const wchar_t*);

extern "C" int GalaxyMessageBox(HWND,const wchar_t*,const wchar_t*,UINT);
extern "C" const wchar_t* GalaxyFileFilter(const wchar_t*);
extern "C" void GalaxyCueBanner(HWND,const wchar_t*);

const char*I18NLanguageSource();
