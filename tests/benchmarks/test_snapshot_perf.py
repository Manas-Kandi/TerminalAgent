"""Snapshot performance benchmarks.

Acceptance criteria:
- Snapshot a 5 MB DOM (Gmail inbox simulation) in <100 ms
- RAM delta <1 MB per snapshot
- If either fails, switch to copy-on-write (no negotiation)

Run with: pytest tests/benchmarks/test_snapshot_perf.py -v -s
"""

import gc
import sys
import time
import tracemalloc
from typing import Any
import pytest

from kernel.objects import ObjectManager, ObjectType, ManagedObject


# ============================================================================
# Thresholds (HARD LIMITS - no negotiation)
# ============================================================================

MAX_SNAPSHOT_TIME_MS = 100  # Must snapshot in <100ms
MAX_SNAPSHOT_RAM_BYTES = 1 * 1024 * 1024  # Must use <1MB RAM delta
TARGET_DOM_SIZE_BYTES = 5 * 1024 * 1024  # 5MB DOM simulation


# ============================================================================
# DOM Simulation Helpers
# ============================================================================

def generate_gmail_inbox_dom(target_size_bytes: int = TARGET_DOM_SIZE_BYTES) -> dict:
    """Generate a simulated Gmail inbox DOM structure.
    
    Gmail inbox characteristics:
    - ~50 email rows visible
    - Each row has nested divs for sender, subject, snippet, date
    - Rich text content, labels, avatars
    - Total DOM ~5MB for loaded inbox
    """
    emails = []
    email_template = {
        "id": "",
        "sender": {
            "name": "John Smith" * 5,  # Pad for realism
            "email": "john.smith@example.com",
            "avatar_url": "https://example.com/avatars/abc123.jpg",
        },
        "subject": "Re: " + "Important meeting about quarterly review " * 3,
        "snippet": "Hi team, I wanted to follow up on our discussion from yesterday regarding the project timeline and deliverables. As we discussed..." * 5,
        "timestamp": 1234567890123,
        "labels": ["inbox", "important", "work"],
        "is_read": False,
        "has_attachments": True,
        "attachments": [
            {"name": "document.pdf", "size": 1234567, "type": "application/pdf"},
            {"name": "spreadsheet.xlsx", "size": 234567, "type": "application/vnd.ms-excel"},
        ],
        "thread_count": 5,
        "starred": False,
        "dom_nodes": {
            "row": {"class": "zA zE", "role": "row", "tabindex": "-1"},
            "checkbox": {"type": "checkbox", "aria-label": "Select"},
            "star": {"class": "T-KT", "aria-label": "Not starred"},
            "sender_col": {"class": "yX xY", "children": []},
            "subject_col": {"class": "y6", "children": []},
            "snippet_col": {"class": "y2", "children": []},
            "date_col": {"class": "xW", "children": []},
        },
    }
    
    # Build up to target size
    current_size = 0
    email_num = 0
    
    while current_size < target_size_bytes:
        email = dict(email_template)
        email["id"] = f"msg-{email_num:06d}"
        email["sender"]["name"] = f"User {email_num} " + "A" * 50
        email["subject"] = f"Email #{email_num}: " + "X" * 100
        email["snippet"] = f"Content for email {email_num}: " + "Y" * 500
        
        emails.append(email)
        email_num += 1
        
        # Estimate size (rough)
        current_size = len(str(emails))
        
        if email_num > 10000:  # Safety limit
            break
    
    return {
        "type": "gmail_inbox",
        "account": "user@gmail.com",
        "unread_count": email_num // 2,
        "total_count": email_num,
        "emails": emails,
        "ui_state": {
            "selected": [],
            "scroll_position": 0,
            "view_mode": "comfortable",
            "density": "default",
        },
    }


def get_object_size(obj: Any) -> int:
    """Get approximate size of object in bytes."""
    return len(str(obj).encode('utf-8'))


# ============================================================================
# Benchmark Tests
# ============================================================================

