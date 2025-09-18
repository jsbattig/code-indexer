# User Story: JWT Token Management

## 📋 **User Story**

As a **CIDX user**, I want **automatic JWT token refresh and re-authentication**, so that **my queries never fail due to token expiration without transparent recovery**.

## 🎯 **Business Value**

Eliminates user friction from authentication failures. Provides seamless long-running session support without interrupting user workflow.

## 📝 **Acceptance Criteria**

### Given: Persistent Token Storage Between Calls
**When** I obtain a JWT token during any remote operation  
**Then** the token is securely stored in .code-indexer/.token file  
**And** subsequent CIDX commands reuse the stored token without re-authentication  
**And** token storage includes expiration time for validation  
**And** stored tokens survive CLI process termination and restart  

### Given: Automatic Token Refresh with Storage
**When** my JWT token expires during normal operation  
**Then** the system automatically refreshes the token  
**And** stores the new token in .code-indexer/.token immediately  
**And** continues the original operation without user intervention  
**And** no error messages about token expiration appear  
**And** query execution completes successfully  

### Given: Re-authentication Fallback with Persistence
**When** token refresh fails or server requires re-authentication  
**Then** system automatically re-authenticates using stored credentials  
**And** obtains new JWT token transparently  
**And** stores new token in .code-indexer/.token  
**And** retries the original operation  
**And** provides success feedback without exposing authentication details  

### Given: Token Lifecycle Management with File Storage
**When** I use remote mode over extended periods  
**Then** token management happens entirely within API client layer  
**And** business logic never handles authentication concerns  
**And** multiple concurrent operations share token state safely  
**And** token validation prevents unnecessary authentication calls  
**And** token file is updated atomically to prevent corruption during concurrent access  

### Given: Secure Token File Management
**When** I examine token storage implementation  
**Then** .code-indexer/.token file has user-only permissions (600)  
**And** token file contains encrypted token data (not plaintext)  
**And** token file includes expiration timestamp for validation  
**And** invalid or corrupted token files trigger re-authentication automatically  

## 🏗️ **Technical Implementation**

