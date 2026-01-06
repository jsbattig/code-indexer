"""
Unit tests for config_section.html template rendering.

Tests that the template renders correctly with various data contexts,
particularly focusing on API Keys section that was having Jinja2 syntax errors.
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def test_api_keys_section_renders_with_github_token():
    """Verify API Keys section renders when GitHub token is configured."""
    # Setup Jinja2 environment
    templates_dir = (
        Path(__file__).parent.parent.parent.parent.parent
        / "src"
        / "code_indexer"
        / "server"
        / "web"
        / "templates"
    )
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    template = env.get_template("partials/config_section.html")

    # Mock context data
    context = {
        "csrf_token": "test-csrf-token",
        "config": {
            "server": {
                "host": "127.0.0.1",
                "port": 8000,
                "workers": 4,
                "log_level": "INFO",
                "jwt_expiration_minutes": 10,
            },
            "cache": {},
            "reindexing": {},
            "timeouts": {},
            "password_security": {},
            "oidc": {"enabled": False, "provider_name": "SSO"},
        },
        "validation_errors": {},
        "api_keys_status": [],
        "github_token_data": {
            "token": "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
            "platform": "github",
        },
        "gitlab_token_data": None,
    }

    # Render template
    rendered = template.render(context)

    # Verify API Keys section is present
    assert (
        "CI/CD API Keys" in rendered
    ), "API Keys section header should be in rendered HTML"
    assert "GitHub" in rendered, "GitHub subsection should be in rendered HTML"
    assert "GitLab" in rendered, "GitLab subsection should be in rendered HTML"

    # Verify token is masked in DISPLAY mode (shows prefix and asterisks)
    assert "ghp_" in rendered, "Token prefix should be visible"
    assert (
        "**************************" in rendered
    ), "Token should be masked with asterisks in display mode"

    # Note: Full token WILL appear in edit form's password input value attribute
    # This is expected - it's in a password field (browser-masked) for editing
    # The security property we care about: masked in the visible display table


def test_api_keys_section_renders_without_tokens():
    """Verify API Keys section renders when no tokens configured."""
    # Setup Jinja2 environment
    templates_dir = (
        Path(__file__).parent.parent.parent.parent.parent
        / "src"
        / "code_indexer"
        / "server"
        / "web"
        / "templates"
    )
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    template = env.get_template("partials/config_section.html")

    # Mock context data with no tokens
    context = {
        "csrf_token": "test-csrf-token",
        "config": {
            "server": {
                "host": "127.0.0.1",
                "port": 8000,
                "workers": 4,
                "log_level": "INFO",
                "jwt_expiration_minutes": 10,
            },
            "cache": {},
            "reindexing": {},
            "timeouts": {},
            "password_security": {},
            "oidc": {"enabled": False, "provider_name": "SSO"},
        },
        "validation_errors": {},
        "api_keys_status": [],
        "github_token_data": None,
        "gitlab_token_data": None,
    }

    # Render template
    rendered = template.render(context)

    # Verify API Keys section is present
    assert (
        "CI/CD API Keys" in rendered
    ), "API Keys section header should be in rendered HTML"
    assert "GitHub" in rendered, "GitHub subsection should be in rendered HTML"
    assert "GitLab" in rendered, "GitLab subsection should be in rendered HTML"

    # Verify "Not configured" state is shown
    assert (
        "Configure" in rendered
    ), "Configure button should be shown for unconfigured tokens"
