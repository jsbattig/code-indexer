# Epic: AST-Based Semantic Code Chunking

## Epic Overview
**As a** developer using code-indexer  
**I want** code to be chunked based on semantic AST boundaries rather than character counts  
**So that** each chunk represents a complete, meaningful code unit that improves search relevance and context understanding

## Business Value
- **Improved Search Accuracy**: Chunks align with actual code structures (classes, methods, functions)
- **Better Context Preservation**: Complete semantic units prevent broken code fragments
- **Enhanced LLM Understanding**: AI models receive complete, syntactically valid code blocks
- **Precise Code Navigation**: Natural addressing like `ClassName.methodName` instead of line ranges
- **Language-Aware Intelligence**: Respects language-specific constructs and patterns

## Technical Approach
We will create entirely new AST parsing code using standard libraries:
- **Python**: Use built-in `ast` module for parsing
- **JavaScript/TypeScript**: Use tree-sitter parsers
- **Java**: Use tree-sitter Java parser
- **Go**: Use tree-sitter Go parser
- **Separate parser classes**: Each language gets its own dedicated parser class
- **Fallback support**: Text chunking for unsupported languages and regular text files

---

## Story 1: AST Chunking Infrastructure
**As a** developer  
**I want** a new AST-based chunking system that integrates with tree-sitter  
**So that** code can be parsed and chunked based on semantic boundaries

### Acceptance Criteria
- [ ] Create `ASTChunker` class that uses tree-sitter for parsing
- [ ] Support Python, JavaScript, TypeScript, and Java initially
- [ ] Fall back to `TextChunker` for unsupported languages
- [ ] Integrate with existing `IndexingConfig` to enable/disable AST chunking
- [ ] Maintain backward compatibility with existing chunks

### Technical Implementation
```python
class SemanticChunker:
    def __init__(self, config: IndexingConfig):
        self.config = config
        self.text_chunker = TextChunker(config)  # Fallback
        
        # Separate parser class for each language
        self.parsers = {
            'python': PythonSemanticParser(),
            'javascript': JavaScriptSemanticParser(),
            'typescript': TypeScriptSemanticParser(),
            'java': JavaSemanticParser(),
            'go': GoSemanticParser(),
        }
        
    def chunk_file(self, content: str, file_path: str) -> List[SemanticChunk]:
        language = self._detect_language(file_path)
        
        # Use semantic chunking if language is supported
        if language in self.parsers and self.config.use_semantic_chunking:
            try:
                return self.parsers[language].chunk(content, file_path)
            except Exception:
                # Fallback to text chunking on any AST parsing error
                pass
        
        # Fallback for unsupported languages and regular text files
        return self.text_chunker.chunk_file(content, file_path)
```

### Definition of Done
- SemanticChunker class created with separate parser classes per language
- Configuration option added to enable/disable semantic chunking
- Tests verify AST parsing and fallback behavior for all supported languages
- Performance benchmarks show acceptable speed
- Fallback works seamlessly for unsupported languages and text files

---

## Story 2: Python Semantic Chunking
**As a** developer working with Python code  
**I want** Python files chunked at class and function boundaries  
**So that** each chunk contains complete, meaningful Python constructs

### Acceptance Criteria
- [ ] Chunk at top-level functions (including async)
- [ ] Chunk at class definitions (entire class as one chunk if within size limit)
- [ ] Handle decorators properly (include with function/class)
- [ ] Chunk large classes at method boundaries
- [ ] Include docstrings with their associated code
- [ ] Handle module-level code (imports, globals) as separate chunks

### Semantic Boundaries
```python
# Chunk 1: Module imports and globals
import os
import sys
GLOBAL_VAR = 42

# Chunk 2: Complete function with decorators
@decorator
@another_decorator
def process_data(input_data):
    """Process the input data."""
    return transformed_data

# Chunk 3: Complete class (if small enough)
class DataProcessor:
    def __init__(self):
        pass
    
    def process(self):
        pass

# Chunk 4: Individual method (if class is too large)
# Metadata: DataProcessor.complex_method
def complex_method(self, data):
    # Long method body...
```

### Metadata Enhancement
- Add `semantic_type`: "function", "class", "method", "module_code"
- Add `semantic_path`: "DataProcessor.complex_method"
- Add `semantic_context`: Parent class/module information
- Preserve existing line number tracking

### Definition of Done
- Python files chunk at semantic boundaries
- Large constructs intelligently split
- Metadata includes semantic information
- Tests verify various Python patterns

