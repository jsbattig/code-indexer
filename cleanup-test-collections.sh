#!/bin/bash
#
# cleanup-test-collections.sh
# Shared script for cleaning up test collections and containers
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use the test infrastructure cleanup which properly handles dynamic ports
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/tests')
sys.path.insert(0, '$SCRIPT_DIR/src')

try:
    from tests.test_infrastructure import TestSuiteCleanup
    # Only cleanup collections, not containers (unless explicitly requested)
    TestSuiteCleanup._cleanup_test_collections()
except Exception as e:
    print(f'⚠️ Test collection cleanup failed: {e}')
"

# Return success even if cleanup fails (best effort)
exit 0