# User Story: Local vs Remote Timestamp Comparison

## 📋 **User Story**

As a **CIDX user**, I want **file-level staleness indicators comparing my local file modifications with remote index timestamps**, so that **I can assess the relevance of query results based on when files were last indexed**.

## 🎯 **Business Value**

Provides crucial context for result interpretation. Users can make informed decisions about result relevance when they know local files have changed since remote indexing.

## 📝 **Acceptance Criteria**

### Given: File-Level Timestamp Comparison
**When** I receive query results from remote repositories  
**Then** each result shows comparison between local file mtime and remote index time  
**And** results flagged as stale when local file is newer than remote index  
**And** staleness threshold configurable (default: any local change newer than index)  
**And** clear visual indicators distinguish fresh from stale results  

### Given: Staleness Metadata Integration
**When** I examine individual query results  
**Then** results include both local file timestamp and remote index timestamp  
**And** staleness calculation performed transparently  
**And** metadata includes time delta between local and remote versions  
**And** results sorted with staleness consideration (fresh results prioritized)  

### Given: Performance Optimization
**When** I execute queries with many results  
**Then** timestamp comparison performs efficiently without blocking queries  
**And** local file stat() operations batched appropriately  
**And** staleness detection adds minimal overhead to query time  
**And** caching prevents redundant file system operations  

## 🏗️ **Technical Implementation**

```python
class StalenessDetector:
    def __init__(self, staleness_threshold_seconds: int = 0):
        self.staleness_threshold = staleness_threshold_seconds
    
    def apply_staleness_detection(
        self, 
        results: List[QueryResultItem], 
        project_root: Path
    ) -> List[EnhancedQueryResultItem]:
        enhanced_results = []
        
        for result in results:
            local_file_path = project_root / result.file_path
            
            # Get local file modification time
            local_mtime = self._get_local_file_mtime(local_file_path)
            
            # Extract remote index timestamp
            remote_timestamp = result.indexed_timestamp
            
            # Calculate staleness
            is_stale = self._is_result_stale(local_mtime, remote_timestamp)
            staleness_delta = self._calculate_staleness_delta(local_mtime, remote_timestamp)
            
            enhanced_result = EnhancedQueryResultItem(
                **result.dict(),
                local_file_mtime=local_mtime,
                is_stale=is_stale,
                staleness_delta_seconds=staleness_delta,
                staleness_indicator=self._format_staleness_indicator(is_stale, staleness_delta)
            )
            
            enhanced_results.append(enhanced_result)
        
        # Sort results with staleness consideration
        return self._sort_with_staleness_priority(enhanced_results)
    
    def _is_result_stale(self, local_mtime: Optional[float], remote_timestamp: Optional[float]) -> bool:
        if local_mtime is None or remote_timestamp is None:
            return False  # Cannot determine staleness
        
        return local_mtime > (remote_timestamp + self.staleness_threshold)
    
    def _format_staleness_indicator(self, is_stale: bool, delta_seconds: Optional[float]) -> str:
        if is_stale and delta_seconds:
            if delta_seconds < 3600:  # Less than 1 hour
                return f"🟡 Local file {int(delta_seconds // 60)}m newer"
            elif delta_seconds < 86400:  # Less than 1 day
                return f"🟠 Local file {int(delta_seconds // 3600)}h newer"
            else:  # More than 1 day
                return f"🔴 Local file {int(delta_seconds // 86400)}d newer"
        return "🟢 Fresh"
```

## 📊 **Definition of Done**

- ✅ File-level timestamp comparison between local and remote versions
- ✅ Staleness indicators integrated into query result presentation
- ✅ Performance optimization for batch timestamp operations
- ✅ Configurable staleness threshold and detection criteria
- ✅ Clear visual indicators for different staleness levels
- ✅ Integration with existing query result processing
- ✅ Comprehensive testing with various timestamp scenarios
- ✅ User experience validation with staleness feedback clarity
- ✅ Error handling for missing timestamps or file access issues
- ✅ Documentation explains staleness detection and interpretation