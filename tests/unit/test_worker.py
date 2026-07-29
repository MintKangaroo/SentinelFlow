from pydantic import SecretStr

from sentinelflow.config import Settings
from sentinelflow.worker import create_celery_app


def test_worker_uses_json_only_serialization() -> None:
    app = create_celery_app(Settings(redis_url=SecretStr("redis://broker:6379/5")))

    assert app.conf.broker_url == "redis://broker:6379/5"
    assert app.conf.result_backend == "redis://broker:6379/5"
    assert app.conf.accept_content == ["json"]
    assert app.conf.task_serializer == "json"
    assert app.conf.result_serializer == "json"
    assert app.conf.broker_connection_retry_on_startup is True
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.worker_prefetch_multiplier == 1
