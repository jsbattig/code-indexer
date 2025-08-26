#!/usr/bin/env python3
"""
Manual test script to verify CoW migration functionality.
This script manually tests the migration system components.
"""

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from code_indexer.services.migration_middleware import MigrationStateTracker, migration_middleware


async def test_migration_components():
    """Test migration system components manually."""
    
    print("🔍 Testing CoW Migration System Components...")
    
    # Test 1: State Tracker
    print("\n1. Testing MigrationStateTracker...")
    state_tracker = MigrationStateTracker()
    
    try:
        state = await state_tracker.load_state()
        print(f"✅ State loaded: container_migrated={state.get('container_migrated')}")
        print(f"   Migrated projects: {len(state.get('migrated_projects', []))}")
    except Exception as e:
        print(f"❌ State tracker failed: {e}")
        return
    
    # Test 2: Container storage path detection
    print("\n2. Testing container storage path detection...")
    try:
        container_storage_path = await migration_middleware._get_container_storage_path()
        if container_storage_path:
            print(f"✅ Container storage path: {container_storage_path}")
            print(f"   Path exists: {container_storage_path.exists()}")
        else:
            print("⚠️  Could not determine container storage path")
    except Exception as e:
        print(f"❌ Container path detection failed: {e}")
    
    # Test 3: Global storage detection  
    print("\n3. Testing global storage detection...")
    try:
        global_storage_path = await migration_middleware._get_global_storage_path()
        if global_storage_path:
            print(f"✅ Global storage path: {global_storage_path}")
            print(f"   Path exists: {global_storage_path.exists()}")
        else:
            print("⚠️  Could not determine global storage path")
    except Exception as e:
        print(f"❌ Global storage detection failed: {e}")
    
    # Test 4: Check current project migration status
    print("\n4. Testing current project migration status...")
    try:
        current_project = Path.cwd()
        needs_migration = await state_tracker.needs_project_migration(current_project)
        needs_container_migration = await state_tracker.needs_container_migration()
        
        print(f"✅ Current project: {current_project}")
        print(f"   Needs migration: {needs_migration}")
        print(f"   Container needs migration: {needs_container_migration}")
    except Exception as e:
        print(f"❌ Migration status check failed: {e}")
    
    print("\n🎯 Migration component test completed!")


async def test_create_legacy_scenario():
    """Test creating a legacy scenario for migration testing."""
    
    print("\n🔧 Testing Legacy Scenario Creation...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_project = Path(temp_dir) / "test_migration_project"
        test_project.mkdir()
        
        # Create .code-indexer config
        code_indexer_dir = test_project / ".code-indexer"
        code_indexer_dir.mkdir()
        
        config_data = {
            "embedding_provider": "voyage-ai",
            "embedding_model": "voyage-code-3",
            "qdrant": {
                "host": "http://localhost:6333",
                "collection": "code_index"
            }
        }
        
        with open(code_indexer_dir / "config.json", 'w') as f:
            json.dump(config_data, f, indent=2)
        
        print(f"✅ Created test project: {test_project}")
        
        # Test finding collections in global storage
        try:
            collections = await migration_middleware._find_project_collections_in_global_storage(test_project)
            print(f"✅ Found {len(collections)} collections in global storage")
            for collection in collections:
                print(f"   - {collection.name} ({collection.size} bytes)")
        except Exception as e:
            print(f"⚠️  Collection search failed (expected if no collections): {e}")
        
        # Test migration need detection
        try:
            container_migration_needed = await migration_middleware._check_container_migration_needed()
            project_migration_needed = await migration_middleware._check_project_migration_needed(test_project)
            
            print(f"✅ Migration needs check:")
            print(f"   Container migration needed: {container_migration_needed}")
            print(f"   Project migration needed: {project_migration_needed}")
        except Exception as e:
            print(f"❌ Migration needs check failed: {e}")

    print("🎯 Legacy scenario test completed!")


if __name__ == "__main__":
    asyncio.run(test_migration_components())
    asyncio.run(test_create_legacy_scenario())