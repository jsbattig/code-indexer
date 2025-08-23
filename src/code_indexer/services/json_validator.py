"""
JSON Syntax Validator and Repairer

Provides comprehensive JSON syntax validation and automatic repair capabilities
for common manual editing errors in configuration files.
"""

import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class JSONFix:
    """Represents a single JSON syntax fix."""

    fix_type: str
    line: int
    description: str
    original: str
    fixed: str


@dataclass
class JSONValidationResult:
    """Result of JSON validation and repair analysis."""

    valid: bool
    errors: List[str]
    fixes: List[JSONFix]
    content: Optional[str] = None


class JSONSyntaxValidator:
    """Validates JSON syntax and detects common manual editing errors."""

    def __init__(self):
        self.common_patterns = [
            self._detect_trailing_commas,
            self._detect_missing_commas,
            self._detect_unquoted_keys,
            self._detect_single_quotes,
            self._detect_comments,
            self._detect_unescaped_strings,
            self._detect_missing_brackets,
        ]

    def validate_json_file(self, file_path: Path) -> JSONValidationResult:
        """Validate JSON syntax and detect common errors."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Try to parse JSON first
            try:
                json.loads(content)
                return JSONValidationResult(
                    valid=True, errors=[], fixes=[], content=content
                )
            except json.JSONDecodeError as e:
                return self._analyze_json_error(content, e)

        except Exception as e:
            return JSONValidationResult(
                valid=False, errors=[f"Cannot read file: {e}"], fixes=[]
            )

    def _analyze_json_error(
        self, content: str, json_error: json.JSONDecodeError
    ) -> JSONValidationResult:
        """Analyze JSON error and suggest fixes."""
        errors = [f"JSON Parse Error at line {json_error.lineno}: {json_error.msg}"]
        fixes = []

        lines = content.split("\n")

        # Apply all detection patterns
        for pattern_detector in self.common_patterns:
            pattern_fixes = pattern_detector(lines, json_error)
            fixes.extend(pattern_fixes)

        return JSONValidationResult(
            valid=False, errors=errors, fixes=fixes, content=content
        )

    def _detect_trailing_commas(
        self, lines: List[str], error: json.JSONDecodeError
    ) -> List[JSONFix]:
        """Detect trailing commas before } or ]."""
        fixes = []
        for i, line in enumerate(lines):
            # Look for patterns like: "value", } or "value", ]
            # Also check for trailing comma followed by newline and then closing bracket
            if re.search(r",\s*[}\]]", line):
                fixed_line = re.sub(r",(\s*[}\]])", r"\1", line)
                fixes.append(
                    JSONFix(
                        fix_type="trailing_comma",
                        line=i + 1,
                        description="Remove trailing comma before closing bracket",
                        original=line,
                        fixed=fixed_line,
                    )
                )
            # Check for trailing comma at end of line followed by closing bracket on next line
            elif line.strip().endswith(",") and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith("}") or next_line.startswith("]"):
                    fixed_line = (
                        line.rstrip().rstrip(",") + "\n"
                        if line.endswith("\n")
                        else line.rstrip().rstrip(",")
                    )
                    fixes.append(
                        JSONFix(
                            fix_type="trailing_comma",
                            line=i + 1,
                            description="Remove trailing comma before closing bracket",
                            original=line,
                            fixed=fixed_line,
                        )
                    )
        return fixes

    def _detect_missing_commas(
        self, lines: List[str], error: json.JSONDecodeError
    ) -> List[JSONFix]:
        """Detect missing commas between JSON elements."""
        fixes = []
        for i in range(len(lines) - 1):
            current_line = lines[i].strip()
            next_line = lines[i + 1].strip()

            # Check if current line ends with value and next starts with key
            if (
                self._ends_with_value(current_line)
                and self._starts_with_key(next_line)
                and not current_line.endswith(",")
            ):
                fixes.append(
                    JSONFix(
                        fix_type="missing_comma",
                        line=i + 1,
                        description="Add missing comma between elements",
                        original=lines[i],
                        fixed=lines[i].rstrip() + ",",
                    )
                )
        return fixes

    def _detect_unquoted_keys(
        self, lines: List[str], error: json.JSONDecodeError
    ) -> List[JSONFix]:
        """Detect unquoted object keys."""
        fixes = []
        for i, line in enumerate(lines):
            # Look for patterns like: key: "value" (unquoted key)
            match = re.search(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", line)
            if match and not re.search(r'^\s*"[^"]*"\s*:', line):
                key = match.group(1)
                fixed_line = re.sub(rf"(\s*)({key})(\s*:)", rf'\1"{key}"\3', line)
                fixes.append(
                    JSONFix(
                        fix_type="unquoted_key",
                        line=i + 1,
                        description=f"Quote the key '{key}'",
                        original=line,
                        fixed=fixed_line,
                    )
                )
        return fixes

    def _detect_single_quotes(
        self, lines: List[str], error: json.JSONDecodeError
    ) -> List[JSONFix]:
        """Detect single quotes instead of double quotes."""
        fixes = []
        for i, line in enumerate(lines):
            if "'" in line:
                # Convert single quotes to double quotes, handling escaping
                fixed_line = self._convert_single_to_double_quotes(line)
                if fixed_line != line:
                    fixes.append(
                        JSONFix(
                            fix_type="single_quotes",
                            line=i + 1,
                            description="Convert single quotes to double quotes",
                            original=line,
                            fixed=fixed_line,
                        )
                    )
        return fixes

    def _detect_comments(
        self, lines: List[str], error: json.JSONDecodeError
    ) -> List[JSONFix]:
        """Detect JavaScript-style comments in JSON."""
        fixes = []
        for i, line in enumerate(lines):
            original_line = line

            # Detect // comments
            if "//" in line:
                comment_pos = line.find("//")
                fixed_line = line[:comment_pos].rstrip()
                fixes.append(
                    JSONFix(
                        fix_type="line_comment",
                        line=i + 1,
                        description="Remove JavaScript-style comment",
                        original=original_line,
                        fixed=fixed_line,
                    )
                )
                line = fixed_line

            # Detect /* */ comments
            if "/*" in line and "*/" in line:
                fixed_line = re.sub(r"/\*.*?\*/", "", line).strip()
                fixes.append(
                    JSONFix(
                        fix_type="block_comment",
                        line=i + 1,
                        description="Remove block comment",
                        original=original_line,
                        fixed=fixed_line,
                    )
                )
        return fixes

    def _detect_unescaped_strings(
        self, lines: List[str], error: json.JSONDecodeError
    ) -> List[JSONFix]:
        """Detect unescaped backslashes and quotes in strings."""
        fixes = []
        for i, line in enumerate(lines):
            original_line = line
            fixed_line = line

            # Check for unescaped backslashes (Windows paths)
            if "\\" in line and not re.search(r"\\\\", line):
                # Only escape backslashes within quoted strings
                fixed_line = re.sub(r'("[^"]*?)\\([^"]*?")', r"\1\\\\\2", fixed_line)

            # Check for unescaped quotes within strings
            if re.search(r'"[^"]*"[^"]*"[^"]*"', line):
                # Complex case - may need manual intervention
                pass

            if fixed_line != original_line:
                fixes.append(
                    JSONFix(
                        fix_type="unescaped_characters",
                        line=i + 1,
                        description="Escape special characters in strings",
                        original=original_line,
                        fixed=fixed_line,
                    )
                )
        return fixes

    def _detect_missing_brackets(
        self, lines: List[str], error: json.JSONDecodeError
    ) -> List[JSONFix]:
        """Detect missing brackets or braces."""
        fixes = []

        # Count brackets and braces
        open_braces = 0
        open_brackets = 0

        for i, line in enumerate(lines):
            open_braces += line.count("{") - line.count("}")
            open_brackets += line.count("[") - line.count("]")

        # Suggest fixes for unmatched brackets
        if open_braces > 0:
            fixes.append(
                JSONFix(
                    fix_type="missing_closing_brace",
                    line=len(lines),
                    description=f"Add {open_braces} missing closing brace(s) '}}' at end",
                    original="",
                    fixed="}" * open_braces,
                )
            )
        elif open_braces < 0:
            fixes.append(
                JSONFix(
                    fix_type="extra_closing_brace",
                    line=len(lines),
                    description=f"Remove {abs(open_braces)} extra closing brace(s)",
                    original="",
                    fixed="",
                )
            )

        if open_brackets > 0:
            fixes.append(
                JSONFix(
                    fix_type="missing_closing_bracket",
                    line=len(lines),
                    description=f"Add {open_brackets} missing closing bracket(s) ']' at end",
                    original="",
                    fixed="]" * open_brackets,
                )
            )
        elif open_brackets < 0:
            fixes.append(
                JSONFix(
                    fix_type="extra_closing_bracket",
                    line=len(lines),
                    description=f"Remove {abs(open_brackets)} extra closing bracket(s)",
                    original="",
                    fixed="",
                )
            )

        return fixes

    def _ends_with_value(self, line: str) -> bool:
        """Check if line ends with a JSON value."""
        line = line.strip()
        return (
            line.endswith('"')
            or line.endswith("}")
            or line.endswith("]")
            or line.endswith("true")
            or line.endswith("false")
            or line.endswith("null")
            or bool(re.search(r"\d$", line))
        )

    def _starts_with_key(self, line: str) -> bool:
        """Check if line starts with a JSON key."""
        line = line.strip()
        return bool(line.startswith('"') and ":" in line)

    def _convert_single_to_double_quotes(self, line: str) -> str:
        """Convert single quotes to double quotes, handling escaping."""
        # Simple conversion - more complex cases may need manual intervention
        if line.count("'") % 2 == 0:  # Even number of single quotes
            # Replace single quotes with double quotes
            result = line.replace("'", '"')
            # If we now have escaped double quotes, we may need to fix that
            return result
        return line


class JSONSyntaxRepairer:
    """Automatically repairs JSON syntax errors."""

    def __init__(self):
        self.validator = JSONSyntaxValidator()

    def repair_json_file(
        self, file_path: Path, dry_run: bool = False, create_backup: bool = True
    ) -> Dict[str, Any]:
        """Attempt to automatically repair JSON syntax errors."""

        # First validate and get error analysis
        analysis = self.validator.validate_json_file(file_path)

        if analysis.valid:
            return {
                "success": True,
                "message": "JSON is already valid",
                "fixes_applied": [],
            }

        if not analysis.fixes:
            return {
                "success": False,
                "message": "No automatic fixes available",
                "manual_intervention_needed": True,
                "errors": analysis.errors,
            }

        # Apply fixes to content
        try:
            if analysis.content is None:
                return {
                    "success": False,
                    "message": "No content available for repair",
                    "manual_intervention_needed": True,
                }

            repaired_content = self._apply_fixes(analysis.content, analysis.fixes)

            # Validate the repaired JSON
            json.loads(repaired_content)

            if not dry_run:
                # Create backup first
                backup_path = None
                if create_backup:
                    backup_path = file_path.with_suffix(f"{file_path.suffix}.backup")
                    shutil.copy2(file_path, backup_path)

                # Write repaired content
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(repaired_content)

            return {
                "success": True,
                "fixes_applied": [fix.__dict__ for fix in analysis.fixes],
                "backup_created": (
                    backup_path if not dry_run and create_backup else None
                ),
                "message": f"Applied {len(analysis.fixes)} fixes successfully",
            }

        except json.JSONDecodeError as e:
            return {
                "success": False,
                "message": f"Automatic repair failed - JSON still invalid after fixes: {e}",
                "manual_intervention_needed": True,
                "attempted_fixes": [fix.__dict__ for fix in analysis.fixes],
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error during repair process: {e}",
                "manual_intervention_needed": True,
            }

    def _apply_fixes(self, content: str, fixes: List[JSONFix]) -> str:
        """Apply a list of fixes to content."""
        lines = content.split("\n")

        # Sort fixes by line number in reverse order to avoid line number shifts
        sorted_fixes = sorted(fixes, key=lambda x: x.line, reverse=True)

        for fix in sorted_fixes:
            line_idx = fix.line - 1

            if fix.fix_type in ["missing_closing_brace", "missing_closing_bracket"]:
                # Append to end
                lines.append(fix.fixed)
            elif 0 <= line_idx < len(lines):
                # Replace line
                lines[line_idx] = fix.fixed

        return "\n".join(lines)

    def generate_error_report(
        self, validation_results: Dict[str, Dict[str, Any]]
    ) -> str:
        """Generate user-friendly report of JSON syntax issues."""

        report = []

        for filename, result in validation_results.items():
            if not result.get("success", False):
                report.append(f"\n📄 {filename}:")

                if result.get("fixes_applied"):
                    report.append("  ✅ Automatically fixed:")
                    for fix in result["fixes_applied"]:
                        report.append(f"    • Line {fix['line']}: {fix['description']}")

                if result.get("manual_intervention_needed"):
                    report.append("  ❌ Manual fixes needed:")
                    report.append(f"    • {result['message']}")
                    if result.get("errors"):
                        for error in result["errors"]:
                            report.append(f"    • {error}")

        if not report:
            return "✅ All JSON files have valid syntax"

        return "\n".join(report)
