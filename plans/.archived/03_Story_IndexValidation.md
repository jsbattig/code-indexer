# Story 3.3: Index Validation

## Story Description

As a CIDX quality assurance system, I need to validate the semantic index integrity after sync and indexing operations, ensuring search quality remains high and detecting any corruption or inconsistencies that could degrade user experience.

## Technical Specification

### Validation Framework

```pseudocode
class IndexValidator:
    def validate(index: SemanticIndex) -> ValidationReport:
        checks = [
            checkIntegrity(),
            checkCompleteness(),
            checkConsistency(),
            checkQuality(),
            checkPerformance()
        ]

        return ValidationReport {
            passed: all(checks),
            issues: collectIssues(checks),
            metrics: collectMetrics(checks),
            recommendations: generateRecommendations()
        }

class ValidationCheck:
    name: string
    severity: CRITICAL | WARNING | INFO

    def execute() -> CheckResult
    def repair() -> bool

class CheckResult:
    passed: bool
    message: string
    details: dict
    repairPossible: bool
```

### Integrity Checks

```pseudocode
class IntegrityChecker:
    def checkVectorDimensions():
        # All embeddings have consistent dimensions

    def checkDocumentReferences():
        # All document IDs correspond to real files

    def checkMetadataCompleteness():
        # Required metadata present for all entries

    def checkIndexCorruption():
        # No corrupted entries in vector store

    def checkDuplicates():
        # No duplicate embeddings for same content
```

## Acceptance Criteria

### Integrity Checks
```gherkin
Given an indexed repository
When running integrity validation
Then the system should verify:
  - All embeddings have correct dimensions
  - Document IDs map to existing files
  - No corrupted entries exist
  - No unexpected duplicates found
  - Metadata is complete and valid
And report any integrity violations
```

### Quality Metrics
```gherkin
Given a validated index
When calculating quality metrics
Then the system should measure:
  - Search result relevance (precision/recall)
  - Embedding coverage (% files indexed)
  - Freshness (age of embeddings)
  - Diversity (distribution of content)
  - Coherence (semantic clustering quality)
And provide quality score (0-100)
```

### Consistency Verification
```gherkin
Given indexed content and source files
When verifying consistency
Then the system should check:
  - File count matches index entries
  - Modified dates align with index
  - File content matches embeddings
  - Dependencies are bidirectional
  - No orphaned references exist
And flag any inconsistencies
```

### Recovery Procedures
```gherkin
Given validation issues detected
When attempting recovery
Then the system should:
  - Categorize issues by severity
  - Attempt automatic repairs for minor issues
  - Re-index specific files if needed
  - Remove corrupted entries safely
  - Log all recovery actions
And report recovery success/failure
```

### Performance Validation
```gherkin
Given a production index
When testing performance
Then the system should verify:
  - Query response time <100ms
  - Similarity search accuracy >90%
  - Index size within limits
  - Memory usage acceptable
  - No performance degradation
And alert if thresholds exceeded
```

## Completion Checklist

- [ ] Integrity checks
  - [ ] Vector dimension validation
  - [ ] Document reference checks
  - [ ] Corruption detection
  - [ ] Duplicate detection
  - [ ] Metadata validation
- [ ] Quality metrics
  - [ ] Relevance scoring
  - [ ] Coverage calculation
  - [ ] Freshness assessment
  - [ ] Diversity analysis
  - [ ] Coherence measurement
- [ ] Consistency verification
  - [ ] File count matching
  - [ ] Timestamp alignment
  - [ ] Content verification
  - [ ] Dependency validation
- [ ] Recovery procedures
  - [ ] Issue categorization
  - [ ] Automatic repair logic
  - [ ] Selective re-indexing
  - [ ] Corruption cleanup
  - [ ] Recovery logging

## Test Scenarios

### Happy Path
1. Clean index → All checks pass → Score 95+
2. Minor issues → Auto-repair → Index healthy
3. After sync → Validation → Consistency confirmed
4. Performance test → Meets targets → Approved

### Error Cases
1. Corrupted entries → Detected → Removed successfully
2. Missing files → Identified → Orphans cleaned
3. Dimension mismatch → Found → Re-indexing triggered
4. Quality degraded → Measured → Full re-index suggested

### Edge Cases
1. Empty index → Valid state → Score reflects empty
2. Partial index → Detected → Completion suggested
3. Old format → Recognized → Migration recommended
4. External changes → Detected → Sync suggested

## Performance Requirements

- Full validation: <30 seconds for 10k documents
- Integrity check: <10 seconds
- Quality metrics: <5 seconds
- Sample queries: <1 second each
- Recovery attempt: <60 seconds

## Validation Metrics

### Quality Score Calculation
```yaml
quality_score:
  components:
    integrity: 40%     # No corruption, complete metadata
    consistency: 30%   # Files match index
    performance: 20%   # Query speed and accuracy
    freshness: 10%     # Age of embeddings

  thresholds:
    excellent: 90-100  # No action needed
    good: 75-89        # Minor issues, monitor
    fair: 60-74        # Issues detected, action recommended
    poor: <60          # Significant issues, immediate action
```

### Issue Severity Levels

| Level | Description | Action Required |
|-------|-------------|-----------------|
| CRITICAL | Index unusable | Immediate re-index |
| HIGH | Major degradation | Repair within hour |
| MEDIUM | Quality issues | Schedule maintenance |
| LOW | Minor issues | Monitor, fix eventually |
| INFO | Optimization opportunity | Consider improvement |

## Sample Validation Report

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "score": 87,
  "status": "GOOD",
  "summary": "Index healthy with minor issues",
  "checks": {
    "integrity": {
      "passed": true,
      "score": 95,
      "issues": []
    },
    "consistency": {
      "passed": true,
      "score": 88,
      "issues": [
        {
          "type": "STALE_ENTRY",
          "count": 3,
          "severity": "LOW"
        }
      ]
    },
    "quality": {
      "passed": true,
      "score": 82,
      "metrics": {
        "precision": 0.91,
        "recall": 0.85,
        "coverage": 0.94
      }
    },
    "performance": {
      "passed": true,
      "score": 90,
      "metrics": {
        "avgQueryTime": 45,
        "p99QueryTime": 98
      }
    }
  },
  "recommendations": [
    "Remove 3 stale entries for consistency",
    "Consider re-indexing 5 files older than 30 days"
  ]
}
```

## Recovery Matrix

| Issue Type | Auto-Repair | Manual Action | Prevention |
|------------|-------------|---------------|------------|
| Corrupted entry | Remove entry | Re-index file | Validation on write |
| Missing file | Remove from index | None needed | File watch system |
| Duplicate entry | Keep newest | Investigate cause | Dedup on insert |
| Wrong dimensions | Re-generate | Check model config | Model validation |
| Stale metadata | Update metadata | Refresh index | Periodic updates |

## Definition of Done

- [ ] All validation checks implemented
- [ ] Quality metrics accurately calculated
- [ ] Consistency verification complete
- [ ] Recovery procedures functional
- [ ] Performance validation working
- [ ] Detailed reports generated
- [ ] Auto-repair for common issues
- [ ] Unit tests >90% coverage
- [ ] Integration tests cover all checks
- [ ] Performance benchmarks met