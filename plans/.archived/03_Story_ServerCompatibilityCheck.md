# User Story: Server Compatibility Check

## 📋 **User Story**

As a **CIDX user**, I want **comprehensive server compatibility validation during remote initialization**, so that **I can be confident my remote setup will work correctly and receive clear guidance when compatibility issues exist**.

## 🎯 **Business Value**

Prevents incompatible remote configurations that would fail during operation. Users get immediate feedback about server compatibility issues with actionable guidance for resolution, avoiding frustration from mysterious failures later.

## 📝 **Acceptance Criteria**

### Given: API Version Compatibility Validation
**When** I initialize remote mode with a server  
**Then** the system checks API version compatibility between client and server  
**And** prevents initialization if versions are incompatible  
**And** provides clear guidance about version requirements  
**And** suggests upgrade paths when version mismatches exist  

### Given: Server Health Verification
**When** I test server compatibility  
**Then** the system validates server is operational and responsive  
**And** checks essential API endpoints are accessible  
**And** verifies server can handle authentication requests  
**And** tests basic query capabilities if authentication succeeds  

### Given: Network Connectivity Validation
**When** I provide server URL during initialization  
**Then** the system tests network connectivity to server  
**And** validates SSL/TLS certificate if using HTTPS  
**And** checks for network firewalls or proxy issues  
**And** provides specific network troubleshooting guidance  

### Given: Authentication System Verification
**When** I complete server compatibility checks  
**Then** the system validates JWT authentication system is working  
**And** tests token generation and validation flows  
**And** verifies user permissions for remote operations  
**And** confirms credential format compatibility  

## 🏗️ **Technical Implementation**

### Server Compatibility Validator
```python
from dataclasses import dataclass
from typing import Dict, List, Optional
import httpx
import ssl
from urllib.parse import urljoin

@dataclass
class CompatibilityResult:
    compatible: bool
    issues: List[str]
    warnings: List[str]
    server_info: Dict[str, Any]
    recommendations: List[str]

class ServerCompatibilityValidator:
    """Comprehensive server compatibility validation."""
    
    REQUIRED_API_VERSION = "v1"
    COMPATIBLE_VERSIONS = ["v1", "v1.1", "v1.2"]
    REQUIRED_ENDPOINTS = [
        "/api/health",
        "/api/auth/login",
        "/api/repos/discover",
        "/api/user/info"
    ]
    
    def __init__(self, server_url: str, timeout: float = 30.0):
        self.server_url = server_url.rstrip('/')
        self.session = httpx.AsyncClient(timeout=timeout)
    
    async def validate_compatibility(
        self, 
        username: str, 
        password: str
    ) -> CompatibilityResult:
        """Perform comprehensive server compatibility validation."""
        issues = []
        warnings = []
        server_info = {}
        recommendations = []
        
        try:
            # Step 1: Basic connectivity test
            connectivity_result = await self._test_connectivity()
            if not connectivity_result['success']:
                issues.extend(connectivity_result['issues'])
                recommendations.extend(connectivity_result['recommendations'])
                return CompatibilityResult(
                    compatible=False,
                    issues=issues,
                    warnings=warnings,
                    server_info=server_info,
                    recommendations=recommendations
                )
            
            # Step 2: Server health check
            health_result = await self._check_server_health()
            server_info.update(health_result.get('server_info', {}))
            
            if not health_result['healthy']:
                issues.extend(health_result['issues'])
                recommendations.extend(health_result['recommendations'])
            
            # Step 3: API version compatibility
            version_result = await self._check_api_version()
            if not version_result['compatible']:
                issues.extend(version_result['issues'])
                recommendations.extend(version_result['recommendations'])
            
            warnings.extend(version_result.get('warnings', []))
            
            # Step 4: Authentication system validation
            auth_result = await self._validate_authentication(username, password)
            if not auth_result['valid']:
                issues.extend(auth_result['issues'])
                recommendations.extend(auth_result['recommendations'])
            
            server_info.update(auth_result.get('user_info', {}))
            
            # Step 5: Essential endpoint availability
            endpoints_result = await self._check_required_endpoints()
            if not endpoints_result['available']:
                issues.extend(endpoints_result['issues'])
                recommendations.extend(endpoints_result['recommendations'])
            
            warnings.extend(endpoints_result.get('warnings', []))
            
            # Determine overall compatibility
            compatible = len(issues) == 0
            
            return CompatibilityResult(
                compatible=compatible,
                issues=issues,
                warnings=warnings,
                server_info=server_info,
                recommendations=recommendations
            )
            
        except Exception as e:
            return CompatibilityResult(
                compatible=False,
                issues=[f"Unexpected error during compatibility check: {str(e)}"],
                warnings=[],
                server_info={},
                recommendations=["Check server URL and network connectivity"]
            )
        
        finally:
            await self.session.aclose()
    
    async def _test_connectivity(self) -> Dict[str, Any]:
        """Test basic network connectivity to server."""
        try:
            response = await self.session.get(self.server_url)
            return {
                'success': True,
                'status_code': response.status_code,
                'response_time': response.elapsed.total_seconds()
            }
            
        except httpx.ConnectError:
            return {
                'success': False,
                'issues': ["Cannot connect to server - connection refused"],
                'recommendations': [
                    "Verify server URL is correct",
                    "Check if server is running and accessible",
                    "Verify firewall settings allow outbound connections"
                ]
            }
        except httpx.TimeoutException:
            return {
                'success': False,
                'issues': ["Connection to server timed out"],
                'recommendations': [
                    "Check network connectivity",
                    "Server may be overloaded or slow to respond",
                    "Consider increasing timeout if server is known to be slow"
                ]
            }
        except ssl.SSLError as e:
            return {
                'success': False,
                'issues': [f"SSL/TLS certificate error: {str(e)}"],
                'recommendations': [
                    "Verify server SSL certificate is valid",
                    "Check if using correct HTTPS URL",
                    "Contact server administrator about certificate issues"
                ]
            }
    
    async def _check_server_health(self) -> Dict[str, Any]:
        """Check server health and basic operational status."""
        try:
            response = await self.session.get(urljoin(self.server_url, "/api/health"))
            
            if response.status_code == 200:
                health_data = response.json()
                return {
                    'healthy': True,
                    'server_info': {
                        'version': health_data.get('version'),
                        'status': health_data.get('status'),
                        'uptime': health_data.get('uptime')
                    }
                }
            else:
                return {
                    'healthy': False,
                    'issues': [f"Server health check failed with status {response.status_code}"],
                    'recommendations': ["Server may be experiencing issues - contact administrator"]
                }
                
        except Exception as e:
            return {
                'healthy': False,
                'issues': [f"Health check endpoint not accessible: {str(e)}"],
                'recommendations': [
                    "Server may not support health checks",
                    "Verify this is a CIDX server"
                ]
            }
    
    async def _check_api_version(self) -> Dict[str, Any]:
        """Validate API version compatibility."""
        try:
            response = await self.session.get(urljoin(self.server_url, "/api/version"))
            
            if response.status_code == 200:
                version_data = response.json()
                server_version = version_data.get('api_version')
                
                if server_version in self.COMPATIBLE_VERSIONS:
                    warnings = []
                    if server_version != self.REQUIRED_API_VERSION:
                        warnings.append(
                            f"Server API version {server_version} is compatible but not optimal. "
                            f"Recommended version: {self.REQUIRED_API_VERSION}"
                        )
                    
                    return {
                        'compatible': True,
                        'server_version': server_version,
                        'warnings': warnings
                    }
                else:
                    return {
                        'compatible': False,
                        'issues': [
                            f"Incompatible API version: server={server_version}, "
                            f"required={self.COMPATIBLE_VERSIONS}"
                        ],
                        'recommendations': [
                            "Upgrade CIDX client to match server version",
                            "Or ask administrator to upgrade server"
                        ]
                    }
            else:
                return {
                    'compatible': False,
                    'issues': ["Cannot determine server API version"],
                    'recommendations': ["Verify this is a compatible CIDX server"]
                }
                
        except Exception:
            return {
                'compatible': False,
                'issues': ["API version endpoint not accessible"],
                'recommendations': ["Server may be running older incompatible version"]
            }
```

