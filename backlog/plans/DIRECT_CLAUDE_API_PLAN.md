# Claude API Integration Implementation Plan

## Overview

This document outlines the complete implementation plan for adding `--use-api` mode to the Claude integration, enabling direct API calls with JSON-based tool utilization instead of relying on Claude CLI. The new system replaces text-based exploration markers with structured JSON tool calls for precise, parallel execution.

## Current State Analysis

### Existing Claude Integration Architecture
- **Primary Service**: `ClaudeIntegrationService` in `src/code_indexer/services/claude_integration.py`
- **Method**: Subprocess calls to Claude CLI (`claude --print`)
- **Features**: Streaming output via Textual framework, tool usage tracking, sophisticated prompt engineering
- **Context Extraction**: `RAGContextExtractor` for semantic search result processing
- **CLI Integration**: `claude` command with options like `--show-claude-plan`, `--stream`, `--quiet`

### Key Components Already in Place
1. **Semantic Search Infrastructure**: Qdrant + embedding providers (VoyageAI/Ollama)
2. **Context Management**: Line-based context extraction with configurable windows
3. **Tool Activity Streaming**: Real-time tool usage tracking with visual feedback
4. **Configuration System**: YAML-based config with service management
5. **Test Infrastructure**: Comprehensive E2E and unit testing

## New Architecture: JSON Tool-Based Direct API Integration

### Core Concept
```
User Query → Initial Context → Claude API → JSON Tool Calls → 
Parallel Tool Execution → Results → Claude API → More Tools/Final Response
```

### Key Design Principles
1. **JSON Tool Calls**: Structured, parseable tool requests with unique IDs
2. **Parallel Execution**: Claude can request multiple tools simultaneously
3. **Stateless Design**: No session state, fresh context on each call
4. **Pluggable Tools**: Easy registration of new tool capabilities
5. **Error Recovery**: Claude handles tool failures and retries
6. **Unique ID Tracking**: Every tool execution has Claude-generated unique ID
7. **Configurable Timeouts**: Tools can specify execution limits
8. **Tool Limits Exposure**: Tools communicate their capabilities and constraints
9. **JSON Streaming Output**: Machine-readable streaming output for web integration

## Implementation Plan

### Phase 1: Shared Architecture and Refactoring

#### 1.1 Semantic Search Service Abstraction
**File**: `src/code_indexer/services/semantic_search_service.py`

Refactor existing query functionality into reusable service:
```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path

class SemanticSearchService:
    """Centralized semantic search service using existing Qdrant + VoyageAI infrastructure."""
    
    def __init__(self, config_manager: 'ConfigManager', codebase_dir: Path):
        self.config_manager = config_manager
        self.codebase_dir = codebase_dir
        # Reuse existing query infrastructure
    
    async def semantic_search(
        self, 
        query: str,
        limit: int = 10,
        language: Optional[str] = None,
        path_filter: Optional[str] = None,
        min_score: Optional[float] = None,
        file_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Unified semantic search using existing Qdrant + VoyageAI voyage-code-3 infrastructure.
        
        This method wraps the existing query functionality to be reusable across:
        - CLI query command
        - Claude CLI integration  
        - Claude API tool calls
        """
        # Implementation reuses existing query logic from cli.py
        pass
    
    async def search_with_context_expansion(
        self,
        query: str, 
        context_lines: int = 500,
        **search_kwargs
    ) -> Tuple[List[Dict[str, Any]], List['CodeContext']]:
        """Combined search + context extraction for efficiency."""
        search_results = await self.semantic_search(query, **search_kwargs)
        contexts = self.extract_contexts(search_results, context_lines)
        return search_results, contexts
    
    def extract_contexts(
        self, 
        search_results: List[Dict[str, Any]], 
        context_lines: int = 500
    ) -> List['CodeContext']:
        """Extract contexts using existing RAGContextExtractor."""
        # Delegate to existing RAGContextExtractor
        pass
```

#### 1.2 Context Extraction Refactoring  
**File**: `src/code_indexer/services/context_extraction_service.py`

Make RAGContextExtractor reusable across modes:
```python
class ContextExtractionService:
    """Service for extracting code context around search matches."""
    
    def __init__(self, codebase_dir: Path):
        self.extractor = RAGContextExtractor(codebase_dir)  # Reuse existing
    
    def extract_context_from_results(
        self,
        search_results: List[Dict[str, Any]],
        context_lines: int = 500,
        max_total_lines: int = 5000,
        ensure_all_files: bool = True,
    ) -> List[CodeContext]:
        """Wrapper around existing RAGContextExtractor for consistency."""
        return self.extractor.extract_context_from_results(
            search_results, context_lines, max_total_lines, ensure_all_files
        )
    
    def extract_file_context(
        self, 
        file_path: str, 
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
        context_lines: int = 50
    ) -> CodeContext:
        """Extract context for specific file ranges (for tools)."""
        # New functionality for tools
        pass
        
    def extract_function_context(
        self, 
        file_path: str, 
        function_name: str,
        include_dependencies: bool = False
    ) -> List[CodeContext]:
        """Extract context around specific functions (for tools)."""
        # New functionality for tools  
        pass
```

#### 1.3 Model-Agnostic Analysis Engine
**File**: `src/code_indexer/services/analysis_engine.py`

Create shared analysis coordination layer:
```python
from enum import Enum
from typing import Union, AsyncIterator, Dict, Any, List

class AnalysisMode(Enum):
    CLAUDE_CLI = "claude_cli"          # Existing Claude CLI subprocess
    CLAUDE_API_TOOLS = "claude_api_tools"  # New Claude API with tools
    # Future: GEMINI_API = "gemini_api"

class CodeAnalysisEngine:
    """
    Unified code analysis engine that coordinates:
    1. Semantic search (reusing existing Qdrant + VoyageAI)
    2. Context extraction (reusing existing RAGContextExtractor) 
    3. LLM interaction (mode-specific: CLI vs API)
    """
    
    def __init__(
        self, 
        config_manager: 'ConfigManager',
        codebase_dir: Path,
        mode: AnalysisMode = AnalysisMode.CLAUDE_CLI
    ):
        self.config_manager = config_manager
        self.codebase_dir = codebase_dir
        self.mode = mode
        
        # Shared services (reuse existing infrastructure)
        self.search_service = SemanticSearchService(config_manager, codebase_dir)
        self.context_service = ContextExtractionService(codebase_dir)
        
        # Mode-specific integration
        if mode == AnalysisMode.CLAUDE_CLI:
            self.llm_service = ClaudeIntegrationService(codebase_dir)  # Existing
        elif mode == AnalysisMode.CLAUDE_API_TOOLS:
            self.llm_service = ClaudeAPIService(config_manager.claude_api)  # New
    
    async def analyze_code_question(
        self,
        question: str,
        output_handler: Optional['OutputHandler'] = None,
        **kwargs
    ) -> 'AnalysisResult':
        """
        Unified analysis method that works for both CLI and API modes.
        
        Coordinates:
        1. Initial semantic search using existing infrastructure
        2. Context extraction using existing RAGContextExtractor  
        3. LLM interaction (mode-specific)
        4. Result formatting and streaming
        """
        # 1. Initial semantic search (reuse existing query logic)
        search_results, initial_contexts = await self.search_service.search_with_context_expansion(
            question, 
            limit=kwargs.get('limit', 10),
            context_lines=kwargs.get('context_lines', 500)
        )
        
        # 2. LLM Analysis (mode-specific)
        if self.mode == AnalysisMode.CLAUDE_CLI:
            return await self._analyze_with_cli(question, initial_contexts, **kwargs)
        elif self.mode == AnalysisMode.CLAUDE_API_TOOLS:
            return await self._analyze_with_api_tools(question, initial_contexts, output_handler, **kwargs)
    
    async def _analyze_with_cli(self, question: str, contexts: List[CodeContext], **kwargs):
        """Use existing Claude CLI integration."""
        return await self.llm_service.run_analysis(question, contexts, **kwargs)
    
    async def _analyze_with_api_tools(self, question: str, contexts: List[CodeContext], output_handler, **kwargs):
        """Use new Claude API with tools."""
        # This is where the new tool-based analysis happens
        pass
```

