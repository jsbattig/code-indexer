#!/usr/bin/env python3
"""
Score Threshold Research Script for CIDX Multi-Repository Search.

Executes semantic queries across repositories and analyzes score distributions
to determine optimal min_score threshold recommendations.

This script provides empirical data to validate the min_score=0.7 recommendation
documented in docs/mcpb/query-guide.md for multi-repository AI agent queries.

Usage:
    # Analyze single repository (path to directory with .code-indexer/)
    python3 scripts/analysis/score_threshold_research.py --repo /path/to/my-project

    # Analyze multiple repositories
    python3 scripts/analysis/score_threshold_research.py --repos /path/to/repo1,/path/to/repo2

    # Use custom queries
    python3 scripts/analysis/score_threshold_research.py --repo /path/to/my-project --queries queries.txt

    # Output detailed results to file
    python3 scripts/analysis/score_threshold_research.py --repo /path/to/my-project --output results.json

    # Analyze current directory (if it has .code-indexer/)
    python3 scripts/analysis/score_threshold_research.py --repo .

Research Methodology:
    1. Execute 20+ diverse semantic queries across specified repositories
    2. Collect all relevance scores from results (min_score NOT applied)
    3. Calculate percentiles: P10, P25, P50, P75, P90
    4. Analyze retention rates at thresholds: 0.5, 0.6, 0.7, 0.8, 0.9
    5. Recommend threshold based on precision/recall balance
    6. Document trade-offs at each threshold

Output:
    - Score distribution statistics (mean, median, std dev, percentiles)
    - Retention rates at each threshold (% of results retained)
    - Recommended min_score value with rationale
    - Trade-off analysis for different thresholds
"""

import argparse
import statistics
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional
from collections import Counter


def check_cidx_available() -> bool:
    """Check if cidx CLI is available."""
    try:
        result = subprocess.run(
            ["cidx", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# Verify cidx is available at startup
if not check_cidx_available():
    print("ERROR: cidx CLI not found. Ensure CIDX is installed and in PATH.")
    print("Install: pip install code-indexer")
    print("Or run from project root: python3 -m code_indexer.cli --version")
    sys.exit(1)


# Constants
TARGET_RETENTION_MIN = 50  # Minimum retention percentage for recommended threshold
TARGET_RETENTION_MAX = 70  # Maximum retention percentage for recommended threshold
BAR_SCALE_FACTOR = 2  # Scale factor for progress bars (percentage / 2)
DEFAULT_LIMIT_PER_QUERY = 50  # Default max results per query


# Default semantic queries covering common use cases
DEFAULT_QUERIES = [
    # Authentication and security
    "user authentication",
    "password validation",
    "JWT token handling",
    "authorization logic",
    "session management",
    # Database operations
    "database connection",
    "SQL query execution",
    "data migration",
    "transaction handling",
    # API and networking
    "REST API endpoint",
    "HTTP request handling",
    "error response",
    "rate limiting",
    # Business logic
    "payment processing",
    "user registration",
    "order fulfillment",
    "notification system",
    # Infrastructure
    "logging configuration",
    "caching strategy",
    "background job",
    "configuration management",
]


def execute_single_query(
    query: str,
    repo_path: str,
    limit: int = DEFAULT_LIMIT_PER_QUERY
) -> List[float]:
    """
    Execute a single semantic query using cidx CLI and extract scores.

    Args:
        query: Semantic query string
        repo_path: Path to repository with .code-indexer directory
        limit: Maximum results to return

    Returns:
        List of relevance scores from this query
    """
    try:
        # Build cidx query command
        # Use --quiet for machine-parseable output
        cmd = [
            "cidx", "query", query,
            "--limit", str(limit),
            "--accuracy", "high",
            "--quiet"
        ]

        # Execute from repository directory
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout per query
        )

        if result.returncode != 0:
            print(f"  [WARN] Query returned non-zero exit code: {result.returncode}")
            return []

        # Parse output - cidx --quiet outputs: "N. path:line score"
        # Example: "1. src/auth.py:42 0.8523"
        scores = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                # Split on last space to get score
                parts = line.rsplit(" ", 1)
                if len(parts) == 2:
                    score = float(parts[1])
                    scores.append(score)
            except (ValueError, IndexError):
                continue

        return scores

    except subprocess.TimeoutExpired:
        print(f"  [WARN] Query timed out after 60s: '{query[:30]}...'")
        return []
    except Exception as e:
        print(f"  [WARN] Query failed: '{query[:30]}...' - {e}")
        return []


def execute_queries(
    repo_path: str,
    queries: List[str],
    limit: int = DEFAULT_LIMIT_PER_QUERY
) -> List[float]:
    """
    Execute semantic queries against a repository and collect all relevance scores.

    Args:
        repo_path: Path to repository with .code-indexer directory
        queries: List of semantic query strings
        limit: Maximum results per query

    Returns:
        List of all relevance scores from all queries
    """
    all_scores = []

    print(f"\nExecuting {len(queries)} queries against {repo_path}...")
    print(f"Collecting up to {limit} results per query (min_score NOT applied)")
    print("-" * 70)

    for i, query in enumerate(queries, 1):
        query_scores = execute_single_query(query, repo_path, limit)
        all_scores.extend(query_scores)

        truncated_query = query[:40] + "..." if len(query) > 40 else query
        print(f"  [{i:2d}/{len(queries)}] '{truncated_query}' -> {len(query_scores)} results")

    print("-" * 70)
    print(f"Total scores collected: {len(all_scores)}\n")

    return all_scores


def analyze_scores(scores: List[float]) -> Dict:
    """
    Analyze score distribution and generate threshold recommendations.

    Args:
        scores: List of relevance scores

    Returns:
        Dictionary containing:
        - Statistics: mean, median, std_dev, percentiles
        - Retention rates at different thresholds
        - Recommended threshold with rationale
    """
    if not scores:
        return {"error": "No scores to analyze"}

    sorted_scores = sorted(scores)
    n = len(sorted_scores)

    # Calculate percentiles
    percentiles = {
        "p10": sorted_scores[int(n * 0.1)],
        "p25": sorted_scores[int(n * 0.25)],
        "p50": sorted_scores[int(n * 0.5)],
        "p75": sorted_scores[int(n * 0.75)],
        "p90": sorted_scores[int(n * 0.9)],
    }

    # Calculate retention at different thresholds
    thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]
    retention = {}
    for t in thresholds:
        retained = sum(1 for s in scores if s >= t)
        retention[t] = {
            "count": retained,
            "percentage": retained / n * 100
        }

    # Determine recommendation based on retention analysis
    recommended_threshold = _determine_recommended_threshold(retention)

    return {
        "total_scores": n,
        "statistics": {
            "mean": statistics.mean(scores),
            "median": statistics.median(scores),
            "std_dev": statistics.stdev(scores) if n > 1 else 0,
            "min": min(scores),
            "max": max(scores),
        },
        "percentiles": percentiles,
        "retention_by_threshold": retention,
        "recommendation": {
            "min_score": recommended_threshold,
            "rationale": f"Retains {retention[recommended_threshold]['percentage']:.1f}% of results, balancing precision and recall",
            "retained_count": retention[recommended_threshold]["count"]
        }
    }


