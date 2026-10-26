# KIO Tools GitHub 업데이트

개발 원본: SSD의 KIO/Projects/KIO-Tools. 빌드 원본: KIO/Build/KIO-Tools.
배포용 복사본: https://github.com/qptywoei-sudo/kio-tools-releases

버전별 ZIP과 소스를 tools-v버전 릴리스로 공개한 뒤, SSD 전용 Ed25519 키로 ZIP 크기·SHA-256·루트·버전을 검증하여 안내 파일을 서명합니다. tools-update-channel 릴리스의 latest.json만 같은 이름으로 갱신합니다. 비밀키는 SSD State/kio-tools-updates에만 보관하며 공개하지 않습니다.

기존 Drive 업데이트 클라이언트는 새 GitHub 설치본으로 한 번 전환해야 합니다. 새 설치본은 GitHub 안내의 서명과 다운로드 해시를 검증합니다. Mac/Windows 프로그램 식별자와 개인 설정 위치는 유지합니다. 기존 Drive 원본은 삭제하지 않습니다.

이 폴더의 publish_windows.py와 Windows-배포방법.md는 구형 Drive 채널의 보존 자료입니다. 새 배포에는 사용하지 않습니다.
