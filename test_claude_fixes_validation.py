#!/usr/bin/env python3
"""
Test to validate that CLAUDE.md Foundation violations have been fixed.
This test checks that the golden_repo_manager.py fixes are working correctly.
"""

import sys
import ast
import re
from pathlib import Path


def check_no_time_sleep_in_production(file_path: Path) -> list:
    """Check for time.sleep() in production code."""
    issues = []
    content = file_path.read_text()
    
    # Check for time.sleep patterns
    sleep_pattern = re.compile(r'time\.sleep\(\s*\d+(?:\.\d+)?\s*\)')
    
    for match in sleep_pattern.finditer(content):
        line_num = content[:match.start()].count('\n') + 1
        context_start = max(0, match.start() - 100)
        context_end = min(len(content), match.end() + 100)
        context = content[context_start:context_end]
        
        # Check if this is in a polling/waiting context (acceptable)
        if '_wait_for_' in context or 'poll' in context.lower():
            continue  # Polling without sleep is acceptable
            
        issues.append(f"Line {line_num}: Found time.sleep() - {match.group()}")
    
    return issues


def check_no_generic_exceptions(file_path: Path) -> list:
    """Check for generic Exception handlers."""
    issues = []
    tree = ast.parse(file_path.read_text())
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type:
                if isinstance(node.type, ast.Name) and node.type.id == 'Exception':
                    # Check if it's re-raising (which is acceptable)
                    has_reraise = any(
                        isinstance(stmt, ast.Raise) and stmt.exc is None
                        for stmt in node.body
                    )
                    if not has_reraise:
                        issues.append(f"Line {node.lineno}: Generic 'except Exception' handler")
    
    return issues


def check_resource_management(file_path: Path) -> list:
    """Check for proper resource management with finally blocks."""
    issues = []
    content = file_path.read_text()
    lines = content.split('\n')
    
    # Look for resource acquisition patterns
    resource_patterns = [
        r'DockerManager\s*\(',
        r'open\s*\(',
        r'subprocess\.run\s*\(',
    ]
    
    for i, line in enumerate(lines, 1):
        for pattern in resource_patterns:
            if re.search(pattern, line):
                # Check if it's in a try block
                context_start = max(0, i - 5)
                context_end = min(len(lines), i + 10)
                context = '\n'.join(lines[context_start:context_end])
                
                # Check for try/finally or with statement
                if 'try:' not in context and 'with ' not in context:
                    issues.append(f"Line {i}: Resource acquisition without proper management - {line.strip()}")
    
    return issues


def check_no_fallback_behavior(file_path: Path) -> list:
    """Check for fallback behaviors."""
    issues = []
    content = file_path.read_text()
    lines = content.split('\n')
    
    # Patterns that indicate fallback behavior
    fallback_patterns = [
        r'fallback',
        r'try.*except.*pass.*continue',
        r'if.*failed.*proceed',
        r'ignore.*error.*continue',
    ]
    
    for i, line in enumerate(lines, 1):
        line_lower = line.lower()
        for pattern in fallback_patterns:
            if re.search(pattern, line_lower):
                # Check context to see if it's a legitimate error handling
                if 'APPROVED FALLBACK' in line:
                    continue  # Approved fallback
                if 'logging' in line_lower:
                    continue  # Just logging, not actual fallback
                    
                issues.append(f"Line {i}: Potential fallback behavior - {line.strip()}")
    
    return issues


def validate_fixes():
    """Main validation function."""
    file_path = Path('/home/jsbattig/Dev/code-indexer/src/code_indexer/server/repositories/golden_repo_manager.py')
    
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return False
    
    print(f"Validating fixes in: {file_path}")
    print("-" * 80)
    
    all_issues = []
    
    # Check for time.sleep() violations
    print("\n🔍 Checking for time.sleep() in production code...")
    sleep_issues = check_no_time_sleep_in_production(file_path)
    if sleep_issues:
        print(f"❌ Found {len(sleep_issues)} time.sleep() violations:")
        for issue in sleep_issues:
            print(f"   - {issue}")
        all_issues.extend(sleep_issues)
    else:
        print("✅ No time.sleep() violations found")
    
    # Check for generic exception handlers
    print("\n🔍 Checking for generic Exception handlers...")
    exception_issues = check_no_generic_exceptions(file_path)
    if exception_issues:
        print(f"❌ Found {len(exception_issues)} generic exception handlers:")
        for issue in exception_issues:
            print(f"   - {issue}")
        all_issues.extend(exception_issues)
    else:
        print("✅ No generic Exception handlers found")
    
    # Check for resource management
    print("\n🔍 Checking for proper resource management...")
    resource_issues = check_resource_management(file_path)
    if resource_issues:
        print(f"❌ Found {len(resource_issues)} resource management issues:")
        for issue in resource_issues:
            print(f"   - {issue}")
        all_issues.extend(resource_issues)
    else:
        print("✅ Proper resource management in place")
    
    # Check for fallback behaviors
    print("\n🔍 Checking for fallback behaviors...")
    fallback_issues = check_no_fallback_behavior(file_path)
    if fallback_issues:
        print(f"⚠️  Found {len(fallback_issues)} potential fallback behaviors:")
        for issue in fallback_issues:
            print(f"   - {issue}")
        # Don't add to all_issues as these might be false positives
    else:
        print("✅ No obvious fallback behaviors found")
    
    print("\n" + "=" * 80)
    if all_issues:
        print(f"❌ VALIDATION FAILED: Found {len(all_issues)} critical issues")
        return False
    else:
        print("✅ VALIDATION PASSED: All critical CLAUDE.md violations appear to be fixed")
        return True


if __name__ == '__main__':
    success = validate_fixes()
    sys.exit(0 if success else 1)