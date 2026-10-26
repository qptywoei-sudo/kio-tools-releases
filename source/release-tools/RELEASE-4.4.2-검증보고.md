# KIO 컨트롤 4.4.2 Windows 수정·검증 보고

작업일: 2026-10-13. 사용자가 별도로 수정한 4.4.1 소스와 패키지를 기준으로 수정했습니다.
실행 위치: `G:\내 드라이브\ADMIN\KIO 컨트롤\KIOControl.exe`
개발 소스: `G:\내 드라이브\ADMIN\KIO 컨트롤\개발소스`

## 동작 변경

- 다른 앱에서 캡처 단축키를 누르면 KIO를 숨기고 Windows 화면 합성 완료 후 캡처합니다. 창을 잠깐 띄워 웹 화면을 깨우던 경로를 제거했습니다.
- KIO가 현재 활성 창이면, 창이 사라지기 전의 선명한 화면을 메모리에 먼저 보관한 뒤 영역을 선택합니다. 따라서 일반 캡처와 AI 캡처로 KIO 자체도 캡처할 수 있습니다. 캡처 준비 이미지의 유효시간은 5초이며 디스크에 저장하지 않습니다.
- 결과 표시와 영역 선택 중 상태를 구분합니다. 결과 창이 열린 상태에서 다음 캡처를 시작할 수 있고, 선택 중 중복 실행은 막습니다. AI 요청이 아직 처리 중이면 완료하거나 취소한 뒤 다시 캡처합니다.
- 이전 결과 컴포넌트가 닫힐 때 새 캡처 세션까지 닫는 문제를 방지했습니다.
- 녹화의 FPS·가로 크기·비율 상세 입력을 없애고 감지한 모니터 선택 카드를 넣었습니다. 모니터 선택은 저장되며 단축키 녹화에도 적용됩니다. 선택한 모니터가 사라지면 임의 화면 녹화를 시작하지 않습니다.
- 설정에 부분 녹화 단축키 항목을 추가했습니다. 기존 단축키는 유지했고 새 항목은 사용자가 지정합니다.
- 번역은 이름 원문, 이름 발음, 메시지 원문, 메시지 번역 순서로 한 블록에 표시·복사합니다. 이름만 중복 반환된 응답을 같은 화자의 다음 메시지와 합칠 때 답장 대상 번호도 함께 보정합니다.
- 교정 전후 문장이 같고 불확실한 부분이 없으면 원문을 한 번만 표시하고 ‘교정할 사항이 없습니다.’를 안내합니다.

## 확인한 결과

| 검사 | 결과 |
|---|---|
| TypeScript / Vite | 통과, 번들 크기 권고 경고만 있음 |
| 프런트엔드 회귀 검사 | 108/108 통과 |
| Python 번역 계약 / 이름 중복 / 녹화 설정 | 21 + 3 + 3개 통과 |
| Windows 네이티브 빌드와 세션 정책 검사 | 통과 |
| 실제 Windows 합성·숨김 검사 | 12회, 예상 밖 픽셀·가시성 실패 0건 |
| 실제 모니터 1 / 2 선택 녹화 | 각 1600×900 MP4 저장 및 디코딩 성공 |
| 부분 녹화 OS 단축키 | 임시 등록 후 키 입력 시뮬레이션으로 선택 화면 열림, 창 깜빡임 없음; 기존 설정 복원 |
| 이동용 ZIP | CRC 검사 통과; 압축 해제 후 포함된 Python 엔진·새 UI·FFmpeg 실행 성공 |

일반 캡처/AI 재캡처는 실제 프로그램의 WM_HOTKEY 처리부터 선택·결과까지 검사했습니다. 부분 녹화는 추가로 OS에 실제 등록한 단축키에 키 입력을 전송했습니다. 사람의 물리 키보드 타이핑을 측정한 것은 아닙니다.

### 재캡처 실측

- external app -> AI: 선택 화면 준비 171.0 ms / KIO 잔상 픽셀 0
- AI result -> AI: 선택 화면 준비 157.0 ms / 기존 KIO 결과 화면과 픽셀 불일치 0%
- AI result -> normal capture: 선택 화면 준비 171.0 ms / 기존 KIO 결과 화면과 픽셀 불일치 0%
- normal capture -> AI: 선택 화면 준비 188.0 ms / 기존 KIO 결과 화면과 픽셀 불일치 0%

재캡처 실측은 합성 테스트 화면과 앱의 해당 테스트 결과만 사용했으며 GPT 요청은 발생시키지 않았습니다. 녹화 검사는 실제 저장 MP4의 크기와 영역을 확인한 것으로 색 정확도 보정 검사는 아닙니다. 테스트 녹화·일반 캡처는 로컬 저장으로 제한한 뒤 기존 저장 설정을 복원했습니다.

### 실제 구독 모델 응답 확인

기존 공식 ChatGPT 구독 계정 연결과 동의 상태를 재사용했습니다. API 키나 별도 유료 API로 전환하지 않았습니다. 사용자가 지정한 현재 모델·추론 설정을 변경하지 않았습니다.

