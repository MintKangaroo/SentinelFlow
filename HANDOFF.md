# SentinelFlow 인수인계

이 문서는 다음 작업자가 현재 구현과 검증 상태를 빠르게 확인하기 위한 체크포인트다.
작업을 시작할 때 `git status --short --branch`, `git log --oneline -5`와 함께 확인한다.

## 현재 체크포인트

- 기준일: 2026-07-28
- 현재 브랜치: `feat/versioned-playbooks`
- 통합 기준: `develop`의 `1fa1ac7`
- Backend 기반: Platform, Incident Lifecycle, Integration Adapter SDK, Versioned Playbooks,
  Auditable Workflow Engine
- Frontend: SOC Dashboard, Live Incident/Playbook/Workflow API Client, deterministic demo mode
- 작업 트리: Dashboard, Playbook, Workflow와 문서 개선이 아직 커밋되지 않은 상태

## 구현된 기능

### Backend

- FastAPI Async Control API, PostgreSQL, Redis/Celery, OpenTelemetry
- Workspace 격리 Incident 생성·조회·목록·전이·Note·Timeline
- 명시적 Incident 상태 머신, 낙관적 Version, Idempotency Key
- ORM과 PostgreSQL Trigger로 보호되는 Append-only Timeline
- 공통 Auth, Timeout, Retry, Circuit Breaker와 Secret Reference를 제공하는 Adapter SDK
- Immutable Revision, Typed Step, Condition, Approval Ordering, Rollback을 갖춘 Playbook
- Playbook 생성·조회·Revision·Publish·Archive·Append-only Event API
- Immutable Revision Snapshot을 사용하는 Workflow Run/Step State Machine
- Retry Budget, Timeout, Cancellation, Approval Gate와 Reverse Compensation
- Workflow 생성·조회·시작·결과·Retry·Approval·Cancel·Compensation·Event API
- Workspace 복합 FK, OCC, Idempotency와 Append-only Workflow Event

### Operations Dashboard

- Overview Metrics, Incident Queue, Response Posture, Live Timeline
- Incident 검색·심각도 필터·상세 Inspector
- Incident 생성과 다음 허용 상태로의 Lifecycle 전이
- `awaiting_approval` Incident의 승인 UI
- Integration 정책 및 상태 View
- Playbook Library, Definition Inspector와 Publish 동작
- Workflow Execution Ledger, Run Inspector와 현재 Approval Step 동작
- Loading, Empty, API Error, Responsive Navigation
- `?demo=1` 결정적 재현 모드
- `?demo=1&view=incidents`, `approvals`, `playbooks`, `workflows`, `integrations` 직접 진입

### 문서와 자산

- `README.md`: Banner, Badge, 실제 Dashboard 화면, Architecture, Quick Start, Security,
  Quality Gate와 Roadmap
- `docs/assets/sentinelflow-dashboard.png`: 메인 Overview 실제 렌더링
- `docs/assets/sentinelflow-incident-workspace.png`: Incident Workspace 실제 렌더링
- `docs/assets/sentinelflow-approval-queue.png`: Approval Queue 실제 렌더링
- `docs/assets/sentinelflow-playbooks.png`: Versioned Playbook 실제 렌더링
- `docs/assets/sentinelflow-workflows.png`: Auditable Workflow 실제 렌더링
- `docs/assets/sentinelflow-banner.svg`: GitHub README Banner

## 검증 상태

- Ruff check: 통과
- Ruff format check: 통과
- mypy strict: 통과
- Backend pytest: 103개 통과
- Backend coverage: 91.31%
- Frontend TypeScript: 통과
- Frontend Vitest: 4개 통과
- Frontend production build: 통과
- Docker Compose config: 통과
- PostgreSQL 17 Migration: 빈 DB에서 Head 적용, Workflow Table/FK/Check/Trigger 확인
- API/Web Docker Image Build: 통과
- Chromium 1440px 실제 렌더링: Overview, Incidents, Approvals, Playbooks, Workflows 확인

호스트 기본 `python3`에는 개발 Dependency가 없다. Python 3.12 검사는 기존 `.venv312`를
Python 3.12 Container에서 사용하며 `PYTHONPATH=/app/src`를 설정했다.

## 중요한 경계

- 데모 모드 지표와 Integration 상태는 문서·UI 검증 Fixture다.
- 일반 경로는 Incident/Playbook/Workflow API를 사용하지만 Workspace와 Actor는 로컬 개발
  기본값이다.
- Approval 화면은 Incident Lifecycle 전이를 사용하며 독립 Approval Aggregate는 아직 없다.
- Workflow Engine은 실행 상태와 감사 원장을 구현했지만 Celery Adapter Dispatcher는 아직
  연결되지 않았다.
- 실제 Vendor Adapter 실행과 Webhook Signature/Replay 방지는 아직 없다.
- `responding` 상태는 Patchtower 작업이 실제 실행되었다는 의미가 아니다.
- 운영 배포에는 Identity Gateway, TLS, Network Policy와 승인된 Secret Manager가 필요하다.

## 다음 작업

1. Celery가 Current Step을 Adapter로 Dispatch하고 결과 API를 호출하도록 연결한다.
2. Worker 중단 후 재개, Delivery Semantics와 Result Authenticity를 검증한다.
3. 독립 Approval Aggregate와 다중 승인·만료·재승인 정책을 구현한다.
4. 실제 Vendor Adapter에 Target Scope, Dry-run과 Credential Policy를 연결한다.
5. Inbound Alert Webhook Signature와 Replay 방지를 구현한다.

각 기능은 Domain → Application Port → Infrastructure → API → Dashboard → Test → Document
순서로 완성하고, 아직 구현되지 않은 외부 실행을 UI에서 성공으로 표현하지 않는다.

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
