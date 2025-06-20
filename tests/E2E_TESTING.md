# End-to-End Testing Framework

This directory contains the E2E testing framework for Code Indexer's embedding providers. The tests are designed to work with real API services when available, but gracefully skip tests when API tokens are not configured.

## Test Structure

### Test Files

- `test_e2e_embedding_providers.py` - Main E2E test suite
- `e2e_test_setup.py` - Setup script and test runner
- `pytest_e2e.ini` - Pytest configuration for E2E tests
- `E2E_TESTING.md` - This documentation file

### Test Categories

1. **TestVoyageAIRealAPI** - Real API integration tests
   - Requires: `VOYAGE_API_KEY` environment variable
   - Tests: Connection, embedding generation, batch processing, rate limiting

2. **TestE2EProviderSwitching** - Provider compatibility tests
   - Tests: Factory pattern, provider switching, configuration

3. **TestE2EQdrantIntegration** - Database integration tests
   - Tests: Model metadata, filtering, multi-provider coexistence

4. **TestE2EFullWorkflow** - Complete workflow scenarios
   - Tests: End-to-end functionality with real code samples

## Setup and Usage

### Quick Start

```bash
# Check environment and run all available tests
python tests/e2e_test_setup.py

# Show configuration guide only
python tests/e2e_test_setup.py guide

# Check environment only
python tests/e2e_test_setup.py check

# Test VoyageAI connection only
python tests/e2e_test_setup.py test-voyage
```

### Manual Test Execution

```bash
# Run all E2E tests
pytest tests/test_e2e_embedding_providers.py -v

# Run only VoyageAI tests (requires API key)
pytest tests/test_e2e_embedding_providers.py::TestVoyageAIRealAPI -v

# Run tests without real API calls
pytest tests/test_e2e_embedding_providers.py -m "not real_api" -v

# Run only fast tests
pytest tests/test_e2e_embedding_providers.py -m "not slow" -v
```

### Test Markers

The tests use pytest markers for categorization:

- `@pytest.mark.e2e` - All E2E tests
- `@pytest.mark.voyage_ai` - Tests requiring VoyageAI API
- `@pytest.mark.real_api` - Tests making real API calls
- `@pytest.mark.qdrant` - Tests requiring Qdrant service
- `@pytest.mark.slow` - Tests that take longer to run

## Environment Configuration

### Required Environment Variables

#### VoyageAI API Key (for VoyageAI tests)
```bash
export VOYAGE_API_KEY="your_api_key_here"
```

To make this persistent across terminal sessions:

```bash
# For bash
echo 'export VOYAGE_API_KEY="your_key"' >> ~/.bashrc
source ~/.bashrc

# For zsh
echo 'export VOYAGE_API_KEY="your_key"' >> ~/.zshrc
source ~/.zshrc
```

### Optional Environment Variables

```bash
# Ollama server URL (default: http://localhost:11434)
export OLLAMA_HOST="http://localhost:11434"

# Qdrant server URL (default: http://localhost:6333)
export QDRANT_HOST="http://localhost:6333"

# Test environment flag
export CODE_INDEXER_ENV="test"
```

## Test Behavior

### Graceful Skipping

Tests are designed to skip gracefully when required services or API keys are not available:

- VoyageAI tests skip if `VOYAGE_API_KEY` is not set
- Ollama tests skip if Ollama service is not reachable
- Qdrant tests skip if Qdrant service is not reachable

### Real API Usage

Tests marked with `@pytest.mark.real_api` make actual API calls to external services. These tests:

- Use real API quotas and may incur costs
- Respect rate limits and implement proper retry logic
- Test actual API behavior, not mocked responses
- Validate real embedding dimensions and model capabilities

### Test Data

E2E tests use:

- Temporary directories for configuration and test projects
- Sample Python code files with realistic content
- Small batch sizes to minimize API usage and costs
- Conservative rate limits to avoid hitting API quotas

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install -e .
        pip install pytest pytest-asyncio
    
    - name: Run E2E tests (without real API)
      run: |
        pytest tests/test_e2e_embedding_providers.py -m "not real_api" -v
    
    - name: Run VoyageAI E2E tests
      if: ${{ secrets.VOYAGE_API_KEY }}
      env:
        VOYAGE_API_KEY: ${{ secrets.VOYAGE_API_KEY }}
      run: |
        pytest tests/test_e2e_embedding_providers.py::TestVoyageAIRealAPI -v
```

### Local Development

For local development, you can set up a `.env` file (not tracked in git):

```bash
# .env file (add to .gitignore)
VOYAGE_API_KEY=your_api_key_here
OLLAMA_HOST=http://localhost:11434
QDRANT_HOST=http://localhost:6333
```

Then load it before running tests:

```bash
# Load environment from .env file
set -a; source .env; set +a

# Run E2E tests
python tests/e2e_test_setup.py
```

## Troubleshooting

### Common Issues

1. **API Key Not Found**
   ```
   VOYAGE_API_KEY environment variable not set
   ```
   - Solution: Set the environment variable as described above

2. **Connection Timeouts**
   ```
   Failed to connect to VoyageAI API
   ```
   - Check internet connection
   - Verify API key is valid
   - Check for rate limiting

3. **Permission Errors**
   ```
   Permission denied when creating temporary files
   ```
   - Ensure write permissions in the test directory
   - Check available disk space

4. **Import Errors**
   ```
   ModuleNotFoundError: No module named 'code_indexer'
   ```
   - Run tests from the project root directory
   - Ensure the package is installed: `pip install -e .`

### Debug Mode

Run tests with debug output:

```bash
# Verbose output with logging
pytest tests/test_e2e_embedding_providers.py -v -s --log-cli-level=DEBUG

# Run specific test with detailed output
pytest tests/test_e2e_embedding_providers.py::TestVoyageAIRealAPI::test_voyage_ai_real_connection -v -s
```

## Contributing

When adding new E2E tests:

1. **Follow the graceful skipping pattern** - Always check for required services/keys
2. **Use appropriate markers** - Mark tests with relevant pytest markers
3. **Minimize API usage** - Use small test data and conservative rate limits
4. **Add documentation** - Update this README with new test descriptions
5. **Test locally** - Verify tests work both with and without real API keys

### Test Template

```python
@pytest.mark.e2e
@pytest.mark.real_api  # If makes real API calls
def test_new_feature(self, api_key_available, console):
    """Test description."""
    # Skip if required services not available
    if not api_key_available:
        pytest.skip("API key not available")
    
    # Test implementation
    assert True  # Replace with actual test logic
```