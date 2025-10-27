"""Telemetry helpers for the advanced realtime FastAPI application."""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import Meter, MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import Settings


@dataclass(frozen=True)
class PipelineMetricsRecorder:
    """Records board event publication metrics."""

    counter: Any
    duration: Any

    def record(self, board_id: str, status: str, latency_seconds: float) -> None:
        attributes = {
            "board_id": board_id,
            "status": status,
        }
        self.counter.add(1, attributes)  # type: ignore[no-untyped-call]
        self.duration.record(latency_seconds, attributes)  # type: ignore[no-untyped-call]


@dataclass(frozen=True)
class TelemetryState:
    """Telemetry configuration and instruments bound to an application instance."""

    enabled: bool
    prometheus_reader: PrometheusMetricReader | None
    meter: Meter | None
    tracer_name: str | None
    request_counter: Any | None
    request_duration: Any | None
    rate_limit_counter: Any | None
    pipeline_metrics: PipelineMetricsRecorder | None

    def metrics_response(self) -> Response:
        """Render a Prometheus response with the current metrics snapshot."""

        if not self.enabled or not self.prometheus_reader:
            return Response(content="telemetry disabled", media_type="text/plain", status_code=503)
        collector = getattr(self.prometheus_reader, "_collector", None)
        payload = generate_latest(collector) if collector else b""
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

    @property
    def tracer(self):  # type: ignore[override]
        if not self.enabled or not self.tracer_name:
            return None
        return trace.get_tracer(self.tracer_name)


_runtime_lock = Lock()
_runtime_configured = False
_runtime_prometheus_reader: PrometheusMetricReader | None = None
_runtime_meter: Meter | None = None
_runtime_tracer_provider: TracerProvider | None = None
_runtime_request_counter: Any | None = None
_runtime_request_duration: Any | None = None
_runtime_rate_limit_counter: Any | None = None
_runtime_pipeline_counter: Any | None = None
_runtime_pipeline_duration: Any | None = None


def _ensure_runtime(settings: Settings) -> None:
    global _runtime_configured
    global _runtime_meter
    global _runtime_prometheus_reader
    global _runtime_tracer_provider

    if _runtime_configured:
        return

    resource = Resource.create(
        {
            "service.name": settings.telemetry_service_name,
            "service.namespace": "advanced-board",
            "service.version": settings.version,
        }
    )

    prometheus_reader = PrometheusMetricReader()
    meter_provider = MeterProvider(resource=resource, metric_readers=[prometheus_reader])
    metrics.set_meter_provider(meter_provider)
    _runtime_meter = meter_provider.get_meter(settings.telemetry_service_name)

    tracer_provider = TracerProvider(resource=resource)
    if settings.otel_exporter_otlp_endpoint:
        exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            headers=settings.otel_exporter_otlp_headers,
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(tracer_provider)

    _runtime_prometheus_reader = prometheus_reader
    _runtime_tracer_provider = tracer_provider
    _runtime_configured = True


