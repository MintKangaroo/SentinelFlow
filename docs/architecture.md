# 아키텍처

## 현재 Runtime

SentinelFlow는 각 프로세스와 외부 서비스를 교체 가능한 경계로 분리한다. 2단계에서
Framework 비의존 Incident 정책과 Workspace 범위 영속성을 추가했고, 3단계에서는 외부
서비스를 안전하게 연결할 공통 Adapter SDK를 추가했다. 현재 React Operations Console은
이 기반 위에서 Incident Queue, Timeline Inspector, Lifecycle Action, Versioned Playbook,
Workflow Run, Approval 및 Integration View를 제공한다.

```text
Browser ──HTTP──> nginx web ──/api──> FastAPI
                                      ├── IncidentService ──> PostgreSQL
                                      ├── PlaybookService ──> PostgreSQL
                                      ├── WorkflowService ──> PostgreSQL
                                      ├── Integration Adapter SDK
                                      │    └── External security services
                                      ├── Redis (coordination and broker)
                                      └── OTLP ──> OpenTelemetry Collector
Celery worker <──────── Redis ────────┘
```

API는 요청 검증과 동기 Command/Query 경계를 소유한다. Celery는 이후 단계에서 Workflow
Step을 Vendor Adapter로 Dispatch한다. PostgreSQL은 내구성 있는 유일한 System of Record이며 Redis는
두 번째 원장으로 사용하지 않는다. React 애플리케이션은 API Client이고 PostgreSQL, Redis,
외부 보안 서비스에 직접 연결하지 않는다.

## Operations Console

웹 애플리케이션은 두 실행 모드를 제공한다.

- 기본 경로(`/`)는 Readiness, Incident, Playbook, Workflow의 Query와 지원되는 Command를
  FastAPI에서 읽고 쓴다.
- `?demo=1`은 서버 상태와 관계없이 동일한 운영 흐름을 재현하는 결정적 데이터셋을 사용한다.
  README 스크린샷과 UI 회귀 검증은 이 모드를 사용한다.

Approval 화면은 독립 Approval Aggregate의 quorum·역할·만료·갱신 정책을 표시한다.
Incident의 `awaiting_approval → responding` 전이는 승인 결과를 반영하는 실행 상태이며,
Approval 결정과 이벤트는 별도 append-only 원장으로 보존된다. Integration 화면의 운영 상태는
데모 데이터이며 실제 Vendor Health API가 아니다.

## 내부 요청 흐름

Incident Command는 다음 방향으로 흐른다.

```text
FastAPI Schema/Header 검증
  └─> IncidentService
       ├─> Incident Aggregate 상태 전이 정책
       └─> IncidentUnitOfWork Port
            └─> SQLAlchemy Repository ──> PostgreSQL
```

Application Service는 Aggregate Version과 Timeline Event를 하나의 Transaction에 기록한다.
모든 Query는 `workspace_id`를 포함하고, 데이터베이스도 Incident와 Workspace 복합 외래키로
Event 범위를 강제한다. PostgreSQL Trigger는 Timeline 수정과 삭제를 거부한다.

외부 REST 요청은 다음 방향으로 흐른다.

```text
Vendor Adapter
  └─> IntegrationHTTPClient
       ├─> SecretManager.resolve(workspace_id, credential_reference)
       ├─> Auth Header 생성
       ├─> Timeout / Retry / Circuit Breaker
       ├─> 고정 HTTPS Origin 요청
       └─> Request 객체와 분리된 AdapterResponse
```

Vendor Adapter는 Domain 정책이나 Vendor 내부 기능을 복제하지 않는다. 요청과 응답 변환만
담당하고 공통 보안 정책은 `IntegrationHTTPClient`에 위임한다.

## Package 경계

- `sentinelflow.api`: HTTP Application Factory와 Transport Schema
- `sentinelflow.domain`: Incident, Playbook, Workflow Aggregate와 상태 정책
- `sentinelflow.application`: Domain Use Case와 Repository/Unit-of-Work Port
- `sentinelflow.infrastructure`: SQLAlchemy, PostgreSQL, Redis Adapter
- `sentinelflow.integrations`: Secret, Auth, Retry, Timeout, Circuit Breaker, REST Adapter SDK
- `sentinelflow.runtime`: Runtime Dependency 주입을 위한 작은 Protocol
- `sentinelflow.worker`: Celery Bootstrap
- `migrations`: 버전이 관리되는 Database Schema 이력
- `web`: React/TypeScript Client와 nginx Runtime
- `deploy`: Process Entry Point와 OpenTelemetry Collector 설정

Domain 정책은 FastAPI, SQLAlchemy, Celery, HTTPX, Vendor SDK에 의존하지 않는다.

