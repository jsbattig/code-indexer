# Story: Add Token Refresh Endpoint

## User Story
As an **API user**, I want to **refresh my authentication token without re-entering credentials** so that **I can maintain seamless access while ensuring security**.

## Problem Context
Currently, when JWT tokens expire, users must re-authenticate with username/password. This creates poor user experience and increases password exposure. A refresh token mechanism is needed.

## Acceptance Criteria

### Scenario 1: Successful Token Refresh
```gherkin
Given I have a valid refresh token
  And my access token has expired
When I send POST request to "/api/auth/refresh" with refresh token
Then the response status should be 200 OK
  And I should receive a new access token
  And I should receive a new refresh token
  And the old refresh token should be invalidated
  And the new access token should be valid for 15 minutes
```

### Scenario 2: Invalid Refresh Token
```gherkin
Given I have an invalid or expired refresh token
When I send POST request to "/api/auth/refresh"
Then the response status should be 401 Unauthorized
  And the response should indicate "Invalid refresh token"
  And an audit log should record the failed attempt
```

### Scenario 3: Revoked Refresh Token
```gherkin
Given I had a valid refresh token
  And the token was revoked due to password change
When I send POST request to "/api/auth/refresh"
Then the response status should be 401 Unauthorized
  And the response should indicate "Token has been revoked"
  And I should be required to re-authenticate
```

### Scenario 4: Token Family Detection
```gherkin
Given I have refresh token "A" that was already used to get token "B"
When I try to use refresh token "A" again (replay attack)
Then the response status should be 401 Unauthorized
  And ALL tokens in the family should be revoked
  And a security alert should be triggered
  And the user should be notified of potential breach
```

### Scenario 5: Concurrent Refresh Attempts
```gherkin
Given I have a valid refresh token
When I send two refresh requests simultaneously
Then only one should succeed with new tokens
  And the other should fail with 409 Conflict
  And no token duplication should occur
```

## Technical Implementation Details

### Token Refresh Implementation
```
from datetime import datetime, timedelta
import jwt
import uuid
from typing import Optional

class TokenService:
    def __init__(self):
        self.access_token_expire = timedelta(minutes=15)
        self.refresh_token_expire = timedelta(days=7)
        self.secret_key = settings.SECRET_KEY
        self.algorithm = "HS256"
    
    async def create_token_pair(self, user_id: str) -> Dict[str, str]:
        """Create new access and refresh token pair"""
        // Generate unique token family ID
        family_id = str(uuid.uuid4())
        
        // Create access token
        access_payload = {
            "sub": user_id,
            "type": "access",
            "exp": datetime.utcnow() + self.access_token_expire,
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4()),
            "family": family_id
        }
        access_token = jwt.encode(access_payload, self.secret_key, self.algorithm)
        
        // Create refresh token
        refresh_payload = {
            "sub": user_id,
            "type": "refresh",
            "exp": datetime.utcnow() + self.refresh_token_expire,
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4()),
            "family": family_id
        }
        refresh_token = jwt.encode(refresh_payload, self.secret_key, self.algorithm)
        
        // Store refresh token in database
        await self.store_refresh_token(
            user_id=user_id,
            token_id=refresh_payload["jti"],
            family_id=family_id,
            expires_at=refresh_payload["exp"]
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire.seconds
        }

@router.post("/api/auth/refresh")
async function refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    try:
        // Decode refresh token
        payload = jwt.decode(
            request.refresh_token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        
        // Validate token type
        if payload.get("type") != "refresh":
            raise HTTPException(401, "Invalid token type")
        
        // Check if token exists and is valid
        stored_token = await db.query(RefreshToken).filter(
            RefreshToken.token_id == payload["jti"],
            RefreshToken.user_id == payload["sub"],
            RefreshToken.revoked == False
        ).with_for_update().first()
        
        if not stored_token:
            // Token not found or already used
            await handle_token_reuse_attack(payload["family"], db)
            raise HTTPException(401, "Invalid refresh token")
        
        // Check if token is expired
        if stored_token.expires_at < datetime.utcnow():
            raise HTTPException(401, "Refresh token expired")
        
        // Revoke old refresh token
        stored_token.revoked = True
        stored_token.revoked_at = datetime.utcnow()
        
        // Create new token pair
        token_service = TokenService()
        new_tokens = await token_service.create_token_pair(payload["sub"])
        
        // Link new token to same family
        new_tokens["family_id"] = payload["family"]
        
        // Commit transaction
        db.commit()
        
        // Log successful refresh
        await log_audit_event(
            user_id=payload["sub"],
            event_type="token_refreshed",
            details={"old_token_id": payload["jti"]}
        )
        
        return new_tokens
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid refresh token")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh failed", exc_info=e)
        raise HTTPException(500, "Internal server error")

async function handle_token_reuse_attack(family_id: str, db: Session):
    """Handle potential token reuse attack by revoking entire family"""
    logger.warning(f"Potential token reuse attack detected for family {family_id}")
    
    // Revoke all tokens in family
    await db.query(RefreshToken).filter(
        RefreshToken.family_id == family_id
    ).update({
        "revoked": True,
        "revoked_at": datetime.utcnow(),
        "revoke_reason": "token_reuse_detected"
    })
    
    // Get user ID from any token in family
    token = await db.query(RefreshToken).filter(
        RefreshToken.family_id == family_id
    ).first()
    
    if token:
        // Log security event
        await log_security_alert(
            user_id=token.user_id,
            alert_type="token_reuse_attack",
            details={"family_id": family_id}
        )
        
        // Send notification to user
        user = await db.query(User).get(token.user_id)
        if user:
            await send_security_alert_email(
                user.email,
                "Suspicious activity detected on your account"
            )
```

### Database Schema
```sql
CREATE TABLE refresh_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    family_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP,
    revoke_reason TEXT,
    ip_address TEXT,
    user_agent TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_refresh_tokens_token_id ON refresh_tokens(token_id);
CREATE INDEX idx_refresh_tokens_family_id ON refresh_tokens(family_id);
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
```

## Testing Requirements

### Unit Tests
- [ ] Test token pair generation
- [ ] Test refresh token validation
- [ ] Test token expiration handling
- [ ] Test token family tracking
- [ ] Test concurrent refresh handling

### Security Tests
- [ ] Test token reuse detection
- [ ] Test family revocation
- [ ] Test JWT signature validation
- [ ] Test timing attacks

### Integration Tests
- [ ] Test with real database
- [ ] Test audit logging
- [ ] Test email notifications
- [ ] Test rate limiting

## Definition of Done
- [ ] POST /api/auth/refresh endpoint implemented
- [ ] Token pair generation working
- [ ] Refresh token rotation implemented
- [ ] Token family tracking active
- [ ] Reuse attack detection working
- [ ] Audit logging complete
- [ ] Unit test coverage > 90%
- [ ] Security tests pass
- [ ] Documentation updated

## Performance Criteria
- Token generation < 50ms
- Token validation < 10ms
- Support 1000 concurrent refreshes
- Database queries optimized with indexes