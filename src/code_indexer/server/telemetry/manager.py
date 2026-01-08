"""
TelemetryManager - Singleton manager for OpenTelemetry SDK lifecycle (Story #695).

This module implements the TelemetryManager class which:
- Manages OTEL SDK initialization and shutdown
- Provides tracer and meter instances for instrumentation
- Supports both gRPC and HTTP protocols for OTLP export
- Handles graceful degradation when telemetry is disabled or collector is unreachable
- Uses lazy loading to ensure zero overhead when disabled

CRITICAL: Lazy loading pattern used throughout to avoid importing OTEL SDK
at module level, ensuring server startup time is unaffected when telemetry is disabled.
"""

from __future__ import annotations

import logging
from threading import Lock
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from opentelemetry.metrics import Meter, MeterProvider
    from opentelemetry.trace import Tracer, TracerProvider

    from src.code_indexer.server.utils.config_manager import TelemetryConfig

logger = logging.getLogger(__name__)

# Singleton instance and lock
_telemetry_manager: Optional["TelemetryManager"] = None
_manager_lock = Lock()


class TelemetryManager:
    """
    Manages OpenTelemetry SDK lifecycle for CIDX Server.

    This class is responsible for:
    - Initializing OTEL TracerProvider and MeterProvider based on config
    - Providing tracer and meter instances for instrumentation
    - Graceful shutdown with telemetry flush
    - No-op behavior when telemetry is disabled

    Thread-safe singleton pattern is implemented via get_telemetry_manager().
    """

    def __init__(self, config: "TelemetryConfig") -> None:
        """
        Initialize TelemetryManager with configuration.

        Args:
            config: TelemetryConfig instance with telemetry settings

        Note:
            OTEL SDK is only loaded if config.enabled is True.
            This ensures zero overhead when telemetry is disabled.
        """
        self._config = config
        self._tracer_provider: Optional["TracerProvider"] = None
        self._meter_provider: Optional["MeterProvider"] = None
        self._is_initialized = False

        if config.enabled:
            self._initialize_otel()

    def _initialize_otel(self) -> None:
        """
        Initialize OpenTelemetry SDK components.

        Lazy imports OTEL libraries to avoid loading them when disabled.
        Sets up TracerProvider and MeterProvider with OTLP exporters.
        """
        try:
            # Lazy import OTEL SDK components
            from opentelemetry import metrics, trace
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.semconv.resource import ResourceAttributes

            # Create resource with service information
            resource = Resource.create(
                {
                    ResourceAttributes.SERVICE_NAME: self._config.service_name,
                    ResourceAttributes.DEPLOYMENT_ENVIRONMENT: self._config.deployment_environment,
                }
            )

            # Initialize TracerProvider if traces are enabled
            if self._config.export_traces:
                self._tracer_provider = TracerProvider(resource=resource)
                self._setup_trace_exporter()
                trace.set_tracer_provider(self._tracer_provider)
            else:
                # Use no-op tracer provider
                self._tracer_provider = TracerProvider(resource=resource)
                trace.set_tracer_provider(self._tracer_provider)

            # Initialize MeterProvider if metrics are enabled
            if self._config.export_metrics:
                self._meter_provider = self._create_meter_provider(resource)
                metrics.set_meter_provider(self._meter_provider)
            else:
                # Use no-op meter provider
                self._meter_provider = MeterProvider(resource=resource)
                metrics.set_meter_provider(self._meter_provider)

            self._is_initialized = True
            logger.info(
                f"OpenTelemetry initialized: service={self._config.service_name}, "
                f"endpoint={self._config.collector_endpoint}, "
                f"protocol={self._config.collector_protocol}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize OpenTelemetry: {e}")
            # Set initialized to True anyway - we tried, and we don't want to fail startup
            self._is_initialized = True

    def _setup_trace_exporter(self) -> None:
        """Configure trace exporter based on protocol."""
        if self._tracer_provider is None:
            return

        try:
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            if self._config.collector_protocol.lower() == "grpc":
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                exporter = OTLPSpanExporter(
                    endpoint=self._config.collector_endpoint,
                    insecure=True,
                )
            else:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )

                # HTTP endpoint typically includes /v1/traces path
                endpoint = self._config.collector_endpoint
                if not endpoint.endswith("/v1/traces"):
                    endpoint = f"{endpoint.rstrip('/')}/v1/traces"
                exporter = OTLPSpanExporter(endpoint=endpoint)

            self._tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

        except Exception as e:
            logger.warning(f"Failed to setup trace exporter: {e}")

    def _create_meter_provider(self, resource) -> "MeterProvider":
        """Create MeterProvider with OTLP exporter."""
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        try:
            if self._config.collector_protocol.lower() == "grpc":
                from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                    OTLPMetricExporter,
                )

                exporter = OTLPMetricExporter(
                    endpoint=self._config.collector_endpoint,
                    insecure=True,
                )
            else:
                from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                    OTLPMetricExporter,
                )

                endpoint = self._config.collector_endpoint
                if not endpoint.endswith("/v1/metrics"):
                    endpoint = f"{endpoint.rstrip('/')}/v1/metrics"
                exporter = OTLPMetricExporter(endpoint=endpoint)

            reader = PeriodicExportingMetricReader(
                exporter,
                export_interval_millis=self._config.machine_metrics_interval_seconds
                * 1000,
            )
            return MeterProvider(resource=resource, metric_readers=[reader])

        except Exception as e:
            logger.warning(f"Failed to setup metric exporter: {e}")
            return MeterProvider(resource=resource)

    @property
    def is_initialized(self) -> bool:
        """Return whether OTEL SDK is initialized."""
        return self._is_initialized

    @property
    def tracer_provider(self) -> Optional["TracerProvider"]:
        """Return the TracerProvider instance, or None if not initialized."""
        return self._tracer_provider

    @property
    def meter_provider(self) -> Optional["MeterProvider"]:
        """Return the MeterProvider instance, or None if not initialized."""
        return self._meter_provider

    @property
    def service_name(self) -> str:
        """Return the configured service name."""
        return self._config.service_name

    @property
    def deployment_environment(self) -> str:
        """Return the configured deployment environment."""
        return self._config.deployment_environment

    @property
    def collector_protocol(self) -> str:
        """Return the configured collector protocol."""
        return self._config.collector_protocol

    def get_tracer(self, name: str, version: Optional[str] = None) -> "Tracer":
        """
        Get a tracer instance for instrumentation.

        Args:
            name: Name of the tracer (typically component/module name)
            version: Optional version string

        Returns:
            Tracer instance (real or no-op depending on config)
        """
        from opentelemetry import trace

        return trace.get_tracer(name, version)

    def get_meter(self, name: str, version: Optional[str] = None) -> "Meter":
        """
        Get a meter instance for metrics.

        Args:
            name: Name of the meter (typically component/module name)
            version: Optional version string

        Returns:
            Meter instance (real or no-op depending on config)
        """
        from opentelemetry import metrics

        return metrics.get_meter(name, version)

    def shutdown(self) -> None:
        """Shutdown telemetry, flushing any pending data."""
        if not self._is_initialized:
            return

        try:
            if self._tracer_provider is not None:
                self._tracer_provider.shutdown()
                logger.debug("TracerProvider shutdown complete")

            if self._meter_provider is not None:
                self._meter_provider.shutdown()
                logger.debug("MeterProvider shutdown complete")

            logger.info("OpenTelemetry shutdown complete")

        except Exception as e:
            logger.warning(f"Error during OpenTelemetry shutdown: {e}")

        finally:
            self._is_initialized = False


def get_telemetry_manager(
    config: Optional["TelemetryConfig"] = None,
) -> TelemetryManager:
    """
    Get the TelemetryManager singleton instance.

    Args:
        config: TelemetryConfig to use for initialization.
                Required on first call, optional on subsequent calls.
                If None on first call, creates a disabled TelemetryConfig as fallback.

    Returns:
        TelemetryManager singleton instance

    Thread-safe implementation using double-checked locking.
    """
    global _telemetry_manager

    if _telemetry_manager is not None:
        return _telemetry_manager

    with _manager_lock:
        # Double-check after acquiring lock
        if _telemetry_manager is not None:
            return _telemetry_manager

        if config is None:
            # Create disabled config as fallback
            from src.code_indexer.server.utils.config_manager import TelemetryConfig

            config = TelemetryConfig(enabled=False)

        _telemetry_manager = TelemetryManager(config)
        return _telemetry_manager


def reset_telemetry_manager() -> None:
    """
    Reset the TelemetryManager singleton.

    This is primarily for testing purposes. It shuts down the current
    manager (if any) and clears the singleton reference.
    """
    global _telemetry_manager

    with _manager_lock:
        if _telemetry_manager is not None:
            _telemetry_manager.shutdown()
            _telemetry_manager = None
