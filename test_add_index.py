#!/usr/bin/env python3
"""
Test script to debug add index authentication issue using Playwright.
"""
import asyncio
from playwright.async_api import async_playwright
import json

async def test_add_index():
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Enable request/response logging
        page = await context.new_page()

        # Log all network requests
        async def log_request(request):
            print(f"\n→ REQUEST: {request.method} {request.url}")
            if request.method == "POST":
                try:
                    body = request.post_data
                    if body:
                        print(f"  Body: {body[:200]}")
                except:
                    pass
            headers = request.headers
            if 'cookie' in headers:
                print(f"  Cookies: {headers['cookie'][:100]}...")

        async def log_response(response):
            print(f"← RESPONSE: {response.status} {response.url}")
            # Log Set-Cookie headers
            headers = response.headers
            if 'set-cookie' in headers:
                print(f"  Set-Cookie: {headers['set-cookie']}")
            if response.status >= 400:
                try:
                    body = await response.text()
                    print(f"  Error body: {body[:500]}")
                except:
                    pass

        page.on("request", log_request)
        page.on("response", log_response)

        print("=" * 80)
        print("STEP 1: Navigate to login page")
        print("=" * 80)
        await page.goto("http://localhost:8090/login")
        await page.wait_for_load_state("networkidle")

        print("\n" + "=" * 80)
        print("STEP 2: Log in as admin")
        print("=" * 80)
        # Fill in login form
        await page.fill('input[name="username"]', "admin")
        await page.fill('input[name="password"]', "admin")
        await page.click('button[type="submit"]')

        # Wait for redirect after login
        await page.wait_for_url("http://localhost:8090/admin/**")
        print(f"✓ Logged in, redirected to: {page.url}")

        # Get cookies to verify session
        cookies = await context.cookies()
        print(f"\nAll cookies ({len(cookies)} total):")
        for c in cookies:
            print(f"  - {c['name']}: {c['value'][:30]}... (path={c.get('path')}, domain={c.get('domain')})")

        session_cookie = next((c for c in cookies if c['name'] == 'session'), None)
        if session_cookie:
            print(f"✓ Session cookie found: {session_cookie['value'][:30]}...")
            print(f"  Path: {session_cookie.get('path', 'NOT SET')}")
            print(f"  Domain: {session_cookie.get('domain', 'NOT SET')}")
        else:
            print("✗ No session cookie found!")

        print("\n" + "=" * 80)
        print("STEP 3: Navigate to golden repos page")
        print("=" * 80)
        await page.goto("http://localhost:8090/admin/golden-repos")
        await page.wait_for_load_state("networkidle")
        print(f"✓ On page: {page.url}")

        print("\n" + "=" * 80)
        print("STEP 4: Try to add an index")
        print("=" * 80)

        # Find a repo and try to add index
        # Wait for repos list to load
        await page.wait_for_selector(".repo-card", timeout=5000)

        # Click on first repo's "Add Index" button
        # First need to show the form
        add_index_button = page.locator('button:has-text("Add Index")').first
        if await add_index_button.count() > 0:
            print("✓ Found 'Add Index' button, clicking...")
            await add_index_button.click()
            await page.wait_for_timeout(500)

            # Select index type (semantic_fts)
            select = page.locator('select[id^="index-type-"]').first
            if await select.count() > 0:
                await select.select_option("semantic_fts")
                print("✓ Selected semantic_fts index type")

                # Click Submit button
                submit_button = page.locator('button:has-text("Submit")').first
                await submit_button.click()
                print("✓ Clicked Submit button")

                # Wait for the API call to complete
                await page.wait_for_timeout(2000)

                print("\n" + "=" * 80)
                print("RESULT: Check logs above for API response")
                print("=" * 80)
            else:
                print("✗ Could not find index type selector")
        else:
            print("✗ Could not find 'Add Index' button")

        # Keep browser open for a moment to see final state
        await page.wait_for_timeout(1000)

        print("\n" + "=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_add_index())
