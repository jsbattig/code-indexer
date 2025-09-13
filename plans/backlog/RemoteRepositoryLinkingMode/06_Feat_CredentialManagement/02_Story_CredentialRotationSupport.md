# User Story: Credential Rotation Support

## 📋 **User Story**

As a **CIDX user**, I want **ability to update my remote credentials while preserving repository configuration**, so that **I can change passwords without losing remote repository links and settings**.

## 🎯 **Business Value**

Enables secure credential lifecycle management without disrupting established remote workflows. Users can maintain security hygiene without reconfiguration overhead.

## 📝 **Acceptance Criteria**

### Given: Credential Update Command with Parameters
**When** I run `cidx auth update --username <new_user> --password <new_pass>` in remote mode  
**Then** system validates new credentials with remote server before storage  
**And** preserves existing remote configuration and repository links  
**And** provides confirmation of successful credential update  
**And** requires both username and password parameters (no prompting)  

### Given: Parameter Validation
**When** I run `cidx auth update` without username or password parameters  
**Then** command fails with clear error message explaining required parameters  
**And** shows usage example: `cidx auth update --username <user> --password <pass>`  
**And** no prompting occurs - command exits immediately  
**And** existing credentials remain unchanged  

### Given: Configuration Preservation
**When** I update credentials with valid parameters  
**Then** server URL and repository link remain unchanged  
**And** user preferences and settings are preserved  
**And** only authentication information is updated  
**And** rollback available if credential update fails  

### Given: Secure Parameter Handling
**When** I provide credentials via command-line parameters  
**Then** sensitive parameters are cleared from process memory immediately  
**And** credential validation occurs before any storage operations  
**And** failed validation preserves existing working credentials  
**And** success confirmation does not echo sensitive parameters  

## 🏗️ **Technical Implementation**

### Command-Line Interface Design
```python
@cli.command("auth")
@click.group()
def auth_group():
    """Authentication management commands."""
    pass

@auth_group.command("update")
@click.option('--username', required=True, help='New username for remote server')
@click.option('--password', required=True, help='New password for remote server')
@click.pass_context
def update_credentials(ctx, username: str, password: str):
    """Update remote credentials while preserving configuration.
    
    Example: cidx auth update --username newuser --password newpass
    """
    mode = ctx.obj['mode']
    project_root = ctx.obj['project_root']
    
    if mode != "remote":
        raise ClickException(
            "Credential update only available in remote mode. "
            "Initialize remote mode first with 'cidx init --remote <server> --username <user> --password <pass>'"
        )
    
    return update_remote_credentials(project_root, username, password)
```

