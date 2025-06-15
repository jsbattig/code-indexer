#!/usr/bin/env python3
"""Debug script to investigate Docker Compose file generation for multiple projects."""

import os
import sys
import yaml
import subprocess
from pathlib import Path

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from code_indexer.services.docker_manager import DockerManager


def save_and_check_compose_file(docker_manager, project_name):
    """Save compose config and check if file is generated correctly."""
    print(f"\n{'='*60}")
    print(f"Checking compose file generation for {project_name}")
    print(f"{'='*60}")
    
    # Generate and save compose config
    compose_config = docker_manager.generate_compose_config()
    compose_file_path = Path(os.getcwd()) / "docker-compose.yml"
    
    print(f"Saving compose file to: {compose_file_path}")
    
    with open(compose_file_path, "w") as f:
        yaml.dump(compose_config, f, default_flow_style=False)
    
    print(f"Compose file exists: {compose_file_path.exists()}")
    print(f"Compose file size: {compose_file_path.stat().st_size if compose_file_path.exists() else 'N/A'} bytes")
    
    # Read and display compose file content
    if compose_file_path.exists():
        with open(compose_file_path, "r") as f:
            content = f.read()
        print(f"Compose file content:\n{content}")
    
    # Test compose file validity
    print(f"\nTesting compose file validity:")
    try:
        result = subprocess.run(
            ["podman-compose", "-p", project_name, "config"],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        print(f"Config validation return code: {result.returncode}")
        if result.stdout:
            print(f"Config stdout:\n{result.stdout}")
        if result.stderr:
            print(f"Config stderr:\n{result.stderr}")
    except Exception as e:
        print(f"Error validating compose file: {e}")
    
    return compose_config


def main():
    """Debug compose file generation for multiple projects."""
    print("DEBUG: Docker Compose file generation for multiple projects")
    
    # Project paths
    test_root = Path(__file__).parent / "tests" / "projects"
    project1_path = test_root / "test_project_1"
    project2_path = test_root / "test_project_2"
    
    print(f"Project 1 path: {project1_path}")
    print(f"Project 2 path: {project2_path}")
    
    # Check if projects exist
    if not project1_path.exists() or not project2_path.exists():
        print("ERROR: Test project directories not found")
        return
    
    # Clean up first
    print("\n=== Cleaning up any existing containers ===")
    for project_path in [project1_path, project2_path]:
        os.chdir(project_path)
        try:
            docker_manager = DockerManager()
            docker_manager.stop()
            docker_manager.clean()
        except Exception as e:
            print(f"Cleanup error for {project_path.name} (expected): {e}")
    
    # Test project 1
    os.chdir(project1_path)
    print(f"Changed to: {os.getcwd()}")
    docker_manager1 = DockerManager()
    print(f"Project 1 name: {docker_manager1.project_name}")
    
    compose_config1 = save_and_check_compose_file(docker_manager1, docker_manager1.project_name)
    
    # Test project 2
    os.chdir(project2_path)
    print(f"Changed to: {os.getcwd()}")
    docker_manager2 = DockerManager()
    print(f"Project 2 name: {docker_manager2.project_name}")
    
    compose_config2 = save_and_check_compose_file(docker_manager2, docker_manager2.project_name)
    
    # Compare configs
    print(f"\n{'='*60}")
    print("Comparing compose configurations")
    print(f"{'='*60}")
    
    print(f"Config 1 services: {list(compose_config1.get('services', {}).keys())}")
    print(f"Config 2 services: {list(compose_config2.get('services', {}).keys())}")
    
    # Check container names
    for service in ['ollama', 'qdrant']:
        if service in compose_config1.get('services', {}):
            name1 = compose_config1['services'][service].get('container_name')
            print(f"Project 1 {service} container name: {name1}")
        
        if service in compose_config2.get('services', {}):
            name2 = compose_config2['services'][service].get('container_name')
            print(f"Project 2 {service} container name: {name2}")
    
    # Test actual container start with detailed logging
    print(f"\n{'='*60}")
    print("Testing actual container start with detailed logging")
    print(f"{'='*60}")
    
    # Start project 1
    os.chdir(project1_path)
    print(f"\nStarting project 1 from: {os.getcwd()}")
    try:
        result = subprocess.run(
            ["podman-compose", "-p", docker_manager1.project_name, "up", "-d"],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        print(f"Project 1 start return code: {result.returncode}")
        print(f"Project 1 start stdout:\n{result.stdout}")
        if result.stderr:
            print(f"Project 1 start stderr:\n{result.stderr}")
    except Exception as e:
        print(f"Error starting project 1: {e}")
    
    # Start project 2
    os.chdir(project2_path)
    print(f"\nStarting project 2 from: {os.getcwd()}")
    try:
        result = subprocess.run(
            ["podman-compose", "-p", docker_manager2.project_name, "up", "-d"],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        print(f"Project 2 start return code: {result.returncode}")
        print(f"Project 2 start stdout:\n{result.stdout}")
        if result.stderr:
            print(f"Project 2 start stderr:\n{result.stderr}")
    except Exception as e:
        print(f"Error starting project 2: {e}")
    
    # Check final container state
    print(f"\n{'='*60}")
    print("Final container state")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(["podman", "ps"], capture_output=True, text=True)
        print(f"Final containers:\n{result.stdout}")
    except Exception as e:
        print(f"Error getting final container state: {e}")


if __name__ == "__main__":
    main()