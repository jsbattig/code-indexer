; MCPB Windows Installer with Authentication Wizard
; Implements Story #576: Windows Installer with Auth Wizard
;
; CRITICAL CONSTRAINT: NO POWERSHELL - Pure NSIS with plugins only
;
; Features:
; - MCPB extraction and unblocking (AC1)
; - Authentication GUI wizard (AC2)
; - API authentication via NScurl (AC3)
; - MCPB configuration generation (AC4)
; - Claude Desktop integration (AC5)
; - Silent installation mode (AC6)
; - Comprehensive error handling (AC7)

;--------------------------------
; Includes

!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

;--------------------------------
; Plugin Directory

!addplugindir "plugins"

;--------------------------------
; Installer Metadata

Name "MCPB Installer"
OutFile "mcpb-installer.exe"
InstallDir "C:\\mcpb"
RequestExecutionLevel admin
SilentInstall normal

;--------------------------------
; Build-Time Configuration

!define DEFAULT_SERVER_URL "https://linner.ddns.net:8383"
!define PRODUCT_VERSION "1.0.0"

;--------------------------------
; Variables

Var Dialog
Var ServerUrlLabel
Var ServerUrlText
Var UsernameLabel
Var UsernameText
Var PasswordLabel
Var PasswordText

Var ServerUrl
Var Username
Var Password
Var AccessToken
Var RefreshToken
Var HttpStatusCode
Var ErrorMessage
Var SilentMode
Var AuthSuccess
Var ClaudeIntegrationFailed

;--------------------------------
; MUI Settings

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"

;--------------------------------
; Pages

!insertmacro MUI_PAGE_WELCOME
Page custom AuthPage AuthPageLeave
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Initialization Function

Function .onInit
    ; Check if running in silent mode
    StrCpy $SilentMode "0"
    ${GetParameters} $0
    ${If} $0 != ""
        ClearErrors
        ${GetOptions} $0 "/S" $1
        ${IfNot} ${Errors}
            StrCpy $SilentMode "1"
            DetailPrint "Silent mode enabled"

            ; Parse command-line parameters for silent mode
            ClearErrors
            ${GetOptions} $0 "/SERVER_URL=" $ServerUrl
            ${If} ${Errors}
                StrCpy $ServerUrl "${DEFAULT_SERVER_URL}"
            ${EndIf}

            ClearErrors
            ${GetOptions} $0 "/USERNAME=" $Username
            ${If} ${Errors}
                MessageBox MB_OK|MB_ICONSTOP "Silent installation requires /USERNAME parameter"
                SetErrorLevel 3
                Quit
            ${EndIf}

            ClearErrors
            ${GetOptions} $0 "/PASSWORD=" $Password
            ${If} ${Errors}
                MessageBox MB_OK|MB_ICONSTOP "Silent installation requires /PASSWORD parameter"
                SetErrorLevel 3
                Quit
            ${EndIf}

            DetailPrint "Silent mode parameters: ServerUrl=$ServerUrl, Username=$Username"
        ${EndIf}
    ${Else}
        ; GUI mode - set default server URL
        StrCpy $ServerUrl "${DEFAULT_SERVER_URL}"
    ${EndIf}

    StrCpy $AuthSuccess "0"
    StrCpy $ClaudeIntegrationFailed "0"
FunctionEnd

;--------------------------------
; Authentication Page (AC2)

Function AuthPage
    ; Skip in silent mode
    IfSilent 0 +2
        Abort

    ${If} $SilentMode == "1"
        Abort
    ${EndIf}

    nsDialogs::Create 1018
    Pop $Dialog

    ${If} $Dialog == error
        Abort
    ${EndIf}

    ; Title
    ${NSD_CreateLabel} 0 0 100% 10u "MCPB Authentication"
    Pop $0
    CreateFont $1 "Arial" 10 700
    SendMessage $0 ${WM_SETFONT} $1 0

    ; Instructions (single line to save space)
    ${NSD_CreateLabel} 0 12u 100% 10u "Enter your CIDX server credentials:"
    Pop $0

    ; Server URL
    ${NSD_CreateLabel} 0 28u 100% 10u "Server URL:"
    Pop $ServerUrlLabel

    ${NSD_CreateText} 0 38u 100% 12u "$ServerUrl"
    Pop $ServerUrlText

    ; Username
    ${NSD_CreateLabel} 0 56u 100% 10u "Username:"
    Pop $UsernameLabel

    ${NSD_CreateText} 0 66u 100% 12u ""
    Pop $UsernameText

    ; Password
    ${NSD_CreateLabel} 0 84u 100% 10u "Password:"
    Pop $PasswordLabel

    ${NSD_CreatePassword} 0 94u 100% 12u ""
    Pop $PasswordText

    ; Help text (fits at bottom)
    ${NSD_CreateLabel} 0 112u 100% 16u "Credentials are used to obtain tokens. Passwords are not stored."
    Pop $0

    nsDialogs::Show
