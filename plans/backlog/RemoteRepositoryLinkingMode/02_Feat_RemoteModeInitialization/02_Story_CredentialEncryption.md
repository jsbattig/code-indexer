# User Story: Credential Encryption

## 📋 **User Story**

As a **CIDX user**, I want **my remote server credentials encrypted with project-specific keys**, so that **my authentication information is secure and cannot be reused across different projects or accessed by unauthorized users**.

## 🎯 **Business Value**

Provides robust security for remote credentials through project-specific encryption. Prevents credential theft, unauthorized access, and credential reuse attacks while maintaining usability for legitimate operations.

## 📝 **Acceptance Criteria**

### Given: PBKDF2 Encryption Implementation
**When** I initialize remote mode with credentials  
**Then** the system encrypts credentials using PBKDF2 with 100,000 iterations  
**And** derives encryption key from username + repo path + server URL combination  
**And** uses cryptographically secure salt generation  
**And** never stores plaintext credentials anywhere  

### Given: Project-Specific Key Derivation
**When** I use the same credentials in different projects  
**Then** each project generates different encryption keys  
**And** credentials from one project cannot decrypt another project's data  
**And** key derivation includes project path, server URL, and username  
**And** prevents cross-project credential compromise  

### Given: Secure Storage Implementation
**When** I examine credential storage  
**Then** encrypted credentials are stored in .code-indexer/.creds  
**And** file permissions are set to user-only read/write (600)  
**And** no credential information appears in logs or temporary files  
**And** secure memory handling prevents credential leakage  

### Given: Credential Retrieval and Validation
**When** I access remote repositories  
**Then** the system safely decrypts credentials for API calls  
**And** validation occurs without exposing plaintext credentials  
**And** decryption failures result in clear re-authentication guidance  
**And** memory is securely cleared after credential use  

## 🏗️ **Technical Implementation**

### Project-Specific Credential Manager
```python
import hashlib
import secrets
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes
from pathlib import Path
from typing import NamedTuple

class DecryptedCredentials(NamedTuple):
    username: str
    password: str
    server_url: str

class ProjectCredentialManager:
    """Manages project-specific credential encryption and storage."""
    
    def __init__(self):
        self.iterations = 100_000  # PBKDF2 iterations
        self.key_length = 32       # AES-256 key length
    
    def _derive_project_key(self, username: str, repo_path: str, server_url: str, salt: bytes) -> bytes:
        """Derive project-specific encryption key using PBKDF2."""
        # Create unique input combining user, project, and server
        key_input = f"{username}:{repo_path}:{server_url}".encode('utf-8')
        
        # Use PBKDF2 with SHA256 for key derivation
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.key_length,
            salt=salt,
            iterations=self.iterations,
        )
        
        return kdf.derive(key_input)
    
    def encrypt_credentials(
        self, 
        username: str, 
        password: str, 
        server_url: str, 
        repo_path: str
    ) -> bytes:
        """Encrypt credentials with project-specific key derivation."""
        try:
            # Generate cryptographically secure salt
            salt = secrets.token_bytes(32)
            
            # Derive project-specific encryption key
            key = self._derive_project_key(username, repo_path, server_url, salt)
            
            # Create credential data to encrypt
            credential_data = {
                'username': username,
                'password': password,
                'server_url': server_url,
                'created_at': time.time()
            }
            
            # Serialize to JSON bytes
            plaintext = json.dumps(credential_data).encode('utf-8')
            
            # Generate initialization vector
            iv = secrets.token_bytes(16)
            
            # Encrypt using AES-256-CBC
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv)
            )
            encryptor = cipher.encryptor()
            
            # PKCS7 padding
            pad_length = 16 - (len(plaintext) % 16)
            padded_plaintext = plaintext + bytes([pad_length]) * pad_length
            
            # Encrypt the data
            ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()
            
            # Combine salt, IV, and ciphertext for storage
            encrypted_data = salt + iv + ciphertext
            
            # Clear sensitive data from memory
            del key, plaintext, padded_plaintext
            
            return encrypted_data
            
        except Exception as e:
            raise CredentialEncryptionError(f"Failed to encrypt credentials: {str(e)}")
    
    def decrypt_credentials(self, encrypted_data: bytes, username: str, repo_path: str, server_url: str) -> DecryptedCredentials:
        """Decrypt credentials using project-specific key derivation."""
        try:
            # Extract components from encrypted data
            salt = encrypted_data[:32]
            iv = encrypted_data[32:48]
            ciphertext = encrypted_data[48:]
            
            # Derive the same project-specific key
            key = self._derive_project_key(username, repo_path, server_url, salt)
            
            # Decrypt using AES-256-CBC
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv)
            )
            decryptor = cipher.decryptor()
            
            # Decrypt the data
            padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Remove PKCS7 padding
            pad_length = padded_plaintext[-1]
            plaintext = padded_plaintext[:-pad_length]
            
            # Parse credential data
            credential_data = json.loads(plaintext.decode('utf-8'))
            
            # Clear sensitive data from memory
            del key, padded_plaintext, plaintext
            
            return DecryptedCredentials(
                username=credential_data['username'],
                password=credential_data['password'],
                server_url=credential_data['server_url']
            )
            
        except Exception as e:
            raise CredentialDecryptionError(f"Failed to decrypt credentials: {str(e)}")
```

