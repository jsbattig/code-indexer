#!/usr/bin/env python3
"""Simple test script for VoyageAI API direct connection."""

import os
import sys
import json
import time
import httpx


def test_voyage_api():
    """Test direct VoyageAI API connection."""
    
    # Check for API key
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        print("❌ ERROR: VOYAGE_API_KEY environment variable not set")
        print("   Set it with: export VOYAGE_API_KEY=your_api_key_here")
        return False
    
    print(f"✅ Found VOYAGE_API_KEY: {api_key[:8]}...{api_key[-4:]}")
    
    # API configuration
    api_endpoint = "https://api.voyageai.com/v1/embeddings"
    model = "voyage-code-3"
    test_text = "Hello, this is a simple test of the VoyageAI embedding API."
    
    print(f"\n📡 Testing VoyageAI API:")
    print(f"   Endpoint: {api_endpoint}")
    print(f"   Model: {model}")
    print(f"   Test text: '{test_text}'")
    
    # Prepare request
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "input": [test_text],
        "model": model
    }
    
    print("\n🔄 Sending request...")
    start_time = time.time()
    
    try:
        # Make request with timeout
        with httpx.Client(timeout=30.0) as client:
            response = client.post(api_endpoint, headers=headers, json=payload)
        
        elapsed_time = time.time() - start_time
        print(f"⏱️  Request completed in {elapsed_time:.2f} seconds")
        
        # Check status
        print(f"\n📊 Response status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Success!")
            
            # Parse response
            result = response.json()
            
            # Display response structure
            print("\n📋 Response structure:")
            print(f"   Keys: {list(result.keys())}")
            
            if "data" in result and result["data"]:
                embedding_data = result["data"][0]
                embedding = embedding_data.get("embedding", [])
                print(f"   Embedding dimensions: {len(embedding)}")
                print(f"   First 5 values: {embedding[:5]}")
                
                # Display usage info if available
                if "usage" in result:
                    usage = result["usage"]
                    print(f"\n💰 Token usage:")
                    for key, value in usage.items():
                        print(f"   {key}: {value}")
            
            print("\n✅ VoyageAI API is working correctly!")
            return True
            
        else:
            print(f"❌ Error: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            
            # Parse error details if possible
            try:
                error_data = response.json()
                if "error" in error_data:
                    print(f"\n📌 Error details:")
                    error = error_data["error"]
                    if isinstance(error, dict):
                        for key, value in error.items():
                            print(f"   {key}: {value}")
                    else:
                        print(f"   {error}")
            except:
                pass
            
            # Common error interpretations
            if response.status_code == 401:
                print("\n💡 This usually means the API key is invalid or expired.")
            elif response.status_code == 429:
                print("\n💡 Rate limit exceeded. Wait a bit and try again.")
            elif response.status_code == 400:
                print("\n💡 Bad request. Check the model name and request format.")
            
            return False
            
    except httpx.TimeoutException:
        print(f"❌ Request timed out after 30 seconds")
        print("💡 This might indicate network issues or server overload.")
        return False
        
    except httpx.ConnectError as e:
        print(f"❌ Connection error: {e}")
        print("💡 Check your internet connection and firewall settings.")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")
        return False


def test_batch_embeddings():
    """Test batch embedding functionality."""
    print("\n" + "="*60)
    print("🔬 Testing batch embeddings...")
    
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        print("❌ Skipping batch test - no API key")
        return False
    
    # Test with multiple texts
    test_texts = [
        "def hello_world():",
        "    print('Hello, World!')",
        "# This is a Python comment",
        "import numpy as np",
        "class MyClass:",
    ]
    
    api_endpoint = "https://api.voyageai.com/v1/embeddings"
    model = "voyage-code-3"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "input": test_texts,
        "model": model
    }
    
    print(f"📝 Sending {len(test_texts)} texts in batch...")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(api_endpoint, headers=headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            if "data" in result:
                print(f"✅ Received {len(result['data'])} embeddings")
                for i, item in enumerate(result["data"]):
                    embedding = item.get("embedding", [])
                    print(f"   Text {i+1}: {len(embedding)} dimensions")
                return True
        else:
            print(f"❌ Batch request failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Batch test error: {e}")
        return False


def main():
    """Run all tests."""
    print("🚀 VoyageAI API Direct Test")
    print("="*60)
    
    # Test basic connection
    success = test_voyage_api()
    
    # Test batch if basic test passed
    if success:
        test_batch_embeddings()
    
    print("\n" + "="*60)
    if success:
        print("✅ All tests completed successfully!")
    else:
        print("❌ Tests failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()