#!/bin/bash
#
# Comprehensive linting script that runs ruff, black, and mypy on all code including tests.
#

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to run a command and report results
run_command() {
    local cmd="$1"
    local description="$2"
    
    echo -e "${BLUE}Running ${description}...${NC}"
    
    if $cmd; then
        echo -e "${GREEN}✅ ${description} passed${NC}"
        return 0
    else
        echo -e "${RED}❌ ${description} failed${NC}"
        return 1
    fi
}

# Main function
main() {
    echo -e "${BLUE}🔍 Running comprehensive linting...${NC}"
    
    # Define paths to lint
    local src_path="src"
    local tests_path="tests"
    
    # Check if paths exist
    if [[ ! -d "$src_path" ]]; then
        echo -e "${RED}❌ Source path $src_path not found${NC}"
        exit 1
    fi
    
    if [[ ! -d "$tests_path" ]]; then
        echo -e "${RED}❌ Tests path $tests_path not found${NC}"
        exit 1
    fi
    
    local all_passed=true
    
    # Run ruff check
    if ! run_command "ruff check $src_path $tests_path" "ruff check"; then
        all_passed=false
    fi
    
    # Run black check
    if ! run_command "black --check $src_path $tests_path" "black check"; then
        all_passed=false
    fi
    
    # Run mypy with explicit package bases (moderate strictness)
    if ! run_command "mypy --explicit-package-bases --check-untyped-defs $src_path $tests_path" "mypy type check"; then
        all_passed=false
    fi
    
    if $all_passed; then
        echo -e "${GREEN}🎉 All linting checks passed!${NC}"
        exit 0
    else
        echo -e "${RED}💥 Some linting checks failed${NC}"
        exit 1
    fi
}

# Run main function
main "$@"