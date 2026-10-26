# KIO 컨트롤 4.4.5 검증 보고

검증일: 2026-10-13. 대상: Windows 및 현재 로그인한 공식 ChatGPT 구독 계정.

## 구현 결과

모델과 추론 선택을 고정 목록에서 계정별 공식 모델 카탈로그로 변경했다. 로그인 계정의 표시용 모델을 제공 순서대로 보여주며, 선택한 모델의 모든 제공 추론 옵션을 표시한다. 계정을 전환하면 이전 목록을 폐기하고 새 계정의 목록을 다시 조회한다. 늦게 도착한 이전 계정의 조회 결과가 새 선택을 덮어쓰지 않도록 막았다. 번역할 때마다 목록을 재조회하지 않는다.

현재 KIO 추천값은 `gpt-6-luna / low`이며, UI의 자동 추천 옵션과 적용 상태에 명시했다. ChatGPT가 제공하는 모델 기본값은 별도 선택이다. 예를 들어 현재 계정의 Luna 기본값은 `medium`이므로 자동 추천과 구분된다. 모델 기본값을 선택하면 카탈로그에 명시된 기본 추론을 요청에 적용하고, 기본값이 없으면 서비스가 결정하도록 생략한다.

현재 계정은 표시용 모델 7개를 제공했다. 이 숫자는 모든 사용자에게 고정하지 않는다. Luna의 제공 추론은 `low, medium, high, xhigh, max`이다. 다른 모델이 제공하는 `ultra`도 표시하지만 현재 직접 화면 스캔 연결이 거절하므로 설명과 함께 비활성화했다. 현재 계정 목록에 없는 `none`은 이전 개발자 벤치마크 결과만으로 추가하지 않는다. 향후 유효한 새 추론 식별자는 제공 목록에서 그대로 표시한다.

새 모델을 선택할 때 지원하지 않는 이전 추론은 추천값으로 바꾼다. 저장한 모델이나 추론이 현재 계정에 없으면 선택 필요 상태를 표시한다. 사용자 승인 없는 유료 API 전환, 별도 API 키 요구, 중계 서버 추가는 없다.

## 수정 파일

- `agent/ai_catalog.py`: 공식 카탈로그의 표시 모델, 입력 형식, 모든 추론 옵션, 기본값, 설명 정규화.
- `agent/chatgpt_account.py`: 정규화 재사용 및 계정별 캐시 유지.
- `agent/ai_translate.py`: 제공 목록에 따른 설정 검증과 실제 추론 요청 적용.
- `desktop-ui/src/features/local-tools/ai-types.ts`: 카탈로그 기본값과 설명 타입.
- `desktop-ui/src/features/local-tools/ai-model-options.ts`: 계정별 선택과 적용값 표시.
- `desktop-ui/src/features/local-tools/AIModelSettings.tsx`: 모델·추론 선택 UI, 적용 상태, 목록 새로고침.
- `desktop-ui/src/features/local-tools/AITranslator.tsx`: 기존 설정 UI 통합, 계정 전환과 이전 응답 차단.
- `desktop-ui/src/features/local-tools/ai-translator.css`: 기존 노란색 스타일을 사용하는 간결한 설정 배치.
- `integration-tests/ai_catalog_tests.py`, `desktop-ui/qa/ai-model-options.test.cjs`: 카탈로그·선택·요청·계정 전환 검사.
- Windows 버전 파일, UI package 파일, agent/common.py, Mac 소스의 버전 문자열을 4.4.5로 갱신. Mac 실행 파일은 빌드하지 않았다.

## 검증 결과

| 검사 | 결과 |
|---|---|
| UI 자동 검사 | 121/121 통과 |
| TypeScript 검사 및 Vite 빌드 | 통과 |
| Python AI 검사 | 55/55 통과 |
| 독립 소스 수집·압축·빌드 검사 | 6/6 통과 |
| 격리 브라우저 UI 흐름 | 7개 시나리오 통과 |
| 실제 프로그램 | 4.4.5, nativeReady 확인 |
| 재시작 전후 설정 | 기존 6종 단축키와 AI 설정 일치 |
| 현재 공식 구독 연결 | 연결 및 플랜 사용 승인 상태 확인 |
| 실제 계정 모델 목록 | 표시용 모델 7개 및 모델별 추론 확인 |
| 실제 Luna/high 이미지 번역 | 성공, 요청 완료까지 11.822초 |
| 실제 sol/ultra 직접 요청 | 거절, aiReasoningUnavailable, 1.570초 |
| 이동 ZIP 검사 | CRC·버전·실행 파일·현재 UI 확인 |
| ZIP 독립 실행 | 별도 프로필에서 포함된 Python 엔진·UI·FFmpeg 실행 성공 |

UI 시나리오는 계정 A의 모델 7개와 계정 B의 다른 모델 2개를 사용한 모의 공식 응답으로 검증했다. A→B→A 목록 전환, 미지원 추론 전환, 새 제공 추론, 늦은 응답 차단, 새로고침 후 선택 유지, 좁은 화면의 가로 넘침 여부를 확인했다. 실제 다른 사용자 계정의 OAuth 로그인을 완료한 검사는 아니다.

high 실측은 정상 동작 확인용 이미지 한 번의 요청이다. 이번 요청에서 none/low/medium 속도 비교를 새로 수행하거나 모든 모델·추론 조합의 실서비스 성공을 확인한 것으로 해석하면 안 된다. 추천 low는 기존 번역 실측 정책을 유지했다. 다른 모델의 xhigh/max 및 향후 새 옵션은 설정·요청 형식 검증까지 완료했으며 모든 조합의 실제 서버 실행은 미검증이다.

원본 이미지·대화 내용·이메일·인증 토큰은 검증 보고와 로그에 기록하지 않았다. ZIP에 사용자 인증정보와 사용자 프로필을 넣지 않았다.

## 배포 파일과 제한

- 실행 프로그램: `G:\내 드라이브\ADMIN\KIO 컨트롤\KIOControl.exe`
- 이동용 ZIP: `G:\내 드라이브\ADMIN\KIO 컨트롤\윈도우용\KIO-Control-4.4.5-Windows-Portable.zip`
- ZIP 크기: 400,198,776바이트, 파일 3,878개.
- SHA-256: `a683b4b2c7d97e3a8c26709dc957b7a7f2199403b711f2e76a5162033110f30e`
- 배포 메모 및 검증 보고: `G:\내 드라이브\ADMIN\KIO 컨트롤\업데이트`
- Google Drive에서 ZIP 파일명과 전체 크기 일치 확인. 파일 ID: `1nWb5VRYkNOqSEHTi3YcoGdXGoqv66ppd`. 현재 소유자 전용 파일이며 공개 공유를 설정하지 않았다.

현재 컴퓨터의 Windows 실행 파일과 수동 이동 ZIP을 갱신했다. 자동 업데이트 피드는 원래 Ed25519 개인 서명 키가 없어 4.4.1 상태를 유지했다. 원래 키 없이 서명을 교체하거나 우회하지 않았다. Mac 앱도 갱신하지 않았다. 따라서 다른 사용자는 이 ZIP으로 수동 교체해야 이번 변경이 적용된다.

공식 설계 참고: https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
