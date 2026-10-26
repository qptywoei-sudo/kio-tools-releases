#pragma once
#include <windows.h>
#include <dwmapi.h>
#include <initializer_list>

// Hide our own windows without a compositor fade. Flush the compositor before
// freezing the desktop, rather than guessing how long an animation takes.
namespace CaptureBackdrop {
inline bool hide(std::initializer_list<HWND> windows){
 struct State{HWND window;BOOL transitions;bool changed;};
 State states[8]={};size_t count=0;
 for(HWND window:windows){
  if(!window||!IsWindow(window)||count>=8)continue;
  BOOL previous=FALSE,disabled=TRUE;
  DwmGetWindowAttribute(window,DWMWA_TRANSITIONS_FORCEDISABLED,&previous,sizeof(previous));
  bool changed=SUCCEEDED(DwmSetWindowAttribute(window,DWMWA_TRANSITIONS_FORCEDISABLED,&disabled,sizeof(disabled)));
  states[count++]={window,previous,changed};ShowWindow(window,SW_HIDE);
 }
 GdiFlush();DwmFlush();
 bool hidden=true;
 for(size_t i=0;i<count;++i){
  auto&state=states[i];hidden=hidden&&!IsWindowVisible(state.window);
  if(state.changed)DwmSetWindowAttribute(state.window,DWMWA_TRANSITIONS_FORCEDISABLED,&state.transitions,sizeof(state.transitions));
 }
 return hidden;
}
}
