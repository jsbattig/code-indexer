#!/usr/bin/env python3
"""
Debug Java regex patterns in detail.
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
    
    class_pattern = r"^\s*(?:public|private|protected|abstract|final|static\s+)*class\s+(\w+)"
    
    lines = error_text.split("\n")
    
    print("All lines:")
    for i, line in enumerate(lines):
        print(f"{i:2}: {repr(line)}")
        
    print("\nTesting class pattern:")
    for line_idx, line in enumerate(lines):
        match = re.search(class_pattern, line)
        if match:
            print(f"Line {line_idx}: {repr(line)} -> Matches class: {match.group(1)}")
        elif "class" in line:
            print(f"Line {line_idx}: {repr(line)} -> Contains 'class' but doesn't match pattern")

if __name__ == "__main__":
    test_java_regex()