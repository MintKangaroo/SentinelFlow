import pytest

from sentinelflow.integrations import (
    CircuitBreakerPolicy,
    CircuitOpenError,
    CircuitState,
)
from sentinelflow.integrations.circuit import CircuitBreaker
from tests.unit.integrations.helpers import FakeClock


@pytest.mark.asyncio
async def test_circuit_opens_rejects_and_closes_after_successful_probe() -> None:
    clock = FakeClock()
    circuit = CircuitBreaker(
        "threatgraph",
        CircuitBreakerPolicy(failure_threshold=2, recovery_timeout_seconds=10),
        clock=clock,
    )

    await circuit.before_request()
    await circuit.record_failure()
    await circuit.before_request()
    await circuit.record_failure()

    snapshot = await circuit.snapshot()
    assert snapshot.state is CircuitState.OPEN
    assert snapshot.failure_count == 2
    assert snapshot.retry_after_seconds == 10

    with pytest.raises(CircuitOpenError) as captured:
        await circuit.before_request()
    assert captured.value.retry_after_seconds == 10

    clock.advance(10)
    await circuit.before_request()
    with pytest.raises(CircuitOpenError):
        await circuit.before_request()

    await circuit.record_success()
    snapshot = await circuit.snapshot()
    assert snapshot.state is CircuitState.CLOSED
    assert snapshot.failure_count == 0


@pytest.mark.asyncio
async def test_failed_or_neutral_half_open_probe_reopens_circuit() -> None:
    clock = FakeClock()
    circuit = CircuitBreaker(
        "redmind",
        CircuitBreakerPolicy(failure_threshold=1, recovery_timeout_seconds=5),
        clock=clock,
    )
    await circuit.before_request()
    await circuit.record_failure()

    clock.advance(5)
    await circuit.before_request()
    await circuit.record_neutral()
    assert (await circuit.snapshot()).state is CircuitState.OPEN

    clock.advance(5)
    await circuit.before_request()
    await circuit.record_failure()
    assert (await circuit.snapshot()).state is CircuitState.OPEN
