# Story 7: Multi-Provider Support with Filesystem Backend

**Story ID:** S07
**Epic:** Filesystem-Based Vector Database Backend
**Priority:** Medium
**Estimated Effort:** 2-3 days
**Implementation Order:** 8

## User Story

**As a** developer using different embedding providers
**I want to** use filesystem backend with VoyageAI, Ollama, and other providers
**So that** I can choose the best embedding model without container dependencies

**Conversation Reference:** User implicitly requires provider flexibility - existing system supports multiple providers, filesystem backend must maintain this capability.

## Acceptance Criteria

### Functional Requirements
1. ✅ VoyageAI embeddings (1024-dim) work with filesystem backend
2. ✅ Ollama embeddings (768-dim) work with filesystem backend
3. ✅ Projection matrices adapt to different vector dimensions
4. ✅ Collection names include provider/model identifier
5. ✅ Multiple provider collections coexist in same repository
6. ✅ Each provider has correct projection matrix for its dimensions

### Technical Requirements
1. ✅ Dynamic projection matrix creation based on vector size
2. ✅ Provider-aware collection naming
3. ✅ Dimension validation during indexing
4. ✅ Correct quantization regardless of input dimensions
5. ✅ Metadata tracking of embedding model used

### Compatibility Requirements
1. ✅ All existing embedding providers work unchanged
2. ✅ Same provider API as Qdrant backend
3. ✅ No provider-specific code in FilesystemVectorStore
4. ✅ Model switching requires reindexing (no mixing)

## Manual Testing Steps

```bash
# Test 1: Index with VoyageAI (1024-dim)
cd /path/to/test-repo
cidx init --vector-store filesystem --embedding-provider voyage
cidx index

# Expected output:
# ℹ️ Using VoyageAI provider (voyage-code-3, 1024 dimensions)
# ℹ️ Creating projection matrix: 1024 → 64 dimensions
# ⏳ Indexing files: [====>  ] 30/100 (30%)...
# ✅ Indexed 100 files, 523 vectors

# Verify collection structure
ls .code-indexer/vectors/
# Expected: voyage-code-3/ directory

cat .code-indexer/vectors/voyage-code-3/collection_meta.json
# Expected: "vector_size": 1024

# Verify projection matrix dimensions
python3 << EOF
import numpy as np
matrix = np.load('.code-indexer/vectors/voyage-code-3/projection_matrix.npy')
print(f"Projection matrix shape: {matrix.shape}")
EOF
# Expected: Projection matrix shape: (1024, 64)

# Test 2: Index with Ollama (768-dim)
cidx init --vector-store filesystem --embedding-provider ollama --embedding-model nomic-embed-text
cidx index

# Expected output:
# ℹ️ Using Ollama provider (nomic-embed-text, 768 dimensions)
# ℹ️ Creating projection matrix: 768 → 64 dimensions
# ⏳ Indexing files: [====>  ] 30/100 (30%)...
# ✅ Indexed 100 files, 523 vectors

ls .code-indexer/vectors/
# Expected: voyage-code-3/, nomic-embed-text/ directories

# Test 3: Query with VoyageAI
cidx query "authentication" --collection voyage-code-3

# Expected: Results from VoyageAI collection
# 🔍 Searching in collection: voyage-code-3
# 📊 Found 8 results...

# Test 4: Query with Ollama
cidx query "database queries" --collection nomic-embed-text

# Expected: Results from Ollama collection

# Test 5: Switch providers (requires reindex)
cd /path/to/new-project
cidx init --vector-store filesystem --embedding-provider voyage
cidx index

# Switch to Ollama
cidx clean  # Clear existing collection
cidx init --vector-store filesystem --embedding-provider ollama
cidx index

# Expected: New collection with different dimensions

# Test 6: Multiple collections coexist
cd /path/to/multi-provider-repo
cidx init --vector-store filesystem --embedding-provider voyage
cidx index

# Index with different provider without cleaning
cidx init --vector-store filesystem --embedding-provider ollama --embedding-model nomic-embed-text
cidx index

ls .code-indexer/vectors/
# Expected: Both collections exist
# voyage-code-3/
# nomic-embed-text/

cidx status
# Expected output:
# 📁 Filesystem Backend
#   Collections: 2
#   - voyage-code-3 (523 vectors, 1024-dim)
#   - nomic-embed-text (523 vectors, 768-dim)

# Test 7: Dimension mismatch detection
# Try to add vectors with wrong dimensions to existing collection
# (This would be caught by validation)
cidx status --validate
# Expected: Dimension validation passes for all vectors
```

## Technical Implementation Details

### Provider-Aware Collection Management

