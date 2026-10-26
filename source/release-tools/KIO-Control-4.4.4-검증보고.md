# KIO 컨트롤 4.4.4 검증 보고

2026-10-13 · Windows 실제 PC 및 별도 테스트 프로필

## 사용자 지정 단축키 유지 — 최우선 수정

6개 항목: 영역 캡처, 전체 캡처, 웹 전체 캡처, AI 스마트 스캔, 녹화 시작·종료, 부분 녹화.

- Windows Native 설정을 현재 등록 성공 상태와 분리하여 사용자 지정값을 보존합니다.
- 영역 캡처도 다른 키와 동일한 표준 문자열로 저장합니다. 이전 INI 설정도 읽으며 Windows 키 조합을 인식합니다.
- 설정 파일 교체 후 Windows INI 캐시를 갱신하고, 새 상태를 내보낸 후 저장 완료 응답을 보냅니다.
- 백엔드 저장과 네이티브 상태 수집을 같은 잠금으로 처리하여 오래된 값이 최신 저장값을 덮어쓰지 않게 했습니다.
- 일반 설정 적용에서는 별도로 저장된 단축키 값을 다시 보내지 않습니다.
- 특정 조합으로 강제 지정하지 않습니다. 이미 옛 버전에서 소실된 사용자 의도는 복원할 수 없으므로 새 버전에서 원하는 키를 한 번 다시 선택해야 합니다.

실제 4.4.4 실행 파일을 완전히 종료·재실행하는 4개 설정 묶음 검사:
1. 6개 항목 사용자 지정 조합: 모두 유지.
2. 6개 항목 모두 사용 안 함: 모두 유지.
3. Windows 키/F키 조합 포함: 모두 유지.
4. Ctrl+Shift+A를 포함한 영문 키 조합 6개: 모두 유지.
다른 일반 설정을 적용한 뒤에도 단축키 값 유지. 테스트 후 테스트 직전 저장값 복원.
별도 위치에 압축 해제한 이동용 EXE 실행: 같은 사용자 프로필의 6개 저장값 그대로 확인.

## 녹화

- LocalAgentClient가 recording 설정을 누락하던 전송 오류 수정. 선택 영역·창·모니터 선택이 서버에 전달되고 저장됩니다.
- 전체/창 녹화 시작 시 열려 있는 앱을 숨기지 않으며, 부분 녹화는 영역 선택 후 이전 앱 표시 상태를 복원합니다.
- 녹화 컨트롤에 앱 열기 추가. 녹화 중 닫았다가 다시 열기, 일시정지/재개 확인.
- 영역 선택 중 명시적으로 앱을 열면 진행 중인 선택을 취소하고 앱으로 돌아오도록 보완.

실측 검증:
- 물리 모니터 2대 각각 1600×900 녹화, 지정 좌표 테두리, MP4 저장 및 실제 프레임 디코딩 통과.
- 숨겨진 앱에서 단축키 녹화: 표시 상태 유지. 열린 앱에서 녹화: 열린 상태 유지.
- 녹화 도구의 앱 열기와 기존 열기 경로, 일시정지/재개 통과.
- 드래그 영역 460×240 및 테스트 창 850×600 녹화·저장 확인.
- 별도 UI에서 모드 3종/모니터 2대 선택 → 실제 설정 API → 페이지 재로드 유지 확인.
- 단축키 동작 테스트는 네이티브 WM_HOTKEY 핸들러 호출이며 모든 물리 키 입력을 반복한 테스트는 아닙니다.

## QR·도장·웹 안내

- QR 결과를 현재 작업 화면에 즉시 표시. 과거 결과는 이전 내역에 계속 보관.
- https://www.naver.com/ QR 생성 → 512×512 PNG 결과 표시 → 별도 디코더로 동일 URL 확인.
- 도장 모양 6종, 테두리 5종, 한국어/한자 글꼴 각 3종. 미설치 시스템 글꼴은 대체됨을 안내.
- 회사명·날짜 없이, 문서 없이 투명 PNG 저장 확인. 640×640 RGBA의 알파 범위 0~255 확인.
- 연결 중에도 웹 확장 안내 표시. Chrome/Edge 주소 복사 값, 4단계 설치 팝업 및 상태 표시 확인.
- 이번 작업은 확장 안내 복원이며 실제 Chrome 웹 전체 캡처 재시험은 하지 않았습니다. 기존 확장 코드 변경 없음.