### Secure Storage Implementation
```python
def store_encrypted_credentials(project_root: Path, encrypted_data: bytes):
    """Store encrypted credentials with secure file permissions."""
    config_dir = project_root / ".code-indexer"
    config_dir.mkdir(mode=0o700, exist_ok=True)  # Directory accessible only to owner
    
    credentials_path = config_dir / ".creds"
    
    # Write encrypted data atomically
    temp_path = credentials_path.with_suffix('.tmp')
    try:
        with open(temp_path, 'wb') as f:
            f.write(encrypted_data)
        
        # Set secure permissions (user read/write only)
        temp_path.chmod(0o600)
        
        # Atomic move to final location
        temp_path.rename(credentials_path)
        
    except Exception:
        # Clean up temporary file on error
        if temp_path.exists():
            temp_path.unlink()
        raise

def load_encrypted_credentials(project_root: Path) -> bytes:
    """Load encrypted credentials from secure storage."""
    credentials_path = project_root / ".code-indexer" / ".creds"
    
    if not credentials_path.exists():
        raise CredentialNotFoundError("No stored credentials found")
    
    # Verify file permissions
    file_mode = credentials_path.stat().st_mode
    if file_mode & 0o077:  # Check if group/other permissions are set
        raise InsecureCredentialStorageError("Credential file has insecure permissions")
    
    with open(credentials_path, 'rb') as f:
        return f.read()
```

### Integration with Remote Configuration
```python
class RemoteConfig:
    """Remote configuration with encrypted credential management."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.credential_manager = ProjectCredentialManager()
        self._config_data = self._load_config()
    
    def get_decrypted_credentials(self) -> DecryptedCredentials:
        """Get decrypted credentials for API operations."""
        encrypted_data = load_encrypted_credentials(self.project_root)
        
        return self.credential_manager.decrypt_credentials(
            encrypted_data,
            self._config_data['username'],
            str(self.project_root),
            self._config_data['server_url']
        )
```

## 🧪 **Testing Requirements**

### Unit Tests
- ✅ PBKDF2 key derivation with project-specific inputs
- ✅ AES encryption/decryption round-trip testing
- ✅ Project isolation (same creds, different projects produce different keys)
- ✅ Secure memory handling and cleanup

### Security Tests
- ✅ Credential file permission validation
- ✅ Cross-project credential isolation verification
- ✅ Salt uniqueness and randomness validation
- ✅ Memory leak detection for sensitive data

### Integration Tests
- ✅ End-to-end credential encryption during initialization
- ✅ Credential retrieval during API operations
- ✅ Error handling for corrupted credential files
- ✅ File system permission handling across platforms

## 📊 **Definition of Done**

- ✅ ProjectCredentialManager with PBKDF2 encryption (100,000 iterations)
- ✅ Project-specific key derivation using username + repo path + server URL
- ✅ Secure AES-256-CBC encryption implementation
- ✅ Secure file storage with proper permissions (600)
- ✅ Cross-project credential isolation validation
- ✅ Secure memory handling with sensitive data cleanup
- ✅ Comprehensive error handling for encryption/decryption failures
- ✅ Integration with remote initialization and API client systems
- ✅ Security testing validates encryption strength and isolation
- ✅ Code review confirms cryptographic implementation correctness