### Persistent Token Storage Manager
```python
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import json
import fcntl
import tempfile

@dataclass
class StoredToken:
    access_token: str
    expires_at: float  # Unix timestamp (UTC)
    refresh_token: Optional[str] = None
    algorithm: str = "RS256"  # JWT algorithm - MUST be RS256 for security
    token_version: int = 1  # Token format version for future compatibility
    
    def is_expired(self) -> bool:
        """Check if token has expired with 30-second clock skew tolerance."""
        current_time = datetime.now(timezone.utc).timestamp()
        return current_time > (self.expires_at + 30)  # 30-second tolerance for clock skew
    
    def expires_soon(self, buffer_seconds: int = 300) -> bool:
        """Check if token expires within buffer time (default 5 minutes)."""
        current_time = datetime.now(timezone.utc).timestamp()
        return current_time > (self.expires_at - buffer_seconds)
    
    def validate_security_constraints(self) -> bool:
        """Validate token meets security requirements."""
        # Token must use RS256 algorithm (asymmetric, more secure than HS256)
        if self.algorithm != "RS256":
            logger.warning(f"Insecure JWT algorithm: {self.algorithm}, expected RS256")
            return False
        
        # Token must not be valid for more than 24 hours (security constraint)
        max_lifetime = 24 * 3600  # 24 hours
        if self.expires_at > (time.time() + max_lifetime):
            logger.warning("JWT token lifetime exceeds maximum allowed (24 hours)")
            return False
        
        return True

class PersistentTokenManager:
    """Manages JWT token storage and retrieval with file persistence."""
    
    # Security and operational constraints
    MAX_TOKEN_FILE_SIZE = 64 * 1024  # 64KB maximum token file size
    TOKEN_REFRESH_SYNCHRONIZATION_TIMEOUT = 30.0  # seconds
    FILE_LOCK_TIMEOUT = 5.0  # seconds for file operations
    MEMORY_CLEAR_ITERATIONS = 3  # Number of times to overwrite sensitive memory
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.token_file = project_root / ".code-indexer" / ".token"
        self.lock_file = project_root / ".code-indexer" / ".token.lock"
        self.credential_manager = ProjectCredentialManager()
        self._refresh_lock = threading.RLock()  # Prevent concurrent token refresh
        self._token_cache: Optional[StoredToken] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 60.0  # Cache token for 60 seconds to reduce file I/O
    
    def load_stored_token(self) -> Optional[StoredToken]:
        """Load token from secure file storage with comprehensive validation."""
        # Check cache first to reduce file I/O
        if (self._token_cache and 
            time.time() - self._cache_timestamp < self._cache_ttl and 
            not self._token_cache.expires_soon()):
            return self._token_cache
        
        if not self.token_file.exists():
            self._token_cache = None
            return None
        
        try:
            # Security validation: check file size to prevent DoS attacks
            file_stat = self.token_file.stat()
            if file_stat.st_size > self.MAX_TOKEN_FILE_SIZE:
                logger.error(f"Token file exceeds maximum size: {file_stat.st_size} > {self.MAX_TOKEN_FILE_SIZE}")
                self.token_file.unlink()
                return None
            
            # Security validation: verify file permissions (user-only read/write)
            if file_stat.st_mode & 0o077:
                logger.warning("Token file has insecure permissions (accessible by group/other), re-authenticating")
                self.token_file.unlink()
                return None
            
            # Platform-specific file locking with timeout
            with open(self.token_file, 'rb') as f:
                try:
                    # Use timeout for file locking to prevent deadlocks
                    if hasattr(fcntl, 'LOCK_NB'):
                        # Non-blocking lock with retry for platforms that support it
                        for attempt in range(50):  # 5 seconds total (50 * 0.1s)
                            try:
                                fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                                break
                            except BlockingIOError:
                                time.sleep(0.1)
                        else:
                            raise TimeoutError("Failed to acquire file lock within timeout")
                    else:
                        # Blocking lock for platforms without non-blocking support
                        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    
                    encrypted_data = f.read()
                    
                except (OSError, TimeoutError) as e:
                    logger.warning(f"File locking failed: {e}")
                    return None
            
            # Validate encrypted data size
            if len(encrypted_data) == 0:
                logger.warning("Empty token file found")
                self.token_file.unlink()
                return None
            
            # Decrypt token data using project-specific key
            try:
                decrypted_data = self.credential_manager.decrypt_token_data(
                    encrypted_data, str(self.project_root)
                )
            except Exception as e:
                logger.warning(f"Token decryption failed: {e}")
                self.token_file.unlink()
                return None
            
            # Parse and validate token structure
            try:
                token_data = json.loads(decrypted_data)
                # Validate required fields exist
                required_fields = ['access_token', 'expires_at']
                if not all(field in token_data for field in required_fields):
                    logger.warning(f"Token missing required fields: {required_fields}")
                    self.token_file.unlink()
                    return None
                
                stored_token = StoredToken(**token_data)
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.warning(f"Token parsing failed: {e}")
                self.token_file.unlink()
                return None
            
            # Security validation: check token security constraints
            if not stored_token.validate_security_constraints():
                logger.warning("Token fails security validation")
                self.token_file.unlink()
                return None
            
            # Validate token expiration
            if stored_token.is_expired():
                logger.debug("Stored token has expired, removing")
                self.token_file.unlink()
                return None
            
            # Cache valid token to reduce file I/O
            self._token_cache = stored_token
            self._cache_timestamp = time.time()
            
            return stored_token
            
        except Exception as e:
            logger.error(f"Unexpected error loading stored token: {e}")
            # Secure cleanup: remove corrupted token file
            try:
                if self.token_file.exists():
                    self.token_file.unlink()
            except Exception:
                pass  # Best effort cleanup
            
            self._token_cache = None
            return None
    
    def store_token(self, access_token: str, expires_in: int, refresh_token: Optional[str] = None):
        """Securely store JWT token with comprehensive atomic operations and memory security."""
        # Synchronize token storage to prevent concurrent writes
        with self._refresh_lock:
            # Secure memory management: use bytearray for secure cleanup
            token_json_bytes = None
            encrypted_data = None
            
            try:
                # Input validation
                if not access_token or not access_token.strip():
                    raise ValueError("access_token cannot be empty")
                if expires_in <= 0:
                    raise ValueError("expires_in must be positive")
                if expires_in > 24 * 3600:  # 24 hours maximum
                    raise ValueError("expires_in exceeds maximum allowed (24 hours)")
                
                # Calculate expiration timestamp with UTC precision
                expires_at = datetime.now(timezone.utc).timestamp() + expires_in
                
                stored_token = StoredToken(
                    access_token=access_token,
                    expires_at=expires_at,
                    refresh_token=refresh_token,
                    algorithm="RS256",  # Enforce secure algorithm
                    token_version=1
                )
                
                # Validate security constraints before storage
                if not stored_token.validate_security_constraints():
                    raise SecurityError("Token fails security validation before storage")
                
                # Serialize token data with secure memory handling
                token_dict = {
                    'access_token': stored_token.access_token,
                    'expires_at': stored_token.expires_at,
                    'refresh_token': stored_token.refresh_token,
                    'algorithm': stored_token.algorithm,
                    'token_version': stored_token.token_version,
                    'stored_at': time.time()  # Add storage timestamp for auditing
                }
                
                # Use bytearray for secure memory that can be cleared
                token_json = json.dumps(token_dict, separators=(',', ':'))  # Compact JSON
                token_json_bytes = bytearray(token_json.encode('utf-8'))
                
                # Encrypt token data using project-specific key
                encrypted_data = self.credential_manager.encrypt_token_data(
                    bytes(token_json_bytes), str(self.project_root)
                )
                
                # Validate encrypted data size
                if len(encrypted_data) > self.MAX_TOKEN_FILE_SIZE:
                    raise ValueError(f"Encrypted token exceeds maximum size: {len(encrypted_data)}")
                
                # Ensure .code-indexer directory exists with secure permissions
                config_dir = self.token_file.parent
                config_dir.mkdir(exist_ok=True, mode=0o700)
                
                # Verify directory permissions
                dir_stat = config_dir.stat()
                if dir_stat.st_mode & 0o077:
                    logger.warning("Config directory has insecure permissions, fixing")
                    config_dir.chmod(0o700)
                
                # Generate unique temporary file to prevent conflicts
                import uuid
                temp_suffix = f'.tmp.{uuid.uuid4().hex[:8]}'
                temp_file = self.token_file.with_suffix(temp_suffix)
                
                try:
                    # Atomic write operation with comprehensive error handling
                    with open(temp_file, 'wb') as f:
                        # Platform-specific exclusive file locking
                        try:
                            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            raise TimeoutError("Cannot acquire exclusive lock for token storage")
                        
                        # Write encrypted data
                        f.write(encrypted_data)
                        f.flush()  # Ensure data is written to disk
                        os.fsync(f.fileno())  # Force filesystem sync
                    
                    # Set secure permissions before making file visible
                    temp_file.chmod(0o600)
                    
                    # Verify file was written correctly
                    if temp_file.stat().st_size != len(encrypted_data):
                        raise IOError("Token file size mismatch after write")
                    
                    # Atomic move to final location (platform-specific implementation)
                    if os.name == 'nt':  # Windows
                        # Windows requires removing target file first
                        if self.token_file.exists():
                            self.token_file.unlink()
                        temp_file.rename(self.token_file)
                    else:  # POSIX (Linux, macOS)
                        temp_file.rename(self.token_file)
                    
                    # Update cache with new token
                    self._token_cache = stored_token
                    self._cache_timestamp = time.time()
                    
                    logger.debug(f"Token stored successfully, expires at {datetime.fromtimestamp(expires_at, timezone.utc).isoformat()}")
                    
                except Exception as e:
                    # Clean up temporary file on any error
                    try:
                        if temp_file.exists():
                            temp_file.unlink()
                    except Exception:
                        pass  # Best effort cleanup
                    raise
                
            except Exception as e:
                logger.error(f"Failed to store token: {e}")
                raise TokenStorageError(f"Could not store authentication token: {str(e)}")
            
            finally:
                # Secure memory cleanup: overwrite sensitive data
                if token_json_bytes:
                    for i in range(self.MEMORY_CLEAR_ITERATIONS):
                        for j in range(len(token_json_bytes)):
                            token_json_bytes[j] = 0
                    del token_json_bytes
                
                if encrypted_data:
                    # encrypted_data is bytes, can't be cleared in-place, but reference can be deleted
                    del encrypted_data
```

