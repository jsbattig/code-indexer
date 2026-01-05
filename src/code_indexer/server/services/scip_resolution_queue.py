from code_indexer.server.middleware.correlation import get_correlation_id
"""
SCIP Resolution Queue.

Manages serialized FIFO queue for processing SCIP project resolution attempts
one at a time to prevent conflicts. Part of Story #645 AC4.
"""

import logging
import asyncio
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

# Queue worker poll timeout (seconds)
WORKER_POLL_TIMEOUT = 1.0

# Base directory for SCIP resolution workspaces
SCIP_WORKSPACE_BASE = "/tmp/cidx-scip"


@dataclass
class QueuedProject:
    """Represents a queued SCIP project for resolution."""

    job_id: str
    project_path: str
    language: str
    build_system: str
    stderr: str


class SCIPResolutionQueue:
    """
    Serialized FIFO queue for SCIP project resolution.

    Ensures only one Claude Code invocation runs at any time,
    preventing conflicts and resource contention.
    """

    def __init__(self, self_healing_service):
        """
        Initialize SCIP Resolution Queue.

        Args:
            self_healing_service: SCIPSelfHealingService instance for
                invoking Claude Code and handling responses
        """
        self.queue: asyncio.Queue[QueuedProject] = asyncio.Queue()
        self.self_healing_service = self_healing_service
        self.worker_task: Optional[asyncio.Task] = None
        self.current_project: Optional[QueuedProject] = None
        self.is_running: bool = False
        self._lock = asyncio.Lock()

    async def enqueue_project(
        self,
        job_id: str,
        project_path: str,
        language: str,
        build_system: str,
        stderr: str,
    ) -> None:
        """
        Add a failed SCIP project to the resolution queue.

        Args:
            job_id: Background job ID
            project_path: Project relative path (e.g., "backend/")
            language: Project language (e.g., "python")
            build_system: Build system (e.g., "poetry")
            stderr: SCIP indexer error output for this project
        """
        project = QueuedProject(
            job_id=job_id,
            project_path=project_path,
            language=language,
            build_system=build_system,
            stderr=stderr,
        )

        await self.queue.put(project)

        logger.info(
            f"Enqueued {language} project at {project_path} for job {job_id} "
            f"(queue size: {self.queue.qsize()})",
            extra={"correlation_id": get_correlation_id()},
        )

    async def process_next_project(self) -> None:
        """
        Process the next project in the queue (FIFO).

        Gets project from queue, sets as current_project, invokes Claude Code,
        and handles the response.
        """
        project: Optional[QueuedProject] = None
        item_retrieved = False

        try:
            # Get next project from queue (FIFO order)
            project = await self.queue.get()
            item_retrieved = True

            async with self._lock:
                self.current_project = project

            logger.info(
                f"Processing {project.language} project at {project.project_path} "
                f"for job {project.job_id}",
                extra={"correlation_id": get_correlation_id()},
            )

            # Create workspace for this project
            workspace_path = Path(f"{SCIP_WORKSPACE_BASE}-{project.job_id}/{project.project_path}")
            workspace_path.mkdir(parents=True, exist_ok=True)

            # Get current attempt count for --resume flag
            # (stub - will be integrated with job manager in AC5)
            attempt = 1

            # Invoke Claude Code for this specific project
            response = await self.self_healing_service.invoke_claude_code(
                job_id=project.job_id,
                project_path=project.project_path,
                language=project.language,
                build_system=project.build_system,
                stderr=project.stderr,
                workspace=workspace_path,
                attempt=attempt,
            )

            # Handle the response (update job status, retry SCIP if needed, etc.)
            await self.self_healing_service.handle_project_response(
                job_id=project.job_id,
                project_path=project.project_path,
                response=response,
            )

            logger.info(
                f"Completed processing {project.project_path} for job {project.job_id}, "
                f"status: {response.status}",
                extra={"correlation_id": get_correlation_id()},
            )

        except asyncio.CancelledError:
            # Worker is being stopped, re-queue current project if retrieved
            if item_retrieved and project:
                logger.warning(
                    f"Worker cancelled while processing {project.project_path}, "
                    "re-queuing project",
                    extra={"correlation_id": get_correlation_id()},
                )
                await self.queue.put(project)
            raise
        except Exception as e:
            # Log error with project info if available
            if project:
                logger.error(
                    f"Error processing project {project.project_path}: {e}",
                    exc_info=True,
                    extra={"correlation_id": get_correlation_id()},
                )
            else:
                logger.error(
                    f"Error before project retrieval: {e}",
                    exc_info=True,
                    extra={"correlation_id": get_correlation_id()},
                )
        finally:
            async with self._lock:
                self.current_project = None
            # Only call task_done if item was successfully retrieved
            if item_retrieved:
                self.queue.task_done()

    def get_status(self) -> Dict[str, Any]:
        """
        Get current queue status.

        Returns:
            Dictionary with:
            - pending_count: Number of projects waiting in queue
            - current_project: Currently processing project (or None)
            - is_running: Whether worker is running
        """
        current = None
        if self.current_project:
            current = asdict(self.current_project)

        return {
            "pending_count": self.queue.qsize(),
            "current_project": current,
            "is_running": self.is_running,
        }

    async def start_worker(self) -> None:
        """
        Start the queue worker task.

        Worker continuously processes projects from queue until stopped.
        Only one worker runs at a time.
        """
        if self.is_running:
            logger.debug("Worker already running, ignoring start request", extra={"correlation_id": get_correlation_id()})
            return

        self.is_running = True
        self.worker_task = asyncio.create_task(self._worker_loop())

        logger.info("SCIP resolution queue worker started", extra={"correlation_id": get_correlation_id()})

    async def stop_worker(self) -> None:
        """
        Stop the queue worker gracefully.

        Cancels worker task and waits for it to complete.
        Currently processing project will be re-queued.
        """
        if not self.is_running:
            logger.debug("Worker not running, ignoring stop request", extra={"correlation_id": get_correlation_id()})
            return

        self.is_running = False

        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None

        logger.info("SCIP resolution queue worker stopped", extra={"correlation_id": get_correlation_id()})

    async def _worker_loop(self) -> None:
        """
        Worker loop that continuously processes projects from queue.

        Runs until is_running becomes False or task is cancelled.
        """
        logger.debug("Worker loop started", extra={"correlation_id": get_correlation_id()})

        try:
            while self.is_running:
                # Wait for next project (blocks if queue empty)
                try:
                    await asyncio.wait_for(
                        self.process_next_project(),
                        timeout=WORKER_POLL_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    # No projects in queue, continue loop
                    if self.queue.empty() and self.is_running:
                        # Stop worker if queue is empty
                        self.is_running = False
                        break
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error in worker loop: {e}", exc_info=True, extra={"correlation_id": get_correlation_id()})
                    # Continue processing other projects

        except asyncio.CancelledError:
            logger.debug("Worker loop cancelled", extra={"correlation_id": get_correlation_id()})
            raise
        finally:
            logger.debug("Worker loop exited", extra={"correlation_id": get_correlation_id()})
