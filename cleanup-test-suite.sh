#!/bin/bash
#
# cleanup-test-suite.sh
# Comprehensive test suite cleanup including containers and collections
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🧹 Performing comprehensive test suite cleanup..."

# Use the test infrastructure cleanup which handles everything properly
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/tests')
sys.path.insert(0, '$SCRIPT_DIR/src')

try:
    from tests.test_infrastructure import TestSuiteCleanup
    # Full cleanup including containers, collections, and temp directories
    TestSuiteCleanup.cleanup_all_test_containers()
except Exception as e:
    print(f'⚠️ Test suite cleanup failed: {e}')
"

# Return success even if cleanup fails (best effort)
exit 0