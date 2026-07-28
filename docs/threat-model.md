# 위협 모델

## 보호 자산

- Workspace 데이터와 격리 경계
- Alert, Incident, Timeline과 Evidence
- 향후 Approval 결정, Action 입력·출력, Audit Event와 Report
- 허가된 대상 범위와 실행 권한
- 불투명한 Integration Credential Reference
- PostgreSQL과 Telemetry의 운영 Metadata

## 3단계 신뢰 경계

- Browser와 API 입력은 모두 신뢰하지 않는다.
- Workspace와 Actor Header는 Identity Gateway가 인증 정보에 결합하기 전까지 신뢰하지 않는다.
- Incident Title, Description, Note, ID와 Event Data는 신뢰하지 않는다.
- PostgreSQL과 Redis는 별도 Network Dependency다.
- Celery Message는 JSON만 허용하며 Pickle 같은 실행 가능 Serializer를 거부한다.
- OTLP Export는 Process 경계를 넘으며 Compose 외부에서는 기본 비활성화된다.
- Container Image와 npm/Python Dependency는 Supply-chain 입력이다.
- 외부 Service Origin, Path, Header, Status Code와 Response Body는 신뢰하지 않는다.
- Secret Manager Provider는 권한 있는 Dependency이며 Workspace 범위를 강제해야 한다.

## 플랫폼 통제

- Production 환경에서 API 문서를 비활성화한다.
- CORS는 명시적 Origin, 필요한 Method와 최소 Header만 허용한다.
- nginx는 Content Type, Framing, Referrer와 Content Security Policy Header를 추가한다.
- Readiness 오류는 Dependency 상태만 노출하고 Exception과 Connection String을 숨긴다.
- Connection String은 Secret-aware 설정 Type을 사용한다.
- Base Image가 허용하는 곳에서 Service를 비특권 사용자로 실행한다.
- CI 권한은 Repository Read-only이며 Backend, Frontend, Compose를 검사한다.

## Incident 통제

- 모든 Incident Query는 명시적 UUID Workspace 범위를 포함한다.
- Event 외래키는 Incident ID와 Workspace ID를 함께 결합한다.
- 쓰기에는 Actor와 Workspace 안에서 유일한 Idempotency Key가 필요하다.
- 낙관적 Aggregate Version이 오래된 동시 변경을 거부한다.
- ORM Hook과 PostgreSQL Trigger가 Timeline Update/Delete를 거부한다.
- 다른 Workspace와 존재하지 않는 Incident 조회는 동일한 Sanitized `404`를 반환한다.

Workspace Header는 격리 Context이지 인증이 아니다. Identity Gateway가 인증 Principal을 허용된
Workspace에 결합하기 전에는 API를 신뢰할 수 없는 Client에 직접 노출하지 않는다.

## Integration Adapter 통제

- 영속화할 수 있는 Credential은 원문이 아닌 불투명 UUID Reference다.
- Secret 조회에는 Workspace ID가 필요하고 Provider 실패에서 식별자를 제거한다.
- Base URL은 기본 HTTPS이며 Credential, Path, Query와 Fragment를 포함할 수 없다.
- 요청별 Absolute URL, Network-path Reference, Redirect와 CR/LF Header를 거부한다.
- Caller가 Auth, Workspace, Correlation, Idempotency Header를 덮어쓰지 못한다.
- Retry 횟수와 Backoff를 제한하고 비멱등 호출에는 Idempotency Key를 요구한다.
- Network Phase 및 전체 연산 Timeout으로 Worker 무한 점유를 방지한다.
- Circuit Breaker는 최종 논리 호출 실패만 집계하고 Open 상태에서 빠르게 실패한다.
- Detached Response는 Authentication Header가 있는 Request 객체를 보존하지 않는다.
- Trace Attribute에 URL Query, Request/Response Body와 Credential을 포함하지 않는다.

## 이후 단계의 필수 통제

Inbound Webhook 또는 위험 작업을 출시하기 전에 다음 통제를 완료해야 한다.

- 운영 Secret Manager Adapter
- 요청 서명 검증과 Webhook Replay 방지
- 인증 정보에 결합된 Workspace Authorization
- 전역 Append-only Audit Event
- 위험도 기반 Human Approval, 만료와 재승인
- 변경 전 Mandatory Dry-run
- Rollback과 Compensation
- 승인된 대상 범위 검증

AI 판단만으로 고위험 작업을 실행할 수 없다.

AutoPentest는 소유하거나 명시적으로 허가받은 대상에만 사용할 수 있다. 공개 Internet 탐색,
Credential 탈취, Persistence, Evasion, Malware 배포, 데이터 파괴와 Exfiltration은
프로젝트 범위를 벗어난다.
