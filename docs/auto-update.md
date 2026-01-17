# CIDX Server Auto-Update Documentation

Story #734: Job-Aware Auto-Update with Graceful Drain Mode

## Overview

The CIDX Server includes an auto-update feature that automatically deploys updates when changes are detected in the master branch of the configured git repository. This feature includes job-aware graceful drain mode to prevent orphan jobs and data corruption during restarts.

## Architecture

### Component Overview

```
                    +------------------+
                    |  AutoUpdateService |
                    |    (Polling Loop)  |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
    +---------v----+  +------v------+  +---v-----------+
    |ChangeDetector|  |DeploymentLock|  |DeploymentExecutor|
    +--------------+  +-------------+  +-------+-------+
                                               |
                           +-------------------+-------------------+
                           |                   |                   |
                    +------v------+     +------v------+     +------v------+
                    | git pull    |     | pip install |     | Maintenance |
                    |             |     |             |     | Mode Flow   |
                    +-------------+     +-------------+     +------+------+
                                                                   |
                                              +--------------------+--------------------+
                                              |                    |                    |
                                       +------v------+      +------v------+      +------v------+
                                       |Enter Maint. |      |Wait for     |      |systemctl    |
                                       |Mode (API)   |      |Drain        |      |restart      |
                                       +-------------+      +-------------+      +-------------+
```

### State Machine

The AutoUpdateService uses a state machine to manage deployment:

1. **IDLE** - Waiting for next check interval
2. **CHECKING** - Polling git remote for changes
3. **DEPLOYING** - Running git pull and pip install
4. **RESTARTING** - Executing graceful restart with drain

## Job-Aware Drain Process

### Problem Solved

Previous versions performed blind `systemctl restart` without checking for running jobs, causing:
- Orphan jobs left in "running" state indefinitely
- Potential data corruption from interrupted indexing operations
- Poor user experience when long-running jobs are killed

### Solution: Graceful Drain Mode

The auto-update process now uses a three-step maintenance mode flow:

1. **Enter Maintenance Mode** - Server stops accepting new jobs
2. **Wait for Drain** - Poll until all running jobs complete (with timeout)
3. **Execute Restart** - Restart the server after jobs complete

### Drain Flow Diagram

```
Auto-Update Triggered
        |
        v
+-------------------+
| Enter Maintenance |---(POST /api/admin/maintenance/enter)
| Mode              |
+---------+---------+
          |
          v
+-------------------+
| Wait for Drain    |---(GET /api/admin/maintenance/drain-status)
| (poll every 10s)  |
+---------+---------+
          |
    +-----+-----+
    |           |
    v           v
 Drained    Timeout (300s)
    |           |
    |           +---> Log WARNING with job details
    |           |
    +-----+-----+
          |
          v
+-------------------+
| systemctl restart |
| cidx-server       |
+-------------------+
```

## Configuration

### DeploymentExecutor Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `server_url` | `http://localhost:8000` | CIDX server URL for maintenance API |
| `drain_timeout` | `300` (5 min) | Maximum seconds to wait for drain |
| `drain_poll_interval` | `10` | Seconds between drain status checks |

### Environment Variables (systemd)

Configure in `/etc/systemd/system/cidx-auto-update.service`:

```ini
[Unit]
Description=CIDX Auto-Update Service
After=network.target cidx-server.service

[Service]
Type=simple
User=cidx
WorkingDirectory=/opt/cidx
ExecStart=/usr/bin/python3 -m code_indexer.server.auto_update.cli
Restart=always
RestartSec=30
Environment=CIDX_REPO_PATH=/opt/cidx
Environment=CIDX_CHECK_INTERVAL=300

[Install]
WantedBy=multi-user.target
```

## API Endpoints

### Maintenance Mode Endpoints

All endpoints are under `/api/admin/maintenance/`.

**Authentication Required**: All maintenance endpoints require admin authentication. Include a valid Bearer token in the Authorization header:

