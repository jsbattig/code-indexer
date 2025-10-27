# Story: Repository Identification in Output

## Story ID: STORY-5.4
## Feature: FEAT-005 (Watch Command Multiplexing)
## Priority: P2 - Enhancement
## Size: Small

## User Story
**As a** developer viewing multiplexed output
**I want to** clearly see which repository generated each message
**So that** I can understand where changes are occurring

## Conversation Context
**Citation**: "multiple into single stdout."

**Context**: When multiplexing output from multiple repositories into a single stdout stream, the conversation implied that each output line must be clearly attributed to its source repository. This enables developers to quickly identify which repository is reporting changes or errors.

## Acceptance Criteria
- [ ] Each output line prefixed with repository identifier
- [ ] Prefixes are consistent and easily recognizable
- [ ] Color coding for different repositories (if terminal supports)
- [ ] Clear visual separation between repositories
- [ ] Repository names are readable and not truncated
- [ ] Prefix format is standardized across all output
- [ ] Optional relative path display for nested repositories

## Technical Implementation

### 1. Repository Prefix Formatter
```python
# proxy/repository_formatter.py
from pathlib import Path
from typing import Optional

class RepositoryPrefixFormatter:
    """Format repository identifiers for output prefixing"""

    def __init__(self, proxy_root: Path):
        self.proxy_root = proxy_root

    def format_prefix(
        self,
        repo_path: str,
        use_relative: bool = True
    ) -> str:
        """
        Format repository path as prefix.

        Args:
            repo_path: Full or relative repository path
            use_relative: Use relative path from proxy root

        Returns:
            Formatted prefix like "[backend/auth-service]"
        """
        if use_relative:
            display_path = self._get_relative_path(repo_path)
        else:
            display_path = repo_path

        return f"[{display_path}]"

    def _get_relative_path(self, repo_path: str) -> str:
        """Get path relative to proxy root"""
        try:
            repo = Path(repo_path).resolve()
            relative = repo.relative_to(self.proxy_root)
            return str(relative)
        except ValueError:
            # Path not relative to proxy root, use as-is
            return repo_path

    def format_output_line(
        self,
        repo_path: str,
        content: str
    ) -> str:
        """
        Format complete output line with prefix.

        Returns: "[repo-name] content"
        """
        prefix = self.format_prefix(repo_path)
        return f"{prefix} {content}"
```

### 2. Color-Coded Repository Identification
```python
class ColorCodedFormatter:
    """Add color coding to repository prefixes"""

    # ANSI color codes
    COLORS = [
        '\033[91m',  # Red
        '\033[92m',  # Green
        '\033[93m',  # Yellow
        '\033[94m',  # Blue
        '\033[95m',  # Magenta
        '\033[96m',  # Cyan
    ]
    RESET = '\033[0m'

    def __init__(self, use_color: bool = None):
        if use_color is None:
            # Auto-detect terminal color support
            self.use_color = self._supports_color()
        else:
            self.use_color = use_color

        self.repo_colors: Dict[str, str] = {}

    def _supports_color(self) -> bool:
        """Detect if terminal supports color"""
        import sys
        return (
            hasattr(sys.stdout, 'isatty') and
            sys.stdout.isatty()
        )

    def get_color_for_repo(self, repo_path: str) -> str:
        """
        Get consistent color for repository.

        Same repository always gets same color.
        """
        if not self.use_color:
            return ''

        if repo_path not in self.repo_colors:
            # Assign new color
            color_index = len(self.repo_colors) % len(self.COLORS)
            self.repo_colors[repo_path] = self.COLORS[color_index]

        return self.repo_colors[repo_path]

    def format_colored_prefix(self, repo_path: str) -> str:
        """Format prefix with color"""
        if not self.use_color:
            return f"[{repo_path}]"

        color = self.get_color_for_repo(repo_path)
        return f"{color}[{repo_path}]{self.RESET}"

    def format_colored_line(
        self,
        repo_path: str,
        content: str
    ) -> str:
        """Format complete line with colored prefix"""
        prefix = self.format_colored_prefix(repo_path)
        return f"{prefix} {content}"
```

### 3. Consistent Prefix Width
```python
class AlignedPrefixFormatter:
    """Format prefixes with consistent width for alignment"""

    def __init__(self, repositories: List[str]):
        # Calculate maximum prefix width
        self.max_width = max(len(repo) for repo in repositories)

    def format_aligned_prefix(self, repo_path: str) -> str:
        """
        Format prefix with consistent width.

        Example:
          [backend/auth-service    ]
          [frontend/web-app        ]
          [backend/user-service    ]
        """
        padded = repo_path.ljust(self.max_width)
        return f"[{padded}]"

    def format_aligned_line(
        self,
        repo_path: str,
        content: str
    ) -> str:
        """Format line with aligned prefix"""
        prefix = self.format_aligned_prefix(repo_path)
        return f"{prefix} {content}"
```

### 4. Repository Name Abbreviation
```python
class AbbreviatedFormatter:
    """Abbreviate long repository names"""

    def __init__(self, max_length: int = 30):
        self.max_length = max_length

    def abbreviate_repo_name(self, repo_path: str) -> str:
        """
        Abbreviate long repository paths.

        Examples:
          backend/authentication-service -> backend/auth-serv...
          very/long/path/to/repository -> .../to/repository
        """
        if len(repo_path) <= self.max_length:
            return repo_path

        # Try to keep last component
        parts = Path(repo_path).parts
        if len(parts) == 1:
            # Single component, truncate with ellipsis
            return repo_path[:self.max_length-3] + '...'

        # Build path from end until we exceed max_length
        result_parts = []
        current_length = 3  # Account for "..."

        for part in reversed(parts):
            if current_length + len(part) + 1 > self.max_length:
                break
            result_parts.insert(0, part)
            current_length += len(part) + 1

        return '.../' + '/'.join(result_parts)
```

