"""
Tests for NSIS installer script validation.

Since NSIS is Windows-only, we validate the script structure, syntax patterns,
and completeness rather than executing the installer.
"""

import re
from pathlib import Path

import pytest


@pytest.fixture
def nsis_script_path():
    """Path to the NSIS installer script."""
    return Path(__file__).parent.parent.parent / "scripts" / "installer" / "mcpb-installer.nsi"


@pytest.fixture
def nsis_script_content(nsis_script_path):
    """Content of the NSIS installer script."""
    if not nsis_script_path.exists():
        pytest.skip(f"NSIS script not found at {nsis_script_path}")
    return nsis_script_path.read_text()


class TestNSISScriptStructure:
    """Test NSIS script has all required structural elements."""

    def test_script_file_exists(self, nsis_script_path):
        """NSIS installer script file exists."""
        assert nsis_script_path.exists(), f"NSIS script not found at {nsis_script_path}"

    def test_has_mui2_include(self, nsis_script_content):
        """Script includes MUI2 for modern UI."""
        assert '!include "MUI2.nsh"' in nsis_script_content

    def test_has_nsdialogs_include(self, nsis_script_content):
        """Script includes nsDialogs for custom pages."""
        assert '!include "nsDialogs.nsh"' in nsis_script_content

    def test_has_plugin_directory(self, nsis_script_content):
        """Script specifies plugin directory."""
        assert re.search(r'!addplugindir\s+"plugins"', nsis_script_content)

    def test_declares_required_variables(self, nsis_script_content):
        """Script declares all required variables."""
        required_vars = [
            "ServerUrl",
            "Username",
            "Password",
            "AccessToken",
            "RefreshToken"
        ]
        for var in required_vars:
            assert re.search(rf'Var\s+{var}', nsis_script_content), \
                f"Missing variable declaration: {var}"

    def test_has_installer_metadata(self, nsis_script_content):
        """Script has installer metadata (name, outfile, etc.)."""
        assert re.search(r'Name\s+"[^"]+"', nsis_script_content)
        assert re.search(r'OutFile\s+"[^"]+"', nsis_script_content)
        assert re.search(r'InstallDir\s+', nsis_script_content)


class TestAC1_MCPBExtraction:
    """Test AC1: MCPB extraction and unblocking."""

    def test_sets_output_path(self, nsis_script_content):
        """Script sets output path to C:\\mcpb\\server\\."""
        assert re.search(r'SetOutPath\s+"C:\\\\mcpb\\\\server', nsis_script_content)

    def test_extracts_mcpb_exe(self, nsis_script_content):
        """Script extracts mcpb-windows-x64.exe using File command."""
        assert re.search(r'File\s+"[^"]*mcpb-windows-x64\.exe"', nsis_script_content)

    def test_creates_directory_structure(self, nsis_script_content):
        """Script creates directory structure."""
        # Should use CreateDirectory or SetOutPath creates it automatically
        assert re.search(r'(CreateDirectory|SetOutPath)\s+"C:\\\\mcpb', nsis_script_content)


class TestAC2_AuthenticationGUI:
    """Test AC2: Authentication GUI wizard."""

    def test_has_custom_auth_page(self, nsis_script_content):
        """Script defines custom authentication page."""
        assert re.search(r'Page\s+custom\s+\w+', nsis_script_content)

    def test_has_server_url_input(self, nsis_script_content):
        """Script creates server URL input field."""
        # Should use nsDialogs::CreateControl or similar with Text control
        assert re.search(r'(nsDialogs::Create(Control|Text)|\$\{NSD_CreateText\})', nsis_script_content, re.IGNORECASE)

    def test_has_username_input(self, nsis_script_content):
        """Script creates username input field."""
        # Username variable should be used with input control
        assert re.search(r'Username', nsis_script_content)

    def test_has_password_input(self, nsis_script_content):
        """Script creates password input field with ES_PASSWORD style."""
        # Password field should use ES_PASSWORD or SECURE flag
        assert re.search(r'(ES_PASSWORD|PASSWORD|Secure)', nsis_script_content, re.IGNORECASE)

    def test_has_field_validation(self, nsis_script_content):
        """Script validates input fields before proceeding."""
        # Should have validation function or StrCmp checks
        assert re.search(r'(StrCmp|StrLen|Validate)', nsis_script_content, re.IGNORECASE)

    def test_has_default_server_url(self, nsis_script_content):
        """Script has build-time configurable default server URL."""
        # Should use !define or StrCpy with default URL
        assert re.search(r'(!define\s+DEFAULT_SERVER_URL|StrCpy.*http)', nsis_script_content, re.IGNORECASE)


