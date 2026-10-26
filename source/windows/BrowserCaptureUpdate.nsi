; Update existing 4.0.0 program sources only. Build from an explicitly frozen stage.
Unicode true
!include "MUI2.nsh"
!ifndef GALAXY_PACKAGE
 !error "GALAXY_PACKAGE must identify the validated frozen Windows stage"
!endif
!ifndef UPDATE_MANIFEST
 !error "UPDATE_MANIFEST must identify the validator-generated payload receipt"
!endif
Name "GalaxyControl Browser Capture 4.0.1"
OutFile "GalaxyControl-BrowserCapture-Update.exe"
InstallDir "$LOCALAPPDATA\Programs\GalaxyControl"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 16
VIProductVersion "4.0.1.0"
VIAddVersionKey "ProductName" "GalaxyControl Browser Capture Update"
VIAddVersionKey "FileVersion" "4.0.1"
VIAddVersionKey "FileDescription" "Per-user browser capture source update"
VIAddVersionKey "LegalCopyright" "GalaxyControl; third-party licenses are preserved"
!define MUI_ABORTWARNING
!define MUI_DIRECTORYPAGE_TEXT_TOP "$(FolderHelp)"
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE CheckFolder
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "$(DoneTitle)"
!define MUI_FINISHPAGE_TEXT "$(DoneHelp)"
!define MUI_FINISHPAGE_TEXT_LARGE
!define MUI_FINISHPAGE_RUN "$INSTDIR\GalaxyControl.exe"
!define MUI_FINISHPAGE_RUN_TEXT "$(RunApp)"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "Korean"
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Vietnamese"
!insertmacro MUI_LANGUAGE "Japanese"
!insertmacro MUI_LANGUAGE "SimpChinese"

