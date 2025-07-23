"""
Tests for SQL semantic parser.
Following TDD approach - writing comprehensive tests to ensure complete coverage
of SQL language constructs including ERROR node handling.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestSQLSemanticParser:
    """Test SQL semantic parser using tree-sitter."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create a SQL parser directly."""
        from code_indexer.indexing.sql_parser import SQLSemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SQLSemanticParser(config)

    def test_basic_table_creation(self, parser):
        """Test parsing basic CREATE TABLE statements."""
        content = dedent(
            """
            CREATE TABLE users (
                id INT PRIMARY KEY AUTO_INCREMENT,
                username VARCHAR(50) NOT NULL UNIQUE,
                email VARCHAR(100) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            );

            CREATE TABLE posts (
                id INT PRIMARY KEY AUTO_INCREMENT,
                user_id INT NOT NULL,
                title VARCHAR(200) NOT NULL,
                content TEXT,
                published BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TEMPORARY TABLE temp_data (
                id INT,
                data VARCHAR(100)
            );
        """
        ).strip()

        chunks = parser.chunk(content, "tables.sql")

        # Should find table creation statements
        assert len(chunks) >= 3

        # Check table chunks
        table_chunks = [c for c in chunks if c.semantic_type == "table"]
        assert len(table_chunks) >= 3

        table_names = {c.semantic_name for c in table_chunks}
        assert "users" in table_names
        assert "posts" in table_names
        assert "temp_data" in table_names

        # Check users table
        users_table = next(c for c in table_chunks if c.semantic_name == "users")
        assert users_table.semantic_path == "users"
        assert "CREATE TABLE users" in users_table.semantic_signature
        assert "table_declaration" in users_table.semantic_language_features

        # Check posts table with foreign key
        posts_table = next(c for c in table_chunks if c.semantic_name == "posts")
        if posts_table.semantic_context.get("constraints"):
            constraints = posts_table.semantic_context["constraints"]
            assert "FOREIGN KEY" in constraints

    def test_view_creation(self, parser):
        """Test parsing CREATE VIEW statements."""
        content = dedent(
            """
            CREATE VIEW active_users AS
            SELECT u.id, u.username, u.email, COUNT(p.id) as post_count
            FROM users u
            LEFT JOIN posts p ON u.id = p.user_id
            WHERE u.created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)
            GROUP BY u.id, u.username, u.email;

            CREATE OR REPLACE VIEW user_stats AS
            SELECT 
                u.username,
                COUNT(p.id) as total_posts,
                MAX(p.created_at) as last_post_date
            FROM users u
            LEFT JOIN posts p ON u.id = p.user_id
            GROUP BY u.username;

            CREATE VIEW simple_view AS
            SELECT * FROM users WHERE active = 1;
        """
        ).strip()

        chunks = parser.chunk(content, "views.sql")

        # Should find view creation statements
        view_chunks = [c for c in chunks if c.semantic_type == "view"]
        assert len(view_chunks) >= 3

        view_names = {c.semantic_name for c in view_chunks}
        assert "active_users" in view_names
        assert "user_stats" in view_names
        assert "simple_view" in view_names

        # Check active_users view
        active_view = next(c for c in view_chunks if c.semantic_name == "active_users")
        assert "CREATE VIEW active_users" in active_view.semantic_signature
        assert "view_declaration" in active_view.semantic_language_features

    def test_stored_procedures(self, parser):
        """Test parsing CREATE PROCEDURE statements."""
        content = dedent(
            """
            DELIMITER //

            CREATE PROCEDURE GetUserPosts(IN userId INT)
            BEGIN
                SELECT p.*, u.username
                FROM posts p
                JOIN users u ON p.user_id = u.id
                WHERE p.user_id = userId
                ORDER BY p.created_at DESC;
            END //

            CREATE OR REPLACE PROCEDURE UpdateUserStats(
                IN user_id INT,
                OUT total_posts INT,
                INOUT last_updated TIMESTAMP
            )
            BEGIN
                SELECT COUNT(*) INTO total_posts
                FROM posts
                WHERE user_id = user_id;
                
                SET last_updated = NOW();
                
                UPDATE users 
                SET post_count = total_posts, updated_at = last_updated
                WHERE id = user_id;
            END //

            CREATE PROCEDURE SimpleProc()
            BEGIN
                SELECT 'Hello World' as message;
            END //

            DELIMITER ;
        """
        ).strip()

        chunks = parser.chunk(content, "procedures.sql")

        # Should find procedure creation statements
        proc_chunks = [c for c in chunks if c.semantic_type == "procedure"]
        assert len(proc_chunks) >= 3

        proc_names = {c.semantic_name for c in proc_chunks}
        assert "GetUserPosts" in proc_names
        assert "UpdateUserStats" in proc_names
        assert "SimpleProc" in proc_names

        # Check GetUserPosts procedure
        get_posts_proc = next(
            c for c in proc_chunks if c.semantic_name == "GetUserPosts"
        )
        assert "CREATE PROCEDURE GetUserPosts" in get_posts_proc.semantic_signature
        assert "procedure_declaration" in get_posts_proc.semantic_language_features

        # Check procedure with parameters
        update_stats_proc = next(
            c for c in proc_chunks if c.semantic_name == "UpdateUserStats"
        )
        if update_stats_proc.semantic_context.get("parameters"):
            params = update_stats_proc.semantic_context["parameters"]
            assert len(params.strip()) > 0

    def test_functions(self, parser):
        """Test parsing CREATE FUNCTION statements."""
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
            DETERMINISTIC
            BEGIN
                RETURN CONCAT(first_name, ' ', last_name);
            END;

            CREATE FUNCTION IsAdult(birth_date DATE)
            RETURNS BOOLEAN
            READS SQL DATA
            BEGIN
                RETURN TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) >= 18;
            END;
        """
        ).strip()

        chunks = parser.chunk(content, "functions.sql")

        # Should find function creation statements
        func_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(func_chunks) >= 3

        func_names = {c.semantic_name for c in func_chunks}
        assert "CalculateAge" in func_names
        assert "GetFullName" in func_names
        assert "IsAdult" in func_names

        # Check CalculateAge function
        calc_age_func = next(
            c for c in func_chunks if c.semantic_name == "CalculateAge"
        )
        assert "CREATE FUNCTION CalculateAge" in calc_age_func.semantic_signature
        assert "function_declaration" in calc_age_func.semantic_language_features

        # Check function with return type
        if calc_age_func.semantic_context.get("return_type"):
            return_type = calc_age_func.semantic_context["return_type"]
            assert return_type is not None

    def test_triggers(self, parser):
        """Test parsing CREATE TRIGGER statements."""
        content = dedent(
            """
            CREATE TRIGGER users_before_insert
            BEFORE INSERT ON users
            FOR EACH ROW
            BEGIN
                SET NEW.created_at = NOW();
                SET NEW.updated_at = NOW();
            END;

            CREATE TRIGGER posts_after_update
            AFTER UPDATE ON posts
            FOR EACH ROW
            BEGIN
                IF NEW.title != OLD.title THEN
                    INSERT INTO audit_log (table_name, action, record_id, changed_at)
                    VALUES ('posts', 'title_changed', NEW.id, NOW());
                END IF;
            END;

            CREATE TRIGGER user_stats_after_delete
            AFTER DELETE ON posts
            FOR EACH ROW
            BEGIN
                UPDATE users 
                SET post_count = post_count - 1 
                WHERE id = OLD.user_id;
            END;
        """
        ).strip()

        chunks = parser.chunk(content, "triggers.sql")

        # Should find trigger creation statements
        trigger_chunks = [c for c in chunks if c.semantic_type == "trigger"]
        assert len(trigger_chunks) >= 3

        trigger_names = {c.semantic_name for c in trigger_chunks}
        assert "users_before_insert" in trigger_names
        assert "posts_after_update" in trigger_names
        assert "user_stats_after_delete" in trigger_names

        # Check trigger features
        before_trigger = next(
            c for c in trigger_chunks if c.semantic_name == "users_before_insert"
        )
        assert "CREATE TRIGGER users_before_insert" in before_trigger.semantic_signature
        assert "trigger_declaration" in before_trigger.semantic_language_features

        # Check trigger timing and events
        if before_trigger.semantic_context:
            context = before_trigger.semantic_context
            timing = context.get("timing")
            events = context.get("events")
            table_name = context.get("table_name")

            if timing:
                assert timing == "BEFORE"
            if events:
                assert "INSERT" in events
            if table_name:
                assert table_name == "users"

    def test_index_creation(self, parser):
        """Test parsing CREATE INDEX statements."""
        content = dedent(
            """
            CREATE INDEX idx_users_email ON users(email);
            
            CREATE UNIQUE INDEX idx_users_username ON users(username);
            
            CREATE INDEX idx_posts_user_created ON posts(user_id, created_at DESC);
            
            CREATE INDEX idx_posts_title_fulltext ON posts(title, content);
        """
        ).strip()

        chunks = parser.chunk(content, "indexes.sql")

        # Should find index creation statements
        index_chunks = [c for c in chunks if c.semantic_type == "index"]
        assert len(index_chunks) >= 4

        index_names = {c.semantic_name for c in index_chunks}
        assert "idx_users_email" in index_names
        assert "idx_users_username" in index_names
        assert "idx_posts_user_created" in index_names

        # Check index features
        email_index = next(
            c for c in index_chunks if c.semantic_name == "idx_users_email"
        )
        assert "CREATE INDEX idx_users_email" in email_index.semantic_signature
        assert "index_declaration" in email_index.semantic_language_features

        # Check table name association
        if email_index.semantic_context.get("table_name"):
            assert email_index.semantic_context["table_name"] == "users"

    def test_select_statements(self, parser):
        """Test parsing SELECT statements."""
        content = dedent(
            """
            SELECT * FROM users WHERE active = 1;

            SELECT u.username, p.title, p.created_at
            FROM users u
            INNER JOIN posts p ON u.id = p.user_id
            WHERE p.published = TRUE
            ORDER BY p.created_at DESC
            LIMIT 10;

            SELECT 
                u.username,
                COUNT(p.id) as post_count,
                MAX(p.created_at) as last_post,
                AVG(p.view_count) as avg_views
            FROM users u
            LEFT JOIN posts p ON u.id = p.user_id
            WHERE u.created_at > '2023-01-01'
            GROUP BY u.id, u.username
            HAVING COUNT(p.id) > 5
            ORDER BY post_count DESC;
        """
        ).strip()

        chunks = parser.chunk(content, "selects.sql")

        # Should find SELECT statements
        select_chunks = [c for c in chunks if c.semantic_type == "select"]
        assert len(select_chunks) >= 2  # Only significant SELECTs with FROM

        # Check that tables are identified
        for chunk in select_chunks:
            if chunk.semantic_context.get("tables"):
                tables = chunk.semantic_context["tables"]
                assert len(tables) >= 1
                assert any(table in ["users", "posts"] for table in tables)

    def test_dml_statements(self, parser):
        """Test parsing INSERT, UPDATE, DELETE statements."""
        content = dedent(
            """
            INSERT INTO users (username, email, password_hash)
            VALUES ('john_doe', 'john@example.com', 'hashed_password');

            INSERT INTO posts (user_id, title, content, published)
            SELECT u.id, 'Welcome Post', 'Welcome to our platform!', TRUE
            FROM users u
            WHERE u.username = 'john_doe';

            UPDATE users 
            SET updated_at = NOW(), last_login = NOW()
            WHERE id = 1;

            UPDATE posts p
            JOIN users u ON p.user_id = u.id
            SET p.author_name = u.username
            WHERE p.author_name IS NULL;

            DELETE FROM posts WHERE published = FALSE AND created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

            DELETE p FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE u.active = FALSE;
        """
        ).strip()

        chunks = parser.chunk(content, "dml.sql")

        # Should find DML statements
        insert_chunks = [c for c in chunks if c.semantic_type == "insert"]
        update_chunks = [c for c in chunks if c.semantic_type == "update"]
        delete_chunks = [c for c in chunks if c.semantic_type == "delete"]

        assert len(insert_chunks) >= 2
        assert len(update_chunks) >= 2
        assert len(delete_chunks) >= 2

        # Check table names in context
        for chunk in insert_chunks:
            if chunk.semantic_context.get("table_name"):
                table_name = chunk.semantic_context["table_name"]
                assert table_name in ["users", "posts"]

    def test_cte_statements(self, parser):
        """Test parsing Common Table Expression (CTE) statements."""
        content = dedent(
            """
            WITH user_stats AS (
                SELECT 
                    user_id,
                    COUNT(*) as post_count,
                    MAX(created_at) as last_post_date
                FROM posts
                GROUP BY user_id
            ),
            active_users AS (
                SELECT id, username, email
                FROM users
                WHERE created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)
            )
            SELECT 
                au.username,
                au.email,
                COALESCE(us.post_count, 0) as posts,
                us.last_post_date
            FROM active_users au
            LEFT JOIN user_stats us ON au.id = us.user_id
            ORDER BY us.post_count DESC;

            WITH RECURSIVE category_hierarchy AS (
                SELECT id, name, parent_id, 0 as level
                FROM categories
                WHERE parent_id IS NULL
                
                UNION ALL
                
                SELECT c.id, c.name, c.parent_id, ch.level + 1
                FROM categories c
                JOIN category_hierarchy ch ON c.parent_id = ch.id
            )
            SELECT * FROM category_hierarchy ORDER BY level, name;
        """
        ).strip()

        chunks = parser.chunk(content, "cte.sql")

        # Should find CTE statements
        cte_chunks = [c for c in chunks if c.semantic_type == "cte"]
        assert len(cte_chunks) >= 2

        cte_names = {c.semantic_name for c in cte_chunks}
        assert (
            "user_stats" in cte_names
            or "active_users" in cte_names
            or "category_hierarchy" in cte_names
        )

    def test_schema_and_database_statements(self, parser):
        """Test parsing schema and database-related statements."""
        content = dedent(
            """
            CREATE SCHEMA blog_app;
            USE blog_app;

            CREATE DATABASE IF NOT EXISTS test_db;
            USE test_db;

            CREATE SCHEMA authorization user_data;
        """
        ).strip()

        chunks = parser.chunk(content, "schema.sql")

        # Should find schema and use statements
        schema_chunks = [c for c in chunks if c.semantic_type == "schema"]
        use_chunks = [c for c in chunks if c.semantic_type == "use"]

        assert len(schema_chunks) >= 1
        assert len(use_chunks) >= 1

        # Check schema names
        if schema_chunks:
            schema_names = {c.semantic_name for c in schema_chunks}
            assert "blog_app" in schema_names or "user_data" in schema_names

        # Check use statements
        if use_chunks:
            use_names = {c.semantic_name for c in use_chunks}
            assert "blog_app" in use_names or "test_db" in use_names

    def test_alter_table_statements(self, parser):
        """Test parsing ALTER TABLE statements."""
        content = dedent(
            """
            ALTER TABLE users ADD COLUMN phone VARCHAR(20);
            
            ALTER TABLE users DROP COLUMN phone;
            
            ALTER TABLE users MODIFY COLUMN email VARCHAR(150) NOT NULL;
            
            ALTER TABLE posts ADD CONSTRAINT fk_posts_user 
            FOREIGN KEY (user_id) REFERENCES users(id);
            
            ALTER TABLE posts DROP CONSTRAINT fk_posts_user;
            
            ALTER TABLE users RENAME TO app_users;
        """
        ).strip()

        chunks = parser.chunk(content, "alter.sql")

        # Should find ALTER TABLE statements
        alter_chunks = [c for c in chunks if c.semantic_type == "alter_table"]
        assert len(alter_chunks) >= 5

        # Check operations
        operations = []
        for chunk in alter_chunks:
            if chunk.semantic_context.get("operation"):
                operations.append(chunk.semantic_context["operation"])

        assert "ADD" in operations
        assert "DROP" in operations or "MODIFY" in operations

    def test_variable_declarations(self, parser):
        """Test parsing variable declarations."""
        content = dedent(
            """
            DECLARE @user_count INT;
            DECLARE @max_posts INT = 100;
            DECLARE @start_date DATE = '2023-01-01';
            DECLARE @message VARCHAR(255) = 'Hello World';

            SET @user_count = (SELECT COUNT(*) FROM users);
        """
        ).strip()

        chunks = parser.chunk(content, "variables.sql")

        # Should find variable declarations
        var_chunks = [c for c in chunks if c.semantic_type == "variable"]
        assert len(var_chunks) >= 3

        var_names = {c.semantic_name for c in var_chunks}
        assert "@user_count" in var_names or "@max_posts" in var_names

        # Check variable types
        for chunk in var_chunks:
            if chunk.semantic_context.get("variable_type"):
                var_type = chunk.semantic_context["variable_type"]
                assert var_type in ["INT", "DATE", "VARCHAR"]

    def test_cursor_declarations(self, parser):
        """Test parsing cursor declarations."""
        content = dedent(
            """
            DECLARE user_cursor CURSOR FOR
            SELECT id, username, email FROM users WHERE active = 1;

            DECLARE post_cursor CURSOR FOR
            SELECT p.id, p.title, u.username
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.published = TRUE;

            OPEN user_cursor;
            FETCH NEXT FROM user_cursor INTO @user_id, @username, @email;
            CLOSE user_cursor;
            DEALLOCATE user_cursor;
        """
        ).strip()

        chunks = parser.chunk(content, "cursors.sql")

        # Should find cursor declarations
        cursor_chunks = [c for c in chunks if c.semantic_type == "cursor"]
        assert len(cursor_chunks) >= 2

        cursor_names = {c.semantic_name for c in cursor_chunks}
        assert "user_cursor" in cursor_names
        assert "post_cursor" in cursor_names

    def test_error_node_handling_basic(self, parser):
        """Test ERROR node handling for basic syntax errors."""
        content = dedent(
            """
            CREATE TABLE valid_table (
                id INT PRIMARY KEY,
                name VARCHAR(100)
            );

            CREATE TABLE broken_table (
                id INT PRIMARY KEY
                name VARCHAR(100)  -- Missing comma
            );

            CREATE VIEW valid_view AS
            SELECT * FROM valid_table;

            CREATE VIEW broken_view AS
            SELECT * FROM non_existent_table WHERE  -- Incomplete WHERE
        """
        ).strip()

        chunks = parser.chunk(content, "broken.sql")

        # Should extract constructs despite syntax errors
        assert len(chunks) >= 2

        # Should find valid constructs
        table_chunks = [c for c in chunks if c.semantic_type == "table"]
        view_chunks = [c for c in chunks if c.semantic_type == "view"]

        assert len(table_chunks) >= 1
        assert len(view_chunks) >= 1

        # Check that valid names are found
        all_names = {c.semantic_name for c in chunks if c.semantic_name}
        assert "valid_table" in all_names or "valid_view" in all_names

    def test_error_node_handling_procedure_errors(self, parser):
        """Test ERROR node handling for procedure syntax errors."""
        content = dedent(
            """
            DELIMITER //

            CREATE PROCEDURE valid_proc(IN param INT)
            BEGIN
                SELECT * FROM users WHERE id = param;
            END //

            CREATE PROCEDURE broken_proc(IN param INT
            -- Missing closing parenthesis and BEGIN/END
                SELECT * FROM users WHERE id = param;

            CREATE PROCEDURE another_valid()
            BEGIN
                SELECT 'Hello' as message;
            END //

            DELIMITER ;
        """
        ).strip()

        chunks = parser.chunk(content, "proc_errors.sql")

        # Should extract procedures despite syntax errors
        proc_chunks = [c for c in chunks if c.semantic_type == "procedure"]
        assert len(proc_chunks) >= 2

        proc_names = {c.semantic_name for c in proc_chunks}
        assert "valid_proc" in proc_names or "another_valid" in proc_names

    def test_error_node_handling_complex_query_errors(self, parser):
        """Test ERROR node handling for complex query syntax errors."""
        content = dedent(
            """
            SELECT u.username, p.title
            FROM users u
            JOIN posts p ON u.id = p.user_id
            WHERE u.active = TRUE;

            SELECT u.username, p.title
            FROM users u
            JOIN posts p ON u.id = p.user_id
            WHERE u.active = TRUE AND  -- Incomplete WHERE condition

            WITH user_stats AS (
                SELECT user_id, COUNT(*) as posts
                FROM posts
                GROUP BY user_id
            )
            SELECT * FROM user_stats;

            WITH broken_cte AS
            -- Missing AS and subquery
            SELECT * FROM users;
        """
        ).strip()

        chunks = parser.chunk(content, "query_errors.sql")

        # Should extract valid queries despite syntax errors
        assert len(chunks) >= 2

        # Should find valid constructs
        select_chunks = [c for c in chunks if c.semantic_type == "select"]
        cte_chunks = [c for c in chunks if c.semantic_type == "cte"]

        assert len(select_chunks) >= 2 or len(cte_chunks) >= 1

    def test_malformed_sql_code_handling(self, parser):
        """Test handling of completely malformed SQL code."""
        malformed_content = """
            This is not valid SQL code at all!
            CREATE??? broken syntax everywhere
            SELECT FROM WHERE;;;
            INVALID KEYWORDS AND STRUCTURE
            %%% random characters @@@
        """

        # Should not crash and should return minimal chunks
        chunks = parser.chunk(malformed_content, "malformed.sql")

        # Parser should handle gracefully
        assert isinstance(chunks, list)

    def test_chunker_integration(self, chunker):
        """Test integration with SemanticChunker for SQL files."""
        content = dedent(
            """
            CREATE DATABASE blog_system;
            USE blog_system;

            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIEW active_users AS
            SELECT id, username, email
            FROM users
            WHERE created_at > DATE_SUB(NOW(), INTERVAL 30 DAY);

            CREATE PROCEDURE GetUserById(IN userId INT)
            BEGIN
                SELECT * FROM users WHERE id = userId;
            END;
        """
        ).strip()

        chunks = chunker.chunk_content(content, "blog_system.sql")

        # Should get semantic chunks from SQL parser
        assert len(chunks) >= 4

        # Verify chunks have semantic metadata
        for chunk in chunks:
            assert chunk.get("semantic_chunking") is True
            assert "semantic_type" in chunk
            assert "semantic_name" in chunk
            assert "semantic_path" in chunk

    def test_multiple_sql_dialects(self, parser):
        """Test parsing SQL from different dialects."""
        content = dedent(
            """
            -- MySQL syntax
            CREATE TABLE mysql_table (
                id INT AUTO_INCREMENT PRIMARY KEY,
                data JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB;

            -- PostgreSQL syntax
            CREATE TABLE postgres_table (
                id SERIAL PRIMARY KEY,
                data JSONB,
                tags TEXT[],
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            -- SQL Server syntax
            CREATE TABLE sqlserver_table (
                id INT IDENTITY(1,1) PRIMARY KEY,
                data NVARCHAR(MAX),
                created_at DATETIME2 DEFAULT GETDATE()
            );

            -- SQLite syntax
            CREATE TABLE sqlite_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT,
                created_at DATETIME DEFAULT (datetime('now'))
            );
        """
        ).strip()

        chunks = parser.chunk(content, "multi_dialect.sql")

        # Should handle different SQL dialects without crashing
        assert len(chunks) >= 4

        table_chunks = [c for c in chunks if c.semantic_type == "table"]
        assert len(table_chunks) >= 4

        table_names = {c.semantic_name for c in table_chunks}
        assert "mysql_table" in table_names
        assert "postgres_table" in table_names
        assert "sqlserver_table" in table_names
        assert "sqlite_table" in table_names

    def test_regex_fallback_functionality(self, parser):
        """Test regex fallback for SQL when tree-sitter fails."""
        # Test the regex fallback method directly
        error_text = """
            CREATE TABLE test_table (
                id INT PRIMARY KEY,
                name VARCHAR(100)
            );
            
            CREATE VIEW test_view AS
            SELECT * FROM test_table;
            
            CREATE PROCEDURE test_proc()
            BEGIN
                SELECT * FROM test_table;
            END;
            
            CREATE FUNCTION test_func() RETURNS INT
            BEGIN
                RETURN 1;
            END;
            
            CREATE TRIGGER test_trigger
            BEFORE INSERT ON test_table
            FOR EACH ROW
            BEGIN
                SET NEW.created_at = NOW();
            END;
            
            CREATE INDEX idx_test ON test_table(name);
        """

        constructs = parser._extract_constructs_from_error_text(error_text, 1, [])

        # Should find constructs through regex
        assert len(constructs) >= 5

        # Check that different construct types were found
        construct_types = {c["type"] for c in constructs}
        expected_types = {"table", "view", "procedure", "function", "trigger", "index"}
        assert len(construct_types.intersection(expected_types)) >= 4

    def test_window_functions_and_advanced_features(self, parser):
        """Test parsing advanced SQL features like window functions."""
        content = dedent(
            """
            SELECT 
                username,
                created_at,
                ROW_NUMBER() OVER (ORDER BY created_at) as user_number,
                RANK() OVER (PARTITION BY DATE(created_at) ORDER BY created_at) as daily_rank,
                LAG(username, 1) OVER (ORDER BY created_at) as previous_user
            FROM users
            WHERE created_at >= '2023-01-01';

            SELECT 
                p.title,
                p.view_count,
                AVG(p.view_count) OVER (
                    PARTITION BY DATE(p.created_at) 
                    ORDER BY p.created_at 
                    ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING
                ) as rolling_avg_views
            FROM posts p
            ORDER BY p.created_at;
        """
        ).strip()

        chunks = parser.chunk(content, "window_functions.sql")

        # Should handle window functions without crashing
        assert len(chunks) >= 1

        select_chunks = [c for c in chunks if c.semantic_type == "select"]
        assert len(select_chunks) >= 1

    def test_data_preservation_no_loss(self, parser):
        """Test that chunking preserves all content without data loss."""
        content = dedent(
            """
            -- Complete blog database schema
            CREATE DATABASE blog_system CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            USE blog_system;

            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                first_name VARCHAR(50),
                last_name VARCHAR(50),
                bio TEXT,
                avatar_url VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                INDEX idx_username (username),
                INDEX idx_email (email),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB;

            CREATE TABLE categories (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                slug VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                parent_id INT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL
            ) ENGINE=InnoDB;

            CREATE VIEW user_post_stats AS
            SELECT 
                u.id,
                u.username,
                COUNT(p.id) as total_posts,
                COUNT(CASE WHEN p.published = TRUE THEN 1 END) as published_posts,
                MAX(p.created_at) as last_post_date,
                AVG(p.view_count) as avg_views_per_post
            FROM users u
            LEFT JOIN posts p ON u.id = p.user_id
            GROUP BY u.id, u.username;

            DELIMITER //

            CREATE FUNCTION GetUserPostCount(userId INT) 
            RETURNS INT
            READS SQL DATA
            DETERMINISTIC
            BEGIN
                DECLARE post_count INT DEFAULT 0;
                SELECT COUNT(*) INTO post_count
                FROM posts
                WHERE user_id = userId AND published = TRUE;
                RETURN post_count;
            END //

            CREATE PROCEDURE UpdatePostStats()
            BEGIN
                DECLARE done INT DEFAULT FALSE;
                DECLARE post_id INT;
                DECLARE comment_count INT;
                
                DECLARE post_cursor CURSOR FOR
                    SELECT id FROM posts WHERE published = TRUE;
                    
                DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;
                
                OPEN post_cursor;
                
                read_loop: LOOP
                    FETCH post_cursor INTO post_id;
                    IF done THEN
                        LEAVE read_loop;
                    END IF;
                    
                    SELECT COUNT(*) INTO comment_count
                    FROM comments
                    WHERE post_id = post_id AND approved = TRUE;
                    
                    UPDATE posts
                    SET comment_count = comment_count
                    WHERE id = post_id;
                END LOOP;
                
                CLOSE post_cursor;
            END //

            DELIMITER ;
        """
        ).strip()

        chunks = parser.chunk(content, "data_preservation.sql")

        # Verify no data loss by checking that all content is captured
        all_chunk_content = "\n".join(chunk.text for chunk in chunks)

        # Check that essential elements are preserved
        assert "CREATE DATABASE blog_system" in all_chunk_content
        assert "CREATE TABLE users" in all_chunk_content
        assert "CREATE TABLE categories" in all_chunk_content
        assert "CREATE VIEW user_post_stats" in all_chunk_content
        assert "CREATE FUNCTION GetUserPostCount" in all_chunk_content
        assert "CREATE PROCEDURE UpdatePostStats" in all_chunk_content

        # Check that we have reasonable chunk coverage
        assert len(chunks) >= 5  # Should have multiple semantic chunks

        # Verify all chunks have proper metadata
        for chunk in chunks:
            assert chunk.semantic_chunking is True
            assert chunk.semantic_type is not None
            assert chunk.semantic_name is not None
            assert chunk.file_path == "data_preservation.sql"
            assert chunk.line_start > 0
            assert chunk.line_end >= chunk.line_start

    def test_file_extension_detection(self, parser):
        """Test detection of different SQL file extensions."""
        simple_content = """
            CREATE TABLE test (
                id INT PRIMARY KEY
            );
        """

        # Test various SQL file extensions
        extensions = [".sql", ".ddl", ".dml"]

        for ext in extensions:
            chunks = parser.chunk(simple_content, f"test{ext}")
            assert len(chunks) >= 1
            assert chunks[0].file_extension == ext