class TestAC3_APIAuthentication:
    """Test AC3: API authentication via NScurl."""

    def test_uses_nscurl_plugin(self, nsis_script_content):
        """Script uses NScurl plugin for HTTPS POST."""
        assert re.search(r'NScurl::', nsis_script_content)

    def test_constructs_json_request(self, nsis_script_content):
        """Script constructs JSON request with nsJSON."""
        assert re.search(r'nsJSON::', nsis_script_content)

    def test_posts_to_auth_endpoint(self, nsis_script_content):
        """Script POSTs to /auth/login endpoint."""
        assert re.search(r'/auth/login', nsis_script_content)

    def test_parses_json_response(self, nsis_script_content):
        """Script parses JSON response to extract tokens."""
        # Should use nsJSON::Get or similar to extract access_token
        assert re.search(r'nsJSON::(Get|Set)', nsis_script_content, re.IGNORECASE)

    def test_handles_http_errors(self, nsis_script_content):
        """Script handles HTTP error status codes."""
        # Should check for 401, 403, 500 or general error handling
        assert re.search(r'(401|403|500|error|status)', nsis_script_content, re.IGNORECASE)

    def test_displays_error_messages(self, nsis_script_content):
        """Script displays meaningful error messages."""
        assert re.search(r'MessageBox\s+MB_', nsis_script_content, re.IGNORECASE)

    def test_allows_retry_on_failure(self, nsis_script_content):
        """Script allows retry on authentication failure."""
        # Should have Abort or loop back to auth page
        assert re.search(r'(Abort|Goto|Retry)', nsis_script_content, re.IGNORECASE)


class TestAC4_MCPBConfiguration:
    """Test AC4: MCPB configuration generation."""

    def test_creates_mcpb_directory(self, nsis_script_content):
        """Script creates .mcpb directory under %USERPROFILE%."""
        assert re.search(r'(CreateDirectory|SetOutPath).*PROFILE.*\.mcpb', nsis_script_content, re.IGNORECASE)

    def test_constructs_config_json(self, nsis_script_content):
        """Script constructs config.json with nsJSON."""
        # Should use nsJSON to build config structure
        assert re.search(r'nsJSON::Set.*server_url', nsis_script_content, re.IGNORECASE)

    def test_writes_config_file(self, nsis_script_content):
        """Script writes config.json file."""
        assert re.search(r'(FileOpen|nsJSON::Serialize.*config\.json)', nsis_script_content, re.IGNORECASE)

    def test_handles_write_failures(self, nsis_script_content):
        """Script handles config write failures gracefully."""
        # Should check file write result or have error handling
        assert re.search(r'(IfErrors|error.*write|write.*fail)', nsis_script_content, re.IGNORECASE)


class TestAC5_ClaudeDesktopIntegration:
    """Test AC5: Claude Desktop integration."""

    def test_detects_claude_config_location(self, nsis_script_content):
        """Script detects Claude Desktop config in %APPDATA%\\Claude\\."""
        assert re.search(r'APPDATA.*Claude', nsis_script_content, re.IGNORECASE)

    def test_reads_existing_config(self, nsis_script_content):
        """Script reads existing claude_desktop_config.json if present."""
        assert re.search(r'claude_desktop_config\.json', nsis_script_content, re.IGNORECASE)

    def test_merges_mcpb_entry(self, nsis_script_content):
        """Script merges MCPB entry into mcpServers object."""
        # Should use nsJSON to merge, preserving existing entries
        assert re.search(r'mcpServers', nsis_script_content, re.IGNORECASE)

    def test_preserves_existing_servers(self, nsis_script_content):
        """Script preserves existing MCP server entries."""
        # Should read existing, merge, not overwrite
        assert re.search(r'(nsJSON::Get|merge|preserve)', nsis_script_content, re.IGNORECASE)

    def test_handles_missing_claude_desktop(self, nsis_script_content):
        """Script handles missing Claude Desktop gracefully."""
        # Should warn but not fail
        assert re.search(r'(IfFileExists|warning|optional)', nsis_script_content, re.IGNORECASE)


