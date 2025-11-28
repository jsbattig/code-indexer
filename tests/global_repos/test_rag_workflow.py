"""
Integration tests for RAG (Retrieval-Augmented Generation) workflow.

Tests AC2 and AC3:
- AC2: Query response includes repo_name, score, snippet
- AC3: Two-step workflow: discovery query → targeted query
"""

import subprocess


from code_indexer.global_repos.global_registry import GlobalRegistry


class TestRAGWorkflow:
    """
    Integration tests for the complete RAG workflow.

    These tests verify that users can:
    1. Query meta-directory to discover relevant repos (AC2)
    2. Use discovered repo_name to perform targeted queries (AC3)
    """

    def test_discovery_query_includes_repo_name_score_snippet(self, tmp_path):
        """
        Test AC2: Query results include repo_name, score, and snippet.

        This verifies the discovery query response format contains all
        fields necessary for RAG workflow decision-making.
        """
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Create a test repo with README
        test_repo = tmp_path / "auth-service"
        test_repo.mkdir()
        (test_repo / "README.md").write_text(
            "# Auth Service\n\nJWT authentication with OAuth2 support."
        )

        # Create .code-indexer/index/ directory (as it would exist in real repo)
        repo_index = test_repo / ".code-indexer" / "index"
        repo_index.mkdir(parents=True)

        # Register the test repo
        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="auth-service",
            alias_name="auth-service-global",
            repo_url="https://github.com/org/auth-service",
            index_path=str(repo_index),
        )

        # Initialize meta-directory
        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        result = subprocess.run(
            ["cidx", "global", "init-meta"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )
        assert result.returncode == 0, f"init-meta failed: {result.stderr}"

        # Initialize and index the meta-directory
        meta_dir = golden_repos_dir / "cidx-meta"

        # Initialize the index
        result = subprocess.run(
            ["cidx", "init"], capture_output=True, text=True, cwd=str(meta_dir)
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Index the meta-directory
        result = subprocess.run(
            ["cidx", "index"], capture_output=True, text=True, cwd=str(meta_dir)
        )
        assert result.returncode == 0, f"Indexing failed: {result.stderr}"

        # Query the meta-directory
        result = subprocess.run(
            [
                "cidx",
                "query",
                "authentication",
                "--repo",
                "cidx-meta-global",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )
        assert result.returncode == 0, f"Query failed: {result.stderr}"

        # Parse output to verify required fields
        output = result.stdout

        # AC2 Verification: Output should contain repo_name
        assert (
            "auth-service" in output
        ), f"Output should contain repo_name\nstdout: {output}\nstderr: {result.stderr}"

        # AC2 Verification: Output should show relevance score
        # (Score format varies, but should have numeric score)
        assert (
            "Score:" in output
            or "score:" in output
            or any(char.isdigit() for char in output)
        ), "Output should contain relevance score"

        # AC2 Verification: Output should contain snippet/description
        assert (
            "JWT" in output or "OAuth2" in output or "Auth Service" in output
        ), "Output should contain description snippet"

    def test_rag_workflow_discovery_to_targeted_query(self, tmp_path):
        """
        Test AC3: Complete RAG workflow from discovery to targeted query.

        This test proves the two-step workflow:
        1. Query meta-directory to discover relevant repos
        2. Use discovered repo to perform targeted query
        """
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Create test repos
        auth_repo = tmp_path / "auth-service"
        auth_repo.mkdir()
        (auth_repo / "README.md").write_text(
            "# Auth Service\n\nJWT token validation and OAuth2 integration."
        )
        (auth_repo / "auth.py").write_text(
            """
def validate_jwt_token(token):
    # Validates JWT token signature and expiration
    pass
"""
        )

        user_repo = tmp_path / "user-management"
        user_repo.mkdir()
        (user_repo / "README.md").write_text(
            "# User Management\n\nUser registration and profile management."
        )

        # Create .code-indexer/index/ directories for both repos
        auth_repo_index = auth_repo / ".code-indexer" / "index"
        auth_repo_index.mkdir(parents=True)
        user_repo_index = user_repo / ".code-indexer" / "index"
        user_repo_index.mkdir(parents=True)

        # Register both repos
        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="auth-service",
            alias_name="auth-service-global",
            repo_url="https://github.com/org/auth",
            index_path=str(auth_repo_index),
        )
        registry.register_global_repo(
            repo_name="user-management",
            alias_name="user-management-global",
            repo_url="https://github.com/org/users",
            index_path=str(user_repo_index),
        )

        # Create aliases for both repos (needed for --repo queries)
        from code_indexer.global_repos.alias_manager import AliasManager

        aliases_dir = golden_repos_dir / "aliases"
        alias_manager = AliasManager(str(aliases_dir))
        alias_manager.create_alias(
            alias_name="auth-service-global",
            target_path=str(auth_repo),
            repo_name="auth-service",
        )
        alias_manager.create_alias(
            alias_name="user-management-global",
            target_path=str(user_repo),
            repo_name="user-management",
        )

        # Initialize and index meta-directory
        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        subprocess.run(
            ["cidx", "global", "init-meta"],
            capture_output=True,
            env={**subprocess.os.environ, **env},
        )

        meta_dir = golden_repos_dir / "cidx-meta"
        subprocess.run(["cidx", "init"], capture_output=True, cwd=str(meta_dir))
        subprocess.run(["cidx", "index"], capture_output=True, cwd=str(meta_dir))

        # STEP 1: Discovery query on meta-directory
        discovery_result = subprocess.run(
            [
                "cidx",
                "query",
                "JWT authentication",
                "--repo",
                "cidx-meta-global",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        assert (
            discovery_result.returncode == 0
        ), f"Discovery query failed: {discovery_result.stderr}"

        # Verify discovery found auth-service
        discovery_output = discovery_result.stdout
        assert (
            "auth-service" in discovery_output
        ), "Discovery should find auth-service repo"

        # STEP 2: Index the discovered repo
        subprocess.run(["cidx", "init"], capture_output=True, cwd=str(auth_repo))
        subprocess.run(["cidx", "index"], capture_output=True, cwd=str(auth_repo))

        # STEP 3: Targeted query using discovered repo alias
        targeted_result = subprocess.run(
            [
                "cidx",
                "query",
                "validate JWT token",
                "--repo",
                "auth-service-global",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        assert (
            targeted_result.returncode == 0
        ), f"Targeted query failed: {targeted_result.stderr}"

        # AC3 Verification: Targeted query should return code from auth-service
        targeted_output = targeted_result.stdout
        assert (
            "validate_jwt_token" in targeted_output or "auth.py" in targeted_output
        ), "Targeted query should find specific code in auth-service"

        # AC3 Verification: Workflow proves discoverability
        # If we can discover the repo AND query it, RAG workflow is functional
        assert len(discovery_output) > 0, "Discovery query should return results"
        assert len(targeted_output) > 0, "Targeted query should return results"

    def test_meta_directory_query_excludes_irrelevant_repos(self, tmp_path):
        """
        Test that discovery query properly filters repos by relevance.

        This ensures the meta-directory serves its purpose: finding
        relevant repos and excluding irrelevant ones.
        """
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Create repos with very different purposes
        auth_repo = tmp_path / "auth-service"
        auth_repo.mkdir()
        (auth_repo / "README.md").write_text(
            "# Auth Service\n\nAuthentication with JWT tokens and OAuth2."
        )

        frontend_repo = tmp_path / "frontend-ui"
        frontend_repo.mkdir()
        (frontend_repo / "README.md").write_text(
            "# Frontend UI\n\nReact components for user interface rendering."
        )

        # Create .code-indexer/index/ directories for both repos
        auth_repo_index = auth_repo / ".code-indexer" / "index"
        auth_repo_index.mkdir(parents=True)
        frontend_repo_index = frontend_repo / ".code-indexer" / "index"
        frontend_repo_index.mkdir(parents=True)

        # Register both repos
        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="auth-service",
            alias_name="auth-service-global",
            repo_url="https://github.com/org/auth",
            index_path=str(auth_repo_index),
        )
        registry.register_global_repo(
            repo_name="frontend-ui",
            alias_name="frontend-ui-global",
            repo_url="https://github.com/org/frontend",
            index_path=str(frontend_repo_index),
        )

        # Initialize and index meta-directory
        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        subprocess.run(
            ["cidx", "global", "init-meta"],
            capture_output=True,
            env={**subprocess.os.environ, **env},
        )

        meta_dir = golden_repos_dir / "cidx-meta"
        subprocess.run(["cidx", "init"], capture_output=True, cwd=str(meta_dir))
        subprocess.run(["cidx", "index"], capture_output=True, cwd=str(meta_dir))

        # Query for authentication - should prioritize auth-service
        result = subprocess.run(
            [
                "cidx",
                "query",
                "JWT token authentication",
                "--repo",
                "cidx-meta-global",
                "--limit",
                "1",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"

        output = result.stdout

        # Verify auth-service is found (highly relevant)
        assert (
            "auth-service" in output
        ), "Discovery should find auth-service for authentication query"

        # Verify frontend-ui is not in top result (less relevant)
        # Note: With limit=1, we should only see the most relevant repo
        # (Results show filenames like auth-service.md, not alias names)
        assert (
            "frontend" not in output.lower()
        ), "With limit=1, should not see less relevant frontend repo"
