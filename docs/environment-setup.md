# Environment Variables Setup

This document explains how to set up environment variables for the Code Indexer project.

## Overview

The project uses environment variables for API keys and other sensitive configuration. These are loaded from `.env` files to keep them out of version control.

## Setup Instructions

1. **Create .env.local file** (if it doesn't exist):
   ```bash
   touch .env.local
   ```

2. **Add your API keys** to `.env.local`:
   ```bash
   # Anthropic Claude API Key
   export CLAUDE_API_KEY="your-claude-api-key-here"
   
   # VoyageAI API Key (required for E2E tests)
   export VOYAGE_API_KEY="your-voyage-api-key-here"
   ```

3. **Source the file** in your shell (optional for manual testing):
   ```bash
   source .env.local
   ```

## Automatic Loading

Environment variables are automatically loaded in the following scenarios:

### For Tests
- When running tests via pytest, the `tests/conftest.py` automatically loads `.env.local` and `.env` files
- This ensures API keys are available for all tests without manual sourcing

### For Scripts
- `full-automation.sh` sources `.env` files automatically
- `ci-github.sh` sources `.env` files automatically
- Other shell scripts should add this near the top:
  ```bash
  # Source .env files if they exist
  if [[ -f ".env.local" ]]; then
      source .env.local
  fi
  if [[ -f ".env" ]]; then
      source .env
  fi
  ```

## File Priority

1. `.env.local` - Local overrides (gitignored)
2. `.env` - Default values (can be committed if no secrets)
3. System environment variables

## Security Notes

- **NEVER commit** `.env.local` - it's gitignored for security
- **NEVER commit** API keys or secrets to version control
- Use `.env.local` for all sensitive values
- Use `.env` only for non-sensitive defaults

## Troubleshooting

### Tests failing with "Invalid API key"
1. Check that `.env.local` exists and contains your API keys
2. Verify the API keys are correct and active
3. Run a single test to verify: 
   ```bash
   python -m pytest tests/test_e2e_embedding_providers.py -k test_voyage_ai_single_embedding -v
   ```

### Environment variable not found
1. Ensure you're in the project root directory
2. Check file permissions: `ls -la .env.local`
3. Verify the format uses `export KEY="value"`

## Required API Keys

### VoyageAI
- Required for: E2E tests, VoyageAI embedding provider
- Get your key at: https://voyageai.com/
- Test with: `echo $VOYAGE_API_KEY`

### Claude (Anthropic)
- Required for: Claude integration features
- Get your key at: https://console.anthropic.com/
- Test with: `echo $CLAUDE_API_KEY`