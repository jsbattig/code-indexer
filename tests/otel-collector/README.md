# OTEL Testing Infrastructure

Local OpenTelemetry testing stack for CIDX Server telemetry development and E2E testing.

## Components

- **OTEL Collector**: Receives OTLP telemetry (traces, metrics, logs) from CIDX Server
- **Jaeger**: Trace visualization and analysis (UI at http://localhost:16686)
- **Prometheus**: Metrics storage and querying (UI at http://localhost:9090)

## Quick Start

```bash
# Start the stack
docker-compose up -d

# Verify services are healthy
docker-compose ps

# View logs
docker-compose logs -f

# Stop the stack
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

## Endpoints

| Service | Port | Description |
|---------|------|-------------|
| OTLP gRPC | 4317 | CIDX sends telemetry here (default) |
| OTLP HTTP | 4318 | Alternative HTTP endpoint |
| Jaeger UI | 16686 | View traces at http://localhost:16686 |
| Prometheus | 9090 | View metrics at http://localhost:9090 |
| Collector Metrics | 8888 | OTEL Collector self-metrics |
| Prometheus Exporter | 8889 | Exported metrics for Prometheus |

## CIDX Server Configuration

To send telemetry to this local stack, configure CIDX with:

```json
{
  "telemetry_config": {
    "enabled": true,
    "collector_endpoint": "http://localhost:4317",
    "collector_protocol": "grpc",
    "service_name": "cidx-server",
    "export_traces": true,
    "export_metrics": true
  }
}
```

Or via environment variables:

```bash
export CIDX_TELEMETRY_ENABLED=true
export CIDX_OTEL_COLLECTOR_ENDPOINT=http://localhost:4317
```

## Verifying Telemetry

### Traces (Jaeger)

1. Open http://localhost:16686
2. Select "cidx-server" from the Service dropdown
3. Click "Find Traces" to see recent traces

### Metrics (Prometheus)

1. Open http://localhost:9090
2. Query for `cidx_*` metrics
3. Example: `cidx_http_requests_total`

### API Verification

```bash
# Check if Jaeger has received traces from cidx-server
curl -s http://localhost:16686/api/services | jq '.data | contains(["cidx-server"])'

# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[].health'
```

## E2E Test Usage

The E2E tests automatically:
1. Start this stack before tests
2. Configure CIDX to send telemetry
3. Execute operations
4. Verify traces appear in Jaeger
5. Verify metrics appear in Prometheus
6. Stop the stack after tests

## Troubleshooting

### No traces appearing in Jaeger

1. Check collector logs: `docker-compose logs otel-collector`
2. Verify CIDX is configured with telemetry enabled
3. Ensure collector_endpoint points to http://localhost:4317

### Connection refused

1. Verify containers are running: `docker-compose ps`
2. Check for port conflicts: `netstat -tlnp | grep -E '4317|4318|16686|9090'`
3. Restart the stack: `docker-compose restart`

### Debug mode

The collector is configured with debug export enabled. Check collector logs
for detailed telemetry data: `docker-compose logs -f otel-collector`
