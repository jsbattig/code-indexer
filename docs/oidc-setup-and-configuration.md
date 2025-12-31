# OIDC/SSO Setup and Configuration Guide

## Overview

CIDX Server supports OpenID Connect (OIDC) authentication, enabling Single Sign-On (SSO) integration with enterprise identity providers. This guide covers setup with any OIDC-compliant provider and explains all available configuration options.

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration Reference](#configuration-reference)
- [Provider Setup Instructions](#provider-setup-instructions)
- [Email-Based Account Linking](#email-based-account-linking)
- [Just-In-Time (JIT) User Provisioning](#just-in-time-jit-user-provisioning)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Prerequisites

- CIDX Server installed and running
- Admin access to your identity provider (Keycloak, Azure AD, etc.)
- HTTPS-enabled deployment (required for OIDC security)

### Basic Setup Steps

1. **Configure your Identity Provider:**
   - Create a new OIDC/OAuth 2.0 client application
   - Set the redirect URI to: `https://your-cidx-server.com/auth/sso/callback`
   - Enable Authorization Code flow with PKCE
   - Request scopes: `openid`, `profile`, `email`
   - Note your client ID, client secret, and issuer URL

2. **Configure CIDX Server:**
   - Edit `~/.cidx-server/config.json`
   - Add the `oidc_provider_config` section (see [Configuration Reference](#configuration-reference))
   - Restart CIDX Server

3. **Test the Integration:**
   - Navigate to the login page
   - Click "Sign in with SSO"
   - Complete authentication at your identity provider
   - Verify you're redirected back and logged in

## Configuration Reference

### Configuration File Location

OIDC configuration is stored in `~/.cidx-server/config.json` under the `oidc_provider_config` key.

### Complete Configuration Schema

```json
{
  "oidc_provider_config": {
    "enabled": true,
    "provider_name": "Company SSO",
    "issuer_url": "https://idp.example.com/realms/main",
    "client_id": "cidx-server",
    "client_secret": "your-client-secret-here",
    "scopes": ["openid", "profile", "email"],
    "email_claim": "email",
    "username_claim": "preferred_username",
    "use_pkce": true,
    "require_email_verification": true,
    "enable_jit_provisioning": true,
    "default_role": "normal_user"
  }
}
```

### Configuration Field Reference

#### Core Settings

**`enabled`** (boolean, default: `false`)
- Master switch for OIDC authentication
- When `false`, SSO login button is hidden and all OIDC endpoints return 404
- Set to `true` to enable SSO integration

**`provider_name`** (string, default: `"SSO"`)
- Display name shown on the login page SSO button
- Examples: "Company SSO", "Keycloak", "Azure AD"
- Visible to end users in the login UI

**`issuer_url`** (string, required)
- OIDC issuer URL (base URL of your identity provider)
- Used for automatic discovery of provider metadata via `.well-known/openid-configuration`
- Examples:
  - Keycloak: `https://keycloak.example.com/realms/myrealm`
  - Azure AD: `https://login.microsoftonline.com/{tenant-id}/v2.0`

**`client_id`** (string, required)
- OAuth 2.0 client identifier provided by your identity provider
- Obtained when registering CIDX Server as a client application

**`client_secret`** (string, required)
- OAuth 2.0 client secret provided by your identity provider
- Keep this secure and never commit to version control
- Used for token exchange during authentication

#### Claims and Scopes

**`scopes`** (array of strings, default: `["openid", "profile", "email"]`)
- OAuth 2.0 scopes requested during authentication
- `openid` is required for OIDC
- `profile` provides username/name claims
- `email` provides email address (required for account linking)
- Add custom scopes as needed: `["openid", "profile", "email", "groups"]`

**`email_claim`** (string, default: `"email"`)
- Name of the claim containing user's email address
- Standard OIDC uses `email`, but some providers use different names
- Examples: `email`, `mail`, `emailAddress`

**`username_claim`** (string, default: `"preferred_username"`)
- Name of the claim to use for username during JIT provisioning
- Falls back to email prefix if claim is missing or invalid
- Common options: `preferred_username`, `username`, `login`, `email`

#### Security Settings

**`use_pkce`** (boolean, default: `true`)
- Enable Proof Key for Code Exchange (PKCE) for enhanced security
- Strongly recommended to keep enabled (prevents authorization code interception)
- Uses S256 challenge method

**`require_email_verification`** (boolean, default: `true`)
- Only auto-link accounts when provider confirms email is verified
- Checks `email_verified` claim from provider
- Prevents account takeover via unverified email addresses
- **Security critical:** Keep enabled unless you trust all emails from provider

#### User Provisioning

**`enable_jit_provisioning`** (boolean, default: `true`)
- Enable Just-In-Time (JIT) user provisioning
- When `true`: New users are automatically created on first login
- When `false`: Only existing CIDX users can login via SSO
- See [JIT User Provisioning](#just-in-time-jit-user-provisioning) for details

**`default_role`** (string, default: `"normal_user"`)
- Role assigned to JIT-provisioned users
- Valid values: `"normal_user"`, `"admin"`
- Does not affect existing users or email-linked accounts (they keep their existing role)

## Provider Setup Instructions

### Generic OIDC Provider Setup

These steps work for any OIDC-compliant identity provider:

1. **Create Client Application:**
   - Access your identity provider's admin console
   - Create a new "OAuth 2.0 / OIDC Client" or "Application"
   - Application type: "Web Application" or "Confidential Client"

2. **Configure Client Settings:**
   - **Redirect URI:** `https://your-cidx-server.com/auth/sso/callback` (exact URL)
   - **Grant Type:** Authorization Code
   - **PKCE:** Required (S256)
   - **Scopes:** `openid`, `profile`, `email` (minimum required)
   - **Client Authentication:** Client Secret (confidential client)

3. **Obtain Credentials:**
   - Copy the Client ID
   - Copy the Client Secret
   - Note the Issuer URL (usually shown in provider metadata or discovery URL)

4. **Configure Email Claims:**
   - Ensure `email` claim is included in ID token or userinfo response
   - Ensure `email_verified` claim is included and accurate
   - Map provider's email attribute to standard `email` claim

5. **Add to CIDX Config:**
   - Update `~/.cidx-server/config.json` with your provider details
   - Restart CIDX Server

### Keycloak Setup

1. **Create Realm (if needed):**
   ```
   Admin Console → Add Realm → Name: "cidx" → Create
   ```

2. **Create Client:**
   ```
   Clients → Create → Client ID: "cidx-server" → Save
   Settings Tab:
   - Access Type: confidential
   - Valid Redirect URIs: https://your-cidx-server.com/auth/sso/callback
   - Web Origins: https://your-cidx-server.com
   → Save
   ```

3. **Get Client Secret:**
   ```
   Credentials Tab → Copy "Secret"
   ```

4. **Configure Mappers (optional):**
   ```
   Mappers Tab → Add Builtin → Select: email, email verified, username → Add
   ```

5. **CIDX Configuration:**
   ```json
   {
     "oidc_provider_config": {
       "enabled": true,
       "provider_name": "Keycloak",
       "issuer_url": "https://keycloak.example.com/realms/cidx",
       "client_id": "cidx-server",
       "client_secret": "paste-secret-here"
     }
   }
   ```

### Azure AD / Microsoft Entra ID Setup

1. **Register Application:**
   ```
   Azure Portal → Microsoft Entra ID → App registrations → New registration
   Name: CIDX Server
   Supported account types: Accounts in this organizational directory only
   Redirect URI: Web → https://your-cidx-server.com/auth/sso/callback
   → Register
   ```

2. **Create Client Secret:**
   ```
   Certificates & secrets → New client secret → Add
   Copy the secret value immediately (shown only once)
   ```

3. **Configure API Permissions:**
   ```
   API permissions → Add a permission → Microsoft Graph → Delegated permissions
   → Select: openid, profile, email, User.Read → Add permissions
   ```

4. **Get Credentials:**
   ```
   Overview page:
   - Application (client) ID
   - Directory (tenant) ID
   ```

5. **CIDX Configuration:**
   ```json
   {
     "oidc_provider_config": {
       "enabled": true,
       "provider_name": "Azure AD",
       "issuer_url": "https://login.microsoftonline.com/{tenant-id}/v2.0",
       "client_id": "your-application-id",
       "client_secret": "your-client-secret"
     }
   }
   ```

## Email-Based Account Linking

### How It Works

When a user logs in via SSO, CIDX automatically links their SSO identity to an existing CIDX account if:

1. **Email match found:** User's SSO email matches an existing CIDX user's email
2. **Email is verified:** Provider confirms email is verified (`email_verified: true`)
3. **Unique match:** Only one CIDX account has that email address

This allows existing CIDX users to seamlessly transition to SSO authentication without creating duplicate accounts.

### Email Matching Algorithm

```
1. Extract email and email_verified from SSO provider
2. If email_verified is false:
   → Skip auto-linking (security protection)
   → Continue to JIT provisioning or error
3. Normalize email (lowercase, trim whitespace)
4. Search all CIDX users for matching email (case-insensitive)
5. If exactly one match found:
   → Link SSO identity to existing user
   → User retains existing role and permissions
   → Future logins use SSO
6. If zero or multiple matches:
   → Skip auto-linking
   → Continue to JIT provisioning or error
```

### User Data Storage

When an SSO identity is linked, CIDX stores:

**In `~/.cidx-server/users.json`:**
```json
{
  "john": {
    "role": "normal_user",
    "password_hash": "bcrypt_hash",
    "email": "john@example.com",
    "oidc_identity": {
      "subject": "oidc-user-id-12345",
      "email": "john@example.com",
      "linked_at": "2025-01-15T10:30:00Z",
      "last_login": "2025-01-20T14:22:00Z"
    }
  }
}
```

**In `~/.cidx-server/oidc_identities.db`:**
```sql
-- Fast lookup table for SSO subject → username mapping
INSERT INTO oidc_identity_links
  (username, subject, email, linked_at, last_login)
VALUES
  ('john', 'oidc-user-id-12345', 'john@example.com', '2025-01-15T10:30:00Z', '2025-01-20T14:22:00Z');
```

### Security Considerations

**Email Verification Requirement:**
- CIDX only auto-links accounts when `email_verified` is `true`
- This prevents account takeover via unverified email addresses
- Configure `require_email_verification: true` (default and recommended)

**Multiple Email Matches:**
- If multiple CIDX users share the same email, auto-linking is skipped
- This prevents ambiguous account linking
- Admin must manually resolve duplicate emails before SSO will work

**Existing Password Login:**
- After SSO linking, users can still use password login (if password is set)
- Password is NOT removed when SSO is linked
- Users with SSO-only accounts (JIT provisioned) have no password set

## Just-In-Time (JIT) User Provisioning

### Overview

JIT provisioning automatically creates new CIDX user accounts when someone logs in via SSO for the first time. This enables frictionless onboarding for organizations using SSO.

### When JIT Provisioning Triggers

JIT provisioning occurs when:
1. `enable_jit_provisioning: true` in config
2. User completes SSO authentication successfully
3. No existing CIDX user matches their email
4. No existing SSO identity link for their subject ID

### Username Generation

CIDX generates usernames using this priority order:

1. **`preferred_username` claim:** If present and valid (alphanumeric + underscores, not already taken)
2. **Email prefix:** Extract part before `@` symbol, sanitize, ensure uniqueness
3. **Subject claim:** Use SSO subject ID, sanitize, ensure uniqueness
4. **Fallback:** Generate `sso_user_<random>` if all else fails

**Username Conflict Resolution:**
- If username exists, append `_2`, `_3`, etc. until unique
- Example: `john` → `john_2` → `john_3`

### User Role Assignment

JIT-provisioned users receive the role specified in `default_role` config:
- `"normal_user"` (default): Standard user access
- `"admin"`: Full administrative access (use cautiously)

**Important:** Email-linked accounts (users who existed before SSO) keep their existing role. JIT provisioning role only applies to newly created users.

### JIT Provisioned User Characteristics

Users created via JIT provisioning have:
- **No password:** Cannot login with password until admin sets one
- **Email address:** From SSO provider
- **SSO identity linked:** Immediate SSO access on creation
- **Default role:** As specified in config
- **Standard user record:** Identical to manually created users otherwise

### Disabling JIT Provisioning

To restrict SSO to existing users only:

```json
{
  "oidc_provider_config": {
    "enable_jit_provisioning": false
  }
}
```

When disabled:
- Only users with existing CIDX accounts can login via SSO
- Email-based auto-linking still works
- New SSO users receive an error message directing them to contact admin

### Example: Complete Authentication Flow

**Scenario:** User `alice@company.com` logs in via SSO for the first time.

```
1. Alice clicks "Sign in with SSO" on login page
2. Redirected to identity provider (e.g., Keycloak)
3. Alice authenticates with Keycloak credentials
4. Keycloak redirects back with authorization code
5. CIDX exchanges code for access token
6. CIDX retrieves user info from Keycloak:
   {
     "sub": "keycloak-12345",
     "email": "alice@company.com",
     "email_verified": true,
     "preferred_username": "alice"
   }
7. CIDX checks for existing account:
   - No user with email "alice@company.com" found
   - No SSO identity link for subject "keycloak-12345" found
8. JIT provisioning triggers:
   - Generate username: "alice" (from preferred_username)
   - Check uniqueness: "alice" is available
   - Create user with role "normal_user"
   - Link SSO identity to new user
9. Create JWT session token
10. Set cidx_session cookie
11. Redirect Alice to dashboard
12. Alice is now logged in with username "alice"
```

## Security Considerations

### HTTPS Requirement

OIDC requires HTTPS for security. Running CIDX Server over plain HTTP will:
- Expose client secrets in transit
- Expose session cookies to interception
- Violate OAuth 2.0 security best practices
- Cause some providers to reject redirect URIs

**Recommendation:** Always deploy CIDX Server behind HTTPS (use reverse proxy with TLS certificate).

### Client Secret Protection

The `client_secret` in your config is sensitive:
- Never commit config files with secrets to version control
- Use file permissions to restrict access: `chmod 600 ~/.cidx-server/config.json`
- Rotate secrets periodically (update in both provider and CIDX config)
- Use environment-specific secrets (dev, staging, prod)

### Email Verification Enforcement

Keep `require_email_verification: true` unless you have a specific reason to disable it:

**Why this matters:**
- Prevents account takeover via unverified emails
- Ensures user actually controls the email address
- Standard security practice for SSO implementations

**When to disable:**
- Your identity provider doesn't provide `email_verified` claim
- You trust all email addresses from your provider implicitly
- You're using a custom email validation process

### PKCE (Proof Key for Code Exchange)

PKCE protects against authorization code interception attacks:
- Always keep `use_pkce: true` (default)
- Uses S256 challenge method (SHA-256)
- Required by OAuth 2.0 security best practices
- Supported by all modern identity providers

### Cookie Security

CIDX sets secure cookies for sessions:
- `HttpOnly`: Prevents JavaScript access (XSS protection)
- `Secure`: Only sent over HTTPS
- `SameSite=Lax`: CSRF protection

### Session Management

After SSO authentication:
- CIDX issues standard JWT session tokens (same as password login)
- No ongoing communication with identity provider
- Session expiration: 10 hours (configurable)
- User logged out when JWT expires
- SSO re-authentication required on next login

## Troubleshooting

### SSO Button Not Appearing

**Symptom:** Login page shows only username/password form, no SSO button.

**Causes and Solutions:**

1. **OIDC not enabled:**
   - Check `oidc_provider_config.enabled` is `true` in config.json
   - Restart CIDX Server after config changes

2. **Config syntax error:**
   - Validate JSON syntax: `python3 -m json.tool ~/.cidx-server/config.json`
   - Check logs for config parsing errors

3. **Server initialization failed:**
   - Check server logs for OIDC initialization errors
   - Verify `issuer_url` is accessible from server

### Invalid Redirect URI Error

**Symptom:** Provider shows "Invalid redirect URI" or "Redirect URI mismatch" error.

**Causes and Solutions:**

1. **Mismatch between provider and CIDX:**
   - Provider expects: `https://cidx.example.com/auth/sso/callback`
   - CIDX uses: `https://cidx.example.com/auth/sso/callback`
   - Ensure exact match (including https vs http, trailing slash)

2. **Localhost vs production URL:**
   - Development: Register `http://localhost:8000/auth/sso/callback`
   - Production: Register `https://your-domain.com/auth/sso/callback`
   - Many providers require separate clients for dev/prod

3. **Multiple server instances:**
   - If running multiple CIDX servers, register all redirect URIs
   - Or use a single canonical URL with load balancer

### Authentication Completes But Login Fails

**Symptom:** SSO authentication succeeds at provider, but CIDX shows error or doesn't log in.

**Causes and Solutions:**

1. **Email not verified:**
   - Check provider sends `email_verified: true` claim
   - Temporarily disable: `require_email_verification: false` (testing only)
   - Configure provider to mark emails as verified

2. **Missing email claim:**
   - Provider might use non-standard claim name
   - Check provider documentation for email claim name
   - Update config: `"email_claim": "mail"` or `"email_claim": "emailAddress"`

3. **JIT provisioning disabled and no existing account:**
   - Enable JIT: `"enable_jit_provisioning": true`
   - Or create CIDX account manually first, then SSO will auto-link

4. **Username generation failed:**
   - Check logs for username generation errors
   - Ensure `preferred_username` claim exists or email is valid

### Discovery Endpoint Unreachable

**Symptom:** Server logs show "Failed to discover OIDC metadata" or connection timeout.

**Causes and Solutions:**

1. **Incorrect issuer URL:**
   - Verify issuer URL is correct (check provider documentation)
   - Test manually: `curl https://your-issuer/.well-known/openid-configuration`

2. **Network connectivity:**
   - Ensure CIDX Server can reach provider (check firewall, proxy)
   - Test from server: `wget https://your-issuer/.well-known/openid-configuration`

3. **Provider doesn't support discovery:**
   - CIDX requires providers that support `.well-known/openid-configuration`
   - Verify your provider is OIDC-compliant
   - Most modern providers (Keycloak, Azure AD, etc.) support automatic discovery

### Token Exchange Failed

**Symptom:** Logs show "Failed to exchange authorization code for tokens" or 400/401 errors.

**Causes and Solutions:**

1. **Invalid client secret:**
   - Verify client secret is correct (copy-paste errors common)
   - Check if secret was rotated at provider
   - Regenerate secret and update config

2. **Client not configured for Authorization Code flow:**
   - Check provider client settings allow "Authorization Code" grant type
   - Ensure client is "Confidential" not "Public"

3. **PKCE not supported or misconfigured:**
   - Some older providers don't support PKCE
   - Try disabling: `"use_pkce": false` (not recommended)
   - Or configure provider to require PKCE

### User Provisioned But Wrong Username

**Symptom:** JIT provisioning creates user with unexpected username like `sso_user_123`.

**Causes and Solutions:**

1. **Missing preferred_username claim:**
   - Check provider sends `preferred_username` in ID token or userinfo
   - Configure claim mapper at provider
   - Or accept email-based usernames

2. **Custom username claim:**
   - Provider uses different claim (e.g., `username`, `login`)
   - Update config: `"username_claim": "login"`

3. **Username conflicts:**
   - Generated username already taken, CIDX appended suffix
   - This is expected behavior for uniqueness

### Testing and Debugging Tips

**Enable Debug Logging:**
```bash
# Edit config.json
{
  "log_level": "DEBUG"
}
# Restart server and check logs
tail -f ~/.cidx-server/logs/server.log | grep -i oidc
```

**Test Provider Metadata Discovery:**
```bash
curl -s https://your-issuer/.well-known/openid-configuration | jq
```

**Verify JWT Tokens:**
Use [jwt.io](https://jwt.io) to decode ID tokens and inspect claims (do not paste production tokens into public sites).

**Check Database State:**
```bash
sqlite3 ~/.cidx-server/oidc_identities.db "SELECT * FROM oidc_identity_links;"
```

**Test Email Verification:**
```bash
# Check if provider sends email_verified claim
# Look in server logs during authentication for user info response
```

## Support and Additional Resources

- **OIDC Specification:** https://openid.net/specs/openid-connect-core-1_0.html
- **OAuth 2.0 Best Practices:** https://tools.ietf.org/html/draft-ietf-oauth-security-topics
- **PKCE Specification:** https://tools.ietf.org/html/rfc7636

For CIDX-specific issues:
- Check server logs in `~/.cidx-server/logs/`
- Review [OIDC Integration Plan](./oidc-integration-plan.md) for implementation details
- Report issues on GitHub: https://github.com/anthropics/code-indexer/issues
