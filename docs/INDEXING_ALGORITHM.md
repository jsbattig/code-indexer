# Code Indexer - Indexing Algorithm Technical Documentation

## Overview

The Code Indexer employs a sophisticated two-phase parallel processing architecture designed to maximize throughput while maintaining file atomicity and providing real-time progress feedback. The system transforms source code files into searchable vector embeddings stored in Qdrant for semantic search capabilities.

## Architecture Components

### Core Processing Components

1. **SmartIndexer** - Orchestration layer managing the overall indexing workflow
2. **HighThroughputProcessor** - Dual-phase parallel processing engine
3. **FileChunkingManager** - Parallel file processing with lifecycle management
4. **VectorCalculationManager** - Multi-threaded embedding generation
5. **VoyageAI/Ollama Clients** - Embedding providers with dynamic batching
6. **CleanSlotTracker** - Thread-safe progress tracking and resource management
7. **Qdrant Client** - Vector database storage layer

## Two-Phase Processing Architecture

### Phase 1: Parallel Hash Calculation
The first phase performs parallel metadata extraction and file hashing to prepare files for vectorization:

```
Input: List of file paths
↓
Parallel Hash Workers (threadcount+2 threads)
├── Calculate file hash (SHA-256)
├── Extract git metadata (commit, branch, hash)
├── Determine file size and modification time
└── Build metadata dictionary
↓
Output: Hash results dictionary {file_path: (metadata, file_size)}
```

**Implementation Details:**
- Worker threads pull from a shared queue of file paths
- Each worker acquires a slot from CleanSlotTracker for progress visibility
- Hash calculation uses git-aware metadata when available
- Non-git projects fall back to filesystem metadata (mtime, size)
- Results stored in thread-safe dictionary with lock protection

### Phase 2: Parallel File Processing and Vectorization
The second phase processes files through a dual-thread-pool architecture:

```
Hash Results from Phase 1
↓
FileChunkingManager (threadcount+2 workers)
├── Read file content
├── Chunk using FixedSizeChunker
├── Token-aware batching (90% of model limit)
├── Submit to VectorCalculationManager
├── Wait for embeddings
└── Write to Qdrant atomically
    ↓
    VectorCalculationManager (threadcount workers)
    ├── Receive chunk batches
    ├── Calculate embeddings via provider
    ├── Handle rate limiting/throttling
    └── Return vector results
```

**Key Design Principles:**
- **File Atomicity**: All chunks from a file are written to Qdrant together
- **Token-Aware Batching**: Chunks accumulated until approaching token limit (90% safety margin)
- **Pipeline Architecture**: Frontend threads stay ahead of backend to ensure continuous utilization
- **Slot-Based Progress**: Fixed-size array (threadcount+2) for real-time visibility

## Detailed Algorithm Flow

### 1. Initialization Phase
```python
# SmartIndexer initialization
- Load configuration (config.json)
- Initialize embedding provider (VoyageAI or Ollama)
- Connect to Qdrant vector database
- Load progressive metadata for resumability
- Acquire indexing lock (prevents concurrent indexing)
```

### 2. File Discovery
```python
# File finding and filtering
- Scan codebase directory recursively
- Apply file extension filters (e.g., .py, .js, .ts)
- Respect .gitignore patterns
- Apply exclude_dirs configuration
- Check max_file_size limits
- Output: List of absolute file paths
```

### 3. Hash Calculation Phase (Parallel)
```python
# Parallel metadata extraction
for each file in parallel (threadcount+2 workers):
    slot_id = acquire_slot(file_data)
    update_slot(PROCESSING)
    
    if git_repository:
        metadata = {
            'file_hash': calculate_sha256(file),
            'commit_hash': get_git_commit(),
            'branch': get_current_branch(),
            'git_hash': get_git_file_hash(),
            'project_id': get_project_id()
        }
    else:
        metadata = {
            'file_hash': calculate_sha256(file),
            'file_mtime': get_modification_time(),
            'file_size': get_file_size(),
            'project_id': hash(codebase_dir)
        }
    
    store_result(file_path, metadata)
    update_slot(COMPLETE)
    release_slot(slot_id)
```

### 4. File Processing Phase (Parallel)
```python
# FileChunkingManager processing (per file)
for each file_result in parallel:
    slot_id = acquire_slot(file_data)
    
    # Phase 1: Chunking
    update_slot(CHUNKING)
    chunks = FixedSizeChunker.chunk_file(file_path)
    
    # Phase 2: Token-aware batching
    update_slot(VECTORIZING)
    current_batch = []
    current_tokens = 0
    TOKEN_LIMIT = model_limit * 0.9  # 90% safety margin
    
    for chunk in chunks:
        chunk_tokens = count_tokens(chunk.text)
        
        if current_tokens + chunk_tokens > TOKEN_LIMIT and current_batch:
            # Submit current batch
            future = vector_manager.submit_batch(current_batch)
            batch_futures.append(future)
            current_batch = []
            current_tokens = 0
        
        current_batch.append(chunk.text)
        current_tokens += chunk_tokens
    
    # Submit final batch
    if current_batch:
        future = vector_manager.submit_batch(current_batch)
        batch_futures.append(future)
    
    # Phase 3: Wait for embeddings
    update_slot(WAITING)
    embeddings = wait_for_all_futures(batch_futures)
    
    # Phase 4: Atomic write to Qdrant
    update_slot(FINALIZING)
    points = create_qdrant_points(chunks, embeddings, metadata)
    qdrant_client.upsert_batch(points)  # Atomic operation
    
    update_slot(COMPLETE)
    release_slot(slot_id)
```