#### 1.4 Base Tool Architecture
**File**: `src/code_indexer/services/claude_tools/base_tool.py`

Create abstract base class for all tools:
```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

@dataclass
class ToolLimits:
    max_execution_time_seconds: int
    max_results: Optional[int] = None
    max_file_size_mb: Optional[int] = None
    rate_limit_per_minute: Optional[int] = None
    memory_limit_mb: Optional[int] = None
    custom_limits: Dict[str, Any] = None

class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: pass
    
    @property
    @abstractmethod 
    def description(self) -> str: pass
    
    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]: pass
    
    def get_limits(self) -> ToolLimits: pass
    def get_usage_examples(self) -> List[Dict[str, Any]]: pass
    def get_detailed_description(self) -> str: pass
    
    @abstractmethod
    async def execute(self, execution_id: str, parameters: Dict[str, Any], 
                     services: Dict[str, Any], timeout_seconds: Optional[int] = None) -> Dict[str, Any]: pass
```

#### 1.2 Tool Registry System
**File**: `src/code_indexer/services/claude_tools/tool_registry.py`

Pluggable tool registration and discovery:
```python
class ToolRegistry:
    def register_tool(self, tool_class: type) -> None
    def get_tool(self, name: str) -> Optional[BaseTool]
    def get_all_tools_for_claude(self) -> List[Dict[str, Any]]
    def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> ValidationResult
```

#### 1.3 Configuration Extensions
**File**: `src/code_indexer/config/config_schema.py`

```yaml
claude_api:
  api_key: "${CLAUDE_API_KEY}"
  model: "claude-3-sonnet-20240229"
  base_url: "https://api.anthropic.com"
  max_tokens: 4096
  temperature: 0.1
  tool_execution:
    max_parallel_tools: 10
    default_timeout_seconds: 30
    max_timeout_seconds: 120
  logging:
    tool_execution_logging: true
    tool_execution_log_path: ".code-indexer/tool_execution.log"
```

#### 1.4 Dependencies
Add to `pyproject.toml`:
```toml
anthropic = "^0.7.0"  # Official Anthropic Python SDK
tiktoken = "^0.5.0"   # Token counting for context management  
jsonschema = "^4.0.0" # Tool parameter validation
```

### Phase 2: Extensible Prompt Architecture

#### 2.1 Prompt Builder Framework
**File**: `src/code_indexer/services/prompt_builder/prompt_builder.py`

Create extensible prompt building system that adapts to different use cases:
```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from enum import Enum

class PromptContext(Enum):
    CLAUDE_CLI = "claude_cli"           # Using Claude CLI (existing behavior)
    CLAUDE_API_TOOLS = "claude_api_tools"  # Using Claude API with tools
    CLAUDE_API_BASIC = "claude_api_basic"  # Using Claude API without tools

class PromptBuilder(ABC):
    @abstractmethod
    def build_system_prompt(self, context: PromptContext, **kwargs) -> str: pass
    
    @abstractmethod
    def build_user_prompt(self, query: str, initial_context: List[CodeContext], **kwargs) -> str: pass

class ClaudeAPIPromptBuilder(PromptBuilder):
    def __init__(self, tool_registry: 'ToolRegistry'):
        self.tool_registry = tool_registry
    
    def build_system_prompt(self, context: PromptContext, **kwargs) -> str:
        if context == PromptContext.CLAUDE_API_TOOLS:
            return self._build_autonomous_engineer_prompt_with_tools()
        elif context == PromptContext.CLAUDE_API_BASIC:
            return self._build_autonomous_engineer_prompt_basic()
        else:
            return self._build_minimal_prompt()
    
    def _build_autonomous_engineer_prompt_with_tools(self) -> str:
        # Comprehensive software engineering persona + tool explanations
        pass
```

#### 2.2 Autonomous Software Engineer Persona
**File**: `src/code_indexer/services/prompt_builder/engineer_persona.py`

Define comprehensive software engineering persona for Claude API:
```python
class AutonomousSoftwareEngineerPersona:
    @staticmethod
    def get_core_identity() -> str:
        return """
You are an autonomous software engineer with deep expertise in code analysis, architecture design, and software engineering best practices. You approach every task with systematic thinking and proven methodologies.

CORE IDENTITY & CAPABILITIES:
- Expert software engineer with 15+ years of experience
- Specialist in code analysis, refactoring, and architecture design
- Proficient in multiple programming languages and frameworks
- Deep understanding of software engineering principles and patterns
- Experienced in leading complex software projects and mentoring teams

ANALYTICAL APPROACH:
- Apply systems thinking to understand complex codebases
- Break down problems into manageable, logical components
- Consider both immediate solutions and long-term architectural implications
- Analyze code quality, maintainability, and performance implications
- Identify patterns, anti-patterns, and improvement opportunities
"""

    @staticmethod
    def get_methodologies() -> str:
        return """
METHODOLOGIES & PRINCIPLES:

Domain-Driven Design (DDD):
- Identify and model core business domains
- Establish clear bounded contexts and domain boundaries
- Design aggregates, entities, and value objects appropriately
- Ensure domain logic is properly encapsulated
- Use ubiquitous language that reflects business concepts

Test-Driven Development (TDD):
- Write tests first to drive design decisions
- Follow Red-Green-Refactor cycle rigorously
- Ensure comprehensive test coverage for critical functionality
- Design testable, loosely coupled components
- Use tests as documentation and design validation

SOLID Principles:
- Single Responsibility: Each class/function has one reason to change
- Open/Closed: Open for extension, closed for modification
- Liskov Substitution: Subtypes must be substitutable for base types
- Interface Segregation: Clients shouldn't depend on unused interfaces
- Dependency Inversion: Depend on abstractions, not concretions

Core Principles:
- DRY (Don't Repeat Yourself): Eliminate code duplication through abstraction
- KISS (Keep It Simple, Stupid): Choose simplest solution that meets requirements
- YAGNI (You Aren't Gonna Need It): Don't build functionality until needed
- Favor composition over inheritance
- Program to interfaces, not implementations
"""

    @staticmethod
    def get_code_analysis_approach() -> str:
        return """
CODE ANALYSIS METHODOLOGY:

1. SYSTEMATIC EXPLORATION:
   - Start with high-level architecture overview
   - Identify key components, modules, and their relationships
   - Understand data flow and control flow patterns
   - Map dependencies and integration points

2. DEEP DIVE ANALYSIS:
   - Examine critical code paths and business logic
   - Analyze error handling and edge cases
   - Evaluate performance bottlenecks and optimization opportunities
   - Assess code quality, readability, and maintainability

3. PATTERN RECOGNITION:
   - Identify design patterns and architectural patterns in use
   - Spot anti-patterns and code smells
   - Recognize opportunities for refactoring and improvement
   - Understand coding conventions and style consistency

4. CONTEXTUAL UNDERSTANDING:
   - Consider business requirements and constraints
   - Understand deployment and operational context
   - Analyze testing strategies and coverage
   - Evaluate documentation and knowledge transfer needs
"""
```

