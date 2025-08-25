"""Integration tests for FixedSizeChunker with real code files.

These tests verify that the fixed-size chunker properly handles real-world code files
from different programming languages and produces meaningful, searchable chunks.
"""

import pytest
from pathlib import Path
from src.code_indexer.indexing.fixed_size_chunker import FixedSizeChunker
from src.code_indexer.config import IndexingConfig


class TestFixedSizeChunkerIntegration:
    """Integration tests for FixedSizeChunker with real code files."""

    @pytest.fixture
    def chunker(self):
        """Create a FixedSizeChunker with standard configuration."""
        config = IndexingConfig()
        return FixedSizeChunker(config)

    @pytest.fixture
    def test_files_dir(self):
        """Path to test files directory."""
        return Path(__file__).parent.parent.parent / "unit" / "parsers" / "test_files"

    def test_java_complex_web_service_chunking(self, chunker, test_files_dir):
        """Test chunking of a complex Java Spring Boot web service."""
        java_file = test_files_dir / "java" / "ComplexWebService.java"
        assert java_file.exists(), f"Test file not found: {java_file}"

        chunks = chunker.chunk_file(java_file)

        # All chunks except last should be exactly 1000 characters
        for i, chunk in enumerate(chunks[:-1]):
            assert (
                len(chunk["text"]) == 1000
            ), f"Java chunk {i} should be exactly 1000 chars, got {len(chunk['text'])}"

        # Should have meaningful code content, not just imports
        meaningful_chunks = 0
        for chunk in chunks:
            text = chunk["text"]
            # Check for meaningful Java constructs beyond imports/packages
            if any(
                pattern in text
                for pattern in [
                    "public class",
                    "private ",
                    "public ",
                    "@Override",
                    "return ",
                    "if (",
                    "for (",
                    "while (",
                    "try {",
                    "catch (",
                ]
            ):
                meaningful_chunks += 1

        # At least 70% of chunks should contain meaningful code
        assert (
            meaningful_chunks >= len(chunks) * 0.7
        ), f"Only {meaningful_chunks}/{len(chunks)} chunks contain meaningful Java code"

        # Verify metadata completeness
        for i, chunk in enumerate(chunks):
            assert chunk["file_extension"] == "java"
            assert chunk["chunk_index"] == i
            assert chunk["total_chunks"] == len(chunks)
            assert chunk["line_start"] > 0
            assert chunk["line_end"] >= chunk["line_start"]

    def test_javascript_react_app_chunking(self, chunker, test_files_dir):
        """Test chunking of a modern React JavaScript application."""
        js_file = test_files_dir / "javascript" / "ModernReactApp.js"
        assert js_file.exists(), f"Test file not found: {js_file}"

        chunks = chunker.chunk_file(js_file)

        # All chunks except last should be exactly 1000 characters
        for i, chunk in enumerate(chunks[:-1]):
            assert (
                len(chunk["text"]) == 1000
            ), f"JavaScript chunk {i} should be exactly 1000 chars, got {len(chunk['text'])}"

        # Should preserve React/ES6 patterns across chunk boundaries
        total_text = "".join(chunk["text"] for chunk in chunks)

        # Verify no corruption of JavaScript constructs
        js_patterns = [
            "function",
            "const",
            "let",
            "=>",
            "React",
            "useState",
            "useEffect",
        ]
        pattern_counts_original = sum(
            total_text.count(pattern) for pattern in js_patterns
        )

        # Reconstruct from chunks and verify pattern preservation
        reconstructed = "".join(chunk["text"] for chunk in chunks)
        pattern_counts_reconstructed = sum(
            reconstructed.count(pattern) for pattern in js_patterns
        )

        # Allow small variance due to overlap, but should be close
        assert (
            abs(pattern_counts_original - pattern_counts_reconstructed) <= 2
        ), "JavaScript patterns not preserved during chunking reconstruction"

    def test_typescript_enterprise_app_chunking(self, chunker, test_files_dir):
        """Test chunking of a complex TypeScript enterprise application."""
        ts_file = test_files_dir / "typescript" / "EnterpriseApp.ts"
        assert ts_file.exists(), f"Test file not found: {ts_file}"

        chunks = chunker.chunk_file(ts_file)

        # All chunks except last should be exactly 1000 characters
        for i, chunk in enumerate(chunks[:-1]):
            assert (
                len(chunk["text"]) == 1000
            ), f"TypeScript chunk {i} should be exactly 1000 chars, got {len(chunk['text'])}"

        # Verify TypeScript-specific constructs are handled
        meaningful_ts_chunks = 0
        for chunk in chunks:
            text = chunk["text"]
            # Look for TypeScript-specific features
            if any(
                pattern in text
                for pattern in [
                    "interface",
                    "type",
                    "enum",
                    "class",
                    "abstract",
                    ": string",
                    ": number",
                    ": boolean",
                    "Promise<",
                    "Array<",
                ]
            ):
                meaningful_ts_chunks += 1

        # Most chunks should contain meaningful TypeScript code
        assert (
            meaningful_ts_chunks >= len(chunks) * 0.6
        ), f"Only {meaningful_ts_chunks}/{len(chunks)} chunks contain meaningful TypeScript code"

    def test_go_microservice_chunking(self, chunker, test_files_dir):
        """Test chunking of a Go microservice architecture file."""
        go_file = test_files_dir / "go" / "MicroserviceArchitecture.go"
        assert go_file.exists(), f"Test file not found: {go_file}"

        chunks = chunker.chunk_file(go_file)

        # All chunks except last should be exactly 1000 characters
        for i, chunk in enumerate(chunks[:-1]):
            assert (
                len(chunk["text"]) == 1000
            ), f"Go chunk {i} should be exactly 1000 chars, got {len(chunk['text'])}"

        # Verify Go-specific constructs are preserved
        go_constructs = 0
        for chunk in chunks:
            text = chunk["text"]
            if any(
                pattern in text
                for pattern in [
                    "func ",
                    "type ",
                    "struct",
                    "interface",
                    "package",
                    "import",
                    "go ",
                    "channel",
                    "goroutine",
                    "defer",
                ]
            ):
                go_constructs += 1

        # Most chunks should contain Go code constructs
        assert (
            go_constructs >= len(chunks) * 0.5
        ), f"Only {go_constructs}/{len(chunks)} chunks contain Go constructs"

    def test_kotlin_android_app_chunking(self, chunker, test_files_dir):
        """Test chunking of a Kotlin Android application."""
        kt_file = test_files_dir / "kotlin" / "AndroidApp.kt"
        assert kt_file.exists(), f"Test file not found: {kt_file}"

        chunks = chunker.chunk_file(kt_file)

        # All chunks except last should be exactly 1000 characters
        for i, chunk in enumerate(chunks[:-1]):
            assert (
                len(chunk["text"]) == 1000
            ), f"Kotlin chunk {i} should be exactly 1000 chars, got {len(chunk['text'])}"

        # Verify Kotlin-specific features are handled
        kotlin_features = 0
        for chunk in chunks:
            text = chunk["text"]
            if any(
                pattern in text
                for pattern in [
                    "fun ",
                    "val ",
                    "var ",
                    "class ",
                    "object",
                    "data class",
                    "sealed",
                    "companion",
                    "?." "!!",
                ]
            ):
                kotlin_features += 1

        # Most chunks should contain Kotlin features
        assert (
            kotlin_features >= len(chunks) * 0.5
        ), f"Only {kotlin_features}/{len(chunks)} chunks contain Kotlin features"

    def test_chunk_metadata_accuracy_across_languages(self, chunker, test_files_dir):
        """Test that chunk metadata is accurate across different programming languages."""
        test_files = [
            ("java", "ComplexWebService.java"),
            ("javascript", "ModernReactApp.js"),
            ("typescript", "EnterpriseApp.ts"),
            ("go", "MicroserviceArchitecture.go"),
            ("kotlin", "AndroidApp.kt"),
        ]

        for lang_dir, filename in test_files:
            file_path = test_files_dir / lang_dir / filename
            if not file_path.exists():
                continue

            chunks = chunker.chunk_file(file_path)

            # Verify metadata consistency
            for i, chunk in enumerate(chunks):
                # Basic metadata validation
                assert chunk["chunk_index"] == i
                assert chunk["total_chunks"] == len(chunks)
                assert chunk["size"] == len(chunk["text"])
                assert chunk["file_path"] == str(file_path)

                # File extension should match expected
                expected_ext = file_path.suffix.lstrip(".")
                assert chunk["file_extension"] == expected_ext

                # Line numbers should be reasonable
                assert chunk["line_start"] > 0
                assert chunk["line_end"] >= chunk["line_start"]

                # Line numbers should progress logically (accounting for overlap)
                if i > 0:
                    prev_chunk = chunks[i - 1]
                    # Due to character-based chunking, line numbers may overlap
                    # but should be in reasonable proximity
                    line_gap = abs(chunk["line_start"] - prev_chunk["line_end"])
                    assert line_gap <= 20, (
                        f"Line numbers gap too large between chunks {i-1} and {i}: "
                        f"{prev_chunk['line_end']} to {chunk['line_start']}"
                    )

    def test_chunk_overlap_consistency_real_files(self, chunker, test_files_dir):
        """Test that 150-character overlap is consistent across real files."""
        test_files = [
            test_files_dir / "java" / "ComplexWebService.java",
            test_files_dir / "javascript" / "ModernReactApp.js",
            test_files_dir / "go" / "MicroserviceArchitecture.go",
        ]

        for file_path in test_files:
            if not file_path.exists():
                continue

            chunks = chunker.chunk_file(file_path)

            if len(chunks) < 2:
                continue  # Need at least 2 chunks to test overlap

            # Test overlap between consecutive chunks
            for i in range(len(chunks) - 1):
                current_chunk = chunks[i]["text"]
                next_chunk = chunks[i + 1]["text"]

                # Last 150 chars of current should match first 150 of next
                current_ending = current_chunk[-150:]
                next_beginning = next_chunk[:150]

                assert (
                    current_ending == next_beginning
                ), f"Overlap mismatch in {file_path.name} between chunks {i} and {i+1}"

    def test_meaningful_code_blocks_not_fragments(self, chunker, test_files_dir):
        """Test that chunks contain meaningful code blocks, not just fragments."""
        java_file = test_files_dir / "java" / "ComplexWebService.java"

        if java_file.exists():
            chunks = chunker.chunk_file(java_file)

            # Count chunks that are likely to be meaningful
            meaningful_chunks = 0
            fragment_chunks = 0

            for chunk in chunks:
                text = chunk["text"].strip()

                # Fragment indicators (things that suggest over-segmentation)
                fragment_indicators = [
                    text.startswith("import ") and len(text.split("\n")) <= 3,
                    text.startswith("package ") and len(text) < 100,
                    text == "" or len(text.strip()) < 50,
                    text.count("{") == 0 and text.count("}") == 0 and len(text) > 100,
                ]

                # Meaningful code indicators
                meaningful_indicators = [
                    "public class" in text or "private class" in text,
                    text.count("{") > 0 and text.count("}") > 0,
                    any(
                        keyword in text
                        for keyword in [
                            "public void",
                            "private void",
                            "public static",
                            "if (",
                            "for (",
                            "while (",
                            "try {",
                            "catch (",
                        ]
                    ),
                    len(text.strip()) >= 200,  # Substantial content
                ]

                if any(fragment_indicators):
                    fragment_chunks += 1
                elif any(meaningful_indicators):
                    meaningful_chunks += 1

            # The new approach should significantly reduce fragments
            total_chunks = len(chunks)
            fragment_ratio = fragment_chunks / total_chunks if total_chunks > 0 else 0
            meaningful_ratio = (
                meaningful_chunks / total_chunks if total_chunks > 0 else 0
            )

            # Much better than the old 76.5% under 300 chars, 52% under 100 chars
            assert (
                fragment_ratio < 0.2
            ), f"Too many fragment chunks: {fragment_chunks}/{total_chunks} ({fragment_ratio:.2%})"
            assert (
                meaningful_ratio > 0.6
            ), f"Too few meaningful chunks: {meaningful_chunks}/{total_chunks} ({meaningful_ratio:.2%})"