- translate: gpt-6-luna / none, 6.9초. 이름·발음을 머리글로 갖는 메시지 1개 반환.
- correct: gpt-6-luna / none, 3.25초. 원문과 교정문 일치, 수정 사항 0개 반환.

위 두 건은 테스트 이미지 각 1회 실측입니다. 모든 문서나 대화의 평균 속도·정확도를 뜻하지 않습니다. 실제 사용자 메시지 내용을 성능 로그에 기록하지 않았습니다.

## 배포와 남은 항목

- Windows 4.4.2 실행본과 이동 ZIP을 준비했습니다. ZIP 내부 루트는 `KIO-Control-Windows`이며 소스·로그인 정보·개인 작업 파일을 넣지 않았습니다.
- 사용자가 Mac 작업을 넘기도록 요청하여 Mac 4.4.1 ZIP은 유지합니다. 일부 공용 UI/소스는 다음 Mac 빌드용으로 수정됐지만 Mac 실행 검증·앱 서명은 하지 않았습니다.
- 기존 `업데이트/latest.json`의 ID와 서명을 유지했습니다. 서명 키가 Mac에 있어 4.4.2 자동 업데이트 게시를 보류합니다. 이전 공개 4.4.1 ZIP은 이 안내가 참조하므로 그대로 보존합니다.
- 이번 Windows 4.4.2는 ZIP 전체를 풀어 직접 실행하는 배포본입니다. 기존 앱의 업데이트 확인에 4.4.2가 뜬다고 주장하지 않습니다.
- 이동용 ZIP의 엔진을 새 임시 프로필에서 실행해 로그인 정보가 미리 연결되어 있지 않음을 확인했습니다. 새 ZIP의 네이티브 바이너리는 본 PC에서 검증한 실행본과 동일한 해시입니다. 별도 설치 프로그램이나 다른 PC/macOS 검증은 하지 않았습니다.

## 수정 파일

- `agent/ai_prompts.py`
- `agent/ai_smart_scan.py`
- `agent/ai_translate.py`
- `agent/common.py`
- `agent/server.py`
- `desktop-ui/package-lock.json`
- `desktop-ui/package.json`
- `desktop-ui/qa/ai-display.test.cjs`
- `desktop-ui/qa/recording-target.test.cjs`
- `desktop-ui/src/features/local-tools/AITranslator.tsx`
- `desktop-ui/src/features/local-tools/GeneralSettings.tsx`
- `desktop-ui/src/features/local-tools/RecordingControls.tsx`
- `desktop-ui/src/features/local-tools/SmartScanPanel.tsx`
- `desktop-ui/src/features/local-tools/ToolsApp.tsx`
- `desktop-ui/src/features/local-tools/TranslationMessages.tsx`
- `desktop-ui/src/features/local-tools/ai-translator.css`
- `desktop-ui/src/features/local-tools/ai-types.ts`
- `desktop-ui/src/features/local-tools/desktop-events.ts`
- `desktop-ui/src/features/local-tools/recording-controls.css`
- `desktop-ui/src/features/local-tools/recording-controls.ts`
- `desktop-ui/src/features/local-tools/translations.ts`
- `desktop-ui/src/features/local-tools/types.ts`
- `integration-tests/ai_speaker_display_tests.py`
- `integration-tests/desktop_source_isolation_tests.py`
- `integration-tests/recording_preferences_tests.py`
- `mac/AgentHost.swift`
- `mac/NativeBridge.swift`
- `windows/AgentEndpoint.h`
- `windows/AgentEndpointSelftest.cpp`
- `windows/CaptureBackdrop.h`
- `windows/CaptureBackdropSelftest.cpp`
- `windows/CaptureTool.cpp`
- `windows/GalaxyControl.rc`
- `windows/NativeBridge.cpp`
- `windows/NativeBridge.h`
- `windows/SharedHost.cpp`
- `windows/SharedHostPolicy.h`
- `windows/SharedHostPolicySelftest.cpp`
- `windows/UxShell.cpp`
- `windows/build-windows.sh`

ZIP SHA-256: `d63f27de26c495640dd2dba42f3ef6f5a7912c78c32deff2b15f72bee1ac2c12`
크기: 400,188,872 bytes

## Drive 업로드 확인

Windows ZIP은 ADMIN / KIO 컨트롤 / 윈도우용에 동기화되었으며 Drive 서버 파일 ID와 크기 400,188,872 bytes를 확인했습니다. 파일 ID: 1TBxzzm28vyIGwxtRZ2Inu370WXdtfnNO. 로컬 복사본 SHA-256도 일치합니다. 연결 도구가 원격 체크섬을 반환하지 않아 원격 바이트 재다운로드 비교는 하지 않았습니다. 새 ZIP은 현재 소유자 계정에서 다운로드할 수 있으며 공개 링크 공유는 설정하지 않았습니다. 자동 업데이트 latest.json은 기존 4.4.1 서명본 그대로입니다.
