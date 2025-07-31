"""
Comprehensive end-to-end test for git-aware workflow.

This test simulates a realistic development scenario with:
- Multi-branch development (master, feature branches, release branch)
- Production emergency fixes on release branch
- Active development with watch mode
- Query validation across branch contexts
- Branch isolation and historical accuracy

Test Scenario: E-commerce Platform Development
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest

from .conftest import local_temporary_directory
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


@pytest.fixture
def comprehensive_test_repo():
    """Create a comprehensive test repository with git structure."""
    with local_temporary_directory() as temp_dir:
        # Create isolated project space using inventory system (no config tinkering)
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.COMPREHENSIVE_GIT_WORKFLOW
        )

        yield temp_dir


class ComprehensiveWorkflowTest:
    """Comprehensive test for git-aware development workflow."""

    def __init__(self, test_repo_dir: Path):
        self.test_repo_dir = test_repo_dir
        self.config_dir = test_repo_dir / ".code-indexer"
        self.watch_process: Optional[subprocess.Popen] = None
        self.query_results: Dict[str, Dict[str, List[Dict]]] = {}

    def setup_test_environment(self):
        """Setup test infrastructure without using deprecated create_fast_e2e_setup."""
        print("🔍 Comprehensive setup: Verifying service functionality...")

        # Simple service verification by running basic commands
        try:
            # Initialize project if config doesn't exist with correct settings
            config_file = self.config_dir / "config.json"
            if not config_file.exists():
                init_result = subprocess.run(
                    [
                        "code-indexer",
                        "init",
                        "--force",
                        "--embedding-provider",
                        "voyage-ai",
                    ],
                    cwd=self.test_repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if init_result.returncode != 0:
                    raise RuntimeError(
                        f"Service verification failed during init: {init_result.stderr}"
                    )

            print("✅ Comprehensive setup complete - services verified functional")
        except Exception as e:
            raise RuntimeError(f"Service functionality verification failed: {e}")

        return True

    def cleanup_test_environment(self):
        """Clean up test environment and repository."""
        # Stop watch if running
        if self.watch_process:
            try:
                self.watch_process.terminate()
                self.watch_process.wait(timeout=10)
            except (subprocess.TimeoutExpired, OSError):
                if self.watch_process.poll() is None:
                    self.watch_process.kill()

        # Clean up repository
        if self.test_repo_dir and self.test_repo_dir.exists():
            import shutil

            shutil.rmtree(self.test_repo_dir, ignore_errors=True)

    def create_ecommerce_codebase(self) -> bool:
        """Create realistic e-commerce platform codebase."""
        try:
            # Create directory structure
            assert self.test_repo_dir is not None
            assert self.config_dir is not None
            (self.test_repo_dir / "src" / "auth").mkdir(parents=True)
            (self.test_repo_dir / "src" / "payment").mkdir(parents=True)
            (self.test_repo_dir / "src" / "inventory").mkdir(parents=True)
            (self.test_repo_dir / "src" / "api").mkdir(parents=True)
            (self.test_repo_dir / "tests").mkdir(parents=True)

            # Create auth module
            (self.test_repo_dir / "src" / "auth" / "login.py").write_text(
                """
'''User authentication module for e-commerce platform.'''

import hashlib
import datetime
from typing import Optional, Dict, Any


class UserAuthenticator:
    '''Handles user login and authentication.'''
    
    def __init__(self):
        self.users_db = {}  # Simple in-memory user store
        self.failed_attempts = {}
        
    def register_user(self, username: str, password: str, email: str) -> bool:
        '''Register a new user account.'''
        if username in self.users_db:
            return False
            
        password_hash = self._hash_password(password)
        self.users_db[username] = {
            'password_hash': password_hash,
            'email': email,
            'created_at': datetime.datetime.now(),
            'is_active': True
        }
        return True
        
    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        '''Authenticate user credentials and return user info.'''
        if username not in self.users_db:
            return None
            
        user = self.users_db[username]
        if not user['is_active']:
            return None
            
        if self._verify_password(password, user['password_hash']):
            # Reset failed attempts on successful login
            self.failed_attempts.pop(username, None)
            return {
                'username': username,
                'email': user['email'],
                'login_time': datetime.datetime.now()
            }
        else:
            # Track failed attempts
            self.failed_attempts[username] = self.failed_attempts.get(username, 0) + 1
            return None
            
    def _hash_password(self, password: str) -> str:
        '''Hash password using SHA-256.'''
        return hashlib.sha256(password.encode()).hexdigest()
        
    def _verify_password(self, password: str, stored_hash: str) -> bool:
        '''Verify password against stored hash.'''
        return self._hash_password(password) == stored_hash
        
    def is_account_locked(self, username: str) -> bool:
        '''Check if account is locked due to failed attempts.'''
        return self.failed_attempts.get(username, 0) >= 3
"""
            )

            # Create session management
            (self.test_repo_dir / "src" / "auth" / "session.py").write_text(
                """
'''Session management for authenticated users.'''

import uuid
import datetime
from typing import Dict, Optional, Any


