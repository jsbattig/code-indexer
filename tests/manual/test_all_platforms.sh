#!/bin/bash

set -e

PASS=0
FAIL=0

test_platform() {
    local platform=$1
    local scope=$2
    local expected_file=$3
    
    echo ""
    echo "========================================="
    echo "Testing: $platform ($scope scope)"
    echo "========================================="
    
    # Backup if file exists
    if [ -f "$expected_file" ]; then
        cp "$expected_file" "$expected_file.backup.$$"
        echo "Backed up existing file"
    fi
    
    # Test 1: Create file (delete if exists)
    echo ""
    echo "Test 1: File creation"
    rm -f "$expected_file"
    
    if [ "$scope" = "project" ]; then
        cidx teach-ai --$platform --project
    else
        cidx teach-ai --$platform --global
    fi
    
    if [ -f "$expected_file" ]; then
        echo "✅ File created: $expected_file"
        PASS=$((PASS + 1))
    else
        echo "❌ File NOT created: $expected_file"
        FAIL=$((FAIL + 1))
        return 1
    fi
    
    # Check content
    if grep -q "CIDX" "$expected_file" && grep -q "semantic search" "$expected_file"; then
        echo "✅ File contains CIDX instructions"
        PASS=$((PASS + 1))
    else
        echo "❌ File missing CIDX instructions"
        FAIL=$((FAIL + 1))
    fi
    
    # Test 2: Update existing file
    echo ""
    echo "Test 2: File update (preserve custom content)"
    
    # Add custom content
    cat > "$expected_file" << 'CUSTOM'
# My Custom Instructions

## Project Rules
- Follow conventions
- Write tests

## Custom Section
Keep this content!

CUSTOM
    
    echo "Added custom content to file"
    
    if [ "$scope" = "project" ]; then
        cidx teach-ai --$platform --project
    else
        cidx teach-ai --$platform --global
    fi
    
    # Check custom content preserved
    if grep -q "My Custom Instructions" "$expected_file" && \
       grep -q "Custom Section" "$expected_file" && \
       grep -q "Keep this content" "$expected_file"; then
        echo "✅ Custom content preserved"
        PASS=$((PASS + 1))
    else
        echo "❌ Custom content NOT preserved"
        FAIL=$((FAIL + 1))
    fi
    
    # Check CIDX content added
    if grep -q "CIDX" "$expected_file" && grep -q "semantic search" "$expected_file"; then
        echo "✅ CIDX section added"
        PASS=$((PASS + 1))
    else
        echo "❌ CIDX section NOT added"
        FAIL=$((FAIL + 1))
    fi
    
    # Restore backup if existed
    if [ -f "$expected_file.backup.$$" ]; then
        mv "$expected_file.backup.$$" "$expected_file"
        echo "Restored original file"
    fi
    
    echo "✅ $platform ($scope) tests passed"
}

cd ~/.tmp/teach-ai-test

# Test 1: Claude - Project
test_platform "claude" "project" "$(pwd)/CLAUDE.md"

# Test 2: Claude - Global
test_platform "claude" "global" "$HOME/.claude/CLAUDE.md"

# Test 3: Codex - Project
test_platform "codex" "project" "$(pwd)/CODEX.md"

# Test 4: Codex - Global
test_platform "codex" "global" "$HOME/.codex/instructions.md"

# Test 5: Gemini - Project only
test_platform "gemini" "project" "$(pwd)/.gemini/styleguide.md"

# Test 6: OpenCode - Project
test_platform "opencode" "project" "$(pwd)/AGENTS.md"

# Test 7: OpenCode - Global
test_platform "opencode" "global" "$HOME/.config/opencode/AGENTS.md"

# Test 8: Q - Project
test_platform "q" "project" "$(pwd)/.amazonq/rules/cidx.md"

# Test 9: Q - Global
test_platform "q" "global" "$HOME/.aws/amazonq/Q.md"

# Test 10: Junie - Project only
test_platform "junie" "project" "$(pwd)/.junie/guidelines.md"

echo ""
echo "========================================="
echo "FINAL RESULTS"
echo "========================================="
echo "PASSED: $PASS"
echo "FAILED: $FAIL"
echo "========================================="

if [ $FAIL -gt 0 ]; then
    exit 1
fi
