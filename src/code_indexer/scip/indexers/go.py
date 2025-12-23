"""Go SCIP indexer using scip-go."""

import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional

from .base import SCIPIndexer, IndexerResult, IndexerStatus


class GoIndexer(SCIPIndexer):
    """SCIP indexer for Go projects."""

    def generate(
        self, project_dir: Path, output_dir: Path, build_system: str
    ) -> IndexerResult:
        """Generate SCIP index for Go project."""
        start_time = time.time()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Validate go.mod exists
            go_mod = project_dir / "go.mod"
            if not go_mod.exists():
                duration = time.time() - start_time
                return IndexerResult(
                    status=IndexerStatus.FAILED,
                    duration_seconds=duration,
                    output_file=None,
                    stdout="",
                    stderr="No go.mod file found in project directory",
                    exit_code=-1,
                )

            # Run scip-go indexer
            cmd = ["scip-go"]

            result = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minutes timeout
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                # Find generated .scip file
                scip_file = project_dir / "index.scip"
                if scip_file.exists():
                    # Move to output directory
                    target_file_path = output_dir / "index.scip"
                    shutil.move(str(scip_file), str(target_file_path))
                    return IndexerResult(
                        status=IndexerStatus.SUCCESS,
                        duration_seconds=duration,
                        output_file=target_file_path,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        exit_code=result.returncode,
                    )

            return IndexerResult(
                status=IndexerStatus.FAILED,
                duration_seconds=duration,
                output_file=None,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )

        except Exception as e:
            duration = time.time() - start_time
            return IndexerResult(
                status=IndexerStatus.FAILED,
                duration_seconds=duration,
                output_file=None,
                stdout="",
                stderr=str(e),
                exit_code=-1,
            )

    def is_available(self) -> bool:
        """Check if scip-go is available."""
        return shutil.which("scip-go") is not None

    def get_version(self) -> Optional[str]:
        """Get scip-go version."""
        try:
            result = subprocess.run(
                ["scip-go", "--version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
