import pytest

import settings
from observability.config import ObservabilitySettings


def test_values_come_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OTEL_SERVICE_NAME", "svc")
    monkeypatch.setattr(settings, "OTEL_SERVICE_NAMESPACE", "ns")
    monkeypatch.setattr(
        settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318/"
    )
    monkeypatch.setattr(settings, "LOG_FILE_MAX_BYTES", 1024)

    resolved = ObservabilitySettings.from_settings()

    assert resolved.service_name == "svc"
    assert resolved.service_namespace == "ns"
    assert resolved.log_file_max_bytes == 1024
    assert resolved.otlp_endpoint("traces") == "http://collector:4318/v1/traces"


def test_overrides_win_over_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OBSERVABILITY_ENABLED", False)

    resolved = ObservabilitySettings.from_settings(enabled=True, log_format="console")

    assert resolved.enabled is True
    assert resolved.log_format == "console"


@pytest.mark.parametrize(
    ("configured", "expected"), [(5.0, 1.0), (-1.0, 0.0), (0.25, 0.25)]
)
def test_sample_ratio_is_clamped(
    monkeypatch: pytest.MonkeyPatch, configured: float, expected: float
) -> None:
    monkeypatch.setattr(settings, "OTEL_TRACES_SAMPLER_ARG", configured)

    assert ObservabilitySettings.from_settings().sample_ratio == expected