### 5. Vector Calculation (Backend Pool)
```python
# VectorCalculationManager worker thread
def calculate_vector(task):
    # Check for empty batch
    if not task.chunk_texts:
        return empty_result()
    
    # Dynamic batching for API providers
    if provider == 'voyage-ai':
        embeddings = voyage_client.get_embeddings_batch(
            texts=task.chunk_texts,
            # Internally handles token-aware sub-batching
        )
    elif provider == 'ollama':
        embeddings = ollama_client.get_embeddings_batch(
            texts=task.chunk_texts
        )
    
    return VectorResult(
        embeddings=embeddings,
        processing_time=elapsed,
        metadata=task.metadata
    )
```

### 6. Qdrant Storage
```python
# Point creation and storage
for chunk, embedding in zip(chunks, embeddings):
    point = {
        'id': hash(f"{project_id}_{file_hash}_{chunk_index}"),
        'vector': embedding,
        'payload': {
            'path': file_path,
            'content': chunk.text,
            'language': file_extension,
            'chunk_index': chunk_index,
            'total_chunks': len(chunks),
            'line_start': chunk.line_start,
            'line_end': chunk.line_end,
            'project_id': project_id,
            'file_hash': file_hash,
            # Git metadata or filesystem metadata
        }
    }
    points.append(point)

# Atomic batch write
qdrant_client.upsert_batch(collection_name, points)
```

## Performance Optimizations

### 1. Token-Aware Batching
- **Problem**: VoyageAI API has 120,000 token limit per request
- **Solution**: Dynamic batching with 90% safety margin (108,000 tokens)
- **Implementation**: Accumulate chunks until approaching limit, then submit batch

### 2. Dual Thread Pool Design
- **Frontend Pool**: threadcount+2 workers for file I/O and chunking
- **Backend Pool**: threadcount workers for vector calculations
- **Benefit**: Frontend stays ahead, ensuring backend threads never idle

### 3. Slot-Based Progress Tracking
- **Fixed Array**: threadcount+2 slots for O(1) access
- **Natural Reuse**: Workers acquire/release slots dynamically
- **Real-time Display**: Direct array scanning for UI updates

### 4. File-Level Parallelism
- **Granularity**: Process complete files in parallel, not individual chunks
- **Atomicity**: All chunks from a file written together
- **Efficiency**: Eliminates inter-chunk coordination overhead

### 5. Git-Aware Deduplication
- **Content Hashing**: SHA-256 hash identifies identical files
- **Branch Isolation**: Separate visibility per git branch
- **Incremental Updates**: Only process modified files

## Progress Reporting

### Real-time Metrics
```
Files: 234/567 (41%) | 12.5 files/s | 145.2 KB/s | 14 threads | current_file.py
```

### File Status Progression
```
starting → chunking → vectorizing → waiting → finalizing → complete
```

### Concurrent Files Display
The system maintains visibility of all files being processed simultaneously:
- Each slot shows: filename, size, status, elapsed time
- Updates occur in real-time as workers progress
- Natural slot reuse as files complete and new ones begin

## Resumability and Fault Tolerance

### Progressive Metadata
- **Checkpoint Storage**: Progress saved to metadata.json
- **Resumable State**: Track completed files, remaining queue
- **Crash Recovery**: Resume from last checkpoint on restart

### Cancellation Handling
- **Graceful Shutdown**: Complete in-flight operations
- **File Atomicity**: Never leave partial file data
- **Clean State**: Resumable after cancellation

## Configuration Parameters

### Thread Configuration
```json
{
  "voyage_ai": {
    "parallel_requests": 12  // Backend thread count
  }
}
```
- Frontend threads: parallel_requests + 2
- Backend threads: parallel_requests

### Chunking Configuration
- **Model-aware sizing**: 
  - voyage-code-3: 4096 tokens
  - nomic-embed-text: 2048 tokens
- **Overlap**: Configurable overlap between chunks
- **Line boundaries**: Respect code structure

## Error Handling

### Retry Logic
- **API Failures**: Exponential backoff with jitter
- **Rate Limiting**: Server-driven backoff (Retry-After header)
- **Network Issues**: Configurable max_retries

### Failure Isolation
- **File-level**: Single file failure doesn't stop indexing
- **Chunk-level**: Failed chunks logged, file marked incomplete
- **Recovery**: Failed files retried on next run

## Performance Characteristics

### Throughput Metrics
- **Small files (<10KB)**: 50-100 files/second with parallel processing
- **Medium files (10-100KB)**: 10-50 files/second
- **Large files (>100KB)**: 1-10 files/second
- **Bottlenecks**: Network latency (VoyageAI), CPU (Ollama)

### Resource Usage
- **Memory**: ~100MB base + cache for file content
- **CPU**: Scales with thread count
- **Network**: Batch requests minimize API calls
- **Disk I/O**: Sequential reads, batch writes to Qdrant

## Summary

The Code Indexer's indexing algorithm achieves high throughput through careful architectural decisions:

1. **Two-phase processing** separates metadata extraction from vectorization
2. **Dual thread pools** maintain continuous pipeline flow
3. **Token-aware batching** maximizes API efficiency
4. **File atomicity** ensures data consistency
5. **Slot-based tracking** provides real-time visibility
6. **Progressive metadata** enables resumability

This architecture balances performance, reliability, and user experience to deliver efficient semantic code indexing at scale.