### Enhanced API Client with Token Persistence
```python
class CIDXRemoteAPIClient:
    """Base API client with persistent JWT token management and circuit breaker."""
    
    # Network and reliability constraints
    DEFAULT_TIMEOUT = httpx.Timeout(
        connect=10.0,  # Connection timeout
        read=30.0,     # Read timeout  
        write=10.0,    # Write timeout
        pool=5.0       # Pool timeout
    )
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 2.0  # Exponential backoff multiplier
    RETRY_BACKOFF_MAX = 60.0    # Maximum backoff time
    CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5  # Failures before opening circuit
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 300.0  # 5 minutes before trying again
    CONCURRENT_REQUEST_LIMIT = 10  # Maximum concurrent requests per client
    
    def __init__(self, server_url: str, credentials: EncryptedCredentials, project_root: Path):
        self.server_url = server_url.rstrip('/')
        self.credentials = credentials
        self.project_root = project_root
        
        # HTTP client with connection pooling and limits
        limits = httpx.Limits(
            max_keepalive_connections=5,
            max_connections=10,
            keepalive_expiry=30.0
        )
        
        self.session = httpx.AsyncClient(
            timeout=self.DEFAULT_TIMEOUT,
            limits=limits,
            http2=True,  # Enable HTTP/2 for performance
            verify=True  # Always verify SSL certificates
        )
        
        self.token_manager = PersistentTokenManager(project_root)
        self._current_token: Optional[str] = None
        
        # Circuit breaker state
        self._circuit_breaker_failures = 0
        self._circuit_breaker_opened_at: Optional[float] = None
        self._circuit_breaker_lock = threading.RLock()
        
        # Request rate limiting
        self._request_semaphore = threading.Semaphore(self.CONCURRENT_REQUEST_LIMIT)
        self._request_count = 0
        self._request_count_lock = threading.Lock()
    
    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is currently open."""
        with self._circuit_breaker_lock:
            if self._circuit_breaker_opened_at is None:
                return False
            
            # Check if recovery timeout has passed
            if time.time() - self._circuit_breaker_opened_at > self.CIRCUIT_BREAKER_RECOVERY_TIMEOUT:
                logger.info("Circuit breaker recovery timeout reached, attempting to close circuit")
                self._circuit_breaker_opened_at = None
                self._circuit_breaker_failures = 0
                return False
            
            return True
    
    def _record_circuit_breaker_success(self):
        """Record successful request for circuit breaker."""
        with self._circuit_breaker_lock:
            self._circuit_breaker_failures = 0
            self._circuit_breaker_opened_at = None
    
    def _record_circuit_breaker_failure(self):
        """Record failed request for circuit breaker."""
        with self._circuit_breaker_lock:
            self._circuit_breaker_failures += 1
            if self._circuit_breaker_failures >= self.CIRCUIT_BREAKER_FAILURE_THRESHOLD:
                self._circuit_breaker_opened_at = time.time()
                logger.warning(f"Circuit breaker opened after {self._circuit_breaker_failures} failures")
    
    async def _get_valid_token(self) -> str:
        """Get valid JWT token with persistent storage and automatic refresh."""
        # Check circuit breaker before attempting network operations
        if self._is_circuit_breaker_open():
            raise CircuitBreakerOpenError("Circuit breaker is open, refusing token operations")
        
        # Synchronize token refresh to prevent concurrent authentication attempts
        with self.token_manager._refresh_lock:
            # Try to load stored token first (may have been refreshed by another thread)
            stored_token = self.token_manager.load_stored_token()
            
            if stored_token and not stored_token.expires_soon():
                self._current_token = stored_token.access_token
                return self._current_token
            
            # If token expires soon or doesn't exist, get new token
            logger.debug("Token expired or expires soon, authenticating")
            return await self._authenticate_and_store()
    
    async def _authenticate_and_store(self) -> str:
        """Authenticate with server and store token persistently with retry logic."""
        decrypted_creds = self.credentials.decrypt()
        
        # Implement exponential backoff retry
        for attempt in range(self.MAX_RETRIES):
            try:
                # Rate limiting: acquire semaphore before making request
                with self._request_semaphore:
                    auth_response = await self.session.post(
                        urljoin(self.server_url, '/api/auth/login'),
                        json={
                            'username': decrypted_creds.username,
                            'password': decrypted_creds.password
                        },
                        headers={
                            'User-Agent': f'CIDX-Client/1.0',
                            'Accept': 'application/json',
                            'Content-Type': 'application/json'
                        }
                    )
                
                # Record successful network operation for circuit breaker
                self._record_circuit_breaker_success()
                
                if auth_response.status_code == 200:
                    token_data = auth_response.json()
                    
                    # Validate required fields in response
                    if 'access_token' not in token_data:
                        raise AuthenticationError("Server response missing access_token")
                    
                    access_token = token_data['access_token']
                    expires_in = token_data.get('expires_in', 3600)  # Default 1 hour
                    refresh_token = token_data.get('refresh_token')
                    
                    # Validate token format (basic JWT structure check)
                    if not access_token or access_token.count('.') != 2:
                        raise AuthenticationError("Server returned invalid JWT token format")
                    
                    # Store token persistently
                    self.token_manager.store_token(access_token, expires_in, refresh_token)
                    
                    self._current_token = access_token
                    logger.debug(f"Authentication successful, token expires in {expires_in} seconds")
                    return access_token
                
                elif auth_response.status_code == 401:
                    # Credential error - don't retry
                    raise AuthenticationError("Invalid credentials - check username and password")
                
                elif auth_response.status_code == 429:
                    # Rate limited - implement longer backoff
                    retry_after = auth_response.headers.get('Retry-After', '60')
                    try:
                        backoff_time = min(float(retry_after), self.RETRY_BACKOFF_MAX)
                    except ValueError:
                        backoff_time = 60.0
                    
                    if attempt < self.MAX_RETRIES - 1:
                        logger.warning(f"Rate limited, backing off for {backoff_time} seconds")
                        await asyncio.sleep(backoff_time)
                        continue
                    else:
                        raise AuthenticationError("Rate limited - too many authentication attempts")
                
                elif 500 <= auth_response.status_code < 600:
                    # Server error - retry with backoff
                    if attempt < self.MAX_RETRIES - 1:
                        backoff_time = min(
                            self.RETRY_BACKOFF_FACTOR ** attempt,
                            self.RETRY_BACKOFF_MAX
                        )
                        logger.warning(f"Server error {auth_response.status_code}, retrying in {backoff_time} seconds")
                        await asyncio.sleep(backoff_time)
                        continue
                    else:
                        raise AuthenticationError(f"Server error: {auth_response.status_code}")
                
                else:
                    # Other client errors - don't retry
                    raise AuthenticationError(f"Authentication failed with status {auth_response.status_code}")
                    
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
                # Network errors - record failure and retry
                self._record_circuit_breaker_failure()
                
                if attempt < self.MAX_RETRIES - 1:
                    backoff_time = min(
                        self.RETRY_BACKOFF_FACTOR ** attempt,
                        self.RETRY_BACKOFF_MAX
                    )
                    logger.warning(f"Network error during authentication: {e}, retrying in {backoff_time} seconds")
                    await asyncio.sleep(backoff_time)
                    continue
                else:
                    raise NetworkError(f"Network error during authentication: {e}")
            
            except Exception as e:
                # Unexpected errors - don't retry
                self._record_circuit_breaker_failure()
                raise AuthenticationError(f"Unexpected error during authentication: {e}")
        
        # Should not reach here due to loop logic, but safety fallback
        raise AuthenticationError("Authentication failed after all retry attempts")
```