FunctionEnd

Function AuthPageLeave
    ; Skip in silent mode
    ${If} $SilentMode == "1"
        Return
    ${EndIf}

    ; Get values from form
    ${NSD_GetText} $ServerUrlText $ServerUrl
    ${NSD_GetText} $UsernameText $Username
    ${NSD_GetText} $PasswordText $Password

    ; Validate inputs
    ${If} $ServerUrl == ""
        MessageBox MB_OK|MB_ICONEXCLAMATION "Please enter a server URL"
        Abort
    ${EndIf}

    ${If} $Username == ""
        MessageBox MB_OK|MB_ICONEXCLAMATION "Please enter a username"
        Abort
    ${EndIf}

    ${If} $Password == ""
        MessageBox MB_OK|MB_ICONEXCLAMATION "Please enter a password"
        Abort
    ${EndIf}

    ; Validate URL format
    StrCpy $0 $ServerUrl 7
    ${If} $0 != "http://"
        StrCpy $0 $ServerUrl 8
        ${If} $0 != "https://"
            MessageBox MB_OK|MB_ICONEXCLAMATION "Server URL must start with http:// or https://"
            Abort
        ${EndIf}
    ${EndIf}

    DetailPrint "Form validation passed: ServerUrl=$ServerUrl, Username=$Username"
FunctionEnd

;--------------------------------
; Main Installation Section (AC1, AC3, AC4, AC5)