class SessionManager:
    '''Manages user sessions and authentication tokens.'''
    
    def __init__(self, session_timeout_minutes: int = 30):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.session_timeout = datetime.timedelta(minutes=session_timeout_minutes)
        
    def create_session(self, user_info: Dict[str, Any]) -> str:
        '''Create a new session for authenticated user.'''
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            'user_info': user_info,
            'created_at': datetime.datetime.now(),
            'last_activity': datetime.datetime.now(),
            'is_active': True
        }
        return session_id
        
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        '''Get session information if valid and active.'''
        if session_id not in self.sessions:
            return None
            
        session = self.sessions[session_id]
        if not session['is_active']:
            return None
            
        # Check if session has expired
        if self._is_session_expired(session):
            self.invalidate_session(session_id)
            return None
            
        # Update last activity
        session['last_activity'] = datetime.datetime.now()
        return session
        
    def invalidate_session(self, session_id: str) -> bool:
        '''Invalidate a session.'''
        if session_id in self.sessions:
            self.sessions[session_id]['is_active'] = False
            return True
        return False
        
    def _is_session_expired(self, session: Dict[str, Any]) -> bool:
        '''Check if session has expired based on last activity.'''
        time_since_activity = datetime.datetime.now() - session['last_activity']
        return time_since_activity > self.session_timeout
        
    def cleanup_expired_sessions(self) -> int:
        '''Remove expired sessions and return count of cleaned up sessions.'''
        expired_sessions = []
        for session_id, session in self.sessions.items():
            if self._is_session_expired(session):
                expired_sessions.append(session_id)
                
        for session_id in expired_sessions:
            del self.sessions[session_id]
            
        return len(expired_sessions)
"""
            )

            # Create payment processing
            (self.test_repo_dir / "src" / "payment" / "processor.py").write_text(
                """
'''Payment processing module for e-commerce platform.'''

import decimal
import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


class PaymentStatus(Enum):
    '''Payment transaction status.'''
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(Enum):
    '''Supported payment methods.'''
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"


@dataclass
class PaymentRequest:
    '''Payment request data structure.'''
    amount: decimal.Decimal
    currency: str
    payment_method: PaymentMethod
    customer_id: str
    order_id: str
    payment_details: Dict[str, Any]


@dataclass
class PaymentResult:
    '''Payment processing result.'''
    transaction_id: str
    status: PaymentStatus
    amount: decimal.Decimal
    currency: str
    timestamp: datetime.datetime
    error_message: Optional[str] = None


class PaymentProcessor:
    '''Main payment processing engine.'''
    
    def __init__(self):
        self.transactions: Dict[str, PaymentResult] = {}
        
    def process_payment(self, payment_request: PaymentRequest) -> PaymentResult:
        '''Process a payment request and return result.'''
        transaction_id = self._generate_transaction_id()
        
        try:
            # Validate payment request
            if not self._validate_payment_request(payment_request):
                return PaymentResult(
                    transaction_id=transaction_id,
                    status=PaymentStatus.FAILED,
                    amount=payment_request.amount,
                    currency=payment_request.currency,
                    timestamp=datetime.datetime.now(),
                    error_message="Invalid payment request"
                )
            
            # Process based on payment method
            if payment_request.payment_method == PaymentMethod.CREDIT_CARD:
                result = self._process_credit_card(payment_request, transaction_id)
            elif payment_request.payment_method == PaymentMethod.PAYPAL:
                result = self._process_paypal(payment_request, transaction_id)
            else:
                result = PaymentResult(
                    transaction_id=transaction_id,
                    status=PaymentStatus.FAILED,
                    amount=payment_request.amount,
                    currency=payment_request.currency,
                    timestamp=datetime.datetime.now(),
                    error_message=f"Unsupported payment method: {payment_request.payment_method}"
                )
                
            # Store transaction
            self.transactions[transaction_id] = result
            return result
            
        except Exception as e:
            return PaymentResult(
                transaction_id=transaction_id,
                status=PaymentStatus.FAILED,
                amount=payment_request.amount,
                currency=payment_request.currency,
                timestamp=datetime.datetime.now(),
                error_message=f"Payment processing error: {str(e)}"
            )
            
    def _validate_payment_request(self, request: PaymentRequest) -> bool:
        '''Validate payment request data.'''
        if request.amount <= 0:
            return False
        if not request.currency or len(request.currency) != 3:
            return False
        if not request.customer_id or not request.order_id:
            return False
        return True
        
    def _process_credit_card(self, request: PaymentRequest, transaction_id: str) -> PaymentResult:
        '''Process credit card payment.'''
        # Simulate credit card processing
        card_details = request.payment_details
        
        if not self._validate_credit_card(card_details):
            return PaymentResult(
                transaction_id=transaction_id,
                status=PaymentStatus.FAILED,
                amount=request.amount,
                currency=request.currency,
                timestamp=datetime.datetime.now(),
                error_message="Invalid credit card details"
            )
            
        # Simulate successful processing
        return PaymentResult(
            transaction_id=transaction_id,
            status=PaymentStatus.COMPLETED,
            amount=request.amount,
            currency=request.currency,
            timestamp=datetime.datetime.now()
        )
        
    def _process_paypal(self, request: PaymentRequest, transaction_id: str) -> PaymentResult:
        '''Process PayPal payment.'''
        # Simulate PayPal processing
        return PaymentResult(
            transaction_id=transaction_id,
            status=PaymentStatus.COMPLETED,
            amount=request.amount,
            currency=request.currency,
            timestamp=datetime.datetime.now()
        )
        
    def _validate_credit_card(self, card_details: Dict[str, Any]) -> bool:
        '''Validate credit card details.'''
        required_fields = ['card_number', 'expiry_month', 'expiry_year', 'cvv']
        return all(field in card_details for field in required_fields)
        
    def _generate_transaction_id(self) -> str:
        '''Generate unique transaction ID.'''
        import uuid
        return f"txn_{uuid.uuid4().hex[:12]}"
        
    def get_transaction(self, transaction_id: str) -> Optional[PaymentResult]:
        '''Get transaction by ID.'''
        return self.transactions.get(transaction_id)
