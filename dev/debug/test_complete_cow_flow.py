#!/usr/bin/env python3
"""
Complete CoW migration flow test.
Tests the actual user workflow: stop/start containers → trigger migration.
"""

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
import sys
import os
import subprocess

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from code_indexer.services.migration_middleware import MigrationStateTracker, migration_middleware
from code_indexer.services.docker_manager import DockerManager


async def test_complete_cow_flow():
    """
    Test the complete CoW flow:
    1. Check current container mount status
    2. Test migration detection
    3. Verify error handling for legacy containers
    """
    
    print("🔍 Testing Complete CoW Migration Flow...")
    
    # Step 1: Check current container status
    print("\n📦 Checking current container configuration...")
    
    docker_manager = DockerManager()
    container_exists = docker_manager._container_exists("qdrant")
    
    if container_exists:
        print("✅ Qdrant container exists")
        
        # Check if it has home mount
        has_home_mount = await migration_middleware._check_container_has_home_mount()
        print(f"   Home directory mounted: {has_home_mount}")
        
        if not has_home_mount:
            print("   ⚠️  Container running in LEGACY mode")
        else:
            print("   ✅ Container running in CoW mode")
    else:
        print("❌ Qdrant container does not exist")
        return
    
    # Step 2: Test migration state
    print("\n🔍 Checking migration state...")
    
    state_tracker = MigrationStateTracker()
    state = await state_tracker.load_state()
    
    print(f"   Container migrated: {state.get('container_migrated')}")
    print(f"   Projects migrated: {len(state.get('migrated_projects', []))}")
    
    current_project = Path.cwd()
    needs_container_migration = await state_tracker.needs_container_migration()
    needs_project_migration = await state_tracker.needs_project_migration(current_project)
    
    print(f"   Current project needs migration: {needs_project_migration}")
    print(f"   Container needs migration: {needs_container_migration}")
    
    # Step 3: Test migration detection logic
    print("\n🔄 Testing migration detection...")
    
    try:
        container_migration_needed = await migration_middleware._check_container_migration_needed()
        print(f"   Container migration check result: {container_migration_needed}")
        
    except RuntimeError as e:
        print(f"   ⚠️  Migration error (expected for legacy containers):")
        print(f"       {str(e)}")
        print("\n   This is CORRECT behavior - user must stop/start containers")
        
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        
    # Step 4: Test project migration detection  
    try:
        project_migration_needed = await migration_middleware._check_project_migration_needed(current_project)
        print(f"   Project migration check result: {project_migration_needed}")
        
    except Exception as e:
        print(f"   ❌ Project migration check failed: {e}")
    
    # Step 5: Test full migration trigger (only if safe)
    print("\n🚀 Testing migration trigger...")
    
    try:
        await migration_middleware.ensure_migration_compatibility(
            "test_complete_flow", current_project
        )
        print("✅ Migration completed successfully")
        
    except RuntimeError as e:
        if "CONTAINER MIGRATION REQUIRED" in str(e):
            print("✅ Correctly detected legacy container and requested stop/start")
            print("   This is the expected behavior!")
        else:
            print(f"❌ Unexpected runtime error: {e}")
            
    except Exception as e:
        print(f"❌ Migration trigger failed: {e}")
    
    print("\n🎯 Complete CoW flow test finished!")


async def test_container_mount_detection():
    """Test container mount detection logic."""
    
    print("\n🔗 Testing Container Mount Detection...")
    
    try:
        has_home_mount = await migration_middleware._check_container_has_home_mount()
        print(f"✅ Home mount detection result: {has_home_mount}")
        
        # Get detailed mount information
        result = subprocess.run([
            "docker", "inspect", "code-indexer-qdrant",
            "--format", "{{range .Mounts}}{{.Source}}:{{.Destination}}:{{.Mode}}{{\"\\n\"}}{{end}}"
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("📋 Current container mounts:")
            mounts = result.stdout.strip().split('\n')
            for mount in mounts:
                if mount.strip():
                    print(f"   {mount}")
                    
            home_dir = str(Path.home())
            print(f"\n🏠 Looking for home mount: {home_dir}:{home_dir}")
            
        else:
            print("❌ Could not inspect container mounts")
            
    except Exception as e:
        print(f"❌ Mount detection test failed: {e}")


async def demonstrate_proper_workflow():
    """Demonstrate the proper user workflow for CoW migration."""
    
    print("\n📋 PROPER CoW MIGRATION WORKFLOW:")
    print("==================================")
    
    print("\n1. 🛑 Stop containers:")
    print("   cidx stop")
    
    print("\n2. 🚀 Start containers (auto-creates CoW mount):")
    print("   cidx start")
    
    print("\n3. 🔍 Use any command requiring qdrant:")
    print("   cidx status")
    print("   cidx query 'test'")
    print("   cidx index")
    
    print("\n4. ✅ Migration happens automatically:")
    print("   - Detects missing local collections")
    print("   - Finds collections in global storage") 
    print("   - Moves collections to local storage")
    print("   - Creates symlinks back to container")
    print("   - Qdrant sees collections via symlinks")
    
    print("\n5. 🎯 Result:")
    print("   - Collections stored locally in project")
    print("   - Qdrant accesses via symlinks")
    print("   - CoW functionality enabled")


if __name__ == "__main__":
    asyncio.run(test_complete_cow_flow())
    asyncio.run(test_container_mount_detection())
    asyncio.run(demonstrate_proper_workflow())