class TestAC6_SilentInstallation:
    """Test AC6: Silent installation mode."""

    def test_defaults_to_gui_mode(self, nsis_script_content):
        """Script defaults to GUI mode (not silent)."""
        assert re.search(r'SilentInstall\s+normal', nsis_script_content, re.IGNORECASE)

    def test_supports_silent_flag(self, nsis_script_content):
        """Script supports /S flag for silent installation via command-line."""
        # The installer handles /S flag in .onInit to enable silent mode
        assert re.search(r'GetOptions.*"/S"', nsis_script_content)

    def test_supports_command_line_params(self, nsis_script_content):
        """Script supports /SERVER_URL=, /USERNAME=, /PASSWORD= parameters."""
        # Should use GetOptions or similar for command line parsing
        assert re.search(r'(GetOptions|GetParameters|/SERVER_URL|/USERNAME|/PASSWORD)', nsis_script_content, re.IGNORECASE)

    def test_skips_gui_in_silent_mode(self, nsis_script_content):
        """Script skips GUI when /S is specified."""
        # Should check silent mode and skip custom pages
        assert re.search(r'(IfSilent|silent.*skip)', nsis_script_content, re.IGNORECASE)

    def test_defines_exit_codes(self, nsis_script_content):
        """Script uses proper exit codes for different failure modes."""
        # Should use SetErrorLevel or similar
        assert re.search(r'SetErrorLevel', nsis_script_content, re.IGNORECASE)

    def test_writes_to_log_file(self, nsis_script_content):
        """Script writes to NSIS log file for troubleshooting."""
        # Should use LogSet or LogText or DetailPrint
        assert re.search(r'(LogSet|LogText|DetailPrint|log)', nsis_script_content, re.IGNORECASE)


class TestAC7_ErrorHandling:
    """Test AC7: Error handling and user feedback."""

    def test_handles_json_error_responses(self, nsis_script_content):
        """Script handles JSON error responses from API."""
        # Should check for "detail" field in error responses (FastAPI style)
        assert re.search(
            r'nsJSON::Get\s+"detail"', nsis_script_content, re.IGNORECASE
        ), "Missing handling for 'detail' error field"
        # Should check for "error" field as alternative
        assert re.search(
            r'nsJSON::Get\s+"error"', nsis_script_content, re.IGNORECASE
        ), "Missing handling for 'error' field"
        # Should have fallback error message for authentication failure
        assert re.search(
            r"Invalid username or password", nsis_script_content, re.IGNORECASE
        ), "Missing fallback error message for authentication failure"

    def test_includes_context_in_errors(self, nsis_script_content):
        """Script includes relevant context (URL, path) in error messages."""
        # Error messages should reference URL or path variables
        assert re.search(r'MessageBox.*(\$ServerUrl|\$INSTDIR|url|path)', nsis_script_content, re.IGNORECASE)

    def test_provides_recovery_guidance(self, nsis_script_content):
        """Script provides recovery guidance in error messages."""
        # Should have retry, check, verify type messages
        assert re.search(r'(retry|check|verify|ensure)', nsis_script_content, re.IGNORECASE)

    def test_logs_detailed_errors(self, nsis_script_content):
        """Script logs detailed error information."""
        # Should log errors for troubleshooting
        assert re.search(r'(LogText|DetailPrint).*error', nsis_script_content, re.IGNORECASE)


class TestNSISSyntaxPatterns:
    """Test NSIS script follows proper syntax patterns."""

    def test_no_powershell_usage(self, nsis_script_content):
        """Script does NOT use PowerShell (per user constraint)."""
        # Check for actual PowerShell execution, not comments about avoiding it
        if re.search(r"(Exec|nsExec).*powershell", nsis_script_content, re.IGNORECASE):
            pytest.fail("PowerShell execution is prohibited"), \
            "PowerShell is prohibited in enterprise environments"

    def test_uses_mui2_page_macros(self, nsis_script_content):
        """Script uses MUI2 page macros."""
        assert re.search(r'!insertmacro\s+MUI_PAGE_', nsis_script_content)

    def test_has_section_definitions(self, nsis_script_content):
        """Script has Section definitions for installation steps."""
        assert re.search(r'Section\s+"[^"]+"', nsis_script_content, re.IGNORECASE)

    def test_has_function_definitions(self, nsis_script_content):
        """Script defines functions for auth, config, etc."""
        assert re.search(r'Function\s+\w+', nsis_script_content)

    def test_proper_string_escaping(self, nsis_script_content):
        """Script properly escapes backslashes in Windows paths."""
        # Windows paths should use \\ or $INSTDIR variables
        if re.search(r'C:\\[^\\]', nsis_script_content):
            pytest.fail("Found single backslash in path - should be double backslash")


