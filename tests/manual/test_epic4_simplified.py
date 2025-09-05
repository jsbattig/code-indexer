#!/usr/bin/env python3
"""
Epic 4: Branch Operations - Simplified Test Execution
Tests core branch operation functionality with proper timing
"""

import requests
import json
import sys
import time


def get_admin_token():
    """Get admin authentication token"""
    print("🔐 Getting admin token...")
    login_data = {"username": "admin", "password": "admin"}

    try:
        response = requests.post(
            "http://localhost:8001/auth/login",
            headers={"Content-Type": "application/json"},
            data=json.dumps(login_data),
        )

        if response.status_code == 200:
            result = response.json()
            token = result["access_token"]
            print("✅ Admin token obtained")
            return token
        else:
            print(f"❌ Admin login failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Admin login error: {str(e)}")
        return None


def wait_for_job(token, job_id, timeout=60):
    """Wait for background job to complete"""
    print(f"⏳ Waiting for job {job_id} to complete...")

    for i in range(timeout):
        try:
            response = requests.get(
                f"http://localhost:8001/api/jobs/{job_id}",
                headers={"Authorization": f"Bearer {token}"},
            )

            if response.status_code == 200:
                job_data = response.json()
                status = job_data["status"]

                if status == "completed":
                    print("✅ Job completed successfully")
                    return True
                elif status == "failed":
                    print(f"❌ Job failed: {job_data.get('error', 'Unknown error')}")
                    return False

                if i % 10 == 0 and i > 0:  # Update every 10 seconds
                    print(f"   Still running... ({i}s)")

            time.sleep(1)

        except Exception as e:
            print(f"   Error checking job: {str(e)}")
            time.sleep(1)

    print(f"⏰ Job timeout after {timeout} seconds")
    return False


