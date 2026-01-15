"""
Multi-repository search module.

Provides parallel search execution across multiple repositories with
proper timeout handling and result aggregation.

Includes:
- Multi-repository semantic/FTS/regex/temporal search
- Multi-repository SCIP intelligence (definitions, references, dependencies, dependents, callchains)
"""

from .multi_search_config import MultiSearchConfig
from .multi_result_aggregator import MultiResultAggregator
from .multi_search_service import MultiSearchService
from .models import MultiSearchRequest, MultiSearchResponse, MultiSearchMetadata
from .scip_models import (
    SCIPMultiRequest,
    SCIPMultiResponse,
    SCIPMultiMetadata,
    SCIPResult,
)
from .scip_multi_service import SCIPMultiService

__all__ = [
    "MultiSearchConfig",
    "MultiResultAggregator",
    "MultiSearchService",
    "MultiSearchRequest",
    "MultiSearchResponse",
    "MultiSearchMetadata",
    "SCIPMultiRequest",
    "SCIPMultiResponse",
    "SCIPMultiMetadata",
    "SCIPResult",
    "SCIPMultiService",
]
