# Code Indexer Release Notes

## Version 1.1.0.0 (2025-01-05)

### 🚀 Major Feature: Copy-on-Write (CoW) Clone Support

#### **Migration Middleware System**
- **Real-time Migration Detection**: Automatically detects when indexed projects are CoW clones and handles migration gracefully
- **Migration State Tracking**: Persistent state tracking across system restarts with async-safe operations
- **Decorator Integration**: `@requires_qdrant_access` decorator automatically applied to all Qdrant-dependent CLI commands
- **Deadlock Prevention**: Fixed critical async deadlock in migration state management

#### **CoW Operations Support**
- **Force-flush Command**: New `force-flush` command ensures data consistency before CoW cloning
- **Multi-filesystem Support**: Comprehensive examples for BTRFS, ZFS, and XFS filesystems
- **Project Isolation**: Proper handling of local storage directories for cloned projects
- **Configuration Migration**: Automatic config fixing for cloned projects

#### **Enhanced CLI Integration**
- **8 Commands Protected**: Applied migration middleware to index, query, claude, watch, status, optimize, schema, and start commands
- **Comprehensive Help**: Added detailed CoW cloning examples and workflow documentation
- **Error Handling**: Robust error handling for missing directories and test environments

#### **Testing Infrastructure**
- **E2E CoW Test**: Comprehensive 10-phase end-to-end test for complete CoW clone workflow
- **Aggressive Setup Pattern**: Tests use shared services for better performance while maintaining isolation
- **Full Automation Integration**: CoW tests included in full-automation.sh by default

### 📊 Technical Implementation
- **Async-safe Operations**: All migration operations designed for concurrent access
- **Snapshot API Integration**: Uses Qdrant snapshot API for reliable data flushing
- **Project Path Flexibility**: Supports both current directory and explicit project path specifications
- **Cleanup Management**: Automatic cleanup of temporary snapshots and migration artifacts

### 🔧 Developer Experience
- **Example Workflows**: Complete documentation of CoW cloning processes for different filesystems
- **Integration Testing**: Comprehensive test coverage for migration scenarios
- **Performance Optimized**: Minimal overhead for non-CoW operations

## Version 1.0.0.7 (2025-01-04)

### 🧪 Testing Infrastructure Improvements

#### **Complete Test Collection Registration System**
- **100% Test Coverage**: Systematically reviewed and updated all 50 Qdrant-dependent tests for proper collection registration
- **Two Registration Patterns**: Implemented both `auto_register_project_collections()` for E2E tests and `register_test_collection()` for integration tests
- **Test Isolation**: All tests now have proper cleanup and isolation mechanisms preventing test pollution
- **Mock Classification**: Properly distinguished between tests using real Qdrant vs mocks (24 tests use mocks appropriately)
- **Zero Missing Registration**: Achieved 0 tests missing required collection registration

#### **Code Quality & Compliance**
- **Linting Compliance**: Fixed all formatting issues with Black, Ruff, and MyPy compliance
- **Systematic Approach**: Used comprehensive audit process with detailed tracking and verification
- **Documentation**: Updated comprehensive audit report with final completion status

### 📊 Test Infrastructure Metrics
- **22 tests (44%)** properly use collection registration for real Qdrant operations
- **4 tests (8%)** have partial registration (intentional for specific testing scenarios)
- **24 tests (48%)** use mocks and don't require collection registration
- **0 tests (0%)** missing required collection registration

## Version 1.0.0.2 (2025-06-26)

### 🐛 Critical Bug Fixes

#### **Throttling System Overhaul**
- **Fixed Stuck Throttling States**: Resolved critical bug where CLIENT_THROTTLED state could persist indefinitely
- **Bounds Checking**: Added bounds checking in RateLimiter.consume_tokens() to prevent extreme negative token values
- **Overflow Protection**: Implemented overflow protection in wait_time() calculation, capping wait times at 120 seconds
- **Recovery Time Improvement**: Reduced maximum recovery time from 11.6 days to ≤1 minute (8,333x improvement)
- **Race Condition Handling**: Enhanced concurrent token consumption handling to prevent extreme negative states
- **Comprehensive Testing**: Added 34 new test cases validating the throttling fix across multiple scenarios

### 📊 Performance Metrics
- **Wait Time Cap**: Maximum wait time reduced from 1,000,001 seconds to 120 seconds
- **Recovery Guarantee**: Throttling states now guaranteed to recover within reasonable timeframes
- **Concurrent Safety**: Improved handling of concurrent token consumption scenarios

## Version 0.1.1.0 (2025-06-25)

### 🚀 Major Features & Enhancements

#### **Comprehensive System Improvements**
- **Enhanced Test Infrastructure**: Implemented reliable end-to-end testing framework with comprehensive test coverage
- **Cancellation System**: Added robust cancellation handling with database consistency guarantees
- **Infrastructure Modernization**: Comprehensive system improvements across all core components

