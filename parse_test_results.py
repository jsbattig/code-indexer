#!/usr/bin/env python3
"""
Parse test results from full-automation.sh output and provide detailed summary.
"""

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


def parse_pytest_output(log_file: Path) -> Dict[str, any]:
    """Parse a pytest log file to extract test results and error details."""
    content = log_file.read_text()
    
    # Extract test results
    failed_tests = []
    error_details = []
    
    # Pattern to match failed test cases
    failed_pattern = re.compile(r'^FAILED (.*?) - (.*)$', re.MULTILINE)
    
    # Pattern to match test errors in verbose output
    error_section_pattern = re.compile(
        r'^_{10,} (.*?) _{10,}$(.*?)^(?:_{10,}|=+\s+\d+)', 
        re.MULTILINE | re.DOTALL
    )
    
    # Find all failed tests
    for match in failed_pattern.finditer(content):
        test_name = match.group(1)
        error_summary = match.group(2)
        failed_tests.append({
            'test': test_name,
            'error_summary': error_summary
        })
    
    # Find detailed error sections
    for match in error_section_pattern.finditer(content):
        test_name = match.group(1).strip()
        error_body = match.group(2).strip()
        
        # Extract the most relevant error info
        error_lines = error_body.split('\n')
        # Look for assertion errors, exceptions, etc.
        relevant_error = []
        for line in error_lines:
            if any(keyword in line for keyword in ['AssertionError', 'Exception', 'Error:', 'assert', 'FAILED']):
                relevant_error.append(line.strip())
        
        if relevant_error:
            error_details.append({
                'test': test_name,
                'details': '\n'.join(relevant_error[:5])  # Limit to 5 most relevant lines
            })
    
    # Extract summary stats if present
    summary_match = re.search(r'=+ (\d+) failed.*?(\d+) passed.*?in ([\d.]+)s', content)
    if summary_match:
        stats = {
            'failed': int(summary_match.group(1)),
            'passed': int(summary_match.group(2)),
            'duration': float(summary_match.group(3))
        }
    else:
        stats = None
    
    return {
        'failed_tests': failed_tests,
        'error_details': error_details,
        'stats': stats
    }


def analyze_test_directory(test_dir: Path) -> None:
    """Analyze all test results in the given directory."""
    
    # Load JSON summary
    summary_file = test_dir / "test_summary.json"
    if summary_file.exists():
        with open(summary_file) as f:
            summary = json.load(f)
    else:
        print(f"❌ Summary file not found: {summary_file}")
        return
    
    test_run = summary['test_run']
    failed_files = [r for r in test_run['test_results'] if r['status'] == 'failed']
    
    if not failed_files:
        print("\n✅ All tests passed!")
        print(f"   Total: {test_run['total_files']} test files")
        print(f"   Duration: {test_run.get('duration', 'N/A')}")
        return
    
    print("\n" + "="*80)
    print("📊 DETAILED TEST FAILURE REPORT")
    print("="*80)
    
    print(f"\n📈 Overall Statistics:")
    print(f"   Total test files: {test_run['total_files']}")
    print(f"   Passed: {test_run['passed_count']}")
    print(f"   Failed: {test_run['failed_count']}")
    print(f"   Success rate: {test_run['passed_count']/test_run['total_files']*100:.1f}%")
    
    # Group failures by error type
    error_categories = defaultdict(list)
    
    print(f"\n❌ Failed Test Files ({len(failed_files)}):")
    for i, failed in enumerate(failed_files, 1):
        print(f"   {i}. {failed['name']}")
        
        # Parse individual log file
        log_file = test_dir / f"{failed['name']}.log"
        if log_file.exists():
            results = parse_pytest_output(log_file)
            
            # Categorize errors
            for test_failure in results['failed_tests']:
                error_type = test_failure['error_summary'].split(':')[0].strip()
                error_categories[error_type].append({
                    'file': failed['name'],
                    'test': test_failure['test'],
                    'error': test_failure['error_summary']
                })
    
    # Display errors by category
    print(f"\n🔍 Errors by Type:")
    for error_type, failures in sorted(error_categories.items()):
        print(f"\n   {error_type} ({len(failures)} occurrences):")
        
        # Group by test file
        by_file = defaultdict(list)
        for failure in failures:
            by_file[failure['file']].append(failure)
        
        for file_name, file_failures in by_file.items():
            print(f"      📁 {file_name}:")
            for f in file_failures[:3]:  # Show max 3 per file
                test_method = f['test'].split('::')[-1] if '::' in f['test'] else f['test']
                print(f"         • {test_method}")
                if len(f['error']) > 100:
                    print(f"           {f['error'][:100]}...")
                else:
                    print(f"           {f['error']}")
            if len(file_failures) > 3:
                print(f"         ... and {len(file_failures) - 3} more")
    
    # Common error patterns
    print(f"\n📋 Common Error Patterns:")
    
    error_patterns = {
        'Container/Service Issues': ['container', 'docker', 'podman', 'qdrant', 'ollama', 'timeout', 'connection'],
        'API Key Issues': ['API key', 'VOYAGE_API_KEY', 'authentication', 'Invalid.*key'],
        'File/Permission Issues': ['Permission denied', 'No such file', 'FileNotFoundError'],
        'Assertion Failures': ['AssertionError', 'assert.*==', 'assert.*in'],
        'Import/Module Issues': ['ImportError', 'ModuleNotFoundError', 'No module named'],
        'Type Errors': ['TypeError', 'type.*expected', 'invalid type'],
    }
    
    pattern_counts = defaultdict(int)
    for category, patterns in error_patterns.items():
        count = 0
        for error_type, failures in error_categories.items():
            for failure in failures:
                if any(re.search(p, failure['error'], re.IGNORECASE) for p in patterns):
                    count += 1
                    break
        if count > 0:
            pattern_counts[category] = count
    
    for category, count in sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"   • {category}: {count} failures")
    
    # Recommendations
    print(f"\n💡 Recommendations:")
    
    if 'Container/Service Issues' in pattern_counts:
        print("   • Check if Docker/Podman services are running properly")
        print("   • Verify container health and readiness checks")
        print("   • Consider increasing timeout values for slow systems")
    
    if 'API Key Issues' in pattern_counts:
        print("   • Ensure VOYAGE_API_KEY is set in .env.local")
        print("   • Verify API key is valid and has proper permissions")
        print("   • Check environment variable loading in test setup")
    
    if 'File/Permission Issues' in pattern_counts:
        print("   • Check file permissions in test directories")
        print("   • Ensure test cleanup is working properly")
        print("   • Verify Docker/Podman volume mount permissions")
    
    print("\n" + "="*80)
    print(f"📁 Full logs available in: {test_dir}")
    print("="*80)


def main():
    if len(sys.argv) != 2:
        print("Usage: python parse_test_results.py <test_output_directory>")
        sys.exit(1)
    
    test_dir = Path(sys.argv[1])
    if not test_dir.exists():
        print(f"Error: Directory {test_dir} does not exist")
        sys.exit(1)
    
    analyze_test_directory(test_dir)


if __name__ == "__main__":
    main()