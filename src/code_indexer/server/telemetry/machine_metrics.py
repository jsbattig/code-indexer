"""
MachineMetricsExporter - OTEL observable gauges for machine metrics (Story #696).

This module exports system metrics (CPU, memory, disk, network) to OTEL
using observable gauges that call back to SystemMetricsCollector.

The exporter registers the following metrics:
- system.cpu.usage: CPU usage percentage (0-100)
- system.memory.usage: Memory usage percentage (0-100)
- system.disk.free: Free disk space in bytes
- system.disk.io.read: Disk read bytes (cumulative counter)
- system.disk.io.write: Disk write bytes (cumulative counter)
- system.network.io.receive: Network receive bytes (cumulative counter)
- system.network.io.transmit: Network transmit bytes (cumulative counter)

Each metric includes host.name and service.name attributes.
"""

from __future__ import annotations

import logging
import socket
from typing import TYPE_CHECKING, Dict, Iterable, Optional, Tuple, Any

if TYPE_CHECKING:
    from code_indexer.server.telemetry.manager import TelemetryManager

logger = logging.getLogger(__name__)

# Singleton instance
_machine_metrics_exporter: Optional["MachineMetricsExporter"] = None


class MachineMetricsExporter:
    """
    Exports machine metrics to OTEL via observable gauges.

    Uses SystemMetricsCollector for metric values and registers
    observable gauges with TelemetryManager's meter.
    """

    def __init__(
        self,
        telemetry_manager: "TelemetryManager",
        machine_metrics_enabled: bool = True,
    ) -> None:
        """
        Initialize MachineMetricsExporter.

        Args:
            telemetry_manager: TelemetryManager instance for getting meter
            machine_metrics_enabled: Whether to actually register gauges
        """
        self._telemetry_manager = telemetry_manager
        self._machine_metrics_enabled = machine_metrics_enabled
        self._is_active = False
        self._registered_gauges: Dict[str, Any] = {}

        # Host identification
        self._host_name: str = socket.gethostname()
        self._service_name: str = telemetry_manager.service_name

        if machine_metrics_enabled and telemetry_manager.is_initialized:
            self._register_gauges()

    def _register_gauges(self) -> None:
        """Register all observable gauges with the meter."""
        try:
            meter = self._telemetry_manager.get_meter("cidx.machine_metrics")

            # CPU usage gauge
            self._registered_gauges["system.cpu.usage"] = meter.create_observable_gauge(
                name="system.cpu.usage",
                callbacks=[self._cpu_callback],
                description="CPU usage percentage",
                unit="%",
            )

            # Memory usage gauge
            self._registered_gauges["system.memory.usage"] = (
                meter.create_observable_gauge(
                    name="system.memory.usage",
                    callbacks=[self._memory_callback],
                    description="Memory usage percentage",
                    unit="%",
                )
            )

            # Disk free space gauge
            self._registered_gauges["system.disk.free"] = meter.create_observable_gauge(
                name="system.disk.free",
                callbacks=[self._disk_free_callback],
                description="Free disk space",
                unit="By",
            )

            # Disk I/O counters
            self._registered_gauges["system.disk.io.read"] = (
                meter.create_observable_gauge(
                    name="system.disk.io.read",
                    callbacks=[self._disk_read_callback],
                    description="Disk read bytes (cumulative)",
                    unit="By",
                )
            )

            self._registered_gauges["system.disk.io.write"] = (
                meter.create_observable_gauge(
                    name="system.disk.io.write",
                    callbacks=[self._disk_write_callback],
                    description="Disk write bytes (cumulative)",
                    unit="By",
                )
            )

            # Network I/O counters
            self._registered_gauges["system.network.io.receive"] = (
                meter.create_observable_gauge(
                    name="system.network.io.receive",
                    callbacks=[self._network_receive_callback],
                    description="Network receive bytes (cumulative)",
                    unit="By",
                )
            )

            self._registered_gauges["system.network.io.transmit"] = (
                meter.create_observable_gauge(
                    name="system.network.io.transmit",
                    callbacks=[self._network_transmit_callback],
                    description="Network transmit bytes (cumulative)",
                    unit="By",
                )
            )

            self._is_active = True
            logger.info(
                f"MachineMetricsExporter initialized: {len(self._registered_gauges)} gauges registered"
            )

        except Exception as e:
            logger.warning(f"Failed to register machine metrics gauges: {e}")
            self._is_active = False

    def _get_attributes(self) -> Dict[str, str]:
        """Get common attributes for all metrics."""
        return {
            "host.name": self._host_name,
            "service.name": self._service_name,
        }

    def _get_metrics_collector(self):
        """Get SystemMetricsCollector lazily to avoid circular imports."""
        from src.code_indexer.server.services.system_metrics_collector import (
            get_system_metrics_collector,
        )

        return get_system_metrics_collector()

    # Callback methods for observable gauges
    # Each callback yields (value, attributes) tuples

    def _cpu_callback(self, options) -> Iterable[Tuple[float, Dict[str, str]]]:
        """Callback for CPU usage gauge."""
        try:
            collector = self._get_metrics_collector()
            value = collector.get_cpu_usage()
            yield (value, self._get_attributes())
        except Exception as e:
            logger.warning(f"Failed to collect CPU metrics: {e}")

    def _memory_callback(self, options) -> Iterable[Tuple[float, Dict[str, str]]]:
        """Callback for memory usage gauge."""
        try:
            collector = self._get_metrics_collector()
            memory = collector.get_memory_usage()
            yield (memory["percent"], self._get_attributes())
        except Exception as e:
            logger.warning(f"Failed to collect memory metrics: {e}")

    def _disk_free_callback(self, options) -> Iterable[Tuple[int, Dict[str, str]]]:
        """Callback for disk free space gauge."""
        try:
            collector = self._get_metrics_collector()
            disk = collector.get_disk_metrics()
            yield (disk["free_bytes"], self._get_attributes())
        except Exception as e:
            logger.warning(f"Failed to collect disk free metrics: {e}")

    def _disk_read_callback(self, options) -> Iterable[Tuple[int, Dict[str, str]]]:
        """Callback for disk read bytes gauge."""
        try:
            collector = self._get_metrics_collector()
            disk = collector.get_disk_metrics()
            yield (disk["read_bytes"], self._get_attributes())
        except Exception as e:
            logger.warning(f"Failed to collect disk read metrics: {e}")

    def _disk_write_callback(self, options) -> Iterable[Tuple[int, Dict[str, str]]]:
        """Callback for disk write bytes gauge."""
        try:
            collector = self._get_metrics_collector()
            disk = collector.get_disk_metrics()
            yield (disk["write_bytes"], self._get_attributes())
        except Exception as e:
            logger.warning(f"Failed to collect disk write metrics: {e}")

    def _network_receive_callback(
        self, options
    ) -> Iterable[Tuple[int, Dict[str, str]]]:
        """Callback for network receive bytes gauge."""
        try:
            collector = self._get_metrics_collector()
            network = collector.get_network_metrics()
            yield (network["receive_bytes"], self._get_attributes())
        except Exception as e:
            logger.warning(f"Failed to collect network receive metrics: {e}")

    def _network_transmit_callback(
        self, options
    ) -> Iterable[Tuple[int, Dict[str, str]]]:
        """Callback for network transmit bytes gauge."""
        try:
            collector = self._get_metrics_collector()
            network = collector.get_network_metrics()
            yield (network["transmit_bytes"], self._get_attributes())
        except Exception as e:
            logger.warning(f"Failed to collect network transmit metrics: {e}")

    @property
    def is_active(self) -> bool:
        """Return whether the exporter is actively exporting metrics."""
        return self._is_active

    @property
    def registered_gauges(self) -> Dict[str, Any]:
        """Return dict of registered gauge names."""
        return self._registered_gauges

    @property
    def host_name(self) -> str:
        """Return the hostname used in metric attributes."""
        return self._host_name

    @property
    def service_name(self) -> str:
        """Return the service name used in metric attributes."""
        return self._service_name


def get_machine_metrics_exporter(
    telemetry_manager: "TelemetryManager",
    machine_metrics_enabled: bool = True,
) -> MachineMetricsExporter:
    """
    Get or create the MachineMetricsExporter singleton.

    Args:
        telemetry_manager: TelemetryManager instance
        machine_metrics_enabled: Whether machine metrics are enabled

    Returns:
        MachineMetricsExporter instance
    """
    global _machine_metrics_exporter

    if _machine_metrics_exporter is None:
        _machine_metrics_exporter = MachineMetricsExporter(
            telemetry_manager, machine_metrics_enabled
        )

    return _machine_metrics_exporter


def reset_machine_metrics_exporter() -> None:
    """Reset the MachineMetricsExporter singleton (for testing)."""
    global _machine_metrics_exporter
    _machine_metrics_exporter = None
