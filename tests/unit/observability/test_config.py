import pytest

from observability.config import ObservabilitySettings

_ENV_VARS = (
    "OBSERVABILITY_ENABLED",
    "OTEL_SDK_DISABLED",
    "OTEL_SERVICE_NAME",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_TRACES_SAMPLER_ARG",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "LOG_FILE",
    "DEPLOYMENT_ENVIRONMENT",
)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    settings = ObservabilitySettings.from_env()

    assert settings.enabled is True
    assert settings.service_name == "r2framework-api"
    assert settings.endpoint == "http://localhost:4318"
    assert settings.sample_ratio == 1.0
    assert settings.log_format == "json"


def test_disabled_by_flag_or_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "false")
    assert ObservabilitySettings.from_env().enabled is False

    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert ObservabilitySettings.from_env().enabled is False


def test_sample_ratio_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "5")
    assert ObservabilitySettings.from_env().sample_ratio == 1.0

    monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "-1")
    assert ObservabilitySettings.from_env().sample_ratio == 0.0

    monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "not-a-number")
    assert ObservabilitySettings.from_env().sample_ratio == 1.0
