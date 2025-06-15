#!/usr/bin/env python3
"""Debug script to investigate multi-project container isolation."""

import os
import sys
import json
import subprocess
from pathlib import Path

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from code_indexer.services.docker_manager import DockerManager


def run_command(cmd, description=""):
    """Run a command and return its output."""
    print(f"\n{'='*60}")
    print(f"Running: {' '.join(cmd)}")
    if description:
        print(f"Description: {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        print(f"Return code: {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
        return result
    except Exception as e:
        print(f"Error running command: {e}")
        return None


def main():
    """Debug multi-project isolation."""
    print("DEBUG: Multi-project container isolation")
    
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
    
    # Set up Docker managers
    print("\n=== Setting up Docker managers ===")
    
    os.chdir(project1_path)
    print(f"Changed to: {os.getcwd()}")
    docker_manager1 = DockerManager()
    print(f"Project 1 name: {docker_manager1.project_name}")
    
    os.chdir(project2_path)
    print(f"Changed to: {os.getcwd()}")
    docker_manager2 = DockerManager()
    print(f"Project 2 name: {docker_manager2.project_name}")
    
    print(f"Project names different: {docker_manager1.project_name != docker_manager2.project_name}")
    
    # Clean up first
    print("\n=== Cleaning up any existing containers ===")
    try:
        docker_manager1.stop()
        docker_manager1.clean()
        docker_manager2.stop()
        docker_manager2.clean()
    except Exception as e:
        print(f"Cleanup error (expected): {e}")
    
    # Check initial state
    print("\n=== Initial container state ===")
    run_command(["podman", "ps", "-a"], "All containers")
    run_command(["podman-compose", "ps", "--format", "json"], "All compose containers")
    
    try:
        # Start project 1
        print("\n=== Starting project 1 ===")
        os.chdir(project1_path)
        docker_manager1.start()
        
        # Check project 1 containers
        print("\n=== After starting project 1 ===")
        run_command(["podman", "ps"], "Running containers")
        run_command(["podman-compose", "-p", docker_manager1.project_name, "ps", "--format", "json"], 
                   f"Project 1 containers ({docker_manager1.project_name})")
        
        status1 = docker_manager1.status()
        print(f"Project 1 status: {status1}")
        
        # Start project 2
        print("\n=== Starting project 2 ===")
        os.chdir(project2_path)
        docker_manager2.start()
        
        # Check all containers after starting both
        print("\n=== After starting both projects ===")
        run_command(["podman", "ps"], "All running containers")
        run_command(["podman-compose", "-p", docker_manager1.project_name, "ps", "--format", "json"], 
                   f"Project 1 containers ({docker_manager1.project_name})")
        run_command(["podman-compose", "-p", docker_manager2.project_name, "ps", "--format", "json"], 
                   f"Project 2 containers ({docker_manager2.project_name})")
        
        # Check project statuses
        os.chdir(project1_path)
        status1 = docker_manager1.status()
        print(f"Project 1 status: {status1}")
        
        os.chdir(project2_path)
        status2 = docker_manager2.status()
        print(f"Project 2 status: {status2}")
        
        # Debug: Check what containers actually exist and their names
        print("\n=== Debugging container names ===")
        result = run_command(["podman", "ps", "--format", "json"], "Container details")
        if result and result.stdout:
            try:
                containers = json.loads(result.stdout)
                for container in containers:
                    print(f"Container: {container.get('Names', [])} - Image: {container.get('Image')} - Status: {container.get('State')}")
            except json.JSONDecodeError as e:
                print(f"Failed to parse container JSON: {e}")
        
        # Check if the issue is with working directory context
        print("\n=== Debugging working directory context ===")
        for path, manager in [(project1_path, docker_manager1), (project2_path, docker_manager2)]:
            os.chdir(path)
            print(f"Working directory: {os.getcwd()}")
            run_command(["podman-compose", "ps", "--format", "json"], 
                       f"Default compose ps from {path.name}")
            run_command(["podman-compose", "-p", manager.project_name, "ps", "--format", "json"], 
                       f"Project-specific compose ps for {manager.project_name}")
        
    finally:
        # Clean up
        print("\n=== Cleaning up ===")
        try:
            docker_manager1.stop()
            docker_manager1.clean()
            docker_manager2.stop() 
            docker_manager2.clean()
        except Exception as e:
            print(f"Cleanup error: {e}")


if __name__ == "__main__":
    main()