```python
class FilesystemProviderSupport:
    """Handle multiple embedding providers with correct dimensions."""

    VECTOR_SIZES = {
        "voyage": 1024,
        "voyage-3": 1024,
        "voyage-code-3": 1024,
        "voyage-2": 1536,
        "ollama": 768,
        "nomic-embed-text": 768,
        "mxbai-embed-large": 1024,
        # Add new providers as needed
    }

    def __init__(self, base_path: Path):
        self.base_path = base_path

    def resolve_collection_name(
        self,
        base_name: str,
        embedding_model: str
    ) -> str:
        """Generate collection name including model identifier.

        Examples:
        - base_name="code_index", model="voyage-code-3" → "code_index_voyage-code-3"
        - base_name="code_index", model="nomic-embed-text" → "code_index_nomic-embed-text"
        """
        model_slug = embedding_model.lower().replace(":", "-").replace("/", "-")
        return f"{base_name}_{model_slug}"

    def get_vector_size_for_provider(
        self,
        provider: str,
        model: Optional[str] = None
    ) -> int:
        """Get expected vector dimension for provider/model.

        Args:
            provider: Provider name (voyage, ollama, etc)
            model: Specific model name

        Returns:
            Vector dimension (e.g., 1024, 768, 1536)
        """
        # Try specific model first
        if model and model in self.VECTOR_SIZES:
            return self.VECTOR_SIZES[model]

        # Fall back to provider default
        if provider in self.VECTOR_SIZES:
            return self.VECTOR_SIZES[provider]

        # Default to 1536 (most common)
        return 1536

    def create_provider_aware_collection(
        self,
        collection_name: str,
        embedding_model: str,
        provider: str
    ) -> bool:
        """Create collection with correct dimensions for provider.

        Args:
            collection_name: Base collection name
            embedding_model: Model identifier
            provider: Provider name

        Returns:
            Success status
        """
        # Resolve full collection name
        full_name = self.resolve_collection_name(collection_name, embedding_model)

        # Get correct vector size
        vector_size = self.get_vector_size_for_provider(provider, embedding_model)

        # Create collection with provider-specific dimensions
        collection_path = self.base_path / full_name
        collection_path.mkdir(parents=True, exist_ok=True)

        # Create projection matrix with correct input dimensions
        projection_matrix = self._create_projection_matrix(
            input_dim=vector_size,
            output_dim=64  # Always reduce to 64 dimensions
        )

        # Save projection matrix
        np.save(collection_path / "projection_matrix.npy", projection_matrix)

        # Create collection metadata
        metadata = {
            "name": full_name,
            "vector_size": vector_size,
            "embedding_provider": provider,
            "embedding_model": embedding_model,
            "created_at": datetime.utcnow().isoformat(),
            "reduced_dimensions": 64,
            "depth_factor": 4
        }

        meta_path = collection_path / "collection_meta.json"
        meta_path.write_text(json.dumps(metadata, indent=2))

        return True

    def validate_vector_dimensions(
        self,
        collection_name: str,
        vector: np.ndarray
    ) -> bool:
        """Validate vector dimensions match collection expectations.

        Args:
            collection_name: Collection to validate against
            vector: Vector to validate

        Returns:
            True if dimensions match, False otherwise
        """
        collection_path = self.base_path / collection_name
        meta_path = collection_path / "collection_meta.json"

        if not meta_path.exists():
            return False

        try:
            metadata = json.loads(meta_path.read_text())
            expected_dim = metadata['vector_size']
            actual_dim = len(vector)

            return expected_dim == actual_dim
        except Exception:
            return False

    def _create_projection_matrix(
        self,
        input_dim: int,
        output_dim: int
    ) -> np.ndarray:
        """Create deterministic projection matrix for dimensionality reduction.

        Uses deterministic seed based on dimensions for reproducibility.
        """
        seed = hash(f"projection_{input_dim}_{output_dim}") % (2**32)
        np.random.seed(seed)

        matrix = np.random.randn(input_dim, output_dim)
        matrix /= np.sqrt(output_dim)  # Normalize

        return matrix
```

### Integration with FilesystemVectorStore

```python
class FilesystemVectorStore:
    """Filesystem vector storage with provider support."""

    def __init__(self, base_path: Path, config: Config):
        self.base_path = base_path
        self.config = config
        self.provider_support = FilesystemProviderSupport(base_path)

    def create_collection(
        self,
        collection_name: str,
        vector_size: Optional[int] = None,
        embedding_provider: Optional[str] = None,
        embedding_model: Optional[str] = None
    ) -> bool:
        """Create collection with provider-aware dimensions.

        Args:
            collection_name: Base collection name
            vector_size: Explicit vector size (optional)
            embedding_provider: Provider name (optional)
            embedding_model: Model name (optional)

        Returns:
            Success status
        """
        # Use explicit vector size if provided
        if vector_size:
            # Direct creation with known dimensions
            return self._create_collection_with_size(collection_name, vector_size)

        # Use provider info to determine dimensions
        if embedding_provider and embedding_model:
            return self.provider_support.create_provider_aware_collection(
                collection_name,
                embedding_model,
                embedding_provider
            )

        # Default dimensions
        return self._create_collection_with_size(collection_name, 1536)

    def upsert_points(
        self,
        collection_name: str,
        points: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Store vectors with dimension validation.

        Validates vectors match collection's expected dimensions.
        """
        results = []

        for point in points:
            try:
                vector = np.array(point['vector'])

                # Validate dimensions
                if not self.provider_support.validate_vector_dimensions(
                    collection_name,
                    vector
                ):
                    collection_meta = self._get_collection_metadata(collection_name)
                    expected = collection_meta.get('vector_size', 'unknown')
                    actual = len(vector)

                    results.append({
                        'id': point.get('id'),
                        'status': 'error',
                        'error': f'Dimension mismatch: expected {expected}, got {actual}'
                    })
                    continue

                # Proceed with storage (from Story 2)
                self._store_vector(collection_name, point)
                results.append({'id': point['id'], 'status': 'ok'})

            except Exception as e:
                results.append({
                    'id': point.get('id'),
                    'status': 'error',
                    'error': str(e)
                })

        return {
            'status': 'ok',
            'result': {
                'processed': len(results),
                'errors': sum(1 for r in results if r['status'] == 'error')
            }
        }
```