#### 2.3 Tool-Aware Prompt Construction
**File**: `src/code_indexer/services/prompt_builder/tool_integration.py`

```python
class ToolAwarePromptBuilder:
    def __init__(self, tool_registry: 'ToolRegistry', engineer_persona: AutonomousSoftwareEngineerPersona):
        self.tool_registry = tool_registry
        self.engineer_persona = engineer_persona
    
    def build_complete_system_prompt(self, user_query: str, initial_context: List[CodeContext]) -> str:
        return f"""
{self.engineer_persona.get_core_identity()}

{self.engineer_persona.get_methodologies()}

{self.engineer_persona.get_code_analysis_approach()}

TOOL-ENHANCED CAPABILITIES:
You have access to a comprehensive set of specialized tools that enhance your analytical capabilities. These tools enable you to:

- Perform semantic searches across the entire codebase
- Navigate and understand complex code structures
- Analyze dependencies and relationships
- Extract contextual information efficiently
- Gather evidence to support your analysis and recommendations

TOOL USAGE PHILOSOPHY:
1. **Strategic Tool Selection**: Choose tools that provide the most relevant information for the task
2. **Systematic Exploration**: Use tools methodically to build comprehensive understanding
3. **Evidence-Based Analysis**: Base all conclusions on concrete evidence gathered through tools
4. **Efficient Information Gathering**: Use parallel tool execution when possible
5. **Comprehensive Coverage**: Ensure all relevant aspects are investigated

IMPORTANT: Always use tools to gather information before making conclusions. Your analysis should be evidence-based and well-documented with specific file locations and line numbers.

{self._generate_detailed_tool_descriptions()}

TOOL EXECUTION PROTOCOL:
{self._generate_tool_execution_guidelines()}

CURRENT ANALYSIS CONTEXT:
{self._format_initial_context(initial_context)}

USER REQUEST: {user_query}

Begin your systematic analysis using the available tools. Gather comprehensive evidence, then provide thorough analysis following software engineering best practices.
"""
    
    def _generate_detailed_tool_descriptions(self) -> str:
        tools = self.tool_registry.get_all_tools()
        description = ["AVAILABLE TOOLS:\n"]
        
        # Group tools by category for better organization
        categories = {}
        for tool in tools:
            cat = tool.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(tool)
        
        for category, cat_tools in categories.items():
            description.append(f"\n=== {category.upper()} TOOLS ===")
            description.append(f"Use these tools for {category}-related analysis:\n")
            
            for tool in cat_tools:
                description.append(f"**{tool.name}**")
                description.append(f"Purpose: {tool.description}")
                description.append(f"Best used for: {tool.get_usage_context()}")
                
                limits = tool.get_limits()
                description.append(f"Limits: {limits.max_execution_time_seconds}s timeout, max {limits.max_results or 'unlimited'} results")
                
                examples = tool.get_usage_examples()
                if examples:
                    description.append("Examples:")
                    for example in examples[:2]:  # Show top 2 examples
                        description.append(f"  - {example.get('description', 'Example usage')}")
                description.append("")
        
        return "\n".join(description)
    
    def _generate_tool_execution_guidelines(self) -> str:
        return """
1. **Unique ID Generation**: Create unique IDs for each tool call (e.g., "search_auth_001", "analyze_deps_002")
2. **Parallel Execution**: Use parallel execution when tools are independent 
3. **Timeout Management**: Specify appropriate timeouts based on tool complexity
4. **Error Handling**: If a tool fails, try alternative approaches or tools
5. **Result Integration**: Synthesize information from multiple tools for comprehensive analysis

JSON Tool Call Format:
```json
{
  "tool_calls": [
    {
      "id": "your_unique_id_001",
      "type": "function", 
      "function": {
        "name": "tool_name",
        "arguments": {
          "param1": "value1",
          "timeout_seconds": 30
        }
      }
    }
  ],
  "parallel_execution": true
}
```
"""
```

#### 2.4 Context-Specific Prompt Variants
**File**: `src/code_indexer/services/prompt_builder/prompt_variants.py`

```python
class PromptVariants:
    @staticmethod
    def get_architectural_analysis_prompt() -> str:
        """For high-level architecture analysis tasks"""
        return """
ARCHITECTURAL ANALYSIS FOCUS:
- Identify system boundaries and major components
- Analyze dependency relationships and coupling
- Evaluate separation of concerns and modularity
- Assess scalability and maintainability implications
- Recommend architectural improvements
"""
    
    @staticmethod
    def get_code_review_prompt() -> str:
        """For code review and quality assessment tasks"""
        return """
CODE REVIEW FOCUS:
- Evaluate code quality and adherence to best practices
- Identify potential bugs, security issues, and performance problems
- Assess test coverage and testing strategies
- Review error handling and edge case coverage
- Suggest specific improvements with examples
"""
    
    @staticmethod
    def get_refactoring_prompt() -> str:
        """For refactoring and improvement recommendations"""
        return """
REFACTORING FOCUS:
- Identify code smells and anti-patterns
- Propose specific refactoring strategies
- Ensure refactoring preserves existing functionality
- Recommend gradual, low-risk improvement approaches
- Consider impact on existing tests and dependencies
"""
    
    @staticmethod
    def get_troubleshooting_prompt() -> str:
        """For debugging and issue investigation"""
        return """
TROUBLESHOOTING FOCUS:
- Systematically investigate reported issues
- Trace execution paths and identify failure points
- Analyze error conditions and exception handling
- Examine recent changes and potential regression sources
- Provide specific, actionable debugging steps
"""
```

### Phase 3: Core Tool Implementation

#### 3.1 Search Tools
**File**: `src/code_indexer/services/claude_tools/search_tools.py`

```python
class SemanticSearchTool(BaseTool):
    name = "semantic_search"
    description = "Perform semantic search across the codebase using natural language queries"
    
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language search query"},
            "max_results": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
            "file_patterns": {"type": "array", "items": {"type": "string"}},
            "exclude_patterns": {"type": "array", "items": {"type": "string"}},
            "context_lines": {"type": "integer", "default": 15, "minimum": 5, "maximum": 100},
            "timeout_seconds": {"type": "integer", "default": 30, "minimum": 5, "maximum": 120}
        },
        "required": ["query"]
    }
    
    def get_limits(self) -> ToolLimits:
        return ToolLimits(
            max_execution_time_seconds=120,
            max_results=100,
            rate_limit_per_minute=30
        )

class FindDefinitionsTool(BaseTool):
    name = "find_definitions"
    description = "Find symbol definitions (functions, classes, variables) by name"
    
class FindUsagesTool(BaseTool):
    name = "find_usages" 
    description = "Find where a symbol is used in the codebase"

class FindReferencesTool(BaseTool):
    name = "find_references"
    description = "Find all references to a symbol across the codebase"

class SearchByPatternTool(BaseTool):
    name = "search_by_pattern"
    description = "Regex/pattern-based code search with advanced filtering"
```

#### 3.2 Context Tools
**File**: `src/code_indexer/services/claude_tools/context_tools.py`

```python
class GetFileContextTool(BaseTool):
    name = "get_file_context"
    description = "Get full context for specific files with optional line ranges"
    
class GetFunctionContextTool(BaseTool):
    name = "get_function_context"
    description = "Get complete function/method implementation with surrounding context"
    
class GetClassContextTool(BaseTool):
    name = "get_class_context"
    description = "Get complete class definition including all methods and properties"
    
class AnalyzeCodeStructureTool(BaseTool):
    name = "analyze_code_structure"
    description = "Analyze code structure (classes, functions, dependencies)"
    
class GetImportChainTool(BaseTool):
    name = "get_import_chain"
    description = "Analyze import dependencies and dependency chains"
```

