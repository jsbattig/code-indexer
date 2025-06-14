"""
Authentication module for Test Project 2
Handles user authentication and session management.
"""

import hashlib
import secrets
import time
from typing import Dict, Optional

class AuthManager:
    def __init__(self):
        self.users: Dict[str, Dict] = {}
        self.sessions: Dict[str, Dict] = {}
        self.session_timeout = 3600  # 1 hour
    
    def hash_password(self, password: str) -> str:
        """Hash a password using SHA-256."""
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}:{password_hash}"
    
    def verify_password(self, password: str, stored_hash: str) -> bool:
        """Verify a password against stored hash."""
        try:
            salt, password_hash = stored_hash.split(':')
            computed_hash = hashlib.sha256((password + salt).encode()).hexdigest()
            return computed_hash == password_hash
        except ValueError:
            return False
    
    def register_user(self, username: str, password: str, email: str) -> bool:
        """Register a new user."""
        if username in self.users:
            return False
        
        self.users[username] = {
            'password_hash': self.hash_password(password),
            'email': email,
            'created_at': time.time(),
            'last_login': None
        }
        return True
    
    def authenticate(self, username: str, password: str) -> Optional[str]:
        """Authenticate user and return session token."""
        if username not in self.users:
            return None
        
        user = self.users[username]
        if not self.verify_password(password, user['password_hash']):
            return None
        
        # Create session
        session_token = secrets.token_urlsafe(32)
        self.sessions[session_token] = {
            'username': username,
            'created_at': time.time(),
            'last_activity': time.time()
        }
        
        # Update last login
        user['last_login'] = time.time()
        
        return session_token
    
    def validate_session(self, session_token: str) -> Optional[str]:
        """Validate session token and return username."""
        if session_token not in self.sessions:
            return None
        
        session = self.sessions[session_token]
        current_time = time.time()
        
        # Check if session expired
        if current_time - session['last_activity'] > self.session_timeout:
            del self.sessions[session_token]
            return None
        
        # Update last activity
        session['last_activity'] = current_time
        return session['username']
    
    def logout(self, session_token: str) -> bool:
        """Logout user and invalidate session."""
        if session_token in self.sessions:
            del self.sessions[session_token]
            return True
        return False
    
    def get_user_info(self, username: str) -> Optional[Dict]:
        """Get user information (excluding password)."""
        if username not in self.users:
            return None
        
        user = self.users[username].copy()
        del user['password_hash']
        return user
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions."""
        current_time = time.time()
        expired_sessions = []
        
        for token, session in self.sessions.items():
            if current_time - session['last_activity'] > self.session_timeout:
                expired_sessions.append(token)
        
        for token in expired_sessions:
            del self.sessions[token]

def create_auth_middleware(auth_manager: AuthManager):
    """Create authentication middleware."""
    def auth_middleware(handler, method, path, query_params):
        # Skip auth for login/register endpoints
        if path in ['/login', '/register', '/']:
            return True
        
        # Check for session token in headers
        session_token = None
        if hasattr(handler, 'headers'):
            session_token = handler.headers.get('Authorization')
        
        if not session_token:
            handler.send_error(401, "Unauthorized")
            return False
        
        # Validate session
        username = auth_manager.validate_session(session_token)
        if not username:
            handler.send_error(401, "Invalid session")
            return False
        
        # Add username to handler for use in routes
        handler.username = username
        return True
    
    return auth_middleware