## 🧪 **Testing Requirements**

### Unit Tests
- ✅ Token storage and retrieval with file persistence (64KB size limit enforcement)
- ✅ Token expiration validation with 30-second clock skew tolerance
- ✅ File permission verification (600) across Windows/Linux/macOS
- ✅ Atomic file operations with platform-specific rename behavior
- ✅ Concurrent access handling with fcntl.LOCK_NB retry logic (50 attempts)
- ✅ Secure memory cleanup validation (3 iterations of overwriting)
- ✅ JWT algorithm validation (RS256 enforcement)
- ✅ Token lifetime validation (24-hour maximum constraint)

### Integration Tests
- ✅ End-to-end token persistence across CLI process restarts
- ✅ Token refresh synchronization with threading.RLock
- ✅ Re-authentication fallback with exponential backoff (2.0 factor, 60s max)
- ✅ Multiple concurrent CIDX commands sharing token state (10 concurrent limit)
- ✅ Circuit breaker behavior (5 failures → 300s recovery timeout)
- ✅ Rate limiting with semaphore-based request control
- ✅ HTTP/2 connection pooling (5 keepalive, 10 max connections)

### Security Tests  
- ✅ Token encryption with project-specific PBKDF2 key derivation
- ✅ File permission enforcement (0o600) and automatic correction
- ✅ Token file corruption recovery with secure cleanup
- ✅ Cross-project token isolation verification
- ✅ JWT token format validation (3-part structure verification)
- ✅ SSL certificate verification enforcement
- ✅ Sensitive data memory clearing validation