---

## Story 3: JavaScript/TypeScript Semantic Chunking
**As a** developer working with JavaScript/TypeScript  
**I want** JS/TS files chunked at function and class boundaries  
**So that** callbacks, arrow functions, and classes are kept intact

### Acceptance Criteria
- [ ] Chunk at function declarations and expressions
- [ ] Handle arrow functions and callbacks intelligently
- [ ] Chunk at class definitions
- [ ] Handle TypeScript interfaces and type definitions
- [ ] Process React/Vue components as semantic units
- [ ] Include JSDoc comments with associated code

### Semantic Boundaries
```javascript
// Chunk 1: Imports and types
import { Something } from './module';
interface UserData { /*...*/ }

// Chunk 2: Complete function
function processUser(user: UserData): ProcessedUser {
    return { /*...*/ };
}

// Chunk 3: Class with methods
class UserService {
    async getUser(id: string) { /*...*/ }
    async updateUser(id: string, data: UserData) { /*...*/ }
}

// Chunk 4: React component
const UserComponent: React.FC<Props> = ({ user }) => {
    return <div>{user.name}</div>;
};

// Chunk 5: Express route with callback
// Metadata: route.handler[POST:/api/users]
app.post('/api/users', async (req, res) => {
    // Route handler
});
```

### Definition of Done
- JS/TS files chunk at semantic boundaries
- Framework patterns recognized (React, Express, etc.)
- Arrow functions and callbacks handled properly
- TypeScript constructs preserved

---

## Story 4: Java Semantic Chunking
**As a** developer working with Java code  
**I want** Java files chunked at class and method boundaries  
**So that** complete Java constructs are preserved

### Acceptance Criteria
- [ ] Chunk at class/interface/enum definitions
- [ ] Handle nested classes appropriately
- [ ] Chunk large classes at method boundaries
- [ ] Include annotations with methods/classes
- [ ] Handle package and import statements
- [ ] Process Javadoc comments with code

### Semantic Boundaries
```java
// Chunk 1: Package and imports
package com.example.service;
import java.util.*;

// Chunk 2: Complete interface
public interface UserService {
    User findById(Long id);
    void save(User user);
}

// Chunk 3: Class with annotations
@Service
@Transactional
public class UserServiceImpl implements UserService {
    // If small enough, entire class
}

// Chunk 4: Individual method from large class
// Metadata: UserServiceImpl.complexBusinessLogic
@Override
@Cacheable("users")
public User complexBusinessLogic(Long id) {
    // Method implementation
}
```

### Definition of Done
- Java files chunk at semantic boundaries
- Annotations preserved with code
- Nested structures handled correctly
- Tests cover common Java patterns

---

## Story 5: Go Semantic Chunking
**As a** developer working with Go code  
**I want** Go files chunked at function, struct, and interface boundaries  
**So that** complete Go constructs are preserved

### Acceptance Criteria
- [ ] Chunk at function definitions
- [ ] Chunk at struct definitions with methods
- [ ] Chunk at interface definitions
- [ ] Handle package declarations and imports
- [ ] Process method receivers properly
- [ ] Include comments and documentation

### Semantic Boundaries
```go
// Chunk 1: Package and imports
package main

import (
    "fmt"
    "net/http"
)

// Chunk 2: Struct with methods
type UserService struct {
    db *Database
}

// Chunk 3: Method with receiver
// Metadata: UserService.GetUser
func (us *UserService) GetUser(id int) (*User, error) {
    // Method implementation
}

// Chunk 4: Interface definition
type UserRepository interface {
    GetUser(id int) (*User, error)
    SaveUser(user *User) error
}

// Chunk 5: Standalone function
func main() {
    // Main function
}
```

### Definition of Done
- Go files chunk at semantic boundaries
- Receivers and methods properly associated
- Interfaces and structs handled correctly
- Tests cover common Go patterns

---

## Story 6: Intelligent Chunk Size Management with Semantic Linking
**As a** developer  
**I want** AST chunks to respect size limits while maintaining semantic integrity and complete coverage  
**So that** no code is lost and large objects are properly linked across multiple chunks

### Acceptance Criteria
- [ ] Show as much of each semantic object as possible within chunk size limits
- [ ] Split large objects (classes, methods) while preserving ALL content
- [ ] Maintain semantic linking across split chunks (same `semantic_path` for all parts)
- [ ] Split at intelligent boundaries (statement level, not arbitrary character counts)
- [ ] Track chunk parts with `part_of_total` metadata (e.g., "1 of 3", "2 of 3")
- [ ] Never lose any content during chunking process
- [ ] Group small related items efficiently