```bash
curl -X POST http://localhost:8000/api/admin/maintenance/enter \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

Without valid admin authentication, all endpoints return HTTP 401 Unauthorized.

#### POST /enter

Enter maintenance mode. Stops accepting new jobs while allowing running jobs to complete.

**Response (200 OK)**:
```json
{
  "maintenance_mode": true,
  "running_jobs": 3,
  "queued_jobs": 5,
  "entered_at": "2025-01-17T10:00:00Z",
  "message": "Maintenance mode active. 3 running, 5 queued."
}
```

#### POST /exit

Exit maintenance mode. Resumes accepting new jobs.

**Response (200 OK)**:
```json
{
  "maintenance_mode": false,
  "message": "Maintenance mode deactivated."
}
```

#### GET /status

Get current maintenance mode status.

**Response (200 OK)**:
```json
{
  "maintenance_mode": true,
  "drained": false,
  "running_jobs": 2,
  "queued_jobs": 0,
  "entered_at": "2025-01-17T10:00:00Z"
}
```

#### GET /drain-status

Get detailed drain status for auto-update coordination.

**Response (200 OK)**:
```json
{
  "drained": false,
  "running_jobs": 2,
  "queued_jobs": 0,
  "estimated_drain_seconds": 120,
  "jobs": [
    {
      "job_id": "abc-123",
      "operation_type": "add_golden_repo",
      "started_at": "2025-01-17T10:00:00Z",
      "progress": 50
    }
  ]
}
```

## Health Endpoint Integration

The `/health` endpoint includes maintenance mode status:

```json
{
  "status": "healthy",
  "maintenance_mode": true,
  "uptime": 3600,
  ...
}
```

During maintenance mode, the health status is **degraded** (not unhealthy) to indicate:
- Server is operational for queries
- New jobs are rejected (returns 503)
- System is draining for planned restart

## Job Rejection During Maintenance

When the server is in maintenance mode, job submission endpoints return HTTP 503:

```json
{
  "error": "Server is in maintenance mode. New jobs are not accepted. Please retry after 60 seconds."
}
```

Affected operations:
- Repository add/sync via `GoldenRepoManager`
- Background jobs via `BackgroundJobManager`
- Sync jobs via `SyncJobManager`

Query operations continue to work normally.

## Force Restart Logging

When drain timeout is exceeded, the system logs all running jobs at WARNING level before forcing restart:

```
WARNING: Forcing restart - running job: job_id=abc-123, operation_type=add_golden_repo, started_at=2025-01-17T10:00:00Z, progress=50%
WARNING: Drain timeout exceeded, forcing restart
```

This provides visibility into which jobs were interrupted for post-restart recovery.

## Startup Behavior

On server startup, the maintenance state is automatically cleared:

1. Maintenance mode is NOT persisted to disk (in-memory only)
2. Server starts in normal operation mode
3. Log message confirms: "Server started in normal operation mode"

This ensures the server recovers cleanly from crashes or forced restarts.

## Troubleshooting

### Jobs stuck in maintenance mode

If the server is stuck in maintenance mode:

1. Check current status: `curl http://localhost:8000/api/admin/maintenance/status`
2. Manually exit: `curl -X POST http://localhost:8000/api/admin/maintenance/exit`
3. Or restart the server (maintenance state is cleared on restart)

### Auto-update not working

1. Check auto-update service status: `systemctl status cidx-auto-update`
2. Check logs: `journalctl -u cidx-auto-update -f`
3. Verify git remote access: `cd /opt/cidx && git fetch origin master`

### Jobs orphaned after restart

If jobs were interrupted during a forced restart:

1. Jobs are automatically marked as CANCELLED on next server startup
2. Check job status via API: `GET /api/jobs/{job_id}/status`
3. Re-submit failed jobs as needed

## Best Practices

1. **Set appropriate drain timeout** - Consider your longest-running jobs when configuring `drain_timeout`
2. **Monitor during updates** - Watch logs during auto-update for any forced restarts
3. **Schedule updates during low usage** - If possible, configure check intervals to align with low-traffic periods
4. **Test recovery procedures** - Periodically verify job recovery after interruptions