### Performance Tests
- ✅ Token file I/O performance with 60-second cache TTL
- ✅ Concurrent token access with threading locks (no deadlocks)
- ✅ File locking overhead measurement (5-second timeout)
- ✅ Network timeout compliance (10s connect, 30s read, 10s write, 5s pool)
- ✅ Circuit breaker performance impact measurement
- ✅ Memory usage validation with secure cleanup

### Reliability Tests
- ✅ Circuit breaker failure threshold accuracy (exactly 5 failures)
- ✅ Exponential backoff timing validation (2.0^attempt up to 60s)
- ✅ Rate limiting behavior under load (429 response handling)
- ✅ Token refresh race condition prevention
- ✅ File system full scenario handling
- ✅ Network partition recovery testing

## 📊 **Definition of Done**

### Core Functionality
- ✅ Persistent JWT token storage in .code-indexer/.token with 64KB limit
- ✅ Encrypted token storage using project-specific PBKDF2 keys  
- ✅ Automatic token refresh with 300-second buffer and immediate storage
- ✅ Re-authentication fallback with 3-attempt retry and exponential backoff
- ✅ Thread-safe token file management with atomic operations and fcntl locking

### Security Requirements
- ✅ Secure file permissions (0o600) with automatic enforcement
- ✅ RS256 JWT algorithm validation and 24-hour lifetime limits
- ✅ Secure memory management with 3-iteration overwriting
- ✅ SSL certificate verification enforcement
- ✅ Cross-project credential isolation validation

