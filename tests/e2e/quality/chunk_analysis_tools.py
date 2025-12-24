"""Chunk analysis tools for Story 7: Validate Search Quality Improvement.

This module provides utilities to analyze chunk distribution and quality
to validate the improvements from fixed-size chunking over the old AST approach.
"""

from typing import List, Dict, Any, Tuple, Optional
import statistics
from pathlib import Path
from dataclasses import dataclass

from code_indexer.indexing.fixed_size_chunker import FixedSizeChunker
from code_indexer.config import IndexingConfig


@dataclass
class ChunkDistributionAnalysis:
    """Analysis results for chunk size distribution."""

    total_chunks: int
    average_size: float
    median_size: float
    min_size: int
    max_size: int
    under_100_count: int
    under_100_percent: float
    under_300_count: int
    under_300_percent: float
    under_1000_count: int
    under_1000_percent: float
    exactly_1000_count: int
    exactly_1000_percent: float


@dataclass
class SearchQualityMetrics:
    """Metrics for evaluating search quality improvements."""

    meaningful_chunks_count: int
    fragment_chunks_count: int
    meaningful_percentage: float
    average_context_length: float
    complete_methods_count: int
    incomplete_methods_count: int


class ChunkAnalyzer:
    """Tool for analyzing chunk quality and distribution."""

    def __init__(self, config: IndexingConfig = None):
        """Initialize chunk analyzer."""
        if config is None:
            config = IndexingConfig()
        self.chunker = FixedSizeChunker(config)

    def analyze_chunk_distribution(
        self, chunks: List[Dict[str, Any]]
    ) -> ChunkDistributionAnalysis:
        """Analyze the size distribution of chunks.

        Args:
            chunks: List of chunk dictionaries with 'size' field

        Returns:
            Analysis of chunk size distribution
        """
        if not chunks:
            return ChunkDistributionAnalysis(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        sizes = [chunk["size"] for chunk in chunks]

        # Basic statistics
        total_chunks = len(sizes)
        average_size = statistics.mean(sizes)
        median_size = statistics.median(sizes)
        min_size = min(sizes)
        max_size = max(sizes)

        # Count chunks by size thresholds
        under_100_count = sum(1 for size in sizes if size < 100)
        under_300_count = sum(1 for size in sizes if size < 300)
        under_1000_count = sum(1 for size in sizes if size < 1000)
        exactly_1000_count = sum(1 for size in sizes if size == 1000)

        # Calculate percentages
        under_100_percent = (under_100_count / total_chunks) * 100
        under_300_percent = (under_300_count / total_chunks) * 100
        under_1000_percent = (under_1000_count / total_chunks) * 100
        exactly_1000_percent = (exactly_1000_count / total_chunks) * 100

        return ChunkDistributionAnalysis(
            total_chunks=total_chunks,
            average_size=average_size,
            median_size=median_size,
            min_size=min_size,
            max_size=max_size,
            under_100_count=under_100_count,
            under_100_percent=under_100_percent,
            under_300_count=under_300_count,
            under_300_percent=under_300_percent,
            under_1000_count=under_1000_count,
            under_1000_percent=under_1000_percent,
            exactly_1000_count=exactly_1000_count,
            exactly_1000_percent=exactly_1000_percent,
        )

    def analyze_search_quality(
        self, chunks: List[Dict[str, Any]]
    ) -> SearchQualityMetrics:
        """Analyze the quality of chunks for search purposes.

        Args:
            chunks: List of chunk dictionaries

        Returns:
            Analysis of search quality metrics
        """
        if not chunks:
            return SearchQualityMetrics(0, 0, 0, 0, 0, 0)

        meaningful_chunks = 0
        fragment_chunks = 0
        context_lengths = []
        complete_methods = 0
        incomplete_methods = 0

        for chunk in chunks:
            text = chunk["text"].strip()

            # Skip empty chunks
            if not text:
                fragment_chunks += 1
                continue

            # Measure context length
            context_lengths.append(len(text))

            # Check if chunk contains meaningful code vs fragments
            is_meaningful = self._is_meaningful_chunk(text)

            if is_meaningful:
                meaningful_chunks += 1
            else:
                fragment_chunks += 1

            # Check for method completeness
            method_analysis = self._analyze_method_completeness(text)
            complete_methods += method_analysis["complete"]
            incomplete_methods += method_analysis["incomplete"]

        total_chunks = len(chunks)
        meaningful_percentage = (meaningful_chunks / total_chunks) * 100
        average_context_length = (
            statistics.mean(context_lengths) if context_lengths else 0
        )

        return SearchQualityMetrics(
            meaningful_chunks_count=meaningful_chunks,
            fragment_chunks_count=fragment_chunks,
            meaningful_percentage=meaningful_percentage,
            average_context_length=average_context_length,
            complete_methods_count=complete_methods,
            incomplete_methods_count=incomplete_methods,
        )

    def _is_meaningful_chunk(self, text: str) -> bool:
        """Determine if a chunk contains meaningful code vs fragments.

        A meaningful chunk should:
        - Be long enough to provide context (> 200 chars)
        - Contain more than just imports or package declarations
        - Have some logical structure or implementation
        """
        # Too short to be meaningful
        if len(text) < 200:
            return False

        lines = text.split("\n")
        code_lines = [
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("#")
        ]

        if len(code_lines) < 3:
            return False

        # Check for fragment indicators
        fragment_patterns = [
            # Just imports/packages
            lambda lines: all(
                line.startswith(("import ", "from ", "package ", "using "))
                or line in ["", "{", "}", "/**", "*/"]
                or line.startswith(("*", "//", "/*"))
                for line in lines
            ),
            # Just variable declarations
            lambda lines: all(
                "=" in line and ";" in line and len(line.split()) < 5
                for line in lines
                if line and not line.startswith(("import", "from", "package"))
            ),
            # Just class/interface declarations without implementation
            lambda lines: len(
                [
                    line
                    for line in lines
                    if any(
                        keyword in line
                        for keyword in [
                            "class ",
                            "interface ",
                            "struct ",
                            "def ",
                            "function ",
                        ]
                    )
                ]
            )
            > 0
            and len(
                [
                    line
                    for line in lines
                    if "{" in line or "return " in line or "if " in line
                ]
            )
            == 0,
        ]

        # If any fragment pattern matches, it's not meaningful
        for pattern in fragment_patterns:
            if pattern(code_lines):
                return False

        return True

    def _analyze_method_completeness(self, text: str) -> Dict[str, int]:
        """Analyze if methods in the chunk are complete or fragmented."""
        complete_methods = 0
        incomplete_methods = 0

        # Simple heuristics for method completeness
        # This is language-agnostic pattern matching

        # Look for method definitions
        method_patterns = [
            "def ",
            "function ",
            "public ",
            "private ",
            "protected ",
            "static ",
        ]
        method_starts = []

        lines = text.split("\n")
        for i, line in enumerate(lines):
            if (
                any(pattern in line.lower() for pattern in method_patterns)
                and "(" in line
            ):
                method_starts.append(i)

        # For each method start, check if it has implementation
        for start_line in method_starts:
            has_implementation = False
            has_return = False
            brace_count = 0

            # Look for implementation indicators in following lines
            for i in range(start_line + 1, min(len(lines), start_line + 20)):
                line = lines[i].strip()
                if not line:
                    continue

                # Count braces to track method body
                brace_count += line.count("{") - line.count("}")

                # Look for implementation indicators
                if any(
                    keyword in line.lower()
                    for keyword in [
                        "return ",
                        "if ",
                        "for ",
                        "while ",
                        "try ",
                        "throw ",
                        "new ",
                        "=",
                        "print",
                    ]
                ):
                    has_implementation = True

                if "return " in line.lower():
                    has_return = True

                # If we've closed all braces, method is likely complete
                if brace_count <= 0 and has_implementation:
                    break

            # Determine if method is complete
            if has_implementation and (has_return or brace_count <= 0):
                complete_methods += 1
            else:
                incomplete_methods += 1

        return {"complete": complete_methods, "incomplete": incomplete_methods}

    def analyze_file_chunking(
        self, file_path: Path
    ) -> Tuple[ChunkDistributionAnalysis, SearchQualityMetrics]:
        """Analyze chunking quality for a specific file.

        Args:
            file_path: Path to file to analyze

        Returns:
            Tuple of (distribution analysis, quality metrics)
        """
        chunks = self.chunker.chunk_file(file_path)
        distribution = self.analyze_chunk_distribution(chunks)
        quality = self.analyze_search_quality(chunks)
        return distribution, quality

    def analyze_directory_chunking(
        self, directory: Path, file_patterns: Optional[List[str]] = None
    ) -> Tuple[ChunkDistributionAnalysis, SearchQualityMetrics]:
        """Analyze chunking quality for all files in a directory.

        Args:
            directory: Directory to analyze
            file_patterns: List of file patterns to include (e.g., ['*.py', '*.java'])

        Returns:
            Tuple of (combined distribution analysis, combined quality metrics)
        """
        if file_patterns is None:
            file_patterns = [
                "*.py",
                "*.java",
                "*.js",
                "*.ts",
                "*.go",
                "*.cpp",
                "*.c",
                "*.cs",
            ]

        all_chunks = []

        for pattern in file_patterns:
            for file_path in directory.glob(f"**/{pattern}"):
                if file_path.is_file():
                    try:
                        chunks = self.chunker.chunk_file(file_path)
                        all_chunks.extend(chunks)
                    except Exception as e:
                        # Skip files that can't be processed
                        print(f"Warning: Could not process {file_path}: {e}")
                        continue

        distribution = self.analyze_chunk_distribution(all_chunks)
        quality = self.analyze_search_quality(all_chunks)
        return distribution, quality

    def compare_with_old_approach_metrics(
        self, current_analysis: ChunkDistributionAnalysis
    ) -> Dict[str, Any]:
        """Compare current results with old AST approach metrics.

        Old approach had:
        - 76.5% chunks under 300 chars
        - 52% chunks under 100 chars
        - 549 average chunk size

        Args:
            current_analysis: Current chunk distribution analysis

        Returns:
            Dictionary with comparison results and improvement metrics
        """
        # Old approach baseline metrics
        old_under_300_percent = 76.5
        old_under_100_percent = 52.0
        old_average_size = 549

        # Calculate improvements
        under_300_improvement = (
            old_under_300_percent - current_analysis.under_300_percent
        )
        under_100_improvement = (
            old_under_100_percent - current_analysis.under_100_percent
        )
        average_size_improvement = current_analysis.average_size - old_average_size

        return {
            "old_metrics": {
                "under_300_percent": old_under_300_percent,
                "under_100_percent": old_under_100_percent,
                "average_size": old_average_size,
            },
            "current_metrics": {
                "under_300_percent": current_analysis.under_300_percent,
                "under_100_percent": current_analysis.under_100_percent,
                "average_size": current_analysis.average_size,
            },
            "improvements": {
                "under_300_reduction": under_300_improvement,
                "under_100_reduction": under_100_improvement,
                "average_size_increase": average_size_improvement,
                "under_300_improvement_ratio": (
                    under_300_improvement / old_under_300_percent
                    if old_under_300_percent > 0
                    else 0
                ),
                "under_100_improvement_ratio": (
                    under_100_improvement / old_under_100_percent
                    if old_under_100_percent > 0
                    else 0
                ),
                "average_size_improvement_ratio": (
                    average_size_improvement / old_average_size
                    if old_average_size > 0
                    else 0
                ),
            },
            "meets_story7_requirements": {
                # For small files with few chunks, allow higher percentage of under-1000 chunks
                # For larger codebases, this percentage should be much lower
                "under_1000_except_final": (
                    current_analysis.under_1000_percent <= 50
                    if current_analysis.total_chunks <= 5
                    else current_analysis.under_1000_percent <= 10
                ),
                "massive_improvement_under_300": under_300_improvement
                >= 60,  # At least 60% improvement
                "massive_improvement_under_100": under_100_improvement
                >= 40,  # At least 40% improvement
                "average_size_near_1000": current_analysis.average_size
                >= 800,  # Close to target 1000
            },
        }

    def generate_report(
        self,
        analysis: ChunkDistributionAnalysis,
        quality: SearchQualityMetrics,
        comparison: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate a comprehensive report of the chunk analysis.

        Args:
            analysis: Chunk distribution analysis
            quality: Search quality metrics
            comparison: Optional comparison with old approach

        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 60)
        report.append("CHUNK QUALITY ANALYSIS REPORT")
        report.append("=" * 60)
        report.append("")

        # Distribution Analysis
        report.append("CHUNK SIZE DISTRIBUTION:")
        report.append(f"  Total chunks: {analysis.total_chunks}")
        report.append(f"  Average size: {analysis.average_size:.1f} chars")
        report.append(f"  Median size: {analysis.median_size:.1f} chars")
        report.append(f"  Size range: {analysis.min_size} - {analysis.max_size} chars")
        report.append("")
        report.append(
            f"  Chunks under 100 chars: {analysis.under_100_count} ({analysis.under_100_percent:.1f}%)"
        )
        report.append(
            f"  Chunks under 300 chars: {analysis.under_300_count} ({analysis.under_300_percent:.1f}%)"
        )
        report.append(
            f"  Chunks under 1000 chars: {analysis.under_1000_count} ({analysis.under_1000_percent:.1f}%)"
        )
        report.append(
            f"  Chunks exactly 1000 chars: {analysis.exactly_1000_count} ({analysis.exactly_1000_percent:.1f}%)"
        )
        report.append("")

        # Quality Metrics
        report.append("SEARCH QUALITY METRICS:")
        report.append(
            f"  Meaningful chunks: {quality.meaningful_chunks_count} ({quality.meaningful_percentage:.1f}%)"
        )
        report.append(f"  Fragment chunks: {quality.fragment_chunks_count}")
        report.append(
            f"  Average context length: {quality.average_context_length:.1f} chars"
        )
        report.append(f"  Complete methods: {quality.complete_methods_count}")
        report.append(f"  Incomplete methods: {quality.incomplete_methods_count}")
        report.append("")

        # Comparison with old approach
        if comparison:
            report.append("COMPARISON WITH OLD AST APPROACH:")
            old = comparison["old_metrics"]
            current = comparison["current_metrics"]
            improvements = comparison["improvements"]

            report.append(
                f"  Under 300 chars: {old['under_300_percent']:.1f}% → {current['under_300_percent']:.1f}% (improvement: {improvements['under_300_reduction']:.1f}%)"
            )
            report.append(
                f"  Under 100 chars: {old['under_100_percent']:.1f}% → {current['under_100_percent']:.1f}% (improvement: {improvements['under_100_reduction']:.1f}%)"
            )
            report.append(
                f"  Average size: {old['average_size']:.0f} → {current['average_size']:.0f} chars (improvement: +{improvements['average_size_increase']:.0f})"
            )
            report.append("")

            # Story 7 Requirements Check
            report.append("STORY 7 REQUIREMENTS VALIDATION:")
            requirements = comparison["meets_story7_requirements"]
            report.append(
                f"  ✓ Nearly all chunks 1000 chars: {'PASS' if requirements['under_1000_except_final'] else 'FAIL'}"
            )
            report.append(
                f"  ✓ Massive improvement under 300: {'PASS' if requirements['massive_improvement_under_300'] else 'FAIL'}"
            )
            report.append(
                f"  ✓ Massive improvement under 100: {'PASS' if requirements['massive_improvement_under_100'] else 'FAIL'}"
            )
            report.append(
                f"  ✓ Average size near 1000: {'PASS' if requirements['average_size_near_1000'] else 'FAIL'}"
            )

        report.append("=" * 60)
        return "\n".join(report)


def run_story7_validation(file_or_directory: Path) -> str:
    """Run complete Story 7 validation on a file or directory.

    Args:
        file_or_directory: Path to file or directory to analyze

    Returns:
        Comprehensive validation report
    """
    analyzer = ChunkAnalyzer()

    if file_or_directory.is_file():
        distribution, quality = analyzer.analyze_file_chunking(file_or_directory)
    else:
        distribution, quality = analyzer.analyze_directory_chunking(file_or_directory)

    comparison = analyzer.compare_with_old_approach_metrics(distribution)
    report = analyzer.generate_report(distribution, quality, comparison)

    return report