## 회사 ChatGPT 계정

스크린샷의 3p_delegated_access_policy_denied를 조직 정책 오류로 구분하고 설정에 도움말을 추가했습니다.
조직 관리자에게 앱 사용 허용 및 구독 공유 대상 계정 여부를 확인해야 합니다.
정책을 우회하거나 유료 API로 전환하지 않습니다. 실제 회사 계정 로그인 성공은 미검증입니다.
공식 복구 문서: https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery

## 빌드·자동 검사

- Windows 네이티브 EXE 빌드, TypeScript 검사, Vite 배포 빌드 성공.
- UI 자동 검사 116개 통과.
- 네이티브 단축키 INI 복원 self-test 통과.
- 계정 정책 1개, 녹화 설정 3개 Python 검사 통과.
- 데스크톱 세션 검사 17개 중 14개 통과, Windows 심볼릭 링크 권한이 필요한 3개 미실행.
- 별도 recording_tests.py는 개발용 imageio_ffmpeg 모듈이 없어 실행하지 못했습니다. 실제 앱의 번들 FFmpeg/MP4 디코딩 검사는 위와 같이 통과했습니다.
- UI 브라우저 검사는 별도 프로필/모의 네이티브 연결을 사용했습니다. QR·도장 저장 엔진과 설정 HTTP는 실제 코드입니다.
- 3,877개 ZIP 항목 CRC 확인, 별도 폴더 압축 해제, 번들 Python 엔진 기동, 최신 UI 제공, FFmpeg 기동 확인.
- 별도 프로필에는 연결된 ChatGPT 계정이 없음을 확인. 소스와 사용자 인증정보는 ZIP 제외.

## 주요 수정 파일

개발소스/windows: CaptureTool.cpp, NativeBridge.cpp/.h, SharedHost.cpp, ToolHub.cpp, ShortcutProfile.h, ShortcutProfileSelftest.cpp, 버전 리소스.
개발소스/agent: server.py, chatgpt_account.py, common.py(버전).
개발소스/desktop-ui/src/services/local-agent.ts.
개발소스/desktop-ui/src/features/local-tools: ToolsApp.tsx, GeneralSettings.tsx, AITranslator.tsx, ai-types.ts, RecordingControls.tsx, translations.ts, StampDesigner.tsx, SignatureStudio.tsx, signature-geometry.ts, document-studio.css, WebCaptureGuide.tsx, extension-setup.css.
개발소스/desktop-ui/qa: stamp-options.test.cjs, settings-transport.test.cjs.
개발소스/integration-tests/account_policy_tests.py.

## 배포

실행: G:/내 드라이브/ADMIN/KIO 컨트롤/KIOControl.exe
ZIP: G:/내 드라이브/ADMIN/KIO 컨트롤/윈도우용/KIO-Control-4.4.4-Windows-Portable.zip
크기: 400197147 bytes
SHA-256: 6c1b72333bdacb6f072d1e3a597f5ad6d3318a9658f0958ec9932f66518cc0d7
Drive 복사본의 해시 일치 확인. 클라우드 업로드 상태는 별도 메타데이터로 확인합니다.
다른 사용자도 4.4.4로 교체해야 수정이 적용됩니다.
Mac 빌드 및 서명 키 접근이 없어 Mac 배포와 기존 서명된 자동 업데이트 피드는 변경하지 않았습니다.

클라우드 업로드 확인: KIO-Control-4.4.4-Windows-Portable.zip / 400197147 bytes.
Drive ZIP: https://drive.google.com/file/d/1wlxgXuS-SvvWpN2HVcoOzquvLVW3wT6q/view

