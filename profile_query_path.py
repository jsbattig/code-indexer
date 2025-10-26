#!/usr/bin/env python3
"""Deep profiling of the query command path."""

import time
import sys
from pathlib import Path

print("="*70)
print("QUERY PATH DEEP ANALYSIS")
print("="*70)

# Phase 1: CLI Entry Point
print("\n[PHASE 1: CLI ENTRY POINT]")
start = time.perf_counter()
import src.code_indexer.cli as cli_module
cli_time = (time.perf_counter() - start) * 1000
print(f"✓ cli.py import:        {cli_time:8.2f}ms")

# Phase 2: Query command imports (local mode path)
print("\n[PHASE 2: QUERY COMMAND DEPENDENCIES]")

# Config and basic setup
start = time.perf_counter()
from src.code_indexer.config import ConfigManager, Config
elapsed = (time.perf_counter() - start) * 1000
print(f"✓ ConfigManager:        {elapsed:8.2f}ms")

# Services needed for query
start = time.perf_counter()
from src.code_indexer.services import EmbeddingProviderFactory
elapsed = (time.perf_counter() - start) * 1000
print(f"✓ EmbeddingFactory:     {elapsed:8.2f}ms")

start = time.perf_counter()
from src.code_indexer.backends.backend_factory import BackendFactory
elapsed = (time.perf_counter() - start) * 1000
print(f"✓ BackendFactory:       {elapsed:8.2f}ms")

start = time.perf_counter()
from src.code_indexer.services.generic_query_service import GenericQueryService
elapsed = (time.perf_counter() - start) * 1000
print(f"✓ GenericQueryService:  {elapsed:8.2f}ms")

start = time.perf_counter()
from src.code_indexer.services.language_mapper import LanguageMapper
elapsed = (time.perf_counter() - start) * 1000
print(f"✓ LanguageMapper:       {elapsed:8.2f}ms")

start = time.perf_counter()
from src.code_indexer.services.language_validator import LanguageValidator
elapsed = (time.perf_counter() - start) * 1000
print(f"✓ LanguageValidator:    {elapsed:8.2f}ms")

start = time.perf_counter()
from src.code_indexer.services.git_topology_service import GitTopologyService
elapsed = (time.perf_counter() - start) * 1000
print(f"✓ GitTopologyService:   {elapsed:8.2f}ms")

# Phase 3: Imports NOT needed for query
print("\n[PHASE 3: UNNECESSARY IMPORTS (loaded but not used for query)]")

# Check what cli.py imports that query doesn't use
start = time.perf_counter()
from src.code_indexer.services.smart_indexer import SmartIndexer
elapsed = (time.perf_counter() - start) * 1000
print(f"✗ SmartIndexer:         {elapsed:8.2f}ms  ← NOT NEEDED for query")

start = time.perf_counter()
from src.code_indexer.services.claude_integration import ClaudeIntegrationService
elapsed = (time.perf_counter() - start) * 1000
print(f"✗ ClaudeIntegration:    {elapsed:8.2f}ms  ← NOT NEEDED for query")

start = time.perf_counter()
from src.code_indexer.services.config_fixer import ConfigurationRepairer
elapsed = (time.perf_counter() - start) * 1000
print(f"✗ ConfigFixer:          {elapsed:8.2f}ms  ← NOT NEEDED for query")

start = time.perf_counter()
from src.code_indexer.remote.credential_manager import ProjectCredentialManager
elapsed = (time.perf_counter() - start) * 1000
print(f"✗ CredentialManager:    {elapsed:8.2f}ms  ← NOT NEEDED for query")

start = time.perf_counter()
from src.code_indexer.api_clients.repos_client import ReposAPIClient
elapsed = (time.perf_counter() - start) * 1000
print(f"✗ ReposAPIClient:       {elapsed:8.2f}ms  ← NOT NEEDED for query")

start = time.perf_counter()
from src.code_indexer.api_clients.admin_client import AdminAPIClient
elapsed = (time.perf_counter() - start) * 1000
print(f"✗ AdminAPIClient:       {elapsed:8.2f}ms  ← NOT NEEDED for query")

# Phase 4: Backend-specific imports (FilesystemVectorStore vs QdrantClient)
print("\n[PHASE 4: BACKEND IMPORTS]")

start = time.perf_counter()
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
elapsed = (time.perf_counter() - start) * 1000
print(f"✓ FilesystemVectorStore: {elapsed:8.2f}ms")

# Phase 5: What happens at runtime
print("\n[PHASE 5: RUNTIME OPERATIONS]")
print("The following happens when query actually executes:")
print("  1. Load config (ConfigManager.load())")
print("  2. Create embedding provider (EmbeddingProviderFactory.create())")
print("  3. Create backend (BackendFactory.create())")
print("  4. Health checks (embedding_provider.health_check(), vector_store.health_check())")
print("  5. HNSW index loading (~600ms for filesystem backend)")
print("  6. Query embedding generation (varies by provider)")
print("  7. Vector similarity search")
print("  8. Post-filtering and result ranking")

print("\n" + "="*70)
print("QUERY PATH OPTIMIZATION OPPORTUNITIES")
print("="*70)

print("\n🔴 BIGGEST ISSUES:")
print(f"  1. cli.py loads {cli_time:.0f}ms of unnecessary services")
print("  2. Services loaded at module level, even for --help")
print("  3. SmartIndexer, ClaudeIntegration, etc. not needed for query")

print("\n💡 OPTIMIZATION STRATEGY:")
print("  Phase 1: Move query-specific imports inside query command")
print("  Phase 2: Lazy load SmartIndexer, ClaudeIntegration, etc.")
print("  Phase 3: Keep only Click, rich, config at module level")

print("\n📊 POTENTIAL SAVINGS:")
print("  Current query startup: ~400ms (cli.py + services)")
print("  Optimized query startup: ~150ms (essential services only)")
print("  Savings: ~250ms per query invocation")

print("\n✅ WHAT TO KEEP AT MODULE LEVEL:")
print("  - click (11ms)")
print("  - rich.console (minimal)")
print("  - Basic config structures")
print("  - Command decorators")

print("\n❌ WHAT TO LAZY LOAD IN QUERY COMMAND:")
print("  - BackendFactory (load when query runs)")
print("  - EmbeddingProviderFactory (load when query runs)")
print("  - GenericQueryService (load when query runs)")
print("  - GitTopologyService (load when query runs)")
print("  - All validation/mapping services (load when query runs)")
