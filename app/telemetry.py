from __future__ import annotations

import atexit
import logging
import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

LOGGER = logging.getLogger(__name__)


def _configured_metrics_endpoint() -> str | None:
    for name in ("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def _service_version() -> str:
    try:
        return version("yt-learner")
    except PackageNotFoundError:
        return "0.1.0"


def _export_interval_millis() -> int:
    raw = os.getenv("YT_LEARNER_OTEL_EXPORT_INTERVAL_MS", "").strip()
    if not raw:
        return 5000
    try:
        return int(raw)
    except ValueError:
        LOGGER.warning(
            "Invalid YT_LEARNER_OTEL_EXPORT_INTERVAL_MS=%r; using default 5000ms",
            raw,
        )
        return 5000


class NoopTelemetry:
    def record_job_enqueued(self, *, source: str) -> None:
        return None

    def record_job_processed(
        self,
        *,
        source: str,
        status: str,
        duration_seconds: float,
        reused_existing: bool | None = None,
        error_type: str | None = None,
    ) -> None:
        return None


@dataclass
class OTelTelemetry:
    jobs_enqueued: object
    jobs_processed: object
    processing_duration: object

    def record_job_enqueued(self, *, source: str) -> None:
        self.jobs_enqueued.add(1, {"source": source})

    def record_job_processed(
        self,
        *,
        source: str,
        status: str,
        duration_seconds: float,
        reused_existing: bool | None = None,
        error_type: str | None = None,
    ) -> None:
        attributes = {
            "source": source,
            "status": status,
        }
        if reused_existing is not None:
            attributes["reused_existing"] = str(reused_existing).lower()
        if error_type is not None:
            attributes["error_type"] = error_type
        self.jobs_processed.add(1, attributes)
        self.processing_duration.record(duration_seconds, attributes)


def _meter_name_for(service_name: str) -> str:
    return service_name.replace("-", ".")


def configure_telemetry(service_name: str) -> NoopTelemetry | OTelTelemetry:
    endpoint = _configured_metrics_endpoint()
    if endpoint is None:
        LOGGER.info("OpenTelemetry metrics disabled for %s; no OTLP endpoint configured", service_name)
        return NoopTelemetry()

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": _service_version(),
        }
    )

    try:
        exporter = OTLPMetricExporter()
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=_export_interval_millis(),
        )
        provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(provider)
        atexit.register(provider.shutdown)
    except Exception:
        LOGGER.exception("Unable to initialize OpenTelemetry metrics for %s", service_name)
        return NoopTelemetry()

    meter = metrics.get_meter(_meter_name_for(service_name), _service_version())
    is_discord = service_name == "yt-learner-discord"
    return OTelTelemetry(
        jobs_enqueued=meter.create_counter(
            "yt_learner_discord_jobs_enqueued_total",
            description="Number of yt-learner jobs accepted by the bot",
            unit="1",
        ),
        jobs_processed=meter.create_counter(
            "yt_learner_worker_jobs_processed_total",
            description="Number of yt-learner jobs finished by the worker",
            unit="1",
        ),
        processing_duration=meter.create_histogram(
            "yt_learner_worker_job_processing_duration_seconds",
            description="End-to-end worker processing duration per job",
            unit="s",
        ),
    )
