# MCP/REST Parity Matrix
**Generated:** generate_parity_matrix.py
**Total MCP Tools:** 75
**Tools with REST Endpoints:** 20
**MCP-only Tools:** 41
**Missing REST Endpoints:** 14

## File CRUD
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| create_file ✓ | POST /api/v1/repos/{alias}/files | Yes | Yes |
| delete_file ✓ | DELETE /api/v1/repos/{alias}/files/{file_path:path} | Yes | Yes |
| edit_file ✓ | PATCH /api/v1/repos/{alias}/files/{file_path:path} | Yes | Yes |

## Git Branches
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| git_branch_create ✓ | POST /api/v1/repos/{alias}/git/branches | Yes | Yes |
| git_branch_delete ✓ | DELETE /api/v1/repos/{alias}/git/branches/{name} | Yes | Yes |
| git_branch_list ✓ | GET /api/v1/repos/{alias}/git/branches | Yes | Yes |
| git_branch_switch ✓ | POST /api/v1/repos/{alias}/git/branches/{name}/switch | Yes | Yes |

## Git Inspection
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| git_blame | - | Yes | Yes |
| git_diff ✓ | GET /api/v1/repos/{alias}/git/diff | Yes | Yes |
| git_file_at_revision | - | Yes | Yes |
| git_file_history | - | Yes | Yes |
| git_log ✓ | GET /api/v1/repos/{alias}/git/log | Yes | Yes |
| git_search_commits | - | Yes | Yes |
| git_search_diffs | - | Yes | Yes |
| git_show_commit | - | Yes | Yes |
| git_status ✓ | GET /api/v1/repos/{alias}/git/status | Yes | Yes |

## Git Recovery
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| git_checkout_file ✓ | POST /api/v1/repos/{alias}/git/checkout-file | Yes | Yes |
| git_clean ✓ | POST /api/v1/repos/{alias}/git/clean | Yes | Yes |
| git_merge_abort ✓ | POST /api/v1/repos/{alias}/git/merge-abort | Yes | Yes |
| git_reset ✓ | POST /api/v1/repos/{alias}/git/reset | Yes | Yes |

## Git Remote
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| git_fetch ✓ | POST /api/v1/repos/{alias}/git/fetch | Yes | Yes |
| git_pull ✓ | POST /api/v1/repos/{alias}/git/pull | Yes | Yes |
| git_push ✓ | POST /api/v1/repos/{alias}/git/push | Yes | Yes |

## Git Staging
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| git_commit ✓ | POST /api/v1/repos/{alias}/git/commit | Yes | Yes |
| git_stage ✓ | POST /api/v1/repos/{alias}/git/stage | Yes | Yes |
| git_unstage ✓ | POST /api/v1/repos/{alias}/git/unstage | Yes | Yes |

## Indexing
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| get_index_status ✗ | GET /api/v1/repos/{alias}/index/status (expected) | Yes | Yes |
| trigger_reindex ✗ | POST /api/v1/repos/{alias}/index (expected) | Yes | Yes |

## Other
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| authenticate | - | Yes | Yes |
| browse_directory | - | Yes | Yes |
| check_health | - | Yes | Yes |
| cidx_quick_reference | - | Yes | Yes |
| directory_tree | - | Yes | Yes |
| get_branches | - | Yes | Yes |
| get_file_content | - | Yes | Yes |
| get_global_config | - | Yes | Yes |
| get_job_details | - | Yes | Yes |
| get_job_statistics | - | Yes | Yes |
| get_tool_categories | - | Yes | Yes |
| list_files | - | Yes | Yes |
| set_global_config | - | Yes | Yes |
| switch_branch | - | Yes | Yes |

## Repository Mgmt
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| activate_repository | - | Yes | Yes |
| add_golden_repo | - | Yes | Yes |
| add_golden_repo_index | - | Yes | Yes |
| deactivate_repository | - | Yes | Yes |
| discover_repositories | - | Yes | Yes |
| get_all_repositories_status | - | Yes | Yes |
| get_golden_repo_indexes | - | Yes | Yes |
| get_repository_statistics | - | Yes | Yes |
| get_repository_status | - | Yes | Yes |
| global_repo_status | - | Yes | Yes |
| list_global_repos | - | Yes | Yes |
| list_repositories | - | Yes | Yes |
| manage_composite_repository | - | Yes | Yes |
| refresh_golden_repo | - | Yes | Yes |
| remove_golden_repo | - | Yes | Yes |
| sync_repository | - | Yes | Yes |

## SCIP
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| scip_callchain ✗ | POST /api/v1/scip/callchain (expected) | Yes | Yes |
| scip_context ✗ | POST /api/v1/scip/context (expected) | Yes | Yes |
| scip_definition ✗ | POST /api/v1/scip/definition (expected) | Yes | Yes |
| scip_dependencies ✗ | POST /api/v1/scip/dependencies (expected) | Yes | Yes |
| scip_dependents ✗ | POST /api/v1/scip/dependents (expected) | Yes | Yes |
| scip_impact ✗ | POST /api/v1/scip/impact (expected) | Yes | Yes |
| scip_references ✗ | POST /api/v1/scip/references (expected) | Yes | Yes |

## SSH Keys
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| cidx_ssh_key_assign_host ✗ | POST /api/v1/ssh-keys/{name}/hosts (expected) | Yes | Yes |
| cidx_ssh_key_create ✗ | POST /api/v1/ssh-keys (expected) | Yes | Yes |
| cidx_ssh_key_delete ✗ | DELETE /api/v1/ssh-keys/{name} (expected) | Yes | Yes |
| cidx_ssh_key_list ✗ | GET /api/v1/ssh-keys (expected) | Yes | Yes |
| cidx_ssh_key_show_public ✗ | GET /api/v1/ssh-keys/{name}/public (expected) | Yes | Yes |

## Search
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| regex_search | - | Yes | Yes |
| search_code | - | Yes | Yes |

## User Mgmt
| MCP Tool | REST Endpoint | Input Schema | Output Schema |
|----------|---------------|--------------|---------------|
| create_user | - | Yes | Yes |
| first_time_user_guide | - | Yes | Yes |
| list_users | - | Yes | Yes |

## Legend
- ✓ = REST endpoint exists
- ✗ = REST endpoint missing (expected to exist)
- No marker = MCP-only tool (no REST endpoint expected)
