from unittest.mock import MagicMock

from fastapi import FastAPI

import sentinelflow.observability as observability
from sentinelflow.config import Settings


def test_telemetry_is_opt_in() -> None:
    assert observability.configure_telemetry(FastAPI(), Settings(otel_enabled=False)) is None


def test_telemetry_instruments_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    provider = MagicMock()
    provider_factory = MagicMock(return_value=provider)
    exporter = MagicMock()
    exporter_factory = MagicMock(return_value=exporter)
    processor = MagicMock()
    processor_factory = MagicMock(return_value=processor)
    resource = MagicMock()
    resource_type = MagicMock()
    resource_type.create.return_value = resource
    trace_api = MagicMock()
    instrumentor = MagicMock()
    monkeypatch.setattr(observability, "TracerProvider", provider_factory)
    monkeypatch.setattr(observability, "OTLPSpanExporter", exporter_factory)
    monkeypatch.setattr(observability, "BatchSpanProcessor", processor_factory)
    monkeypatch.setattr(observability, "Resource", resource_type)
    monkeypatch.setattr(observability, "trace", trace_api)
    monkeypatch.setattr(observability, "FastAPIInstrumentor", instrumentor)
    app = FastAPI()
    settings = Settings(
        environment="test",
        otel_enabled=True,
        otel_service_name="test-api",
        otel_exporter_otlp_endpoint="http://collector:4317",
    )

    result = observability.configure_telemetry(app, settings)

    assert result is provider
    exporter_factory.assert_called_once_with(endpoint="http://collector:4317", insecure=True)
    processor_factory.assert_called_once_with(exporter)
    provider.add_span_processor.assert_called_once_with(processor)
    trace_api.set_tracer_provider.assert_called_once_with(provider)
    instrumentor.instrument_app.assert_called_once()