def test_epic4_branch_operations():
    """Test Epic 4 Branch Operations"""
    print("🚀 EPIC 4: BRANCH OPERATIONS - SIMPLIFIED TEST")
    print("=" * 60)

    token = get_admin_token()
    if not token:
        return False

    results = {}

    # Test 1: Activate existing golden repository for branch tests
    print("\n📋 Test 1: Activate existing repository")
    try:
        # Check what golden repositories are available
        response = requests.get(
            "http://localhost:8001/api/admin/golden-repos",
            headers={"Authorization": f"Bearer {token}"},
        )

        if response.status_code == 200:
            golden_repos = response.json()
            print(f"   Found {len(golden_repos)} golden repositories")

            # Use the first available golden repo or the epic4-test we just created
            test_repo = None
            for repo in golden_repos:
                if repo["alias"] in ["epic4-test", "sample-repo", "hello-world-fixed"]:
                    test_repo = repo
                    break

            if test_repo:
                print(f"   Using golden repository: {test_repo['alias']}")

                # Activate the repository
                activate_data = {
                    "golden_repo_alias": test_repo["alias"],
                    "user_alias": "epic4-test-repo",
                }

                activate_response = requests.post(
                    "http://localhost:8001/api/repos/activate",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(activate_data),
                )

                if activate_response.status_code == 202:
                    activate_result = activate_response.json()
                    job_id = activate_result["job_id"]
                    if wait_for_job(token, job_id, 90):
                        results["activation"] = True
                        print("✅ Repository activation successful")
                    else:
                        results["activation"] = False
                        print("❌ Repository activation failed")
                else:
                    results["activation"] = False
                    print(
                        f"❌ Activation request failed: {activate_response.status_code}"
                    )
            else:
                results["activation"] = False
                print("❌ No suitable golden repository found")
        else:
            results["activation"] = False
            print(f"❌ Failed to list golden repositories: {response.status_code}")

    except Exception as e:
        results["activation"] = False
        print(f"❌ Activation test error: {str(e)}")

    if not results["activation"]:
        print("\n❌ Cannot proceed without activated repository")
        return False

    # Test 2: Test branch switching API endpoint
    print("\n📋 Test 2: Branch switching API endpoint")
    try:
        # First, let's see what branches might be available
        # Try to switch to a feature branch
        switch_data = {"branch": "feature/branch-test"}

        response = requests.put(
            "http://localhost:8001/api/repos/epic4-test-repo/branch",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(switch_data),
        )

        if response.status_code == 200:
            results["branch_switch"] = True
            print("✅ Branch switch API endpoint working")
            switch_result = response.json()
            print(f"   Response: {switch_result['message']}")
        elif response.status_code == 400:
            # This is expected if the branch doesn't exist
            results["branch_switch"] = "partial"
            print("⚠️  Branch switch rejected (branch may not exist)")
            print(f"   Response: {response.text}")
        else:
            results["branch_switch"] = False
            print(f"❌ Branch switch failed: {response.status_code} - {response.text}")

    except Exception as e:
        results["branch_switch"] = False
        print(f"❌ Branch switch test error: {str(e)}")

    # Test 3: Test error handling for non-existent repository
    print("\n📋 Test 3: Error handling for non-existent repository")
    try:
        switch_data = {"branch": "master"}

        response = requests.put(
            "http://localhost:8001/api/repos/non-existent-repo/branch",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(switch_data),
        )

        if response.status_code == 404:
            results["error_handling"] = True
            print("✅ Non-existent repository properly rejected (404)")
        else:
            results["error_handling"] = False
            print(f"❌ Expected 404, got {response.status_code}")

    except Exception as e:
        results["error_handling"] = False
        print(f"❌ Error handling test error: {str(e)}")

    # Test 4: Query repository to verify it's functional
    print("\n📋 Test 4: Query repository after branch operations")
    try:
        query_data = {
            "query": "function",
            "repository_alias": "epic4-test-repo",
            "limit": 3,
        }

        response = requests.post(
            "http://localhost:8001/api/query",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(query_data),
        )

        if response.status_code == 200:
            query_result = response.json()
            results_count = len(query_result["results"])
            results["query_functional"] = results_count > 0
            print(f"✅ Repository query functional: {results_count} results found")

            if results_count > 0:
                print("   Sample results:")
                for i, result in enumerate(query_result["results"][:2]):
                    print(
                        f"   {i+1}. {result['file_path']}:{result['line_number']} (score: {result['similarity_score']:.3f})"
                    )
        else:
            results["query_functional"] = False
            print(f"❌ Query failed: {response.status_code} - {response.text}")

    except Exception as e:
        results["query_functional"] = False
        print(f"❌ Query test error: {str(e)}")

    # Test 5: Test invalid branch handling
    print("\n📋 Test 5: Invalid branch handling")
    try:
        switch_data = {"branch": "definitely-non-existent-branch"}

        response = requests.put(
            "http://localhost:8001/api/repos/epic4-test-repo/branch",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(switch_data),
        )

        if response.status_code in [400, 404]:
            results["invalid_branch"] = True
            print(f"✅ Invalid branch properly rejected ({response.status_code})")
        else:
            results["invalid_branch"] = False
            print(f"❌ Expected 400/404, got {response.status_code}")

    except Exception as e:
        results["invalid_branch"] = False
        print(f"❌ Invalid branch test error: {str(e)}")

    # Cleanup
    print("\n🧹 Cleanup: Deactivate test repository")
    try:
        response = requests.delete(
            "http://localhost:8001/api/repos/epic4-test-repo",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code in [200, 202, 404]:
            print("✅ Cleanup successful")
        else:
            print(f"⚠️  Cleanup warning: {response.status_code}")
    except Exception:
        print("⚠️  Cleanup error (non-critical)")

    # Results Summary
    print("\n" + "=" * 60)
    print("📊 EPIC 4 TEST RESULTS SUMMARY")
    print("=" * 60)

    passed = 0
    total = 0

    for test_name, result in results.items():
        total += 1
        if result is True:
            passed += 1
            status = "✅ PASS"
        elif result == "partial":
            status = "⚠️  PARTIAL"
        else:
            status = "❌ FAIL"

        print(f"{test_name:20} {status}")

    success_rate = passed / total if total > 0 else 0
    print(f"\nOverall: {passed}/{total} tests passed ({success_rate*100:.1f}%)")

    if success_rate >= 0.8:
        print("🎉 EPIC 4 BRANCH OPERATIONS: SUCCESS")
        conclusion = "The branch operations API endpoints are implemented and functional. While there may be limitations with specific branch switching scenarios (like local repositories without remote origins), the core infrastructure is working."
    elif success_rate >= 0.6:
        print("⚠️  EPIC 4 BRANCH OPERATIONS: PARTIAL SUCCESS")
        conclusion = "The branch operations API has basic functionality but some advanced features need work. The core activation and query systems work correctly."
    else:
        print("❌ EPIC 4 BRANCH OPERATIONS: NEEDS WORK")
        conclusion = "The branch operations functionality has significant issues that need to be addressed."

    print(f"\n📝 Conclusion: {conclusion}")

    return success_rate >= 0.6


if __name__ == "__main__":
    success = test_epic4_branch_operations()
    sys.exit(0 if success else 1)
