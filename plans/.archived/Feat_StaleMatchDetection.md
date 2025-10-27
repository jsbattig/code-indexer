# Feature: Stale Match Detection (File-Level Granularity)

## 🎯 **Feature Overview**

Implement file-level staleness detection using timestamp comparison between local files and remote index data. Provides users with awareness of result relevance based on file modification times.

## ✅ **Acceptance Criteria**

### Local vs Remote Timestamp Comparison
- ✅ Compare local file mtime with remote index timestamp for each result
- ✅ Flag results where local file is newer than remote index
- ✅ Provide staleness indicators in query results
- ✅ Handle timezone differences with UTC normalization

### Universal Staleness Detection
- ✅ Apply staleness detection to both local AND remote query results
- ✅ Consistent staleness indicators across both modes
- ✅ Same algorithm and thresholds for fairness
- ✅ Clear visual indicators for stale vs fresh results

### Timezone-Independent Comparison
- ✅ Normalize all timestamps to UTC for accurate comparison
- ✅ Handle different server and client timezone configurations
- ✅ Account for daylight saving time transitions
- ✅ Provide accurate staleness detection across global teams

## 📊 **Stories**
1. **Local vs Remote Timestamp Comparison**: File-level staleness detection
2. **Timezone Independent Comparison**: UTC normalization for accuracy
3. **Stale Detection for Both Modes**: Universal staleness awareness