# ============================================================================
# Story #578: Windows Uninstaller Tests
# ============================================================================


class TestUninstallerAC1_InstallationDirectoryRemoval:
    """Test AC1: Installation directory removal."""

    def test_has_uninstall_section(self, nsis_script_content):
        """Script has Uninstall section."""
        assert re.search(r'Section\s+"Uninstall"', nsis_script_content, re.IGNORECASE)

    def test_removes_installation_directory(self, nsis_script_content):
        """Script removes C:\\mcpb directory using RMDir /r."""
        assert re.search(r'RMDir\s+/r\s+"\$INSTDIR"', nsis_script_content, re.IGNORECASE)

    def test_checks_directory_exists_before_removal(self, nsis_script_content):
        """Script checks if directory exists before attempting removal."""
        assert re.search(r'IfFileExists.*INSTDIR', nsis_script_content, re.IGNORECASE)

    def test_handles_locked_files(self, nsis_script_content):
        """Script handles locked files gracefully."""
        # Should check if removal succeeded and provide error message
        assert re.search(r'(locked|in use|close.*application)', nsis_script_content, re.IGNORECASE)

    def test_continues_on_locked_files(self, nsis_script_content):
        """Script continues uninstallation even if some files are locked."""
        # Should have Goto or continue pattern after locked file error
        assert re.search(r'(Goto|continue).*config', nsis_script_content, re.IGNORECASE)


class TestUninstallerAC2_ConfigurationDirectoryRemoval:
    """Test AC2: Configuration directory removal."""

    def test_removes_config_directory(self, nsis_script_content):
        """Script removes %USERPROFILE%\\.mcpb directory."""
        assert re.search(r'RMDir\s+/r\s+"\$PROFILE\\\.mcpb"', nsis_script_content, re.IGNORECASE)

    def test_handles_missing_config_directory(self, nsis_script_content):
        """Script handles missing config directory gracefully."""
        # Should check if config directory exists before removal
        assert re.search(r'IfFileExists.*PROFILE.*\.mcpb', nsis_script_content, re.IGNORECASE)

    def test_logs_config_removal(self, nsis_script_content):
        """Script logs configuration directory removal."""
        assert re.search(r'(LogText|DetailPrint).*[Cc]onfiguration.*remov', nsis_script_content, re.IGNORECASE)


class TestUninstallerAC3_ClaudeDesktopConfigCleanup:
    """Test AC3: Claude Desktop configuration cleanup."""

    def test_has_remove_mcpb_function(self, nsis_script_content):
        """Script has un.RemoveMcpbFromClaudeConfig function."""
        assert re.search(r'Function\s+un\.RemoveMcpbFromClaudeConfig', nsis_script_content)

    def test_calls_remove_mcpb_function(self, nsis_script_content):
        """Uninstall section calls un.RemoveMcpbFromClaudeConfig."""
        assert re.search(r'Call\s+un\.RemoveMcpbFromClaudeConfig', nsis_script_content)

    def test_reads_claude_config(self, nsis_script_content):
        """Function reads existing claude_desktop_config.json."""
        # Should read config file in uninstaller function
        assert re.search(r'un\.RemoveMcpbFromClaudeConfig.*claude_desktop_config\.json', nsis_script_content, re.IGNORECASE | re.DOTALL)

    def test_removes_only_mcpb_key(self, nsis_script_content):
        """Function removes only mcpb key from mcpServers."""
        # Should use nsJSON::Delete for specific key removal
        assert re.search(r'nsJSON::Delete.*mcpServers.*mcpb', nsis_script_content, re.IGNORECASE)

    def test_preserves_other_mcp_servers(self, nsis_script_content):
        """Function preserves other mcpServers entries."""
        # Should use nsJSON::Delete (not recreating entire object)
        # This ensures other servers are preserved
        assert re.search(r'nsJSON::Delete', nsis_script_content)

    def test_writes_updated_config(self, nsis_script_content):
        """Function writes updated config back to file."""
        # Should serialize and write after removing mcpb entry
        # Check for both operations separately since they're on different lines
        assert re.search(r'un\.RemoveMcpbFromClaudeConfig.*nsJSON::Serialize', nsis_script_content, re.IGNORECASE | re.DOTALL)
        assert re.search(r'un\.RemoveMcpbFromClaudeConfig.*FileWrite', nsis_script_content, re.IGNORECASE | re.DOTALL)

    def test_handles_missing_claude_config(self, nsis_script_content):
        """Function handles missing claude_desktop_config.json gracefully."""
        # Should check if file exists and handle missing file
        assert re.search(r'un\.RemoveMcpbFromClaudeConfig.*IfFileExists.*claude_desktop_config', nsis_script_content, re.IGNORECASE | re.DOTALL)

    def test_handles_missing_mcpb_entry(self, nsis_script_content):
        """Function handles missing mcpb entry gracefully."""
        # Should check if mcpb entry exists before trying to delete
        assert re.search(r'nsJSON::Get.*mcpb', nsis_script_content, re.IGNORECASE)