#### 3.3 Navigation Tools
**File**: `src/code_indexer/services/claude_tools/navigation_tools.py`

```python
class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = "List files and directories with filtering options"
    
class FindFilesTool(BaseTool):
    name = "find_files"
    description = "Find files by name or pattern across the repository"
    
class GetFileTreeTool(BaseTool):
    name = "get_file_tree"
    description = "Get hierarchical file structure of directories"
```

#### 3.4 Git Tools
**File**: `src/code_indexer/services/claude_tools/git_tools.py`

```python
class GitCommandTool(BaseTool):
    name = "git_command"
    description = "Execute git commands with full repository access and control"
    category = "git"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Git command to execute (e.g., 'status', 'log --oneline -10', 'diff HEAD~1')"
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional command arguments as separate array items",
                    "default": []
                },
                "working_directory": {
                    "type": "string",
                    "description": "Working directory for git command (defaults to repository root)",
                    "default": "."
                },
                "timeout_seconds": {
                    "type": "integer",
                    "default": 30,
                    "minimum": 5,
                    "maximum": 120,
                    "description": "Command execution timeout"
                }
            },
            "required": ["command"]
        }
    
    def get_limits(self) -> ToolLimits:
        return ToolLimits(
            max_execution_time_seconds=120,
            rate_limit_per_minute=30,
            custom_limits={
                "allowed_commands": ["status", "log", "diff", "show", "branch", "remote", "config", "blame", "describe", "ls-files"],
                "restricted_commands": ["push", "pull", "fetch", "reset --hard", "rm", "clean"],
                "read_only_mode": True
            }
        )
    
    def get_usage_examples(self) -> List[Dict[str, Any]]:
        return [
            {
                "description": "Get repository status",
                "parameters": {"command": "status", "args": ["--porcelain"]}
            },
            {
                "description": "View recent commit history",
                "parameters": {"command": "log", "args": ["--oneline", "-10"]}
            },
            {
                "description": "Show changes in specific commit",
                "parameters": {"command": "show", "args": ["HEAD", "--stat"]}
            },
            {
                "description": "Compare with previous commit",
                "parameters": {"command": "diff", "args": ["HEAD~1", "HEAD"]}
            },
            {
                "description": "Show file blame information",
                "parameters": {"command": "blame", "args": ["src/main.py"]}
            },
            {
                "description": "List all tracked files",
                "parameters": {"command": "ls-files"}
            }
        ]
    
    async def execute(self, execution_id: str, parameters: Dict[str, Any], 
                     services: Dict[str, Any], timeout_seconds: Optional[int] = None) -> Dict[str, Any]:
        
        command = parameters['command']
        args = parameters.get('args', [])
        working_dir = parameters.get('working_directory', '.')
        actual_timeout = timeout_seconds or parameters.get('timeout_seconds', 30)
        
        # Security validation
        limits = self.get_limits()
        allowed_commands = limits.custom_limits.get('allowed_commands', [])
        restricted_commands = limits.custom_limits.get('restricted_commands', [])
        
        if command in restricted_commands:
            raise ToolExecutionError(f"Git command '{command}' is restricted for security")
        
        if allowed_commands and command not in allowed_commands:
            raise ToolExecutionError(f"Git command '{command}' is not in allowed list")
        
        try:
            # Build full git command
            full_command = ['git', command] + args
            
            # Execute with timeout
            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *full_command,
                    cwd=working_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    text=True
                ),
                timeout=actual_timeout
            )
            
            stdout, stderr = await result.communicate()
            
            return {
                "command": f"git {command} {' '.join(args)}",
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "success": result.returncode == 0,
                "working_directory": working_dir
            }
            
        except asyncio.TimeoutError:
            raise ToolExecutionTimeout(f"Git command exceeded {actual_timeout}s timeout")
        except Exception as e:
            raise ToolExecutionError(f"Git command failed: {str(e)}")
```

#### 3.5 Analysis Tools
**File**: `src/code_indexer/services/claude_tools/analysis_tools.py`

```python
class AnalyzeFunctionTool(BaseTool):
    name = "analyze_function"
    description = "Deep analysis of function behavior, complexity, and dependencies"
    
class TraceCallChainTool(BaseTool):
    name = "trace_call_chain"
    description = "Trace function call chains and execution paths"
    
class FindSimilarCodeTool(BaseTool):
    name = "find_similar_code"
    description = "Find similar code patterns and potential duplicates"
    
class GetCodeMetricsTool(BaseTool):
    name = "get_code_metrics"
    description = "Calculate code complexity and quality metrics"
```

#### 3.6 Tool Execution Engine
**File**: `src/code_indexer/services/claude_tools/execution_engine.py`

**Responsibilities**:
- Execute tool calls with unique ID tracking
- Parallel and sequential execution modes
- Timeout handling and error recovery
- Performance monitoring and statistics

```python
class ToolExecutionEngine:
    async def execute_tool_calls(self, tool_calls: List[Dict[str, Any]], parallel: bool = True) -> Dict[str, Any]
    async def _execute_single_tool(self, tool_call: Dict[str, Any]) -> ToolExecutionResult
    def _format_error_response(self, tool_call_id: str, exception: Exception) -> ToolExecutionResult
```

### Phase 3: Claude API Integration and System Prompts

#### 3.1 Enhanced Claude API Service
**File**: `src/code_indexer/services/claude_api_service.py`

```python
class ClaudeAPIService:
    def __init__(self, config: ClaudeAPIConfig, tool_executor: ToolExecutionEngine):
        self.config = config
        self.tool_executor = tool_executor
        self.tool_registry = tool_executor.registry
    
    async def send_message_with_tools(self, message: str, conversation_history: List[Dict]) -> AsyncIterator[str]
    def _build_system_prompt_with_tools(self, user_query: str, initial_context: List[CodeContext]) -> str
    def _generate_tools_description(self) -> str
    async def _handle_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]
```

#### 3.2 System Prompt with JSON Tools
**File**: `src/code_indexer/services/claude_api_prompts.py`

```markdown
You are a code analysis expert with access to powerful tools for exploring codebases.

TOOL USAGE PROTOCOL:
1. Generate unique IDs for each tool call (e.g., "search_001", "find_def_002") 
2. Use specific tools based on their capabilities and limitations
3. You can request parallel execution by calling multiple tools simultaneously
4. Specify timeout_seconds for each tool call if needed (within tool limits)
5. Tool calls return results with your provided ID for tracking

AVAILABLE TOOLS:
{detailed_tools_description}

TOOL CALL FORMAT:
```json
{
  "tool_calls": [
    {
      "id": "your_unique_id_001",
      "type": "function",
      "function": {
        "name": "tool_name",
        "arguments": {
          "param1": "value1",
          "timeout_seconds": 30
        }
      }
    }
  ],
  "parallel_execution": true
}
```

ERROR HANDLING:
- If a tool fails, you'll receive an error response with your ID
- Tool timeouts return "EXECUTION_TIMEOUT" error code
- You can retry with different parameters or try alternative approaches
- Use tool limits information to set appropriate expectations

CURRENT CONTEXT: {initial_context}
USER QUESTION: {user_query}

Use the available tools systematically to research this question, then provide a comprehensive answer with proper citations.
```

#### 3.3 JSON Tool Call Parser
**File**: `src/code_indexer/services/claude_tools/tool_call_parser.py`