### Critical Requirements
1. **No Data Loss**: Every line of code must be indexed somewhere
2. **Semantic Linking**: Split chunks maintain the same semantic identity
3. **Complete Coverage**: Large objects are fully represented across multiple chunks
4. **Intelligent Splitting**: Split at statement boundaries, not mid-expression

### Splitting Strategies
```python
def chunk_large_method(self, method_node, content, class_name):
    """Handle methods that exceed chunk size limits."""
    method_content = self._extract_method_content(method_node, content)
    
    if len(method_content) <= self.config.max_chunk_size:
        # Fits in one chunk - show complete object
        return [self._create_single_method_chunk(method_node, content, class_name)]
    else:
        # Must split but maintain semantic linking
        return self._split_method_into_semantic_chunks(method_node, content, class_name)

def _split_method_into_semantic_chunks(self, method_node, content, class_name):
    """Split large method while preserving semantic identity."""
    chunks = []
    semantic_path = f"{class_name}.{method_node.name}"
    
    # Split at statement boundaries, not arbitrary character counts
    statements = self._extract_statements(method_node)
    
    current_chunk = []
    current_size = 0
    
    for stmt in statements:
        stmt_size = len(stmt)
        
        if current_size + stmt_size > self.config.max_chunk_size and current_chunk:
            # Create chunk with same semantic identity
            chunks.append(SemanticChunk(
                semantic_path=semantic_path,  # SAME for all parts
                semantic_type='method',
                semantic_name=method_node.name,
                part_of_total=f"{len(chunks)+1} of {total_parts}",
                content='\n'.join(current_chunk)
            ))
            current_chunk = []
            current_size = 0
        
        current_chunk.append(stmt)
        current_size += stmt_size
    
    # Add final chunk - NO CONTENT LOST
    if current_chunk:
        chunks.append(SemanticChunk(
            semantic_path=semantic_path,  # SAME semantic identity
            part_of_total=f"{len(chunks)+1} of {total_parts}",
            content='\n'.join(current_chunk)
        ))
    
    return chunks
```

### Enhanced Display with Split Objects
```bash
# Query results showing split method with semantic linking
0.85 user_service.py:45-120 [UserService.very_large_method] (part 1 of 3)
 45: def very_large_method(self, data):
 46:     """Process large amounts of data."""
 47:     # First part of method - complete statements
 ...
120:     # End of first chunk at statement boundary

0.83 user_service.py:121-200 [UserService.very_large_method] (part 2 of 3)
121:     # Continuation of same method - SAME semantic identity
122:     # Middle part of method
 ...
200:     # End of second chunk at statement boundary

0.81 user_service.py:201-250 [UserService.very_large_method] (part 3 of 3)
201:     # Final part of method - ALL content preserved
 ...
250:     return result  # Method complete, no content lost
```

### Configuration
```python
class ASTChunkingConfig:
    max_chunk_size: int = 2000  # Larger than text chunking
    min_chunk_size: int = 200   # Avoid tiny fragments
    group_small_methods: bool = True
    split_large_methods: bool = True
    preserve_context_lines: int = 2
    split_at_statement_boundaries: bool = True  # Never split mid-expression
```

### Definition of Done
- Large constructs split intelligently at statement boundaries
- All chunks from split objects have same `semantic_path`
- Part tracking shows "X of Y" for split objects
- Zero content loss during chunking process
- Small items grouped efficiently
- Configuration options documented
- Performance remains acceptable

---

## Story 7: Metadata and Context Enhancement
**As a** developer  
**I want** rich metadata with each AST chunk including split tracking  
**So that** I can understand the code's context and handle split objects properly

### Acceptance Criteria
- [ ] Include full semantic path (e.g., "ClassName.InnerClass.methodName")
- [ ] Add parent context (containing class/module)
- [ ] Include signature for functions/methods
- [ ] Add import context for better understanding
- [ ] Track split objects with part information
- [ ] Preserve all existing metadata (line numbers, etc.)