### Secure Credential Update Implementation
```python
async def update_remote_credentials(project_root: Path, new_username: str, new_password: str):
    """Update remote credentials with comprehensive validation and rollback."""
    
    # Secure memory management for sensitive parameters
    username_bytes = bytearray(new_username.encode('utf-8'))
    password_bytes = bytearray(new_password.encode('utf-8'))
    
    try:
        click.echo("🔄 Updating remote credentials...")
        
        # Step 1: Load current remote configuration
        remote_config_path = project_root / ".code-indexer" / ".remote-config"
        if not remote_config_path.exists():
            raise CredentialUpdateError("No remote configuration found")
        
        with open(remote_config_path, 'r') as f:
            current_config = json.load(f)
        
        server_url = current_config['server_url']
        
        # Step 2: Validate new credentials with server before any changes
        click.echo("🔐 Validating new credentials with server...")
        
        validation_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0),
            verify=True
        )
        
        try:
            auth_response = await validation_client.post(
                urljoin(server_url, '/api/auth/login'),
                json={
                    'username': new_username,
                    'password': new_password
                },
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'CIDX-Client/1.0'
                }
            )
            
            if auth_response.status_code != 200:
                if auth_response.status_code == 401:
                    raise CredentialValidationError("Invalid new credentials - authentication failed")
                else:
                    raise CredentialValidationError(f"Server error during validation: {auth_response.status_code}")
            
            # Validate response contains required token data
            token_data = auth_response.json()
            if 'access_token' not in token_data:
                raise CredentialValidationError("Server response missing access_token")
            
            click.echo("✅ New credentials validated successfully")
            
        finally:
            await validation_client.aclose()
        
        # Step 3: Create backup of current credentials for rollback
        credential_manager = ProjectCredentialManager()
        backup_creds_path = project_root / ".code-indexer" / ".creds.backup"
        current_creds_path = project_root / ".code-indexer" / ".creds"
        
        if current_creds_path.exists():
            # Create atomic backup
            shutil.copy2(current_creds_path, backup_creds_path)
            click.echo("📁 Current credentials backed up for rollback")
        
        try:
            # Step 4: Encrypt and store new credentials
            click.echo("🔒 Encrypting and storing new credentials...")
            
            encrypted_creds = credential_manager.encrypt_credentials(
                new_username, new_password, server_url, str(project_root)
            )
            
            # Atomic write of new credentials
            temp_creds_path = current_creds_path.with_suffix('.tmp')
            with open(temp_creds_path, 'wb') as f:
                f.write(encrypted_creds)
            
            temp_creds_path.chmod(0o600)
            temp_creds_path.rename(current_creds_path)
            
            # Step 5: Update remote configuration with new username
            updated_config = current_config.copy()
            updated_config['username'] = new_username
            updated_config['credentials_updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Atomic write of updated configuration
            temp_config_path = remote_config_path.with_suffix('.tmp')
            with open(temp_config_path, 'w') as f:
                json.dump(updated_config, f, indent=2)
            
            temp_config_path.rename(remote_config_path)
            
            # Step 6: Test new credentials with actual API call
            click.echo("🧪 Testing new credentials with server...")
            
            test_client = CIDXRemoteAPIClient(server_url, 
                                            EncryptedCredentials(current_creds_path), 
                                            project_root)
            
            try:
                # Test authentication and basic API access
                user_info = await test_client.get_user_info()
                click.echo(f"✅ Credentials updated successfully for user: {user_info.username}")
                
                # Clean up backup on success
                if backup_creds_path.exists():
                    backup_creds_path.unlink()
                    
            except Exception as e:
                # Rollback on test failure
                click.echo(f"❌ Credential test failed: {e}")
                await rollback_credential_update(project_root, backup_creds_path, current_config)
                raise CredentialUpdateError(f"Credential update failed validation test: {e}")
            
            finally:
                await test_client.close()
            
            # Step 7: Invalidate any cached tokens to force re-authentication
            token_file = project_root / ".code-indexer" / ".token"
            if token_file.exists():
                token_file.unlink()
                click.echo("🔄 Cached authentication tokens cleared")
            
            click.echo("🎉 Credential update completed successfully!")
            click.echo("💡 Next queries will use the new credentials automatically")
            
        except Exception as e:
            # Rollback on any storage/update failure
            click.echo(f"❌ Credential update failed: {e}")
            await rollback_credential_update(project_root, backup_creds_path, current_config)
            raise
            
    except Exception as e:
        click.echo(f"❌ Failed to update credentials: {e}")
        raise ClickException(f"Credential update failed: {str(e)}")
    
    finally:
        # Secure memory cleanup: overwrite sensitive parameters
        if username_bytes:
            for i in range(3):  # 3 iterations for security
                for j in range(len(username_bytes)):
                    username_bytes[j] = 0
            del username_bytes
        
        if password_bytes:
            for i in range(3):  # 3 iterations for security
                for j in range(len(password_bytes)):
                    password_bytes[j] = 0
            del password_bytes

async def rollback_credential_update(project_root: Path, backup_path: Path, original_config: dict):
    """Rollback credential update to previous working state."""
    try:
        click.echo("🔄 Rolling back to previous credentials...")
        
        current_creds_path = project_root / ".code-indexer" / ".creds"
        remote_config_path = project_root / ".code-indexer" / ".remote-config"
        
        # Restore credential file from backup
        if backup_path.exists():
            backup_path.rename(current_creds_path)
            click.echo("✅ Credential file restored from backup")
        
        # Restore original configuration
        with open(remote_config_path, 'w') as f:
            json.dump(original_config, f, indent=2)
        
        click.echo("✅ Configuration restored to previous state")
        click.echo("💡 Previous credentials are still active and working")
        
    except Exception as rollback_error:
        click.echo(f"❌ Rollback failed: {rollback_error}")
        click.echo("⚠️ Manual intervention may be required to restore credentials")
```

### Command Usage Examples
```bash
# Update credentials (both parameters required)
cidx auth update --username newuser --password newpass123

# Missing parameters will fail immediately (no prompting)
cidx auth update --username newuser
# Error: Missing option '--password'

cidx auth update --password newpass123  
# Error: Missing option '--username'

cidx auth update
# Error: Missing option '--username' / Missing option '--password'
```

## 📊 **Definition of Done**

- ✅ `cidx auth update --username <user> --password <pass>` command (no prompting)
- ✅ Mandatory parameter validation with immediate failure on missing options
- ✅ New credential validation with server before any storage operations
- ✅ Remote configuration and repository link preservation during update
- ✅ Comprehensive rollback capability on any credential update failures
- ✅ Secure parameter handling with memory cleanup (3-iteration overwriting)
- ✅ Atomic credential file operations to prevent corruption
- ✅ Token cache invalidation to force re-authentication with new credentials
- ✅ Integration with existing encrypted credential storage system
- ✅ Comprehensive testing with credential rotation scenarios and rollback
- ✅ Error handling for validation failures, network issues, and storage problems
- ✅ Clear success/failure feedback without echoing sensitive parameters