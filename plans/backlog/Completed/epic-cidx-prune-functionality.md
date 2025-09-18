# Epic: Cidx Prune Functionality for Database Cleanup

## Epic Intent
Implement a comprehensive `cidx prune` command that removes database objects (chunks, metadata, visibility records) whose file paths no longer pass the current filtering criteria, enabling users to clean up their vector database after changing filtering rules, gitignore patterns, or override configurations.

## Business Value
- **Database Consistency**: Ensures vector database only contains objects for files that should be indexed
- **Storage Optimization**: Removes unnecessary data after configuration changes, reducing storage usage
- **Performance Improvement**: Smaller database means faster queries and lower memory usage
- **Configuration Flexibility**: Users can confidently change filtering rules knowing they can clean up afterward
- **Maintenance Hygiene**: Regular cleanup prevents database bloat over time

## Technical Background

### Current Filtering Architecture
The system uses a multi-layered filtering approach to determine which files should be indexed:

1. **Base Filtering (FileFinder)**: 
   - `file_extensions` whitelist from config
   - `exclude_dirs` patterns from config  
   - `max_file_size` limit from config
   - Gitignore patterns (recursive .gitignore files)
   - Common exclude patterns (node_modules, __pycache__, etc.)
   - Text file detection (binary file exclusion)

2. **Override Filtering (OverrideFilterService)**:
   - `force_exclude_patterns` (highest priority - absolute exclusion)
   - `force_include_patterns` (overrides base exclusion)
   - `add_extensions`/`remove_extensions` (modify file extension filtering)
   - `add_exclude_dirs`/`add_include_dirs` (modify directory filtering)

3. **Configuration Sources**:
   - Main config file (`.code-indexer/config.json`)
   - Override config file (`.code-indexer-override.yaml`)
   - Project-specific gitignore files (`.gitignore`)

### Database Object Types
Objects in Qdrant that contain file path information and are subject to pruning:

- **Content Chunks**: Text chunks from indexed files (`type="content"`)
- **File Metadata**: File-level metadata records (`type="metadata"`)
- **Visibility Records**: Branch visibility tracking (`type="visibility"`)

Each object contains a `path` field with the relative file path from the codebase root.

## User Stories

### Story 1: Basic Prune Command Implementation
**As a developer**, I want a `cidx prune` command that removes database objects for files that no longer pass filtering criteria, so that my database stays clean after configuration changes.

**Acceptance Criteria:**
- GIVEN a vector database with indexed content
- WHEN I run `cidx prune`
- THEN the system should identify objects whose file paths don't pass current filtering
- AND remove those objects from the database
- AND display a summary of what was pruned
- AND maintain objects for files that still pass filtering criteria
- AND preserve database integrity throughout the operation

**Technical Implementation:**
```pseudocode
def prune_command(dry_run: bool = False, quiet: bool = False):
    # Initialize filtering components
    config = ConfigManager.load()
    file_finder = FileFinder(config)
    
    # Get current valid file paths
    valid_files = set()
    for file_path in file_finder.find_files():
        relative_path = str(file_path.relative_to(config.codebase_dir))
        valid_files.add(relative_path)
    
    # Query database for all indexed file paths
    qdrant_client = QdrantClient(config)
    indexed_objects = get_all_indexed_objects(qdrant_client)
    
    # Identify objects to prune
    objects_to_prune = []
    for obj in indexed_objects:
        file_path = obj.payload.get("path")
        if file_path and file_path not in valid_files:
            objects_to_prune.append(obj)
    
    # Report and execute pruning
    if not quiet:
        report_pruning_summary(objects_to_prune, valid_files)
    
    if not dry_run:
        execute_pruning(qdrant_client, objects_to_prune)
        
    return PruningStats(
        objects_scanned=len(indexed_objects),
        objects_pruned=len(objects_to_prune),
        files_remaining=len(valid_files)
    )
```

