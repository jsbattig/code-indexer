#!/usr/bin/env python3
"""
Test script to demonstrate the CoW clone configuration fix functionality.

This script shows how the new project configuration fixes work for CoW clones
by simulating the scenario where a CoW clone needs its own containers and ports.
"""

import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

# Import the new functionality
from code_indexer.services.config_fixer import ConfigurationRepairer


def simulate_cow_clone_fix():
    """Simulate a CoW clone needing configuration fixes."""
    print("🧪 Simulating CoW clone configuration fix...")
    
    # Create a temporary directory structure to simulate a CoW clone
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        project_dir = temp_path / "cow_clone_project"
        config_dir = project_dir / ".code-indexer"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a sample config file with old port configurations
        config_data = {
            "codebase_dir": str(project_dir),
            "embedding_provider": "voyage-ai",
            "voyage_ai": {"model": "voyage-code-2"},
            "qdrant": {"collection_base_name": "test-collection"},
            "project_hash": "old_hash_123",
            "project_ports": {
                "qdrant_port": 6333,  # Old default port
                "ollama_port": 11434,  # Old default port
                "data_cleaner_port": 8091  # Old default port
            }
        }
        
        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)
        
        print(f"📁 Created test project at: {project_dir}")
        print(f"⚙️  Original config: {config_data['project_ports']}")
        
        # Mock the DockerManager to simulate new port generation
        with patch("code_indexer.services.config_fixer.DockerManager") as mock_docker_manager_class:
            mock_docker_manager = Mock()
            
            # Simulate what would happen for a CoW clone at a different filesystem location
            mock_docker_manager._generate_container_names.return_value = {
                "project_hash": "new_hash_456",  # Different hash based on new location
                "qdrant_name": "cidx-new_hash_456-qdrant",
                "ollama_name": "cidx-new_hash_456-ollama",
                "data_cleaner_name": "cidx-new_hash_456-data-cleaner"
            }
            
            # Simulate new ports calculated from the new project hash
            mock_docker_manager._calculate_project_ports.return_value = {
                "qdrant_port": 7123,    # New port based on hash
                "ollama_port": 12567,   # New port based on hash
                "data_cleaner_port": 8789  # New port based on hash
            }
            
            mock_docker_manager_class.return_value = mock_docker_manager
            
            # Create the configuration repairer and run the fix
            repairer = ConfigurationRepairer(config_dir, dry_run=True)
            
            print("\n🔧 Running project configuration fix...")
            project_info = repairer._regenerate_project_configuration()
            
            if project_info:
                print(f"✅ New project hash: {project_info['project_hash']}")
                print(f"✅ New container names: {project_info['container_names']}")
                print(f"✅ New port assignments: {project_info['port_assignments']}")
                
                # Show what fixes would be applied
                with patch("code_indexer.services.config_fixer.ConfigManager") as mock_config_manager_class:
                    mock_config_manager = Mock()
                    mock_config = Mock()
                    mock_config.project_ports = Mock()
                    mock_config.project_ports.qdrant_port = 6333
                    mock_config.project_ports.ollama_port = 11434
                    mock_config.project_ports.data_cleaner_port = 8091
                    mock_config_manager.load.return_value = mock_config
                    mock_config_manager_class.return_value = mock_config_manager
                    
                    fixes = repairer._fix_project_configuration()
                    
                    print(f"\n📝 Configuration fixes that would be applied: {len(fixes)}")
                    for fix in fixes:
                        print(f"   • {fix.fix_type}: {fix.description}")
                        print(f"     Reason: {fix.reason}")
                    
                    print("\n🎉 CoW clone configuration fix simulation completed!")
                    return True
            else:
                print("❌ Failed to regenerate project configuration")
                return False


def demonstrate_port_calculation():
    """Demonstrate how ports are calculated for different project locations."""
    print("\n🔢 Demonstrating port calculation for different project locations...")
    
    # Simulate different project locations
    test_locations = [
        "/home/user/project1",
        "/home/user/project2", 
        "/tmp/cow_clone_project1",
        "/tmp/cow_clone_project2"
    ]
    
    with patch("code_indexer.services.config_fixer.DockerManager") as mock_docker_manager_class:
        for i, location in enumerate(test_locations):
            mock_docker_manager = Mock()
            
            # Each location gets a different hash
            project_hash = f"hash_{i:04d}"
            mock_docker_manager._generate_container_names.return_value = {
                "project_hash": project_hash,
                "qdrant_name": f"cidx-{project_hash}-qdrant",
                "ollama_name": f"cidx-{project_hash}-ollama",
                "data_cleaner_name": f"cidx-{project_hash}-data-cleaner"
            }
            
            # Each location gets different ports
            base_offset = i * 100
            mock_docker_manager._calculate_project_ports.return_value = {
                "qdrant_port": 6333 + base_offset,
                "ollama_port": 11434 + base_offset,
                "data_cleaner_port": 8091 + base_offset
            }
            
            mock_docker_manager_class.return_value = mock_docker_manager
            
            # Create a temporary config directory
            with tempfile.TemporaryDirectory() as temp_dir:
                config_dir = Path(temp_dir) / ".code-indexer"
                config_dir.mkdir(parents=True)
                
                repairer = ConfigurationRepairer(config_dir, dry_run=True)
                project_info = repairer._regenerate_project_configuration()
                
                if project_info:
                    print(f"📍 {location}")
                    print(f"   Hash: {project_info['project_hash']}")
                    print(f"   Ports: {project_info['port_assignments']}")


if __name__ == "__main__":
    print("🚀 Testing CoW Clone Configuration Fix Functionality")
    print("=" * 60)
    
    try:
        success = simulate_cow_clone_fix()
        if success:
            demonstrate_port_calculation()
            print("\n✅ All tests completed successfully!")
        else:
            print("\n❌ Tests failed!")
    except Exception as e:
        print(f"\n💥 Error during testing: {e}")
        raise