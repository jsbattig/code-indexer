#!/usr/bin/env python3
"""
Debug Java regex patterns.
"""

import re

def test_java_regex():
    error_text = """package com.example;

public class ValidClass {
    private String name;

    public ValidClass(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}

public class BrokenClass {
    private String value;

    public BrokenClass(String value) {
        this.value = value;
    // Missing closing brace

public class AnotherClass {
    private int id;

    public int getId() {
        return id;
    }
}"""
    
    patterns = {
        "class": r"^\s*(?:public|private|protected|abstract|final|static\s+)*class\s+(\w+)",
        "interface": r"^\s*(?:public|private|protected\s+)*interface\s+(\w+)",
        "enum": r"^\s*(?:public|private|protected\s+)*enum\s+(\w+)",
        "method": r"^\s*(?:public|private|protected|static|final|abstract\s+)*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*(?:throws[^{]*)?{",
        "constructor": r"^\s*(?:public|private|protected\s+)*(\w+)\s*\([^)]*\)\s*(?:throws[^{]*)?{",
        "field": r"^\s*(?:public|private|protected|static|final\s+)*\w+(?:\[\])?\s+(\w+)\s*[=;]",
    }
    
    lines = error_text.split("\n")
    
    for line_idx, line in enumerate(lines):
        for construct_type, pattern in patterns.items():
            match = re.search(pattern, line)
            if match:
                print(f"Line {line_idx}: {repr(line)}")
                print(f"  -> Matches {construct_type}: {match.group(1)}")

if __name__ == "__main__":
    test_java_regex()