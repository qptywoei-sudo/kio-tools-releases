#pragma once
#include <windows.h>
#include <string>
#include <functional>
#include <vector>
#include "include/json.hpp"
namespace NativeAgent {
constexpr UINT ReadyMessage=WM_APP+120;
constexpr UINT PollTimer=801;
void Init(HWND,HINSTANCE);
void StartupStage(const char*stage);
void SetInitialHome(bool);
bool Handle(UINT,WPARAM,LPARAM);
void OpenTools(bool browser=false);
void OpenCategory(const std::string&);
void SetInitialShortcut(const std::string&);
void RunShortcut(const std::string&);
std::string ShortcutDestination(const std::string&);
void Shutdown();void PrepareQuit();
bool Busy();
void Signal(const char*);
bool CaptureRequestLive();bool RecordRequestLive();
void CaptureAccepted(const std::wstring&);
void CaptureSaved(const std::wstring&,const std::wstring&,bool);
void CaptureOverlayShown();
void CaptureImageAsync(std::function<std::vector<BYTE>()>);
void CaptureCancelled(const char*error="cancelled");
void RecordStarted(bool);
void RecordFinished(bool,const std::wstring&);
const std::wstring&StateDir();
}
namespace NativeServices {
using Json=nlohmann::json;
bool CanDispatch();
void CancelSelectionForOpen();
bool PrepareShortcutCapture(bool includeHost);
Json Settings();void InitializeShortcuts();
bool ApplySettings(const Json&,std::string&);
bool Capture(const Json&,std::string&,const std::string&requestId);
bool CancelCapture(const std::string&requestId);
bool SetSaveFolder(const std::wstring&);
bool CopyClipboardImage(const std::wstring&,std::string&);
bool Record(const Json&,std::string&);
bool Editor(const std::wstring&,std::string&);
void ShowTool(const std::string&);
}