### Enhanced Metadata Structure
```python
{
    # Existing metadata
    "path": "src/services/user_service.py",
    "line_start": 45,
    "line_end": 67,
    
    # New AST metadata
    "semantic_chunking": True,
    "semantic_type": "method",
    "semantic_path": "UserService.authenticate",
    "semantic_signature": "def authenticate(self, username: str, password: str) -> Optional[User]",
    "semantic_parent": "class UserService(BaseService)",
    "semantic_context": {
        "imports": ["from typing import Optional", "from .models import User"],
        "class_decorators": ["@service", "@injectable"],
        "method_decorators": ["@validate_input"]
    },
    "semantic_scope": "class",
    "semantic_language_features": ["async", "private"],
    
    # Split tracking (for large objects split across chunks)
    "is_split_object": True,
    "part_number": 1,
    "total_parts": 3,
    "part_of_total": "1 of 3",
    
    "ast_chunk_version": "1.0"
}
```

### Split Object Linking
All chunks from the same split object share:
- **Same `semantic_path`**: `"UserService.authenticate"`
- **Same `semantic_type`**: `"method"`
- **Same `semantic_signature`**: Complete method signature
- **Different `part_number`**: 1, 2, 3, etc.
- **Same `total_parts`**: Total number of chunks for this object

### Definition of Done
- Rich metadata available for each chunk
- Semantic paths enable precise navigation
- Split objects properly tracked and linked
- Context helps understand isolated chunks
- Part tracking enables reassembly of split objects
- Backward compatible with existing queries

---

## Story 8: Search and Retrieval Enhancement
**As a** developer  
**I want** to search using semantic paths  
**So that** I can find specific methods and classes directly

### Acceptance Criteria
- [ ] Support queries like "UserService.authenticate"
- [ ] Enable searching by semantic type (find all classes)
- [ ] Integrate with existing search infrastructure
- [ ] Maintain compatibility with line-based search
- [ ] Add semantic filters to search API

### Query Examples
```bash
# Find specific method
cidx query "UserService.authenticate"

# Find all methods named "process"
cidx query "*.process" --semantic-type method

# Find all React components
cidx query --semantic-type component --language typescript

# Traditional search still works
cidx query "authentication logic"
```

### Definition of Done
- Semantic path queries functional
- Type-based filtering implemented
- Search performance acceptable
- Documentation updated

---

## Story 9: Enhanced Query Display  
**As a** developer  
**I want** query results to show semantic context information  
**So that** I can quickly understand what code structures match my search

### Acceptance Criteria
- [ ] Show semantic path in brackets `[UserService.authenticate]` for both quiet and verbose modes
- [ ] Display full code content with line numbers in both modes
- [ ] In verbose mode, show additional semantic metadata (signature, context, scope)
- [ ] Quiet mode only suppresses headers/footers, not match details
- [ ] Maintain existing score and file location display

### Enhanced Display Examples

#### Quiet Mode (no headers/footers, full match info)
```bash
0.85 authentication.py:6-26 [UserService.authenticate]
  6: @validate_input
  7: def authenticate(self, username: str, password: str) -> bool:
  8:     """Authenticate user credentials against the database."""
  9:     if not username or not password:
 10:         return False
 11:     # ... rest of function

0.92 user_service.py:45-67 [UserService.validate_email]
 45: def validate_email(self, email: str) -> bool:
 46:     """Validate email format and domain."""
 47:     import re
 48:     # ... rest of function
```

#### Verbose Mode (with headers/footers plus semantic metadata)
```bash
📊 Search Results for "authenticate" (3 matches found)
════════════════════════════════════════════════════

📄 File: authentication.py:6-26 | 🏷️ Language: python | 📊 Score: 0.856
🔧 Semantic: UserService.authenticate (method) | 📝 Signature: def authenticate(self, username: str, password: str) -> bool
🏗️ Context: class UserService(BaseService) | 🎯 Scope: class

📖 Content (Lines 6-26):
──────────────────────────────────────────────────
  6: @validate_input
  7: def authenticate(self, username: str, password: str) -> bool:
  8:     """Authenticate user credentials against the database."""
  9:     if not username or not password:
 10:         return False
 11:     # ... rest of function

════════════════════════════════════════════════════
📊 Found 3 matches in 0.45s
```

### Definition of Done
- Both quiet and verbose modes show semantic context
- Full code content displayed in both modes
- Semantic metadata enhances understanding
- No change to core functionality, only enhanced display

---

## Story 10: Comprehensive AST Test Suite Generation
**As a** developer implementing semantic chunking  
**I want** comprehensive test coverage for all AST parsing scenarios  
**So that** the semantic chunking is robust and handles all language constructs correctly

