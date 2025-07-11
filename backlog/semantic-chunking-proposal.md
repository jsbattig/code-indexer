# Semantic Chunking Proposal

## Current State Analysis

### Existing Metadata Schema
The current metadata schema (v3.0 - BRANCH_TOPOLOGY) includes:
- **Core fields**: path, content, language, file_size, chunk_index, total_chunks, indexed_at, project_id, file_hash
- **Line tracking**: line_start, line_end 
- **Git awareness**: git_commit_hash, git_branch, git_blob_hash, git_merge_base, branch_ancestry
- **Working directory**: working_directory_status, file_change_type, staged_at

### Current Query Display
**Quiet Mode**: `0.85 authentication.py:6-26`
**Verbose Mode**: Shows file path, language, score, git info, and content with line numbers

## Proposed Semantic Extensions

### 1. New Metadata Fields

Add these semantic fields to the metadata schema:

```python
# Semantic chunking fields (optional, when semantic_chunking=True)
SEMANTIC_FIELDS = {
    "semantic_chunking",      # Boolean: whether this chunk uses semantic chunking
    "semantic_type",          # String: "function", "class", "method", "interface", "struct", etc.
    "semantic_name",          # String: name of the semantic unit (e.g., "authenticate", "UserService")
    "semantic_signature",     # String: function/method signature (e.g., "def authenticate(username: str) -> bool")
    "semantic_path",          # String: full path (e.g., "UserService.authenticate", "utils.hash_password")
    "semantic_parent",        # String: parent context (e.g., "class UserService", "namespace auth")
    "semantic_context",       # Dict: additional context (decorators, imports, etc.)
    "semantic_scope",         # String: "global", "class", "function", "module"
    "semantic_language_features", # List: language-specific features (e.g., ["async", "static", "private"])
}
```

### 2. Enhanced Query Display with Semantic Information

#### **Quiet Mode with Semantic Info**
```bash
# Current
0.85 authentication.py:6-26

# Enhanced  
0.85 authentication.py:6-26 [UserService.authenticate]
0.92 user_service.py:45-67 [UserService.validate_email]
0.88 auth_utils.py:12-34 [hash_password]
```

#### **Verbose Mode with Semantic Context**
```bash
# Current
📄 File: authentication.py:6-26 | 🏷️ Language: python | 📊 Score: 0.856

# Enhanced
📄 File: authentication.py:6-26 | 🏷️ Language: python | 📊 Score: 0.856
🔧 Semantic: UserService.authenticate (method) | 📝 Signature: def authenticate(self, username: str, password: str) -> bool

📏 Size: 1234 bytes | 🕒 Indexed: 2024-01-01T00:00:00Z
🔧 Project: my-project | 📝 Git: master (abcd1234)
🏗️ Context: class UserService(BaseService) | 🎯 Scope: class

📖 Content (Lines 6-26):
──────────────────────────────────────────────────
  6: @validate_input
  7: def authenticate(self, username: str, password: str) -> bool:
  8:     """
  9:     Authenticate user credentials against the database.
 10:     ...
```

### 3. Semantic Query Features

#### **Semantic Path Queries**
```bash
# Find specific method
cidx query "UserService.authenticate"

# Find all methods in a class
cidx query "UserService.*"

# Find all functions with specific name
cidx query "*.authenticate"

# Find by semantic type
cidx query --semantic-type method --query "password"
cidx query --semantic-type class --query "User"
```

#### **Enhanced Filtering**
```bash
# Find async functions
cidx query --semantic-features async --query "database"

# Find private methods
cidx query --semantic-features private --query "validation"

# Find constructors/initializers
cidx query --semantic-type constructor
```

## Implementation Plan

### Phase 1: Infrastructure (Story 1)
Create new AST-based chunking system:

```python
# New chunker class
class SemanticChunker:
    def __init__(self, config: IndexingConfig):
        self.config = config
        self.text_chunker = TextChunker(config)  # Fallback
        self.parsers = {
            'python': PythonSemanticParser(),
            'javascript': JavaScriptSemanticParser(),
            'typescript': TypeScriptSemanticParser(),
            'java': JavaSemanticParser(),
            'go': GoSemanticParser(),
        }
    
    def chunk_file(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Chunk file using AST or fallback to text chunking."""
        language = self._detect_language(file_path)
        
        if language in self.parsers and self.config.use_semantic_chunking:
            try:
                return self.parsers[language].chunk(content, file_path)
            except Exception as e:
                # Fallback to text chunking on AST parsing errors
                return self.text_chunker.chunk_file(content, file_path)
        
        return self.text_chunker.chunk_file(content, file_path)
```

### Phase 2: Language Parsers (Stories 2-6)
Create AST parsers for each language:

