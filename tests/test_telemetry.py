from __future__ import annotations

import logging

from app import telemetry


class FakeRootLogger:
    def __init__(self) -> None:
        self.handlers = []
        self.level = None

    def addHandler(self, handler) -> None:
        self.handlers.append(handler)

    def setLevel(self, level) -> None:
        self.level = level

    def removeHandler(self, handler) -> None:
        if handler in self.handlers:
            self.handlers.remove(handler)


def test_configure_logging_skips_otel_when_endpoint_missing(monkeypatch) -> None:
    basic_config_calls = []

    monkeypatch.setattr(telemetry, "_configured_logs_endpoint", lambda: None)
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: basic_config_calls.append(kwargs))

    telemetry.configure_logging("yt-learner-discord")

    assert basic_config_calls == [{"level": logging.INFO}]


def test_configure_logging_adds_otel_handler_once(monkeypatch) -> None:
    root_logger = FakeRootLogger()
    basic_config_calls = []
    set_provider_calls = []
    atexit_calls = []
    providers = []

    class FakeProvider:
        def __init__(self, *, resource) -> None:
            self.resource = resource
            self.processors = []
            providers.append(self)

        def add_log_record_processor(self, processor) -> None:
            self.processors.append(processor)

        def shutdown(self) -> None:
            return None

    class FakeProcessor:
        def __init__(self, exporter) -> None:
            self.exporter = exporter

    class FakeHandler:
        def __init__(self, *, level, logger_provider) -> None:
            self.level = level
            self.logger_provider = logger_provider

    monkeypatch.setattr(telemetry, "_configured_logs_endpoint", lambda: "http://collector:4318/v1/logs")
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: basic_config_calls.append(kwargs))
    monkeypatch.setattr(logging, "getLogger", lambda name=None: root_logger if name is None else logging.Logger(name))
    monkeypatch.setattr(telemetry, "LoggerProvider", FakeProvider)
    monkeypatch.setattr(telemetry, "BatchLogRecordProcessor", FakeProcessor)
    monkeypatch.setattr(telemetry, "OTLPLogExporter", lambda: "exporter")
    monkeypatch.setattr(telemetry, "LoggingHandler", FakeHandler)
    monkeypatch.setattr(telemetry._logs, "set_logger_provider", lambda provider: set_provider_calls.append(provider))
    monkeypatch.setattr(telemetry.atexit, "register", lambda callback: atexit_calls.append(callback))
    monkeypatch.setattr(telemetry, "_resource_for", lambda service_name: {"service.name": service_name})

    telemetry.configure_logging("yt-learner-worker")
    telemetry.configure_logging("yt-learner-worker")

    assert basic_config_calls == [{"level": logging.INFO}, {"level": logging.INFO}]
    assert len(root_logger.handlers) == 1
    assert getattr(root_logger.handlers[0], telemetry._OTEL_HANDLER_ATTR) is True
    assert root_logger.level == logging.INFO
    assert len(providers) == 1
    assert providers[0].resource == {"service.name": "yt-learner-worker"}
    assert len(providers[0].processors) == 1
    assert providers[0].processors[0].exporter == "exporter"
    assert set_provider_calls == [providers[0]]
    assert atexit_calls == [providers[0].shutdown]