### Acceptance Criteria
- [ ] Generate test source code files for all supported languages in `tests/ast_test_cases/`
- [ ] Create at least 3 test cases for each unique AST construct per language
- [ ] Cover all language features that result in unique AST parsing behavior
- [ ] Include edge cases, nested constructs, and complex scenarios
- [ ] Generate unit tests that verify correct semantic chunking for each test case
- [ ] Ensure high test coverage (>90%) for all AST parsing code

### Test File Structure
```
tests/ast_test_cases/
├── python/
│   ├── classes/
│   │   ├── simple_class.py
│   │   ├── nested_class.py
│   │   ├── multiple_inheritance.py
│   ├── functions/
│   │   ├── simple_function.py
│   │   ├── async_function.py
│   │   ├── generator_function.py
│   │   ├── lambda_functions.py
│   ├── decorators/
│   │   ├── function_decorators.py
│   │   ├── class_decorators.py
│   │   ├── multiple_decorators.py
│   ├── control_flow/
│   │   ├── if_statements.py
│   │   ├── loops.py
│   │   ├── exception_handling.py
│   └── edge_cases/
│       ├── very_long_method.py
│       ├── deeply_nested.py
│       └── mixed_constructs.py
├── javascript/
│   ├── functions/
│   │   ├── function_declarations.js
│   │   ├── arrow_functions.js
│   │   ├── callback_functions.js
│   ├── classes/
│   │   ├── es6_classes.js
│   │   ├── constructor_functions.js
│   │   ├── prototype_methods.js
│   ├── modules/
│   │   ├── import_export.js
│   │   ├── commonjs_modules.js
│   │   ├── dynamic_imports.js
│   └── async/
│       ├── promises.js
│       ├── async_await.js
│       └── generators.js
├── typescript/
│   ├── interfaces/
│   │   ├── simple_interface.ts
│   │   ├── generic_interface.ts
│   │   ├── extending_interfaces.ts
│   ├── types/
│   │   ├── type_aliases.ts
│   │   ├── union_types.ts
│   │   ├── conditional_types.ts
│   ├── generics/
│   │   ├── generic_functions.ts
│   │   ├── generic_classes.ts
│   │   ├── generic_constraints.ts
│   └── decorators/
│       ├── method_decorators.ts
│       ├── class_decorators.ts
│       └── parameter_decorators.ts
├── java/
│   ├── classes/
│   │   ├── SimpleClass.java
│   │   ├── AbstractClass.java
│   │   ├── InnerClasses.java
│   ├── interfaces/
│   │   ├── SimpleInterface.java
│   │   ├── FunctionalInterface.java
│   │   ├── DefaultMethods.java
│   ├── enums/
│   │   ├── SimpleEnum.java
│   │   ├── EnumWithMethods.java
│   │   └── EnumWithConstructors.java
│   ├── annotations/
│   │   ├── MethodAnnotations.java
│   │   ├── ClassAnnotations.java
│   │   └── CustomAnnotations.java
│   └── generics/
│       ├── GenericClass.java
│       ├── GenericMethods.java
│       └── BoundedGenerics.java
└── go/
    ├── functions/
    │   ├── simple_functions.go
    │   ├── variadic_functions.go
    │   ├── method_receivers.go
    ├── structs/
    │   ├── simple_struct.go
    │   ├── embedded_structs.go
    │   ├── struct_methods.go
    ├── interfaces/
    │   ├── simple_interface.go
    │   ├── empty_interface.go
    │   ├── interface_embedding.go
    ├── packages/
    │   ├── package_functions.go
    │   ├── exported_functions.go
    │   └── init_functions.go
    └── goroutines/
        ├── goroutine_functions.go
        ├── channel_operations.go
        └── select_statements.go
```

### Language Feature Coverage Requirements

#### Python
- [ ] Classes (simple, nested, multiple inheritance)
- [ ] Functions (sync, async, generators, lambdas)
- [ ] Decorators (function, class, multiple)
- [ ] Control flow (if/else, loops, try/except)
- [ ] Modules (imports, from imports, star imports)
- [ ] Context managers (with statements)
- [ ] Comprehensions (list, dict, set, generator)

#### JavaScript
- [ ] Functions (declarations, expressions, arrows, callbacks)
- [ ] Classes (ES6, constructor functions, prototype)
- [ ] Modules (import/export, CommonJS, dynamic)
- [ ] Async (promises, async/await, generators)
- [ ] Objects (literals, destructuring, spread)
- [ ] Closures and hoisting scenarios