Section "Install MCPB" SecInstall
    DetailPrint "Starting MCPB installation"

    ; AC1: Extract MCPB binary
    SetOutPath "C:\\mcpb\\server"
    DetailPrint "SetOutPath: C:\\mcpb\\server"

    ; Extract mcpb-windows-x64.exe from installer
    ; Note: Binary must exist at build time in scripts/installer/ directory
    ; Build with: python scripts/build_binary.py --platform windows
    File "mcpb-windows-x64.exe"
    DetailPrint "MCPB binary extracted to C:\\mcpb\\server\\mcpb-windows-x64.exe"

    ; Verify file exists after extraction (paranoid check for filesystem errors)
    IfFileExists "C:\\mcpb\\server\\mcpb-windows-x64.exe" extraction_success 0
        StrCpy $ErrorMessage "MCPB binary not found after extraction - possible filesystem error"
        DetailPrint "$ErrorMessage"
        ${If} $SilentMode == "1"
            SetErrorLevel 2
            Quit
        ${Else}
            MessageBox MB_OK|MB_ICONSTOP "$ErrorMessage"
            Abort
        ${EndIf}

    extraction_success:
        DetailPrint "Binary extraction verified successfully"

    ; AC3: Authenticate with API
    Call AuthenticateWithAPI

    ${If} $AuthSuccess == "0"
        ; Authentication failed
        ${If} $SilentMode == "1"
            DetailPrint "Authentication failed in silent mode, exiting"
            SetErrorLevel 1
            Quit
        ${Else}
            MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "Authentication failed: $ErrorMessage$\r$\n$\r$\nClick Retry to try again with different credentials, or Cancel to abort installation." IDRETRY retry
            DetailPrint "User cancelled after authentication failure"
            Abort

            retry:
            DetailPrint "User chose to retry authentication"
            Abort  ; Return to auth page
        ${EndIf}
    ${EndIf}

    ; AC4: Create MCPB configuration
    Call CreateMCPBConfig

    ${If} ${Errors}
        ${If} $SilentMode == "1"
            DetailPrint "Config creation failed in silent mode, exiting"
            SetErrorLevel 2
            Quit
        ${Else}
            MessageBox MB_OK|MB_ICONSTOP "Failed to create MCPB configuration: $ErrorMessage"
            Abort
        ${EndIf}
    ${EndIf}

    ; AC5: Integrate with Claude Desktop
    Call IntegrateWithClaudeDesktop

    ; Note: Claude Desktop integration failures are warnings, not errors
    ; Exit code 4 indicates partial success (MCPB installed but Claude Desktop failed)

    ; AC4 (Story #578): Write uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"
    DetailPrint "Uninstaller created at $INSTDIR\uninstall.exe"

    ; AC4 (Story #578): Write Add/Remove Programs registry entries
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MCPB" "DisplayName" "MCPB - MCP Bridge"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MCPB" "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MCPB" "Publisher" "Code Indexer"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MCPB" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MCPB" "InstallLocation" "$INSTDIR"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MCPB" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MCPB" "NoRepair" 1
    DetailPrint "Add/Remove Programs registry entries created"

    DetailPrint "MCPB installation completed successfully"

    ${If} $SilentMode == "1"
        ${If} $ClaudeIntegrationFailed == "1"
            DetailPrint "Setting exit code 4 (partial success - Claude Desktop integration failed)"
            SetErrorLevel 4
        ${Else}
            SetErrorLevel 0
        ${EndIf}
    ${Else}
        DetailPrint "Installation completed successfully!"
        DetailPrint "MCPB binary: C:\\mcpb\\server\\mcpb-windows-x64.exe"
        DetailPrint "Configuration: $PROFILE\\.mcpb\\config.json"
    ${EndIf}
SectionEnd

;--------------------------------
; AC3: API Authentication Function

Function AuthenticateWithAPI
    DetailPrint "AuthenticateWithAPI: Starting"
    DetailPrint "Server URL: $ServerUrl"

    ; Build JSON request body
    StrCpy $0 `{"username":"$Username","password":"$Password"}`

    ; Define temp file path
    StrCpy $3 "$TEMP\mcpb_auth_response.json"

    ; Make HTTP POST request - write response directly to file (NOT Memory mode)
    DetailPrint "Sending authentication request..."
    NScurl::http POST "$ServerUrl/auth/login" "$3" /HEADER "Content-Type: application/json" /DATA "$0" /TIMEOUT 30000 /END
    Pop $0

    DetailPrint "NScurl status: $0"

    ${If} $0 != "OK"
        StrCpy $ErrorMessage "Connection failed: $0"
        StrCpy $AuthSuccess "0"
        Return
    ${EndIf}

    ; Parse the response file directly with nsJSON
    DetailPrint "Parsing response..."
    ClearErrors
    nsJSON::Set /file "$3"
    ${If} ${Errors}
        StrCpy $ErrorMessage "Invalid server response"
        StrCpy $AuthSuccess "0"
        Delete "$3"
        Return
    ${EndIf}

    ; Clean up temp file
    Delete "$3"

    ; Extract access_token
    ClearErrors
    nsJSON::Get "access_token" /END
    Pop $AccessToken

    ${If} $AccessToken == ""
    ${OrIf} $AccessToken == "null"
        ; Try to get error message
        nsJSON::Get "detail" /END
        Pop $0
        ${If} $0 != ""
        ${AndIf} $0 != "null"
            StrCpy $ErrorMessage "$0"
        ${Else}
            StrCpy $ErrorMessage "Invalid username or password"
        ${EndIf}
        StrCpy $AuthSuccess "0"
        Return
    ${EndIf}

    ; Get refresh token
    nsJSON::Get "refresh_token" /END
    Pop $RefreshToken

    DetailPrint "Authentication successful"
    StrCpy $AuthSuccess "1"
FunctionEnd

;--------------------------------
; AC4: Create MCPB Configuration

Function CreateMCPBConfig
    DetailPrint "CreateMCPBConfig: Starting"

    ClearErrors

    ; Create .mcpb directory under %USERPROFILE%
    CreateDirectory "$PROFILE\.mcpb"
    ${If} ${Errors}
        StrCpy $ErrorMessage "Failed to create directory: $PROFILE\.mcpb"
        DetailPrint "$ErrorMessage"
        Return
    ${EndIf}

    DetailPrint "Created directory: $PROFILE\.mcpb"

    ; Construct config.json using nsJSON
    ; CRITICAL: nsJSON requires backticks for literal JSON values, not double quotes
    ClearErrors
    nsJSON::Set /value `{}`
    ${If} ${Errors}
        StrCpy $ErrorMessage "Failed to initialize config JSON"
        DetailPrint "$ErrorMessage"
        SetErrors
        Return
    ${EndIf}

    ; Set server_url
    ClearErrors
    nsJSON::Set "server_url" /VALUE `"$ServerUrl"` /END
    ${If} ${Errors}
        StrCpy $ErrorMessage "Failed to set server_url in config"
        DetailPrint "$ErrorMessage"
        SetErrors
        Return
    ${EndIf}

    ; Set access_token
    ClearErrors
    nsJSON::Set "access_token" /VALUE `"$AccessToken"` /END
    ${If} ${Errors}
        StrCpy $ErrorMessage "Failed to set access_token in config"
        DetailPrint "$ErrorMessage"
        SetErrors
        Return
    ${EndIf}

    ; Set refresh_token
    ClearErrors
    nsJSON::Set "refresh_token" /VALUE `"$RefreshToken"` /END
    ${If} ${Errors}
        StrCpy $ErrorMessage "Failed to set refresh_token in config"
        DetailPrint "$ErrorMessage"
        SetErrors
        Return
    ${EndIf}

    ; Serialize to JSON string
    nsJSON::Serialize /PRETTY /UNICODE
    Pop $0  ; JSON string

    DetailPrint "Config JSON: $0"

    ; Write config.json file
    ClearErrors
    FileOpen $1 "$PROFILE\.mcpb\config.json" w
    ${If} ${Errors}
        StrCpy $ErrorMessage "Failed to open config file for writing: $PROFILE\.mcpb\config.json"
        DetailPrint "$ErrorMessage"
        Return
    ${EndIf}

    FileWrite $1 "$0"
    FileClose $1

    ${If} ${Errors}
        StrCpy $ErrorMessage "Failed to write config file: $PROFILE\.mcpb\config.json"
        DetailPrint "$ErrorMessage"
        Return
    ${EndIf}

    DetailPrint "Config file created successfully: $PROFILE\.mcpb\config.json"
    DetailPrint "MCPB configuration created at $PROFILE\.mcpb\config.json"
FunctionEnd

;--------------------------------
; AC5: Claude Desktop Integration

Function IntegrateWithClaudeDesktop
    DetailPrint "IntegrateWithClaudeDesktop: Starting"

    ClearErrors

    ; Detect Claude Desktop config location
    StrCpy $0 "$APPDATA\Claude"

    IfFileExists "$0\*.*" claude_exists claude_missing

    claude_missing:
        DetailPrint "Claude Desktop not found at $0"
        StrCpy $ClaudeIntegrationFailed "1"
        ${If} $SilentMode == "1"
            DetailPrint "Skipping Claude Desktop integration (not installed)"
        ${Else}
            DetailPrint "Warning: Claude Desktop not found - skipping integration"
            MessageBox MB_OK|MB_ICONINFORMATION "Claude Desktop is not installed on this system.$\r$\n$\r$\nMCPB has been installed successfully, but automatic integration with Claude Desktop was skipped.$\r$\n$\r$\nTo manually configure Claude Desktop, add this to claude_desktop_config.json:$\r$\n$\r$\n{$\r$\n  $\"mcpServers$\": {$\r$\n    $\"mcpb$\": {$\r$\n      $\"command$\": $\"$INSTDIR\\\\server\\\\mcpb-windows-x64.exe$\",$\r$\n      $\"args$\": []$\r$\n    }$\r$\n  }$\r$\n}"
        ${EndIf}
        Return

    claude_exists:
        DetailPrint "Claude Desktop found at $0"

        ; Check if config file exists
        IfFileExists "$0\claude_desktop_config.json" config_exists config_missing

        config_missing:
            DetailPrint "claude_desktop_config.json does not exist, creating new"

            ; Create new config with mcpb entry - build incrementally with backticks
            ; CRITICAL: nsJSON requires backticks for literal JSON values
            ClearErrors
            nsJSON::Set /value `{}`
            ${If} ${Errors}
                DetailPrint "Failed to initialize Claude Desktop config JSON"
                DetailPrint "Warning: Failed to create Claude Desktop config"
                StrCpy $ClaudeIntegrationFailed "1"
                Return
            ${EndIf}

            ; Add mcpServers object
            nsJSON::Set "mcpServers" /value `{}`
            ; Add mcpb entry under mcpServers
            nsJSON::Set "mcpServers" "mcpb" /value `{}`
            ; Set command path (variable expansion works in backticks)
            nsJSON::Set "mcpServers" "mcpb" "command" /value `"$INSTDIR\server\mcpb-windows-x64.exe"`
            ; Set empty args array
            nsJSON::Set "mcpServers" "mcpb" "args" /value `[]`

            Goto write_config

        config_exists:
            DetailPrint "claude_desktop_config.json exists, merging"

            ; Parse existing JSON directly from file (more reliable than FileRead + /value)
            ClearErrors
            nsJSON::Set /file "$0\claude_desktop_config.json"
            ${If} ${Errors}
                DetailPrint "Failed to parse existing config at $0\claude_desktop_config.json"
                DetailPrint "Warning: Existing Claude Desktop config at $0 is invalid JSON"
                StrCpy $ClaudeIntegrationFailed "1"
                Return
            ${EndIf}

            ; Check if mcpServers exists
            nsJSON::Get "mcpServers" /END
            Pop $4  ; Value
            Pop $3  ; Result

            ${If} $3 != "ok"
                ; mcpServers doesn't exist, create it
                DetailPrint "mcpServers object not found, creating"
                ClearErrors
                nsJSON::Set "mcpServers" /VALUE `{}` /END
            ${EndIf}

            ; Check if mcpb entry already exists
            nsJSON::Get "mcpServers" "mcpb" /END
            Pop $4  ; Value
            Pop $3  ; Result

            ${If} $3 == "ok"
                ; mcpb entry already exists
                DetailPrint "Existing mcpb entry found in Claude Desktop config"
                ${If} $SilentMode == "1"
                    DetailPrint "Silent mode: Overwriting existing mcpb entry"
                ${Else}
                    MessageBox MB_YESNO|MB_ICONQUESTION "An existing MCPB configuration was found in Claude Desktop.$\r$\n$\r$\nDo you want to overwrite it with the new configuration?" IDYES overwrite
                    DetailPrint "User chose not to overwrite existing mcpb entry"
                    Return
                    overwrite:
                    DetailPrint "User confirmed overwrite of existing mcpb entry"
                ${EndIf}
            ${EndIf}

            ; Add mcpb entry to mcpServers
            ClearErrors
            nsJSON::Set "mcpServers" "mcpb" /VALUE `{"command":"$INSTDIR\\\\server\\\\mcpb-windows-x64.exe","args":[]}` /END
            ${If} ${Errors}
                DetailPrint "Failed to merge mcpb entry"
                DetailPrint "Warning: Failed to merge MCPB into Claude Desktop config"
                StrCpy $ClaudeIntegrationFailed "1"
                Return
            ${EndIf}

        write_config:
            ; Serialize merged config
            nsJSON::Serialize /PRETTY /UNICODE
            Pop $1  ; JSON string

            DetailPrint "Writing merged config: $1"

            ; Write config file
            ClearErrors
            FileOpen $2 "$0\claude_desktop_config.json" w
            ${If} ${Errors}
                DetailPrint "Failed to open claude_desktop_config.json for writing at $0"
                DetailPrint "Warning: Could not write Claude Desktop config at $0"
                StrCpy $ClaudeIntegrationFailed "1"
                Return
            ${EndIf}

            FileWrite $2 "$1"
            FileClose $2

            ${If} ${Errors}
                DetailPrint "Failed to write claude_desktop_config.json at $0"
                DetailPrint "Warning: Error writing Claude Desktop config at $0"
                StrCpy $ClaudeIntegrationFailed "1"
                Return
            ${EndIf}

            DetailPrint "Claude Desktop integration completed successfully"
            DetailPrint "Claude Desktop configured with MCPB integration"
FunctionEnd

;--------------------------------
; Uninstall Section (Story #578)

Section "Uninstall"
    DetailPrint "Starting MCPB uninstallation"

    ; AC1: Remove installation directory
    DetailPrint "Removing installation directory: $INSTDIR"

    ; Check if directory exists
    IfFileExists "$INSTDIR\*.*" dir_exists dir_missing

    dir_missing:
        DetailPrint "Installation directory not found (already removed or moved)"
        Goto remove_config

    dir_exists:
        ; Try to remove directory
        RMDir /r "$INSTDIR"

        ; Check if removal succeeded
        IfFileExists "$INSTDIR\*.*" dir_locked dir_removed

        dir_locked:
            ; Directory still exists - files may be locked
            DetailPrint "Warning: Some files in $INSTDIR could not be removed (may be in use)"
            IfSilent silent_dir_error
            MessageBox MB_OK|MB_ICONEXCLAMATION "Some files in $INSTDIR could not be removed.$\r$\n$\r$\nPlease close any applications using MCPB and run uninstaller again."
            silent_dir_error:
            SetErrorLevel 2
            ; Continue with rest of uninstallation
            Goto remove_config

        dir_removed:
            DetailPrint "Installation directory removed successfully"

    remove_config:
        ; AC2: Remove configuration directory
        DetailPrint "Removing configuration directory: $PROFILE\.mcpb"

        IfFileExists "$PROFILE\.mcpb\*.*" config_exists config_missing

        config_missing:
            DetailPrint "Configuration directory not found (already removed or never created)"
            Goto remove_claude_config

        config_exists:
            RMDir /r "$PROFILE\.mcpb"

            IfFileExists "$PROFILE\.mcpb\*.*" config_locked config_removed

            config_locked:
                DetailPrint "Warning: Configuration directory could not be removed"
                IfSilent silent_config_error
                MessageBox MB_OK|MB_ICONEXCLAMATION "Configuration directory $PROFILE\.mcpb could not be removed."
                silent_config_error:
                SetErrorLevel 2
                Goto remove_claude_config

            config_removed:
                DetailPrint "Configuration directory removed successfully"

    remove_claude_config:
        ; AC3: Remove MCPB from Claude Desktop configuration
        Call un.RemoveMcpbFromClaudeConfig

    ; AC4: Remove Add/Remove Programs registry entries
    DetailPrint "Removing registry entries"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MCPB"
    DetailPrint "Registry entries removed"

    DetailPrint "MCPB uninstallation completed"

    ; Set exit code based on success
    IfErrors uninstall_error uninstall_success

    uninstall_error:
        DetailPrint "Uninstallation completed with errors"
        IfSilent 0 +2
        SetErrorLevel 1
        Goto end_uninstall

    uninstall_success:
        DetailPrint "Uninstallation completed successfully"
        IfSilent 0 +2
        SetErrorLevel 0

    end_uninstall:
SectionEnd

;--------------------------------
; AC3 (Story #578): Remove MCPB from Claude Desktop Config

Function un.RemoveMcpbFromClaudeConfig
    DetailPrint "un.RemoveMcpbFromClaudeConfig: Starting"

    ClearErrors

    ; Detect Claude Desktop config location
    StrCpy $0 "$APPDATA\Claude"

    IfFileExists "$0\claude_desktop_config.json" config_exists config_missing

    config_missing:
        DetailPrint "Claude Desktop config not found at $0\claude_desktop_config.json"
        Return

    config_exists:
        DetailPrint "Claude Desktop config found at $0\claude_desktop_config.json"

        ; Parse existing JSON directly from file (more reliable than FileRead + /value)
        ClearErrors
        nsJSON::Set /file "$0\claude_desktop_config.json"
        ${If} ${Errors}
            DetailPrint "Failed to parse Claude Desktop config at $0\claude_desktop_config.json"
            Return
        ${EndIf}

        ; Check if mcpServers exists
        nsJSON::Get "mcpServers" /END
        Pop $4  ; Value
        Pop $3  ; Result

        ${If} $3 != "ok"
            ; mcpServers doesn't exist - nothing to remove
            DetailPrint "mcpServers object not found in config - nothing to remove"
            Return
        ${EndIf}

        ; Check if mcpb entry exists
        nsJSON::Get "mcpServers" "mcpb" /END
        Pop $4  ; Value
        Pop $3  ; Result

        ${If} $3 != "ok"
            ; mcpb entry doesn't exist - nothing to remove
            DetailPrint "mcpb entry not found in mcpServers - nothing to remove"
            Return
        ${EndIf}

        ; Remove mcpb entry from mcpServers
        DetailPrint "Removing mcpb entry from mcpServers"
        nsJSON::Delete "mcpServers" "mcpb" /END
        Pop $3

        ${If} $3 != "ok"
            DetailPrint "Failed to remove mcpb entry: $3"
            Return
        ${EndIf}

        ; Serialize updated config
        nsJSON::Serialize /PRETTY /UNICODE
        Pop $1  ; JSON string

        DetailPrint "Writing updated Claude Desktop config: $1"

        ; Write updated config file
        ClearErrors
        FileOpen $2 "$0\claude_desktop_config.json" w
        ${If} ${Errors}
            DetailPrint "Failed to open claude_desktop_config.json for writing"
            Return
        ${EndIf}

        FileWrite $2 "$1"
        FileClose $2

        ${If} ${Errors}
            DetailPrint "Failed to write updated Claude Desktop config"
            Return
        ${EndIf}

        DetailPrint "MCPB entry removed from Claude Desktop config successfully"
FunctionEnd