def _determine_recommended_threshold(retention: Dict) -> float:
    """
    Determine recommended threshold based on retention rates.

    Target: 50-70% retention for good precision/recall balance.

    Args:
        retention: Dictionary mapping threshold to retention stats

    Returns:
        Recommended min_score threshold
    """
    # Priority order: 0.7 (documented default), then 0.6, 0.8, 0.5
    for t in [0.7, 0.6, 0.8, 0.5]:
        if TARGET_RETENTION_MIN <= retention[t]["percentage"] <= TARGET_RETENTION_MAX:
            return t

    # Fallback to documented default if no threshold in target range
    return 0.7


def print_report_header(repository: str):
    """Print report header with repository information."""
    print("\n" + "=" * 70)
    print("SCORE THRESHOLD ANALYSIS REPORT")
    print(f"Repository: {repository}")
    print("=" * 70)


def print_statistics(analysis: Dict):
    """Print score distribution statistics section."""
    print("\nSCORE DISTRIBUTION STATISTICS")
    print("-" * 70)
    stats = analysis["statistics"]
    print(f"  Total Results Analyzed:  {analysis['total_scores']}")
    print(f"  Mean Score:              {stats['mean']:.3f}")
    print(f"  Median Score:            {stats['median']:.3f}")
    print(f"  Std Deviation:           {stats['std_dev']:.3f}")
    print(f"  Min Score:               {stats['min']:.3f}")
    print(f"  Max Score:               {stats['max']:.3f}")


def print_percentiles(analysis: Dict):
    """Print score percentiles section."""
    print("\nSCORE PERCENTILES")
    print("-" * 70)
    percs = analysis["percentiles"]
    print(f"  P10 (90th percentile):   {percs['p10']:.3f}  (10% of results above this)")
    print(f"  P25 (75th percentile):   {percs['p25']:.3f}  (25% of results above this)")
    print(f"  P50 (median):            {percs['p50']:.3f}  (50% of results above this)")
    print(f"  P75 (25th percentile):   {percs['p75']:.3f}  (75% of results above this)")
    print(f"  P90 (10th percentile):   {percs['p90']:.3f}  (90% of results above this)")


