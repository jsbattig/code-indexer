"""
LogExportFormatter - Format logs for export in JSON and CSV formats.

Implements:
- JSON export with metadata header (export timestamp, filters, count)
- CSV export with UTF-8 BOM for Excel compatibility
- Proper escaping of special characters in CSV
- Human-readable formatting
"""

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List


class LogExportFormatter:
    """
    Format log entries for export to JSON or CSV formats.

    Provides standardized export formatting for logs with proper encoding,
    escaping, and metadata inclusion.
    """

    @staticmethod
    def to_json(logs: List[Dict[str, Any]], filters: Dict[str, Any]) -> str:
        """
        Export logs as formatted JSON with metadata header.

        Args:
            logs: List of log entry dicts from LogAggregatorService
            filters: Dict of applied filters (search, level, etc.)

        Returns:
            JSON string with metadata and logs array, formatted with 2-space indentation

        Format:
            {
              "metadata": {
                "exported_at": "2025-01-02T15:30:00Z",
                "filters": {...},
                "count": 47
              },
              "logs": [...]
            }
        """
        export_data = {
            "metadata": {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "filters": filters,
                "count": len(logs),
            },
            "logs": logs,
        }

        # Format with 2-space indentation for readability
        return json.dumps(export_data, indent=2, default=str, ensure_ascii=False)

    @staticmethod
    def to_csv(logs: List[Dict[str, Any]]) -> str:
        """
        Export logs as CSV with UTF-8 BOM for Excel compatibility.

        Args:
            logs: List of log entry dicts from LogAggregatorService

        Returns:
            CSV string with UTF-8 BOM, header row, and data rows

        Features:
            - UTF-8 BOM for Excel compatibility
            - Proper escaping of commas, quotes, newlines
            - All log fields as columns
            - None values handled gracefully
        """
        output = io.StringIO()

        # Define CSV columns matching log entry structure
        fieldnames = [
            "timestamp",
            "level",
            "source",
            "message",
            "correlation_id",
            "user_id",
            "request_path",
        ]

        writer = csv.DictWriter(
            output,
            fieldnames=fieldnames,
            extrasaction="ignore",  # Ignore extra fields like 'id'
            quoting=csv.QUOTE_MINIMAL,  # Quote only when necessary
        )

        # Write header row
        writer.writeheader()

        # Write data rows
        writer.writerows(logs)

        # Get CSV content
        csv_content = output.getvalue()

        # Add UTF-8 BOM for Excel compatibility
        return "\ufeff" + csv_content
