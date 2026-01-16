"""
Unit tests for jobs.html template - Story #724.

Tests that the job type filter dropdown includes all operation types
and that filter values match actual database column values.

These tests verify acceptance criteria:
- AC1: Dropdown includes `global_repo_refresh` option
- AC2: Dropdown includes `add_index` option
- AC3: Dropdown includes `sync_repository` option
- AC4: Filter value `activate_repository` matches actual DB value
- AC5: Filter value `deactivate_repository` matches actual DB value
- AC6: All filter values exactly match database column values
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import pytest


# The canonical list of operation_type values from the codebase:
# - add_golden_repo         : golden_repo_manager.py:400
# - remove_golden_repo      : golden_repo_manager.py:622
# - refresh_golden_repo     : golden_repo_manager.py:1242
# - add_index               : golden_repo_manager.py:1884
# - sync_repository         : handlers.py:1277
# - global_repo_refresh     : refresh_scheduler.py:217
# - activate_repository     : activated_repo_manager.py:219
# - deactivate_repository   : activated_repo_manager.py:653
EXPECTED_OPERATION_TYPES = {
    "add_golden_repo": "Add Golden Repo",
    "remove_golden_repo": "Remove Golden Repo",
    "refresh_golden_repo": "Refresh Golden Repo",
    "add_index": "Add Index",
    "sync_repository": "Sync Repository",
    "global_repo_refresh": "Global Repo Refresh (Scheduled)",
    "activate_repository": "Activate Repo",
    "deactivate_repository": "Deactivate Repo",
}


@pytest.fixture
def jobs_template():
    """Load the jobs.html template for testing."""
    templates_dir = (
        Path(__file__).parent.parent.parent.parent.parent
        / "src"
        / "code_indexer"
        / "server"
        / "web"
        / "templates"
    )
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    return env.get_template("jobs.html")


@pytest.fixture
def base_context():
    """Provide minimal context needed to render jobs.html."""
    return {
        "queue_status": {
            "running_count": 0,
            "queued_count": 0,
            "max_total_concurrent_jobs": 4,
            "max_concurrent_jobs_per_user": 2,
        },
        "jobs": [],
        "total_pages": 1,
        "current_page": 1,
        "status_filter": "",
        "type_filter": "",
        "search": "",
    }


class TestJobsDropdownContainsAllOperationTypes:
    """Tests for AC1-AC3: Dropdown includes all missing operation types."""

    def test_dropdown_contains_global_repo_refresh(self, jobs_template, base_context):
        """AC1: Dropdown includes global_repo_refresh option."""
        rendered = jobs_template.render(base_context)

        assert (
            'value="global_repo_refresh"' in rendered
        ), "Dropdown must include option with value='global_repo_refresh'"
        assert (
            "Global Repo Refresh" in rendered
        ), "Dropdown must include 'Global Repo Refresh' label"

    def test_dropdown_contains_add_index(self, jobs_template, base_context):
        """AC2: Dropdown includes add_index option."""
        rendered = jobs_template.render(base_context)

        assert (
            'value="add_index"' in rendered
        ), "Dropdown must include option with value='add_index'"
        assert ">Add Index<" in rendered, "Dropdown must include 'Add Index' label"

    def test_dropdown_contains_sync_repository(self, jobs_template, base_context):
        """AC3: Dropdown includes sync_repository option."""
        rendered = jobs_template.render(base_context)

        assert (
            'value="sync_repository"' in rendered
        ), "Dropdown must include option with value='sync_repository'"
        assert (
            ">Sync Repository<" in rendered
        ), "Dropdown must include 'Sync Repository' label"


class TestJobsDropdownValuesMatchDatabaseValues:
    """Tests for AC4-AC6: Filter values match actual database column values."""

    def test_activate_filter_uses_activate_repository(
        self, jobs_template, base_context
    ):
        """AC4: Filter value for activate must be 'activate_repository' not 'activate_repo'."""
        rendered = jobs_template.render(base_context)

        # Must use correct value
        assert (
            'value="activate_repository"' in rendered
        ), "Activate filter must use value='activate_repository' to match DB"
        # Must NOT use wrong value
        assert (
            'value="activate_repo"' not in rendered
        ), "Filter must NOT use 'activate_repo' - it doesn't match DB value"

    def test_deactivate_filter_uses_deactivate_repository(
        self, jobs_template, base_context
    ):
        """AC5: Filter value for deactivate must be 'deactivate_repository' not 'deactivate_repo'."""
        rendered = jobs_template.render(base_context)

        # Must use correct value
        assert (
            'value="deactivate_repository"' in rendered
        ), "Deactivate filter must use value='deactivate_repository' to match DB"
        # Must NOT use wrong value
        assert (
            'value="deactivate_repo"' not in rendered
        ), "Filter must NOT use 'deactivate_repo' - it doesn't match DB value"

    def test_all_operation_types_present_in_dropdown(self, jobs_template, base_context):
        """AC6: All operation types must be present in the dropdown."""
        rendered = jobs_template.render(base_context)

        missing_types = []
        for op_type in EXPECTED_OPERATION_TYPES.keys():
            if f'value="{op_type}"' not in rendered:
                missing_types.append(op_type)

        assert not missing_types, (
            f"Missing operation types in dropdown: {missing_types}. "
            f"All types must be present: {list(EXPECTED_OPERATION_TYPES.keys())}"
        )


class TestJobsDropdownSelectedState:
    """Tests that selected state works correctly for filter."""

    @pytest.mark.parametrize("op_type,label", EXPECTED_OPERATION_TYPES.items())
    def test_type_filter_shows_selected_state(
        self, jobs_template, base_context, op_type, label
    ):
        """Each operation type filter should show selected state when active."""
        context = {**base_context, "type_filter": op_type}
        rendered = jobs_template.render(context)

        # Check that the option has selected attribute when filter is active
        # The pattern is: value="op_type" ... selected
        assert (
            f'value="{op_type}"' in rendered
        ), f"Operation type {op_type} must be in dropdown"
        # When type_filter matches, the option should be marked selected
        # We verify by checking the Jinja2 conditional rendered correctly
        select_section = rendered.split('id="job_type"')[1].split("</select>")[0]
        expected_selected = f'value="{op_type}"'
        option_line = [
            line for line in select_section.split("\n") if expected_selected in line
        ]
        assert option_line, f"Could not find option for {op_type}"
        # When filter is set, the option should have 'selected'
        assert (
            "selected" in option_line[0]
        ), f"Option {op_type} should be marked selected when type_filter='{op_type}'"