def print_retention(analysis: Dict):
    """Print retention rates at different thresholds."""
    print("\nRETENTION RATES AT DIFFERENT THRESHOLDS")
    print("-" * 70)
    retention = analysis["retention_by_threshold"]
    for threshold in [0.5, 0.6, 0.7, 0.8, 0.9]:
        r = retention[threshold]
        bar_length = int(r["percentage"] / BAR_SCALE_FACTOR)
        bar = "█" * bar_length
        print(f"  min_score={threshold}:  {r['percentage']:5.1f}%  ({r['count']:5d} results)  {bar}")


def print_recommendation(analysis: Dict):
    """Print recommendation and trade-off guidance."""
    print("\nRECOMMENDATION")
    print("-" * 70)
    rec = analysis["recommendation"]
    print(f"  Recommended min_score:   {rec['min_score']}")
    print(f"  Rationale:               {rec['rationale']}")
    print(f"  Results retained:        {rec['retained_count']} of {analysis['total_scores']}")

    print("\nTRADE-OFF GUIDANCE")
    print("-" * 70)
    print("  0.5:  Broad search, high recall, may include noise")
    print("  0.6:  Moderate filtering, good for exploratory queries")
    print("  0.7:  Balanced precision/recall (RECOMMENDED for AI agents)")
    print("  0.8:  Focused results, high precision, may miss relevant code")
    print("  0.9:  Very strict, only near-exact semantic matches")
    print("\n" + "=" * 70 + "\n")


def print_report(analysis: Dict, repository: str):
    """Print complete human-readable analysis report."""
    if "error" in analysis:
        print(f"\nERROR: {analysis['error']}")
        return

    print_report_header(repository)
    print_statistics(analysis)
    print_percentiles(analysis)
    print_retention(analysis)
    print_recommendation(analysis)


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze semantic search score distributions to determine optimal min_score thresholds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze single repository (must have .code-indexer/ directory)
  python3 scripts/analysis/score_threshold_research.py --repo /path/to/my-project

  # Analyze current directory
  python3 scripts/analysis/score_threshold_research.py --repo .

  # Analyze multiple repositories
  python3 scripts/analysis/score_threshold_research.py --repos /path/to/repo1,/path/to/repo2

  # Use custom queries from file
  python3 scripts/analysis/score_threshold_research.py --repo /path/to/repo --queries my-queries.txt

  # Save results to JSON
  python3 scripts/analysis/score_threshold_research.py --repo /path/to/repo --output results.json
        """
    )

    parser.add_argument("--repo", help="Path to repository directory (must contain .code-indexer/)")
    parser.add_argument("--repos", help="Comma-separated paths to repository directories")
    parser.add_argument("--queries", type=Path, help="Path to file containing queries (one per line)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT_PER_QUERY, help="Maximum results per query")
    parser.add_argument("--output", type=Path, help="Output file for JSON results (optional)")

    return parser.parse_args()


def load_queries(queries_path: Path) -> List[str]:
    """Load queries from file, one per line."""
    if not queries_path.exists():
        print(f"ERROR: Query file not found: {queries_path}")
        sys.exit(1)
    with open(queries_path) as f:
        return [line.strip() for line in f if line.strip()]


def print_multi_repo_summary(all_results: Dict):
    """Print aggregate recommendation for multiple repositories."""
    print("\n" + "=" * 70)
    print("MULTI-REPOSITORY RECOMMENDATION")
    print("=" * 70)

    recommended_thresholds = [
        r["recommendation"]["min_score"]
        for r in all_results.values()
        if "recommendation" in r
    ]

    if recommended_thresholds:
        most_common = Counter(recommended_thresholds).most_common(1)[0][0]
        print(f"  Most common recommendation: min_score={most_common}")
        print(f"  Basis: {len(recommended_thresholds)} repositories analyzed")

    print("=" * 70 + "\n")


def main():
    """Main entry point for score threshold research."""
    args = parse_arguments()

    # Determine repository list
    if args.repo:
        repositories = [args.repo]
    elif args.repos:
        repositories = [r.strip() for r in args.repos.split(",")]
    else:
        print("ERROR: Must specify --repo or --repos")
        sys.exit(1)

    # Load queries
    queries = load_queries(args.queries) if args.queries else DEFAULT_QUERIES

    # Print research header
    print("\n" + "=" * 70)
    print("CIDX SCORE THRESHOLD RESEARCH")
    print("=" * 70)
    print(f"Repositories:  {', '.join(repositories)}")
    print(f"Queries:       {len(queries)}")
    print(f"Limit/query:   {args.limit}")
    print("=" * 70)

    # Execute research for each repository
    all_results = {}
    for repo in repositories:
        scores = execute_queries(repo, queries, args.limit)
        analysis = analyze_scores(scores)
        all_results[repo] = analysis
        print_report(analysis, repo)

    # Multi-repository summary
    if len(repositories) > 1:
        print_multi_repo_summary(all_results)

    # Save to JSON if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"Results saved to: {args.output}")


if __name__ == "__main__":
    main()