#### **Git-Aware Indexing Enhancements**
- **Branch Topology Awareness**: Smart incremental indexing across git branches with O(δ) complexity
- **Advanced Git Integration**: Comprehensive git-aware indexing and testing infrastructure
- **Working Directory Support**: Index staged and unstaged files for comprehensive coverage

#### **Claude CLI Integration**
- **Streaming Feedback**: Implemented Claude CLI streaming feedback with `--show-claude-plan` feature
- **AI-Powered Analysis**: Enhanced integration with Claude CLI for intelligent code analysis using RAG
- **Tool Tracking**: Improved Claude tool tracking and response handling

#### **Performance & Reliability**
- **Progress Reporting**: Fixed and enhanced progress indicator with real-time feedback
- **Concurrent Processing**: Added support for high-throughput parallel processing
- **Indexing Lock System**: Implemented comprehensive indexing lock management for concurrent safety

#### **Testing & Quality Assurance**
- **Comprehensive Test Suite**: Added 30+ new test files covering various scenarios
- **Pytest Markers**: Enhanced test organization with markers for different test types
- **CI/CD Improvements**: Improved continuous integration with faster test execution

### 🐛 Bug Fixes
- Fixed progress indicator display issues
- Resolved indexing problems with file processing
- Addressed linting errors and code quality issues  
- Fixed reconcile functionality bugs
- Corrected display formatting issues during indexing

### 🔧 Technical Improvements
- **Code Quality**: Comprehensive linting fixes and code improvements
- **Documentation**: Enhanced README with updated installation instructions
- **Dependencies**: Added proper dependency management with requirements files
- **Docker Management**: Improved Docker container lifecycle management
- **Configuration**: Enhanced configuration system with new options

### 📁 New Components
- `git_hook_manager.py` - Git hook management system
- `indexing_lock.py` - Concurrent indexing protection
- `vector_calculation_manager.py` - Vector computation optimization
- `high_throughput_processor.py` - Enhanced parallel processing
- Multiple new test modules for comprehensive coverage

### 🏗️ Architecture Improvements
- **Service Layer**: Refactored core services for better modularity
- **Chunking System**: Enhanced code chunking with improved algorithms
- **Vector Database**: Optimized Qdrant integration and search parameters
- **Health Checking**: Improved service health monitoring

### 📋 Documentation & Planning
- Added comprehensive technical documentation plans
- Created dependency documentation
- Added execution plan tracking
- Enhanced README with detailed setup instructions

---

## Version 0.1.0.0 (2024-06-24)

### 🎉 Initial Major Release

#### **Core Features**
- **Semantic Code Search**: AI-powered semantic search using vector embeddings
- **Multiple Embedding Providers**: Support for both Ollama (local) and VoyageAI (cloud)
- **Vector Database**: Integrated Qdrant for efficient vector storage and retrieval
- **Docker Integration**: Automated Docker container management for services
- **CLI Interface**: Rich command-line interface with progress bars and interactive features

#### **Git Integration**
- **Incremental Updates**: Smart re-indexing of only changed files
- **Branch Awareness**: Git-aware processing with branch topology understanding
- **Multi-Project Support**: Handle multiple projects simultaneously

#### **Search & Filtering**
- **Language Filtering**: Filter results by programming language
- **Path Filtering**: Search within specific directories or files
- **Similarity Scoring**: Configurable similarity thresholds
- **Result Ranking**: Intelligent ranking of search results

#### **Performance Features**
- **Parallel Processing**: Concurrent embedding generation for faster indexing
- **Optimized Chunking**: Intelligent code chunking for better search accuracy
- **Caching**: Efficient caching mechanisms to avoid redundant processing
- **Progress Tracking**: Real-time progress feedback during operations

#### **Configuration & Usability**
- **Project Detection**: Automatic project name detection from git repos
- **Configurable Settings**: Extensive configuration options
- **Multiple Aliases**: Both `code-indexer` and `cidx` command aliases
- **Path Parameter**: Added `--path` parameter for flexible directory targeting

---

## Previous Versions

### Version 0.0.25.0 and Earlier
- Initial development versions
- Core functionality implementation
- Basic search and indexing capabilities
- Foundation for git-aware processing

---

## Installation

### Using pipx (Recommended)
```bash
pipx install https://github.com/jsbattig/code-indexer/releases/download/v1.0.0.7/code_indexer-1.0.0.7-py3-none-any.whl
```

### Using pip
```bash
pip install https://github.com/jsbattig/code-indexer/releases/download/v1.0.0.7/code_indexer-1.0.0.7-py3-none-any.whl
```

### From Source
```bash
pip install git+https://github.com/jsbattig/code-indexer.git
```

## Getting Started

1. **Initialize and Start Services**
   ```bash
   code-indexer init
   code-indexer start
   ```

2. **Index Your Code**
   ```bash
   code-indexer index /path/to/your/project
   ```

3. **Search Your Code**
   ```bash
   code-indexer search "your search query"
   ```

For detailed usage instructions, see the [README](README.md).

---

**Note**: This project is under active development. Features and APIs may change between versions. Please check the documentation for the most up-to-date information.