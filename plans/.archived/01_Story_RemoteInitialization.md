# User Story: Remote Initialization

## 📋 **User Story**

As a **CIDX user**, I want to **initialize remote mode with mandatory server URL, username, and password parameters**, so that **I can connect to a remote CIDX server with proper authentication and validation**.

## 🎯 **Business Value**

Provides secure entry point for remote mode with comprehensive validation. Ensures users cannot create invalid remote configurations and provides clear guidance for proper setup.

## 📝 **Acceptance Criteria**

### Given: Mandatory Parameter Requirement
**When** I run `cidx init --remote <server>` without username or password  
**Then** the command fails with clear error message  
**And** explains that --username and --password are required with --remote  
**And** provides example of correct usage  
**And** doesn't create any configuration files  

### Given: Complete Remote Initialization
**When** I run `cidx init --remote <server> --username <user> --password <pass>`  
**Then** the system validates server connectivity and authentication  
**And** creates .code-indexer/.remote-config with server configuration  
**And** stores encrypted credentials securely  
**And** confirms successful initialization with next steps  

### Given: Server URL Validation
**When** I provide server URL during initialization  
**Then** the system validates URL format (HTTP/HTTPS required)  
**And** normalizes URL (removes trailing slashes, ensures protocol)  
**And** tests connectivity to server before proceeding  
**And** provides clear error for malformed or unreachable URLs  

### Given: Authentication Validation
**When** I provide credentials during initialization  
**Then** the system tests authentication with provided credentials  
**And** validates user has necessary permissions for remote operations  
**And** fails initialization if authentication unsuccessful  
**And** provides actionable guidance for authentication failures  

## 🏗️ **Technical Implementation**

### Enhanced Init Command
```python
@cli.command("init")
@click.option('--remote', 'server_url', help='Initialize remote mode with server URL')
@click.option('--username', help='Username for remote server (required with --remote)')
@click.option('--password', help='Password for remote server (required with --remote)')
@click.pass_context
def init_command(ctx, server_url: Optional[str], username: Optional[str], password: Optional[str]):
    """Initialize CIDX repository (local or remote mode)."""
    project_root = ctx.obj['project_root']
    
    if server_url:
        # Remote mode initialization
        if not username or not password:
            raise ClickException(
                "Remote initialization requires --username and --password parameters.\n"
                "Usage: cidx init --remote <server_url> --username <user> --password <pass>"
            )
        
        return initialize_remote_mode(project_root, server_url, username, password)
    else:
        # Local mode initialization (existing functionality)
        return initialize_local_mode(project_root)
```

### Remote Mode Initialization Logic
```python
async def initialize_remote_mode(
    project_root: Path, 
    server_url: str, 
    username: str, 
    password: str
):
    """Initialize remote mode with comprehensive validation."""
    click.echo("🌐 Initializing CIDX Remote Mode")
    click.echo("=" * 35)
    
    try:
        # Step 1: Validate and normalize server URL
        click.echo("🔍 Validating server URL...", nl=False)
        normalized_url = validate_and_normalize_server_url(server_url)
        click.echo("✅")
        
        # Step 2: Test server connectivity
        click.echo("🔌 Testing server connectivity...", nl=False)
        await test_server_connectivity(normalized_url)
        click.echo("✅")
        
        # Step 3: Validate credentials
        click.echo("🔐 Validating credentials...", nl=False)
        user_info = await validate_credentials(normalized_url, username, password)
        click.echo(f"✅ Authenticated as {user_info.username}")
        
        # Step 4: Check API compatibility
        click.echo("🔄 Checking API compatibility...", nl=False)
        await validate_api_compatibility(normalized_url)
        click.echo("✅")
        
        # Step 5: Create configuration directory
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir(exist_ok=True)
        
        # Step 6: Encrypt and store credentials
        click.echo("🔒 Encrypting credentials...", nl=False)
        credential_manager = ProjectCredentialManager()
        encrypted_creds = credential_manager.encrypt_credentials(
            username, password, normalized_url, str(project_root)
        )
        
        credentials_path = config_dir / ".creds"
        with open(credentials_path, 'wb') as f:
            f.write(encrypted_creds)
        
        # Secure file permissions (user-only read/write)
        credentials_path.chmod(0o600)
        click.echo("✅")
        
        # Step 7: Create remote configuration
        remote_config = {
            "server_url": normalized_url,
            "username": username,
            "initialized_at": datetime.now(timezone.utc).isoformat(),
            "api_version": "v1",  # From compatibility check
            "repository_link": None  # Will be set during repository linking
        }
        
        config_path = config_dir / ".remote-config"
        with open(config_path, 'w') as f:
            json.dump(remote_config, f, indent=2)
        
        click.echo("\n✨ Remote mode initialized successfully!")
        click.echo(f"📝 Server: {normalized_url}")
        click.echo(f"👤 User: {username}")
        click.echo(f"📁 Configuration: {config_path}")
        
        click.echo("\n💡 Next steps:")
        click.echo("   1. Link to a remote repository (automatic during first query)")
        click.echo("   2. Use 'cidx query <text>' to search remote repositories")
        click.echo("   3. Use 'cidx status' to check remote connection health")
        
    except Exception as e:
        # Clean up partial initialization on failure
        cleanup_failed_initialization(project_root)
        raise ClickException(f"Remote initialization failed: {str(e)}")
```

### URL Validation and Normalization
```python
def validate_and_normalize_server_url(server_url: str) -> str:
    """Validate and normalize server URL format."""
    # Add protocol if missing
    if not server_url.startswith(('http://', 'https://')):
        server_url = f"https://{server_url}"
    
    # Parse URL to validate format
    try:
        parsed = urllib.parse.urlparse(server_url)
        if not parsed.netloc:
            raise ValueError("Invalid URL format")
    except Exception:
        raise ValueError(f"Invalid server URL format: {server_url}")
    
    # Remove trailing slash and normalize
    normalized = server_url.rstrip('/')
    
    # Validate protocol
    if not normalized.startswith(('http://', 'https://')):
        raise ValueError("Server URL must use HTTP or HTTPS protocol")
    
    return normalized
```

## 🧪 **Testing Requirements**

### Unit Tests
- ✅ Parameter validation for missing username/password
- ✅ Server URL validation and normalization
- ✅ Error handling for malformed inputs
- ✅ Configuration file creation and structure

### Integration Tests
- ✅ End-to-end initialization with real server
- ✅ Authentication validation with valid/invalid credentials
- ✅ Server connectivity testing
- ✅ Configuration persistence and loading

### Error Scenario Tests
- ✅ Network failures during initialization
- ✅ Authentication failures with clear error messages
- ✅ Partial initialization cleanup on failures
- ✅ File permission issues during configuration creation

## 📊 **Definition of Done**

- ✅ Remote initialization command with mandatory parameter validation
- ✅ Server URL validation and normalization
- ✅ Comprehensive server connectivity and authentication testing
- ✅ Secure configuration file creation with proper permissions
- ✅ Error handling with actionable guidance for all failure scenarios
- ✅ Integration with existing local mode initialization
- ✅ Comprehensive test coverage including error scenarios
- ✅ User experience validation with clear success and failure messages
- ✅ Documentation updated with remote initialization instructions
- ✅ Code review validates security and user experience quality