def configure_telemetry(settings: Settings) -> TelemetryState:
    """Initialise telemetry providers and instruments for the application."""

    if not settings.telemetry_enabled:
        return TelemetryState(
            enabled=False,
            prometheus_reader=None,
            meter=None,
            tracer_name=None,
            request_counter=None,
            request_duration=None,
            rate_limit_counter=None,
            pipeline_metrics=None,
        )

    with _runtime_lock:
        _ensure_runtime(settings)

        global _runtime_request_counter
        global _runtime_request_duration
        global _runtime_rate_limit_counter
        global _runtime_pipeline_counter
        global _runtime_pipeline_duration

        meter = _runtime_meter
        if meter is None:
            raise RuntimeError("Meter provider was not initialised")

        if _runtime_request_counter is None:
            _runtime_request_counter = meter.create_counter(
                name="advanced_http_requests_total",
                description="Total HTTP requests processed by the advanced realtime service.",
            )
        if _runtime_request_duration is None:
            _runtime_request_duration = meter.create_histogram(
                name="advanced_http_request_duration_seconds",
                unit="s",
                description="Latency of HTTP requests handled by the advanced realtime service.",
            )
        if _runtime_rate_limit_counter is None:
            _runtime_rate_limit_counter = meter.create_counter(
                name="advanced_http_rate_limit_rejections_total",
                description="HTTP requests rejected due to configured rate limits.",
            )
        if _runtime_pipeline_counter is None:
            _runtime_pipeline_counter = meter.create_counter(
                name="advanced_board_events_published_total",
                description="Board events published via the event pipeline.",
            )
        if _runtime_pipeline_duration is None:
            _runtime_pipeline_duration = meter.create_histogram(
                name="advanced_board_event_publish_duration_seconds",
                unit="s",
                description="Time taken to publish board events through the pipeline.",
            )

    pipeline_metrics = PipelineMetricsRecorder(
        counter=_runtime_pipeline_counter,
        duration=_runtime_pipeline_duration,
    )

    tracer_name = settings.telemetry_service_name

    return TelemetryState(
        enabled=True,
        prometheus_reader=_runtime_prometheus_reader,
        meter=_runtime_meter,
        tracer_name=tracer_name,
        request_counter=_runtime_request_counter,
        request_duration=_runtime_request_duration,
        rate_limit_counter=_runtime_rate_limit_counter,
        pipeline_metrics=pipeline_metrics,
    )


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware that emits tracing spans and request metrics."""

    def __init__(self, app, telemetry: TelemetryState) -> None:  # type: ignore[override]
        super().__init__(app)
        self._telemetry = telemetry

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not self._telemetry.enabled:
            return await call_next(request)

        tracer = self._telemetry.tracer
        start = time.perf_counter()
        response: Response | None = None

        route = request.scope.get("route")
        route_template = getattr(route, "path", request.url.path) if route else request.url.path
        span_name = f"{request.method} {route_template}"

        span_context = tracer.start_as_current_span(span_name) if tracer else contextlib.nullcontext()

        with span_context as span:  # type: ignore[assignment]
            if span:
                span.set_attribute("http.method", request.method)
                span.set_attribute("http.route", route_template)
                span.set_attribute("http.target", request.url.path)
                span.set_attribute("net.peer.ip", request.client.host if request.client else "")
            try:
                response = await call_next(request)
            except Exception as exc:
                if span:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR))
                    span.set_attribute("http.status_code", 500)
                raise
            else:
                if span and response is not None:
                    span.set_attribute("http.status_code", response.status_code)
                    span.set_status(Status(StatusCode.OK))

        duration = time.perf_counter() - start
        status_code = response.status_code if response is not None else 500
        self._record_metrics(route_template, request.method, status_code, duration)
        return response

    def _record_metrics(self, route: str, method: str, status_code: int, duration: float) -> None:
        if not self._telemetry.request_counter or not self._telemetry.request_duration:
            return
        attributes = {
            "http.route": route,
            "http.method": method,
            "http.status_code": str(status_code),
        }
        self._telemetry.request_counter.add(1, attributes)  # type: ignore[no-untyped-call]
        self._telemetry.request_duration.record(duration, attributes)  # type: ignore[no-untyped-call]


def record_rate_limit_rejection(telemetry: TelemetryState, request: Request) -> None:
    """Increment the rate-limit rejection counter when a request is blocked."""

    if not telemetry.enabled or not telemetry.rate_limit_counter:
        return

    route = request.scope.get("route")
    route_template = getattr(route, "path", request.url.path) if route else request.url.path
    attributes = {
        "http.route": route_template,
        "http.method": request.method,
    }
    telemetry.rate_limit_counter.add(1, attributes)  # type: ignore[no-untyped-call]


__all__ = [
    "ObservabilityMiddleware",
    "PipelineMetricsRecorder",
    "TelemetryState",
    "configure_telemetry",
    "record_rate_limit_rejection",
]
