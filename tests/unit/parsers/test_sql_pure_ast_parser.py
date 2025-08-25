"""
Tests for SQL pure AST-based parser - TDD approach.

These tests demonstrate the expected behavior of a SQL parser that uses ONLY
tree-sitter AST analysis and eliminates ALL regex-based parsing on AST node text.

CRITICAL: These tests are designed to FAIL initially to demonstrate TDD approach.
They define the expected behavior of the pure AST implementation.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.sql_parser import SQLSemanticParser


class TestSQLPureASTParser:
    """Tests for pure AST-based SQL parsing - eliminating regex abuse."""

    @pytest.fixture
    def parser(self):
        """Create a SQL parser configured for pure AST parsing."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SQLSemanticParser(config)

    def test_create_table_pure_ast_detection(self, parser):
        """Test CREATE TABLE detection using only AST node types (no regex)."""
        content = dedent(
            """
            CREATE TABLE users (
                id INT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                email VARCHAR(100) UNIQUE
            );
            
            CREATE TABLE posts (
                id INT PRIMARY KEY,
                user_id INT,
                title VARCHAR(200),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """
        ).strip()

        chunks = parser.chunk(content, "tables.sql")

        # Verify pure AST detection worked
        table_chunks = [c for c in chunks if c.semantic_type == "table"]
        assert len(table_chunks) == 2

        # Verify table names extracted via AST structure
        table_names = {c.semantic_name for c in table_chunks}
        assert "users" in table_names
        assert "posts" in table_names

        # Verify AST-based column extraction
        users_table = next(c for c in table_chunks if c.semantic_name == "users")
        assert users_table.semantic_context.get("columns") is not None

        # Verify no regex fallback was used
        for chunk in table_chunks:
            context = chunk.semantic_context
            assert context.get("regex_fallback") is not True  # Should be AST-based

    def test_create_view_pure_ast_detection(self, parser):
        """Test CREATE VIEW detection using only AST node types."""
        content = dedent(
            """
            CREATE VIEW active_users AS
            SELECT id, username, email 
            FROM users 
            WHERE created_at > NOW() - INTERVAL 30 DAY;
            
            CREATE OR REPLACE VIEW user_stats AS
            SELECT username, COUNT(p.id) as post_count
            FROM users u
            LEFT JOIN posts p ON u.id = p.user_id
            GROUP BY username;
        """
        ).strip()

        chunks = parser.chunk(content, "views.sql")

        # Verify AST-based view detection
        view_chunks = [c for c in chunks if c.semantic_type == "view"]
        assert len(view_chunks) == 2

        view_names = {c.semantic_name for c in view_chunks}
        assert "active_users" in view_names
        assert "user_stats" in view_names

        # Verify AST extraction (not regex)
        for chunk in view_chunks:
            assert chunk.semantic_context.get("regex_fallback") is not True

    def test_create_procedure_pure_ast_detection(self, parser):
        """Test CREATE PROCEDURE detection using only AST analysis."""
        content = dedent(
            """
            DELIMITER //

            CREATE PROCEDURE GetUserPosts(IN userId INT)
            BEGIN
                SELECT p.*, u.username
                FROM posts p
                JOIN users u ON p.user_id = u.id
                WHERE p.user_id = userId;
            END //

            CREATE OR REPLACE PROCEDURE UpdateUserStats(
                IN user_id INT,
                OUT total_posts INT
            )
            BEGIN
                SELECT COUNT(*) INTO total_posts FROM posts WHERE user_id = user_id;
            END //

            DELIMITER ;
        """
        ).strip()

        chunks = parser.chunk(content, "procedures.sql")

        # Even with tree-sitter ERROR nodes, should extract via AST structure
        proc_chunks = [c for c in chunks if c.semantic_type == "procedure"]
        assert len(proc_chunks) >= 2

        proc_names = {c.semantic_name for c in proc_chunks}
        assert "GetUserPosts" in proc_names
        assert "UpdateUserStats" in proc_names

        # Verify parameter extraction via AST (not regex)
        get_posts_proc = next(
            c for c in proc_chunks if c.semantic_name == "GetUserPosts"
        )
        if get_posts_proc.semantic_context.get("parameters"):
            # Should be extracted from AST structure, not regex patterns
            assert "IN userId INT" in get_posts_proc.semantic_context["parameters"]

    def test_create_function_pure_ast_detection(self, parser):
        """Test CREATE FUNCTION detection using only AST analysis."""
        content = dedent(
            """
            CREATE FUNCTION CalculateAge(birthdate DATE) 
            RETURNS INT
            DETERMINISTIC
            BEGIN
                RETURN TIMESTAMPDIFF(YEAR, birthdate, CURDATE());
            END;

            CREATE OR REPLACE FUNCTION GetFullName(
                first_name VARCHAR(50),
                last_name VARCHAR(50)
            )
            RETURNS VARCHAR(101)
            BEGIN
                RETURN CONCAT(first_name, ' ', last_name);
            END;
        """
        ).strip()

        chunks = parser.chunk(content, "functions.sql")

        # Should detect functions via AST even in ERROR nodes
        func_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(func_chunks) >= 2

        func_names = {c.semantic_name for c in func_chunks}
        assert "CalculateAge" in func_names
        assert "GetFullName" in func_names

        # Verify return type extraction via AST
        calc_age_func = next(
            c for c in func_chunks if c.semantic_name == "CalculateAge"
        )
        if calc_age_func.semantic_context.get("return_type"):
            assert calc_age_func.semantic_context["return_type"] == "INT"

    def test_create_index_pure_ast_detection(self, parser):
        """Test CREATE INDEX detection using only AST node types."""
        content = dedent(
            """
            CREATE INDEX idx_users_email ON users(email);
            CREATE UNIQUE INDEX idx_users_username ON users(username);
            CREATE INDEX idx_posts_user_created ON posts(user_id, created_at DESC);
        """
        ).strip()

        chunks = parser.chunk(content, "indexes.sql")

        # Should detect via create_index AST node type
        index_chunks = [c for c in chunks if c.semantic_type == "index"]
        assert len(index_chunks) == 3

        index_names = {c.semantic_name for c in index_chunks}
        assert "idx_users_email" in index_names
        assert "idx_users_username" in index_names
        assert "idx_posts_user_created" in index_names

        # Verify table name extraction via AST structure
        email_index = next(
            c for c in index_chunks if c.semantic_name == "idx_users_email"
        )
        assert email_index.semantic_context.get("table_name") == "users"

    def test_select_statement_pure_ast_detection(self, parser):
        """Test SELECT statement detection using only AST node types."""
        content = dedent(
            """
            SELECT * FROM users WHERE active = 1;

            SELECT u.username, p.title, p.created_at
            FROM users u
            INNER JOIN posts p ON u.id = p.user_id
            WHERE p.published = TRUE
            ORDER BY p.created_at DESC
            LIMIT 10;
        """
        ).strip()

        chunks = parser.chunk(content, "selects.sql")

        # Should detect via 'select' AST node type
        select_chunks = [c for c in chunks if c.semantic_type == "select"]
        assert len(select_chunks) == 2

        # Verify table extraction via AST traversal of 'from' nodes
        for chunk in select_chunks:
            tables = chunk.semantic_context.get("tables", [])
            assert len(tables) >= 1
            assert any(table in ["users", "posts"] for table in tables)

    def test_dml_statements_pure_ast_detection(self, parser):
        """Test INSERT, UPDATE, DELETE detection using only AST node types."""
        content = dedent(
            """
            INSERT INTO users (username, email) 
            VALUES ('john_doe', 'john@example.com');

            UPDATE users 
            SET updated_at = NOW() 
            WHERE id = 1;

            DELETE FROM posts 
            WHERE published = FALSE;
        """
        ).strip()

        chunks = parser.chunk(content, "dml.sql")

        # Should detect via AST node types: insert, update, delete
        insert_chunks = [c for c in chunks if c.semantic_type == "insert"]
        update_chunks = [c for c in chunks if c.semantic_type == "update"]
        delete_chunks = [c for c in chunks if c.semantic_type == "delete"]

        assert len(insert_chunks) == 1
        assert len(update_chunks) == 1
        assert len(delete_chunks) == 1

        # Verify table name extraction via AST structure
        insert_chunk = insert_chunks[0]
        assert insert_chunk.semantic_context.get("table_name") == "users"

        update_chunk = update_chunks[0]
        assert update_chunk.semantic_context.get("table_name") == "users"

        delete_chunk = delete_chunks[0]
        assert delete_chunk.semantic_context.get("table_name") == "posts"

    def test_cte_pure_ast_detection(self, parser):
        """Test Common Table Expression detection using only AST node types."""
        content = dedent(
            """
            WITH user_stats AS (
                SELECT user_id, COUNT(*) as post_count
                FROM posts
                GROUP BY user_id
            ),
            active_users AS (
                SELECT id, username
                FROM users
                WHERE created_at > NOW() - INTERVAL 30 DAY
            )
            SELECT au.username, COALESCE(us.post_count, 0) as posts
            FROM active_users au
            LEFT JOIN user_stats us ON au.id = us.user_id;
        """
        ).strip()

        chunks = parser.chunk(content, "cte.sql")

        # Should detect via 'cte' AST node type
        cte_chunks = [c for c in chunks if c.semantic_type == "cte"]
        assert len(cte_chunks) == 2

        cte_names = {c.semantic_name for c in cte_chunks}
        assert "user_stats" in cte_names
        assert "active_users" in cte_names

    def test_pure_ast_no_regex_abuse(self, parser):
        """Test that NO regex patterns are used on AST node text."""
        content = dedent(
            """
            CREATE TABLE test_table (
                id INT PRIMARY KEY,
                name VARCHAR(100) NOT NULL
            );

            CREATE VIEW test_view AS 
            SELECT * FROM test_table WHERE active = 1;

            CREATE PROCEDURE test_proc(IN param INT)
            BEGIN
                SELECT * FROM test_table WHERE id = param;
            END;
        """
        ).strip()

        chunks = parser.chunk(content, "test_ast.sql")

        # Verify constructs were found
        assert len(chunks) >= 3

        table_chunks = [c for c in chunks if c.semantic_type == "table"]
        view_chunks = [c for c in chunks if c.semantic_type == "view"]
        proc_chunks = [c for c in chunks if c.semantic_type == "procedure"]

        assert len(table_chunks) == 1
        assert len(view_chunks) == 1
        assert len(proc_chunks) >= 1

        # CRITICAL: Verify NO regex fallback was used
        for chunk in chunks:
            context = chunk.semantic_context
            assert context.get("regex_fallback") is not True

        # Verify names were extracted via AST structure
        assert table_chunks[0].semantic_name == "test_table"
        assert view_chunks[0].semantic_name == "test_view"

    def test_error_node_ast_structure_analysis(self, parser):
        """Test that ERROR nodes are handled via AST structure analysis, not regex."""
        content = dedent(
            """
            CREATE PROCEDURE complex_proc(
                IN param1 INT,
                OUT param2 VARCHAR(100),
                INOUT param3 DECIMAL(10,2)
            )
            BEGIN
                DECLARE var1 INT DEFAULT 0;
                DECLARE cursor1 CURSOR FOR SELECT id FROM users;
                
                SELECT COUNT(*) INTO param2 FROM users WHERE active = 1;
                SET param3 = param3 * 1.1;
            END;
        """
        ).strip()

        chunks = parser.chunk(content, "complex_proc.sql")

        # Even with complex syntax that creates ERROR nodes, should extract via AST
        proc_chunks = [c for c in chunks if c.semantic_type == "procedure"]

        assert len(proc_chunks) >= 1

        # Procedure should be detected via AST structure in ERROR nodes
        proc_chunk = proc_chunks[0]
        assert proc_chunk.semantic_name == "complex_proc"

        # Verify extraction was AST-based, not regex-based
        assert proc_chunk.semantic_context.get("regex_fallback") is not True

    def test_meaningful_chunk_content_validation(self, parser):
        """Test that only meaningful content creates chunks - no null/empty fragments."""
        content = dedent(
            """
            CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(50));
            
            -- This should create meaningful chunks, not null fragments
            CREATE VIEW user_view AS SELECT * FROM users;
            
            -- Comments should not create meaningless chunks
            /* Multi-line comment
               should not generate chunks */
               
            CREATE PROCEDURE get_users() 
            BEGIN 
                SELECT * FROM users; 
            END;
        """
        ).strip()

        chunks = parser.chunk(content, "meaningful.sql")

        # All chunks should have meaningful content
        for chunk in chunks:
            assert chunk.text is not None
            assert len(chunk.text.strip()) > 0
            assert chunk.text.strip() not in ["null", "null;", ";", ""]
            assert chunk.semantic_name is not None
            assert len(chunk.semantic_name.strip()) > 0

        # Should have reasonable number of constructs
        construct_types = {c.semantic_type for c in chunks}
        expected_types = {"table", "view", "procedure"}
        assert construct_types.intersection(expected_types)

    def test_sql_dialect_compatibility_via_ast(self, parser):
        """Test that different SQL dialects work via AST structure, not regex patterns."""
        content = dedent(
            """
            -- MySQL specific
            CREATE TABLE mysql_table (
                id INT AUTO_INCREMENT PRIMARY KEY,
                data JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB;

            -- PostgreSQL specific  
            CREATE TABLE postgres_table (
                id SERIAL PRIMARY KEY,
                data JSONB,
                tags TEXT[]
            );

            -- SQL Server specific
            CREATE TABLE sqlserver_table (
                id INT IDENTITY(1,1) PRIMARY KEY,
                data NVARCHAR(MAX)
            );
        """
        ).strip()

        chunks = parser.chunk(content, "multi_dialect.sql")

        # Should handle all dialects via AST structure
        table_chunks = [c for c in chunks if c.semantic_type == "table"]
        assert len(table_chunks) == 3

        table_names = {c.semantic_name for c in table_chunks}
        assert "mysql_table" in table_names
        assert "postgres_table" in table_names
        assert "sqlserver_table" in table_names

        # All should be detected via AST, not regex
        for chunk in table_chunks:
            assert chunk.semantic_context.get("regex_fallback") is not True

    def test_search_relevance_validation(self, parser):
        """Test that chunks have good search relevance for semantic queries."""
        content = dedent(
            """
            CREATE TABLE users (
                id INT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                email VARCHAR(100) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE PROCEDURE GetUserStats(IN user_id INT)
            BEGIN
                SELECT 
                    u.username,
                    COUNT(p.id) as total_posts,
                    MAX(p.created_at) as last_post_date
                FROM users u
                LEFT JOIN posts p ON u.id = p.user_id
                WHERE u.id = user_id
                GROUP BY u.username;
            END;
        """
        ).strip()

        chunks = parser.chunk(content, "search_relevance.sql")

        # Chunks should have content that would match semantic searches
        table_chunk = next(c for c in chunks if c.semantic_type == "table")
        proc_chunk = next(c for c in chunks if c.semantic_type == "procedure")

        # Table chunk should contain CREATE TABLE users
        assert "CREATE TABLE users" in table_chunk.text
        assert "username" in table_chunk.text
        assert "email" in table_chunk.text

        # Procedure chunk should contain full procedure definition
        assert "CREATE PROCEDURE GetUserStats" in proc_chunk.text
        assert "SELECT" in proc_chunk.text
        assert "JOIN" in proc_chunk.text

        # Semantic metadata should be meaningful
        assert table_chunk.semantic_signature.startswith("CREATE TABLE users")
        assert proc_chunk.semantic_signature.startswith("CREATE PROCEDURE GetUserStats")

    def test_no_false_positives_from_comments_strings(self, parser):
        """Test that SQL in comments/strings doesn't create false positive chunks."""
        content = dedent(
            """
            -- This comment mentions CREATE TABLE fake_table but shouldn't create chunks
            /* 
             * Another comment with CREATE VIEW fake_view AS SELECT * FROM nowhere
             * This should not generate constructs
             */
            
            CREATE TABLE real_table (
                id INT PRIMARY KEY,
                description TEXT DEFAULT 'Contains CREATE TABLE in string but not parsed'
            );
            
            INSERT INTO real_table (description) 
            VALUES ('This string has CREATE PROCEDURE fake_proc() but is just data');
        """
        ).strip()

        chunks = parser.chunk(content, "false_positives.sql")

        # Should only find real constructs, not ones in comments/strings
        table_chunks = [c for c in chunks if c.semantic_type == "table"]
        insert_chunks = [c for c in chunks if c.semantic_type == "insert"]

        assert len(table_chunks) == 1
        assert table_chunks[0].semantic_name == "real_table"

        assert len(insert_chunks) == 1

        # Should NOT create chunks for fake constructs in comments
        all_names = {c.semantic_name for c in chunks if c.semantic_name}
        assert "fake_table" not in all_names
        assert "fake_view" not in all_names
        assert "fake_proc" not in all_names
