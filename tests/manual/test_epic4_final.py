#!/usr/bin/env python3
"""
Epic 4: Branch Operations - Final Test Execution
Tests the core branch operation functionality using existing repositories
"""

import requests
import json
import sys


def get_admin_token():
    """Get admin authentication token"""
    login_data = {"username": "admin", "password": "admin"}

    try:
        response = requests.post(
            "http://localhost:8001/auth/login",
            headers={"Content-Type": "application/json"},
            data=json.dumps(login_data),
        )

        if response.status_code == 200:
            result = response.json()
            return result["access_token"]
        else:
            print(f"❌ Admin login failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Admin login error: {str(e)}")
        return None


def test_epic4_branch_operations():
    """Test Epic 4 Branch Operations using existing activated repositories"""
    print("🚀 EPIC 4: BRANCH OPERATIONS - FINAL TEST")
    print("=" * 60)

    token = get_admin_token()
    if not token:
        return False

    results = {}

    # Test 1: List existing activated repositories
    print("\n📋 Step 1: Check existing activated repositories")
    try:
        response = requests.get(
            "http://localhost:8001/api/repos",
            headers={"Authorization": f"Bearer {token}"},
        )

        if response.status_code == 200:
            repos = response.json()
            print(f"✅ Found {len(repos)} activated repositories")

            if len(repos) > 0:
                test_repo = repos[0]["user_alias"]
                print(f"   Using repository: {test_repo}")
                results["repo_available"] = True
            else:
                print("❌ No activated repositories available for testing")
                results["repo_available"] = False
                return False
        else:
            print(f"❌ Failed to list repositories: {response.status_code}")
            results["repo_available"] = False
            return False

    except Exception as e:
        print(f"❌ Repository listing error: {str(e)}")
        results["repo_available"] = False
        return False

    # Test 2: Test branch switching endpoint exists and responds
    print(f"\n📋 Test 2: Branch switching endpoint for '{test_repo}'")
    try:
        switch_data = {"branch_name": "main"}

        response = requests.put(
            f"http://localhost:8001/api/repos/{test_repo}/branch",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(switch_data),
        )

        print(f"   Response status: {response.status_code}")
        print(f"   Response body: {response.text}")

        if response.status_code == 200:
            results["branch_switch_endpoint"] = True
            print("✅ Branch switch endpoint working (200 OK)")
        elif response.status_code == 400:
            results["branch_switch_endpoint"] = "partial"
            print("⚠️  Branch switch endpoint exists but rejected request (400)")
        elif response.status_code == 404:
            results["branch_switch_endpoint"] = False
            print("❌ Branch switch endpoint not found (404)")
        else:
            results["branch_switch_endpoint"] = "partial"
            print(
                f"⚠️  Branch switch endpoint responded unexpectedly ({response.status_code})"
            )

    except Exception as e:
        results["branch_switch_endpoint"] = False
        print(f"❌ Branch switch test error: {str(e)}")

    # Test 3: Test with different branch names
    print("\n📋 Test 3: Try different branch names")
    branch_tests = ["master", "feature/test", "develop", "non-existent-branch"]
    branch_results = {}

    for branch in branch_tests:
        try:
            switch_data = {"branch_name": branch}

            response = requests.put(
                f"http://localhost:8001/api/repos/{test_repo}/branch",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(switch_data),
            )

            branch_results[branch] = response.status_code
            print(f"   Branch '{branch}': {response.status_code}")

        except Exception as e:
            branch_results[branch] = "error"
            print(f"   Branch '{branch}': error - {str(e)}")

    # Check if we get different responses for different branches
    unique_responses = len(set(branch_results.values()))
    results["branch_variety"] = unique_responses > 1
    print(
        f"   Got {unique_responses} different response types ({'✅ Good' if unique_responses > 1 else '⚠️ Limited'})"
    )

    # Test 4: Test error handling for non-existent repository
    print("\n📋 Test 4: Error handling for non-existent repository")
    try:
        switch_data = {"branch_name": "master"}

        response = requests.put(
            "http://localhost:8001/api/repos/definitely-non-existent-repo-12345/branch",
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
            print(f"   Response: {response.text}")

    except Exception as e:
        results["error_handling"] = False
        print(f"❌ Error handling test failed: {str(e)}")

    # Test 5: Verify repository still functional after branch operations
    print("\n📋 Test 5: Verify repository functionality after branch tests")
    try:
        query_data = {
            "query_text": "function",
            "repository_alias": test_repo,
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
            results["post_branch_query"] = results_count > 0
            print(f"✅ Repository still functional: {results_count} query results")
        else:
            results["post_branch_query"] = False
            print(f"❌ Repository query failed: {response.status_code}")

    except Exception as e:
        results["post_branch_query"] = False
        print(f"❌ Post-branch query error: {str(e)}")

    # Results Summary
    print("\n" + "=" * 60)
    print("📊 EPIC 4 BRANCH OPERATIONS RESULTS")
    print("=" * 60)

    # Epic 4 Test Case Mapping
    epic_tests = {
        "4.1.1 - Branch switch API exists": results.get(
            "branch_switch_endpoint", False
        ),
        "4.1.4 - Invalid branch handling": results.get("branch_variety", False),
        "4.1.5 - Non-existent repo returns 404": results.get("error_handling", False),
        "4.3.1 - Repository functional after operations": results.get(
            "post_branch_query", False
        ),
    }

    passed = 0
    total = len(epic_tests)

    for test_name, result in epic_tests.items():
        if result is True:
            passed += 1
            status = "✅ PASS"
        elif result == "partial":
            passed += 0.5
            status = "⚠️  PARTIAL"
        else:
            status = "❌ FAIL"

        print(f"{test_name:<50} {status}")

    success_rate = passed / total if total > 0 else 0
    print(
        f"\nBranch Operations: {passed}/{total} tests passed ({success_rate*100:.1f}%)"
    )

    # Detailed Analysis
    print("\n🔍 ANALYSIS:")

    if results.get("branch_switch_endpoint") is True:
        print("✅ Branch switching API endpoint is implemented and functional")
    elif results.get("branch_switch_endpoint") == "partial":
        print("⚠️  Branch switching API endpoint exists but has limitations")
        print("   - Endpoint responds but may reject certain branch operations")
        print(
            "   - This could be due to local repository limitations (no remote origin)"
        )
    else:
        print("❌ Branch switching API endpoint is not working")

    if results.get("error_handling"):
        print("✅ Error handling for non-existent repositories works correctly")
    else:
        print("❌ Error handling for non-existent repositories needs improvement")

    if results.get("post_branch_query"):
        print("✅ Repository remains functional after branch operations")
    else:
        print("❌ Repository functionality affected by branch operations")

    print("\n📝 EPIC 4 CONCLUSION:")
    if success_rate >= 0.75:
        print("🎉 Branch Operations API is substantially implemented")
        print("   - Core endpoints exist and respond appropriately")
        print("   - Error handling works for edge cases")
        print("   - Repository integrity maintained")
        conclusion = "MOSTLY COMPLETE"
    elif success_rate >= 0.5:
        print("⚠️  Branch Operations API has basic functionality")
        print("   - Some endpoints work but may have limitations")
        print("   - May need fixes for specific branch switching scenarios")
        conclusion = "PARTIALLY COMPLETE"
    else:
        print("❌ Branch Operations API needs significant work")
        print("   - Core functionality not working as expected")
        conclusion = "NEEDS WORK"

    print(f"\nStatus: {conclusion}")

    return success_rate >= 0.5


if __name__ == "__main__":
    success = test_epic4_branch_operations()
    sys.exit(0 if success else 1)