### Story 2: Dry-Run and Reporting Capabilities
**As a developer**, I want to see what would be pruned before actually removing objects, so that I can verify the pruning operation is correct.

**Acceptance Criteria:**
- GIVEN a database with objects to be pruned
- WHEN I run `cidx prune --dry-run`
- THEN the system should show what would be pruned without making changes
- AND display statistics about objects to be removed vs retained
- AND group pruned objects by reason (gitignore, config exclude, extension, etc.)
- AND show file paths that would be affected
- AND provide clear summary statistics

**Technical Implementation:**
```pseudocode
def generate_pruning_report(objects_to_prune, valid_files, config):
    # Categorize pruning reasons
    pruning_reasons = {
        "gitignore_excluded": [],
        "extension_filtered": [],
        "directory_excluded": [],
        "size_exceeded": [],
        "override_excluded": [],
        "file_not_found": [],
        "binary_file": []
    }
    
    for obj in objects_to_prune:
        file_path = Path(obj.payload["path"])
        reason = determine_exclusion_reason(file_path, config)
        pruning_reasons[reason].append(str(file_path))
    
    # Generate detailed report
    report = PruningReport(
        total_objects=len(objects_to_prune) + len(valid_files),
        objects_to_prune=len(objects_to_prune),
        objects_to_retain=len(valid_files),
        pruning_breakdown=pruning_reasons,
        storage_savings_estimate=estimate_storage_savings(objects_to_prune)
    )
    
    return report

def determine_exclusion_reason(file_path: Path, config: Config) -> str:
    # Determine why a file is no longer passing filters
    if not file_path.exists():
        return "file_not_found"
    if file_path.stat().st_size > config.indexing.max_file_size:
        return "size_exceeded"
    # ... check other exclusion reasons ...
```

### Story 3: Selective Pruning with Filtering Options
**As a developer**, I want to prune only specific types of objects or files matching certain patterns, so that I can perform targeted cleanup operations.

**Acceptance Criteria:**
- GIVEN various filtering options for pruning
- WHEN I run `cidx prune --pattern "*.js" --type content`
- THEN only JavaScript content chunks should be considered for pruning
- AND other file types should be ignored during this operation
- AND the system should support multiple filter combinations
- AND filtering should work with object types (content, metadata, visibility)

**Technical Implementation:**
```pseudocode
@click.command()
@click.option("--pattern", multiple=True, help="Only prune files matching pattern")
@click.option("--type", type=click.Choice(["content", "metadata", "visibility", "all"]), 
              default="all", help="Object type to prune")
@click.option("--exclude-pattern", multiple=True, help="Skip files matching pattern")
@click.option("--dry-run", is_flag=True, help="Show what would be pruned")
@click.option("--quiet", is_flag=True, help="Minimal output")
def prune_command(pattern, type, exclude_pattern, dry_run, quiet):
    """Prune database objects that no longer pass filtering criteria."""
    
    # Apply selective filtering
    pruning_filter = PruningFilter(
        include_patterns=list(pattern),
        exclude_patterns=list(exclude_pattern),
        object_types=[type] if type != "all" else ["content", "metadata", "visibility"]
    )
    
    # Execute selective pruning
    execute_selective_pruning(pruning_filter, dry_run, quiet)
```

### Story 4: Performance-Optimized Pruning for Large Databases
**As a developer with large codebases**, I want pruning operations to be efficient and non-blocking, so that I can clean up large databases without impacting system performance.

**Acceptance Criteria:**
- GIVEN a large database with millions of objects
- WHEN I run `cidx prune`
- THEN the operation should process objects in batches
- AND provide progress feedback during long operations
- AND not overwhelm the database with simultaneous requests
- AND allow cancellation via Ctrl+C without corrupting the database
- AND resume capability if interrupted during large operations