## Versioned Playbook 일관성

- Playbook Aggregate Version은 Revision 번호와 분리한다. Revision 생성, Publish, Archive가
  Aggregate Version을 증가시키며 오래된 Expected Version은 거부한다.
- Revision은 1부터 단조 증가하고 생성된 Step Definition은 수정·삭제하지 않는다.
- Active Version은 Immutable Revision을 가리키는 Pointer이며 Publish는 내용을 복사하거나
  변경하지 않는다.
- Canonical JSON SHA-256 Hash로 동일 Definition을 안정적으로 식별한다.
- High/Critical Action은 앞선 Approval Step과 명시적인 Rollback이 모두 있어야 한다.
- Event Sequence는 변경 결과의 Aggregate Version과 같고 Workspace 범위 Idempotency Key를
  함께 보존한다.

## Workflow 실행 일관성

- Run 생성은 선택한 Immutable Playbook Revision의 ID, 번호, Definition Hash와 실행에 필요한
  Step Metadata를 Snapshot한다. 이후 Playbook Publish는 기존 Run을 바꾸지 않는다.
- Run Aggregate가 모든 Step State를 소유하며 한 Transaction에서 Run, Step, Event를 함께
  저장한다.
- 명시적인 Current Step만 상태를 변경할 수 있고, Expected Version이 오래된 동시 Command를
  거부한다.
- Approval은 `waiting_approval`, 실패 재시도는 Attempt Budget, Timeout은 안정적인 Error
  Code로 표현한다.
- 실패 또는 취소 시 Rollback 정의가 있는 완료 Action을 역순으로 `compensating` 상태로
  활성화한다.
- Event는 Workspace 안에서 Idempotency Key가 유일하며 ORM Hook과 PostgreSQL Trigger가
  Update/Delete를 거부한다.

Workflow Dispatcher는 Celery에서 Redis lease를 획득한 뒤 Adapter를 호출하고, timeout·제한
retry·compensation 결과를 Workflow 원장에 기록한다. 외부 모드에서는 workspace에 바인딩된
allowlist Adapter만 실행하며, 기본 모드는 side effect가 없는 dry-run이다.

## Incident 일관성

- Aggregate Version은 `1`에서 시작하고 상태 변경 또는 Note 추가 때마다 증가한다.
- Client는 `expected_version`을 전달하며 오래된 쓰기는 최신 데이터를 덮어쓰지 못한다.
- Event Sequence는 변경 결과의 Aggregate Version과 같다.
- Idempotency Key는 Workspace 안에서 유일하고 동일한 Operation만 Replay할 수 있다.
- Timeline에는 HTTP 수정/삭제 Route가 없고 ORM 및 PostgreSQL 수준에서 불변이다.

## Adapter 복원력

- HTTP Phase Timeout과 전체 논리 연산 Timeout을 함께 사용한다.
- 멱등하거나 Idempotency Key가 있는 요청만 재시도한다.
- Retry를 모두 소비한 최종 결과만 Circuit 실패 한 번으로 기록한다.
- Circuit이 열리면 외부 요청과 Credential 조회를 시도하지 않는다.
- Recovery Timeout 후 하나의 Half-open Probe만 허용한다.
- 4xx는 Dependency가 응답 가능한 상태이므로 Circuit 실패로 계산하지 않는다.
- 5xx와 기본 Transient Status, Network Error, Timeout은 Circuit 실패로 계산한다.

## Configuration과 Secret

일반 설정은 `SENTINELFLOW_` 접두사 환경 변수로 읽는다. Database와 Redis URL은 로그에서
실수로 표현되지 않도록 Secret-aware Type을 사용한다. Compose Credential은 교체 가능한
로컬 개발용 Placeholder다.

Integration Secret은 PostgreSQL 또는 Domain JSON에 원문으로 저장하지 않는다.
`CredentialReference`는 UUID만 포함하고, 실제 값은 Workspace 범위를 확인하는
`SecretManager` Adapter가 호출 시점에 제공한다. 운영 Secret Manager 구현은 이후 배포
환경에서 Vault 또는 승인된 Cloud Provider를 연결한다.

## 관측성

OpenTelemetry는 Compose 외부에서 기본 비활성화된다. Compose는 API Trace를 로컬 Collector로
보낸다. Integration Span은 안정적인 Service Name, HTTP Method, Status Code만 기록하며 URL
Query, Body, Credential을 기록하지 않는다.

운영 환경은 Debug Exporter를 승인된 관측성 Backend로 교체하고 전송 구간 TLS, 접근 통제,
보존 기간과 민감정보 Filter를 구성해야 한다.