```python
class ToolCallParser:
    def parse_tool_calls_from_response(self, response_text: str) -> List[Dict[str, Any]]
    def validate_tool_call_format(self, tool_call: Dict[str, Any]) -> ValidationResult
    def extract_parallel_execution_flag(self, response_text: str) -> bool
```

### Phase 4: CLI Integration

#### 4.1 Extend Existing Claude Command
**File**: `src/code_indexer/cli.py`

Add new options for JSON tool-based API mode:
```python
@click.option(
    "--use-api",
    is_flag=True,
    help="Use Claude API directly with JSON tools instead of Claude CLI"
)
@click.option(
    "--api-model",
    default="claude-3-sonnet-20240229",
    help="Claude API model to use (sonnet/haiku/opus)"
)
@click.option(
    "--max-parallel-tools",
    type=int,
    help="Maximum parallel tool executions (overrides config)"
)
@click.option(
    "--tool-timeout",
    type=int,
    help="Default tool execution timeout in seconds"
)
@click.option(
    "--json-output",
    is_flag=True,
    help="Stream output in JSON format for programmatic consumption"
)
@click.option(
    "--output-format",
    type=click.Choice(["interactive", "json", "json-lines"]),
    default="interactive",
    help="Output format: interactive (human), json (single object), json-lines (streaming)"
)
```

#### 4.2 Command Flow Integration
```python
if use_api:
    # Initialize JSON tool system
    tool_registry = ToolRegistry()
    tool_registry.discover_and_register_tools()
    
    tool_executor = ToolExecutionEngine(tool_registry, services)
    claude_api_service = ClaudeAPIService(config.claude_api, tool_executor)
    
    # Initialize output formatter based on format
    if output_format == "interactive":
        output_handler = InteractiveOutputHandler()
    elif output_format == "json":
        output_handler = JSONOutputHandler()
    elif output_format == "json-lines":
        output_handler = JSONLinesOutputHandler()
    
    # Execute with tool-based approach
    result = await claude_api_service.analyze_with_tools(
        query=question,
        initial_context=extracted_contexts,
        max_parallel_tools=max_parallel_tools,
        output_handler=output_handler
    )
else:
    # Use existing Claude CLI integration
    result = claude_service.run_analysis(...)
```

#### 4.3 JSON Output Handlers
**File**: `src/code_indexer/services/output_handlers.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncIterator

class OutputHandler(ABC):
    @abstractmethod
    async def handle_tool_execution_start(self, tool_calls: List[Dict[str, Any]]) -> None: pass
    
    @abstractmethod
    async def handle_tool_progress(self, tool_call_id: str, status: str, result: Dict[str, Any] = None) -> None: pass
    
    @abstractmethod
    async def handle_claude_response_chunk(self, chunk: str) -> None: pass
    
    @abstractmethod
    async def handle_session_complete(self, final_response: str, metadata: Dict[str, Any]) -> None: pass

class InteractiveOutputHandler(OutputHandler):
    """Traditional interactive output with Textual display"""
    async def handle_tool_execution_start(self, tool_calls: List[Dict[str, Any]]) -> None:
        # Show interactive progress display
        pass

class JSONOutputHandler(OutputHandler):
    """Single JSON object output (for batch processing)"""
    def __init__(self):
        self.session_data = {"events": [], "final_response": None}
    
    async def handle_session_complete(self, final_response: str, metadata: Dict[str, Any]) -> None:
        self.session_data["final_response"] = final_response
        self.session_data["metadata"] = metadata
        print(json.dumps(self.session_data, indent=2))

class JSONLinesOutputHandler(OutputHandler):
    """Streaming JSON Lines output (for web applications)"""
    async def handle_tool_execution_start(self, tool_calls: List[Dict[str, Any]]) -> None:
        event = {
            "type": "tool_execution_start",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"tool_calls": tool_calls}
        }
        print(json.dumps(event))
        
    async def handle_tool_progress(self, tool_call_id: str, status: str, result: Dict[str, Any] = None) -> None:
        event = {
            "type": "tool_progress",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "tool_call_id": tool_call_id,
                "status": status,
                "result": result
            }
        }
        print(json.dumps(event))
        
    async def handle_claude_response_chunk(self, chunk: str) -> None:
        event = {
            "type": "claude_response_chunk",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"chunk": chunk}
        }
        print(json.dumps(event))
```

#### 4.4 Activity Display Integration
**File**: `src/code_indexer/services/activity_display_service.py`

Enhanced activity display supporting multiple output formats:
```python
class ToolActivityDisplayService:
    def __init__(self, output_handler: OutputHandler):
        self.output_handler = output_handler
    
    async def show_tool_execution_start(self, tool_calls: List[Dict[str, Any]]) -> None:
        await self.output_handler.handle_tool_execution_start(tool_calls)
    
    async def show_tool_progress(self, tool_call_id: str, tool_name: str, status: str, result: Dict[str, Any] = None) -> None:
        await self.output_handler.handle_tool_progress(tool_call_id, status, result)
    
    async def show_claude_response_chunk(self, chunk: str) -> None:
        await self.output_handler.handle_claude_response_chunk(chunk)
```

### Phase 5: JSON Streaming Output Specifications

#### 5.1 Output Format Types

**Interactive Mode** (default):
- Traditional Textual-based display
- Real-time progress indicators
- Human-readable formatting
- Suitable for terminal usage

**JSON Mode** (`--output-format json`):
- Single JSON object output
- Complete session data in one response
- Suitable for batch processing
- All events collected and output at end

**JSON Lines Mode** (`--output-format json-lines`):
- Streaming newline-delimited JSON
- Real-time event streaming
- Perfect for web application integration
- Each line is a complete JSON event

#### 5.2 JSON Lines Event Types

**Tool Execution Start Event**:
```json
{
  "type": "tool_execution_start",
  "timestamp": "2024-01-01T12:00:00Z",
  "data": {
    "tool_calls": [
      {
        "id": "search_001",
        "tool_name": "semantic_search",
        "parameters": {"query": "authentication", "max_results": 10}
      }
    ],
    "parallel_execution": true,
    "estimated_duration_seconds": 30
  }
}
```

**Tool Progress Event**:
```json
{
  "type": "tool_progress",
  "timestamp": "2024-01-01T12:00:01Z", 
  "data": {
    "tool_call_id": "search_001",
    "status": "executing",
    "progress_percentage": 45,
    "message": "Processing semantic search..."
  }
}
```

**Tool Completion Event**:
```json
{
  "type": "tool_completion",
  "timestamp": "2024-01-01T12:00:05Z",
  "data": {
    "tool_call_id": "search_001", 
    "status": "success",
    "execution_time_ms": 4500,
    "result": {
      "matches": [
        {
          "file_path": "src/auth.py",
          "line_start": 45,
          "line_end": 67,
          "relevance_score": 0.92,
          "context": "def authenticate_user..."
        }
      ],
      "total_matches": 12
    }
  }
}
```

**Claude Response Chunk Event**:
```json
{
  "type": "claude_response_chunk",
  "timestamp": "2024-01-01T12:00:06Z",
  "data": {
    "chunk": "Based on the search results, I can see that authentication is handled in the",
    "chunk_index": 0,
    "is_final": false
  }
}
```

**Session Complete Event**:
```json
{
  "type": "session_complete",
  "timestamp": "2024-01-01T12:00:30Z",
  "data": {
    "final_response": "Complete analysis response text...",
    "metadata": {
      "total_execution_time_ms": 30000,
      "tools_executed": 3,
      "tools_successful": 3,
      "tools_failed": 0,
      "total_api_calls": 2,
      "total_tokens_used": 15000
    }
  }
}
```

