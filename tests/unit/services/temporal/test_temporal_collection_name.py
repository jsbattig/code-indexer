"""Test for temporal collection name bug.

Root cause: TemporalIndexer stores vectors with collection_name=None,
which goes to default collection, but TemporalSearchService searches
'code-indexer-temporal' collection.
"""



def test_temporal_indexer_collection_name_hardcoded():
    """Verify TemporalIndexer uses hardcoded temporal collection name.

    BUG REPRODUCTION:
    1. TemporalIndexer.index_commits() line 284: upsert_points(collection_name=None)
    2. This stores in DEFAULT collection (voyage-code-3)
    3. TemporalSearchService.query_temporal() line 172: searches 'code-indexer-temporal'
    4. Result: 0 results because searching wrong collection

    FIX:
    - TemporalIndexer must have TEMPORAL_COLLECTION_NAME = "code-indexer-temporal"
    - Pass this to upsert_points() instead of None
    - Both indexer and search service must use same constant
    """
    from code_indexer.services.temporal.temporal_indexer import TemporalIndexer

    # ASSERTION 1: TemporalIndexer must have temporal collection name constant
    assert hasattr(
        TemporalIndexer, "TEMPORAL_COLLECTION_NAME"
    ), "TemporalIndexer must define TEMPORAL_COLLECTION_NAME constant"

    # ASSERTION 2: TemporalSearchService must use same collection name
    indexer_collection = TemporalIndexer.TEMPORAL_COLLECTION_NAME
    search_collection = "code-indexer-temporal"  # Hardcoded in line 172

    assert indexer_collection == search_collection, (
        f"Collection name mismatch: "
        f"TemporalIndexer uses '{indexer_collection}', "
        f"TemporalSearchService uses '{search_collection}'"
    )

    # ASSERTION 3: Must contain 'temporal' to distinguish from HEAD collection
    assert "temporal" in indexer_collection.lower(), (
        f"Collection name must contain 'temporal', got: {indexer_collection}"
    )


def test_temporal_search_service_collection_name():
    """Verify TemporalSearchService uses correct collection name for queries."""
    from code_indexer.services.temporal.temporal_search_service import (
        TemporalSearchService,
    )

    # Check that search service has collection name configuration
    # This will fail until we add the constant
    assert hasattr(
        TemporalSearchService, "TEMPORAL_COLLECTION_NAME"
    ), "TemporalSearchService should define TEMPORAL_COLLECTION_NAME constant"

    # Verify it matches what indexer uses
    assert (
        TemporalSearchService.TEMPORAL_COLLECTION_NAME == "code-indexer-temporal"
    ), "Search service collection name must be 'code-indexer-temporal'"
