"""Java SCIP indexer using scip-java."""

import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional

from .base import SCIPIndexer, IndexerResult, IndexerStatus


class JavaIndexer(SCIPIndexer):
    """SCIP indexer for Java/Kotlin projects using scip-java."""
    
    def generate(
        self,
        project_dir: Path,
        output_dir: Path,
        build_system: str
    ) -> IndexerResult:
        """Generate SCIP index for Java/Kotlin project."""
        start_time = time.time()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Build command based on build system
            if build_system == "maven":
                cmd = ["cs", "launch", "com.sourcegraph:scip-java_2.13:0.11.1", "--", "index", "--build-tool=maven"]
            elif build_system == "gradle":
                cmd = ["cs", "launch", "com.sourcegraph:scip-java_2.13:0.11.1", "--", "index", "--build-tool=gradle"]
            else:
                raise ValueError(f"Unsupported build system: {build_system}")
            
            # Run indexer
            result = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                # Find generated .scip file
                scip_file = project_dir / "index.scip"
                if scip_file.exists():
                    # Move to output directory
                    target_file = output_dir / "index.scip"
                    shutil.move(str(scip_file), str(target_file))
                    return IndexerResult(
                        status=IndexerStatus.SUCCESS,
                        duration_seconds=duration,
                        output_file=target_file,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        exit_code=result.returncode
                    )
            
            return IndexerResult(
                status=IndexerStatus.FAILED,
                duration_seconds=duration,
                output_file=None,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode
            )
            
        except Exception as e:
            duration = time.time() - start_time
            return IndexerResult(
                status=IndexerStatus.FAILED,
                duration_seconds=duration,
                output_file=None,
                stdout="",
                stderr=str(e),
                exit_code=-1
            )
    
    def is_available(self) -> bool:
        """Check if Coursier and scip-java are available."""
        return shutil.which("cs") is not None
    
    def get_version(self) -> Optional[str]:
        """Get scip-java version."""
        try:
            result = subprocess.run(
                ["cs", "launch", "com.sourcegraph:scip-java_2.13:0.11.1", "--", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