LangString FolderHelp ${LANG_KOREAN} "기존 GalaxyControl 4.0.0 폴더를 선택하세요. 설치본은 자동으로 찾습니다. 무설치 버전은 GalaxyControl.exe가 있는 Windows 폴더를 선택하세요."
LangString FolderHelp ${LANG_ENGLISH} "Choose your existing GalaxyControl 4.0.0 folder. Installed copies are found automatically. For a portable copy, select its Windows folder containing GalaxyControl.exe."
LangString FolderHelp ${LANG_VIETNAMESE} "Chọn thư mục GalaxyControl 4.0.0 hiện có. Bản đã cài được tìm tự động. Với bản di động, chọn thư mục Windows chứa GalaxyControl.exe."
LangString FolderHelp ${LANG_JAPANESE} "既存の GalaxyControl 4.0.0 フォルダーを選択してください。インストール版は自動検出します。ポータブル版は GalaxyControl.exe がある Windows フォルダーを選択します。"
LangString FolderHelp ${LANG_SIMPCHINESE} "请选择已有的 GalaxyControl 4.0.0 文件夹。安装版会自动查找。便携版请选择包含 GalaxyControl.exe 的 Windows 文件夹。"
LangString QuitHelp ${LANG_KOREAN} "GalaxyControl이 실행 중입니다. 창의 X는 앱을 종료하지 않습니다. 트레이 아이콘 메뉴에서 완전히 종료한 뒤 [다시 시도]를 누르세요. 앱을 강제 종료하지 않습니다."
LangString QuitHelp ${LANG_ENGLISH} "GalaxyControl is running. Closing its window does not quit it. Quit it fully from its system tray menu, then click Retry. This updater does not force-close the app."
LangString QuitHelp ${LANG_VIETNAMESE} "GalaxyControl đang chạy. Đóng cửa sổ không thoát ứng dụng. Hãy thoát hoàn toàn từ biểu tượng khay hệ thống, rồi bấm Thử lại. Trình cập nhật không cưỡng chế tắt ứng dụng."
LangString QuitHelp ${LANG_JAPANESE} "GalaxyControl が実行中です。ウィンドウを閉じても終了しません。通知領域のアイコンから完全に終了して、［再試行］を押してください。強制終了は行いません。"
LangString QuitHelp ${LANG_SIMPCHINESE} "GalaxyControl 正在运行。关闭窗口不会退出应用。请从系统托盘菜单完全退出，然后点击“重试”。更新程序不会强制关闭应用。"
LangString InvalidFolder ${LANG_KOREAN} "이 폴더에서 올바른 GalaxyControl 4.0.0 설치본과 기존 브라우저 확장 프로그램을 확인하지 못했습니다. 전체 프로그램이 있는 폴더를 다시 선택하세요. 변경된 파일은 없습니다."
LangString InvalidFolder ${LANG_ENGLISH} "This folder could not be verified as GalaxyControl 4.0.0 with its original browser extension. Select the folder containing the complete app. No files were changed."
LangString InvalidFolder ${LANG_VIETNAMESE} "Không xác minh được GalaxyControl 4.0.0 và tiện ích trình duyệt gốc trong thư mục này. Chọn thư mục chứa ứng dụng đầy đủ. Chưa thay đổi tệp nào."
LangString InvalidFolder ${LANG_JAPANESE} "このフォルダーで GalaxyControl 4.0.0 と元のブラウザー拡張機能を確認できません。アプリ全体があるフォルダーを選び直してください。ファイルは変更していません。"
LangString InvalidFolder ${LANG_SIMPCHINESE} "无法确认此文件夹包含 GalaxyControl 4.0.0 及其原有浏览器扩展。请重新选择包含完整应用的文件夹。尚未更改任何文件。"
LangString UpdateStatus ${LANG_KOREAN} "프로그램 파일을 백업하고 브라우저 캡처를 업데이트합니다."
LangString UpdateStatus ${LANG_ENGLISH} "Backing up program files and updating browser capture."
LangString UpdateStatus ${LANG_VIETNAMESE} "Đang sao lưu tệp chương trình và cập nhật chụp trình duyệt."
LangString UpdateStatus ${LANG_JAPANESE} "プログラムファイルをバックアップし、ブラウザーキャプチャを更新しています。"
LangString UpdateStatus ${LANG_SIMPCHINESE} "正在备份程序文件并更新浏览器截图功能。"
LangString UpdateFailed ${LANG_KOREAN} "업데이트를 완료하지 못했습니다. 쓰기 권한과 여유 공간을 확인하세요. 백업은 tools\updates\browser-capture-before-4.0.1에 보존합니다. 자동 복원에 실패한 경우 이 백업에서 복구할 수 있습니다. 앱을 실행하기 전에 다시 시도하세요."
LangString UpdateFailed ${LANG_ENGLISH} "The update could not finish. Check write permission and free disk space. Backups are retained in tools\updates\browser-capture-before-4.0.1. If automatic restoration failed, recover files from that backup. Retry before reopening the app."
LangString UpdateFailed ${LANG_VIETNAMESE} "Không thể hoàn tất cập nhật. Kiểm tra quyền ghi và dung lượng trống. Bản sao lưu nằm tại tools\updates\browser-capture-before-4.0.1. Nếu khôi phục tự động thất bại, phục hồi tệp từ bản sao lưu. Thử lại trước khi mở ứng dụng."
LangString UpdateFailed ${LANG_JAPANESE} "更新を完了できませんでした。書き込み権限と空き容量を確認してください。バックアップは tools\updates\browser-capture-before-4.0.1 に残ります。自動復元できなかった場合は、このバックアップから復旧できます。アプリを開く前に再試行してください。"
LangString UpdateFailed ${LANG_SIMPCHINESE} "更新未能完成。请检查写入权限和可用空间。备份保留在 tools\updates\browser-capture-before-4.0.1。如果自动恢复失败，请用此备份恢复文件。请先重试，再打开应用。"
LangString DoneTitle ${LANG_KOREAN} "브라우저 캡처 업데이트 완료"
LangString DoneTitle ${LANG_ENGLISH} "Browser capture update complete"
LangString DoneTitle ${LANG_VIETNAMESE} "Đã cập nhật chụp trình duyệt"
LangString DoneTitle ${LANG_JAPANESE} "ブラウザーキャプチャの更新完了"
LangString DoneTitle ${LANG_SIMPCHINESE} "浏览器截图更新完成"
LangString DoneHelp ${LANG_KOREAN} "Chrome: chrome://extensions$\r$\nEdge: edge://extensions$\r$\n$\r$\n기존 GalaxyControl 확장 프로그램의 새로고침 버튼을 한 번 누르세요. 확장 프로그램을 삭제하거나 다시 추가할 필요가 없습니다.$\r$\n$\r$\nGalaxyControl을 다시 실행하세요. 기존 승인과 개인 설정은 유지됩니다."
LangString DoneHelp ${LANG_ENGLISH} "Chrome: chrome://extensions$\r$\nEdge: edge://extensions$\r$\n$\r$\nClick Reload once on the existing GalaxyControl extension. You do not need to remove or add it again.$\r$\n$\r$\nReopen GalaxyControl. Existing approvals and personal settings are preserved."
LangString DoneHelp ${LANG_VIETNAMESE} "Chrome: chrome://extensions$\r$\nEdge: edge://extensions$\r$\n$\r$\nBấm Tải lại một lần trên tiện ích GalaxyControl hiện có. Không cần gỡ hoặc thêm lại tiện ích.$\r$\n$\r$\nMở lại GalaxyControl. Quyền đã cấp và cài đặt cá nhân được giữ nguyên."
LangString DoneHelp ${LANG_JAPANESE} "Chrome: chrome://extensions$\r$\nEdge: edge://extensions$\r$\n$\r$\n既存の GalaxyControl 拡張機能の再読み込みを一度押してください。削除や追加し直す必要はありません。$\r$\n$\r$\nGalaxyControl を起動してください。既存の許可と個人設定は保持されます。"
LangString DoneHelp ${LANG_SIMPCHINESE} "Chrome: chrome://extensions$\r$\nEdge: edge://extensions$\r$\n$\r$\n在已有的 GalaxyControl 扩展上点击一次“重新加载”。无需删除或重新添加扩展。$\r$\n$\r$\n重新打开 GalaxyControl。已有授权和个人设置会保留。"
LangString RunApp ${LANG_KOREAN} "GalaxyControl 다시 실행"
LangString RunApp ${LANG_ENGLISH} "Reopen GalaxyControl"
LangString RunApp ${LANG_VIETNAMESE} "Mở lại GalaxyControl"
LangString RunApp ${LANG_JAPANESE} "GalaxyControl を起動"
LangString RunApp ${LANG_SIMPCHINESE} "重新打开 GalaxyControl"