### 5. Visual Separation Enhancement
```python
class VisualSeparator:
    """Enhance visual separation between repositories"""

    def __init__(self):
        self.last_repo: Optional[str] = None

    def format_with_separation(
        self,
        repo_path: str,
        content: str
    ) -> str:
        """
        Add visual separation when repository changes.

        Inserts blank line when different repository outputs.
        """
        output_lines = []

        # Add separator if repository changed
        if self.last_repo is not None and self.last_repo != repo_path:
            output_lines.append('')  # Blank line

        # Add the actual output
        output_lines.append(f"[{repo_path}] {content}")

        self.last_repo = repo_path

        return '\n'.join(output_lines)

    def reset_separation(self):
        """Reset separation tracking"""
        self.last_repo = None
```

## Testing Scenarios

### Unit Tests
1. **Test prefix formatting**
   ```python
   formatter = RepositoryPrefixFormatter(Path('/proxy'))
   prefix = formatter.format_prefix('/proxy/backend/auth')
   assert prefix == '[backend/auth]'
   ```

2. **Test color assignment**
   ```python
   formatter = ColorCodedFormatter(use_color=True)
   color1 = formatter.get_color_for_repo('repo1')
   color2 = formatter.get_color_for_repo('repo1')
   assert color1 == color2  # Same repo, same color
   ```

3. **Test abbreviation**
   ```python
   formatter = AbbreviatedFormatter(max_length=20)
   short = formatter.abbreviate_repo_name('backend/auth')
   assert short == 'backend/auth'
   long = formatter.abbreviate_repo_name('very/long/path/to/repository')
   assert len(long) <= 20
   ```

### Integration Tests
1. **Test visual identification**
   ```bash
   # Start watch
   cidx watch

   # Trigger output from multiple repos
   echo "test" >> repo1/file.txt
   echo "test" >> repo2/file.txt

   # Verify output shows clear prefixes
   # [repo1] File changed: file.txt
   # [repo2] File changed: file.txt
   ```

2. **Test color display**
   - Run watch in color-supporting terminal
   - Verify different repos have different colors
   - Check colors are consistent for same repo

## Error Handling

### Long Repository Names
- Abbreviate intelligently
- Preserve important path components
- Keep output readable
- Provide full path in debug mode

### Color Support Detection
- Auto-detect terminal capabilities
- Gracefully fallback to no color
- Allow user override
- Handle color disable environment variables

## Performance Considerations

### Prefix Formatting Speed
- Cache formatted prefixes
- Avoid repeated string operations
- Pre-calculate alignment widths
- Minimal overhead per line

### Color Code Overhead
- Color codes add ~10 bytes per line
- Negligible for typical output volumes
- Pre-compute color assignments
- Reuse color code strings

## Dependencies
- `pathlib` for path operations
- Standard ANSI color codes
- `sys` for terminal detection
- No external dependencies

## Documentation Updates
- Document prefix format options
- Explain color coding system
- Provide customization examples
- Include terminal compatibility notes

## Example Output

### Basic Prefix Format
```bash
[backend/auth-service] Change detected: src/auth/login.py
[backend/auth-service] Re-indexing 1 file...
[frontend/web-app] Change detected: src/components/Login.vue
[backend/auth-service] Indexing complete
[frontend/web-app] Re-indexing 1 file...
[backend/user-service] Change detected: src/models/user.py
[frontend/web-app] Indexing complete
[backend/user-service] Re-indexing 1 file...
```

### Color-Coded Output (conceptual - colors not visible here)
```bash
[backend/auth-service] Change detected: src/auth/login.py     # Red
[frontend/web-app] Change detected: src/components/Login.vue   # Green
[backend/user-service] Change detected: src/models/user.py     # Blue
```

### Aligned Prefix Format
```bash
[backend/auth-service    ] Change detected: src/auth/login.py
[frontend/web-app        ] Change detected: src/components/Login.vue
[backend/user-service    ] Change detected: src/models/user.py
```

### Abbreviated Paths
```bash
[.../auth-service] Change detected: src/auth/login.py
[.../web-app     ] Change detected: src/components/Login.vue
[.../user-service] Change detected: src/models/user.py
```

### With Visual Separation
```bash
[backend/auth-service] Change detected: src/auth/login.py
[backend/auth-service] Re-indexing 1 file...
[backend/auth-service] Indexing complete

[frontend/web-app] Change detected: src/components/Login.vue
[frontend/web-app] Re-indexing 1 file...

[backend/user-service] Change detected: src/models/user.py
```

## User Experience Principles
- Immediately clear which repository is active
- Consistent and recognizable format
- Visual aids (color) when available
- Readable without color
- Scannable output for quick comprehension
- No ambiguity about source repository

## Configuration Options

### Environment Variables
```bash
# Disable colors
export NO_COLOR=1

# Force colors even if not a TTY
export FORCE_COLOR=1

# Use abbreviated paths
export CIDX_ABBREVIATE_REPOS=1

# Set max repository name length
export CIDX_MAX_REPO_NAME=25
```

### Command-Line Flags (future enhancement)
```bash
cidx watch --no-color
cidx watch --abbreviate-repos
cidx watch --aligned-prefixes
```
