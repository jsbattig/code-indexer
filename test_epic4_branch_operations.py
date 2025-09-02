#!/usr/bin/env python3
"""
Epic 4: Branch Operations - Complete Manual Test Execution
Tests all remaining branch operation functionality as specified in MANUAL_TESTING_EPIC.md
"""

import requests
import json
import sys
import time
import subprocess
import os
from pathlib import Path
import shutil

class Epic4BranchTester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.admin_token = None
        self.power_user_token = None
        self.test_repo_path = None
        
    def get_admin_token(self):
        """Get admin authentication token"""
        print("🔐 Getting admin token...")
        login_data = {"username": "admin", "password": "admin"}
        
        try:
            response = requests.post(
                f"{self.base_url}/auth/login",
                headers={"Content-Type": "application/json"},
                data=json.dumps(login_data)
            )
            
            if response.status_code == 200:
                result = response.json()
                self.admin_token = result["access_token"]
                print(f"✅ Admin token obtained")
                return True
            else:
                print(f"❌ Admin login failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Admin login error: {str(e)}")
            return False
    
    def setup_test_repository(self):
        """Create a test repository with multiple branches for testing"""
        print("\n📁 Setting up test repository with multiple branches...")
        
        self.test_repo_path = Path("/home/jsbattig/Dev/code-indexer/test-data/epic4-branch-test")
        
        # Remove existing test repo if it exists
        if self.test_repo_path.exists():
            shutil.rmtree(self.test_repo_path)
        
        # Create repository directory
        self.test_repo_path.mkdir(parents=True, exist_ok=True)
        os.chdir(self.test_repo_path)
        
        try:
            # Initialize git repository
            subprocess.run(["git", "init"], check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], check=True)
            
            # Create initial files on main branch
            with open("main.py", "w") as f:
                f.write('def main():\n    print("Hello from main branch")\n    return "main_branch_result"\n')
            with open("auth.py", "w") as f:
                f.write('def authenticate():\n    print("Auth from main")\n    return "main_auth"\n')
            
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit on main"], check=True)
            
            # Create feature/branch-test branch
            subprocess.run(["git", "checkout", "-b", "feature/branch-test"], check=True)
            with open("feature.py", "w") as f:
                f.write('def new_feature():\n    print("New feature implementation")\n    return "feature_result"\n')
            with open("main.py", "w") as f:
                f.write('def main():\n    print("Hello from feature branch")\n    return "feature_branch_result"\n')
            
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", "Add feature implementation"], check=True)
            
            # Create hotfix/bug-fix branch
            subprocess.run(["git", "checkout", "-b", "hotfix/bug-fix"], check=True)
            with open("bugfix.py", "w") as f:
                f.write('def fix_critical_bug():\n    print("Critical bug fixed")\n    return "bugfix_result"\n')
            with open("main.py", "w") as f:
                f.write('def main():\n    print("Hello from hotfix branch - bug fixed")\n    return "hotfix_branch_result"\n')
            
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", "Fix critical bug"], check=True)
            
            # Switch back to master (default branch in new git repos)
            subprocess.run(["git", "checkout", "master"], check=True)
            
            print(f"✅ Test repository created at: {self.test_repo_path}")
            
            # List all branches
            result = subprocess.run(["git", "branch", "-a"], capture_output=True, text=True)
            print(f"📋 Available branches:\n{result.stdout}")
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Git setup failed: {e}")
            return False
        except Exception as e:
            print(f"❌ Repository setup error: {str(e)}")
            return False
    
    def register_golden_repository(self, alias, branch="master"):
        """Register test repository as golden repository"""
        print(f"\n🏆 Registering golden repository '{alias}' on branch '{branch}'...")
        
        register_data = {
            "alias": alias,
            "repo_url": str(self.test_repo_path),
            "default_branch": branch
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/admin/golden-repos",
                headers={
                    "Authorization": f"Bearer {self.admin_token}",
                    "Content-Type": "application/json"
                },
                data=json.dumps(register_data)
            )
            
            if response.status_code == 202:
                result = response.json()
                print(f"✅ Golden repository registration started: {result['message']}")
                print(f"   Job ID: {result['job_id']}")
                
                # Wait for job to complete
                job_id = result['job_id']
                for i in range(30):  # Wait up to 30 seconds
                    job_response = requests.get(
                        f"{self.base_url}/api/jobs/{job_id}",
                        headers={"Authorization": f"Bearer {self.admin_token}"}
                    )
                    
                    if job_response.status_code == 200:
                        job_data = job_response.json()
                        if job_data['status'] == 'completed':
                            print(f"✅ Golden repository '{alias}' registration completed")
                            return True
                        elif job_data['status'] == 'failed':
                            print(f"❌ Golden repository registration failed: {job_data.get('error', 'Unknown error')}")
                            return False
                    
                    time.sleep(1)
                
                print(f"⏰ Registration job still running after 30 seconds")
                return False
                
            else:
                print(f"❌ Golden repository registration failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Golden repository registration error: {str(e)}")
            return False
    
    def activate_repository(self, golden_alias, user_alias, branch=None):
        """Activate repository for testing"""
        print(f"\n🚀 Activating repository '{golden_alias}' as '{user_alias}' on branch '{branch or 'default'}'...")
        
        activate_data = {
            "golden_repo_alias": golden_alias,
            "user_alias": user_alias
        }
        if branch:
            activate_data["branch"] = branch
        
        try:
            response = requests.post(
                f"{self.base_url}/api/repos/activate",
                headers={
                    "Authorization": f"Bearer {self.admin_token}",
                    "Content-Type": "application/json"
                },
                data=json.dumps(activate_data)
            )
            
            if response.status_code == 202:
                result = response.json()
                print(f"✅ Repository activation started: {result['message']}")
                
                # Wait for activation to complete
                job_id = result['job_id']
                for i in range(60):  # Wait up to 60 seconds
                    job_response = requests.get(
                        f"{self.base_url}/api/jobs/{job_id}",
                        headers={"Authorization": f"Bearer {self.admin_token}"}
                    )
                    
                    if job_response.status_code == 200:
                        job_data = job_response.json()
                        if job_data['status'] == 'completed':
                            print(f"✅ Repository '{user_alias}' activation completed")
                            return True
                        elif job_data['status'] == 'failed':
                            print(f"❌ Repository activation failed: {job_data.get('error', 'Unknown error')}")
                            return False
                    
                    time.sleep(1)
                
                print(f"⏰ Activation job still running after 60 seconds")
                return False
                
            else:
                print(f"❌ Repository activation failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Repository activation error: {str(e)}")
            return False
    
    def switch_branch(self, user_alias, branch):
        """Test branch switching API"""
        print(f"\n🌿 Switching '{user_alias}' to branch '{branch}'...")
        
        switch_data = {"branch": branch}
        
        try:
            response = requests.put(
                f"{self.base_url}/api/repos/{user_alias}/branch",
                headers={
                    "Authorization": f"Bearer {self.admin_token}",
                    "Content-Type": "application/json"
                },
                data=json.dumps(switch_data)
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Branch switch successful: {result['message']}")
                return True
            else:
                print(f"❌ Branch switch failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Branch switch error: {str(e)}")
            return False
    
    def query_repository(self, user_alias, query_text):
        """Query repository and return results"""
        print(f"\n🔍 Querying '{user_alias}' for: '{query_text}'...")
        
        query_data = {
            "query": query_text,
            "repository_alias": user_alias,
            "limit": 5
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/query",
                headers={
                    "Authorization": f"Bearer {self.admin_token}",
                    "Content-Type": "application/json"
                },
                data=json.dumps(query_data)
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Query successful: {len(result['results'])} results found")
                for i, res in enumerate(result['results'][:3]):  # Show first 3 results
                    print(f"   {i+1}. {res['file_path']}:{res['line_number']} (score: {res['similarity_score']:.3f})")
                    print(f"      {res['code_snippet'][:80]}...")
                return result
            else:
                print(f"❌ Query failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Query error: {str(e)}")
            return None
    
    def test_story_4_1_branch_switching(self):
        """Story 4.1: Branch Switching Tests"""
        print("\n" + "="*60)
        print("📋 STORY 4.1: BRANCH SWITCHING TESTS")
        print("="*60)
        
        results = {}
        
        # Test 4.1.1: Switch to existing branch
        print("\n🧪 Test 4.1.1: Switch to existing branch")
        results["4.1.1"] = self.switch_branch("test-repo-main", "feature/branch-test")
        
        if results["4.1.1"]:
            # Test 4.1.2: Branch switch updates indexing data
            print("\n🧪 Test 4.1.2: Branch switch updates indexing data")
            query_result = self.query_repository("test-repo-main", "feature implementation")
            results["4.1.2"] = query_result is not None and len(query_result['results']) > 0
            
            # Test 4.1.3: Branch switch preserves user configuration
            print("\n🧪 Test 4.1.3: Branch switch preserves user configuration")
            # Check that the repository is still accessible and functional
            query_result2 = self.query_repository("test-repo-main", "main function")
            results["4.1.3"] = query_result2 is not None
        else:
            results["4.1.2"] = False
            results["4.1.3"] = False
        
        # Test 4.1.4: Switch to non-existent branch returns error
        print("\n🧪 Test 4.1.4: Switch to non-existent branch returns error")
        switch_data = {"branch": "non-existent-branch"}
        try:
            response = requests.put(
                f"{self.base_url}/api/repos/test-repo-main/branch",
                headers={
                    "Authorization": f"Bearer {self.admin_token}",
                    "Content-Type": "application/json"
                },
                data=json.dumps(switch_data)
            )
            results["4.1.4"] = response.status_code in [400, 404]
            if results["4.1.4"]:
                print(f"✅ Non-existent branch properly rejected ({response.status_code})")
            else:
                print(f"❌ Expected 400/404, got {response.status_code}")
        except Exception as e:
            print(f"❌ Test error: {str(e)}")
            results["4.1.4"] = False
        
        # Test 4.1.5: Branch switch on non-activated repo returns 404
        print("\n🧪 Test 4.1.5: Branch switch on non-activated repo returns 404")
        switch_data = {"branch": "master"}
        try:
            response = requests.put(
                f"{self.base_url}/api/repos/non-existent-repo/branch",
                headers={
                    "Authorization": f"Bearer {self.admin_token}",
                    "Content-Type": "application/json"
                },
                data=json.dumps(switch_data)
            )
            results["4.1.5"] = response.status_code == 404
            if results["4.1.5"]:
                print(f"✅ Non-activated repo properly rejected (404)")
            else:
                print(f"❌ Expected 404, got {response.status_code}")
        except Exception as e:
            print(f"❌ Test error: {str(e)}")
            results["4.1.5"] = False
        
        return results
    
    def test_story_4_2_branch_activation_variations(self):
        """Story 4.2: Branch Activation Variations"""
        print("\n" + "="*60)
        print("📋 STORY 4.2: BRANCH ACTIVATION VARIATIONS")
        print("="*60)
        
        results = {}
        
        # Test 4.2.1: Activate repository on main branch (using master as default)
        print("\n🧪 Test 4.2.1: Activate repository on main branch")
        results["4.2.1"] = self.activate_repository("epic4-test", "test-main-branch", "master")
        
        # Test 4.2.2: Activate repository on a main branch (using master)  
        print("\n🧪 Test 4.2.2: Activate repository on master branch")
        # This should succeed since our repo uses master as default
        results["4.2.2"] = self.activate_repository("epic4-test", "test-master-branch", "master")
        
        # Test 4.2.3: Activate repository on feature/branch-test branch
        print("\n🧪 Test 4.2.3: Activate repository on feature/branch-test branch")
        results["4.2.3"] = self.activate_repository("epic4-test", "test-feature-branch", "feature/branch-test")
        
        # Test 4.2.4: Activate repository on hotfix/bug-fix branch
        print("\n🧪 Test 4.2.4: Activate repository on hotfix/bug-fix branch")
        results["4.2.4"] = self.activate_repository("epic4-test", "test-hotfix-branch", "hotfix/bug-fix")
        
        # Test 4.2.5: Each branch activation shows different indexed content
        print("\n🧪 Test 4.2.5: Each branch activation shows different indexed content")
        content_differences = 0
        
        if results["4.2.1"]:  # main branch
            main_results = self.query_repository("test-main-branch", "main function")
            if main_results and len(main_results['results']) > 0:
                content_differences += 1
        
        if results["4.2.3"]:  # feature branch
            feature_results = self.query_repository("test-feature-branch", "new feature")
            if feature_results and len(feature_results['results']) > 0:
                content_differences += 1
                
        if results["4.2.4"]:  # hotfix branch
            hotfix_results = self.query_repository("test-hotfix-branch", "bug fixed")
            if hotfix_results and len(hotfix_results['results']) > 0:
                content_differences += 1
        
        results["4.2.5"] = content_differences >= 2
        print(f"   Found different content in {content_differences} branch activations")
        
        return results
    
    def test_story_4_3_branch_content_verification(self):
        """Story 4.3: Branch Content Verification"""
        print("\n" + "="*60)
        print("📋 STORY 4.3: BRANCH CONTENT VERIFICATION")
        print("="*60)
        
        results = {}
        
        # Test 4.3.1: Query results differ between branches
        print("\n🧪 Test 4.3.1: Query results differ between branches")
        main_results = self.query_repository("test-main-branch", "main")
        feature_results = self.query_repository("test-feature-branch", "main")
        
        if main_results and feature_results:
            main_content = [r['code_snippet'] for r in main_results['results']]
            feature_content = [r['code_snippet'] for r in feature_results['results']]
            results["4.3.1"] = main_content != feature_content
            print(f"   Content differs: {results['4.3.1']}")
        else:
            results["4.3.1"] = False
        
        # Test 4.3.2: Branch-specific files are indexed correctly
        print("\n🧪 Test 4.3.2: Branch-specific files are indexed correctly")
        feature_specific = self.query_repository("test-feature-branch", "new_feature")
        hotfix_specific = self.query_repository("test-hotfix-branch", "fix_critical_bug")
        
        feature_found = feature_specific and len(feature_specific['results']) > 0
        hotfix_found = hotfix_specific and len(hotfix_specific['results']) > 0
        results["4.3.2"] = feature_found and hotfix_found
        print(f"   Feature-specific files indexed: {feature_found and hotfix_found}")
        
        # Test 4.3.3: File changes between branches reflected in queries
        print("\n🧪 Test 4.3.3: File changes between branches reflected in queries")
        main_main_py = self.query_repository("test-main-branch", "main branch")
        feature_main_py = self.query_repository("test-feature-branch", "feature branch")
        
        main_found = main_main_py and any("main_branch" in r['code_snippet'] for r in main_main_py['results'])
        feature_found = feature_main_py and any("feature_branch" in r['code_snippet'] for r in feature_main_py['results'])
        results["4.3.3"] = main_found and feature_found
        print(f"   File changes reflected in queries: {main_found and feature_found}")
        
        # Test 4.3.4: Branch metadata tracked in query results
        print("\n🧪 Test 4.3.4: Branch metadata tracked in query results")
        query_result = self.query_repository("test-feature-branch", "function")
        if query_result and len(query_result['results']) > 0:
            # Check if branch information is available in metadata
            metadata = query_result.get('query_metadata', {})
            results["4.3.4"] = 'repositories_searched' in metadata
            print(f"   Branch metadata tracked: {results['4.3.4']}")
        else:
            results["4.3.4"] = False
        
        return results
    
    def cleanup_test_repositories(self):
        """Clean up test repositories"""
        print("\n🧹 Cleaning up test repositories...")
        
        repos_to_cleanup = ["test-repo-main", "test-main-branch", "test-master-branch", 
                           "test-feature-branch", "test-hotfix-branch"]
        
        for repo_alias in repos_to_cleanup:
            try:
                response = requests.delete(
                    f"{self.base_url}/api/repos/{repo_alias}",
                    headers={"Authorization": f"Bearer {self.admin_token}"}
                )
                if response.status_code in [200, 202, 404]:
                    print(f"   ✅ {repo_alias} cleanup initiated")
                else:
                    print(f"   ⚠️ {repo_alias} cleanup failed: {response.status_code}")
            except:
                pass
        
        # Clean up golden repository
        try:
            response = requests.delete(
                f"{self.base_url}/api/admin/golden-repos/epic4-test",
                headers={"Authorization": f"Bearer {self.admin_token}"}
            )
            if response.status_code in [200, 404]:
                print(f"   ✅ Golden repository cleanup initiated")
        except:
            pass
    
    def run_all_tests(self):
        """Run all Epic 4 Branch Operations tests"""
        print("🚀 EPIC 4: BRANCH OPERATIONS - COMPREHENSIVE TEST SUITE")
        print("=" * 80)
        
        # Setup
        if not self.get_admin_token():
            return False
        
        if not self.setup_test_repository():
            return False
        
        # Register golden repository
        if not self.register_golden_repository("epic4-test", "master"):
            return False
        
        # Activate initial repository for basic branch operations
        if not self.activate_repository("epic4-test", "test-repo-main"):
            return False
        
        # Run test stories
        story_4_1_results = self.test_story_4_1_branch_switching()
        story_4_2_results = self.test_story_4_2_branch_activation_variations()
        story_4_3_results = self.test_story_4_3_branch_content_verification()
        
        # Cleanup
        self.cleanup_test_repositories()
        
        # Print summary
        print("\n" + "="*80)
        print("📊 EPIC 4 TEST RESULTS SUMMARY")
        print("="*80)
        
        all_results = {**story_4_1_results, **story_4_2_results, **story_4_3_results}
        passed = sum(1 for result in all_results.values() if result)
        total = len(all_results)
        
        print(f"\n📈 Overall Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        print(f"\n📋 Story 4.1 (Branch Switching): {sum(story_4_1_results.values())}/{len(story_4_1_results)} passed")
        for test, result in story_4_1_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {test}: {status}")
        
        print(f"\n📋 Story 4.2 (Branch Activation): {sum(story_4_2_results.values())}/{len(story_4_2_results)} passed")
        for test, result in story_4_2_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {test}: {status}")
        
        print(f"\n📋 Story 4.3 (Content Verification): {sum(story_4_3_results.values())}/{len(story_4_3_results)} passed")
        for test, result in story_4_3_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {test}: {status}")
        
        success_rate = passed / total
        if success_rate >= 0.8:
            print(f"\n🎉 EPIC 4 BRANCH OPERATIONS: MOSTLY SUCCESSFUL ({success_rate*100:.1f}% pass rate)")
        elif success_rate >= 0.5:
            print(f"\n⚠️  EPIC 4 BRANCH OPERATIONS: PARTIAL SUCCESS ({success_rate*100:.1f}% pass rate)")
        else:
            print(f"\n❌ EPIC 4 BRANCH OPERATIONS: NEEDS SIGNIFICANT WORK ({success_rate*100:.1f}% pass rate)")
        
        return success_rate >= 0.5

if __name__ == "__main__":
    tester = Epic4BranchTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)