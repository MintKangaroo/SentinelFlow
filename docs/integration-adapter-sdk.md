# Integration Adapter SDK

## 목적

Integration Adapter SDK는 AI-SOC Dashboard, ThreatGraph, RedMind, Patchtower,
AutoPentest AI, AIShield가 서로 다른 인증과 REST 계약을 사용하더라도 SentinelFlow의
공통 보안·복원력 정책을 일관되게 적용하기 위한 기반이다.

SDK는 Vendor 기능을 구현하지 않는다. 각 Vendor Adapter는 요청과 응답 Schema 변환에만
집중하고, 인증, Credential 조회, Timeout, Retry, Circuit Breaker와 Telemetry는 공통
`IntegrationHTTPClient`에 위임한다.

## 패키지 구성

| 모듈 | 책임 |
| --- | --- |
| `credentials.py` | 불투명한 CredentialReference와 workspace-scoped SecretManager Port |
| `auth.py` | Bearer, API Key, Basic, No Auth 전략 |
| `policies.py` | Timeout, Retry, Circuit Breaker 정책 값 |
| `circuit.py` | Closed/Open/Half-open 상태와 Recovery Probe |
| `client.py` | 고정 Origin REST 요청, Retry, Timeout, Error 정규화, Trace |
| `base.py` | 구체 Vendor REST Adapter가 상속 또는 합성할 최소 기반 |
| `models.py` | 요청 Context와 Request 객체에서 분리된 Response |
| `errors.py` | Credential과 응답 본문을 노출하지 않는 안정적인 오류 계약 |

## Credential 경계

애플리케이션과 PostgreSQL에는 UUID 형태의 `CredentialReference`만 저장할 수 있다.
실제 Secret은 호출 시점에 다음 Port를 통해 해석한다.

```python
class SecretManager(Protocol):
    async def resolve(
        self,
        *,
        workspace_id: UUID,
        reference: CredentialReference,
    ) -> SecretStr: ...
```

`workspace_id`를 필수 인자로 두어 다른 Workspace의 Credential을 참조하는 실수를
Secret Manager Adapter에서도 차단할 수 있게 한다. Provider 오류는
`CredentialResolutionError`로 정규화하며 Reference ID와 Provider 응답을 오류 메시지에
포함하지 않는다.

운영 구현체는 Vault 또는 Cloud Secret Manager를 연결해야 한다. 원문 Secret을 DB,
Integration 설정 JSON, Log, Trace Attribute, Exception Message에 보관해서는 안 된다.

## Retry 안전성

기본 Retry 대상 Status는 `408`, `425`, `429`, `500`, `502`, `503`, `504`다.

- GET, HEAD, OPTIONS, PUT, DELETE는 HTTP 멱등 의미에 따라 Retry할 수 있다.
- POST, PATCH 등은 `AdapterRequestContext.idempotency_key`가 있을 때만 Retry한다.
- `max_attempts`는 최초 호출을 포함하며 1~10으로 제한한다.
- Numeric `Retry-After`를 사용하되 `max_backoff_seconds`보다 길게 대기하지 않는다.
- 개별 Retry는 Circuit Breaker 실패 횟수로 계산하지 않는다.

실제 대응 Adapter는 API가 Idempotency Key를 처리하는지 확인해야 한다. 지원하지 않는
Vendor 쓰기 API는 SDK Retry를 사용하지 않고 Workflow 수준의 명시적인 재시도와 검토를
사용한다.

## Timeout

`TimeoutPolicy`는 connect, read, write, pool Timeout과 전체 논리 연산 Timeout을 분리한다.
전체 연산 Timeout에는 Retry Backoff도 포함된다. 따라서 느린 Dependency가 Worker를
무기한 점유하지 못한다.

## Circuit Breaker

```text
closed -- failure threshold 도달 --> open
open -- recovery timeout 경과 --> half_open
half_open -- 단일 probe 성공 --> closed
half_open -- 실패/중립 취소 --> open
```

Half-open에서는 하나의 Recovery Probe만 허용한다. Circuit 상태에는 Service 이름, 상태,
실패 횟수와 재시도 가능 시간만 포함하며 Credential, URL Query, 요청·응답 Body는 포함하지
않는다.

## SSRF와 Credential 전달 방지

- Base URL은 기본적으로 HTTPS만 허용한다.
- Base URL에 Username, Password, Query, Fragment, Path를 넣을 수 없다.
- 호출별 Path는 `/`로 시작하는 동일 Origin 상대 경로여야 한다.
- 외부 Absolute URL과 Network-path Reference(`//host/path`)를 거부한다.
- Redirect를 따라가지 않는다.
- Authorization, Idempotency Key, Workspace, Correlation Header는 SDK가 관리한다.
- Header Name과 Value의 CR/LF를 거부한다.
- 테스트용 HTTP Origin은 `allow_insecure_http=True`를 명시한 경우에만 허용한다.

## 오류 계약

| 오류 | 의미 |
| --- | --- |
| `CredentialResolutionError` | Secret을 안전하게 해석할 수 없음 |
| `CircuitOpenError` | Circuit이 열려 요청을 시도하지 않음 |
| `AdapterTimeoutError` | Network Phase 또는 전체 연산 Timeout |
| `AdapterTransportError` | Dependency 연결 실패 |
| `AdapterHTTPError` | 원격 서비스의 비성공 응답 |
| `IntegrationConfigurationError` | 안전하지 않거나 잘못된 Adapter 설정 |

`AdapterHTTPError.response`에는 Vendor Adapter가 오류 코드를 해석하기 위한 Body가 있지만,
오류 문자열에는 Body를 넣지 않는다. 상위 계층은 해당 객체를 그대로 Log에 기록하지 말고
승인된 Field만 Audit Evidence로 추출해야 한다.
`Set-Cookie`, `WWW-Authenticate`, `Proxy-Authenticate` 같은 인증성 응답 Header는 Detached
Response에서 제거한다.

## Vendor Adapter 작성 규칙

1. `RESTAdapter`를 합성하거나 상속한다.
2. 안정적인 `service_name`과 고정 HTTPS Origin을 사용한다.
3. Domain 객체를 Vendor JSON에 직접 결합하지 않고 명시적 Schema 변환을 둔다.
4. 모든 요청에 `AdapterRequestContext`를 전달한다.
5. 위험한 쓰기는 Workflow, Human Approval, dry-run Gate가 준비되기 전에 호출하지 않는다.
6. 응답에서 필요한 Evidence만 추출하고 Credential 또는 불필요한 개인정보를 보존하지 않는다.
7. Unit Test는 MockTransport를 사용하고 운영 Endpoint에 접근하지 않는다.

## 테스트 범위

- Workspace-scoped Credential 조회
- Bearer, API Key, Basic, No Auth
- Retry Status, 지수 Backoff와 Retry-After 상한
- POST Idempotency Key 유무에 따른 Retry 차이
- HTTP Phase 및 전체 연산 Timeout
- Circuit Open, Fast Fail, Half-open Recovery
- Redirect 차단과 고정 Origin
- Header Injection, Absolute URL, 잘못된 Base URL 거부
- Sanitized Error Message와 Detached Response
