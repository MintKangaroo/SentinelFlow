# Contributing

Python 3.12 이상과 Node.js 20 이상을 사용합니다. 변경은 작고 명확하게 유지하고 타입, 테스트,
문서를 함께 갱신합니다. 커밋 전에 전체 품질 게이트를 실행합니다.

```bash
python3 -m pip install -e ".[dev]"
npm --prefix web ci
make check
```

## 브랜치 전략

```text
main
└─ 항상 실행 가능한 안정 버전

develop
└─ 다음 릴리스 통합

feat/<기능명>
└─ 기능별 작업

fix/<문제명>
└─ 버그 수정

docs/<문서명>
└─ 문서 변경
```

- 일반 작업 브랜치는 최신 `develop`에서 생성하고 검증 후 `develop`을 대상으로 리뷰합니다.
- 릴리스 준비가 끝난 `develop`만 `main`으로 병합합니다.
- `main`과 `develop`에는 직접 작업 커밋을 만들지 않습니다.
- 기능, 수정, 문서 변경을 한 브랜치에 섞지 않습니다.
- Conventional Commits 형식을 사용합니다.

`.env`, Credential, Token, 운영 데이터 또는 허가되지 않은 대상 정보를 커밋하지 않습니다.
보안 관련 변경에는 기본 거부 테스트, 오용 사례, 오류 정보 제거 및 감사 가능한 권한 결정을
포함해야 합니다.