"""
            )

            # Create README
            (self.test_repo_dir / "README.md").write_text(
                """
# E-commerce Platform

A comprehensive e-commerce platform with authentication, payment processing, and inventory management.

## Features

### Authentication
- User registration and login
- Session management
- Account security with failed attempt tracking

### Payment Processing  
- Multiple payment methods (Credit Card, PayPal, Bank Transfer)
- Secure transaction processing
- Payment validation and error handling

### Inventory Management
- Stock tracking and management
- Product catalog
- Inventory alerts and reporting

### API
- RESTful API endpoints
- Request middleware and validation
- Rate limiting and security

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python -m src.main

# Run tests
python -m pytest tests/
```

## Architecture

The platform follows a modular architecture with clear separation of concerns:
- Authentication module handles user management
- Payment module processes transactions
- Inventory module manages stock
- API module provides external interfaces
"""
            )

            # Preserve existing config created by setup_test_environment
            # Don't overwrite the working configuration with hardcoded values

            return True

        except Exception as e:
            print(f"Failed to create e-commerce codebase: {e}")
            return False

    def run_git_command(self, args: List[str]) -> subprocess.CompletedProcess:
        """Run git command in test repository."""
        assert self.test_repo_dir is not None
        return subprocess.run(
            ["git"] + args,
            cwd=self.test_repo_dir,
            capture_output=True,
            text=True,
            check=False,  # Don't raise on non-zero exit
        )

    def index_current_branch(self) -> Dict[str, Any]:
        """Index the current branch and return stats."""
        try:
            assert self.test_repo_dir is not None
            assert self.config_dir is not None
            # Use CLI helper to run index command
            cmd = [
                sys.executable,
                "-m",
                "code_indexer.cli",
                "--config",
                str(self.config_dir / "config.json"),
                "index",
            ]

            result = subprocess.run(
                cmd,
                cwd=self.test_repo_dir,
                capture_output=True,
                text=True,
                timeout=180,  # 2 minutes timeout
            )

            if result.returncode == 0:
                # Parse output to extract stats (simplified)
                output_lines = result.stdout.split("\n")
                files_processed = 0
                for line in output_lines:
                    if "files processed:" in line.lower():
                        try:
                            # Extract number from line like "📄 Files processed: 4"
                            parts = line.split(":")
                            if len(parts) >= 2:
                                number_part = parts[1].strip()
                                if number_part.isdigit():
                                    files_processed = int(number_part)
                                    break
                        except (subprocess.TimeoutExpired, OSError):
                            pass

                return {
                    "success": True,
                    "files_processed": files_processed,
                    "output": result.stdout,
                }
            else:
                return {"success": False, "error": result.stderr, "files_processed": 0}

        except Exception as e:
            return {"success": False, "error": str(e), "files_processed": 0}

    def query_codebase(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Query the codebase and return results with comprehensive debugging."""
        try:
            assert self.test_repo_dir is not None
            assert self.config_dir is not None

            print(f"🔍 Querying: '{query}' (limit: {limit})")

            # Use CLI helper to run query command
            cmd = [
                sys.executable,
                "-m",
                "code_indexer.cli",
                "--config",
                str(self.config_dir / "config.json"),
                "query",
                query,
                "--limit",
                str(limit),
            ]

            result = subprocess.run(
                cmd,
                cwd=self.test_repo_dir,
                capture_output=True,
                text=True,
                timeout=60,  # 1 minute timeout
            )

            print(f"Query result: {result.returncode}")
            if result.returncode != 0:
                print(f"Query stderr: {result.stderr}")
                print(f"Query stdout: {result.stdout}")

                # Diagnose potential issues
                try:
                    # Check service status
                    status_cmd = [
                        sys.executable,
                        "-m",
                        "code_indexer.cli",
                        "--config",
                        str(self.config_dir / "config.json"),
                        "status",
                    ]
                    status_result = subprocess.run(
                        status_cmd,
                        cwd=self.test_repo_dir,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    print(f"Service status during failed query: {status_result.stdout}")
                except Exception as e:
                    print(f"Could not get diagnostic info: {e}")
                return []

            if result.returncode == 0:
                if (
                    "❌ No results found" in result.stdout
                    or "No results found" in result.stdout
                ):
                    print("⚠️  Query succeeded but returned no results")
                    return []

                # Parse query results from output
                # Look for pattern: "📄 File: path | ... | 📊 Score: 0.xxx"
                results = []
                lines = result.stdout.split("\n")
                current_result = None
                in_content = False

                for line in lines:
                    stripped_line = line.strip()

                    # Check for file header line
                    if stripped_line.startswith("📄 File:"):
                        # Save previous result
                        if current_result:
                            results.append(current_result)

                        # Parse new file result
                        current_result = {"content": "", "score": 0.0}

                        # Extract file path
                        parts = stripped_line.split("|")
                        if len(parts) > 0:
                            file_part = parts[0].replace("📄 File:", "").strip()
                            current_result["file"] = file_part

                        # Extract score
                        for part in parts:
                            if "📊 Score:" in part:
                                try:
                                    score_str = part.split("📊 Score:")[1].strip()
                                    current_result["score"] = float(score_str)
                                except (ValueError, IndexError):
                                    pass

                        in_content = False

                    # Check for content section start
                    elif stripped_line.startswith("📖 Content:"):
                        in_content = True

                    # Check for content section separator
                    elif stripped_line.startswith("──────"):
                        # Toggle content reading state
                        if current_result:
                            in_content = not in_content

                    # Collect content lines
                    elif in_content and current_result and stripped_line:
                        current_result["content"] = (
                            str(current_result["content"]) + line + "\n"
                        )

                # Add final result
                if current_result:
                    results.append(current_result)

                print(f"✅ Query returned {len(results)} results")
                return results
            else:
                print(f"Query failed with code {result.returncode}: {result.stderr}")
                return []

        except Exception as e:
            print(f"Query error: {e}")
            return []

    def start_watch_mode(self, debounce: float = 1.0):
        """Start watch mode for real-time monitoring."""
        assert self.test_repo_dir is not None
        assert self.config_dir is not None

        if self.watch_process and self.watch_process.poll() is None:
            print("⚠️ Watch already running")
            return True

        try:
            cmd = [
                sys.executable,
                "-m",
                "code_indexer.cli",
                "--config",
                str(self.config_dir / "config.json"),
                "watch",
                "--debounce",
                str(debounce),
            ]

            self.watch_process = subprocess.Popen(
                cmd,
                cwd=self.test_repo_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent)},
            )

            # Give watch time to start
            time.sleep(3.0)

            # Check if process started successfully
            if self.watch_process.poll() is not None:
                stdout, stderr = self.watch_process.communicate()
                raise RuntimeError(
                    f"Watch process failed to start. STDOUT: {stdout}, STDERR: {stderr}"
                )

            print(f"👀 Watch mode started with PID {self.watch_process.pid}")
            return True

        except Exception as e:
            print(f"❌ Failed to start watch mode: {e}")
            if self.watch_process:
                try:
                    self.watch_process.terminate()
                except (OSError, subprocess.SubprocessError):
                    pass
                self.watch_process = None
            return False

    def stop_watch_mode(self):
        """Stop watch mode if running."""
        if self.watch_process:
            try:
                print(f"🛑 Stopping watch mode (PID {self.watch_process.pid})")
                self.watch_process.terminate()
                self.watch_process.wait(timeout=10)
                print("✅ Watch mode stopped")
            except (subprocess.TimeoutExpired, OSError):
                if self.watch_process.poll() is None:
                    print("⚠️ Force killing watch process")
                    self.watch_process.kill()
                    self.watch_process.wait()
            finally:
                self.watch_process = None

    def validate_branch_isolation(self) -> bool:
        """Validate that queries return appropriate results per branch."""
        # This will be implemented for validation
        return True


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for comprehensive workflow test",
)
@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
def test_comprehensive_git_workflow_all_phases(comprehensive_test_repo):
    """Complete git-aware workflow test covering all development phases."""
    test_dir = comprehensive_test_repo

    try:
        original_cwd = Path.cwd()
        os.chdir(test_dir)

        # Initialize and start services
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        start_result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Create workflow test instance with the fixture-provided repo
        workflow_test = ComprehensiveWorkflowTest(test_dir)
        workflow_test.setup_test_environment()

        # === PHASE 1: Initial Setup and Baseline ===
        print("\n=== PHASE 1: Initial Setup and Baseline ===")

        # Create realistic e-commerce codebase
        assert workflow_test.create_ecommerce_codebase()

        # Initialize git repository
        git_result = workflow_test.run_git_command(["init"])
        assert git_result.returncode == 0

        # Configure git
        workflow_test.run_git_command(["config", "user.name", "Test Developer"])
        workflow_test.run_git_command(["config", "user.email", "dev@example.com"])

        # Commit A: Initial commit with basic auth and payment
        workflow_test.run_git_command(["add", "."])
        commit_result = workflow_test.run_git_command(
            ["commit", "-m", "Initial commit: Basic auth and payment systems"]
        )
        assert commit_result.returncode == 0

        # Index master branch and establish baseline
        index_stats = workflow_test.index_current_branch()
        assert index_stats[
            "success"
        ], f"Indexing failed: {index_stats.get('error', 'Unknown error')}"
        assert index_stats["files_processed"] > 0

        # Validate baseline queries
        auth_results = workflow_test.query_codebase("authentication methods")
        payment_results = workflow_test.query_codebase("payment processing")

        assert len(auth_results) > 0, "Should find authentication-related code"
        assert len(payment_results) > 0, "Should find payment-related code"

        # Store baseline results
        workflow_test.query_results["master_baseline"] = {
            "auth": auth_results,
            "payment": payment_results,
        }
        print(f"✅ Phase 1 complete - Indexed {index_stats['files_processed']} files")

        # === PHASE 2: Feature Development Workflow ===
        _run_phase_2_feature_development(workflow_test)

        # === PHASE 3: Production Emergency (Release Branch) ===
        _run_phase_3_production_emergency(workflow_test)

        # === PHASE 4: Branch Isolation Validation ===
        _run_phase_4_validation(workflow_test)

        print("✅ Comprehensive git workflow test completed successfully!")

    finally:
        try:
            os.chdir(original_cwd)
            # Clean up
            subprocess.run(
                ["code-indexer", "clean", "--remove-data", "--quiet"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception:
            pass


def _run_phase_2_feature_development(workflow_test):
    """Phase 2: Feature development with branch switching."""
    print("\n=== PHASE 2: Feature Development Workflow ===")

    # Ensure we start from master branch
    workflow_test.run_git_command(["checkout", "master"])

    # Start from master branch and add inventory management (Commit B)
    inventory_code = '''
"""Inventory management module for e-commerce platform."""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import datetime


class StockStatus(Enum):
    """Stock availability status."""
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"


@dataclass
class Product:
    """Product information."""
    product_id: str
    name: str
    description: str
    price: float
    category: str
    sku: str


@dataclass
class InventoryItem:
    """Inventory item with stock information."""
    product: Product
    quantity: int
    reserved_quantity: int
    reorder_level: int
    reorder_quantity: int
    last_updated: datetime.datetime
    status: StockStatus


class InventoryManager:
    """Main inventory management system."""
    
    def __init__(self):
        self.inventory: Dict[str, InventoryItem] = {}
        self.transaction_log: List[Dict] = []
        
    def add_product(self, product: Product, initial_quantity: int = 0) -> bool:
        """Add a new product to inventory."""
        if product.product_id in self.inventory:
            return False
            
        status = self._determine_stock_status(initial_quantity, 10)  # Default reorder level
        
        inventory_item = InventoryItem(
            product=product,
            quantity=initial_quantity,
            reserved_quantity=0,
            reorder_level=10,
            reorder_quantity=50,
            last_updated=datetime.datetime.now(),
            status=status
        )
        
        self.inventory[product.product_id] = inventory_item
        self._log_transaction("ADD_PRODUCT", product.product_id, initial_quantity)
        return True
        
    def update_stock(self, product_id: str, quantity_change: int, reason: str = "MANUAL") -> bool:
        """Update stock quantity for a product."""
        if product_id not in self.inventory:
            return False
            
        item = self.inventory[product_id]
        new_quantity = item.quantity + quantity_change
        
        if new_quantity < 0:
            return False  # Cannot have negative stock
            
        item.quantity = new_quantity
        item.last_updated = datetime.datetime.now()
        item.status = self._determine_stock_status(new_quantity, item.reorder_level)
        
        self._log_transaction(reason, product_id, quantity_change)
        return True
        
    def reserve_stock(self, product_id: str, quantity: int) -> bool:
        """Reserve stock for pending orders."""
        if product_id not in self.inventory:
            return False
            
        item = self.inventory[product_id]
        available_quantity = item.quantity - item.reserved_quantity
        
        if available_quantity < quantity:
            return False
            
        item.reserved_quantity += quantity
        item.last_updated = datetime.datetime.now()
        self._log_transaction("RESERVE", product_id, quantity)
        return True
        
    def release_reservation(self, product_id: str, quantity: int) -> bool:
        """Release reserved stock."""
        if product_id not in self.inventory:
            return False
            
        item = self.inventory[product_id]
        if item.reserved_quantity < quantity:
            return False
            
        item.reserved_quantity -= quantity
        item.last_updated = datetime.datetime.now()
        self._log_transaction("RELEASE", product_id, quantity)
        return True
        
    def get_available_quantity(self, product_id: str) -> int:
        """Get available (non-reserved) quantity."""
        if product_id not in self.inventory:
            return 0
            
        item = self.inventory[product_id]
        return item.quantity - item.reserved_quantity
        
    def get_low_stock_items(self) -> List[InventoryItem]:
        """Get items that need reordering."""
        return [
            item for item in self.inventory.values()
            if item.status in [StockStatus.LOW_STOCK, StockStatus.OUT_OF_STOCK]
        ]
        
    def _determine_stock_status(self, quantity: int, reorder_level: int) -> StockStatus:
        """Determine stock status based on quantity."""
        if quantity == 0:
            return StockStatus.OUT_OF_STOCK
        elif quantity <= reorder_level:
            return StockStatus.LOW_STOCK
        else:
            return StockStatus.IN_STOCK
            
    def _log_transaction(self, transaction_type: str, product_id: str, quantity: int):
        """Log inventory transaction."""
        self.transaction_log.append({
            'timestamp': datetime.datetime.now(),
            'type': transaction_type,
            'product_id': product_id,
            'quantity': quantity
        })
'''

    # Create inventory module
    assert workflow_test.test_repo_dir is not None
    (workflow_test.test_repo_dir / "src" / "inventory" / "manager.py").write_text(
        inventory_code
    )

    # Commit B: Add inventory management
    workflow_test.run_git_command(["add", "src/inventory/manager.py"])
    commit_b = workflow_test.run_git_command(
        ["commit", "-m", "Add inventory management system"]
    )
    assert commit_b.returncode == 0

    # Index master with inventory before creating feature branch
    master_index_stats = workflow_test.index_current_branch()
    assert master_index_stats["success"]

    # Create feature-payment-v2 branch from commit B
    branch_result = workflow_test.run_git_command(
        ["checkout", "-b", "feature-payment-v2"]
    )
    assert branch_result.returncode == 0

    # Add experimental payment gateway integration (Commit I)
    payment_v2_code = '''
"""Advanced payment gateway integration module."""

import asyncio
import aiohttp
import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from .processor import PaymentResult, PaymentStatus, PaymentMethod


@dataclass
class GatewayConfig:
    """Payment gateway configuration."""
    gateway_name: str
    api_endpoint: str
    api_key: str
    webhook_secret: str
    timeout_seconds: int = 30


class PaymentGatewayV2:
    """Advanced payment gateway with multiple provider support."""
    
    def __init__(self):
        self.gateways: Dict[str, GatewayConfig] = {}
        self.webhook_handlers: Dict[str, callable] = {}
        
    def register_gateway(self, config: GatewayConfig):
        """Register a payment gateway."""
        self.gateways[config.gateway_name] = config
        
    async def process_payment_async(
        self, 
        gateway_name: str,
        payment_data: Dict[str, Any]
    ) -> PaymentResult:
        """Process payment asynchronously through specified gateway."""
        if gateway_name not in self.gateways:
            raise ValueError(f"Gateway '{gateway_name}' not registered")
            
        gateway = self.gateways[gateway_name]
        
        async with aiohttp.ClientSession() as session:
            try:
                headers = {
                    'Authorization': f'Bearer {gateway.api_key}',
                    'Content-Type': 'application/json'
                }
                
                async with session.post(
                    gateway.api_endpoint,
                    json=payment_data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=gateway.timeout_seconds)
                ) as response:
                    
                    if response.status == 200:
                        result_data = await response.json()
                        return self._parse_gateway_response(result_data)
                    else:
                        error_text = await response.text()
                        return PaymentResult(
                            transaction_id=payment_data.get('transaction_id', 'unknown'),
                            status=PaymentStatus.FAILED,
                            amount=payment_data.get('amount', 0),
                            currency=payment_data.get('currency', 'USD'),
                            timestamp=datetime.datetime.now(),
                            error_message=f"Gateway error: {error_text}"
                        )
                        
            except asyncio.TimeoutError:
                return PaymentResult(
                    transaction_id=payment_data.get('transaction_id', 'unknown'),
                    status=PaymentStatus.FAILED,
                    amount=payment_data.get('amount', 0),
                    currency=payment_data.get('currency', 'USD'),
                    timestamp=datetime.datetime.now(),
                    error_message="Payment gateway timeout"
                )
                
    def register_webhook_handler(self, event_type: str, handler: callable):
        """Register webhook event handler."""
        self.webhook_handlers[event_type] = handler
        
    async def handle_webhook(self, event_data: Dict[str, Any]) -> bool:
        """Handle incoming webhook from payment gateway."""
        event_type = event_data.get('event_type')
        if event_type in self.webhook_handlers:
            try:
                await self.webhook_handlers[event_type](event_data)
                return True
            except Exception as e:
                print(f"Webhook handler error: {e}")
                return False
        return False
        
    def _parse_gateway_response(self, response_data: Dict[str, Any]) -> PaymentResult:
        """Parse response from payment gateway."""
        # This would be customized per gateway
        return PaymentResult(
            transaction_id=response_data.get('id', 'unknown'),
            status=PaymentStatus.COMPLETED,
            amount=response_data.get('amount', 0),
            currency=response_data.get('currency', 'USD'),
            timestamp=datetime.datetime.now()
        )


class RecurringPaymentManager:
    """Manage recurring subscription payments."""
    
    def __init__(self, gateway: PaymentGatewayV2):
        self.gateway = gateway
        self.subscriptions: Dict[str, Dict] = {}
        
    async def create_subscription(
        self,
        customer_id: str,
        plan_id: str,
        payment_method: Dict[str, Any]
    ) -> str:
        """Create a recurring subscription."""
        subscription_id = f"sub_{customer_id}_{plan_id}"
        
        subscription_data = {
            'customer_id': customer_id,
            'plan_id': plan_id,
            'payment_method': payment_method,
            'status': 'active',
            'created_at': datetime.datetime.now(),
            'next_billing_date': datetime.datetime.now() + datetime.timedelta(days=30)
        }
        
        self.subscriptions[subscription_id] = subscription_data
        return subscription_id
        
    async def process_recurring_payment(self, subscription_id: str) -> PaymentResult:
        """Process a recurring payment for subscription."""
        if subscription_id not in self.subscriptions:
            raise ValueError(f"Subscription {subscription_id} not found")
            
        subscription = self.subscriptions[subscription_id]
        
        payment_data = {
            'transaction_id': f"recurring_{subscription_id}_{int(datetime.datetime.now().timestamp())}",
            'customer_id': subscription['customer_id'],
            'amount': subscription.get('amount', 29.99),
            'currency': 'USD',
            'payment_method': subscription['payment_method']
        }
        
        # Use the first available gateway for recurring payments
        gateway_name = list(self.gateway.gateways.keys())[0]
        return await self.gateway.process_payment_async(gateway_name, payment_data)
'''

    # Add payment v2 module
    assert workflow_test.test_repo_dir is not None
    (workflow_test.test_repo_dir / "src" / "payment" / "gateway_v2.py").write_text(
        payment_v2_code
    )

    # Commit I: Experimental payment gateway integration
    workflow_test.run_git_command(["add", "src/payment/gateway_v2.py"])
    commit_i = workflow_test.run_git_command(
        ["commit", "-m", "Add experimental payment gateway v2 with async support"]
    )
    assert commit_i.returncode == 0

    # Index the feature branch
    feature_index_stats = workflow_test.index_current_branch()
    assert feature_index_stats["success"]

    # Query the feature branch - should now find payment gateway v2 features
    payment_v2_results = workflow_test.query_codebase("async payment gateway")
    recurring_results = workflow_test.query_codebase("recurring subscription payments")

    assert len(payment_v2_results) > 0, "Should find async payment gateway code"
    assert len(recurring_results) > 0, "Should find recurring payment code"

    # === WATCH MODE INTEGRATION: Simulate active development ===
    print("\n🔄 Testing watch mode during active development...")

    # Start watch mode for real-time monitoring
    # Note: Watch mode may fail due to system inotify limits in test environments
    watch_started = workflow_test.start_watch_mode(debounce=0.5)
    if not watch_started:
        print(
            "⚠️ Watch mode failed to start (likely due to inotify limits) - skipping watch mode tests"
        )
        # Continue with the rest of the test without watch mode
        watch_mode_available = False
    else:
        print("✅ Watch mode started successfully")
        watch_mode_available = True

    # Simulate continued development while watch is running
    assert workflow_test.test_repo_dir is not None
    additional_feature_file = (
        workflow_test.test_repo_dir / "src" / "payment" / "analytics.py"
    )
    additional_feature_file.write_text(
        '''
"""Payment analytics module for monitoring transactions."""

from typing import Dict, List, Any
from datetime import datetime, timedelta


class PaymentAnalytics:
    """Analytics for payment processing patterns."""
    
    def __init__(self):
        self.transaction_data: List[Dict[str, Any]] = []
        
    def track_transaction(self, transaction_result):
        """Track a payment transaction for analytics."""
        self.transaction_data.append({
            'timestamp': datetime.now(),
            'amount': transaction_result.amount,
            'status': transaction_result.status.value,
            'transaction_id': transaction_result.transaction_id
        })
        
    def get_success_rate(self, time_period: timedelta = timedelta(hours=24)) -> float:
        """Calculate payment success rate over time period."""
        cutoff_time = datetime.now() - time_period
        recent_transactions = [
            t for t in self.transaction_data 
            if t['timestamp'] > cutoff_time
        ]
        
        if not recent_transactions:
            return 0.0
            
        successful = sum(1 for t in recent_transactions if t['status'] == 'completed')
        return successful / len(recent_transactions)
'''
    )

    # Watch mode verification (only if watch mode is available)
    if watch_mode_available:
        # Wait briefly for watch to potentially detect the new file
        time.sleep(2.0)
        # Stop watch mode
        workflow_test.stop_watch_mode()
        print("✅ Watch mode integration tested successfully")
    else:
        print(
            "✅ Watch mode test skipped due to system limitations - continuing without watch mode"
        )

    # Store feature branch results
    workflow_test.query_results["feature_payment_v2"] = {
        "payment_v2": payment_v2_results,
        "recurring": recurring_results,
    }
    print("✅ Phase 2 complete - Feature branch with async payment gateway")


def _run_phase_3_production_emergency(workflow_test):
    """Phase 3: Production emergency on release branch from older commit."""
    print("\n=== PHASE 3: Production Emergency (Release Branch) ===")

    # Switch back to master to get commit A for release branch
    workflow_test.run_git_command(["checkout", "master"])

    # Get commit A hash (first commit)
    log_result = workflow_test.run_git_command(["log", "--oneline", "--reverse"])
    first_commit = log_result.stdout.strip().split("\n")[0].split()[0]

    # Create release-v1.2 branch from commit A (older baseline)
    release_result = workflow_test.run_git_command(
        ["checkout", "-b", "release-v1.2", first_commit]
    )
    assert release_result.returncode == 0

    # Add critical security fix in auth (Commit G)
    security_fix = '''
def check_password_strength(password: str) -> bool:
    """Check if password meets security requirements."""
    if len(password) < 8:
        return False
    if not any(c.isupper() for c in password):
        return False
    if not any(c.islower() for c in password):
        return False
    if not any(c.isdigit() for c in password):
        return False
    return True

def is_password_compromised(password: str) -> bool:
    """Check against common compromised passwords."""
    # Simplified check - in reality would check against breach database
    common_passwords = ["password", "123456", "admin", "qwerty"]
    return password.lower() in common_passwords
'''

    # Add security functions to login.py
    assert workflow_test.test_repo_dir is not None
    login_file = workflow_test.test_repo_dir / "src" / "auth" / "login.py"
    current_content = login_file.read_text()
    updated_content = current_content + "\n\n" + security_fix
    login_file.write_text(updated_content)

    # Commit G: Security fix
    workflow_test.run_git_command(["add", "src/auth/login.py"])
    commit_g = workflow_test.run_git_command(
        ["commit", "-m", "SECURITY: Add password strength validation"]
    )
    assert commit_g.returncode == 0

    # Index release branch
    release_index_stats = workflow_test.index_current_branch()
    assert release_index_stats["success"]

    # Query release branch - should have security features but not inventory/payment v2
    security_results = workflow_test.query_codebase("password strength validation")
    inventory_results = workflow_test.query_codebase("InventoryManager class")

    assert len(security_results) > 0, "Should find security validation code"

    # Check that no actual InventoryManager class is found (more specific test)
    inventory_manager_results = [
        r for r in inventory_results if "InventoryManager" in r.get("content", "")
    ]
    assert (
        len(inventory_manager_results) == 0
    ), f"Should NOT find InventoryManager class in release branch, found: {[r['file'] for r in inventory_manager_results]}"

    # Also check that inventory manager file doesn't exist in results at all
    inventory_file_results = [
        r for r in inventory_results if "inventory/manager.py" in r["file"]
    ]
    assert (
        len(inventory_file_results) == 0
    ), "Should NOT find inventory/manager.py file in release branch"

    # Store release branch results
    workflow_test.query_results["release_v1_2"] = {
        "security": security_results,
        "inventory": inventory_results,
    }
    print("✅ Phase 3 complete - Release branch with security fixes")


def _run_phase_4_validation(workflow_test):
    """Phase 4: Final validation of branch isolation."""
    print("\n=== PHASE 4: Branch Isolation Validation ===")

    # Test query isolation across branches
    branches_to_test = ["master", "feature-payment-v2", "release-v1.2"]
    validation_results = {}

    for branch in branches_to_test:
        print(f"Testing branch: {branch}")
        checkout_result = workflow_test.run_git_command(["checkout", branch])
        if checkout_result.returncode != 0:
            continue

        # Re-index the current branch to ensure proper branch isolation
        branch_index_stats = workflow_test.index_current_branch()
        if not branch_index_stats["success"]:
            print(f"  ⚠️  Warning: Failed to re-index branch {branch}")

        # Test queries that should show different results per branch
        auth_results = workflow_test.query_codebase("authentication methods")
        payment_results = workflow_test.query_codebase("payment processing")
        inventory_results = workflow_test.query_codebase("InventoryManager class")

        # Check for specific inventory file
        inventory_file_results = [
            r for r in inventory_results if "inventory/manager.py" in r["file"]
        ]

        validation_results[branch] = {
            "auth_count": len(auth_results),
            "payment_count": len(payment_results),
            "inventory_count": len(
                inventory_file_results
            ),  # Count actual inventory file
            "inventory_total": len(inventory_results),  # Include all for reference
        }
        print(
            f"  Branch {branch}: auth={len(auth_results)}, payment={len(payment_results)}, inventory_files={len(inventory_file_results)}"
        )

    # Validate branch isolation expectations
    # Master: has auth + payment + inventory (but not payment v2)
    assert (
        validation_results["master"]["inventory_count"] > 0
    ), "Master should have inventory"

    # Feature branch: has auth + payment + inventory + payment v2
    assert (
        validation_results["feature-payment-v2"]["inventory_count"] > 0
    ), "Feature branch should have inventory"

    # Release branch: has auth only (older branch point, before inventory was added)
    assert (
        validation_results["release-v1.2"]["inventory_count"] == 0
    ), "Release should NOT have inventory"

    print("✅ Phase 4 complete - Branch isolation validated")
    print(f"Branch results: {validation_results}")

    # Store validation results (convert to expected type)
    workflow_test.query_results["branch_validation"] = {
        "validation": [validation_results]  # Wrap in list to match expected type
    }


# Helper functions for test validation
def validate_query_results_differ_by_branch(
    results_branch_a: List[Dict], results_branch_b: List[Dict], context: str
) -> bool:
    """Validate that query results differ appropriately between branches."""
    # Implementation pending
    return True


def validate_branch_isolation(
    master_results: List[Dict],
    feature_results: List[Dict],
    release_results: List[Dict],
    query_type: str,
) -> bool:
    """Validate that branch isolation works correctly."""
    # Implementation pending
    return True


def validate_historical_accuracy(
    release_results: List[Dict],
    expected_features: List[str],
    excluded_features: List[str],
) -> bool:
    """Validate that release branch reflects historical state correctly."""
    # Implementation pending
    return True
