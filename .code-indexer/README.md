# Code Indexer Configuration Guide

This directory contains your project's code indexing configuration.

## Quick Start

1. **Review** the `config.json` file below
2. **Customize** the settings (especially `exclude_dirs`)
3. **Run** `code-indexer index` to start indexing

## Configuration File: config.json

Edit `config.json` to customize how your codebase is indexed.

### Key Settings

#### `exclude_dirs` - Folders to Skip
Add directory names to exclude from indexing:
```json
"exclude_dirs": [
  "node_modules", "dist", "build",     // Build outputs
  "logs", "cache", "tmp",              // Temporary files  
  "coverage", ".pytest_cache",         // Test artifacts
  "vendor", "third_party",             // Dependencies
  "my_custom_folder"                   // Your custom exclusions
]
```

#### `file_extensions` - File Types to Index
Specify which file types to include:
```json
"file_extensions": ["py", "js", "ts", "java", "cpp", "go", "rs", "md"]
```

#### `max_file_size` - Size Limit (bytes)
Files larger than this are skipped (default: 1MB):
```json
"max_file_size": 2097152  // 2MB limit
```

#### `chunk_size` - Text Processing Size
How text is split for AI processing:
- Larger = more context, slower processing
- Smaller = less context, faster processing
```json
"chunk_size": 1500  // 1500 characters (default)
```

## Additional Exclusions

The system also respects `.gitignore` patterns automatically.
You can use `.gitignore` for file-level exclusions:

```gitignore
*.log
*.tmp
temp_files/
generated_*
```

## After Making Changes

Run this command to apply your configuration changes:
```bash
code-indexer index --clear
```

## Need Help?

- Run `code-indexer --help` for command documentation
- Run `code-indexer COMMAND --help` for specific command help
- Check the main documentation for advanced configuration

