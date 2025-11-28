# Meta-Repo Discovery: RAG-Style Repository Discovery

## Overview

The meta-repository (cidx-meta-global) serves as the canonical discovery endpoint for finding relevant repositories before searching them. This enables a RAG-style (Retrieval-Augmented Generation) workflow where AI assistants first discover which repositories are relevant, then search within those specific repositories for precise results.

## Why Use Meta-Repo Discovery?

### Problem: Global Search Noise

When searching across many repositories simultaneously, results can be:
- Overwhelming (too many matches from irrelevant repos)
- Diluted (relevant matches buried in noise)
- Inefficient (searching repos that don't contain what you need)

### Solution: Two-Step Discovery Workflow

1. **Discovery Phase**: Query the meta-repo to find relevant repositories
2. **Search Phase**: Query specific repositories for detailed code search

This mimics how humans research: first find the right book, then read it.

## Quick Start

### 1. Initialize Meta-Directory

```bash
cidx global init-meta
```

This creates:
- A meta-directory at `~/.code-indexer/golden-repos/cidx-meta`
- AI-generated descriptions for all registered global repos
- Registers meta-directory as `cidx-meta-global`

### 2. Discover Repositories

```bash
cidx query "authentication libraries" --repo cidx-meta-global --limit 5
```

Example output:
```
Repository: auth-service (auth-service-global)
Score: 0.92
JWT authentication service with OAuth2 support and token refresh...

Repository: user-management (user-management-global)
Score: 0.78
User registration and role-based access control with password hashing...
```

### 3. Search Specific Repository

```bash
cidx query "JWT token validation" --repo auth-service-global --limit 10
```

This searches only the `auth-service` repository for precise results.

## Meta-Repo as Well-Known Endpoint (AC1)

### Reserved Names

The following names are reserved for the meta-directory:

- `cidx-meta-global` - Primary discovery endpoint
- `cidx-meta` - Alias for convenience

**These names cannot be used for user repositories.**

Attempting to register a repo with these names will fail:

```bash
Error: Cannot register repo with name 'cidx-meta-global':
This name is reserved for meta-directory for repository discovery.
Choose a different alias name for your repository.
```

### Documentation and Conventions

- **Discovery endpoint**: Always use `cidx-meta-global` for discovery queries
- **Well-known**: This is the standard way to find repositories
- **AI-friendly**: Designed for AI assistants to use programmatically

## Discovery Query Response Format (AC2)

Query results from `cidx-meta-global` include:

- **Repo Name**: Base name of the repository
- **Global Alias**: Full alias for use with `--repo` flag
- **Relevance Score**: Similarity score (0.0 to 1.0)
- **Description Snippet**: AI-generated summary of repository purpose
- **Technologies**: Languages/frameworks used in the repo

### Example JSON Response (MCP/REST)

```json
{
  "query": "authentication libraries",
  "repo": "cidx-meta-global",
  "results": [
    {
      "repo_name": "auth-service",
      "global_alias": "auth-service-global",
      "relevance_score": 0.92,
      "description_snippet": "JWT authentication service with OAuth2 support...",
      "technologies": ["Python", "FastAPI", "JWT"],
      "source_file": "auth-service.md"
    }
  ]
}
```

## RAG Workflow Integration (AC3)

### Complete Workflow Example

User question: "How do we validate JWT tokens in our authentication system?"

#### Step 1: Discovery Query

```bash
cidx query "JWT authentication validation" --repo cidx-meta-global --limit 3
```

Results show:
- `auth-service-global` (score: 0.95)
- `api-gateway-global` (score: 0.72)
- `user-management-global` (score: 0.68)

#### Step 2: Targeted Search

```bash
cidx query "JWT token validation middleware" --repo auth-service-global --limit 10
```

This returns precise code locations within the auth-service repo.

#### Step 3: Follow-Up (if needed)

If auth-service doesn't have what you need, query the next most relevant repo:

```bash
cidx query "JWT validation" --repo api-gateway-global --limit 10
```

### Benefits of Two-Step Workflow

- **Precision**: Focus search on relevant repos only
- **Efficiency**: Don't search 100 repos when you need 1
- **Context**: Understand which repos contain what before diving in
- **Scalability**: Works with 10 repos or 1000 repos

## Catalog Completeness (AC4)

### Verify All Repos Registered

Use `cidx global list` to verify all golden repos are registered:

```bash
cidx global list
```

Output:
```
                    Global Repositories (5 total)
Alias                  Repo Name         URL
auth-service-global    auth-service      https://github.com/org/auth
user-management-global user-management   https://github.com/org/users
api-gateway-global     api-gateway       https://github.com/org/gateway
cidx-meta-global       cidx-meta         (local)
```

### One-to-One Mapping

Every registered golden repo should have a corresponding description in the meta-directory:

- Golden repo registered → Description file created
- Description file → Indexed in cidx-meta-global
- Query meta-repo → Discover all repos

### Missing Descriptions

If a repo is registered but missing from discovery results:

1. Check `cidx global list` to verify registration
2. Run `cidx global init-meta` to regenerate descriptions
3. Query meta-repo again to verify completeness

## Catalog Freshness Indicator (AC5)

### Check Meta-Repo Status

Use `cidx global status` to check when the catalog was last refreshed:

```bash
cidx global status cidx-meta-global
```

Output:
```
Repository Status: cidx-meta-global
Alias:        cidx-meta-global
Repo Name:    cidx-meta
URL:          (local repository)
Index Path:   ~/.code-indexer/golden-repos/cidx-meta/.code-indexer/index
Created:      2025-11-28 09:00:00 UTC
Last Refresh: 2025-11-28 09:30:00 UTC
```

### Interpreting Freshness

- **Last Refresh**: When meta-directory was last updated
- **Staleness**: If new repos registered after this time, they won't appear in discovery
- **Action**: Run `cidx global init-meta` to refresh if stale

### When to Refresh

Refresh the meta-directory when:

- New repos are registered
- Repo descriptions become outdated
- Discovery results seem incomplete
- After significant changes to registered repos

## Command Reference

### Global Commands

#### List All Global Repos

```bash
cidx global list
```

Shows all registered global repositories with their aliases, URLs, and last refresh timestamps.

#### Check Repository Status

```bash
cidx global status <alias-name>
```

Shows detailed metadata for a specific global repository:
- Alias and repo name
- Repository URL
- Index storage location
- Creation and last refresh timestamps

#### Initialize Meta-Directory

```bash
cidx global init-meta
```

Creates or refreshes the meta-directory with descriptions for all registered repos.

### Query Commands

#### Discover Repositories

```bash
cidx query "<search-term>" --repo cidx-meta-global [--limit N]
```

Search meta-directory to discover relevant repositories.

#### Search Specific Repository

```bash
cidx query "<search-term>" --repo <alias-name> [--limit N]
```

Search within a specific repository discovered in step 1.

## Best Practices

### For AI Assistants

1. **Start with Discovery**: Always query `cidx-meta-global` first for new topics
2. **Use Scores**: Focus on repos with score > 0.7 for relevance
3. **Iterate**: If first repo doesn't have results, try next highest score
4. **Cache Results**: Remember which repos contain what for session efficiency

### For Users

1. **Keep Meta Fresh**: Refresh after registering new repos
2. **Descriptive Repos**: Ensure repo README files describe their purpose clearly
3. **Verify Completeness**: Use `cidx global list` to check all repos registered
4. **Monitor Staleness**: Check `cidx global status cidx-meta-global` periodically

### For Organizations

1. **Standardize Discovery**: Train teams to use meta-repo for exploration
2. **Maintain Descriptions**: Keep repo READMEs up-to-date for better discovery
3. **Regular Refresh**: Schedule periodic meta-directory refreshes
4. **Document Repos**: Add clear purpose statements to repo documentation

## Troubleshooting

### Repository Not Appearing in Discovery

**Problem**: Query meta-repo but repo doesn't show up

**Solutions**:
1. Verify repo is registered: `cidx global list`
2. Check if repo has a README or description
3. Refresh meta-directory: `cidx global init-meta`
4. Query again with broader terms

### Discovery Results Too Broad

**Problem**: Too many repos returned, all with similar scores

**Solutions**:
1. Use more specific search terms
2. Add technical keywords (e.g., "Python JWT authentication" vs "auth")
3. Use `--limit` to reduce results
4. Focus on highest-scoring repos (>0.8)

### Reserved Name Error

**Problem**: Cannot register repo with desired name

**Error**: `Cannot register repo with name 'cidx-meta-global': This name is reserved...`

**Solution**: Choose a different alias name. Reserved names:
- `cidx-meta-global`
- `cidx-meta`

### Stale Catalog

**Problem**: New repos registered but not appearing in discovery

**Solutions**:
1. Check last refresh: `cidx global status cidx-meta-global`
2. Refresh meta-directory: `cidx global init-meta`
3. Verify new repos indexed: `cidx global list`

## Technical Details

### Meta-Directory Structure

```
~/.code-indexer/golden-repos/
  cidx-meta/                      # Meta-directory
    auth-service.md               # AI-generated description
    user-management.md            # AI-generated description
    api-gateway.md                # AI-generated description
    .code-indexer/
      index/                      # Indexed descriptions
```

### Description File Format

Each `.md` file contains:
- Repository name and purpose
- Primary technologies and frameworks
- Key features and capabilities
- Use cases and examples

These are AI-generated from:
- README files
- Package metadata
- Directory structure analysis
- Code statistics

### Indexing Process

1. Generate descriptions for each registered repo
2. Write descriptions to `.md` files in `cidx-meta/`
3. Index all descriptions using standard CIDX indexing
4. Register meta-directory as `cidx-meta-global`
5. Query just like any other global repo

## Related Documentation

- [Global Repos Architecture](architecture.md#global-repos)
- [Query Command Reference](../README.md#query-command)
- [Migration to v8.0](migration-to-v8.md)
