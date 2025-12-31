"""
Unit tests for MCP tool output schema documentation.

Tests verify that all 27 MCP tools have complete output schemas
that accurately document the fields returned by their handlers.

Critical API documentation - MCP clients need to know what fields
to expect without guessing.
"""

import pytest
import json
from code_indexer.server.mcp.tools import TOOL_REGISTRY


class TestToolOutputSchemas:
    """Test that all tools have complete output schema documentation."""

    def test_all_tools_have_output_schema(self):
        """Test that every tool in TOOL_REGISTRY has an outputSchema field."""
        tools_without_schema = []

        for tool_name, tool_def in TOOL_REGISTRY.items():
            if "outputSchema" not in tool_def:
                tools_without_schema.append(tool_name)

        assert not tools_without_schema, (
            f"Tools missing outputSchema: {', '.join(tools_without_schema)}\n"
            "ALL 27 tools must have output schema documentation."
        )

    def test_output_schemas_are_valid_json_schema(self):
        """Test that all outputSchema fields are valid JSON schema objects."""
        for tool_name, tool_def in TOOL_REGISTRY.items():
            schema = tool_def.get("outputSchema")

            # Must be a dict
            assert isinstance(schema, dict), f"{tool_name}: outputSchema must be a dict"

            # Must have required JSON schema fields
            assert "type" in schema, f"{tool_name}: outputSchema missing 'type' field"
            assert (
                schema["type"] == "object"
            ), f"{tool_name}: outputSchema type must be 'object'"
            assert (
                "properties" in schema
            ), f"{tool_name}: outputSchema missing 'properties' field"

    def test_search_code_output_schema(self):
        """Test search_code has complete output schema."""
        schema = TOOL_REGISTRY["search_code"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props, "Missing 'success' field"
        assert "results" in props or "error" in props, "Missing result/error fields"

        # Results structure (when success=True)
        if "results" in props:
            results_props = props["results"]["properties"]
            assert "results" in results_props, "Missing nested 'results' array"
            assert "total_results" in results_props, "Missing 'total_results'"
            assert "query_metadata" in results_props, "Missing 'query_metadata'"

            # Query metadata fields
            metadata_props = results_props["query_metadata"]["properties"]
            assert "query_text" in metadata_props
            assert "execution_time_ms" in metadata_props
            assert "repositories_searched" in metadata_props
            assert "timeout_occurred" in metadata_props

    def test_list_repositories_output_schema(self):
        """Test list_repositories has complete output schema with normalized fields."""
        schema = TOOL_REGISTRY["list_repositories"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "repositories" in props

        # Repository item schema (normalized schema)
        repo_items = props["repositories"]["items"]["properties"]

        # CRITICAL: Must document normalized schema fields
        assert "user_alias" in repo_items, "Missing 'user_alias' field"
        assert "golden_repo_alias" in repo_items, "Missing 'golden_repo_alias' field"
        assert "current_branch" in repo_items, "Missing 'current_branch' field"
        assert "is_global" in repo_items, "Missing 'is_global' field"
        assert "repo_url" in repo_items, "Missing 'repo_url' field"
        assert "last_refresh" in repo_items, "Missing 'last_refresh' field"
        assert "index_path" in repo_items, "Missing 'index_path' field"
        assert "created_at" in repo_items, "Missing 'created_at' field"

        # Verify field descriptions are present
        assert "description" in repo_items["user_alias"]
        assert "description" in repo_items["is_global"]

    def test_list_global_repos_output_schema(self):
        """Test list_global_repos has complete output schema."""
        schema = TOOL_REGISTRY["list_global_repos"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "repos" in props

        # Repo item schema (should match normalized schema)
        repo_items = props["repos"]["items"]["properties"]

        # CRITICAL: Must document normalized schema fields
        assert "user_alias" in repo_items
        assert "golden_repo_alias" in repo_items
        assert "is_global" in repo_items
        assert "repo_url" in repo_items
        assert "last_refresh" in repo_items

    def test_get_job_statistics_output_schema(self):
        """Test get_job_statistics has complete output schema."""
        schema = TOOL_REGISTRY["get_job_statistics"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "statistics" in props

        # Statistics fields
        stats_props = props["statistics"]["properties"]
        assert "active" in stats_props, "Missing 'active' count"
        assert "pending" in stats_props, "Missing 'pending' count"
        assert "failed" in stats_props, "Missing 'failed' count"
        assert "total" in stats_props, "Missing 'total' count"

        # Verify field types
        assert stats_props["active"]["type"] == "integer"
        assert stats_props["pending"]["type"] == "integer"
        assert stats_props["failed"]["type"] == "integer"
        assert stats_props["total"]["type"] == "integer"

    def test_activate_repository_output_schema(self):
        """Test activate_repository has complete output schema."""
        schema = TOOL_REGISTRY["activate_repository"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "job_id" in props
        assert "message" in props

        # Verify nullable job_id (can be null on error)
        assert "job_id" in props

    def test_get_file_content_output_schema(self):
        """Test get_file_content has complete output schema with content array."""
        schema = TOOL_REGISTRY["get_file_content"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "content" in props
        assert "metadata" in props

        # Content must be array of content blocks
        assert props["content"]["type"] == "array"
        content_items = props["content"]["items"]["properties"]
        assert "type" in content_items
        assert "text" in content_items

    def test_check_health_output_schema(self):
        """Test check_health has complete output schema."""
        schema = TOOL_REGISTRY["check_health"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "health" in props

        # Health fields (should match HealthResponse model)
        health_props = props["health"]["properties"]
        assert "status" in health_props
        assert "checks" in health_props
        assert "timestamp" in health_props

    def test_list_files_output_schema(self):
        """Test list_files has complete output schema."""
        schema = TOOL_REGISTRY["list_files"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "files" in props

        # File items schema
        file_items = props["files"]["items"]["properties"]
        assert "path" in file_items
        assert "size_bytes" in file_items
        assert "modified_at" in file_items

    def test_get_branches_output_schema(self):
        """Test get_branches has complete output schema."""
        schema = TOOL_REGISTRY["get_branches"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "branches" in props

        # Branch items schema
        branch_items = props["branches"]["items"]["properties"]
        assert "name" in branch_items
        assert "is_current" in branch_items
        assert "last_commit" in branch_items

        # Last commit nested fields
        commit_props = branch_items["last_commit"]["properties"]
        assert "sha" in commit_props
        assert "message" in commit_props
        assert "author" in commit_props
        assert "date" in commit_props

    def test_list_users_output_schema(self):
        """Test list_users has complete output schema."""
        schema = TOOL_REGISTRY["list_users"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "users" in props
        assert "total" in props

        # User items schema
        user_items = props["users"]["items"]["properties"]
        assert "username" in user_items
        assert "role" in user_items
        assert "created_at" in user_items

    def test_add_golden_repo_output_schema(self):
        """Test add_golden_repo has complete output schema."""
        schema = TOOL_REGISTRY["add_golden_repo"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "job_id" in props
        assert "message" in props

    def test_global_repo_status_output_schema(self):
        """Test global_repo_status has complete output schema."""
        schema = TOOL_REGISTRY["global_repo_status"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        # Note: handler returns {...status} which spreads fields
        # Schema should document the flattened structure

    def test_get_repository_statistics_output_schema(self):
        """Test get_repository_statistics has complete output schema."""
        schema = TOOL_REGISTRY["get_repository_statistics"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "statistics" in props

        # Statistics should document StatsResponse model fields

    def test_discover_repositories_output_schema(self):
        """Test discover_repositories has complete output schema."""
        schema = TOOL_REGISTRY["discover_repositories"]["outputSchema"]
        props = schema["properties"]

        # Top-level fields
        assert "success" in props
        assert "repositories" in props

    def test_all_schemas_document_success_field(self):
        """Test that all output schemas document the 'success' field."""
        for tool_name, tool_def in TOOL_REGISTRY.items():
            schema = tool_def.get("outputSchema", {})
            props = schema.get("properties", {})

            assert (
                "success" in props
            ), f"{tool_name}: Missing 'success' field in output schema"
            assert (
                props["success"]["type"] == "boolean"
            ), f"{tool_name}: 'success' field must be boolean"

    def test_all_schemas_document_error_field(self):
        """Test that all output schemas document the 'error' field for failures."""
        for tool_name, tool_def in TOOL_REGISTRY.items():
            schema = tool_def.get("outputSchema", {})
            props = schema.get("properties", {})

            # Every schema should document 'error' field
            # (present when success=False)
            assert (
                "error" in props
            ), f"{tool_name}: Missing 'error' field in output schema"
            assert (
                props["error"]["type"] == "string"
            ), f"{tool_name}: 'error' field must be string"

    def test_schema_descriptions_are_meaningful(self):
        """Test that field descriptions are meaningful, not just field names."""
        for tool_name, tool_def in TOOL_REGISTRY.items():
            schema = tool_def.get("outputSchema", {})
            props = schema.get("properties", {})

            for field_name, field_schema in props.items():
                if "description" in field_schema:
                    desc = field_schema["description"]

                    # Description should be more than just the field name
                    assert len(desc) > len(
                        field_name
                    ), f"{tool_name}.{field_name}: Description too short"

                    # Description should not just be title-cased field name
                    assert desc.lower() != field_name.replace(
                        "_", " "
                    ), f"{tool_name}.{field_name}: Description is just field name"


class TestOutputSchemaCompleteness:
    """Test that output schemas match actual handler responses."""

    @pytest.mark.asyncio
    async def test_search_code_schema_matches_handler_response(self):
        """Test that search_code output schema matches actual handler response structure."""
        from code_indexer.server.mcp.handlers import search_code
        from code_indexer.server.auth.user_manager import User, UserRole
        from unittest.mock import Mock, patch

        # Mock user
        user = Mock(spec=User)
        user.username = "testuser"
        user.role = UserRole.NORMAL_USER

        # Mock params
        params = {
            "query_text": "authentication",
            "limit": 5,
        }

        # Mock handler dependencies
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "authentication",
                    "execution_time_ms": 100,
                    "repositories_searched": 0,
                    "timeout_occurred": False,
                },
            }

            # Execute handler
            result = await search_code(params, user)

            # Parse response
            response_data = json.loads(result["content"][0]["text"])

            # Get schema
            TOOL_REGISTRY["search_code"]["outputSchema"]

            # Verify response matches schema structure
            assert "success" in response_data
            assert "results" in response_data or "error" in response_data

            # If successful, verify results structure
            if response_data.get("success"):
                results = response_data["results"]
                assert "results" in results
                assert "total_results" in results
                assert "query_metadata" in results
                assert "query_text" in results["query_metadata"]
                assert "execution_time_ms" in results["query_metadata"]

    @pytest.mark.asyncio
    async def test_list_repositories_schema_matches_handler_response(self):
        """Test that list_repositories output schema matches actual handler response."""
        from code_indexer.server.mcp.handlers import list_repositories
        from code_indexer.server.auth.user_manager import User, UserRole
        from unittest.mock import Mock, patch, MagicMock

        # Mock user
        user = Mock(spec=User)
        user.username = "testuser"
        user.role = UserRole.NORMAL_USER

        # Mock activated repos (should not have is_global or it should be false/missing)
        activated_repos = [
            {
                "user_alias": "my-repo",
                "golden_repo_alias": "test-repo",
                "current_branch": "main",
            }
        ]

        # Mock global repos
        global_repos = [
            {
                "alias_name": "global-repo-global",
                "repo_name": "global-repo",
                "repo_url": "https://example.com/repo.git",
                "last_refresh": "2025-11-30T10:00:00Z",
                "index_path": "/path/to/index",
                "created_at": "2025-11-30T09:00:00Z",
            }
        ]

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.activated_repo_manager.list_activated_repositories.return_value = (
                activated_repos
            )

            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = global_repos

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                # Execute handler
                result = await list_repositories({}, user)

                # Parse response
                response_data = json.loads(result["content"][0]["text"])

                # Verify response matches schema
                assert "success" in response_data
                assert "repositories" in response_data

                # Verify repository items have normalized fields
                for repo in response_data["repositories"]:
                    assert "user_alias" in repo
                    assert "golden_repo_alias" in repo

                    # Either has current_branch (activated) or is_global=True (global)
                    assert "current_branch" in repo or repo.get("is_global") is True

                    # Global repos have additional fields
                    if repo.get("is_global") is True:
                        assert "repo_url" in repo
                        assert "last_refresh" in repo
                        assert "index_path" in repo

    @pytest.mark.asyncio
    async def test_get_job_statistics_schema_matches_handler_response(self):
        """Test that get_job_statistics output schema matches actual handler response."""
        from code_indexer.server.mcp.handlers import get_job_statistics
        from code_indexer.server.auth.user_manager import User
        from unittest.mock import Mock, patch

        # Mock user
        user = Mock(spec=User)
        user.username = "testuser"

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.background_job_manager.get_active_job_count.return_value = 2
            mock_app.background_job_manager.get_pending_job_count.return_value = 5
            mock_app.background_job_manager.get_failed_job_count.return_value = 1

            # Execute handler
            result = await get_job_statistics({}, user)

            # Parse response
            response_data = json.loads(result["content"][0]["text"])

            # Verify response matches schema
            assert "success" in response_data
            assert "statistics" in response_data

            stats = response_data["statistics"]
            assert "active" in stats
            assert "pending" in stats
            assert "failed" in stats
            assert "total" in stats

            # Verify types
            assert isinstance(stats["active"], int)
            assert isinstance(stats["pending"], int)
            assert isinstance(stats["failed"], int)
            assert isinstance(stats["total"], int)

            # Verify calculation
            assert (
                stats["total"] == stats["active"] + stats["pending"] + stats["failed"]
            )


class TestSearchCodeTemporalFields:
    """Test search_code output schema includes all temporal fields (Issue Fix)."""

    def test_search_code_schema_documents_source_repo_field(self):
        """Verify source_repo field is documented in search_code output schema."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["search_code"]["outputSchema"]
        result_items_schema = schema["properties"]["results"]["properties"]["results"][
            "items"
        ]

        # Should have source_repo field documented
        assert (
            "source_repo" in result_items_schema["properties"]
        ), "search_code output schema missing source_repo field (for composite repos)"

        source_repo_prop = result_items_schema["properties"]["source_repo"]
        assert source_repo_prop["type"] in [
            ["string", "null"],
            "string",
            ["null", "string"],
        ], f"source_repo should be string|null type, got {source_repo_prop.get('type')}"
        assert "description" in source_repo_prop, "source_repo should have description"
        assert (
            "composite" in source_repo_prop["description"].lower()
        ), "source_repo description should mention composite repositories"

    def test_search_code_schema_documents_temporal_context_field(self):
        """Verify temporal_context field is documented in search_code output schema."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["search_code"]["outputSchema"]
        result_items_schema = schema["properties"]["results"]["properties"]["results"][
            "items"
        ]

        # Should have temporal_context field documented
        assert (
            "temporal_context" in result_items_schema["properties"]
        ), "search_code output schema missing temporal_context field"

        temporal_prop = result_items_schema["properties"]["temporal_context"]
        assert temporal_prop["type"] in [
            ["object", "null"],
            "object",
            ["null", "object"],
        ], f"temporal_context should be object|null type, got {temporal_prop.get('type')}"
        assert (
            "description" in temporal_prop
        ), "temporal_context should have description"

        # Verify nested fields are documented
        if "properties" in temporal_prop:
            expected_fields = [
                "first_seen",
                "last_seen",
                "commit_count",
                "commits",
                "is_removed",
            ]
            for field in expected_fields:
                assert (
                    field in temporal_prop["properties"]
                ), f"temporal_context missing nested field: {field}"

    def test_search_code_schema_documents_timestamp_fields(self):
        """Verify timestamp fields are documented in search_code output schema."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["search_code"]["outputSchema"]
        result_items_schema = schema["properties"]["results"]["properties"]["results"][
            "items"
        ]

        # Should have file_last_modified
        assert (
            "file_last_modified" in result_items_schema["properties"]
        ), "search_code output schema missing file_last_modified field"

        # Should have indexed_timestamp
        assert (
            "indexed_timestamp" in result_items_schema["properties"]
        ), "search_code output schema missing indexed_timestamp field"

        # Both should be number type
        file_mod_type = result_items_schema["properties"]["file_last_modified"]["type"]
        assert file_mod_type in [
            "number",
            ["number", "null"],
            ["null", "number"],
        ], f"file_last_modified should be number|null type, got {file_mod_type}"

        indexed_type = result_items_schema["properties"]["indexed_timestamp"]["type"]
        assert indexed_type in [
            "number",
            ["number", "null"],
            ["null", "number"],
        ], f"indexed_timestamp should be number|null type, got {indexed_type}"


class TestGlobalRepoStatusOutputSchema:
    """Test global_repo_status output schema documents actual flattened fields (Issue Fix)."""

    def test_global_repo_status_schema_documents_all_fields(self):
        """Verify global_repo_status schema documents all fields from get_status()."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["global_repo_status"]["outputSchema"]

        # Schema should document actual fields, not just success/error
        expected_fields = [
            "success",
            "error",
            "alias",
            "repo_name",
            "url",
            "last_refresh",
        ]

        props = schema["properties"]
        for field in expected_fields:
            assert field in props, f"global_repo_status schema missing field: {field}"

        # Verify field types
        assert (
            props["alias"]["type"] == "string"
        ), f"alias should be string, got {props['alias'].get('type')}"
        assert (
            props["repo_name"]["type"] == "string"
        ), f"repo_name should be string, got {props['repo_name'].get('type')}"
        assert (
            props["url"]["type"] == "string"
        ), f"url should be string, got {props['url'].get('type')}"
        assert props["last_refresh"]["type"] in [
            "string",
            ["string", "null"],
            ["null", "string"],
        ], f"last_refresh should be string|null, got {props['last_refresh'].get('type')}"


class TestGetGlobalConfigOutputSchema:
    """Test get_global_config output schema documents actual config fields (Issue Fix)."""

    def test_get_global_config_schema_documents_refresh_interval(self):
        """Verify get_global_config schema documents refresh_interval field."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["get_global_config"]["outputSchema"]

        # Should have refresh_interval documented
        assert (
            "refresh_interval" in schema["properties"]
        ), "get_global_config schema missing refresh_interval field"

        refresh_prop = schema["properties"]["refresh_interval"]
        assert (
            refresh_prop["type"] == "integer"
        ), f"refresh_interval should be integer type, got {refresh_prop.get('type')}"
        assert "description" in refresh_prop, "refresh_interval should have description"


class TestGetRepositoryStatisticsOutputSchema:
    """Test get_repository_statistics output schema expands RepositoryStatsResponse (Issue Fix)."""

    def test_repository_statistics_schema_documents_all_nested_fields(self):
        """Verify statistics schema documents all RepositoryStatsResponse fields."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["get_repository_statistics"]["outputSchema"]
        stats_props = schema["properties"]["statistics"]["properties"]

        # Should have repository_id
        assert "repository_id" in stats_props, "statistics schema missing repository_id"

        # Should have files object with nested fields
        assert "files" in stats_props, "statistics schema missing files"
        files_props = stats_props["files"]["properties"]
        assert "total" in files_props, "files missing total field"
        assert "indexed" in files_props, "files missing indexed field"
        assert "by_language" in files_props, "files missing by_language field"

        # Should have storage object with nested fields
        assert "storage" in stats_props, "statistics schema missing storage"
        storage_props = stats_props["storage"]["properties"]
        assert (
            "repository_size_bytes" in storage_props
        ), "storage missing repository_size_bytes"
        assert "index_size_bytes" in storage_props, "storage missing index_size_bytes"
        assert "embedding_count" in storage_props, "storage missing embedding_count"

        # Should have activity object with nested fields
        assert "activity" in stats_props, "statistics schema missing activity"
        activity_props = stats_props["activity"]["properties"]
        assert "created_at" in activity_props, "activity missing created_at"
        assert "last_sync_at" in activity_props, "activity missing last_sync_at"
        assert "last_accessed_at" in activity_props, "activity missing last_accessed_at"
        assert "sync_count" in activity_props, "activity missing sync_count"

        # Should have health object with nested fields
        assert "health" in stats_props, "statistics schema missing health"
        health_props = stats_props["health"]["properties"]
        assert "score" in health_props, "health missing score"
        assert "issues" in health_props, "health missing issues"


class TestGetRepositoryStatusOutputSchema:
    """Test get_repository_status output schema documents actual status fields (Issue Fix)."""

    def test_repository_status_schema_documents_all_fields(self):
        """Verify status schema documents all fields from get_repository_details()."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["get_repository_status"]["outputSchema"]
        status_props = schema["properties"]["status"]["properties"]

        # Expected fields from get_repository_details()
        expected_fields = [
            "alias",
            "repo_url",
            "default_branch",
            "clone_path",
            "created_at",
            "activation_status",
            "branches_list",
            "file_count",
            "index_size",
            "last_updated",
            "enable_temporal",
            "temporal_status",
        ]

        for field in expected_fields:
            assert (
                field in status_props
            ), f"get_repository_status schema missing field: {field}"

        # Verify temporal_status has nested structure
        temporal_status_prop = status_props["temporal_status"]
        assert temporal_status_prop["type"] in [
            ["object", "null"],
            "object",
            ["null", "object"],
        ], f"temporal_status should be object|null, got {temporal_status_prop.get('type')}"
        if "properties" in temporal_status_prop:
            assert (
                "enabled" in temporal_status_prop["properties"]
            ), "temporal_status missing enabled"
            assert (
                "diff_context" in temporal_status_prop["properties"]
            ), "temporal_status missing diff_context"


class TestDiscoverRepositoriesOutputSchema:
    """Test discover_repositories output schema documents actual repository fields (Issue Fix)."""

    def test_discover_repositories_schema_documents_golden_repo_fields(self):
        """Verify discover_repositories schema documents fields from GoldenRepository.to_dict()."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["discover_repositories"]["outputSchema"]
        repo_items = schema["properties"]["repositories"]["items"]

        # Should document actual golden repo fields
        expected_fields = [
            "alias",
            "repo_url",
            "default_branch",
            "clone_path",
            "created_at",
            "enable_temporal",
            "temporal_options",
        ]

        # Schema should either have full properties or clear description
        assert (
            "properties" in repo_items or "description" in repo_items
        ), "discover_repositories items should have properties or detailed description"

        if "properties" in repo_items:
            repo_props = repo_items["properties"]
            for field in expected_fields:
                assert (
                    field in repo_props
                ), f"discover_repositories schema missing field: {field}"