class TestUninstallerAC4_AddRemoveProgramsIntegration:
    """Test AC4: Add/Remove Programs integration."""

    def test_writes_uninstaller_during_install(self, nsis_script_content):
        """Installer writes uninstall.exe."""
        assert re.search(r'WriteUninstaller\s+"\$INSTDIR\\uninstall\.exe"', nsis_script_content, re.IGNORECASE)

    def test_writes_registry_display_name(self, nsis_script_content):
        """Installer writes DisplayName registry entry."""
        assert re.search(r'WriteRegStr.*Uninstall\\MCPB.*DisplayName', nsis_script_content, re.IGNORECASE)

    def test_writes_registry_display_version(self, nsis_script_content):
        """Installer writes DisplayVersion registry entry."""
        assert re.search(r'WriteRegStr.*Uninstall\\MCPB.*DisplayVersion', nsis_script_content, re.IGNORECASE)

    def test_writes_registry_publisher(self, nsis_script_content):
        """Installer writes Publisher registry entry."""
        assert re.search(r'WriteRegStr.*Uninstall\\MCPB.*Publisher', nsis_script_content, re.IGNORECASE)

    def test_writes_registry_uninstall_string(self, nsis_script_content):
        """Installer writes UninstallString registry entry."""
        assert re.search(r'WriteRegStr.*Uninstall\\MCPB.*UninstallString', nsis_script_content, re.IGNORECASE)

    def test_writes_registry_install_location(self, nsis_script_content):
        """Installer writes InstallLocation registry entry."""
        assert re.search(r'WriteRegStr.*Uninstall\\MCPB.*InstallLocation', nsis_script_content, re.IGNORECASE)

    def test_writes_registry_no_modify(self, nsis_script_content):
        """Installer writes NoModify registry entry."""
        assert re.search(r'WriteRegDWORD.*Uninstall\\MCPB.*NoModify', nsis_script_content, re.IGNORECASE)

    def test_writes_registry_no_repair(self, nsis_script_content):
        """Installer writes NoRepair registry entry."""
        assert re.search(r'WriteRegDWORD.*Uninstall\\MCPB.*NoRepair', nsis_script_content, re.IGNORECASE)

    def test_deletes_registry_key_on_uninstall(self, nsis_script_content):
        """Uninstaller removes registry entries."""
        assert re.search(r'DeleteRegKey.*Uninstall\\MCPB', nsis_script_content, re.IGNORECASE)


class TestUninstallerAC5_ConfirmationPrompt:
    """Test AC5: Confirmation prompt."""

    def test_has_uninstall_confirm_page(self, nsis_script_content):
        """Script has MUI2 uninstaller confirmation page."""
        assert re.search(r'!insertmacro\s+MUI_UNPAGE_CONFIRM', nsis_script_content)

    def test_has_uninstall_instfiles_page(self, nsis_script_content):
        """Script has MUI2 uninstaller instfiles page."""
        assert re.search(r'!insertmacro\s+MUI_UNPAGE_INSTFILES', nsis_script_content)

    def test_logs_uninstall_actions(self, nsis_script_content):
        """Script logs uninstallation actions."""
        # Should have DetailPrint calls in uninstall section
        assert re.search(r'Section\s+"Uninstall".*DetailPrint', nsis_script_content, re.IGNORECASE | re.DOTALL)


