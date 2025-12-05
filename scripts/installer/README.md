# MCPB Windows Installer

Complete Windows installer with authentication wizard for MCPB (MCP Bridge).

## Overview

This installer automates the entire MCPB setup process on Windows, replacing the manual 6-step process with a single executable. It provides:

- GUI wizard with authentication
- Silent installation mode for automation
- API authentication with token management
- Automatic Claude Desktop integration
- Comprehensive error handling

## Prerequisites

### Build Environment

1. NSIS 3.x (Nullsoft Scriptable Install System)
   - Download from: https://nsis.sourceforge.io/Download
   - Install to default location: `C:\Program Files (x86)\NSIS`

2. Required NSIS Plugins:
   - NScurl: HTTPS/curl support
   - nsJSON: JSON manipulation

### Installing Plugins

#### NScurl Plugin

1. Download from: https://github.com/negrutiu/nsis-nscurl/releases/download/v25.11.11.274/NScurl.zip
2. Extract the archive
3. Copy files to NSIS directories:
   ```
   NScurl.dll -> C:\Program Files (x86)\NSIS\Plugins\x86-unicode\
   NScurl-amd64.dll -> C:\Program Files (x86)\NSIS\Plugins\x86-ansi\
   NScurl.nsh -> C:\Program Files (x86)\NSIS\Include\
   ```

#### nsJSON Plugin

1. Download from: https://nsis.sourceforge.io/mediawiki/images/f/f0/NsJSON.zip
2. Extract the archive
3. Copy files to NSIS directories:
   ```
   nsJSON.dll -> C:\Program Files (x86)\NSIS\Plugins\x86-unicode\
   nsJSON-amd64.dll -> C:\Program Files (x86)\NSIS\Plugins\x86-ansi\
   ```

## Building the Installer

### Prepare MCPB Binary

1. Build or download the MCPB Windows binary:
   ```bash
   # From project root
   python scripts/build_binary.py --platform windows
   ```

2. Place `mcpb-windows-x64.exe` in `scripts/installer/` directory

### Compile Installer

#### GUI Method

1. Right-click `mcpb-installer.nsi`
2. Select "Compile NSIS Script"
3. Wait for compilation to complete
4. Output: `mcpb-installer.exe` in same directory

#### Command Line Method

```cmd
cd scripts\installer
"C:\Program Files (x86)\NSIS\makensis.exe" mcpb-installer.nsi
```

## Installation Modes

### GUI Installation

