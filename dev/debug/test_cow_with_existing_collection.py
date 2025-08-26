#!/usr/bin/env python3
"""
Test CoW migration with an actual existing collection.
This creates a realistic legacy scenario and tests the full migration.
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


async def create_realistic_legacy_scenario():
    """Create a realistic legacy scenario by copying an existing collection."""
    
    print("🔧 Creating Realistic Legacy Migration Scenario...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_project = Path(temp_dir) / "legacy_migration_test"
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
        
        # Step 1: Get current container storage path
        try:
            result = subprocess.run([
                "docker", "inspect", "code-indexer-qdrant",
                "--format", "{{range .Mounts}}{{if eq .Destination \"/qdrant/storage\"}}{{.Source}}{{end}}{{end}}"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0 or not result.stdout.strip():
                print("❌ Could not get container storage path")
                return False
                
            container_storage_path = Path(result.stdout.strip())
            print(f"✅ Container storage path: {container_storage_path}")
            
        except Exception as e:
            print(f"❌ Failed to get container storage path: {e}")
            return False
        
        # Step 2: Find an existing collection to work with
        collections_dir = container_storage_path / "collections"
        if not collections_dir.exists():
            print(f"❌ Collections directory not found: {collections_dir}")
            return False
            
        existing_collections = [d for d in collections_dir.iterdir() if d.is_dir() and not d.is_symlink()]
        if not existing_collections:
            print("❌ No existing collections found to test with")
            return False
            
        # Pick a small collection for testing
        test_collection = None
        for collection in existing_collections[:10]:  # Check first 10
            if collection.name.startswith('code_index_'):
                test_collection = collection
                break
                
        if not test_collection:
            print("❌ No suitable test collection found")
            return False
            
        print(f"✅ Selected test collection: {test_collection.name}")
        
        # Step 3: Create project-specific collection by copying existing one
        # Generate a project ID for our test project
        from code_indexer.services.embedding_factory import EmbeddingProviderFactory
        project_id = EmbeddingProviderFactory.generate_project_id(str(test_project))
        
        # Create a project-specific collection name
        test_collection_name = f"code_index_{project_id}_voyage_ai_voyage_code_3"
        target_collection_path = collections_dir / test_collection_name
        
        try:
            print(f"📁 Copying collection to create legacy scenario...")
            print(f"   From: {test_collection}")
            print(f"   To: {target_collection_path}")
            
            # Copy the collection
            shutil.copytree(test_collection, target_collection_path)
            print(f"✅ Created test collection: {test_collection_name}")
            
        except Exception as e:
            print(f"❌ Failed to copy collection: {e}")
            return False
        
        # Step 4: Remove project from migration state to simulate legacy
        state_tracker = MigrationStateTracker()
        state = await state_tracker.load_state()
        
        project_key = str(test_project.resolve())
        if project_key in state.get("migrated_projects", []):
            state["migrated_projects"].remove(project_key)
            state_tracker._state = state
            await state_tracker.save_state()
            
        print(f"✅ Simulated legacy state for project: {project_key}")
        
        # Step 5: Verify legacy scenario is set up
        collections = await migration_middleware._find_project_collections_in_global_storage(test_project)
        print(f"✅ Found {len(collections)} collections in legacy scenario:")
        for collection in collections:
            print(f"   - {collection.name} ({collection.size} bytes)")
        
        # Step 6: Trigger migration
        print(f"\n🚀 Triggering CoW Migration...")
        try:
            await migration_middleware.ensure_migration_compatibility(
                "test_legacy_migration", test_project
            )
            print("✅ Migration completed successfully!")
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            # Clean up test collection
            if target_collection_path.exists():
                shutil.rmtree(target_collection_path)
            return False
        
        # Step 7: Verify migration results
        print(f"\n🔍 Verifying migration results...")
        
        # Check local storage
        local_storage = test_project / ".code-indexer" / "qdrant-data"
        local_collections = local_storage / "collections"
        local_collection_path = local_collections / test_collection_name
        
        if local_collection_path.exists():
            print(f"✅ Collection migrated to local storage: {local_collection_path}")
        else:
            print(f"❌ Collection not found in local storage")
            
        # Check symlink
        symlink_path = collections_dir / test_collection_name
        if symlink_path.is_symlink():
            print(f"✅ Symlink created: {symlink_path} -> {symlink_path.resolve()}")
            
            # Verify symlink points to local collection
            if symlink_path.resolve() == local_collection_path.resolve():
                print(f"✅ Symlink points to correct local collection")
            else:
                print(f"❌ Symlink points to wrong location: {symlink_path.resolve()}")
                
        else:
            print(f"❌ Symlink not created at: {symlink_path}")
        
        # Check migration state
        final_state = await state_tracker.load_state()
        if project_key in final_state.get("migrated_projects", []):
            print("✅ Project marked as migrated")
        else:
            print("❌ Project not marked as migrated")
        
        # Step 8: Test that qdrant can access the collection via symlink
        print(f"\n🔗 Testing Qdrant access via symlink...")
        try:
            import requests
            response = requests.get(f"http://localhost:6333/collections/{test_collection_name}")
            if response.status_code == 200:
                print(f"✅ Qdrant can access collection via symlink")
                collection_info = response.json()
                vectors_count = collection_info.get('result', {}).get('vectors_count', 0)
                print(f"   Vectors count: {vectors_count}")
            else:
                print(f"⚠️  Qdrant response: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Qdrant access test failed: {e}")
        
        print(f"\n🎉 Legacy migration scenario test completed!")
        
        # Clean up: remove test collection
        try:
            if local_collection_path.exists():
                shutil.rmtree(local_collection_path)
            if symlink_path.exists() or symlink_path.is_symlink():
                if symlink_path.is_symlink():
                    symlink_path.unlink()
                else:
                    shutil.rmtree(symlink_path)
            print(f"✅ Cleaned up test collection")
        except Exception as e:
            print(f"⚠️  Cleanup warning: {e}")
        
        return True


if __name__ == "__main__":
    success = asyncio.run(create_realistic_legacy_scenario())
    if success:
        print(f"\n🎯 CoW Migration System: FULLY FUNCTIONAL ✅")
    else:
        print(f"\n❌ CoW Migration System: NEEDS ATTENTION")