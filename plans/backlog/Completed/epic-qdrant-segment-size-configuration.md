# Epic: Configurable Qdrant Segment Size for Git-Friendly Storage

## Epic Intent
Enable users to configure Qdrant segment size during initialization to optimize storage for their use case, with a default of 100MB segments that prioritize search performance while remaining compatible with Git platforms.

## User Stories

### Story 1: Add Segment Size Configuration to QdrantConfig
**As a developer**, I want to configure Qdrant segment size in the configuration file so that I can optimize storage based on my project's Git requirements.

**Acceptance Criteria:**
- GIVEN the QdrantConfig class in src/code_indexer/config.py
- WHEN I add a new configuration field for segment size
- THEN the field should be named `max_segment_size_kb` with type int
- AND the default value should be 102400 (100MB in KB)
- AND the field should include proper documentation explaining the Git-friendly default
- AND the field should have validation to ensure values are positive integers

**Technical Implementation:**
```pseudocode
class QdrantConfig(BaseModel):
    # Add new field
    max_segment_size_kb: int = Field(
        default=102400,
        description="Maximum segment size in KB (default: 100MB for optimal performance)"
    )
    
    # Add validation
    @field_validator("max_segment_size_kb")
    def validate_segment_size(cls, v):
        if v <= 0:
            raise ValueError("Segment size must be positive")
        return v
```

### Story 2: Add CLI Option to Init Command
**As a user**, I want to specify segment size during initialization so that I can set it without manually editing configuration files.

**Acceptance Criteria:**
- GIVEN the init command in src/code_indexer/cli.py
- WHEN I add a new CLI option `--qdrant-segment-size`
- THEN it should accept integer values representing MB
- AND it should have a helpful description about Git compatibility and performance
- AND it should default to 100 (100MB) if not specified
- AND it should validate that the value is positive
- AND it should convert MB to KB internally for storage
- AND it should update the QdrantConfig when provided

**Technical Implementation:**
```pseudocode
@click.option(
    "--qdrant-segment-size",
    type=int,
    default=100,
    help="Qdrant segment size in MB (default: 100MB for optimal performance)"
)
def init(ctx, ..., qdrant_segment_size: int, ...):
    # Validate segment size
    if qdrant_segment_size <= 0:
        console.print("❌ Qdrant segment size must be positive", style="red")
        sys.exit(1)
    
    # Convert MB to KB for internal storage
    segment_size_kb = qdrant_segment_size * 1024
    
    # Update qdrant configuration
    if updates needed:
        qdrant_config = config.qdrant.model_dump()
        qdrant_config["max_segment_size_kb"] = segment_size_kb
        updates["qdrant"] = qdrant_config
```

### Story 3: Apply Segment Size Configuration in Qdrant Collection Creation
**As a developer**, I want the configured segment size to be applied when creating Qdrant collections so that storage respects my Git-friendly settings.

**Acceptance Criteria:**
- GIVEN the QdrantClient class in src/code_indexer/services/qdrant.py
- WHEN creating collections via `_create_collection_direct` method
- THEN the `optimizers_config` should use the configured `max_segment_size_kb`
- AND the configuration should be passed through all collection creation methods
- AND existing hardcoded segment size values should be replaced with config values

**Technical Implementation:**
```pseudocode
def _create_collection_direct(self, collection_name: str, vector_size: int) -> bool:
    collection_config = {
        "vectors": {...},
        "hnsw_config": {...},
        "optimizers_config": {
            "memmap_threshold": 20000,
            "indexing_threshold": 10000,
            "default_segment_number": 8,
            "max_segment_size_kb": self.config.max_segment_size_kb  # Use config value
        },
        "on_disk_payload": True,
    }
```

### Story 4: Update Documentation and Help Text
**As a user**, I want clear documentation about segment size configuration so that I understand the Git compatibility benefits and performance trade-offs.

**Acceptance Criteria:**
- GIVEN the init command help text
- WHEN displaying help for the `--qdrant-segment-size` option
- THEN it should explain the Git compatibility benefits of smaller segments
- AND it should mention the performance trade-offs
- AND it should provide examples of appropriate values in MB

