#!/usr/bin/env python3
"""
Debug Java regex patterns step by step.
"""

import re

def test_java_regex():
    test_line = "public class ValidClass {"
    
    # Try progressively simpler patterns
    patterns = [
        r"^\s*(?:(?:public|private|protected|abstract|final|static)\s+)*class\s+(\w+)",
        r"^\s*(?:public\s+)*class\s+(\w+)",
        r"^\s*public\s+class\s+(\w+)",
        r"^public\s+class\s+(\w+)",
        r"public\s+class\s+(\w+)",
        r"class\s+(\w+)",
    ]
    
    print(f"Testing line: {repr(test_line)}")
    
    for i, pattern in enumerate(patterns):
        match = re.search(pattern, test_line)
        if match:
            print(f"Pattern {i}: {repr(pattern)} -> MATCHES: {match.group(1)}")
        else:
            print(f"Pattern {i}: {repr(pattern)} -> NO MATCH")

if __name__ == "__main__":
    test_java_regex()