class TestSnapshotPerformance:
    """Benchmark tests for snapshot performance."""
    
    def test_snapshot_time_under_threshold(self):
        """Snapshot must complete in <100ms for 5MB DOM."""
        objects = ObjectManager()
        
        # Create tab with large DOM data
        dom_data = generate_gmail_inbox_dom(TARGET_DOM_SIZE_BYTES)
        dom_size = get_object_size(dom_data)
        
        tab = objects.create(ObjectType.TAB, url="https://mail.google.com/")
        tab._data["dom"] = dom_data
        tab._data["content_size"] = dom_size
        
        print(f"\nDOM size: {dom_size / 1024 / 1024:.2f} MB")
        print(f"Email count: {len(dom_data['emails'])}")
        
        # Warm up
        _ = objects.snapshot_all()
        
        # Measure snapshot time (average of 5 runs)
        times = []
        for _ in range(5):
            gc.collect()
            
            start = time.perf_counter()
            snapshot = objects.snapshot_all()
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
        
        avg_time_ms = sum(times) / len(times)
        min_time_ms = min(times)
        max_time_ms = max(times)
        
        print(f"Snapshot times: min={min_time_ms:.2f}ms, avg={avg_time_ms:.2f}ms, max={max_time_ms:.2f}ms")
        print(f"Threshold: {MAX_SNAPSHOT_TIME_MS}ms")
        
        assert avg_time_ms < MAX_SNAPSHOT_TIME_MS, (
            f"SNAPSHOT TOO SLOW: {avg_time_ms:.2f}ms > {MAX_SNAPSHOT_TIME_MS}ms threshold. "
            f"Must implement copy-on-write."
        )
    
    def test_snapshot_ram_under_threshold(self):
        """Snapshot must use <1MB RAM delta for 5MB DOM."""
        objects = ObjectManager()
        
        # Create tab with large DOM data
        dom_data = generate_gmail_inbox_dom(TARGET_DOM_SIZE_BYTES)
        
        tab = objects.create(ObjectType.TAB, url="https://mail.google.com/")
        tab._data["dom"] = dom_data
        
        # Force GC and start memory tracking
        gc.collect()
        tracemalloc.start()
        
        # Take snapshot
        snapshot_start = tracemalloc.take_snapshot()
        snapshot = objects.snapshot_all()
        snapshot_end = tracemalloc.take_snapshot()
        
        tracemalloc.stop()
        
        # Calculate memory delta
        stats = snapshot_end.compare_to(snapshot_start, 'lineno')
        total_delta = sum(stat.size_diff for stat in stats if stat.size_diff > 0)
        
        print(f"\nRAM delta: {total_delta / 1024 / 1024:.2f} MB")
        print(f"Threshold: {MAX_SNAPSHOT_RAM_BYTES / 1024 / 1024:.2f} MB")
        
        # Top allocations
        print("\nTop memory allocations:")
        for stat in stats[:5]:
            print(f"  {stat}")
        
        assert total_delta < MAX_SNAPSHOT_RAM_BYTES, (
            f"SNAPSHOT USES TOO MUCH RAM: {total_delta / 1024 / 1024:.2f}MB > "
            f"{MAX_SNAPSHOT_RAM_BYTES / 1024 / 1024:.2f}MB threshold. "
            f"Must implement copy-on-write."
        )
    
    def test_multi_tab_snapshot_scales(self):
        """Snapshot of 10 tabs must still meet thresholds."""
        objects = ObjectManager()
        
        # Create 10 tabs, each with ~500KB DOM (total ~5MB)
        per_tab_size = TARGET_DOM_SIZE_BYTES // 10
        
        for i in range(10):
            dom_data = generate_gmail_inbox_dom(per_tab_size)
            tab = objects.create(ObjectType.TAB, url=f"https://site{i}.com/")
            tab._data["dom"] = dom_data
        
        # Measure snapshot
        gc.collect()
        
        start = time.perf_counter()
        snapshot = objects.snapshot_all()
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n10-tab snapshot time: {elapsed_ms:.2f}ms")
        print(f"Threshold: {MAX_SNAPSHOT_TIME_MS}ms")
        
        assert elapsed_ms < MAX_SNAPSHOT_TIME_MS, (
            f"MULTI-TAB SNAPSHOT TOO SLOW: {elapsed_ms:.2f}ms > {MAX_SNAPSHOT_TIME_MS}ms"
        )
    
    def test_restore_time_under_threshold(self):
        """Restore must also be fast."""
        objects = ObjectManager()
        
        dom_data = generate_gmail_inbox_dom(TARGET_DOM_SIZE_BYTES)
        tab = objects.create(ObjectType.TAB, url="https://mail.google.com/")
        tab._data["dom"] = dom_data
        
        # Take snapshot
        snapshot = objects.snapshot_all()
        
        # Modify state
        tab._data["dom"]["emails"] = []
        
        # Measure restore time
        gc.collect()
        times = []
        
        for _ in range(5):
            # Re-modify before each restore
            tab._data["dom"]["emails"] = []
            
            start = time.perf_counter()
            objects.restore_snapshot(snapshot)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
        
        avg_time_ms = sum(times) / len(times)
        
        print(f"\nRestore times: avg={avg_time_ms:.2f}ms")
        print(f"Threshold: {MAX_SNAPSHOT_TIME_MS}ms")
        
        assert avg_time_ms < MAX_SNAPSHOT_TIME_MS, (
            f"RESTORE TOO SLOW: {avg_time_ms:.2f}ms > {MAX_SNAPSHOT_TIME_MS}ms"
        )


class TestCopyOnWriteFallback:
    """Tests for copy-on-write implementation (if needed)."""
    
    def test_cow_reduces_memory(self):
        """Copy-on-write should share unchanged subtrees."""
        # This test documents the expected behavior if we need to implement COW
        objects = ObjectManager()
        
        # Create two identical tabs
        dom_data = generate_gmail_inbox_dom(TARGET_DOM_SIZE_BYTES // 2)
        
        tab1 = objects.create(ObjectType.TAB, url="https://site1.com/")
        tab1._data["dom"] = dom_data
        
        tab2 = objects.create(ObjectType.TAB, url="https://site2.com/")
        tab2._data["dom"] = dom_data  # Same reference initially
        
        # With COW, snapshot should detect shared data
        # For now, we just verify the test runs
        snapshot = objects.snapshot_all()
        
        # This test will be expanded if we implement COW
        assert snapshot is not None


# ============================================================================
# Performance regression guard
# ============================================================================

@pytest.mark.benchmark
class TestPerformanceRegression:
    """Guards against performance regressions."""
    
    def test_snapshot_performance_baseline(self):
        """Baseline performance test - fails CI if regression."""
        objects = ObjectManager()
        
        # Standard 1MB DOM
        dom_data = generate_gmail_inbox_dom(1 * 1024 * 1024)
        tab = objects.create(ObjectType.TAB, url="https://example.com/")
        tab._data["dom"] = dom_data
        
        # Must complete in <20ms for 1MB
        start = time.perf_counter()
        snapshot = objects.snapshot_all()
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        # 1MB should be ~5x faster than 5MB threshold
        threshold_1mb = MAX_SNAPSHOT_TIME_MS / 5
        
        print(f"\n1MB baseline: {elapsed_ms:.2f}ms (threshold: {threshold_1mb:.2f}ms)")
        
        assert elapsed_ms < threshold_1mb, (
            f"Performance regression: 1MB snapshot took {elapsed_ms:.2f}ms"
        )
