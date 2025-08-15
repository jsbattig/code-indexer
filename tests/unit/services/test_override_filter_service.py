"""
Test-driven development for OverrideFilterService.

Tests the filtering logic that applies override rules to file paths.
"""

from pathlib import Path

# Import the OverrideConfig from the main codebase
from code_indexer.config import OverrideConfig


class TestOverrideFilterService:
    """Test the override filtering service."""

    def test_service_initialization(self):
        """Test that service initializes with override config."""
        override_config = OverrideConfig(
            add_extensions=[".custom"],
            remove_extensions=[".tmp"],
            add_exclude_dirs=["temp"],
            add_include_dirs=["important"],
            force_include_patterns=["*.min.js"],
            force_exclude_patterns=["**/*.log"],
        )

        from code_indexer.services.override_filter_service import OverrideFilterService

        service = OverrideFilterService(override_config)

        assert service.override_config == override_config

    def test_force_exclude_patterns_override_everything(self):
        """Test that force_exclude_patterns override all other rules."""
        override_config = OverrideConfig(
            add_extensions=[".log"],  # Would normally include .log files
            remove_extensions=[],
            add_exclude_dirs=[],
            add_include_dirs=[],
            force_include_patterns=["important.log"],  # Would normally force include
            force_exclude_patterns=["**/*.log"],  # Should exclude ALL .log files
        )

        from code_indexer.services.override_filter_service import OverrideFilterService

        service = OverrideFilterService(override_config)

        # Even files that would be included by other rules should be excluded
        assert not service.should_include_file(Path("important.log"), base_result=True)
        assert not service.should_include_file(Path("src/debug.log"), base_result=True)
        assert not service.should_include_file(
            Path("any/path/file.log"), base_result=True
        )

    def test_force_include_patterns_override_base_exclusion(self):
        """Test that force_include_patterns override base exclusion decisions."""
        override_config = OverrideConfig(
            add_extensions=[],
            remove_extensions=[],
            add_exclude_dirs=[],
            add_include_dirs=[],
            force_include_patterns=["dist/*.min.js", "build/critical/**"],
            force_exclude_patterns=[],
        )

        from code_indexer.services.override_filter_service import OverrideFilterService

        service = OverrideFilterService(override_config)

        # Files that would normally be excluded should be included
        assert service.should_include_file(Path("dist/app.min.js"), base_result=False)
        assert service.should_include_file(
            Path("build/critical/config.json"), base_result=False
        )

        # Files not matching patterns should keep base result
        assert not service.should_include_file(
            Path("other/app.min.js"), base_result=False
        )
        assert service.should_include_file(Path("src/main.js"), base_result=True)

    def test_extension_filtering_logic(self):
        """Test add_extensions and remove_extensions filtering."""
        override_config = OverrideConfig(
            add_extensions=[".custom", ".special"],
            remove_extensions=[".tmp", ".cache"],
            add_exclude_dirs=[],
            add_include_dirs=[],
            force_include_patterns=[],
            force_exclude_patterns=[],
        )

        from code_indexer.services.override_filter_service import OverrideFilterService

        service = OverrideFilterService(override_config)

        # Files with added extensions should be included even if base says no
        assert service.should_include_file(Path("file.custom"), base_result=False)
        assert service.should_include_file(
            Path("src/config.special"), base_result=False
        )

        # Files with removed extensions should be excluded even if base says yes
        assert not service.should_include_file(Path("temp.tmp"), base_result=True)
        assert not service.should_include_file(Path("data.cache"), base_result=True)

        # Other files should keep base result
        assert service.should_include_file(Path("main.py"), base_result=True)
        assert not service.should_include_file(Path("readme.md"), base_result=False)

    def test_directory_filtering_logic(self):
        """Test add_include_dirs and add_exclude_dirs filtering."""
        override_config = OverrideConfig(
            add_extensions=[],
            remove_extensions=[],
            add_exclude_dirs=["temp-cache", "build-artifacts"],
            add_include_dirs=["important-build", "critical-temp"],
            force_include_patterns=[],
            force_exclude_patterns=[],
        )

        from code_indexer.services.override_filter_service import OverrideFilterService

        service = OverrideFilterService(override_config)

        # Files in excluded dirs should be excluded even if base says yes
        assert not service.should_include_file(
            Path("temp-cache/file.txt"), base_result=True
        )
        assert not service.should_include_file(
            Path("build-artifacts/output.js"), base_result=True
        )

        # Files in included dirs should be included even if base says no
        assert service.should_include_file(
            Path("important-build/config.json"), base_result=False
        )
        assert service.should_include_file(
            Path("critical-temp/data.xml"), base_result=False
        )

        # Files in other dirs should keep base result
        assert service.should_include_file(Path("src/main.py"), base_result=True)
        assert not service.should_include_file(
            Path("docs/readme.md"), base_result=False
        )

    def test_processing_order_force_exclude_wins(self):
        """Test that force_exclude_patterns win over force_include_patterns."""
        override_config = OverrideConfig(
            add_extensions=[],
            remove_extensions=[],
            add_exclude_dirs=[],
            add_include_dirs=[],
            force_include_patterns=[
                "important/**"
            ],  # Would include everything in important/
            force_exclude_patterns=["**/*.log"],  # Should exclude all .log files
        )

        from code_indexer.services.override_filter_service import OverrideFilterService

        service = OverrideFilterService(override_config)

        # force_exclude should win over force_include
        assert not service.should_include_file(
            Path("important/debug.log"), base_result=False
        )

        # force_include should work for non-excluded files
        assert service.should_include_file(
            Path("important/config.json"), base_result=False
        )

    def test_complex_integration_scenario(self):
        """Test complex scenario with multiple override rules."""
        override_config = OverrideConfig(
            add_extensions=[".special"],
            remove_extensions=[".tmp"],
            add_exclude_dirs=["temp"],
            add_include_dirs=["important"],
            force_include_patterns=["critical.*"],
            force_exclude_patterns=["**/*.log"],
        )

        from code_indexer.services.override_filter_service import OverrideFilterService

        service = OverrideFilterService(override_config)

        # Test various combinations
        assert service.should_include_file(
            Path("file.special"), base_result=False
        )  # add_extensions
        assert not service.should_include_file(
            Path("file.tmp"), base_result=True
        )  # remove_extensions
        assert not service.should_include_file(
            Path("temp/file.py"), base_result=True
        )  # add_exclude_dirs
        assert service.should_include_file(
            Path("important/file.py"), base_result=False
        )  # add_include_dirs
        assert service.should_include_file(
            Path("critical.config"), base_result=False
        )  # force_include_patterns
        assert not service.should_include_file(
            Path("critical.log"), base_result=True
        )  # force_exclude_patterns wins

        # Normal files should keep base result
        assert service.should_include_file(Path("src/main.py"), base_result=True)
        assert not service.should_include_file(
            Path("docs/readme.md"), base_result=False
        )

    def test_empty_override_config_preserves_base_result(self):
        """Test that empty override config doesn't change base filtering result."""
        override_config = OverrideConfig(
            add_extensions=[],
            remove_extensions=[],
            add_exclude_dirs=[],
            add_include_dirs=[],
            force_include_patterns=[],
            force_exclude_patterns=[],
        )

        from code_indexer.services.override_filter_service import OverrideFilterService

        service = OverrideFilterService(override_config)

        # Should preserve base results for all files
        assert service.should_include_file(Path("main.py"), base_result=True)
        assert not service.should_include_file(Path("temp.txt"), base_result=False)
        assert service.should_include_file(Path("src/config.json"), base_result=True)
