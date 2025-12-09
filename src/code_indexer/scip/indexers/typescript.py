"""TypeScript SCIP indexer using scip-typescript."""

import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional

from .base import SCIPIndexer, IndexerResult, IndexerStatus


class TypeScriptIndexer(SCIPIndexer):
    """SCIP indexer for TypeScript/JavaScript projects."""
    
    def generate(
        self,
        project_dir: Path,
        output_dir: Path,
        build_system: str
    ) -> IndexerResult:
        """Generate SCIP index for TypeScript/JavaScript project."""
        start_time = time.time()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Run scip-typescript indexer
            cmd = ["scip-typescript", "index"]
            
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
        """Check if scip-typescript is available."""
        return shutil.which("scip-typescript") is not None
    
    def get_version(self) -> Optional[str]:
        """Get scip-typescript version."""
        try:
            result = subprocess.run(
                ["scip-typescript", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
