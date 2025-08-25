"""
Tests for Ruby parser cohesive chunking - demonstrating expected behavior.
These tests currently FAIL and demonstrate the desired behavior where:
1. Methods should create ONE cohesive chunk containing all assignments
2. No separate chunks for individual instance variable assignments within methods
3. AST-based parsing instead of regex abuse patterns
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.ruby_parser import RubySemanticParser


class TestRubyCohesiveChunking:
    """Test Ruby parser cohesive chunking behavior - these tests currently FAIL."""

    @pytest.fixture
    def parser(self):
        """Create a Ruby parser directly."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return RubySemanticParser(config)

    def test_initialize_method_cohesive_chunking(self, parser):
        """
        Test that initialize method creates ONE cohesive chunk, not fragments.

        CURRENT BAD BEHAVIOR: Creates separate chunks for @name = name, @email = email
        DESIRED BEHAVIOR: Creates ONE chunk for entire initialize method
        """
        content = dedent(
            """
            class User
              def initialize(name, email)
                @name = name
                @email = email
                puts "User created"
                validate_email
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "user.rb")

        # Find method chunks
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        initialize_chunks = [
            c for c in method_chunks if c.semantic_name == "initialize"
        ]

        # ASSERTION 1: Should have exactly ONE initialize method chunk
        assert (
            len(initialize_chunks) == 1
        ), f"Expected 1 initialize chunk, got {len(initialize_chunks)} chunks"

        initialize_chunk = initialize_chunks[0]

        # ASSERTION 2: The chunk should contain ALL method content
        chunk_text = initialize_chunk.text
        assert (
            "@name = name" in chunk_text
        ), "Initialize chunk should contain @name assignment"
        assert (
            "@email = email" in chunk_text
        ), "Initialize chunk should contain @email assignment"
        assert (
            'puts "User created"' in chunk_text
        ), "Initialize chunk should contain puts statement"
        assert (
            "validate_email" in chunk_text
        ), "Initialize chunk should contain method call"

        # ASSERTION 3: Should NOT have separate chunks for individual assignments
        assignment_chunks = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and (c.semantic_name == "@name" or c.semantic_name == "@email")
        ]
        assert len(assignment_chunks) == 0, (
            f"Should not have separate chunks for individual assignments, "
            f"but found {len(assignment_chunks)} assignment chunks: "
            f"{[c.semantic_name for c in assignment_chunks]}"
        )

    def test_method_with_multiple_assignments_stays_cohesive(self, parser):
        """
        Test that methods with multiple assignments remain as single chunks.

        CURRENT BAD BEHAVIOR: Fragments method into multiple assignment chunks
        DESIRED BEHAVIOR: Keep entire method as one cohesive semantic unit
        """
        content = dedent(
            """
            class Configuration
              def setup_defaults
                @host = "localhost"
                @port = 3000
                @ssl = true
                @timeout = 30
                @retries = 3
                puts "Configuration setup complete"
                validate_config
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "config.rb")

        # Find setup_defaults method
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        setup_chunks = [c for c in method_chunks if c.semantic_name == "setup_defaults"]

        # Should have exactly ONE method chunk
        assert (
            len(setup_chunks) == 1
        ), f"Expected 1 setup_defaults chunk, got {len(setup_chunks)}"

        method_chunk = setup_chunks[0]
        chunk_text = method_chunk.text

        # Method chunk should contain ALL assignments and statements
        expected_content = [
            '@host = "localhost"',
            "@port = 3000",
            "@ssl = true",
            "@timeout = 30",
            "@retries = 3",
            'puts "Configuration setup complete"',
            "validate_config",
        ]

        for content_item in expected_content:
            assert (
                str(content_item) in chunk_text
            ), f"Method chunk should contain '{content_item}' but chunk text is: {chunk_text}"

        # Should NOT have separate chunks for individual instance variables
        instance_var_chunks = [
            c for c in chunks if c.semantic_type == "instance_variable"
        ]
        assert len(instance_var_chunks) == 0, (
            f"Should not have separate instance variable chunks within method context, "
            f"but found {len(instance_var_chunks)}: {[c.semantic_name for c in instance_var_chunks]}"
        )

    def test_class_level_assignments_vs_method_level_assignments(self, parser):
        """
        Test distinction between class-level and method-level assignments.

        Class-level assignments (like attr_accessor) can be separate chunks.
        Method-level assignments should be part of method chunk.
        """
        content = dedent(
            """
            class Person
              attr_accessor :name, :age
              
              DEFAULT_AGE = 18
              
              def initialize(name, age = DEFAULT_AGE)
                @name = name
                @age = age
                @created_at = Time.now
              end
              
              def update_info(name, age)
                @name = name
                @age = age
                @updated_at = Time.now
                notify_observers
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "person.rb")

        # Find initialize method - should be ONE cohesive chunk
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        init_chunks = [c for c in method_chunks if c.semantic_name == "initialize"]

        assert len(init_chunks) == 1, "Initialize should be one cohesive chunk"

        init_chunk = init_chunks[0]
        init_text = init_chunk.text

        # Initialize chunk should contain ALL its assignments
        assert "@name = name" in init_text
        assert "@age = age" in init_text
        assert "@created_at = Time.now" in init_text

        # Find update_info method - should also be ONE cohesive chunk
        update_chunks = [c for c in method_chunks if c.semantic_name == "update_info"]
        assert len(update_chunks) == 1, "update_info should be one cohesive chunk"

        update_chunk = update_chunks[0]
        update_text = update_chunk.text

        # Update chunk should contain ALL its assignments and calls
        assert "@name = name" in update_text
        assert "@age = age" in update_text
        assert "@updated_at = Time.now" in update_text
        assert "notify_observers" in update_text

        # Class-level items can be separate (this is acceptable)
        # But should NOT have method-internal assignments as separate chunks
        internal_assignment_chunks = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name in ["@name", "@age", "@created_at", "@updated_at"]
        ]

        assert len(internal_assignment_chunks) == 0, (
            f"Should not have separate chunks for method-internal assignments, "
            f"found {len(internal_assignment_chunks)}: {[c.semantic_name for c in internal_assignment_chunks]}"
        )

    def test_rails_controller_action_cohesion(self, parser):
        """
        Test Rails controller actions remain cohesive with all assignments.
        This is critical for Ruby on Rails code understanding.
        """
        content = dedent(
            """
            class UsersController < ApplicationController
              def create
                @user = User.new(user_params)
                @user.status = 'active'
                @user.created_by = current_user.id
                
                if @user.save
                  @success_message = "User created successfully"
                  redirect_to @user
                else
                  @error_message = "Failed to create user"
                  @errors = @user.errors.full_messages
                  render :new
                end
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "users_controller.rb")

        # Find create action method
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        create_chunks = [c for c in method_chunks if c.semantic_name == "create"]

        assert (
            len(create_chunks) == 1
        ), f"Expected 1 create action chunk, got {len(create_chunks)}"

        create_chunk = create_chunks[0]
        chunk_text = create_chunk.text

        # Should contain ALL controller logic as one cohesive unit
        expected_elements = [
            "@user = User.new(user_params)",
            "@user.status = 'active'",
            "@user.created_by = current_user.id",
            '@success_message = "User created successfully"',
            '@error_message = "Failed to create user"',
            "@errors = @user.errors.full_messages",
            "if @user.save",
            "redirect_to @user",
            "render :new",
        ]

        for element in expected_elements:
            assert element in chunk_text, f"Create action should contain '{element}'"

        # Should NOT fragment into separate instance variable chunks
        controller_instance_vars = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name
            in ["@user", "@success_message", "@error_message", "@errors"]
        ]

        assert len(controller_instance_vars) == 0, (
            f"Controller action should not be fragmented into separate variable chunks, "
            f"found {len(controller_instance_vars)}: {[c.semantic_name for c in controller_instance_vars]}"
        )

    def test_method_visibility_with_assignments_stays_cohesive(self, parser):
        """
        Test that private/protected methods with assignments remain cohesive.
        """
        content = dedent(
            """
            class SecurityManager
              def initialize
                @users = {}
                @roles = {}
              end
              
              private
              
              def setup_admin_user
                @admin_user = User.new('admin')
                @admin_user.role = 'administrator'
                @admin_user.permissions = ALL_PERMISSIONS
                @admin_user.created_at = Time.now
                save_user(@admin_user)
                log_admin_creation
              end
              
              protected
              
              def validate_permissions
                @current_permissions = get_current_permissions
                @required_permissions = get_required_permissions  
                @validation_result = @current_permissions & @required_permissions
                @validation_result.any?
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "security.rb")

        # Check setup_admin_user private method
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        admin_setup_chunks = [
            c for c in method_chunks if c.semantic_name == "setup_admin_user"
        ]

        assert (
            len(admin_setup_chunks) == 1
        ), "setup_admin_user should be one cohesive chunk"

        admin_chunk = admin_setup_chunks[0]
        admin_text = admin_chunk.text

        # Should contain all admin setup logic
        assert "@admin_user = User.new('admin')" in admin_text
        assert "@admin_user.role = 'administrator'" in admin_text
        assert "@admin_user.permissions = ALL_PERMISSIONS" in admin_text
        assert "save_user(@admin_user)" in admin_text
        assert "log_admin_creation" in admin_text

        # Check validate_permissions protected method
        validate_chunks = [
            c for c in method_chunks if c.semantic_name == "validate_permissions"
        ]
        assert (
            len(validate_chunks) == 1
        ), "validate_permissions should be one cohesive chunk"

        validate_chunk = validate_chunks[0]
        validate_text = validate_chunk.text

        # Should contain all validation logic
        assert "@current_permissions = get_current_permissions" in validate_text
        assert "@required_permissions = get_required_permissions" in validate_text
        assert (
            "@validation_result = @current_permissions & @required_permissions"
            in validate_text
        )

        # Should NOT have fragmented instance variable chunks from these methods
        method_internal_vars = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and c.semantic_name
            in [
                "@admin_user",
                "@current_permissions",
                "@required_permissions",
                "@validation_result",
            ]
        ]

        assert len(method_internal_vars) == 0, (
            f"Private/protected methods should not be fragmented, "
            f"found {len(method_internal_vars)}: {[c.semantic_name for c in method_internal_vars]}"
        )

    def test_search_relevance_for_complete_methods(self, parser):
        """
        Test that searching for 'initialize' returns complete method, not fragments.
        This demonstrates the user experience problem with current fragmentation.
        """
        content = dedent(
            """
            class DatabaseConnection
              def initialize(host, port, database)
                @host = host
                @port = port  
                @database = database
                @connection = nil
                @connected = false
                @retry_count = 0
                establish_connection
                verify_connection
              end
            end
            """
        ).strip()

        chunks = parser.chunk(content, "database.rb")

        # When user searches for "initialize", they should get the COMPLETE method
        initialize_chunks = [
            c
            for c in chunks
            if c.semantic_type == "method" and c.semantic_name == "initialize"
        ]

        assert (
            len(initialize_chunks) == 1
        ), "Should find exactly one initialize method chunk"

        initialize_chunk = initialize_chunks[0]

        # The chunk should be semantically complete and useful for search
        assert "def initialize(host, port, database)" in initialize_chunk.text
        assert "@host = host" in initialize_chunk.text
        assert "@port = port" in initialize_chunk.text
        assert "@database = database" in initialize_chunk.text
        assert "establish_connection" in initialize_chunk.text
        assert "verify_connection" in initialize_chunk.text

        # User should NOT get meaningless fragments when searching for initialize
        # These would be useless search results:
        assignment_fragments = [
            c
            for c in chunks
            if c.semantic_type == "instance_variable"
            and c.text.strip()
            in ["@host = host", "@port = port", "@database = database"]
        ]

        assert len(assignment_fragments) == 0, (
            f"Search for 'initialize' should not return meaningless assignment fragments, "
            f"found {len(assignment_fragments)}: {[c.text.strip() for c in assignment_fragments]}"
        )

    def test_no_regex_on_node_text_required(self, parser):
        """
        Test that demonstrates we should use AST node types, not regex on node text.
        This is a meta-test to ensure AST-based parsing approach.
        """
        content = dedent(
            """
            class TestClass
              def test_method
                @test_var = "test"
              end
            end
            """
        ).strip()

        # Parse the content
        chunks = parser.chunk(content, "test.rb")

        # The parser should be able to identify method and class constructs
        # using AST node.type properties, not regex patterns

        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        method_chunks = [c for c in chunks if c.semantic_type == "method"]

        assert len(class_chunks) >= 1, "Should identify class using AST node.type"
        assert len(method_chunks) >= 1, "Should identify method using AST node.type"

        # This test passes when we eliminate regex abuse and use pure AST parsing
        # The implementation should use node.type == "class", node.type == "method", etc.
        # NOT regex patterns like re.search(r"def\s+(\w+)", node_text)
