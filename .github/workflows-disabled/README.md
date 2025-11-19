# Disabled Workflows

This directory contains GitHub Actions workflows that are intentionally disabled but preserved for future use.

## publish.yml - PyPI Publishing Workflow

**Status**: Disabled (moved from `.github/workflows/`)
**Purpose**: Publish CIDX package to PyPI when a GitHub release is created

### Why Disabled?

GitHub Actions was persistently triggering this workflow on push events despite being configured to only run on release:published events. This caused spurious workflow failures visible in the Actions tab.

### How to Enable for Publishing

When you're ready to publish a new version to PyPI:

```bash
# 1. Move workflow back to active directory
mv .github/workflows-disabled/publish.yml .github/workflows/

# 2. Commit the change
git add .github/workflows/publish.yml
git commit -m "chore: enable publish workflow for release"
git push

# 3. Create and publish a GitHub release
# The workflow will automatically trigger and publish to PyPI

# 4. Optional: Disable again after publishing
mv .github/workflows/publish.yml .github/workflows-disabled/
git add -A
git commit -m "chore: disable publish workflow after release"
git push
```

### Workflow Requirements

- **Trigger**: Runs only on `release: types: [published]` events
- **Environment**: Uses `release` environment (configure in repo settings)
- **Publishing**: Uses PyPI trusted publishing (no API token needed)
- **Configuration**: Must set up trusted publishing at https://pypi.org/manage/account/publishing/

### Alternative: Manual Publishing

If you prefer not to use the workflow, you can publish manually:

```bash
# Build the package
python -m build

# Publish to PyPI (requires PyPI credentials)
python -m twine upload dist/*
```
