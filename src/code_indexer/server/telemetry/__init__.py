"""
OpenTelemetry integration for CIDX Server (Story #695, #696).

This module provides telemetry functionality including tracing, metrics,
and logging export to an OpenTelemetry collector. It is designed with
lazy loading to ensure zero overhead when telemetry is disabled.

Usage:
    from code_indexer.server.telemetry import get_telemetry_manager

    # Initialize with config (typically done once at server startup)
    manager = get_telemetry_manager(telemetry_config)

    # Get tracers and meters for instrumentation
    tracer = manager.get_tracer("my-component")
    meter = manager.get_meter("my-component")

    # Shutdown when server stops
    manager.shutdown()
"""

from code_indexer.server.telemetry.manager import (
    TelemetryManager,
    get_telemetry_manager,
    reset_telemetry_manager,
)
from code_indexer.server.telemetry.machine_metrics import (
    MachineMetricsExporter,
    get_machine_metrics_exporter,
    reset_machine_metrics_exporter,
)
from code_indexer.server.telemetry.instrumentation import (
    instrument_fastapi,
    uninstrument_fastapi,
    DEFAULT_EXCLUDED_URLS,
    reset_instrumentation_state,
)
from code_indexer.server.telemetry.correlation_bridge import (
    CorrelationBridgeMiddleware,
    get_current_correlation_id,
    set_current_correlation_id,
    CORRELATION_ID_HEADER,
    CORRELATION_ID_ATTRIBUTE,
)
from code_indexer.server.telemetry.metrics_instrumentation import (
    ApplicationMetrics,
    get_application_metrics,
    reset_application_metrics,
)
from code_indexer.server.telemetry.job_metrics import (
    JobMetrics,
    get_job_metrics,
    reset_job_metrics,
)
from code_indexer.server.telemetry.spans import (
    traced,
    create_span,
    get_tracer,
    add_span_attribute,
    add_span_event,
    reset_spans_state,
)
from code_indexer.server.telemetry.log_handler import (
    OTELLogHandler,
    OTELLogFormatter,
    get_trace_context,
)

__all__ = [
    # Manager
    "TelemetryManager",
    "get_telemetry_manager",
    "reset_telemetry_manager",
    # Machine metrics
    "MachineMetricsExporter",
    "get_machine_metrics_exporter",
    "reset_machine_metrics_exporter",
    # Instrumentation
    "instrument_fastapi",
    "uninstrument_fastapi",
    "DEFAULT_EXCLUDED_URLS",
    "reset_instrumentation_state",
    # Correlation bridge
    "CorrelationBridgeMiddleware",
    "get_current_correlation_id",
    "set_current_correlation_id",
    "CORRELATION_ID_HEADER",
    "CORRELATION_ID_ATTRIBUTE",
    # Application metrics
    "ApplicationMetrics",
    "get_application_metrics",
    "reset_application_metrics",
    # Job metrics
    "JobMetrics",
    "get_job_metrics",
    "reset_job_metrics",
    # Custom spans
    "traced",
    "create_span",
    "get_tracer",
    "add_span_attribute",
    "add_span_event",
    "reset_spans_state",
    # Log handler
    "OTELLogHandler",
    "OTELLogFormatter",
    "get_trace_context",
]
