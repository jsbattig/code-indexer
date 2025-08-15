#!/usr/bin/env python3
"""
Script to reorganize the test directory from flat structure to logical hierarchies.

This script uses the TestFileReorganizer to move test files from the current
flat structure into organized subdirectories based on test type and functionality.
"""

import sys
from pathlib import Path
from src.code_indexer.test_infrastructure.test_reorganizer import TestFileReorganizer


def main():
    """Main reorganization function."""
    test_root = Path(__file__).parent / "tests"
    
    if not test_root.exists():
        print(f"Error: Test directory not found at {test_root}")
        sys.exit(1)
    
    # Get statistics first
    reorganizer = TestFileReorganizer(test_root, dry_run=True)
    stats = reorganizer.get_file_statistics()
    
    print("=" * 60)
    print("TEST DIRECTORY REORGANIZATION")
    print("=" * 60)
    print(f"Test root: {test_root}")
    print(f"Total test files: {stats['total']}")
    print(f"Unit tests: {stats['unit']}")
    print(f"Integration tests: {stats['integration']}")
    print(f"E2E tests: {stats['e2e']}")
    print()
    
    # Show dry run results
    print("DRY RUN - Proposed file moves:")
    print("-" * 40)
    move_plan = reorganizer.reorganize_tests()
    
    for move in move_plan:
        print(f"{move['source']} -> {move['destination']}")
    
    print(f"\nTotal files to move: {len(move_plan)}")
    print()
    
    # Ask for confirmation
    response = input("Proceed with reorganization? (y/N): ").strip().lower()
    if response != 'y':
        print("Reorganization cancelled.")
        sys.exit(0)
    
    # Create backup
    print("Creating backup...")
    reorganizer_real = TestFileReorganizer(test_root, dry_run=False, backup_original=True)
    backup_path = reorganizer_real.create_backup()
    print(f"Backup created at: {backup_path}")
    
    try:
        # Create directory structure
        print("Creating directory structure...")
        reorganizer_real.create_directory_structure()
        
        # Reorganize files
        print("Moving files...")
        actual_moves = reorganizer_real.reorganize_tests()
        
        # Validate reorganization
        print("Validating reorganization...")
        validation = reorganizer_real.validate_reorganization()
        
        print("=" * 60)
        print("REORGANIZATION COMPLETE")
        print("=" * 60)
        print(f"Files moved: {len(actual_moves)}")
        print(f"All files moved: {validation['all_files_moved']}")
        print(f"No missing files: {validation['no_missing_files']}")
        print(f"Import paths valid: {validation['import_paths_valid']}")
        print(f"Tests discovered: {len(validation['discovered_tests'])}")
        
        if validation['errors']:
            print("\nErrors encountered:")
            for error in validation['errors']:
                print(f"  - {error}")
        
        print(f"\nBackup location: {backup_path}")
        print("Reorganization completed successfully!")
        
    except Exception as e:
        print(f"Error during reorganization: {e}")
        print(f"Rolling back from backup: {backup_path}")
        reorganizer_real.rollback_from_backup(backup_path)
        print("Rollback completed.")
        sys.exit(1)


if __name__ == "__main__":
    main()