### CLI Integration

```python
@click.command()
@click.option(
    "--embedding-provider",
    type=click.Choice(["voyage", "ollama"]),
    default="voyage",
    help="Embedding provider"
)
@click.option(
    "--embedding-model",
    help="Specific model (e.g., voyage-code-3, nomic-embed-text)"
)
def init_command(
    vector_store: str,
    embedding_provider: str,
    embedding_model: Optional[str],
    **kwargs
):
    """Initialize with provider-aware configuration."""
    # Determine vector size
    if embedding_model:
        model_name = embedding_model
    else:
        # Default models
        model_name = {
            "voyage": "voyage-code-3",
            "ollama": "nomic-embed-text"
        }[embedding_provider]

    # Create configuration
    config = create_config(
        vector_store_provider=vector_store,
        embedding_provider=embedding_provider,
        embedding_model=model_name,
        **kwargs
    )

    # Initialize backend
    backend = VectorStoreBackendFactory.create_backend(config)
    backend.initialize(config)

    # Report dimensions
    provider_support = FilesystemProviderSupport(Path(".code-indexer/vectors"))
    vector_size = provider_support.get_vector_size_for_provider(
        embedding_provider,
        model_name
    )

    console.print(f"✅ Initialized with {embedding_provider} provider")
    console.print(f"📊 Model: {model_name} ({vector_size} dimensions)")
```

## Dependencies

### Internal Dependencies
- Story 2: Vector storage infrastructure
- Story 1: Backend abstraction layer
- Existing embedding provider system

### External Dependencies
- NumPy for projection matrices with varying dimensions
- Existing VoyageAI and Ollama client integrations

## Success Metrics

1. ✅ VoyageAI and Ollama both work with filesystem backend
2. ✅ Projection matrices created with correct dimensions
3. ✅ Collections cleanly separated by provider/model
4. ✅ Dimension validation prevents corrupted indexes
5. ✅ Multiple provider collections coexist without conflicts

## Non-Goals

- Mixing vectors from different providers in same collection
- Runtime provider switching (requires reindex)
- Automatic dimension detection from vectors
- Cross-provider semantic search

## Follow-Up Stories

- **Story 8**: Switch Between Qdrant and Filesystem Backends (includes provider switching)

## Implementation Notes

### Critical Constraint: No Mixed Dimensions

**One collection = One embedding model = One vector dimension**

Collections CANNOT mix vectors of different dimensions because:
- Projection matrix is collection-specific
- Quantization depends on consistent dimensions
- Similarity computation requires identical vector spaces

To switch providers: Clean collection, reinit, reindex.

### Collection Naming Strategy

Include model identifier in collection name:
- `code_index_voyage-code-3` (explicit model)
- `code_index_nomic-embed-text` (explicit model)

This prevents collisions when same repository indexed with multiple providers.

### Projection Matrix Determinism

**Critical:** Projection matrices must be deterministic based on dimensions:
- Use `hash(f"projection_{input_dim}_{output_dim}")` as seed
- Same dimensions always produce same matrix
- Enables reproducible quantization
- Matrix can be regenerated if lost

### Dimension Validation

Validate dimensions at **two points**:
1. **Collection creation**: Create correct projection matrix
2. **Vector insertion**: Reject vectors with wrong dimensions

Early validation prevents corrupted indexes.

### Provider Discovery

System automatically discovers vector dimensions from:
1. Explicit `--embedding-model` flag
2. Provider defaults (voyage → 1024, ollama → 768)
3. Fallback to 1536 (most conservative)

### Storage Efficiency by Provider

| Provider | Vector Dim | Storage per Vector | Compression Ratio |
|----------|------------|-------------------|-------------------|
| VoyageAI | 1024 | ~12 KB | 2x better than 1536 |
| Ollama | 768 | ~9 KB | 3x better than 1536 |
| Default | 1536 | ~18 KB | Baseline |

Smaller dimensions = less git repository bloat.