**Error Event**:
```json
{
  "type": "error",
  "timestamp": "2024-01-01T12:00:10Z",
  "data": {
    "tool_call_id": "search_002",
    "error_code": "EXECUTION_TIMEOUT",
    "error_message": "Tool execution exceeded 30 second timeout",
    "error_details": {
      "requested_timeout": 30,
      "actual_execution_time": 30.001
    },
    "recoverable": true
  }
}
```

#### 5.3 Web Application Integration

**Usage Example**:
```bash
# Stream JSON output for web application
code-indexer claude "How does authentication work?" --use-api --output-format json-lines

# Each line output can be parsed by web backend:
{"type": "tool_execution_start", "timestamp": "...", "data": {...}}
{"type": "tool_progress", "timestamp": "...", "data": {...}}
{"type": "claude_response_chunk", "timestamp": "...", "data": {...}}
{"type": "session_complete", "timestamp": "...", "data": {...}}
```

**Web Backend Integration**:
```python
# Example web backend processing
import subprocess
import json

def stream_analysis(query: str):
    process = subprocess.Popen([
        'code-indexer', 'claude', query,
        '--use-api', '--output-format', 'json-lines'
    ], stdout=subprocess.PIPE, text=True)
    
    for line in process.stdout:
        event = json.loads(line.strip())
        yield f"data: {json.dumps(event)}\n\n"  # Server-Sent Events format
```

### Phase 6: JSON Tool Protocol Specifications

#### 6.1 Tool Call Request Format

**Claude Request Structure**:
```json
{
  "tool_calls": [
    {
      "id": "search_auth_001",
      "type": "function",
      "function": {
        "name": "semantic_search",
        "arguments": {
          "query": "authentication mechanisms",
          "max_results": 15,
          "timeout_seconds": 45,
          "file_patterns": ["*.py"]
        }
      }
    },
    {
      "id": "find_def_002", 
      "type": "function",
      "function": {
        "name": "find_definitions",
        "arguments": {
          "symbol": "authenticate_user",
          "timeout_seconds": 30
        }
      }
    }
  ],
  "parallel_execution": true
}
```

#### 6.2 Tool Response Format

**Structured Response with ID Tracking**:
```json
{
  "tool_responses": [
    {
      "tool_call_id": "search_auth_001",
      "execution_time_ms": 1234,
      "status": "success",
      "result": {
        "matches": [
          {
            "file_path": "src/auth/handlers.py",
            "line_start": 45,
            "line_end": 67,
            "relevance_score": 0.92,
            "context": "def authenticate_user(username, password):\\n    # Implementation..."
          }
        ],
        "total_matches": 12,
        "truncated": false
      }
    },
    {
      "tool_call_id": "find_def_002",
      "execution_time_ms": 30001,
      "status": "timeout",
      "error": {
        "code": "EXECUTION_TIMEOUT",
        "message": "Tool execution exceeded 30 second timeout",
        "requested_timeout": 30,
        "actual_execution_time": 30.001
      }
    }
  ],
  "execution_summary": {
    "total_tools_called": 2,
    "successful": 1,
    "failed": 1,
    "parallel_execution_time_ms": 30001
  }
}
```

#### 6.3 Error Code Specifications

**Standard Error Codes**:
- `EXECUTION_TIMEOUT`: Tool exceeded timeout limit
- `INVALID_PARAMETERS`: Parameter validation failed
- `TOOL_NOT_FOUND`: Requested tool doesn't exist
- `RATE_LIMIT_EXCEEDED`: Tool rate limit hit
- `SEARCH_SERVICE_ERROR`: Underlying search service failed
- `FILE_ACCESS_ERROR`: File reading/access failed
- `MEMORY_LIMIT_EXCEEDED`: Tool exceeded memory constraints

#### 6.4 Performance Monitoring

**Tool Execution Logging**:
```json
{
  "session_id": "uuid",
  "timestamp": "2024-01-01T12:00:00Z",
  "user_query": "How does authentication work?",
  "tool_executions": [
    {
      "tool_call_id": "search_auth_001",
      "tool_name": "semantic_search",
      "parameters": {"query": "authentication", "max_results": 15},
      "execution_time_ms": 1234,
      "status": "success",
      "result_size_bytes": 8192,
      "matches_returned": 12
    }
  ],
  "parallel_batches": [
    {
      "batch_id": 1,
      "tool_calls": ["search_auth_001", "find_def_002"],
      "parallel_execution_time_ms": 1250,
      "successful_tools": 1,
      "failed_tools": 1
    }
  ],
  "total_execution_time_ms": 2500,
  "total_api_calls": 2
}
```

### Phase 7: Testing Strategy

#### 7.1 Unit Tests

**Test Files**:
- `tests/test_claude_tools/test_base_tool.py`
- `tests/test_claude_tools/test_tool_registry.py`
- `tests/test_claude_tools/test_execution_engine.py`
- `tests/test_claude_tools/test_search_tools.py`
- `tests/test_claude_api_service.py`
- `tests/test_tool_call_parser.py`

**Key Test Cases**:
```python
class TestToolExecutionEngine:
    def test_execute_single_tool_success()
    def test_execute_single_tool_timeout()
    def test_execute_single_tool_error()
    def test_parallel_tool_execution()
    def test_sequential_tool_execution()
    def test_unique_id_tracking()
    
class TestToolRegistry:
    def test_tool_registration()
    def test_tool_discovery()
    def test_parameter_validation()
    def test_get_tools_for_claude()
    
class TestSearchTools:
    def test_semantic_search_tool_execution()
    def test_find_definitions_tool_execution()
    def test_tool_limits_enforcement()
    def test_timeout_handling()
```

#### 7.2 Integration Tests

**Test Files**:
- `tests/test_claude_api_tools_e2e.py`
- `tests/test_tool_workflow.py`

**Mock Tool Call Responses**:
```python
MOCK_TOOL_CALLS = [
    {
        "input": {
            "tool_calls": [
                {
                    "id": "search_001",
                    "type": "function",
                    "function": {
                        "name": "semantic_search",
                        "arguments": {"query": "authentication", "max_results": 5}
                    }
                }
            ]
        },
        "expected_response": {
            "tool_responses": [
                {
                    "tool_call_id": "search_001",
                    "status": "success",
                    "result": {"matches": [], "total_matches": 0}
                }
            ]
        }
    }
]
```

#### 7.3 JSON Output Testing

**Test Files**:
- `tests/test_output_handlers.py`
- `tests/test_json_streaming.py`

**Key Test Cases**:
```python
class TestJSONOutputHandlers:
    def test_interactive_output_handler()
    def test_json_output_handler_complete_session()
    def test_json_lines_streaming_events()
    def test_event_ordering_and_timestamps()
    def test_error_event_formatting()
    
class TestJSONStreamingIntegration:
    def test_json_lines_tool_execution_flow()
    def test_claude_response_chunk_streaming()
    def test_session_complete_metadata()
    def test_web_application_integration()
```

#### 7.4 E2E Tests

**Real API Testing** (when API key available):
- Complete tool-based analysis workflows
- Parallel tool execution validation
- JSON streaming output validation
- Error recovery scenarios
- Performance benchmarking
- Web application integration testing

## Comprehensive Implementation Task List (TDD + DDD)

### Phase 1: Domain Architecture & Testing Foundation (Week 1)

