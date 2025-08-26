#!/usr/bin/env python3
"""
Script to systematically add collection registration to e2e tests.
"""

import re
from pathlib import Path

# List of e2e test files that create real collections
E2E_TEST_FILES = [
    "test_branch_topology_e2e.py",
    "test_schema_migration_e2e.py", 
    "test_comprehensive_git_workflow.py",
    "test_git_aware_watch_e2e.py",
    "test_reconcile_e2e.py",
    "test_claude_e2e.py",
    "test_line_number_display_e2e.py",
    "test_deadlock_reproduction.py",
    "test_stuck_verification_retry.py",
]

def add_import_if_missing(file_path: Path):
    """Add the auto_register_project_collections import if not present."""
    content = file_path.read_text()
    
    # Check if import already exists
    if "auto_register_project_collections" in content:
        print(f"✅ {file_path.name}: import already exists")
        return content
    
    # Pattern to find test_infrastructure imports
    pattern = r'(from \.test_infrastructure import .*?)(\))'
    
    match = re.search(pattern, content, re.DOTALL)
    if match:
        # Add auto_register_project_collections to the import
        import_section = match.group(1)
        if "auto_register_project_collections" not in import_section:
            new_import = import_section + ",\n    auto_register_project_collections,"
            content = content.replace(match.group(1), new_import)
            print(f"🔧 {file_path.name}: added auto_register_project_collections import")
        
        file_path.write_text(content)
        return content
    else:
        # Try to add it to existing imports
        pattern = r'(from \.test_infrastructure import [^)]+)'
        match = re.search(pattern, content)
        if match:
            new_import = match.group(1) + ", auto_register_project_collections"
            content = content.replace(match.group(1), new_import)
            print(f"🔧 {file_path.name}: added auto_register_project_collections to existing import")
            file_path.write_text(content)
            return content
    
    print(f"⚠️  {file_path.name}: could not find test_infrastructure import to modify")
    return content

def add_collection_registration(file_path: Path):
    """Add collection registration calls to test methods."""
    content = file_path.read_text()
    
    # Patterns to look for project directory creation or usage
    patterns = [
        # Pattern 1: tempfile.mkdtemp or TemporaryDirectory usage
        (r'(temp_dir = Path\(tempfile\.mkdtemp.*?\))', 
         r'\1\n            # Auto-register collections for this project\n            auto_register_project_collections(temp_dir)'),
        
        # Pattern 2: project_path or similar assignments  
        (r'(project_(?:path|dir) = .*?)\n',
         r'\1\n        # Auto-register collections for this project\n        auto_register_project_collections(project_path)\n'),
         
        # Pattern 3: self.test_repo_dir assignments
        (r'(self\.test_repo_dir = .*?)\n',
         r'\1\n        # Auto-register collections for this project\n        auto_register_project_collections(self.test_repo_dir)\n'),
    ]
    
    modified = False
    for pattern, replacement in patterns:
        if re.search(pattern, content):
            new_content = re.sub(pattern, replacement, content)
            if new_content != content:
                content = new_content
                modified = True
                print(f"🔧 {file_path.name}: added collection registration")
    
    if modified:
        file_path.write_text(content)
    else:
        print(f"ℹ️  {file_path.name}: no obvious places to add registration (might already be done or need manual review)")

def main():
    """Main function to update all e2e test files."""
    tests_dir = Path(__file__).parent.parent / "tests"
    
    print("🚀 Starting systematic update of e2e test collection registration...")
    
    for test_file in E2E_TEST_FILES:
        file_path = tests_dir / test_file
        if file_path.exists():
            print(f"\n📄 Processing {test_file}...")
            
            # Step 1: Add import
            content = add_import_if_missing(file_path)
            
            # Step 2: Add registration calls 
            add_collection_registration(file_path)
            
        else:
            print(f"⚠️  {test_file} not found")
    
    print("\n✅ Systematic update complete!")
    print("\nNote: Some files may need manual review for more complex patterns.")

if __name__ == "__main__":
    main()