# Story: Standardize Auth Error Responses

## User Story
As a **security engineer**, I want **authentication errors to not reveal sensitive information** so that **attackers cannot enumerate users or gather system intelligence**.

## Problem Context
Current authentication error messages reveal whether usernames exist, timing differences expose valid accounts, and detailed errors provide too much information to potential attackers.

## Acceptance Criteria

### Scenario 1: Login with Invalid Username
```gherkin
Given no user exists with username "nonexistent"
When I send POST request to "/api/auth/login" with:
  """
  {
    "username": "nonexistent",
    "password": "anypassword"
  }
  """
Then the response status should be 401 Unauthorized
  And the response should contain generic message "Invalid credentials"
  And the response time should be ~100ms (same as valid username)
  And no information about user existence should be revealed
```

### Scenario 2: Login with Valid Username but Wrong Password
```gherkin
Given user "alice" exists
When I send POST request to "/api/auth/login" with wrong password
Then the response status should be 401 Unauthorized
  And the response should contain generic message "Invalid credentials"
  And the message should be identical to invalid username response
  And the response time should be ~100ms (constant time)
```

### Scenario 3: Account Locked Response
```gherkin
Given user "bob" account is locked due to failed attempts
When I send POST request to "/api/auth/login" with correct credentials
Then the response status should be 401 Unauthorized
  And the response should contain generic message "Invalid credentials"
  And detailed lock reason should only be in secure logs
  And no lock status should be exposed to client
```

### Scenario 4: Registration with Existing Email
```gherkin
Given user already exists with email "existing@example.com"
When I send POST request to "/api/auth/register" with same email
Then the response status should be 200 OK
  And the response should indicate "Registration initiated"
  And a duplicate account email should be sent to the address
  And no immediate indication of existing account should be given
```

### Scenario 5: Password Reset for Non-Existent Email
```gherkin
Given no user exists with email "fake@example.com"
When I send POST request to "/api/auth/reset-password" with that email
Then the response status should be 200 OK
  And the response should indicate "Password reset email sent if account exists"
  And the response time should match existing email response time
  And no email should actually be sent
```

## Technical Implementation Details

