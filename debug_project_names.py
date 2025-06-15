#!/usr/bin/env python3

from code_indexer.services.docker_manager import DockerManager
import os

def test_scenario_like_integration_test():
    """Test the exact scenario from the failing integration test."""
    print('=== Testing Docker Manager Creation Scenario ===')
    
    # Create DockerManager instances exactly like the integration test does
    print('\n1. Creating docker_manager1 in project1 directory:')
    os.chdir('/home/jsbattig/Dev/code-indexer/tests/projects/test_project_1')
    docker_manager1 = DockerManager()
    print(f'Current dir when creating dm1: {os.getcwd()}')
    print(f'dm1.project_name: {docker_manager1.project_name}')
    
    print('\n2. Creating docker_manager2 in project2 directory:')
    os.chdir('/home/jsbattig/Dev/code-indexer/tests/projects/test_project_2')
    docker_manager2 = DockerManager()
    print(f'Current dir when creating dm2: {os.getcwd()}')
    print(f'dm2.project_name: {docker_manager2.project_name}')
    
    print('\n3. Checking container names each would generate:')
    print(f'dm1 ollama container: {docker_manager1.get_container_name("ollama")}')
    print(f'dm2 ollama container: {docker_manager2.get_container_name("ollama")}')
    print(f'dm1 qdrant container: {docker_manager1.get_container_name("qdrant")}')
    print(f'dm2 qdrant container: {docker_manager2.get_container_name("qdrant")}')
    
    print('\n4. Are the project names different?')
    different = docker_manager1.project_name != docker_manager2.project_name
    print(f'dm1.project_name != dm2.project_name: {different}')
    
    if not different:
        print('\n❌ PROBLEM: Both DockerManager instances have the same project name!')
        print('This would cause container name conflicts.')
        return False
    else:
        print('\n✅ Project names are different as expected.')
        
        # Check what current working directory is for each instance
        print('\n5. Checking internal state:')
        print(f'Current working directory: {os.getcwd()}')
        
        # Let's also manually check what _detect_project_name would return for each
        print('\n6. Manual project name detection:')
        os.chdir('/home/jsbattig/Dev/code-indexer/tests/projects/test_project_1')
        manual_dm1 = DockerManager()
        print(f'Manual dm1 project name: {manual_dm1.project_name}')
        
        os.chdir('/home/jsbattig/Dev/code-indexer/tests/projects/test_project_2')
        manual_dm2 = DockerManager()
        print(f'Manual dm2 project name: {manual_dm2.project_name}')
        
        return True

if __name__ == "__main__":
    test_scenario_like_integration_test()