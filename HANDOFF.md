# SentinelFlow 인수인계

이 문서는 세션이 바뀌어도 구현 상태와 다음 작업을 즉시 이어가기 위한 작업 기준서다.
새 세션은 먼저 이 파일과 `git status --short --branch`, `git log --oneline -5`를 확인한다.

## 현재 체크포인트

- 기준일: 2026-07-28
- 현재 브랜치: `feat/integration-adapter-sdk`
- 통합 기준: `develop`의 `bd53841`
- 안정 브랜치: `main`의 `03a2c8c`
- 진행 단계: 3단계 Integration Adapter SDK 구현 및 전체 검증 완료
- 작업 트리: 커밋과 GitHub PR 통합 전 상태

## 완료된 단계

| 단계 | 상태 | 핵심 커밋 또는 PR |
| --- | --- | --- |
| 1. 플랫폼 초기화 | 완료, `main`/`develop` 반영 | `03a2c8c`까지의 초기 커밋 |
| 2. Incident 및 Timeline | 완료, `develop` 반영 | `acc3f2d`, PR #1, merge `bd53841` |
| 3. Integration Adapter SDK | 구현·검증 완료, 통합 대기 | 이 브랜치에서 작업 중 |

## 현재 구현 결정

- 외부 서비스 기능을 복제하지 않고 `sentinelflow.integrations`의 공통 REST 경계만 제공한다.
- Credential은 원문 대신 UUID 기반 `CredentialReference`만 영속화할 수 있다.
- `SecretManager`는 반드시 `workspace_id`와 CredentialReference를 함께 받아 비밀을 해석한다.
- HTTPS origin을 기본 강제하며 base URL credential/query/fragment/path를 거부한다.
- Redirect를 따라가지 않고 요청 경로가 고정 origin을 벗어나지 못하게 한다.
- Bearer, API Key, Basic, No Auth 전략을 공통 제공한다.
- GET 등 멱등 메서드는 transient 오류에 재시도할 수 있다.
- POST 같은 비멱등 요청은 idempotency key가 있을 때만 재시도한다.
- timeout은 HTTP 연결 단계와 전체 논리 연산 양쪽에 적용한다.
- Circuit Breaker 실패 횟수는 개별 retry가 아니라 최종 논리 호출 단위로 집계한다.
- 오류 메시지에는 Credential, 응답 본문, 내부 transport 상세를 포함하지 않는다.

## 현재 검증 상태

- 신규 SDK Ruff: 통과
- 신규 SDK mypy strict: 통과
- 전체 Backend 테스트: 86개 통과
- 전체 Coverage: 95.11%
- Frontend TypeScript 검사, Vitest 2개, Production Build: 통과
- Docker Compose Config와 실제 Build/Health: 통과
- README 실제 화면 캡처: `docs/assets/sentinelflow-stage-03.png`
- CI Formatter 재현성을 위해 Ruff `0.15.22` 고정

## 즉시 다음 작업

1. `feat(integrations): add security service adapter SDK`로 커밋하고 GitHub에 push한다.
2. `feat/integration-adapter-sdk → develop` PR을 만들고 CI 통과 후 병합한다.
3. 최신 `develop`에서 4단계용 `feat/versioned-playbooks` 브랜치를 만든다.

## 남은 단계와 커밋 메시지

1. `feat(playbook): add versioned response playbooks`
2. `feat(workflow): implement auditable workflow execution`
3. `feat(approval): add risk-based approval gates`
4. `feat(integrations): connect detection and threat graph services`
5. `feat(integrations): add RedMind analysis workflow`
6. `feat(response): orchestrate Patchtower remediation`
7. `feat(validation): add post-response security validation`
8. `feat(ai-security): integrate model robustness assessments`
9. `feat(web): add security operations dashboard`
10. `test(e2e): add end-to-end incident response demo`

각 단계는 기능 브랜치, 테스트, 문서, 커밋, push, `develop` 대상 PR, CI, 병합 순서로
진행한다. 사용자에게 중간 선택을 요청하지 않고 안전한 기본값으로 계속 진행한다.
`main`은 모든 단계가 통합되고 릴리스 검증이 끝나기 전까지 직접 변경하지 않는다.

## README 및 화면 캡처 완료 조건

- README는 한국어로 목적, 아키텍처, 보안 통제, 실행법, API, 개발법, 브랜치 전략,
  로드맵, 제한사항을 설명한다.
- 3단계 현재 화면의 실제 캡처를 먼저 추가한다.
- 12단계 운영 대시보드가 완성되면 Incident Queue, SLA/MTTD/MTTR, Approval Queue,
  Workflow Timeline 화면을 다시 캡처해 README 이미지를 교체하거나 추가한다.
- 생성형 목업을 실제 화면처럼 사용하지 않는다.

## 전체 검증 명령

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
python -m pytest
npm --prefix web run typecheck
npm --prefix web test -- --run
npm --prefix web run build
docker compose config --quiet
```

로컬 호스트의 `.venv312/bin/python`은 컨테이너 내부 `/usr/local/bin/python`을 가리키므로
호스트에서 깨진 링크처럼 보인다. Python 검사는 저장소의 기존 Python 3.12 컨테이너
환경 또는 CI에서 실행한다.