1. Run `mcpb-installer.exe`
2. Click through welcome screen
3. Enter authentication credentials:
   - Server URL (default: https://linner.ddns.net:8383)
   - Username
   - Password
4. Click Next to authenticate
5. Wait for installation to complete

The installer will:
- Extract MCPB binary to `C:\mcpb\server\`
- Authenticate with the API and obtain tokens
- Create configuration at `%USERPROFILE%\.mcpb\config.json`
- Integrate with Claude Desktop (if installed)

### Silent Installation

For automation, use command-line parameters:

```cmd
mcpb-installer.exe /S /SERVER_URL=https://server.example.com /USERNAME=user /PASSWORD=pass
```

Parameters:
- `/S` - Silent mode (no GUI)
- `/SERVER_URL=` - API server URL (optional, defaults to https://linner.ddns.net:8383)
- `/USERNAME=` - Username (required in silent mode)
- `/PASSWORD=` - Password (required in silent mode)

Exit codes:
- `0` - Complete success
- `1` - Authentication failure
- `2` - Configuration write failure
- `3` - Missing required parameters
- `4` - Partial success (MCPB installed but Claude Desktop integration failed)

## Uninstalling MCPB

### GUI Uninstallation

1. Open Windows Settings → Apps → Installed apps
2. Find "MCPB - MCP Bridge" in the list
3. Click the three dots (⋮) and select "Uninstall"
4. Confirm the uninstallation when prompted
5. Wait for the uninstaller to complete

### Silent Uninstallation

For automation or scripting:

```cmd
"C:\mcpb\uninstall.exe" /S
```

Exit codes:
- `0` - Uninstallation completed successfully
- `1` - Uninstallation failed
- `2` - Partial success (some files could not be removed)

### What Gets Removed

The uninstaller removes:
- MCPB binary: `C:\mcpb\server\mcpb-windows-x64.exe`
- Installation directory: `C:\mcpb\` (entire directory)
- Configuration: `%USERPROFILE%\.mcpb\config.json`
- Configuration directory: `%USERPROFILE%\.mcpb\`
- Claude Desktop integration: Removes `mcpb` entry from `claude_desktop_config.json`
- Registry entries: Removes from Add/Remove Programs list

### What Gets Preserved

The uninstaller preserves:
- Other MCP servers in Claude Desktop config
- Claude Desktop application and settings
- All other system configuration

### Troubleshooting Uninstallation

**Files in use error:**
- Close Claude Desktop before uninstalling
- Close any terminals running `mcpb-windows-x64.exe`
- Retry uninstallation

**Partial uninstallation (exit code 2):**
If some files cannot be removed, manually delete:
- `C:\mcpb\` directory
- `%USERPROFILE%\.mcpb\` directory

## Manual Testing

### Test Case 1: Successful GUI Installation

1. Run installer in GUI mode
2. Enter valid credentials
3. Verify authentication succeeds
4. Verify files created:
   - `C:\mcpb\server\mcpb-windows-x64.exe`
   - `%USERPROFILE%\.mcpb\config.json`
5. Verify Claude Desktop config updated (if Claude Desktop installed)

Expected:
- No errors displayed
- Success message on completion
- All files present with correct content

### Test Case 2: Invalid Credentials (HTTP 401)

1. Run installer in GUI mode
2. Enter invalid username/password
3. Click Next

Expected:
- Error message: "Invalid username or password (HTTP 401)"
- Option to retry with different credentials
- No files created

### Test Case 3: Server Unreachable

1. Run installer with invalid server URL
2. Enter credentials
3. Click Next

Expected:
- Error message: "Connection failed: [reason]. Please verify the server URL..."
- Option to retry
- No files created

### Test Case 4: Silent Installation Success

```cmd
mcpb-installer.exe /S /USERNAME=testuser /PASSWORD=testpass
```

Expected:
- No GUI displayed
- Exit code 0
- Files created successfully
- Installation log written

### Test Case 5: Silent Installation Missing Parameters

```cmd
mcpb-installer.exe /S
```

Expected:
- Error message about missing /USERNAME
- Exit code 3
- No installation performed

### Test Case 6: Claude Desktop Not Installed

1. Run installer on system without Claude Desktop
2. Complete authentication

Expected:
- Warning message about Claude Desktop not found
- Instruction to manually configure
- Installation completes successfully
- MCPB config created correctly

### Test Case 7: Claude Desktop Config Merge

1. Create existing Claude Desktop config with other MCP servers:
   ```json
   {
     "mcpServers": {
       "other-server": {
         "command": "C:\\other\\server.exe",
         "args": []
       }
     }
   }
   ```
2. Run installer
3. Complete installation

Expected:
- Existing config preserved
- MCPB entry added to mcpServers
- Both servers present in final config

## Configuration Files

### MCPB Configuration

Location: `%USERPROFILE%\.mcpb\config.json`

Format:
```json
{
  "server_url": "https://linner.ddns.net:8383",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### Claude Desktop Configuration

Location: `%APPDATA%\Claude\claude_desktop_config.json`

MCPB Entry:
```json
{
  "mcpServers": {
    "mcpb": {
      "command": "C:\\mcpb\\server\\mcpb-windows-x64.exe",
      "args": []
    }
  }
}
```

## Troubleshooting

### Build Errors

**Error: "Can't open script file"**
- Verify you're in the correct directory
- Check file permissions

**Error: "Unknown plugin command"**
- Install required plugins (NScurl, nsJSON)
- Verify plugins are in correct NSIS directories

**Error: "Can't find mcpb-windows-x64.exe"**
- Build the binary first using `build_binary.py`
- Place binary in `scripts/installer/` directory
- Or comment out the `File` command for testing

### Runtime Errors

**Authentication fails with connection error**
- Verify server URL is correct
- Check network connectivity
- Verify firewall allows HTTPS traffic
- Test server URL in browser first

**HTTP 401 errors**
- Verify credentials are correct
- Check username/password for typos
- Confirm account exists on server

**Config write failures**
- Run installer as administrator
- Check disk space
- Verify %USERPROFILE% path is accessible

**Claude Desktop integration fails**
- Confirm Claude Desktop is installed
- Check %APPDATA%\Claude directory exists
- Verify claude_desktop_config.json has valid JSON
- Try manual integration if auto-merge fails

**Blocked Executable Errors**

If Windows warns that `mcpb-windows-x64.exe` is blocked or unsafe:

Why this rarely happens: Files extracted by NSIS are embedded in the installer at build time and do not inherit Zone.Identifier marks during installation. However, antivirus software or Windows SmartScreen may add blocks after extraction.

How to unblock:
1. Manual: Right-click `C:\mcpb\server\mcpb-windows-x64.exe` → Properties → Check "Unblock" → OK
2. PowerShell (if available): `Unblock-File -Path "C:\mcpb\server\mcpb-windows-x64.exe"`

See "Development Notes → Key Implementation Details" for technical details about Zone.Identifier handling.

### Installation Logs

View detailed logs:
1. Open `%TEMP%\nsis-[random].log`
2. Search for "LogText" entries
3. Look for error messages and HTTP status codes

## Development Notes

### Design Constraints

- NO POWERSHELL: Pure NSIS implementation only (enterprise restriction)
- Plugin-based architecture: NScurl for HTTPS, nsJSON for JSON
- Graceful degradation: Warn but don't fail on missing Claude Desktop

### Key Implementation Details

1. **Zone.Identifier Handling (Unblock Mechanism)**: Files extracted by NSIS using the `File` command are embedded in the installer's internal archive at build time. When the installer runs, files are extracted directly from this internal archive to the target directory. Since the files are not downloaded from the internet during installation, they do not inherit the Zone.Identifier alternate data stream from the installer executable. This means extracted files (like `mcpb-windows-x64.exe`) are automatically "unblocked" and do not require manual unblocking via PowerShell or file properties.

   **Troubleshooting**: If users encounter "blocked" executables after installation:
   - Verify the installer was built correctly with `File "mcpb-windows-x64.exe"` command
   - Check if antivirus software is adding Zone.Identifier after extraction
   - Manually unblock: Right-click executable → Properties → Check "Unblock" → OK
   - Or use PowerShell: `Unblock-File -Path "C:\mcpb\server\mcpb-windows-x64.exe"`

2. Password Security: Password field uses ES_PASSWORD style for masking
3. Error Mapping: HTTP status codes mapped to user-friendly messages with context
4. JSON Merging: Preserves existing Claude Desktop MCP server entries, prompts before overwriting
5. Retry Logic: Failed authentication allows retry without restarting
6. Exit Code 4: Indicates partial success - MCPB installed successfully but Claude Desktop integration failed (not installed or config error)

### Future Enhancements

- Progress bar during download (if binary is downloaded vs bundled)
- Automatic token refresh validation
- ~~Uninstaller with cleanup~~ ✅ Implemented
- Upgrade detection and migration
- Multi-language support

## CI/CD Integration

The installer build is fully automated in the GitHub Actions workflow at `.github/workflows/release-mcpb.yml`.

### Workflow Overview

The `build-windows-installer` job runs on every release and:

1. **Environment Setup** (AC1):
   - Uses `windows-latest` runner
   - Installs NSIS via chocolatey
   - Downloads NScurl plugin from https://github.com/negrutiu/nsis-nscurl/releases/download/v25.11.11.274/NScurl.zip
   - Downloads nsJSON plugin from https://nsis.sourceforge.io/mediawiki/images/f/f0/NsJSON.zip
   - Copies plugins to NSIS directories (x86-unicode and x86-ansi)
   - Verifies `makensis` command availability

2. **Installer Compilation** (AC2):
   - Extracts pre-built `mcpb-windows-x64.exe` from artifact
   - Copies binary to `scripts/installer/` directory
   - Compiles `mcpb-installer.nsi` with `makensis /V4`
   - Renames output to `mcpb-windows-x64-setup.exe`
   - Fails workflow on compilation errors
   - Logs compilation output for debugging

3. **Silent Installation Testing** (AC3):
   - Runs installer with `/S /USERNAME=ci-test /PASSWORD=ci-test`
   - Expected: Exit code 1 (authentication failure - no real server)
   - Verifies binary extraction to `C:\mcpb\server\mcpb-windows-x64.exe`
   - Captures and logs exit code

4. **Artifact Upload** (AC6):
   - Uploads `mcpb-windows-x64-setup.exe` as build artifact
   - Includes installer in GitHub release alongside platform binaries

### Testing Limitations

**Authentication Testing (AC3)**: The installer requires authentication against a CIDX server. In CI, we have chosen **Option A** from the story:
- **Skip authentication test**: Installer exit code 1 is expected without real server
- **Focus on extraction**: Verify installer compiles and extracts binary correctly
- **Rationale**: Creating a mock endpoint adds complexity without significant value. The installer's extraction and compilation are the critical CI concerns. Full authentication flow is tested manually.

**Installation Verification (AC4)**: Without successful authentication, `config.json` is not created. CI focuses on:
- Binary extraction verification (primary goal)
- Installer compilation success
- Plugin integration correctness

**Claude Desktop Config Testing (AC5)**: Merge logic is verified through:
- Unit tests (if implemented)
- Manual testing (documented in this README)
- CI skips this test due to auth dependency

### Manual Testing Requirements

While CI validates compilation and extraction, the following must be tested manually before release:

1. **Full authentication flow** - Test with real server credentials
2. **Config.json creation** - Verify token storage
3. **Claude Desktop integration** - Test config merge logic
4. **Error handling** - HTTP 401, 403, 500, connection failures
5. **Retry logic** - Failed auth with GUI retry option

See "Manual Testing" section above for detailed test cases.

### Triggering CI Build

The installer build runs automatically when:
- A version tag is pushed (e.g., `v1.0.0`)
- The workflow is manually triggered via `workflow_dispatch`

To manually trigger:
```bash
gh workflow run release-mcpb.yml
```

### Viewing CI Logs

Monitor installer build progress:
```bash
gh run list --workflow=release-mcpb.yml --limit 5
gh run view <run-id> --log
```

Check for:
- NSIS installation success
- Plugin download and installation
- Compilation output (`makensis /V4`)
- Binary extraction verification
- Artifact upload confirmation

### Troubleshooting CI Failures

**Plugin download failures**:
- Check URLs are still valid (NScurl, nsJSON)
- Verify network connectivity in CI environment
- Update plugin versions if releases move

**Compilation errors**:
- Review makensis output in logs
- Verify `mcpb-windows-x64.exe` was extracted from artifact
- Check for NSIS syntax errors

**Extraction test failures**:
- Verify installer runs in silent mode
- Check `C:\mcpb\server\` directory creation
- Look for Windows SmartScreen or antivirus interference

## Support

For issues:
1. Check installation log in %TEMP%
2. Verify all prerequisites installed
3. Test server connectivity manually
4. Review troubleshooting section above
5. Report bugs with log files attached
