# User Story: Timezone Independent Comparison

## 📋 **User Story**

As a **CIDX user working with global teams**, I want **accurate staleness detection regardless of timezone differences**, so that **staleness indicators are reliable across different server and client timezone configurations**.

## 🎯 **Business Value**

Ensures accurate staleness detection for distributed teams across multiple timezones. Prevents false staleness indicators due to timezone mismatches.

## 📝 **Acceptance Criteria**

### Given: UTC Timestamp Normalization
**When** I compare local and remote file timestamps  
**Then** all timestamps are normalized to UTC before comparison  
**And** local file times converted from system timezone to UTC  
**And** remote timestamps stored and transmitted in UTC  
**And** timezone conversion handles daylight saving transitions correctly  

### Given: Cross-Timezone Accuracy
**When** I work with remote servers in different timezones  
**Then** staleness detection accuracy is unaffected by timezone differences  
**And** same file modifications produce consistent staleness results  
**And** team members in different timezones see identical staleness indicators  
**And** server timezone changes don't affect staleness calculation  

## 🏗️ **Technical Implementation**

```python
from datetime import datetime, timezone
import time

class TimezoneAwareStalenessDetector:
    @staticmethod
    def normalize_to_utc(timestamp: float, source_timezone: Optional[str] = None) -> float:
        \"\"\"Convert timestamp to UTC for consistent comparison.\"\"\"
        if source_timezone:
            # Handle explicit timezone conversion
            local_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            return local_dt.timestamp()
        else:
            # Assume timestamp is already in local timezone, convert to UTC
            local_dt = datetime.fromtimestamp(timestamp)
            utc_dt = local_dt.replace(tzinfo=timezone.utc)
            return utc_dt.timestamp()
    
    def get_local_file_mtime_utc(self, file_path: Path) -> Optional[float]:
        \"\"\"Get local file modification time normalized to UTC.\"\"\"
        try:
            local_mtime = file_path.stat().st_mtime
            # Convert local system time to UTC
            return self.normalize_to_utc(local_mtime)
        except (OSError, IOError):
            return None
    
    def compare_timestamps_utc(
        self, 
        local_mtime_utc: float, 
        remote_timestamp_utc: float
    ) -> Dict[str, Any]:
        \"\"\"Compare UTC-normalized timestamps for staleness.\"\"\"
        delta_seconds = local_mtime_utc - remote_timestamp_utc
        
        return {
            'is_stale': delta_seconds > self.staleness_threshold,
            'delta_seconds': delta_seconds,
            'local_newer_by': max(0, delta_seconds),
            'comparison_timezone': 'UTC'
        }
```

## 📊 **Definition of Done**

- ✅ UTC normalization for all timestamp comparisons
- ✅ Local file timestamp conversion to UTC
- ✅ Server timestamp storage and transmission in UTC
- ✅ Cross-timezone accuracy validation
- ✅ Daylight saving time transition handling
- ✅ Comprehensive testing across multiple timezones
- ✅ Performance validation of timezone conversion operations
- ✅ Integration with existing staleness detection
- ✅ Documentation explains timezone handling approach
- ✅ Error handling for timezone conversion failures