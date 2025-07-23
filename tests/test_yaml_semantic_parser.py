"""
Tests for YAML semantic parser.
Following TDD - writing comprehensive tests first.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestYAMLSemanticParser:
    """Test YAML-specific semantic parsing."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create a YAML parser directly."""
        from code_indexer.indexing.yaml_parser import YamlSemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return YamlSemanticParser(config)

    def test_basic_yaml_structure(self, chunker):
        """Test parsing of basic YAML key-value pairs."""
        content = dedent(
            """
            name: MyApplication
            version: 1.2.3
            description: A sample application configuration
            debug: true
            port: 8080
            database:
              host: localhost
              port: 5432
              name: myapp_db
            """
        ).strip()

        chunks = chunker.chunk_content(content, "config.yaml")

        # Should have chunks for key-value pairs and nested structures
        assert len(chunks) >= 4

        # Check basic key-value pairs
        pair_chunks = [c for c in chunks if c["semantic_type"] == "pair"]
        assert len(pair_chunks) >= 4

        # Check name pair
        name_chunks = [c for c in pair_chunks if c["semantic_name"] == "name"]
        assert len(name_chunks) >= 1
        name_chunk = name_chunks[0]
        assert name_chunk["semantic_context"]["value"] == "MyApplication"
        assert "value_type_string" in name_chunk["semantic_language_features"]

        # Check port pair
        port_chunks = [c for c in pair_chunks if c["semantic_name"] == "port"]
        assert len(port_chunks) >= 1
        port_chunk = port_chunks[0]
        assert "value_type_integer" in port_chunk["semantic_language_features"]

        # Check debug pair
        debug_chunks = [c for c in pair_chunks if c["semantic_name"] == "debug"]
        assert len(debug_chunks) >= 1
        debug_chunk = debug_chunks[0]
        assert "value_type_boolean" in debug_chunk["semantic_language_features"]

    def test_yaml_nested_mappings(self, chunker):
        """Test parsing of nested YAML mappings."""
        content = dedent(
            """
            server:
              host: 0.0.0.0
              port: 8080
              ssl:
                enabled: true
                cert_file: /path/to/cert.pem
                key_file: /path/to/key.pem
            
            logging:
              level: INFO
              handlers:
                console:
                  enabled: true
                  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                file:
                  enabled: false
                  path: /var/log/app.log
            """
        ).strip()

        chunks = chunker.chunk_content(content, "nested.yaml")

        # Check top-level mappings
        mapping_chunks = [c for c in chunks if c["semantic_type"] == "mapping"]
        assert len(mapping_chunks) >= 2  # server and logging sections

        # Check server mapping
        server_chunks = [c for c in mapping_chunks if "server" in c["semantic_name"]]
        assert len(server_chunks) >= 1
        server_chunk = server_chunks[0]
        assert "block_mapping" in server_chunk["semantic_language_features"]

        # Check nested structure - SSL configuration
        ssl_pairs = [
            c
            for c in chunks
            if c["semantic_name"] == "ssl" and c["semantic_type"] == "pair"
        ]
        if ssl_pairs:
            assert "value_type_mapping" in ssl_pairs[0]["semantic_language_features"]

        # Check deeply nested values
        cert_pairs = [c for c in chunks if c["semantic_name"] == "cert_file"]
        assert len(cert_pairs) >= 1
        cert_chunk = cert_pairs[0]
        assert "/path/to/cert.pem" in cert_chunk["semantic_context"]["value"]

    def test_yaml_sequences_and_arrays(self, chunker):
        """Test parsing of YAML sequences (arrays)."""
        content = dedent(
            """
            fruits:
              - apple
              - banana
              - orange
              - strawberry
            
            shopping_list:
              - item: milk
                quantity: 2
                urgent: true
              - item: bread
                quantity: 1
                urgent: false
              - item: eggs
                quantity: 12
                urgent: true
            
            simple_numbers: [1, 2, 3, 4, 5]
            mixed_array: ["string", 42, true, null]
            """
        ).strip()

        chunks = chunker.chunk_content(content, "sequences.yaml")

        # Check sequence chunks
        sequence_chunks = [
            c for c in chunks if c["semantic_type"] in ["sequence", "flow_sequence"]
        ]
        assert len(sequence_chunks) >= 3

        # Check block sequence
        block_sequences = [
            c
            for c in sequence_chunks
            if "block_sequence" in c["semantic_language_features"]
        ]
        assert len(block_sequences) >= 2

        # Check fruits sequence
        fruits_seq = [c for c in sequence_chunks if "4_items" in c["semantic_name"]]
        assert len(fruits_seq) >= 1
        fruits_chunk = fruits_seq[0]
        assert fruits_chunk["semantic_context"]["item_count"] == 4
        assert "array" in fruits_chunk["semantic_language_features"]

        # Check flow sequence (inline array)
        flow_sequences = [
            c
            for c in sequence_chunks
            if "flow_sequence" in c["semantic_language_features"]
        ]
        assert len(flow_sequences) >= 2

        flow_seq = flow_sequences[0]
        assert "inline_array" in flow_seq["semantic_language_features"]

    def test_yaml_flow_style(self, chunker):
        """Test parsing of YAML flow style (JSON-like syntax)."""
        content = dedent(
            """
            person: {name: "John Doe", age: 30, city: "New York"}
            coordinates: {x: 10.5, y: 20.3, z: 0}
            tags: ["web", "api", "json", "yaml"]
            config: {
              database: {host: "localhost", port: 5432},
              cache: {enabled: true, ttl: 3600},
              features: ["auth", "logging", "metrics"]
            }
            """
        ).strip()

        chunks = chunker.chunk_content(content, "flow.yaml")

        # Check flow mappings
        flow_mapping_chunks = [
            c for c in chunks if c["semantic_type"] == "flow_mapping"
        ]
        assert len(flow_mapping_chunks) >= 3  # person, coordinates, config objects

        # Check person flow mapping
        person_mappings = [
            c for c in flow_mapping_chunks if "3_keys" in c["semantic_name"]
        ]
        assert len(person_mappings) >= 1
        person_chunk = person_mappings[0]
        assert "flow_mapping" in person_chunk["semantic_language_features"]
        assert "inline_mapping" in person_chunk["semantic_language_features"]
        assert person_chunk["semantic_context"]["key_count"] == 3

        # Check flow sequences
        flow_seq_chunks = [c for c in chunks if c["semantic_type"] == "flow_sequence"]
        assert len(flow_seq_chunks) >= 2  # tags and features arrays

        tags_seq = [c for c in flow_seq_chunks if "4_items" in c["semantic_name"]]
        assert len(tags_seq) >= 1
        assert "inline_array" in tags_seq[0]["semantic_language_features"]

    def test_yaml_anchors_and_aliases(self, chunker):
        """Test parsing of YAML anchors and aliases."""
        content = dedent(
            """
            defaults: &default_config
              timeout: 30
              retries: 3
              logging: true
            
            development:
              <<: *default_config
              debug: true
              database:
                host: localhost
                port: 5432
            
            production:
              <<: *default_config
              debug: false
              database:
                host: prod.example.com
                port: 5432
            
            test_config: *default_config
            """
        ).strip()

        chunks = chunker.chunk_content(content, "anchors.yaml")

        # Check for anchor chunks
        anchor_chunks = [c for c in chunks if c["semantic_type"] == "anchor"]
        assert len(anchor_chunks) >= 1
        anchor_chunk = anchor_chunks[0]
        assert anchor_chunk["semantic_name"] == "default_config"
        assert "yaml_anchor" in anchor_chunk["semantic_language_features"]
        assert "reference_definition" in anchor_chunk["semantic_language_features"]

        # Check for alias chunks
        alias_chunks = [c for c in chunks if c["semantic_type"] == "alias"]
        assert len(alias_chunks) >= 1
        alias_chunk = alias_chunks[0]
        assert "yaml_alias" in alias_chunk["semantic_language_features"]
        assert "reference_usage" in alias_chunk["semantic_language_features"]

    def test_yaml_multiline_strings(self, chunker):
        """Test parsing of YAML multiline strings."""
        content = dedent(
            """
            description: |
              This is a literal block scalar.
              It preserves newlines and formatting.
              Each line is kept as-is.
            
            summary: >
              This is a folded block scalar.
              Long lines are folded into a single line.
              Only paragraph breaks are preserved.
            
            code: |2
                def hello():
                    print("Hello, World!")
                    return True
            
            single_line: "This is a regular string"
            quoted_multiline: "This string spans
              multiple lines but is
              still a single string"
            """
        ).strip()

        chunks = chunker.chunk_content(content, "multiline.yaml")

        # Check for multiline string pairs
        pair_chunks = [c for c in chunks if c["semantic_type"] == "pair"]

        # Check literal block scalar
        description_pairs = [
            c for c in pair_chunks if c["semantic_name"] == "description"
        ]
        assert len(description_pairs) >= 1
        desc_chunk = description_pairs[0]
        assert (
            "value_type_block_scalar" in desc_chunk["semantic_language_features"]
            or "value_type_string" in desc_chunk["semantic_language_features"]
        )

        # Check folded block scalar
        summary_pairs = [c for c in pair_chunks if c["semantic_name"] == "summary"]
        assert len(summary_pairs) >= 1

        # Check indented literal block
        code_pairs = [c for c in pair_chunks if c["semantic_name"] == "code"]
        assert len(code_pairs) >= 1

    def test_yaml_comments(self, chunker):
        """Test parsing of YAML comments."""
        content = dedent(
            """
            # Main application configuration
            name: MyApp
            version: 1.0.0  # Application version
            
            # Database configuration section
            database:
              host: localhost  # Development host
              port: 5432
              # Connection pool settings
              pool:
                min_size: 5
                max_size: 20
            
            # Features to enable
            features:
              - auth    # Authentication module
              - logging # Logging system
              - metrics # Performance metrics
            """
        ).strip()

        chunks = chunker.chunk_content(content, "comments.yaml")

        # Check for comment chunks
        comment_chunks = [c for c in chunks if c["semantic_type"] == "comment"]
        assert len(comment_chunks) >= 4  # Several comments in the file

        # Check main comment
        main_comments = [
            c
            for c in comment_chunks
            if "Main application" in c["semantic_context"]["comment_content"]
        ]
        assert len(main_comments) >= 1
        main_comment = main_comments[0]
        assert "yaml_comment" in main_comment["semantic_language_features"]

        # Check inline comments
        version_comments = [
            c
            for c in comment_chunks
            if "version" in c["semantic_context"]["comment_content"]
        ]
        assert len(version_comments) >= 1

    def test_yaml_documents_and_directives(self, chunker):
        """Test parsing of YAML documents with directives."""
        content = dedent(
            """
            %YAML 1.2
            %TAG ! tag:example.com,2000:app/
            ---
            name: Document 1
            type: configuration
            ---
            name: Document 2
            type: data
            items:
              - item1
              - item2
            ...
            """
        ).strip()

        chunks = chunker.chunk_content(content, "documents.yaml")

        # Check for directive chunks
        directive_chunks = [c for c in chunks if c["semantic_type"] == "directive"]
        assert len(directive_chunks) >= 1  # At least YAML directive

        yaml_directive = [c for c in directive_chunks if c["semantic_name"] == "YAML"]
        assert len(yaml_directive) >= 1
        yaml_dir = yaml_directive[0]
        assert "yaml_directive" in yaml_dir["semantic_language_features"]
        assert yaml_dir["semantic_context"]["directive_value"] == "1.2"

        # Check for document separators (implicit in document chunks)
        doc_chunks = [c for c in chunks if c["semantic_type"] == "document"]
        if doc_chunks:
            assert len(doc_chunks) >= 1
            assert "yaml_document" in doc_chunks[0]["semantic_language_features"]

    def test_yaml_complex_data_types(self, chunker):
        """Test parsing of complex YAML data types."""
        content = dedent(
            """
            # Various data types
            string_value: "Hello World"
            integer_value: 42
            float_value: 3.14159
            boolean_true: true
            boolean_false: false
            null_value: null
            empty_value: ""
            
            # Timestamps and special values
            timestamp: 2023-01-01T12:00:00Z
            date: 2023-01-01
            
            # Binary data (base64)
            binary_data: !!binary |
              R0lGODlhDAAMAIQAAP//9/X17unp5WZmZgAAAOfn515eXvPz7Y6OjuDg4J+fn5
              OTk6enp56enmlpaWNjY6Ojo4SEhP/++f/++f/++f/++f/++f/++f/++f/++f/++
              f/++f/++f/++f/++f/++SH+Dk1hZGUgd2l0aCBHSU1QACwAAAAADAAMAAAFLC
            
            # Complex nested structure
            application:
              metadata:
                created: &creation_date "2023-01-01"
                modified: *creation_date
                tags: [v1.0, stable, production]
              settings:
                cache: {enabled: true, ttl: 3600, size: "100MB"}
                logging: {level: INFO, format: json}
            """
        ).strip()

        chunks = chunker.chunk_content(content, "complex.yaml")

        # Check various data types
        pair_chunks = [c for c in chunks if c["semantic_type"] == "pair"]

        # Check different value types
        string_pairs = [
            c
            for c in pair_chunks
            if "value_type_string" in c["semantic_language_features"]
        ]
        integer_pairs = [
            c
            for c in pair_chunks
            if "value_type_integer" in c["semantic_language_features"]
        ]
        float_pairs = [
            c
            for c in pair_chunks
            if "value_type_float" in c["semantic_language_features"]
        ]
        boolean_pairs = [
            c
            for c in pair_chunks
            if "value_type_boolean" in c["semantic_language_features"]
        ]

        assert len(string_pairs) >= 2
        assert len(integer_pairs) >= 1
        assert len(float_pairs) >= 1
        assert len(boolean_pairs) >= 2

        # Check complex nested structures
        mapping_chunks = [c for c in chunks if c["semantic_type"] == "mapping"]
        assert len(mapping_chunks) >= 2  # application, metadata, settings

    def test_error_node_fallback(self, chunker):
        """Test ERROR node handling with regex fallback."""
        # Malformed YAML that might create ERROR nodes
        content = dedent(
            """
            good_key: good_value
            another_key: another_value
            
            # This might cause parsing errors
            broken_indent:
              - item1
                - badly_indented_item
            good_key2: value2
            
            # Missing colon
            bad_syntax
              value: test
            
            final_key: final_value
            """
        ).strip()

        chunks = chunker.chunk_content(content, "broken.yaml")

        # Should still extract meaningful content even with errors
        assert len(chunks) >= 3

        # Check that good pairs are still parsed
        pair_chunks = [c for c in chunks if c["semantic_type"] == "pair"]
        good_pairs = [c for c in pair_chunks if "good" in c["semantic_name"]]
        assert len(good_pairs) >= 2

        # Check that comments are preserved
        comment_chunks = [c for c in chunks if c["semantic_type"] == "comment"]
        assert len(comment_chunks) >= 1

    def test_yaml_configuration_patterns(self, chunker):
        """Test parsing of common YAML configuration patterns."""
        content = dedent(
            """
            # Application configuration
            app_name: MyApplication
            version: "1.0.0"
            environment: development
            
            # Server configuration
            server:
              host: 0.0.0.0
              port: 8080
              workers: 4
            
            # Database configuration
            databases:
              primary:
                engine: postgresql
                host: localhost
                port: 5432
                name: myapp
                credentials:
                  username: admin
                  password: secret
              redis:
                host: localhost
                port: 6379
                db: 0
            
            # Feature flags
            features:
              authentication: true
              rate_limiting: false
              metrics_collection: true
            
            # Environment-specific overrides
            overrides:
              production:
                server:
                  workers: 8
                databases:
                  primary:
                    host: prod-db.example.com
            """
        ).strip()

        chunks = chunker.chunk_content(content, "app_config.yaml")

        # Check configuration-related features
        pair_chunks = [c for c in chunks if c["semantic_type"] == "pair"]
        config_pairs = [
            c for c in pair_chunks if "configuration" in c["semantic_language_features"]
        ]
        assert (
            len(config_pairs) >= 5
        )  # app_name, version, environment, host, port, etc.

        # Check nested configuration sections
        mapping_chunks = [c for c in chunks if c["semantic_type"] == "mapping"]
        assert len(mapping_chunks) >= 4  # server, databases, features, overrides

        # Check that mappings have appropriate sizes
        large_mappings = [
            c
            for c in mapping_chunks
            if "large_mapping" in c["semantic_language_features"]
        ]
        if large_mappings:
            assert len(large_mappings) >= 1

    def test_fallback_parsing(self, chunker):
        """Test complete fallback parsing when tree-sitter fails."""
        # Extremely malformed YAML
        content = dedent(
            """
            good_key: value
            
            << completely broken syntax >>
            
            # comment
            
            another_key: another_value
            """
        ).strip()

        chunks = chunker.chunk_content(content, "broken.yaml")

        # Should create at least a fallback chunk
        assert len(chunks) >= 1

        # If fallback chunk is created, it should have document type
        if len(chunks) == 1 and chunks[0]["semantic_type"] == "document":
            assert chunks[0]["semantic_name"] == "broken"
            assert "fallback_chunk" in chunks[0]["semantic_language_features"]
        else:
            # Or should extract what it can
            pair_chunks = [c for c in chunks if c["semantic_type"] == "pair"]
            comment_chunks = [c for c in chunks if c["semantic_type"] == "comment"]
            assert len(pair_chunks) >= 1 or len(comment_chunks) >= 1

    def test_yaml_kubernetes_manifest(self, chunker):
        """Test parsing of a Kubernetes-style YAML manifest."""
        content = dedent(
            """
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: nginx-deployment
              namespace: default
              labels:
                app: nginx
                version: "1.0"
            spec:
              replicas: 3
              selector:
                matchLabels:
                  app: nginx
              template:
                metadata:
                  labels:
                    app: nginx
                spec:
                  containers:
                  - name: nginx
                    image: nginx:1.20
                    ports:
                    - containerPort: 80
                      protocol: TCP
                    env:
                    - name: ENV_VAR
                      value: "production"
                    resources:
                      requests:
                        memory: "64Mi"
                        cpu: "250m"
                      limits:
                        memory: "128Mi"
                        cpu: "500m"
            """
        ).strip()

        chunks = chunker.chunk_content(content, "k8s-deployment.yaml")

        # Should parse the complex nested structure
        assert len(chunks) >= 10

        # Check top-level API fields
        api_pairs = [c for c in chunks if c["semantic_name"] in ["apiVersion", "kind"]]
        assert len(api_pairs) >= 2

        # Check metadata section
        metadata_mappings = [c for c in chunks if "metadata" in c["semantic_name"]]
        assert len(metadata_mappings) >= 1

        # Check spec section with complex nesting
        spec_mappings = [c for c in chunks if "spec" in c["semantic_name"]]
        assert len(spec_mappings) >= 1

        # Check arrays in containers
        sequence_chunks = [
            c for c in chunks if c["semantic_type"] in ["sequence", "flow_sequence"]
        ]
        assert len(sequence_chunks) >= 3  # containers, ports, env arrays
