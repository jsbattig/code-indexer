"""C# SCIP indexer using scip-dotnet."""

import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional

from .base import SCIPIndexer, IndexerResult, IndexerStatus


class CSharpIndexer(SCIPIndexer):
    """SCIP indexer for C# projects."""

    def generate(
        self, project_dir: Path, output_dir: Path, build_system: str
    ) -> IndexerResult:
        """Generate SCIP index for C# project."""
        start_time = time.time()
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Determine target file based on build system
            if build_system == "solution":
                # Find .sln file
                sln_files = list(project_dir.glob("*.sln"))
                if not sln_files:
                    duration = time.time() - start_time
                    return IndexerResult(
                        status=IndexerStatus.FAILED,
                        duration_seconds=duration,
                        output_file=None,
                        stdout="",
                        stderr="No .sln file found in project directory",
                        exit_code=-1,
                    )
                target_file = str(sln_files[0].name)
            else:
                # For project build system, use current directory
                target_file = "."

            # Run scip-dotnet indexer
            cmd = ["scip-dotnet", "index", target_file]

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
        """Check if scip-dotnet is available."""
        return shutil.which("scip-dotnet") is not None

    def get_version(self) -> Optional[str]:
        """Get scip-dotnet version."""
        try:
            result = subprocess.run(
                ["scip-dotnet", "--version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
