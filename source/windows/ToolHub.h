#pragma once
#include <windows.h>
#include <shellapi.h>
#include <string>
void InitToolHub(HWND,HINSTANCE,int);void ShowToolPage(int);void LayoutToolHub();bool ToolEngineBusy();void ShutdownToolHub();void ToolHubDrop(HDROP);
bool HandleToolHubMessage(UINT,WPARAM,LPARAM);
void OpenEditorFile(const wchar_t*,const wchar_t*pdf=nullptr,int page=0);
void BeginNativeCapture(int mode=0);void BeginRecordingRegion();void StartRecordingRect(RECT);bool StartRecordingRectWithFPS(RECT,int,int width=0,int scalePercent=100,bool viaSharedHost=false);
void SubmitPdfOverlay(const std::wstring&,int,const std::wstring&);
std::wstring EditorOutputFolder();

namespace Gdiplus{class Bitmap;}
bool CopyNativeImage(Gdiplus::Bitmap*);bool SaveClipboardImage(const std::wstring&);

void ToolHubLanguageChanged();

void PdfAnnotationCommitted(const wchar_t*,const wchar_t*);
bool ToolHubPaste();
