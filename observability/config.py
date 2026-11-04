"""Observability configuration, resolved from ``settings``."""

from __future__ import annotations

from dataclasses import dataclass, replace

import settings


@dataclass(frozen=True, slots=True)
class ObservabilitySettings:
    """Resolved observability configuration.

    Values come from ``settings.py`` (and so from ``.env``); build it with
    ``from_settings`` and override fields there, e.g. in tests.
    """

    enabled: bool
    service_name: str
    service_namespace: str
    environment: str
    endpoint: str
    sample_ratio: float
    log_level: str
    log_format: str
    log_file: str | None
    log_file_max_bytes: int
    log_file_backup_count: int
    strands_log_level: str

    def otlp_endpoint(self, signal: str) -> str:
        """Return the OTLP/HTTP URL for a signal such as ``traces`` or ``logs``."""
        return f"{self.endpoint.rstrip('/')}/v1/{signal}"

    @classmethod
    def from_settings(cls, **overrides: object) -> ObservabilitySettings:
        resolved = cls(
            enabled=settings.OBSERVABILITY_ENABLED,
            service_name=settings.OTEL_SERVICE_NAME,
            service_namespace=settings.OTEL_SERVICE_NAMESPACE,
            environment=settings.DEPLOYMENT_ENVIRONMENT,
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            sample_ratio=settings.OTEL_TRACES_SAMPLER_ARG,
            log_level=settings.LOG_LEVEL,
            log_format=settings.LOG_FORMAT,
            log_file=settings.LOG_FILE,
            log_file_max_bytes=settings.LOG_FILE_MAX_BYTES,
            log_file_backup_count=settings.LOG_FILE_BACKUP_COUNT,
            strands_log_level=settings.STRANDS_LOG_LEVEL,
        )
        resolved = replace(resolved, **overrides)
        # A sampler ratio outside [0, 1] is a misconfiguration; clamp it.
        return replace(resolved, sample_ratio=min(max(resolved.sample_ratio, 0.0), 1.0))