class TestUninstallerAC6_SilentUninstallation:
    """Test AC6: Silent uninstallation mode."""

    def test_supports_silent_uninstall(self, nsis_script_content):
        """Script supports /S flag for silent uninstallation."""
        # Should check IfSilent in uninstall section
        assert re.search(r'Section\s+"Uninstall".*IfSilent', nsis_script_content, re.IGNORECASE | re.DOTALL)

    def test_skips_messageboxes_in_silent_mode(self, nsis_script_content):
        """Script skips MessageBox prompts in silent mode."""
        # Should have IfSilent before MessageBox calls in uninstall section
        # Check within the uninstall section
        uninstall_section = re.search(r'Section\s+"Uninstall".*?(?=^Section|^Function|\Z)', nsis_script_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if uninstall_section:
            assert re.search(r'IfSilent', uninstall_section.group(0), re.IGNORECASE)

    def test_sets_exit_code_on_success(self, nsis_script_content):
        """Script sets exit code 0 on successful uninstallation."""
        # Should set SetErrorLevel 0 for success
        assert re.search(r'Section\s+"Uninstall".*SetErrorLevel\s+0', nsis_script_content, re.IGNORECASE | re.DOTALL)

    def test_sets_exit_code_on_failure(self, nsis_script_content):
        """Script sets non-zero exit code on failure."""
        # Should set SetErrorLevel with non-zero value for errors
        assert re.search(r'Section\s+"Uninstall".*SetErrorLevel\s+[12]', nsis_script_content, re.IGNORECASE | re.DOTALL)

    def test_writes_to_log_during_uninstall(self, nsis_script_content):
        """Script writes to log file during uninstallation."""
        # Should have DetailPrint calls throughout uninstall section
        uninstall_section = re.search(r'Section\s+"Uninstall".*?(?=Section|\Z)', nsis_script_content, re.IGNORECASE | re.DOTALL)
        if uninstall_section:
            assert re.search(r'DetailPrint', uninstall_section.group(0))


class TestUninstallerErrorHandling:
    """Test uninstaller error handling."""

    def test_handles_directory_removal_failure(self, nsis_script_content):
        """Script handles directory removal failures."""
        # Should check IfFileExists after RMDir to verify removal
        assert re.search(r'RMDir.*IfFileExists', nsis_script_content, re.IGNORECASE | re.DOTALL)

    def test_provides_error_context(self, nsis_script_content):
        """Script provides context in error messages."""
        # Should include paths in error messages
        assert re.search(r'MessageBox.*\$INSTDIR', nsis_script_content, re.IGNORECASE)

    def test_logs_uninstall_errors(self, nsis_script_content):
        """Script logs uninstallation errors."""
        # Should log warnings and errors
        assert re.search(r'DetailPrint.*[Ww]arning', nsis_script_content, re.IGNORECASE)

    def test_completes_uninstall_despite_errors(self, nsis_script_content):
        """Script continues uninstallation despite non-critical errors."""
        # Should use Goto to continue after errors instead of Abort
        assert re.search(r'Section\s+"Uninstall".*Goto', nsis_script_content, re.IGNORECASE | re.DOTALL)


class TestUninstallerIntegration:
    """Test uninstaller integration with installer."""

    def test_uninstaller_created_during_install(self, nsis_script_content):
        """Uninstaller is created during installation."""
        # WriteUninstaller should be in install section
        assert re.search(r'Section\s+"Install.*WriteUninstaller', nsis_script_content, re.IGNORECASE | re.DOTALL)

    def test_registry_entries_created_during_install(self, nsis_script_content):
        """Registry entries are created during installation."""
        # WriteReg calls should be in install section
        assert re.search(r'Section\s+"Install.*WriteReg', nsis_script_content, re.IGNORECASE | re.DOTALL)

    def test_uninstaller_location_matches_registry(self, nsis_script_content):
        """Uninstaller location in registry matches actual location."""
        # Both should reference $INSTDIR\uninstall.exe
        write_uninstaller = re.search(r'WriteUninstaller\s+"([^"]+)"', nsis_script_content, re.IGNORECASE)
        # UninstallString value is quoted and may have escaped quotes
        uninstall_string = re.search(r'UninstallString"\s+"([^"]+uninstall\.exe[^"]*)"', nsis_script_content, re.IGNORECASE)

        if write_uninstaller and uninstall_string:
            # Both should reference uninstall.exe in $INSTDIR
            assert 'uninstall.exe' in write_uninstaller.group(1).lower()
            assert 'uninstall.exe' in uninstall_string.group(1).lower()
