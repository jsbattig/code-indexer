#!/usr/bin/env python3
"""
Test script for JWT token refresh mechanism.
"""

import requests  # type: ignore[import-untyped]
import json
import sys


def test_jwt_refresh():
    base_url = "http://localhost:8001"

    print("🔐 Testing JWT Token Refresh Mechanism")
    print("=" * 50)

    # Step 1: Login to get initial token
    print("\n1️⃣ Step 1: Login to get initial token")
    login_data = {"username": "admin", "password": "admin"}

    try:
        login_response = requests.post(
            f"{base_url}/auth/login",
            headers={"Content-Type": "application/json"},
            data=json.dumps(login_data),
        )

        if login_response.status_code != 200:
            print(
                f"❌ Login failed: {login_response.status_code} - {login_response.text}"
            )
            return False

        login_result = login_response.json()
        initial_token = login_result["access_token"]
        print(f"✅ Login successful. Token: {initial_token[:50]}...")
        print(
            f"   User: {login_result['user']['username']} ({login_result['user']['role']})"
        )

    except Exception as e:
        print(f"❌ Login request failed: {str(e)}")
        return False

    # Step 2: Test token refresh endpoint
    print("\n2️⃣ Step 2: Test token refresh endpoint")

    try:
        refresh_response = requests.post(
            f"{base_url}/auth/refresh",
            headers={
                "Authorization": f"Bearer {initial_token}",
                "Content-Type": "application/json",
            },
        )

        if refresh_response.status_code != 200:
            print(
                f"❌ Token refresh failed: {refresh_response.status_code} - {refresh_response.text}"
            )
            return False

        refresh_result = refresh_response.json()
        refreshed_token = refresh_result["access_token"]
        print(f"✅ Token refresh successful. New token: {refreshed_token[:50]}...")
        print(
            f"   User: {refresh_result['user']['username']} ({refresh_result['user']['role']})"
        )

        # Verify tokens are different
        if initial_token == refreshed_token:
            print("⚠️  Warning: Refreshed token is identical to initial token")
        else:
            print("✅ Tokens are different (as expected)")

    except Exception as e:
        print(f"❌ Token refresh request failed: {str(e)}")
        return False

    # Step 3: Test refreshed token works with protected endpoint
    print("\n3️⃣ Step 3: Test refreshed token with protected endpoint")

    try:
        # Try to access a protected endpoint with the refreshed token
        repos_response = requests.get(
            f"{base_url}/api/repos",
            headers={
                "Authorization": f"Bearer {refreshed_token}",
                "Content-Type": "application/json",
            },
        )

        if repos_response.status_code == 200:
            print("✅ Refreshed token works with protected endpoints")
            repos_data = repos_response.json()
            print(f"   Repositories endpoint returned: {len(repos_data)} repositories")
        elif repos_response.status_code == 403:
            print("❌ Refreshed token rejected by protected endpoint (403 Forbidden)")
            print(f"   Response: {repos_response.text}")
            return False
        else:
            print(
                f"⚠️  Protected endpoint returned: {repos_response.status_code} - {repos_response.text}"
            )

    except Exception as e:
        print(f"❌ Protected endpoint test failed: {str(e)}")
        return False

    # Step 4: Test refresh without valid token
    print("\n4️⃣ Step 4: Test refresh with invalid token")

    try:
        invalid_refresh_response = requests.post(
            f"{base_url}/auth/refresh",
            headers={
                "Authorization": "Bearer invalid_token_here",
                "Content-Type": "application/json",
            },
        )

        if invalid_refresh_response.status_code == 401:
            print("✅ Invalid token properly rejected (401 Unauthorized)")
        else:
            print(
                f"⚠️  Expected 401 for invalid token, got: {invalid_refresh_response.status_code}"
            )

    except Exception as e:
        print(f"❌ Invalid token test failed: {str(e)}")
        return False

    print("\n🎉 JWT Token Refresh Mechanism Test Complete!")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = test_jwt_refresh()
    sys.exit(0 if success else 1)