### Standardized Error Response Handler
```
from enum import Enum
import time
import hashlib

class AuthErrorType(Enum):
    INVALID_CREDENTIALS = "invalid_credentials"
    ACCOUNT_LOCKED = "account_locked"
    EXPIRED_TOKEN = "expired_token"
    INVALID_TOKEN = "invalid_token"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"

class AuthErrorHandler:
    """Standardized authentication error handler"""
    
    // Generic messages that don't reveal information
    ERROR_MESSAGES = {
        AuthErrorType.INVALID_CREDENTIALS: "Invalid credentials",
        AuthErrorType.ACCOUNT_LOCKED: "Invalid credentials",
        AuthErrorType.EXPIRED_TOKEN: "Authentication required",
        AuthErrorType.INVALID_TOKEN: "Authentication required",
        AuthErrorType.INSUFFICIENT_PERMISSIONS: "Access denied"
    }
    
    @staticmethod
    async def handle_auth_error(
        error_type: AuthErrorType,
        internal_details: str = None,
        user_identifier: str = None,
        request_metadata: dict = None
    ) -> JSONResponse:
        """
        Handle authentication errors with consistent responses
        """
        // Log detailed error internally
        if internal_details:
            logger.warning(
                f"Auth error: {error_type.value}",
                extra={
                    "internal_details": internal_details,
                    "user_identifier": user_identifier,
                    "request_metadata": request_metadata
                }
            )
        
        // Return generic error to client
        return JSONResponse(
            status_code=401,
            content={
                "error": AuthErrorHandler.ERROR_MESSAGES[error_type],
                "code": error_type.value
            }
        )

@router.post("/api/auth/login")
async function secure_login(
    credentials: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    start_time = time.perf_counter()
    
    try:
        // Always perform full authentication flow for timing consistency
        user = await db.query(User).filter(
            User.username == credentials.username
        ).first()
        
        // Always hash password even if user doesn't exist
        if user:
            password_valid = pwd_context.verify(
                credentials.password,
                user.password_hash
            )
        else:
            // Perform dummy hash operation for timing consistency
            pwd_context.hash(credentials.password)
            password_valid = False
        
        // Check various failure conditions
        if not user or not password_valid:
            await ensure_constant_time(start_time)
            return await AuthErrorHandler.handle_auth_error(
                AuthErrorType.INVALID_CREDENTIALS,
                internal_details=f"Login failed for username: {credentials.username}",
                user_identifier=credentials.username,
                request_metadata={"ip": request.client.host}
            )
        
        if user.is_locked:
            await ensure_constant_time(start_time)
            return await AuthErrorHandler.handle_auth_error(
                AuthErrorType.ACCOUNT_LOCKED,
                internal_details=f"Locked account login attempt: {user.id}",
                user_identifier=str(user.id)
            )
        
        // Successful login
        tokens = await create_token_pair(user.id)
        
        await ensure_constant_time(start_time)
        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer"
        }
        
    except Exception as e:
        logger.error(f"Login error", exc_info=e)
        await ensure_constant_time(start_time)
        return await AuthErrorHandler.handle_auth_error(
            AuthErrorType.INVALID_CREDENTIALS
        )

@router.post("/api/auth/register")
async function secure_register(
    registration: RegistrationRequest,
    db: Session = Depends(get_db)
):
    """
    Secure registration that doesn't reveal existing accounts
    """
    // Check if user exists
    existing_user = await db.query(User).filter(
        or_(
            User.email == registration.email,
            User.username == registration.username
        )
    ).first()
    
    if existing_user:
        // Send email about duplicate attempt
        await send_duplicate_account_email(
            registration.email,
            existing_user.username
        )
        
        // Return same response as successful registration
        return {
            "message": "Registration initiated. Please check your email.",
            "status": "pending_verification"
        }
    
    // Create new user
    new_user = User(
        username=registration.username,
        email=registration.email,
        password_hash=pwd_context.hash(registration.password)
    )
    db.add(new_user)
    db.commit()
    
    // Send verification email
    await send_verification_email(new_user.email)
    
    return {
        "message": "Registration initiated. Please check your email.",
        "status": "pending_verification"
    }

@router.post("/api/auth/reset-password")
async function secure_password_reset(
    reset_request: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """
    Password reset that doesn't reveal account existence
    """
    user = await db.query(User).filter(
        User.email == reset_request.email
    ).first()
    
    if user:
        // Generate reset token and send email
        reset_token = generate_reset_token(user.id)
        await send_password_reset_email(user.email, reset_token)
    else:
        // Log attempt but don't reveal to client
        logger.info(f"Password reset attempted for non-existent email: {reset_request.email}")
    
    // Always return same response
    return {
        "message": "Password reset email sent if account exists",
        "status": "check_email"
    }

async function ensure_constant_time(
    start_time: float,
    target_seconds: float = 0.1
):
    """Ensure operation takes constant time"""
    elapsed = time.perf_counter() - start_time
    if elapsed < target_seconds:
        await asyncio.sleep(target_seconds - elapsed)
```

### Error Response Audit Configuration
```
# Logging configuration for security audit
SECURITY_LOG_CONFIG = {
    "version": 1,
    "handlers": {
        "security": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/var/log/cidx/security.log",
            "maxBytes": 10485760,
            "backupCount": 10,
            "formatter": "detailed"
        }
    },
    "loggers": {
        "security": {
            "handlers": ["security"],
            "level": "INFO"
        }
    }
}
```

## Testing Requirements

### Unit Tests
- [ ] Test error message consistency
- [ ] Test timing attack prevention
- [ ] Test error logging
- [ ] Test duplicate account handling
- [ ] Test password reset flow

### Security Tests
- [ ] Test user enumeration prevention
- [ ] Test timing consistency
- [ ] Test information leakage
- [ ] Test error response codes

### Integration Tests
- [ ] Test with real authentication flow
- [ ] Test email sending logic
- [ ] Test audit logging
- [ ] Test rate limiting integration

## Definition of Done
- [ ] All auth errors return generic messages
- [ ] Timing attacks prevented with constant-time operations
- [ ] User enumeration impossible through errors
- [ ] Detailed logging for security audit
- [ ] Email-based verification for sensitive operations
- [ ] Unit test coverage > 90%
- [ ] Security tests pass
- [ ] Penetration test shows no information leakage
- [ ] Documentation updated

## Security Checklist
- [ ] No user existence revealed in errors
- [ ] Constant-time operations for all auth paths
- [ ] Generic error messages for all failures
- [ ] Detailed internal logging maintained
- [ ] Email verification for account operations
- [ ] No sensitive data in client responses
- [ ] Rate limiting on all endpoints
- [ ] Security headers properly set