"""Celery worker bootstrap without domain tasks."""

from celery import Celery

from sentinelflow.config import Settings, get_settings


def create_celery_app(settings: Settings | None = None) -> Celery:
    """Create a JSON-only worker configured for reliable startup."""
    runtime_settings = settings or get_settings()
    redis_url = runtime_settings.redis_url.get_secret_value()
    app = Celery("sentinelflow", broker=redis_url, backend=redis_url)
    app.conf.update(
        accept_content=["json"],
        broker_connection_retry_on_startup=True,
        enable_utc=True,
        result_serializer="json",
        task_serializer="json",
        task_track_started=True,
        timezone="UTC",
        worker_hijack_root_logger=False,
    )
    return app


celery_app = create_celery_app()
