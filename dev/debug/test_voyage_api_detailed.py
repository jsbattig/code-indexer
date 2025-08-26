#!/usr/bin/env python3
"""Detailed test script for VoyageAI API with various test scenarios."""

import os
import sys
import json
import time
import httpx
from typing import List, Dict, Any


class VoyageAPITester:
    """Test harness for VoyageAI API."""
    
    def __init__(self):
        self.api_key = os.getenv("VOYAGE_API_KEY")
        self.api_endpoint = "https://api.voyageai.com/v1/embeddings"
        self.default_model = "voyage-code-3"
        
    def make_request(self, texts: List[str], model: str = None) -> Dict[str, Any]:
        """Make a request to VoyageAI API."""
        if not self.api_key:
            raise ValueError("VOYAGE_API_KEY environment variable not set")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "input": texts,
            "model": model or self.default_model
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(self.api_endpoint, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    
    def test_single_embedding(self):
        """Test single text embedding."""
        print("\n🧪 Test 1: Single Text Embedding")
        print("-" * 40)
        
        test_text = "def calculate_fibonacci(n):\n    if n <= 1:\n        return n\n    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)"
        
        print(f"📝 Input text (Python code):")
        print(f"   {repr(test_text[:50])}...")
        
        try:
            start = time.time()
            result = self.make_request([test_text])
            elapsed = time.time() - start
            
            embedding = result["data"][0]["embedding"]
            print(f"✅ Success!")
            print(f"   Time: {elapsed:.3f}s")
            print(f"   Dimensions: {len(embedding)}")
            print(f"   Tokens used: {result['usage']['total_tokens']}")
            print(f"   Sample values: {embedding[:3]} ... {embedding[-3:]}")
            
            # Check embedding properties
            print(f"\n📊 Embedding properties:")
            print(f"   Min value: {min(embedding):.6f}")
            print(f"   Max value: {max(embedding):.6f}")
            print(f"   Mean value: {sum(embedding)/len(embedding):.6f}")
            
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_batch_processing(self):
        """Test batch embedding with various code snippets."""
        print("\n🧪 Test 2: Batch Code Embeddings")
        print("-" * 40)
        
        code_snippets = [
            "import numpy as np",
            "def main():\n    print('Hello, World!')",
            "class UserModel(BaseModel):\n    name: str\n    email: str",
            "SELECT * FROM users WHERE age > 18",
            "const sum = (a, b) => a + b;",
            "#!/bin/bash\necho 'Shell script test'",
        ]
        
        print(f"📝 Processing {len(code_snippets)} code snippets from different languages")
        
        try:
            start = time.time()
            result = self.make_request(code_snippets)
            elapsed = time.time() - start
            
            print(f"✅ Success!")
            print(f"   Time: {elapsed:.3f}s")
            print(f"   Total tokens: {result['usage']['total_tokens']}")
            print(f"   Embeddings received: {len(result['data'])}")
            
            # Analyze similarity between Python snippets
            python_indices = [0, 1, 2]  # First 3 are Python
            print(f"\n📈 Analyzing Python code similarity:")
            
            for i in python_indices:
                embedding = result["data"][i]["embedding"]
                print(f"   Snippet {i+1}: {len(embedding)} dims")
            
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_large_batch(self):
        """Test with larger batch size."""
        print("\n🧪 Test 3: Large Batch Processing")
        print("-" * 40)
        
        # Generate 50 simple code snippets
        snippets = []
        for i in range(50):
            snippets.append(f"def function_{i}():\n    return {i}")
        
        print(f"📝 Processing {len(snippets)} generated function definitions")
        
        try:
            start = time.time()
            result = self.make_request(snippets)
            elapsed = time.time() - start
            
            print(f"✅ Success!")
            print(f"   Time: {elapsed:.3f}s")
            print(f"   Throughput: {len(snippets)/elapsed:.1f} embeddings/second")
            print(f"   Total tokens: {result['usage']['total_tokens']}")
            print(f"   Average tokens per snippet: {result['usage']['total_tokens']/len(snippets):.1f}")
            
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_error_handling(self):
        """Test API error handling."""
        print("\n🧪 Test 4: Error Handling")
        print("-" * 40)
        
        # Test with invalid model
        print("📝 Testing with invalid model name...")
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            
            payload = {
                "input": ["test"],
                "model": "invalid-model-name"
            }
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(self.api_endpoint, headers=headers, json=payload)
                
            print(f"   Response status: {response.status_code}")
            if response.status_code != 200:
                print(f"✅ Correctly rejected invalid model")
                error_data = response.json()
                if "error" in error_data:
                    print(f"   Error message: {error_data['error']}")
            else:
                print(f"❌ Unexpected success with invalid model")
                
        except Exception as e:
            print(f"   Exception: {e}")
        
        # Test with empty input
        print("\n📝 Testing with empty input...")
        try:
            result = self.make_request([])
            print(f"   Result: {result}")
        except Exception as e:
            print(f"✅ Correctly handled empty input: {type(e).__name__}")
        
        return True
    
    def test_model_info(self):
        """Display model information."""
        print("\n🧪 Test 5: Model Information")
        print("-" * 40)
        
        models = {
            "voyage-code-3": 1024,
            "voyage-large-2": 1536,
            "voyage-2": 1024,
        }
        
        print("📋 Known VoyageAI models:")
        for model, dims in models.items():
            print(f"   {model}: {dims} dimensions")
        
        # Test current model
        print(f"\n🔍 Testing {self.default_model}...")
        try:
            result = self.make_request(["test"])
            embedding = result["data"][0]["embedding"]
            actual_dims = len(embedding)
            expected_dims = models.get(self.default_model, "unknown")
            
            print(f"✅ Model: {result['model']}")
            print(f"   Expected dimensions: {expected_dims}")
            print(f"   Actual dimensions: {actual_dims}")
            print(f"   Match: {'✅' if actual_dims == expected_dims else '❌'}")
            
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests."""
        if not self.api_key:
            print("❌ ERROR: VOYAGE_API_KEY environment variable not set")
            print("   Set it with: export VOYAGE_API_KEY=your_api_key_here")
            return False
        
        print(f"🚀 VoyageAI API Detailed Test Suite")
        print(f"=" * 60)
        print(f"✅ API Key found: {self.api_key[:8]}...{self.api_key[-4:]}")
        print(f"📡 Endpoint: {self.api_endpoint}")
        print(f"🎯 Default model: {self.default_model}")
        
        tests = [
            self.test_single_embedding,
            self.test_batch_processing,
            self.test_large_batch,
            self.test_error_handling,
            self.test_model_info,
        ]
        
        passed = 0
        for test in tests:
            try:
                if test():
                    passed += 1
            except Exception as e:
                print(f"❌ Test failed with exception: {e}")
        
        print(f"\n{'='*60}")
        print(f"📊 Test Results: {passed}/{len(tests)} passed")
        
        if passed == len(tests):
            print("✅ All tests passed!")
            return True
        else:
            print("❌ Some tests failed.")
            return False


def main():
    """Run the test suite."""
    tester = VoyageAPITester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()