### Reliability Requirements  
- ✅ Circuit breaker implementation (5 failures → 300s recovery)
- ✅ Request rate limiting with 10 concurrent request semaphore
- ✅ Network timeout configuration (10s/30s/10s/5s for connect/read/write/pool)
- ✅ HTTP/2 connection pooling with 5 keepalive, 10 max connections
- ✅ Exponential backoff retry (2.0 factor, 60s maximum, 3 attempts)

### Performance Requirements
- ✅ Token caching with 60-second TTL to minimize file I/O
- ✅ File locking timeout of 5 seconds to prevent deadlocks  
- ✅ Memory footprint optimization with immediate cleanup
- ✅ Network connection reuse with 30-second keepalive expiry

### Testing Requirements
- ✅ Unit test coverage >95% including all error paths
- ✅ Integration testing with real network conditions and timeouts
- ✅ Security testing validates all cryptographic constraints
- ✅ Performance testing confirms <100ms token retrieval from cache
- ✅ Reliability testing validates circuit breaker and retry behavior
- ✅ Cross-platform testing on Windows, Linux, and macOS
- ✅ Concurrency testing with 50+ simultaneous operations

### Operational Requirements
- ✅ Comprehensive logging with appropriate levels (DEBUG/INFO/WARNING/ERROR)
- ✅ Metrics collection for token refresh rates and failure counts
- ✅ Error handling provides actionable user guidance
- ✅ Graceful degradation when token storage unavailable
- ✅ Documentation includes troubleshooting for common scenarios