### Integration with Initialization
```python
async def initialize_remote_mode_with_validation(
    project_root: Path, 
    server_url: str, 
    username: str, 
    password: str
):
    """Initialize remote mode with comprehensive compatibility validation."""
    click.echo("🌐 Initializing CIDX Remote Mode")
    click.echo("=" * 35)
    
    # Comprehensive server compatibility check
    click.echo("🔍 Validating server compatibility...")
    
    validator = ServerCompatibilityValidator(server_url)
    compatibility_result = await validator.validate_compatibility(username, password)
    
    # Display results
    if compatibility_result.compatible:
        click.echo("✅ Server compatibility validated successfully")
        
        if compatibility_result.server_info:
            server_version = compatibility_result.server_info.get('version')
            if server_version:
                click.echo(f"💻 Server version: {server_version}")
        
        # Show warnings if any
        for warning in compatibility_result.warnings:
            click.echo(f"⚠️  Warning: {warning}")
    
    else:
        click.echo("❌ Server compatibility validation failed")
        
        # Display issues
        click.echo("\n🚫 Issues found:")
        for issue in compatibility_result.issues:
            click.echo(f"  • {issue}")
        
        # Display recommendations
        if compatibility_result.recommendations:
            click.echo("\n💡 Recommendations:")
            for rec in compatibility_result.recommendations:
                click.echo(f"  • {rec}")
        
        raise ClickException("Cannot initialize remote mode due to compatibility issues")
    
    # Continue with initialization if compatible...
    # (rest of initialization process)
```

## 🧪 **Testing Requirements**

### Unit Tests
- ✅ API version compatibility validation logic
- ✅ Server health check response parsing
- ✅ Network connectivity error handling
- ✅ Authentication validation workflows

### Integration Tests
- ✅ End-to-end compatibility validation with real servers
- ✅ Version mismatch scenarios
- ✅ Network failure simulation and error handling
- ✅ SSL certificate validation

### Mock Server Tests
- ✅ Incompatible server version responses
- ✅ Unhealthy server status responses
- ✅ Authentication failure scenarios
- ✅ Missing endpoint simulation

## 📊 **Definition of Done**

- ✅ ServerCompatibilityValidator with comprehensive validation logic
- ✅ API version compatibility checking with clear version requirements
- ✅ Server health verification including essential endpoints
- ✅ Network connectivity validation with SSL certificate checking
- ✅ Authentication system verification with user permission validation
- ✅ Clear error messages and actionable recommendations for all failure scenarios
- ✅ Integration with remote initialization process
- ✅ Comprehensive testing including mock servers and error scenarios
- ✅ User experience validation with clear success and failure feedback
- ✅ Documentation updated with compatibility requirements and troubleshooting