"""Environment-driven configuration for telemetry and structured logging."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_SERVICE_NAME = "r2framework-api"
DEFAULT_ENDPOINT = "http://localhost:4318"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class ObservabilitySettings:
    """Resolved observability configuration."""

    enabled: bool = True
    service_name: str = DEFAULT_SERVICE_NAME
    environment: str = "development"
    endpoint: str = DEFAULT_ENDPOINT
    sample_ratio: float = 1.0
    log_level: str = "INFO"
    log_format: str = "json"
    log_file: str | None = None

    def otlp_endpoint(self, signal: str) -> str:
        """Return the OTLP/HTTP URL for a signal such as ``traces`` or ``logs``."""
        return f"{self.endpoint.rstrip('/')}/v1/{signal}"

    @classmethod
    def from_env(cls) -> ObservabilitySettings:
        sdk_disabled = _env_bool("OTEL_SDK_DISABLED", False)
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_ENDPOINT).strip()
        return cls(
            enabled=_env_bool("OBSERVABILITY_ENABLED", True) and not sdk_disabled,
            service_name=os.getenv("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME).strip()
            or DEFAULT_SERVICE_NAME,
            environment=os.getenv("DEPLOYMENT_ENVIRONMENT", "development").strip()
            or "development",
            endpoint=endpoint or DEFAULT_ENDPOINT,
            sample_ratio=min(max(_env_float("OTEL_TRACES_SAMPLER_ARG", 1.0), 0.0), 1.0),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            log_format=os.getenv("LOG_FORMAT", "json").lower(),
            log_file=os.getenv("LOG_FILE") or None,
        )