#### 1.1 Domain Model Design (TDD: Red Phase)
1. **Define Core Domain Models**
   - [ ] Design `AnalysisMode` enum (CLI vs API)
   - [ ] Design `ToolLimits` domain object with validation rules
   - [ ] Design `ToolExecutionResult` aggregate
   - [ ] Create domain exceptions (`ToolExecutionError`, `ToolNotFoundError`, `ToolValidationError`)
   - [ ] Write unit tests for domain models (should fail initially)

2. **Tool Domain Interface (TDD: Red Phase)**
   - [ ] Write failing tests for `BaseTool` interface contract
   - [ ] Define `BaseTool` abstract class with method signatures only
   - [ ] Write failing tests for `ToolRegistry` behavior
   - [ ] Create empty `ToolRegistry` class structure
   - [ ] Write failing tests for tool parameter validation
   - [ ] Write failing tests for tool limits enforcement

#### 1.2 Shared Services Architecture (DDD: Bounded Context)
3. **Semantic Search Service Refactoring (TDD: Red → Green)**
   - [ ] Write failing tests for `SemanticSearchService.semantic_search()`
   - [ ] Extract existing query logic from `cli.py` into `SemanticSearchService`
   - [ ] Implement `SemanticSearchService.semantic_search()` to pass tests
   - [ ] Write failing tests for `search_with_context_expansion()`
   - [ ] Implement context expansion method
   - [ ] Refactor existing CLI to use new service (Green phase)

4. **Context Extraction Service Wrapper (TDD: Red → Green)**
   - [ ] Write failing tests for `ContextExtractionService` wrapper
   - [ ] Create wrapper around existing `RAGContextExtractor`
   - [ ] Add new methods: `extract_file_context()`, `extract_function_context()`
   - [ ] Write tests for new functionality
   - [ ] Implement new methods to pass tests

#### 1.3 Prompt Architecture (TDD: Red → Green)
5. **Prompt Builder Framework**
   - [ ] Write failing tests for `PromptBuilder` interface
   - [ ] Write failing tests for `AutonomousSoftwareEngineerPersona`
   - [ ] Implement prompt building classes to pass tests
   - [ ] Write failing tests for context-specific prompt variants
   - [ ] Implement prompt variants (architectural, code review, etc.)

### Phase 2: Tool Implementation (Week 2)

#### 2.1 Core Search Tools (TDD: Red → Green → Refactor)
6. **Semantic Search Tool**
   - [ ] Write failing tests for `SemanticSearchTool.execute()`
   - [ ] Write failing tests for parameter validation
   - [ ] Write failing tests for timeout handling
   - [ ] Implement `SemanticSearchTool` to pass all tests
   - [ ] Refactor to improve code quality

7. **Definition & Usage Tools**
   - [ ] Write failing tests for `FindDefinitionsTool.execute()`
   - [ ] Write failing tests for `FindUsagesTool.execute()`
   - [ ] Write failing tests for `FindReferencesTool.execute()`
   - [ ] Implement tools to pass tests
   - [ ] Refactor shared functionality

#### 2.2 Context & Navigation Tools (TDD: Red → Green → Refactor)
8. **Context Tools**
   - [ ] Write failing tests for `GetFileContextTool.execute()`
   - [ ] Write failing tests for `GetFunctionContextTool.execute()`
   - [ ] Write failing tests for `GetClassContextTool.execute()`
   - [ ] Implement context tools to pass tests
   - [ ] Refactor to eliminate duplication

9. **Navigation Tools**
   - [ ] Write failing tests for `ListDirectoryTool.execute()`
   - [ ] Write failing tests for `FindFilesTool.execute()`
   - [ ] Implement navigation tools to pass tests

#### 2.3 Git Tools (TDD: Red → Green → Refactor)
10. **Git Command Tool**
    - [ ] Write failing tests for `GitCommandTool.execute()`
    - [ ] Write failing tests for security validation
    - [ ] Write failing tests for command restrictions
    - [ ] Implement `GitCommandTool` with security to pass tests
    - [ ] Write failing tests for timeout handling
    - [ ] Implement timeout functionality

### Phase 3: Tool Execution Engine (Week 2-3)

#### 3.1 Tool Execution Framework (TDD: Red → Green → Refactor)
11. **Tool Registry**
    - [ ] Write failing tests for tool registration
    - [ ] Write failing tests for tool discovery
    - [ ] Implement `ToolRegistry.register_tool()` to pass tests
    - [ ] Write failing tests for `get_all_tools_for_claude()`
    - [ ] Implement Claude API tool definitions

12. **Tool Execution Engine**
    - [ ] Write failing tests for `execute_tool_calls()` with unique IDs
    - [ ] Write failing tests for parallel execution
    - [ ] Write failing tests for sequential execution
    - [ ] Implement basic execution engine to pass tests
    - [ ] Write failing tests for error handling and recovery
    - [ ] Implement error handling to pass tests

#### 3.2 Claude API Integration (TDD: Red → Green)
13. **Enhanced Claude API Service**
    - [ ] Write failing tests for `ClaudeAPIService` with tool integration
    - [ ] Write failing tests for tool call parsing
    - [ ] Write failing tests for tool response formatting
    - [ ] Implement `ClaudeAPIService` to pass tests
    - [ ] Write failing tests for streaming with tools
    - [ ] Implement streaming functionality

### Phase 4: Output Handling & CLI Integration (Week 3)

#### 4.1 Output Handlers (TDD: Red → Green → Refactor)
14. **Output Handler Framework**
    - [ ] Write failing tests for `OutputHandler` interface
    - [ ] Write failing tests for `InteractiveOutputHandler`
    - [ ] Write failing tests for `JSONOutputHandler`
    - [ ] Write failing tests for `JSONLinesOutputHandler`
    - [ ] Implement all output handlers to pass tests

15. **JSON Streaming Events**
    - [ ] Write failing tests for tool execution events
    - [ ] Write failing tests for Claude response chunk events
    - [ ] Write failing tests for session complete events
    - [ ] Implement event system to pass tests

#### 4.2 CLI Integration (TDD: Red → Green)
16. **Command Line Interface**
    - [ ] Write failing tests for `--use-api` flag
    - [ ] Write failing tests for `--output-format` flag
    - [ ] Write failing tests for `--max-parallel-tools` flag
    - [ ] Implement CLI integration to pass tests
    - [ ] Write failing tests for backward compatibility
    - [ ] Ensure existing functionality still works

### Phase 5: Integration & End-to-End Testing (Week 3-4)

#### 5.1 Analysis Engine Integration (TDD: Red → Green → Refactor)
17. **Code Analysis Engine**
    - [ ] Write failing tests for `CodeAnalysisEngine.analyze_code_question()`
    - [ ] Write failing tests for mode switching (CLI vs API)
    - [ ] Implement unified analysis engine to pass tests
    - [ ] Write failing tests for error recovery
    - [ ] Implement robust error handling

#### 5.2 End-to-End Testing (TDD: Red → Green)
18. **E2E Workflow Tests**
    - [ ] Write failing E2E test for complete API workflow
    - [ ] Write failing E2E test for JSON streaming output
    - [ ] Write failing E2E test for parallel tool execution
    - [ ] Implement functionality to pass E2E tests
    - [ ] Write failing tests for web application integration
    - [ ] Implement web integration features

### Phase 6: Performance & Production Readiness (Week 4)

#### 6.1 Performance Optimization (Test-Driven)
19. **Performance Testing**
    - [ ] Write performance tests for 5M line codebase simulation
    - [ ] Write tests for parallel tool execution efficiency
    - [ ] Write tests for memory usage under load
    - [ ] Optimize to meet performance requirements
    - [ ] Write tests for tool execution concurrency limits