#### TypeScript
- [ ] All JavaScript features plus:
- [ ] Interfaces (simple, generic, extending)
- [ ] Types (aliases, unions, intersections, conditional)
- [ ] Generics (functions, classes, constraints)
- [ ] Decorators (method, class, parameter)
- [ ] Namespaces and modules
- [ ] Enums and const assertions

#### Java
- [ ] Classes (simple, abstract, inner, static)
- [ ] Interfaces (simple, functional, default methods)
- [ ] Enums (simple, with methods, with constructors)
- [ ] Annotations (built-in, custom, method/class)
- [ ] Generics (classes, methods, bounded)
- [ ] Packages and imports

#### Go
- [ ] Functions (simple, variadic, with receivers)
- [ ] Structs (simple, embedded, with methods)
- [ ] Interfaces (simple, empty, embedding)
- [ ] Packages (functions, exported, init)
- [ ] Goroutines and channels
- [ ] Type definitions and methods

### Unit Test Requirements
- [ ] Each test case file has corresponding unit tests
- [ ] Tests verify correct semantic chunking output
- [ ] Tests check semantic metadata (type, name, path, signature)
- [ ] Tests validate chunk boundaries and content
- [ ] Tests verify split object handling for large constructs
- [ ] Tests ensure no content loss during chunking
- [ ] Performance tests for large files with many constructs

### Definition of Done
- All test case files generated in `tests/ast_test_cases/`
- Unit tests achieve >90% coverage for AST parsing code
- All language features covered with at least 3 test cases each
- Edge cases and complex scenarios included
- Tests pass for all supported languages
- Performance benchmarks within acceptable limits

---

## Story 11: Migration and Compatibility
**As a** developer with existing indexed projects  
**I want** smooth migration to AST chunking  
**So that** I can benefit without re-indexing everything

### Acceptance Criteria
- [ ] Detect chunks created with old vs new system
- [ ] Provide migration command for gradual updates
- [ ] Support mixed environments (some AST, some text chunks)
- [ ] Add `--reindex-ast` flag to force AST re-chunking
- [ ] Document migration process

### Migration Strategy
1. New indexing uses AST by default (if configured)
2. Existing chunks remain valid
3. Incremental re-indexing on file changes
4. Bulk migration command available
5. Ability to disable AST per-project

### Definition of Done
- Migration path documented
- Mixed chunk types coexist
- Performance impact measured
- Rollback procedure available

---

## Epic Definition of Done
- [ ] All stories completed with acceptance criteria met
- [ ] AST chunking available for Python, JavaScript, TypeScript, Java, and Go
- [ ] Intelligent chunk size management with semantic linking implemented
- [ ] Split objects properly tracked and linked across chunks
- [ ] Zero content loss during chunking process
- [ ] Enhanced query display shows semantic context in both quiet and verbose modes
- [ ] **Comprehensive test suite generated** with >90% coverage for AST parsing code
- [ ] **Test files created** in `tests/ast_test_cases/` for all supported languages
- [ ] **At least 3 test cases** for each unique AST construct per language
- [ ] **Unit tests verify** correct semantic chunking for all language features
- [ ] **Edge cases and complex scenarios** thoroughly tested
- [ ] Performance benchmarks show acceptable impact (<20% slower than text chunking)
- [ ] Search accuracy improved (measure with test queries)
- [ ] Documentation complete with examples
- [ ] Integration tests cover various code patterns and split object scenarios
- [ ] Fallback to text chunking works seamlessly
- [ ] Feature flag enables gradual rollout

## Technical Dependencies
- **NEW AST parsing code** using standard libraries (NOT ls-ai-code)
- Python's built-in `ast` module for Python parsing
- Tree-sitter parsers for JavaScript, TypeScript, Java, and Go
- Existing chunking infrastructure (TextChunker for fallback)
- Qdrant schema supports new semantic metadata fields
- Search API extensions for semantic queries

## Performance Considerations
- AST parsing overhead vs. improved search quality
- Memory usage for large files
- Caching parsed ASTs during bulk indexing
- Parallel processing for multiple files
- Split object processing overhead

## Breaking Changes
- None - fallback to text chunking maintains compatibility
- New metadata fields added but existing queries still work
- Enhanced display shows additional information but doesn't break existing functionality

## Future Enhancements
- Support for additional languages (Rust, C/C++)
- Semantic diff chunking for git-aware indexing
- Cross-file semantic understanding (inheritance, imports)
- IDE integration with semantic navigation
- LLM-optimized chunk formatting
- Advanced split object reassembly for IDE features