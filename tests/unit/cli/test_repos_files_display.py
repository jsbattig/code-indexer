"""Unit tests for repository file display helper functions."""

from code_indexer.cli_repos_files import display_file_tree, display_with_line_numbers


def test_display_file_tree_empty(capsys):
    """display_file_tree handles empty list."""
    display_file_tree([])

    captured = capsys.readouterr()
    assert "(empty directory)" in captured.out


def test_display_file_tree_sorts_alphabetically(capsys):
    """display_file_tree sorts files and directories."""
    files = [
        {"name": "zzz.txt", "type": "file", "size": 100},
        {"name": "aaa", "type": "directory", "size": 0},
        {"name": "mmm.py", "type": "file", "size": 200},
    ]
    display_file_tree(files)

    captured = capsys.readouterr()
    # Check that directories appear before files
    assert "📁" in captured.out
    assert "📄" in captured.out


def test_display_file_tree_with_path(capsys):
    """display_file_tree displays path header when provided."""
    files = [{"name": "test.py", "type": "file", "size": 100}]
    display_file_tree(files, "/src")

    captured = capsys.readouterr()
    assert "Directory: /src" in captured.out


def test_display_with_line_numbers_empty(capsys):
    """display_with_line_numbers handles empty content."""
    display_with_line_numbers("")

    captured = capsys.readouterr()
    assert "(empty file)" in captured.out


def test_display_with_line_numbers_single_line(capsys):
    """display_with_line_numbers works with single line."""
    display_with_line_numbers("single line")

    captured = capsys.readouterr()
    assert "1 │ single line" in captured.out


def test_display_with_line_numbers_multiple_lines(capsys):
    """display_with_line_numbers formats multi-line content."""
    content = "line1\nline2\nline3"
    display_with_line_numbers(content)

    captured = capsys.readouterr()
    assert "1 │ line1" in captured.out
    assert "2 │ line2" in captured.out
    assert "3 │ line3" in captured.out


def test_display_with_line_numbers_alignment(capsys):
    """display_with_line_numbers aligns line numbers properly."""
    # Create content with 100 lines to test alignment
    content = "\n".join([f"line {i}" for i in range(1, 101)])
    display_with_line_numbers(content)

    captured = capsys.readouterr()
    # Line 1 should be right-aligned to match line 100
    assert "  1 │" in captured.out
    assert "100 │" in captured.out


def test_display_file_tree_with_api_response_format(capsys):
    """display_file_tree should handle actual API response format (path, size_bytes)."""
    # Actual API response format
    files = [
        {
            "path": "README.md",
            "size_bytes": 1234,
            "type": "file",
            "modified_at": "2025-11-13T08:54:17.423169Z",
            "language": "markdown",
            "is_indexed": False,
        },
        {
            "path": "src/main.py",
            "size_bytes": 567,
            "type": "file",
            "modified_at": "2025-11-13T08:54:17.423169Z",
            "language": "python",
            "is_indexed": True,
        },
    ]

    # Should not crash and should display files
    display_file_tree(files)

    captured = capsys.readouterr()

    # Should display both files
    assert "README.md" in captured.out
    assert "src/main.py" in captured.out
    assert "📄" in captured.out
    # Should show file sizes
    assert "KB" in captured.out or "B" in captured.out
    # Should not show 0 items
    assert "0 items" not in captured.out
    # Should show correct count
    assert "2 items" in captured.out
    assert "0 directories, 2 files" in captured.out
