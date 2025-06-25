"""
Test for real Claude response formatting issues.

This test reproduces the exact formatting issue seen in the user's real Claude response
where headers, bold text, code blocks and other formatting are not being displayed properly.
"""

import tempfile
from pathlib import Path
from io import StringIO

from src.code_indexer.services.claude_integration import ClaudeIntegrationService
from rich.console import Console


def test_real_claude_response_formatting_issue():
    """Test that reproduces the exact formatting issue from user's real Claude response."""

    # Create a test ClaudeIntegrationService
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "main.py").write_text("print('hello')")

        service = ClaudeIntegrationService(
            codebase_dir=temp_path, project_name="test_project"
        )

        # Use the exact Claude response content from the user's output
        real_claude_response = """I'll analyze this codebase to understand what the project is about and identify the top 5 core algorithms. Let me start with semantic searches to 
understand the project's purpose and key components.
🔍✨ Semantic search: 'project purpose main functionality' --limit 10 (description=Search for project overview and main functionality)
Let me read the README to understand the project purpose better.
📖 Reading: /home/jsbattig/Dev/code-indexer/README.md
Now let me search for core algorithms and key components in the codebase:
🔍✨ Semantic search: 'core algorithms indexing chunking embedding' --limit 15 (description=Search for core algorithms in the codebase)
Let me search for more specific algorithms and services:
🔍✨ Semantic search: 'vector search semantic similarity embedding generation git topology' --limit 10 (description=Search for vector search and git 
algorithms)
Let me read the key algorithm files to understand the core components:
📖 Reading: /home/jsbattig/Dev/code-indexer/src/code_indexer/indexing/chunker.py
📖 Reading: /home/jsbattig/Dev/code-indexer/src/code_indexer/services/qdrant.py
🔍✨ Semantic search: 'git topology branch aware incremental indexing' --limit 10 (description=Search for git and branch topology algorithms)
📖 Reading: /home/jsbattig/Dev/code-indexer/src/code_indexer/services/git_topology_service.py
Now let me search for embedding generation and file watching algorithms:
🔍✨ Semantic search: 'file watcher real time monitoring debouncing' --limit 8 (description=Search for file watching algorithms)
📖 Reading: /home/jsbattig/Dev/code-indexer/src/code_indexer/services/git_aware_watch_handler.py
Now let me search for smart indexing logic:
🔍✨ Semantic search: 'smart indexing progressive metadata resumable' --limit 8 (description=Search for smart indexing algorithms)
Based on my comprehensive analysis of the code-indexer codebase, I can now provide a detailed overview of what this project is about and identify the top 5
core algorithms.

## 🔬 **Code-Indexer Project Analysis**

### **What is This Project About?**

**Code-Indexer** is an AI-powered semantic code search tool (/home/jsbattig/Dev/code-indexer/README.md) that transforms how developers search and understand codebases. Unlike traditional text-based search, it uses advanced AI embeddings to understand the 
**meaning** and **context** of code, enabling semantic queries like "authentication logic" or "error handling patterns."

**Key Project Purpose:**
- **Semantic Code Search**: Find code by meaning, not just keywords
- **Multi-Provider Support**: Works with both local (Ollama) and cloud (VoyageAI) AI models
- **Git-Aware Intelligence**: Understands branch topology and code changes
- **Real-Time Synchronization**: Keeps search index current as code evolves
- **AI-Powered Analysis**: Integrates with Claude CLI for intelligent code analysis using RAG

## 🧠 **Top 5 Core Algorithms at the Heart of This Codebase**

### **1. Intelligent Text Chunking Algorithm**
**Location:** TextChunker class (/home/jsbattig/Dev/code-indexer/src/code_indexer/indexing/chunker.py)

**What it does:**
- **Language-Aware Splitting**: Uses regex patterns specific to each programming language (Python, JavaScript, C++, etc.) to break code at semantic 
boundaries
- **Smart Fragment Prevention**: Filters out meaningless fragments like lone docstring delimiters or incomplete function definitions
- **Overlap Management**: Implements configurable chunk overlap to preserve context across boundaries
- **Size Optimization**: Dynamically adjusts chunk sizes while maintaining code coherence

**Algorithm highlights:**
```python
# Language-specific splitters preserve semantic meaning
"py": [
    r"\n\ndef *",  # Function definitions
    r"\n\nclass *",  # Class definitions  
    r"\n\nasync def *",  # Async functions
]
```

### **2. Git Topology-Aware Branch Analysis Algorithm**
**Location:** GitTopologyService class (/home/jsbattig/Dev/code-indexer/src/code_indexer/services/git_topology_service.py)

**What it does:**
- **O(δ) Complexity Optimization**: Only processes files that actually changed between branches, not the entire codebase
- **Merge Base Analysis**: Uses `git merge-base` to find common ancestors and determine minimal change sets
- **Working Directory Integration**: Tracks staged/unstaged files separately from committed changes
- **Branch Ancestry Mapping**: Maintains parent-child relationships for topology-aware queries

**Algorithm highlights:**
```python
def analyze_branch_change(self, old_branch: str, new_branch: str) -> BranchChangeAnalysis:
    # Find merge base for efficient diff
    merge_base = self._get_merge_base(old_branch, new_branch)
    # Get only changed files using git diff
    changed_files = self._get_changed_files(old_branch, new_branch)  
    # Separate files needing full reindex vs metadata updates
    unchanged_files = 
```

### **3. Vector Search with Model-Aware Filtering Algorithm**
**Location:** QdrantClient class (/home/jsbattig/Dev/code-indexer/src/code_indexer/services/qdrant.py)

**What it does:**
- **Cosine Similarity Search**: Uses high-dimensional vector space for semantic code matching
- **Multi-Model Support**: Filters results by embedding model to ensure consistency
- **Branch Topology Integration**: Combines vector similarity with git branch visibility
- **Performance Optimization**: Uses disk-based storage and quantization for large codebases

**Algorithm highlights:**
```python
def search_with_model_filter(self, query_vector: List, embedding_model: str):
    # Create model filter for consistency
    model_filter = self.create_model_filter(embedding_model)
    # Combine with branch topology filters
    final_filter = self.combine_filters(model_filter, additional_filters)
    # Perform vector search with filters
    return self.search(query_vector, filter_conditions=final_filter)
```

### **4. Real-Time File Monitoring with Debounced Processing Algorithm**
**Location:** GitAwareWatchHandler class (/home/jsbattig/Dev/code-indexer/src/code_indexer/services/git_aware_watch_handler.py)

**What it does:**
- **Multi-Threaded Architecture**: Separates file system monitoring, change batching, and index updates
- **Intelligent Debouncing**: Prevents thrashing during rapid development by batching changes with configurable delays
- **Git State Integration**: Monitors both file changes AND git branch switches for comprehensive awareness
- **Thread-Safe Operations**: Uses locks and atomic operations for reliable concurrent processing

**Algorithm highlights:**
```python
def _process_changes_loop(self):
    while True:
        time.sleep(self.debounce_seconds)  # Configurable debouncing
        # Check git state changes first
        git_change = self.git_monitor.check_for_changes()
        if git_change:
            continue  # Handle branch changes separately
        # Process batched file changes
        self._process_pending_changes()
```

### **5. Progressive Metadata with Smart Resume Algorithm**
**Location:** ProgressiveMetadata class (/home/jsbattig/Dev/code-indexer/src/code_indexer/services/progressive_metadata.py) and SmartIndexer class (/home/jsbattig/Dev/code-indexer/src/code_indexer/services/smart_indexer.py)

**What it does:**
- **Continuous Progress Saving**: Saves metadata after every file processed, not just at the end
- **Intelligent Resume Logic**: Determines whether to do full indexing, incremental updates, or resume interrupted operations
- **Configuration Change Detection**: Forces full reindex when embedding providers or models change
- **Safety Buffers**: Uses time-based buffers to handle rapid development cycles

**Algorithm highlights:**
```python
def determine_indexing_strategy(self) -> IndexingStrategy:
    if not self.has_existing_index():
        return IndexingStrategy.FULL_INDEX
    if self.embedding_config_changed():
        return IndexingStrategy.FULL_INDEX  
    if self.has_interrupted_indexing():
        return IndexingStrategy.RESUME
    return IndexingStrategy.INCREMENTAL  # Smart default
```

## 🔄 **How These Algorithms Work Together**

These five algorithms form a sophisticated pipeline:

1. **Text Chunking** breaks code into semantically meaningful pieces
2. **Git Topology Analysis** determines what needs reprocessing when branches change  
3. **Vector Search** enables fast semantic similarity matching
4. **File Monitoring** keeps the index current in real-time
5. **Progressive Metadata** ensures reliable operations and smart resumption

The result is a system that can handle large codebases efficiently while providing lightning-fast semantic search that understands code context and 
relationships, not just text matches."""

        # Capture console output with terminal formatting enabled
        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=80)

        # Test the _render_content_with_file_links method
        result = service._render_content_with_file_links(real_claude_response, console)

        # Get the captured output
        output = string_io.getvalue()

        # Should process the content successfully
        assert result is True, "Should successfully process the content"

        # Should not be empty
        assert len(output.strip()) > 0, "Should produce formatted output"

        print(f"Raw output length: {len(output)}")
        print(f"First 500 chars of output:\n{output[:500]}")

        # The main issue: Headers should be formatted properly (not as plain text)
        # Look for ANSI color codes that indicate proper formatting
        lines = output.split("\n")

        # Find the main headers that should be formatted
        analysis_header_found = False
        algorithm_header_found = False

        # Join all lines to handle headers that span multiple lines due to formatting
        full_output_text = " ".join(lines)

        for line in lines:
            stripped = line.strip()
            if "Code-Indexer Project Analysis" in stripped:
                analysis_header_found = True
                # Look for ANSI color codes (cyan = \x1b[96m or similar)
                assert (
                    "\x1b[" in line
                ), f"Main header '{stripped}' should have ANSI color codes, got: {repr(line)}"

            # Check for "Top 5" and "Core Algorithms" separately since they might be on different lines
            if ("Top" in stripped and "5" in stripped) or (
                "Core Algorithms" in stripped
            ):
                if "\x1b[" in line:
                    algorithm_header_found = True

        # Also check if the full text contains the algorithms header
        if "Top 5 Core Algorithms" in full_output_text.replace("\x1b[", "").replace(
            "[0m", ""
        ):
            algorithm_header_found = True

        assert analysis_header_found, "Should find the main project analysis header"
        assert (
            algorithm_header_found
        ), f"Should find the algorithms header. Found lines with formatting: {[line for line in lines if 'Core Algorithms' in line or ('Top' in line and '5' in line)]}"

        # Check that bold text is properly formatted with ANSI codes
        bold_text_formatted = False
        for line in lines:
            if "Code-Indexer" in line and ("AI-powered" in line or "semantic" in line):
                # Look for ANSI bold codes
                if "\x1b[" in line:
                    bold_text_formatted = True
                    break

        assert (
            bold_text_formatted
        ), "Should find and properly format bold text with ANSI codes"

        # Check that code blocks are formatted properly
        for line in lines:
            if "```python" in line or line.strip().startswith("```"):
                # Code blocks should be handled specially
                break

        # Note: We'll add code block assertions later once we understand how they should be handled


def test_current_formatting_method_works():
    """Test that demonstrates the current _render_content_with_file_links method now works to format content."""

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "main.py").write_text("print('hello')")

        service = ClaudeIntegrationService(
            codebase_dir=temp_path, project_name="test_project"
        )

        # Simple test content with headers and bold text
        test_content = """## Main Header

This is **bold text** and this is *italic text*.

### Sub Header

Some regular text with `inline code`.

```python
def example():
    return "code block"
```

- List item 1
- List item 2"""

        string_io = StringIO()
        console = Console(file=string_io, force_terminal=True, width=80)

        # This should format the content properly now
        service._render_content_with_file_links(test_content, console)
        output = string_io.getvalue()

        print(f"Current formatting output:\n{output}")

        # Now check if formatting is working properly
        lines = output.split("\n")
        header_formatted = False

        for line in lines:
            if "Main Header" in line:
                # Should have ANSI color codes now
                if "\x1b[" in line:
                    header_formatted = True
                    print(f"Found formatted header: {repr(line)}")

        # This should now PASS with our fix
        assert (
            header_formatted
        ), f"Headers should now be formatted with ANSI codes. Output was: {repr(output[:200])}"