```python
class PythonSemanticParser:
    def chunk(self, content: str, file_path: str) -> List[SemanticChunk]:
        """Parse Python AST and create semantic chunks."""
        import ast
        
        try:
            tree = ast.parse(content)
            chunks = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    chunks.append(self._create_function_chunk(node, content))
                elif isinstance(node, ast.ClassDef):
                    chunks.append(self._create_class_chunk(node, content))
                elif isinstance(node, ast.AsyncFunctionDef):
                    chunks.append(self._create_async_function_chunk(node, content))
            
            return chunks
        except SyntaxError:
            # Return empty list to trigger fallback
            return []
    
    def _create_function_chunk(self, node: ast.FunctionDef, content: str) -> SemanticChunk:
        """Create semantic chunk for Python function."""
        lines = content.split('\n')
        start_line = node.lineno
        end_line = node.end_lineno or start_line
        
        # Extract function signature
        signature = self._extract_function_signature(node)
        
        # Get decorators
        decorators = [ast.get_source_segment(content, d) for d in node.decorator_list]
        
        return SemanticChunk(
            content='\n'.join(lines[start_line-1:end_line]),
            line_start=start_line,
            line_end=end_line,
            semantic_type='function',
            semantic_name=node.name,
            semantic_signature=signature,
            semantic_path=node.name,  # Will be enhanced with class context
            semantic_parent=None,     # Will be set if inside class
            semantic_context={
                'decorators': decorators,
                'is_async': False,
                'is_private': node.name.startswith('_'),
            },
            semantic_scope='global',
            semantic_language_features=['async'] if isinstance(node, ast.AsyncFunctionDef) else []
        )
```

### Phase 3: Metadata Schema Update (Story 7)
Extend the metadata schema to include semantic fields:

```python
# Add to GitAwareMetadataSchema
SEMANTIC_FIELDS = {
    "semantic_chunking",      # Boolean
    "semantic_type",          # String
    "semantic_name",          # String
    "semantic_signature",     # String
    "semantic_path",          # String
    "semantic_parent",        # String
    "semantic_context",       # Dict
    "semantic_scope",         # String
    "semantic_language_features", # List
}

# Update ALL_FIELDS
ALL_FIELDS = (
    REQUIRED_FIELDS
    | GIT_FIELDS
    | WORKING_DIR_FIELDS
    | FILESYSTEM_FIELDS
    | LINE_NUMBER_FIELDS
    | SEMANTIC_FIELDS
)
```

### Phase 4: Query Enhancement (Story 8)
Enhance query command to support semantic queries:

```python
# Enhanced query command
@click.command()
@click.argument('query', required=True)
@click.option('--semantic-path', help='Search by semantic path (e.g., "UserService.authenticate")')
@click.option('--semantic-type', type=click.Choice(['function', 'class', 'method', 'interface']))
@click.option('--semantic-features', multiple=True, help='Filter by language features (async, private, etc.)')
@click.option('--show-signature', is_flag=True, help='Show function/method signatures')
def query(query, semantic_path, semantic_type, semantic_features, show_signature):
    """Enhanced query with semantic search capabilities."""
    # Implementation handles semantic filtering
    pass
```

### Phase 5: Display Enhancement (Story 9)
Update result display to show semantic information:

```python
def format_semantic_result(result: dict, quiet: bool = False) -> str:
    """Format search result with semantic information."""
    if quiet:
        # Enhanced quiet mode: score file:lines [semantic_path]
        semantic_info = ""
        if result.get('semantic_path'):
            semantic_info = f" [{result['semantic_path']}]"
        
        return f"{result['score']:.2f} {result['path']}:{result['line_start']}-{result['line_end']}{semantic_info}"
    
    else:
        # Enhanced verbose mode with semantic context
        lines = [
            f"📄 File: {result['path']}:{result['line_start']}-{result['line_end']} | 🏷️ Language: {result['language']} | 📊 Score: {result['score']:.3f}"
        ]
        
        if result.get('semantic_path'):
            lines.append(f"🔧 Semantic: {result['semantic_path']} ({result.get('semantic_type', 'unknown')}) | 📝 Signature: {result.get('semantic_signature', 'N/A')}")
        
        if result.get('semantic_parent'):
            lines.append(f"🏗️ Context: {result['semantic_parent']} | 🎯 Scope: {result.get('semantic_scope', 'unknown')}")
        
        return '\n'.join(lines)
```

## Benefits of This Approach

1. **Precise Code Navigation**: Find `UserService.authenticate` directly
2. **Better Context**: Understand what each chunk represents
3. **Improved Search**: Filter by semantic type, language features
4. **Enhanced Display**: See function signatures, class context
5. **Backward Compatible**: Falls back to text chunking for unsupported languages
6. **Extensible**: Easy to add new languages and semantic types

## Questions for Implementation

1. **Chunk Size Strategy**: Should we allow semantic chunks to exceed normal size limits?
2. **Nested Structures**: How to handle nested classes/functions (full path vs parent reference)?
3. **Performance**: Cache AST parsing results during bulk indexing?
4. **Error Handling**: How aggressive should fallback to text chunking be?
5. **Configuration**: Per-language settings for semantic chunking?

This proposal provides a comprehensive path to semantic chunking while maintaining compatibility with existing functionality and improving the user experience significantly.