**Technical Implementation:**
```pseudocode
CLI Help Text Updates:
- Add --qdrant-segment-size to init command examples
- Explain 100MB default for optimal performance
- Document performance considerations (smaller = faster indexing, more files)
- Provide examples: 10MB (Git-friendly), 50MB (balanced), 100MB (default), 200MB (large repos)
- Add to configuration documentation in README.md
```

### Story 5: Provide Usage Examples and Documentation
**As a user**, I want clear examples of how to use the --qdrant-segment-size option so that I can choose appropriate values for my use case.

**Acceptance Criteria:**
- GIVEN the init command documentation
- WHEN users read the help text or documentation
- THEN they should see clear examples of segment size usage
- AND examples should include common scenarios with explanations
- AND performance trade-offs should be clearly documented

**Technical Implementation:**
```pseudocode
Documentation Examples:
# Default (optimal performance)
code-indexer init --qdrant-segment-size 100

# Git-friendly for smaller files
code-indexer init --qdrant-segment-size 10

# Balanced approach
code-indexer init --qdrant-segment-size 50

# Large repositories prioritizing search performance
code-indexer init --qdrant-segment-size 200
```

### Story 6: Backward Compatibility and Migration
**As a developer**, I want existing configurations to continue working without manual intervention so that the feature introduction doesn't break existing setups.

**Acceptance Criteria:**
- GIVEN existing .code-indexer/config.json files without max_segment_size_kb
- WHEN loading the configuration
- THEN the default value (102400 KB = 100MB) should be used automatically
- AND no migration or user intervention should be required
- AND existing collections should continue functioning with their current segment sizes
- AND new collections should use the new default

**Technical Implementation:**
```pseudocode
# Pydantic automatically handles missing fields with defaults
# No explicit migration needed - Field(default=10240) handles it

# Ensure backward compatibility in QdrantClient
def _create_collection_direct(self, collection_name: str, vector_size: int) -> bool:
    # Use getattr for safe access with fallback
    max_segment_size = getattr(self.config, 'max_segment_size_kb', 102400)  # 100MB default
```

### Story 7: Testing Infrastructure for Segment Size Configuration
**As a quality assurance engineer**, I want comprehensive tests for segment size configuration so that the feature works reliably across different scenarios.

**Acceptance Criteria:**
- GIVEN the test suite
- WHEN testing segment size configuration
- THEN unit tests should verify config field validation
- AND CLI tests should verify the --qdrant-segment-size option works correctly
- AND integration tests should verify Qdrant collections use the configured size
- AND tests should verify MB to KB conversion works properly
- AND backward compatibility tests should ensure existing configs work

**Technical Implementation:**
```pseudocode
# Unit tests for config validation
def test_segment_size_validation():
    # Test positive values accepted
    # Test negative values rejected
    # Test default value applied (102400 KB = 100MB)

# CLI tests
def test_init_qdrant_segment_size_option():
    # Test CLI option parsing (MB input)
    # Test MB to KB conversion (100 MB = 102400 KB)
    # Test validation

# Integration tests
def test_qdrant_uses_configured_segment_size():
    # Create collection with custom segment size
    # Verify Qdrant collection configuration
    # Test different size values (10MB, 50MB, 100MB, 200MB)
```

## Implementation Notes

- **Default Choice**: 100MB default prioritizes search performance while staying within Git platform limits
- **Git Platform Limits**: 
  - GitHub: 100MB individual file limit (50MB warning), 1GB repository recommended
  - GitLab: 100MB individual file limit (free tier), 10GB repository soft limit
  - Bitbucket: 4GB repository hard limit, 2GB recommended for performance
- **Performance Impact**: Smaller segments = faster indexing, more files; Larger segments = better search performance, fewer files
- **Backward Compatibility**: Pydantic Field defaults ensure seamless upgrades
- **Configuration Location**: QdrantConfig is the natural location for this setting
- **CLI Integration**: Follows existing patterns in init command for embedding provider selection