Function .onInit
 !insertmacro MUI_LANGDLL_DISPLAY
 ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GalaxyControlADMIN" "InstallLocation"
 StrCmp $0 "" +2
 StrCpy $INSTDIR $0
 InitPluginsDir
 SetOutPath "$PLUGINSDIR"
 File /oname=BrowserCaptureUpdate.py "${__FILEDIR__}/BrowserCaptureUpdate.py"
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

Function CheckFolder
 retry:
 Call RequireClosed
 IfFileExists "$INSTDIR\GalaxyControl.exe" 0 invalid
 IfFileExists "$INSTDIR\tools\python\python.exe" 0 invalid
 nsExec::ExecToStack /TIMEOUT=30000 '"$INSTDIR\tools\python\python.exe" -I "$PLUGINSDIR\BrowserCaptureUpdate.py" validate "$INSTDIR\."'
 Pop $0
 Pop $1
 StrCmp $0 "0" valid
 StrCmp $0 "3" retry invalid
 invalid:
 MessageBox MB_OK|MB_ICONSTOP "$(InvalidFolder)"
 Abort
 valid:
FunctionEnd

Section "GalaxyControl Browser Capture" SEC_PATCH
 Call RequireClosed
 SetOutPath "$PLUGINSDIR\payload"
 File /oname=update-payload.json "${UPDATE_MANIFEST}"
 SetOutPath "$PLUGINSDIR\payload\tools\engine\agent"
 File "${GALAXY_PACKAGE}\tools\engine\agent\server.py"
 SetOutPath "$PLUGINSDIR\payload\tools\browser-extension"
 File /r "${GALAXY_PACKAGE}\tools\browser-extension\*"
 SetOutPath "$PLUGINSDIR\payload\tools\source"
 File "${GALAXY_PACKAGE}\tools\source\GalaxyControl-source.zip"
 DetailPrint "$(UpdateStatus)"
 retryApply:
 ; No timeout: allow the transactional helper to finish or roll back safely.
 nsExec::ExecToStack '"$INSTDIR\tools\python\python.exe" -I "$PLUGINSDIR\BrowserCaptureUpdate.py" apply "$INSTDIR\." "$PLUGINSDIR\payload\."'
 Pop $0
 Pop $1
 StrCmp $0 "0" done
 StrCmp $0 "3" 0 failed
 Call RequireClosed
 Goto retryApply
 failed:
 MessageBox MB_OK|MB_ICONSTOP "$(UpdateFailed)"
 SetErrorLevel 2
 Abort
 done:
 SetOutPath "$INSTDIR"
SectionEnd
