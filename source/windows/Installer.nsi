; Optional per-user installer. Build with NSIS 3 after staging the complete portable folder:
; makensis -DGALAXY_PACKAGE=/absolute/staged/Windows Installer.nsi
; Files, runtimes, sources and licenses must come from one validated release tree.
Unicode true
!include "MUI2.nsh"
!ifndef GALAXY_PACKAGE
 !error "GALAXY_PACKAGE must identify the complete validated portable Windows folder"
!endif
Name "GalaxyControl"
OutFile "GalaxyControl-Setup.exe"
Icon "${__FILEDIR__}/GalaxyControl.ico"
UninstallIcon "${__FILEDIR__}/GalaxyControl.ico"
InstallDir "$LOCALAPPDATA\Programs\GalaxyControl"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 16
VIProductVersion "4.2.1.0"
VIAddVersionKey "ProductName" "GalaxyControl"
VIAddVersionKey "FileVersion" "4.2.1"
VIAddVersionKey "FileDescription" "Per-user GalaxyControl local tools installer"
!define MUI_ABORTWARNING
!define MUI_ICON "${__FILEDIR__}/GalaxyControl.ico"
!define MUI_UNICON "${__FILEDIR__}/GalaxyControl.ico"
!define MUI_CUSTOMFUNCTION_GUIINIT PreserveLoginStartup
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\GalaxyControl.exe"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Korean"
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Vietnamese"
!insertmacro MUI_LANGUAGE "Japanese"
!insertmacro MUI_LANGUAGE "SimpChinese"
LangString QuitHelp ${LANG_KOREAN} "GalaxyControl이 실행 중입니다. 창의 X는 앱을 종료하지 않습니다. 트레이 아이콘 메뉴에서 완전히 종료한 뒤 [다시 시도]를 누르세요. 앱을 강제 종료하지 않습니다."
LangString QuitHelp ${LANG_ENGLISH} "GalaxyControl is running. Closing its window does not quit it. Quit it fully from its system tray menu, then click Retry. This updater does not force-close the app."
LangString QuitHelp ${LANG_VIETNAMESE} "GalaxyControl đang chạy. Đóng cửa sổ không thoát ứng dụng. Hãy thoát hoàn toàn từ biểu tượng khay hệ thống, rồi bấm Thử lại. Trình cập nhật không cưỡng chế tắt ứng dụng."
LangString QuitHelp ${LANG_JAPANESE} "GalaxyControl が実行中です。ウィンドウを閉じても終了しません。通知領域のアイコンから完全に終了して、［再試行］を押してください。強制終了は行いません。"
LangString QuitHelp ${LANG_SIMPCHINESE} "GalaxyControl 正在运行。关闭窗口不会退出应用。请从系统托盘菜单完全退出，然后点击“重试”。更新程序不会强制关闭应用。"
LangString DesktopShortcut ${LANG_KOREAN} "바탕화면 바로가기"
LangString DesktopShortcut ${LANG_ENGLISH} "Desktop shortcut"
LangString DesktopShortcut ${LANG_VIETNAMESE} "Lối tắt trên màn hình"
LangString DesktopShortcut ${LANG_JAPANESE} "デスクトップのショートカット"
LangString DesktopShortcut ${LANG_SIMPCHINESE} "桌面快捷方式"
LangString LoginStartup ${LANG_KOREAN} "로그인 시 자동 실행"
LangString LoginStartup ${LANG_ENGLISH} "Start at login"
LangString LoginStartup ${LANG_VIETNAMESE} "Chạy khi đăng nhập"
LangString LoginStartup ${LANG_JAPANESE} "ログイン時に起動"
LangString LoginStartup ${LANG_SIMPCHINESE} "登录时自动运行"
Function .onInit
 !insertmacro MUI_LANGDLL_DISPLAY
 ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalaxyControlADMIN" "InstallLocation"
 StrCmp $0 "" +2
 StrCpy $INSTDIR $0
FunctionEnd
Function RequireClosed
 retry:
 FindWindow $0 "GalaxyCaptureMain"
 StrCmp $0 0 0 running
 System::Call 'kernel32::OpenMutexW(i 0x00100000, i 0, w "Local\GalaxyCapturePortableSingleInstance") p .r0'
 StrCmp $0 0 done
 System::Call 'kernel32::CloseHandle(p r0)'
 running:
 MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "$(QuitHelp)" IDRETRY retry
 Abort
 done:
FunctionEnd
Section "GalaxyControl" SEC_MAIN
 SectionIn RO
 Call RequireClosed
 SetShellVarContext current
 SetOutPath "$INSTDIR"
 File "${GALAXY_PACKAGE}\GalaxyControl.exe"
 SetOutPath "$INSTDIR\tools"
 File /r "${GALAXY_PACKAGE}\tools\*"
 SetOutPath "$INSTDIR\resources"
 File /r "${GALAXY_PACKAGE}\resources\*"
 SetOutPath "$INSTDIR"
 WriteUninstaller "$INSTDIR\Uninstall.exe"
 CreateShortCut "$SMPROGRAMS\GalaxyControl.lnk" "$INSTDIR\GalaxyControl.exe"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalaxyControlADMIN" "DisplayName" "GalaxyControl"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalaxyControlADMIN" "DisplayVersion" "4.2.1"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalaxyControlADMIN" "InstallLocation" "$INSTDIR"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalaxyControlADMIN" "UninstallString" '"$INSTDIR\Uninstall.exe"'
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalaxyControlADMIN" "NoModify" 1
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalaxyControlADMIN" "NoRepair" 1
 ; Existing user settings and pairing files are outside the installation directory.
SectionEnd
Section "$(DesktopShortcut)" SEC_DESKTOP
 SetShellVarContext current
 CreateShortCut "$DESKTOP\GalaxyControl.lnk" "$INSTDIR\GalaxyControl.exe"
SectionEnd
Section "$(LoginStartup)" SEC_STARTUP
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "GalaxyControlPersonal" '"$INSTDIR\GalaxyControl.exe" --background'
SectionEnd
Function PreserveLoginStartup
 ; Updates preserve a user's disabled login setting. Fresh installs default ON.
 ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalaxyControlADMIN" "InstallLocation"
 StrCmp $0 "" done
 ReadRegStr $1 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "GalaxyControlPersonal"
 StrCmp $1 "" 0 done
 SectionSetFlags ${SEC_STARTUP} 0
 done:
FunctionEnd
Section "Uninstall"
 SetShellVarContext current
 ; Remove our startup value only when it still targets this installed copy.
 ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "GalaxyControlPersonal"
 StrCmp $0 '"$INSTDIR\GalaxyControl.exe" --background' 0 +2
 DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "GalaxyControlPersonal"
 Delete "$SMPROGRAMS\GalaxyControl.lnk"
 Delete "$DESKTOP\GalaxyControl.lnk"
 Delete "$SMPROGRAMS\GalaxyControl ADMIN.lnk"
 DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalaxyControlADMIN"
 Delete "$INSTDIR\GalaxyControl.exe"
 RMDir /r "$INSTDIR\tools"
 RMDir /r "$INSTDIR\resources"
 Delete "$INSTDIR\Uninstall.exe"
 RMDir "$INSTDIR"
 ; Pictures/GalaxyControl and LocalAppData/GalaxyControl user settings are preserved.
SectionEnd
