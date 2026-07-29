# SentinelFlow 다음 세션 인수인계

기준일: 2026-07-30
브랜치: `feat/versioned-playbooks`
원격: `origin` → `https://github.com/MintKangaroo/SentinelFlow.git`
최신 커밋: `3902fd7` (`fix: import credential resolution error from errors`)
작업 트리: clean

## 현재 상태

기능 구현은 이번 마일스톤 범위에서 완료되었다. GitHub Actions CI `30441696798`이
통과했으며 Backend 128개 테스트, Ruff, mypy, Frontend typecheck/Vitest/Vite build,
Docker Compose config를 검증했다. 로컬 기본 실행은 외부 side effect가 없는 `dry_run`이다.

GitHub에서 확인할 링크:

- 브랜치: <https://github.com/MintKangaroo/SentinelFlow/tree/feat/versioned-playbooks>
- PR 생성: <https://github.com/MintKangaroo/SentinelFlow/pull/new/feat/versioned-playbooks>
- 마지막 CI 실행: <https://github.com/MintKangaroo/SentinelFlow/actions/runs/30441696798>

## 구현 완료 범위

### Backend

- Incident lifecycle, workspace isolation, OCC, idempotency, append-only timeline
- Immutable versioned Playbook, typed steps, conditions, approval ordering, rollback
- Workflow snapshot/state machine, retry budget, timeout, cancellation, compensation, events
- 독립 Approval Aggregate: quorum, eligible roles, self-approval 방지, 만료/갱신/취소, immutable events
- Celery Dispatcher + Redis lease + dry-run/external executor 경계
- HMAC-signed AI-SOC detection webhook + stale/replay guard
- Allowlist Vendor Adapter: AI-SOC, ThreatGraph, RedMind, Patchtower, AutoPentest, AIShield
- Incident Report projection: timeline, approvals, workflow steps, SHA-256 digest
- Migration heads: `20260728_0005_human_approvals.py`, `20260728_0006_workflow_execution_snapshots.py`

### Web / 문서

- React SOC Operations Dashboard와 deterministic `?demo=1` mode
- Incident, Playbook, Workflow, Approval, Integration 화면
- README 실제 스크린샷과 시스템 맵 SVG
- README, `docs/api.md`, `docs/architecture.md`, `docs/roadmap.md` 동기화

## 주요 진입점

- `src/sentinelflow/application/dispatch.py` — Dispatcher
- `src/sentinelflow/application/detections.py` — 탐지 수신 서비스
- `src/sentinelflow/api/approvals.py` — Approval API
- `src/sentinelflow/api/detections.py` — `POST /api/v1/detections/ai-soc`
- `src/sentinelflow/api/reports.py` — `GET /api/v1/reports/incidents/{id}`
- `src/sentinelflow/infrastructure/vendor_runtime.py` — external adapter registry
- `docs/assets/sentinelflow-system-map.svg` — README 시스템 흐름도

실제 Approval 도메인 파일은 `src/sentinelflow/domain/approval.py`, 서비스 파일은
`src/sentinelflow/application/approvals.py`이다.

## 안전한 실행 설정

- `SENTINELFLOW_WORKFLOW_EXECUTION_MODE=dry_run`가 기본값
- `external` 모드는 `SENTINELFLOW_INTEGRATION_WORKSPACE_ID`와 벤더별 paired HTTPS URL/token 필요
- 운영에서는 환경 SecretManager를 Vault 또는 승인된 Cloud Secret Manager로 교체할 것
- `X-Workspace-ID`, `X-Actor-ID`는 인증이 아니라 격리/감사 문맥이다. Identity Gateway 뒤에 배포할 것
- 실제 Patchtower/AutoPentest side effect 전에 vendor 계약, target authorization, rollback 정책을 검증할 것

## 다음 세션에서 우선 확인할 일

1. PR을 `develop` 또는 프로젝트의 지정 대상 브랜치로 merge한다.
2. 운영 SecretManager와 Identity Gateway 연동을 설계/구현한다.
3. Redis replay guard를 현재 process-local guard에서 실제 Redis `SET NX EX` 구현으로 교체한다.
4. Approval 만료 자동화(Celery beat 또는 delayed dispatch sweep)를 운영 방식으로 결정한다.
5. 라이브 Dashboard가 독립 Approval Aggregate와 Report API를 직접 표시하는지 확인하고, 필요하면 demo 전용 Approval 화면을 API-backed 화면으로 확장한다.
6. 실제 벤더 sandbox contract test와 외부 side-effect 승인 절차를 추가한다.
7. Postgres migration을 빈 DB와 기존 DB에서 모두 실행하고 rollback/backup 절차를 문서화한다.

## 검증 명령

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

현재 셸의 Python이 3.10이면 프로젝트 요구사항(`>=3.12`) 때문에 백엔드 테스트를 직접
실행할 수 없다. CI의 Python 3.12 결과를 기준으로 하거나 Python 3.12 환경을 사용한다.