**Technical Implementation:**
```pseudocode
def execute_batch_pruning(qdrant_client, objects_to_prune, progress_callback):
    batch_size = 1000  # Process 1000 objects at a time
    total_batches = (len(objects_to_prune) + batch_size - 1) // batch_size
    
    with ProgressBar(total=len(objects_to_prune)) as progress:
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(objects_to_prune))
            batch_objects = objects_to_prune[start_idx:end_idx]
            
            # Extract point IDs from batch
            point_ids = [obj.id for obj in batch_objects]
            
            # Delete batch from Qdrant
            try:
                qdrant_client.delete_points(
                    collection_name=config.qdrant.collection_name,
                    point_ids=point_ids
                )
                progress.update(len(batch_objects))
                
            except KeyboardInterrupt:
                # Save progress for potential resume
                save_pruning_progress(batch_idx, total_batches, objects_to_prune)
                raise
                
            except Exception as e:
                logger.warning(f"Failed to prune batch {batch_idx}: {e}")
                continue
```

## Implementation Strategy

### **Risk Level: Medium-Low**
- **Data Safety**: Implements dry-run and detailed reporting before actual deletion
- **Performance Impact**: Uses batch processing to avoid overwhelming database
- **Recoverability**: Objects can be restored by re-running indexing
- **Backward Compatibility**: New command doesn't affect existing functionality

### **Mitigation Strategies:**
1. **Mandatory Dry-Run First**: Show what will be pruned before deletion
2. **Batch Processing**: Process objects in manageable chunks
3. **Progress Persistence**: Save progress for large operations
4. **Conservative Defaults**: Err on side of caution for ambiguous cases
5. **Comprehensive Testing**: Test with various configuration scenarios

## Technical Requirements

### **CLI Interface:**
```bash
# Basic pruning
cidx prune

# Dry run to see what would be pruned
cidx prune --dry-run

# Selective pruning
cidx prune --pattern "*.js" --type content
cidx prune --exclude-pattern "test/**" --type metadata

# Quiet mode for scripting
cidx prune --quiet --dry-run
```

### **Configuration Integration:**
```yaml
# .code-indexer-override.yaml
pruning:
  auto_suggest: true          # Suggest pruning after config changes
  batch_size: 1000           # Objects per batch during pruning
  require_confirmation: true  # Require explicit confirmation for pruning
  preserve_object_types:     # Never prune these object types
    - "visibility"
```

### **Output Format:**
```
🧹 Pruning Analysis
==================
Objects scanned: 15,234
Objects to prune: 1,847
Objects to retain: 13,387

Pruning breakdown:
  • Extension filtered: 423 objects (removed .log, .tmp extensions)
  • Directory excluded: 891 objects (added node_modules/, dist/ to excludes)
  • Gitignore patterns: 298 objects (new .gitignore patterns)
  • File not found: 235 objects (files deleted from disk)

Estimated storage savings: ~47.2MB

Run without --dry-run to execute pruning.
```

## Definition of Done

### **Code Implementation:**
- [ ] Core pruning algorithm implemented
- [ ] Qdrant integration for object enumeration and deletion
- [ ] FileFinder integration for current filtering criteria
- [ ] Batch processing for large datasets
- [ ] Progress tracking and cancellation support

### **CLI Interface:**
- [ ] `cidx prune` command with all specified options
- [ ] Comprehensive help text and usage examples  
- [ ] Integration with existing CLI architecture

### **Safety Features:**
- [ ] Mandatory dry-run reporting before deletion
- [ ] Detailed breakdown of pruning reasons
- [ ] Progress persistence for large operations
- [ ] Safe batch processing with error recovery

### **Testing:**
- [ ] Unit tests for pruning logic
- [ ] Integration tests with various configurations
- [ ] Performance tests with large datasets
- [ ] Error handling and recovery tests

### **Documentation:**
- [ ] Updated README with prune command documentation
- [ ] CLI help text covers all options and use cases
- [ ] Configuration examples for pruning settings

This epic provides a comprehensive solution for database cleanup that maintains safety, performance, and usability while giving users full control over their vector database hygiene.