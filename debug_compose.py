#!/usr/bin/env python3

import os
import sys
import tempfile
from pathlib import Path

# Add the project root to sys.path to import modules
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from code_indexer.services.docker_manager import DockerManager

def main():
    # Create a test directory
    with tempfile.TemporaryDirectory(suffix="-test-project") as test_dir:
        os.chdir(test_dir)
        
        print(f"Test directory: {test_dir}")
        
        # Create DockerManager
        docker_manager = DockerManager()
        
        # Generate compose config
        print(f"Project name: {docker_manager.project_name}")
        compose_config = docker_manager.generate_compose_config()
        
        # Print the compose config for debugging
        import json
        print("Generated compose config:")
        print(json.dumps(compose_config, indent=2, default=str))
        
        # Check healthcheck configurations specifically
        print("\n=== Healthcheck configurations ===")
        if "services" in compose_config:
            for service_name, service_config in compose_config["services"].items():
                if "healthcheck" in service_config:
                    print(f"{service_name} healthcheck:")
                    print(f"  test: {service_config['healthcheck']['test']}")
                    print(f"  test type: {type(service_config['healthcheck']['test'])}")
                    if isinstance(service_config['healthcheck']['test'], list):
                        for i, item in enumerate(service_config['healthcheck']['test']):
                            print(f"    [{i}]: '{item}' (type: {type(item)})")
                else:
                    print(f"{service_name}: No healthcheck")

if __name__ == "__main__":
    main()