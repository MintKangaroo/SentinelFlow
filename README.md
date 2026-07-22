# SentinelFlow

SentinelFlow는 탐지, 분석, 승인, 대응, 검증, 보고 과정을 하나로 연결하는
AI-Native Security Operations Control Plane입니다. 연동된 보안 서비스의 내부 기능을
복제하지 않고, 각 서비스가 본래 역할을 수행하도록 조정하고 통제합니다.

> 현재 상태: 1단계 플랫폼 기반 구축 완료. Incident 워크플로와 외부 서비스 Adapter는
> 의도적으로 아직 구현하지 않았습니다.

## 목표

SentinelFlow는 후속 단계에서 다음 보안 서비스를 Adapter 방식으로 연결합니다.

| 서비스 | 역할 |
| --- | --- |
| AI-SOC Dashboard | 탐지 및 Alert 수집 |
| ThreatGraph | IOC와 관계 분석 |
| RedMind | AI 기반 분석 및 대응 계획 제안 |
| Patchtower | 서버 점검, 패치 및 복구 |
| AutoPentest AI | 허가된 공격 경로 검증 |
| AIShield | AI 모델 강건성 평가 |

최종적으로 다음 대응 흐름을 일관된 감사 기록과 명시적 승인 절차 아래 연결합니다.

```text
Alert 수신 → Incident 생성 → ThreatGraph 상관분석 → AI 분석
→ Playbook 제안 → Human Approval → 대응 실행 → 결과 검증
→ Incident 종료 → 사후 보고서
```

## 현재 플랫폼 기반

- 생존 상태와 의존성 준비 상태를 분리한 FastAPI Control API
- 비동기 SQLAlchemy 기반 PostgreSQL 연결과 Alembic 마이그레이션 기준선
- JSON 메시지만 허용하는 Redis 기반 Celery Worker 경계
- 보안 설정을 적용한 nginx가 제공하는 React 및 TypeScript 웹 셸
- 로컬 Collector를 통한 OpenTelemetry Trace 전송
- 재현 가능한 Docker Compose 개발 스택과 CI 품질 게이트

## 전체 스택 실행

전체 플랫폼 기반은 Docker Compose로 실행할 수 있습니다.

```bash
cp .env.example .env
docker compose up --build
```

기동 후 다음 주소에 접속합니다.

- 웹 셸: <http://localhost:3000>
- API 서비스 정보: <http://localhost:8000/>
- API 문서: <http://localhost:8000/docs>
- 의존성 준비 상태: <http://localhost:8000/api/v1/health/ready>

`.env.example`의 값은 로컬 개발 전용 예시입니다. 공유 환경에서 사용하기 전에 반드시
변경해야 하며, Integration Credential을 이 저장소나 애플리케이션 데이터베이스에 원문으로
저장해서는 안 됩니다.

기본 포트가 이미 사용 중이면 `.env`에서 `WEB_PORT`와 `API_PORT`를 변경할 수 있습니다.

## 로컬 개발

Python 3.12 이상과 Node.js 20 이상이 필요합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
cd web && npm ci && cd ..
make check
```

API와 웹 개발 서버는 각각 `make api`, `make web`으로 실행합니다. PostgreSQL과 Redis 연결
설정은 `SENTINELFLOW_` 환경 변수 접두사를 사용하며, 전체 설정 예시는
[.env.example](.env.example)에서 확인할 수 있습니다.

## 현재 구현 범위

현재 단계에는 Incident 모델, Playbook, Workflow 상태 머신, 승인 게이트, 대응 작업,
검증 실행 및 외부 서비스 Adapter가 포함되지 않습니다. 해당 기능은
[단계별 로드맵](docs/roadmap.md)에 따라 순차적으로 구현합니다.

현재 스택은 다음 플랫폼 경계만 제공합니다.

- API 프로세스 및 요청 경계
- PostgreSQL 영속성 및 마이그레이션 경계
- Redis 조정 계층과 Celery 비동기 실행 경계
- React 웹 클라이언트와 nginx 제공 경계
- OpenTelemetry 관측성 경계

## 보안

SentinelFlow는 운영자가 방어와 테스트를 명시적으로 허가받은 시스템에서만 사용해야 합니다.
Integration Credential 원문 저장 금지, 요청 서명 검증, Webhook Replay 방지, Workspace 격리,
Human Approval, Dry-run, Rollback 및 전체 감사 로그와 같은 필수 통제는 각 관련 구현 단계에서
검증 가능한 형태로 추가됩니다. AI의 판단만으로 위험 작업을 실행하는 것은 허용하지 않습니다.

자세한 내용은 [보안 정책](SECURITY.md)과 [위협 모델](docs/threat-model.md)을 참고하십시오.
이 프로젝트는 MIT License를 따릅니다.
