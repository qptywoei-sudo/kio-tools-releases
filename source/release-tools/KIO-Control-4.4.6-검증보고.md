# KIO Control 4.4.6 변경 및 검증

2026-10-13. Windows 4.4.5 최신 공통 소스를 기반으로 Windows x64 실행 파일과 Mac arm64/x86_64 실행 파일을 실제 빌드했습니다.

## 수정
- Mac AgentHost.swift: 단축키 선행 창 표시 제거, 선택 진행 중만 중복 차단, 이전 결과가 열린 상태 재캡처, 의도한 자기 화면 캡처를 위한 사전 프레임 보관.
- Mac NativeCapture.swift: 앱 창을 숨긴 뒤 WindowServer 가시성 확인, 모니터별 정지 화면 영역 선택, Esc 취소, 임시 이미지 정리.
- Mac NativeBridge.swift: 여섯 단축키의 원자적 등록·실패 롤백, 추가 Mac 키 지원, 저장값 보존, 실제 모니터 정보 전달.
- Mac ScreenRecord.swift: 녹화/일시정지 테두리, 선택 영역 후 원래 창과 키 포커스 복원, 전체/영역/창 선택 유지.
- 공통 RecordingControls: Mac 모니터 선택을 모든 녹화 모드에 반영.
- updater/update_security/update_helper: 기존 서명 형식 1과 고정 안내 ID를 유지하면서 서명된 platformReleases로 OS별 독립 업데이트.
- prepare_update/publish_windows/Publish-Windows.ps1: 기존 Ed25519 암호화 키 보안 입력, 실제 ZIP 빌드 버전·해시·익명 다운로드 검증, 고정 feed 덮어쓰기·실패 복구.

## 자동 검사
- 공통 UI TypeScript 검사, 121개 테스트, 프로덕션 빌드 통과.
- Python 통합 107개 통과. 추가 암호화 키 비밀번호/다른 키 거부 검사 통과(플랫폼 배포 검사 총 9개).
- 기존 updater 검사 13개 통과. 구형 4.4.5 검증기가 새 전환 안내를 검증하는 호환 테스트 포함.
- 최종 Mac self-check, native-bridge, native-shortcut conflict rollback, agent-endpoint, 900x640/1150x820 layout 검사 통과.
- Windows 크로스 빌드 성공. Windows 실제 실행 검사는 이 Mac에서 수행하지 않았습니다.

## 실제 Mac 검사
- 일반→일반, 일반→AI, AI→AI, AI→일반 캡처 성공. 이전 결과를 열린 채 재캡처 가능.
- 개인정보 없는 별도 테스트 앱을 캡처했고 KIO 잔상 없는 영역 이미지 확인.
- Ctrl+C 및 Ctrl+S 후 편집 창 닫힘 확인.
- ChatGPT 플랜 연결로 실제 이미지 영어→한국어 번역 성공. 테스트 문장만 전송.
- 여섯 단축키 모두 Command+Control+Option+Shift+숫자로 변경 후 완전 종료/재실행 유지 확인. 모두 사용 안 함도 재실행 유지. 원래 사용자 설정 복원.
- 모니터 1대 자동 감지, 전체 화면·선택 영역·선택 창 녹화 및 MP4 저장. 녹화→일시정지→재개→종료 버튼 상태, 녹화 중 X 닫기와 메뉴에서 다시 열기 확인.
- 생성한 전체/부분/창 MP4 세 파일을 FFmpeg로 끝까지 디코딩(exit 0). 창 녹화 null 출력 시 시간축 재스케일 경고가 있어 별도 재생 확인 필요.
- QR 생성 즉시 미리보기·복사 확인. 날짜·회사명 없는 도장만 투명 PNG 저장 확인.

## 제한과 미검증
- 모니터는 1대만 연결됨. 다중 모니터 실사용, 다른 Mac/계정, Windows 런타임·PowerShell의 실제 Drive 게시 미검증.
- 자동 UI 입력은 앱 대상으로 전달되므로 물리 키보드로 다른 앱 사용 중 전역 단축키 여섯 개 실행하는 최종 검사는 별도 필요. 실제 Carbon 등록·충돌 롤백과 저장/복원은 검사했습니다.
- 자기 앱 영역 캡처는 사전 프레임을 사용합니다. 자기 앱을 시스템 창 선택으로 캡처하는 경로와 이동하는 녹화 창 테두리 추적은 추가 검증 필요.
- 기존 Mac 서명은 로컬 안정 서명 인증서이며 Developer ID 공증이 아닙니다. 기존 방식으로 서명 후 검증했습니다. 새로운 Mac에서 Gatekeeper 신뢰는 별도 필요합니다. Apple 인증서는 내보내지 않았습니다.
- 웹 확장 연결 상태는 확인했으나 실제 긴 페이지 캡처, 사진/PDF/영상 드래그 앤 드롭의 이번 실사용 재검사는 미완료입니다. 공통 UI 자동 검사는 통과했습니다.
- 모든 AI 결과 9종은 공통 자동 검사 범위이며 실제 서비스 호출은 이미지 번역만 확인했습니다.

## 배포 구조
- 기존 고정 feed ID: 1p91Pj2v2RhhnSG0rxOxBJW_oBvGjuGqd (삭제/재생성 금지).
- 최상위 version/packages는 실제 4.4.6 전환 ZIP을 계속 보존. 이후 Windows만 배포하면 platformReleases.Windows만 변경합니다.
- 원래 공개키 L1MEbjag8uGWGER+oAdjTk2mq0B/Rx4nQ/Niy1H6U10= 유지. 기존 개인키에서 계산해 일치 확인, 암호화 PKCS#8 복호화 왕복 확인.
- ADMIN/KIO-배포키 및 파일 전부 owner-only, 공유 false 확인. 앱 ZIP에 개인키/계정/설정/로그를 넣지 않습니다.
- Windows 다음 배포 명령 및 복구는 Windows-배포방법.md 참조.

실제 원격 게시·기존 앱 업데이트 완료 여부는 배포 결과 파일에서 확인하세요. 이 문서의 빌드 검증만으로 게시 완료를 의미하지 않습니다.