20. **Production Hardening**
    - [ ] Write failing tests for edge cases and error scenarios
    - [ ] Write failing tests for resource exhaustion scenarios
    - [ ] Implement robust error handling to pass tests
    - [ ] Write failing tests for security edge cases
    - [ ] Implement security hardening

#### 6.2 Documentation & Migration (DDD: Ubiquitous Language)
21. **Documentation & Examples**
    - [ ] Document domain model and bounded contexts
    - [ ] Create tool usage examples and best practices
    - [ ] Create migration guide from CLI to API mode
    - [ ] Document JSON streaming integration for web apps
    - [ ] Create troubleshooting guide

### Critical TDD/DDD Principles Applied:

**Test-Driven Development:**
- Every feature starts with failing tests
- Red → Green → Refactor cycle for each component
- Unit tests for domain models
- Integration tests for service interactions
- E2E tests for complete workflows

**Domain-Driven Design:**
- Clear bounded contexts (Tools, Analysis, Output, CLI)
- Rich domain models with behavior
- Domain services for complex operations
- Aggregates for consistency boundaries
- Domain events for loose coupling

**Chronological Dependencies:**
1. Domain models must be defined before services
2. Shared services before tool implementations
3. Tool implementations before execution engine
4. Execution engine before API integration
5. API integration before CLI integration
6. CLI integration before E2E testing

### Phase 9: Backward Compatibility and Migration

#### 9.1 Backward Compatibility
- Existing `claude` command behavior unchanged by default
- `--use-api` is opt-in feature
- All existing options work with both modes
- Graceful fallback if API key unavailable
- Existing configuration files remain valid

#### 9.2 Configuration Migration
```python
def migrate_config_for_tool_support(config: dict) -> dict:
    """Add tool configuration section if missing."""
    if 'claude_api' not in config:
        config['claude_api'] = {
            'api_key': '${CLAUDE_API_KEY}',
            'model': 'claude-3-sonnet-20240229',
            'tool_execution': {
                'max_parallel_tools': 10,
                'default_timeout_seconds': 30
            }
        }
    return config
```

#### 9.3 Feature Comparison Matrix

| Feature | CLI Mode | JSON Tool API Mode |
|---------|----------|-------------------|
| Streaming Output | ✅ | ✅ |
| Tool Activity Display | ✅ | ✅ (Enhanced) |
| Context Extraction | ✅ | ✅ |
| Quiet Mode | ✅ | ✅ |
| Dry Run | ✅ | ✅ |
| Text-based Exploration | ✅ | ❌ |
| JSON Tool Calls | ❌ | ✅ |
| Parallel Tool Execution | ❌ | ✅ |
| Unique ID Tracking | ❌ | ✅ |
| Configurable Timeouts | ❌ | ✅ |
| Tool Limits Awareness | ❌ | ✅ |
| JSON Streaming Output | ❌ | ✅ |
| Web Application Ready | ❌ | ✅ |
| Machine-Readable Events | ❌ | ✅ |

## Security Considerations

### API Key Management
1. **Environment Variables**: Primary method for API key storage
2. **Runtime Validation**: Verify key validity before requests
3. **No Logging**: Never log API keys in debug output
4. **Secure Defaults**: API key required, no hardcoded defaults

### Data Privacy
1. **Local Processing**: All semantic search and context extraction remains local
2. **Minimal API Exposure**: Only send necessary context to API
3. **No Persistent Caching**: Don't cache API responses containing code
4. **Audit Logging**: Optional tool execution logging (parameters only, no code content)

### Tool Security
1. **Parameter Validation**: JSON schema validation for all tool inputs
2. **Execution Limits**: Timeout and resource constraints per tool
3. **Rate Limiting**: Tool-level rate limiting to prevent abuse
4. **Sandboxed Execution**: Tools operate within defined boundaries

## Error Handling Strategy

### API Errors
- **Rate Limiting**: Exponential backoff with user notification
- **Network Issues**: Retry with progressive delays
- **Invalid API Key**: Clear error message with setup instructions
- **Token Limits**: Context optimization and graceful degradation

### Tool Execution Errors
- **Timeout Handling**: Clear timeout error reporting with unique IDs
- **Parameter Validation**: Detailed validation error messages
- **Search Failures**: Individual tool failures don't stop other tools
- **Resource Limits**: Memory/CPU limit violations handled gracefully

### Recovery Mechanisms
- **Unique ID Tracking**: Failed tools can be retried with same ID
- **Parallel Fallback**: Failed parallel execution falls back to sequential
- **Tool Substitution**: Claude can try alternative tools on failure
- **Clear Error Messages**: Structured error responses with actionable details

## Performance Considerations

### Optimization Targets
- **Tool Execution Time**: < 30 seconds per tool (configurable)
- **Parallel Execution**: 5-10 concurrent tools by default
- **API Response Time**: Depends on Claude API (1-10 seconds)
- **Memory Usage**: < 100MB additional per tool execution

### Scalability Factors
- **Parallel Tool Limits**: Configurable max parallel executions
- **Tool Resource Management**: Memory and CPU monitoring per tool
- **Result Size Limits**: Maximum result sizes to prevent memory issues
- **Stateless Design**: No session state enables horizontal scaling

## Success Criteria

### Functional Requirements
✅ **Extensible Prompt Architecture**: Context-aware prompt building for different use cases
✅ **Autonomous Engineer Persona**: Comprehensive software engineering identity with DDD, TDD, SOLID principles
✅ **Tool-Aware Prompts**: Intelligent integration of tool descriptions and usage guidelines
✅ **JSON Tool Calls**: Claude can make structured, parseable tool requests
✅ **Unique ID Tracking**: Every tool execution tracked with Claude-provided IDs
✅ **Parallel Execution**: Multiple tools execute concurrently for performance
✅ **Error Recovery**: Tool failures are reported and Claude can retry/adapt
✅ **Configurable Timeouts**: Tools support custom timeout specifications
✅ **Tool Limits Exposure**: Tools communicate their capabilities to Claude
✅ **JSON Streaming Output**: Machine-readable streaming for web integration
✅ **Backward Compatibility**: Existing CLI mode remains unchanged

### Quality Requirements
✅ **Performance**: Tool executions complete within specified timeouts
✅ **Reliability**: Robust error handling with clear error codes
✅ **Security**: Safe tool parameter validation and execution limits
✅ **Usability**: Enhanced activity display for tool execution progress
✅ **Maintainability**: Pluggable tool architecture following DDD principles

### User Experience
✅ **Transparency**: Users see real-time tool execution progress
✅ **Control**: Users can configure tool limits and timeouts
✅ **Efficiency**: Parallel tool execution provides faster results
✅ **Quality**: Structured tool responses enable precise code analysis
✅ **Web Integration**: JSON streaming enables seamless web application integration

## API Key Storage

The API key should be stored as an environment variable:
```bash
export CLAUDE_API_KEY="your-actual-api-key-here"
```

And referenced in config as:
```yaml
claude_api:
  api_key: "${CLAUDE_API_KEY}"
```

## Next Steps

1. **Environment Setup**: Configure API key and dependencies
2. **Start Implementation**: Begin with Phase 1 (Base Tool Architecture)
3. **TDD Approach**: Write tests first for each tool and component
4. **Incremental Development**: Build and test each phase systematically
5. **Real-world Testing**: Test with actual codebase scenarios

---

This comprehensive plan provides a structured roadmap for implementing JSON tool-based Claude API integration with unique ID tracking, parallel execution, and pluggable tool architecture while maintaining full backward compatibility with the existing system.