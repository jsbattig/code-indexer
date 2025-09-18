# User Story: Stale Detection for Both Modes

## 📋 **User Story**

As a **CIDX user**, I want **consistent staleness detection in both local and remote modes**, so that **I have the same awareness of result relevance regardless of which mode I'm using**.

## 🎯 **Business Value**

Provides consistent user experience and result interpretation across both operational modes. Users develop single mental model for understanding result freshness.

## 📝 **Acceptance Criteria**

### Given: Universal Staleness Application
**When** I query repositories in either local or remote mode  
**Then** staleness detection applies identical logic in both modes  
**And** same staleness thresholds and indicators used consistently  
**And** visual presentation of staleness identical across modes  
**And** result sorting considers staleness the same way in both modes  

### Given: Mode-Agnostic Implementation
**When** I examine staleness detection code  
**Then** same StalenessDetector class used for both local and remote results  
**And** mode-specific adaptations handled transparently  
**And** configuration settings apply equally to both modes  
**And** testing validates identical behavior across modes  

### Given: Consistent User Experience
**When** I switch between local and remote modes  
**Then** staleness indicators look and behave identically  
**And** result interpretation remains the same  
**And** help documentation explains staleness consistently  
**And** troubleshooting guidance applies to both modes  

## 🏗️ **Technical Implementation**

```python
class UniversalStalenessDetector:
    \"\"\"Staleness detection that works identically for local and remote modes.\"\"\"
    
    def apply_staleness_detection(
        self, 
        results: List[QueryResultItem], 
        project_root: Path,
        mode: Literal[\"local\", \"remote\"]
    ) -> List[EnhancedQueryResultItem]:
        \"\"\"Apply identical staleness logic regardless of query mode.\"\"\"
        enhanced_results = []
        
        for result in results:
            # Get local file timestamp (same for both modes)
            local_mtime_utc = self._get_local_file_mtime_utc(project_root / result.file_path)
            
            # Get index timestamp (source differs by mode but comparison is identical)
            index_timestamp_utc = self._get_index_timestamp_utc(result, mode)
            
            # Apply identical staleness calculation
            staleness_info = self._calculate_staleness(local_mtime_utc, index_timestamp_utc)
            
            enhanced_result = EnhancedQueryResultItem(
                **result.dict(),
                **staleness_info,
                mode=mode  # For debugging/logging only
            )
            
            enhanced_results.append(enhanced_result)
        
        # Apply identical sorting logic
        return self._sort_with_staleness_priority(enhanced_results)
    
    def _get_index_timestamp_utc(self, result: QueryResultItem, mode: str) -> Optional[float]:
        \"\"\"Get index timestamp normalized to UTC, mode-agnostic.\"\"\"
        if mode == \"remote\":
            # Remote mode: use indexed_timestamp from API response
            return result.indexed_timestamp
        else:
            # Local mode: use file_last_modified from local index
            return result.file_last_modified
    
    def _calculate_staleness(
        self, 
        local_mtime_utc: Optional[float], 
        index_timestamp_utc: Optional[float]
    ) -> Dict[str, Any]:
        \"\"\"Identical staleness calculation for both modes.\"\"\"
        if local_mtime_utc is None or index_timestamp_utc is None:
            return {
                'local_file_mtime': local_mtime_utc,
                'index_timestamp': index_timestamp_utc,
                'is_stale': False,
                'staleness_delta_seconds': None,
                'staleness_indicator': '❓ Cannot determine'
            }
        
        delta_seconds = local_mtime_utc - index_timestamp_utc
        is_stale = delta_seconds > self.staleness_threshold
        
        return {
            'local_file_mtime': local_mtime_utc,
            'index_timestamp': index_timestamp_utc,
            'is_stale': is_stale,
            'staleness_delta_seconds': delta_seconds,
            'staleness_indicator': self._format_staleness_indicator(is_stale, delta_seconds)
        }
```

## 📊 **Definition of Done**

- ✅ Universal staleness detector works identically in both modes
- ✅ Same staleness thresholds and calculation logic applied consistently
- ✅ Identical visual indicators and result presentation
- ✅ Mode-specific timestamp source handling with common comparison logic
- ✅ Comprehensive testing validates identical behavior across modes
- ✅ Configuration applies equally to local and remote staleness detection
- ✅ User experience consistency validation
- ✅ Documentation explains universal staleness approach
- ✅ Performance parity between modes for staleness operations
- ✅ Integration testing with both local and remote query workflows