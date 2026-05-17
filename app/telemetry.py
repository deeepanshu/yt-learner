from __future__ import annotations

import atexit
import logging
import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from opentelemetry import _logs, metrics
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

LOGGER = logging.getLogger(__name__)
_OTEL_HANDLER_ATTR = "_yt_learner_otel_handler"


def _configured_signal_endpoint(signal_name: str) -> str | None:
    for name in (f"OTEL_EXPORTER_OTLP_{signal_name.upper()}_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def _configured_metrics_endpoint() -> str | None:
    return _configured_signal_endpoint("metrics")


def _configured_logs_endpoint() -> str | None:
    return _configured_signal_endpoint("logs")


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


def _resource_for(service_name: str) -> Resource:
    return Resource.create(
        {
            "service.name": service_name,
            "service.version": _service_version(),
        }
    )


def configure_logging(service_name: str, *, level: int = logging.INFO) -> None:
    logging.basicConfig(level=level)

    endpoint = _configured_logs_endpoint()
    if endpoint is None:
        LOGGER.info("OpenTelemetry logs disabled for %s; no OTLP endpoint configured", service_name)
        return

    root_logger = logging.getLogger()
    if any(getattr(handler, _OTEL_HANDLER_ATTR, False) for handler in root_logger.handlers):
        return

    try:
        provider = LoggerProvider(resource=_resource_for(service_name))
        provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
        _logs.set_logger_provider(provider)
        handler = LoggingHandler(level=level, logger_provider=provider)
        setattr(handler, _OTEL_HANDLER_ATTR, True)
        root_logger.addHandler(handler)
        root_logger.setLevel(level)
        atexit.register(provider.shutdown)
    except Exception:
        LOGGER.exception("Unable to initialize OpenTelemetry logs for %s", service_name)


def configure_telemetry(service_name: str) -> NoopTelemetry | OTelTelemetry:
    endpoint = _configured_metrics_endpoint()
    if endpoint is None:
        LOGGER.info("OpenTelemetry metrics disabled for %s; no OTLP endpoint configured", service_name)
        return NoopTelemetry()

    try:
        exporter = OTLPMetricExporter()
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=_export_interval_millis(),
        )
        provider = MeterProvider(resource=_resource_for(service_name), metric_readers=[reader])
        metrics.set_meter_provider(provider)
        atexit.register(provider.shutdown)
    except Exception:
        LOGGER.exception("Unable to initialize OpenTelemetry metrics for %s", service_name)
        return NoopTelemetry()

    meter = metrics.get_meter(_meter_name_for(service_name), _service_version())
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
