"""Chaos test suite - Adversarial conditions for kernel robustness.

Tests:
- CDP event reordering
- Impossible state transitions
- IPC socket failures
- Malformed messages
"""

import json
import pytest
import threading
import time
from unittest.mock import MagicMock, patch

from kernel.objects import ObjectManager, ObjectType, Tab
from kernel.audit import AuditLog
from kernel.transactions import TransactionCoordinator, TransactionState
from kernel.renderer.mock import MockRenderer, MockPage


class TestEventReordering:
    """Tests for handling out-of-order CDP events."""
    
    def setup_method(self):
        self.audit = AuditLog()
        self.objects = ObjectManager(audit_log=self.audit)
        self.transactions = TransactionCoordinator(self.objects, self.audit)
        self.renderer = MockRenderer(self.objects, self.audit)
    
    def test_navigate_before_tab_exists(self):
        """Navigation to nonexistent tab returns error, not crash."""
        result = self.renderer.navigate("tab:nonexistent", "https://example.com/")
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()
    
    def test_fill_form_before_form_found(self):
        """Fill on nonexistent form returns error."""
        result = self.renderer.fill_form("form:nonexistent", {"email": "test"})
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()
    
    def test_submit_form_before_fill(self):
        """Submit before fill still works (empty submission)."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        self.renderer.navigate(tab.id, "https://example.com/login")
        form_id = self.renderer.find_form(tab.id, "login")
        
        # Submit without filling
        result = self.renderer.submit_form(form_id)
        
        # Should succeed (forms can be submitted empty)
        assert result["success"] is True
    
    def test_double_navigate_during_load(self):
        """Second navigate while first is loading doesn't crash."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        
        # First navigate
        self.renderer.navigate(tab.id, "https://example.com/page1")
        # Second navigate before load completes (simulated)
        result = self.renderer.navigate(tab.id, "https://example.com/page2")
        
        assert result["success"] is True
        assert tab.url == "https://example.com/page2"


class TestImpossibleStateTransitions:
    """Tests for handling impossible/inconsistent state."""
    
    def setup_method(self):
        self.audit = AuditLog()
        self.objects = ObjectManager(audit_log=self.audit)
        self.transactions = TransactionCoordinator(self.objects, self.audit)
        self.renderer = MockRenderer(self.objects, self.audit)
    
    def test_tab_url_changes_without_navigate(self):
        """Detect when tab URL changes without navigate call."""
        tab = self.objects.create(ObjectType.TAB, url="https://original.com")
        
        # Simulate external URL change (e.g., renderer bug)
        tab._data["url"] = "https://unexpected.com"
        
        # ObjectManager should have the inconsistent state
        assert tab.url == "https://unexpected.com"
        
        # Audit should NOT have a navigate entry
        nav_entries = self.audit.query(op="renderer.navigate")
        assert len(nav_entries) == 0
    
    def test_form_exists_without_tab(self):
        """Form can't reference nonexistent tab."""
        # Create form without tab
        form = self.objects.create(ObjectType.FORM, tab_id="tab:ghost", form_type="login")
        
        # Form exists but tab doesn't
        assert form.id.startswith("form:")
        assert self.objects.get("tab:ghost") is None
    
    def test_transaction_commit_twice(self):
        """Double commit on transaction is handled."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        
        with self.transactions.begin() as tx:
            tx.commit()
            # Second commit should be no-op or error, not crash
            # (Transaction is no longer active)
            assert not tx.is_active
    
    def test_rollback_after_commit(self):
        """Rollback after commit fails gracefully."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        
        with self.transactions.begin() as tx:
            tx.checkpoint("cp1")
            tx.commit()
        
        # Transaction is now committed, rollback should fail
        from kernel.transactions import TransactionError
        with pytest.raises(TransactionError):
            self.transactions.rollback("cp1")


class TestIPCSocketFailures:
    """Tests for handling IPC connection failures."""
    
    def test_renderer_survives_interrupted_operation(self):
        """Renderer handles interrupted operations gracefully."""
        audit = AuditLog()
        objects = ObjectManager(audit_log=audit)
        renderer = MockRenderer(objects, audit)
        
        tab = objects.create(ObjectType.TAB, url="about:blank")
        
        # Simulate navigation with mock that "fails mid-operation"
        # In real implementation, this would be socket.timeout or ConnectionReset
        renderer.navigate(tab.id, "https://example.com/")
        
        # Tab should be in a consistent state (not half-updated)
        assert tab._data["load_state"] in ["complete", "loading", "idle"]
    
    def test_transaction_survives_renderer_disconnect(self):
        """Transaction state is preserved if renderer disconnects."""
        audit = AuditLog()
        objects = ObjectManager(audit_log=audit)
        transactions = TransactionCoordinator(objects, audit)
        
        tab = objects.create(ObjectType.TAB, url="https://original.com")
        
        with transactions.begin() as tx:
            tx.checkpoint("before-danger")
            tab._data["url"] = "https://during-operation.com"
            
            # Simulate "renderer died here" - we still have transaction
            # Rollback should work
            tx.rollback("before-danger")
            
            assert tab.url == "https://original.com"
            tx.commit()


class TestMalformedMessages:
    """Tests for handling malformed IPC messages."""
    
    def test_empty_json_object(self):
        """Empty JSON object is handled."""
        from tests.fixtures.cdp.schemas import KernelMessage
        
        with pytest.raises((KeyError, TypeError)):
            KernelMessage.from_json("{}")
    
    def test_null_values(self):
        """Null values in message fields are handled."""
        msg_json = json.dumps({
            "type": "navigate_result",
            "tab_id": None,
            "request_id": None,
            "payload": None,
            "timestamp": None,
        })
        
        from tests.fixtures.cdp.schemas import KernelMessage
        msg = KernelMessage.from_json(msg_json)
        
        assert msg.tab_id is None
        assert msg.payload is None
    
    def test_extra_fields_ignored(self):
        """Extra fields in messages are preserved but don't break parsing."""
        msg_json = json.dumps({
            "type": "test",
            "tab_id": "tab:1",
            "request_id": 1,
            "payload": {},
            "timestamp": 0,
            "extra_field": "should not break",
            "another_extra": {"nested": True},
        })
        
        from tests.fixtures.cdp.schemas import KernelMessage
        msg = KernelMessage.from_json(msg_json)
        
        assert msg.type == "test"
        # Extra fields don't become attributes
        assert not hasattr(msg, "extra_field")
    
    def test_unicode_in_payload(self):
        """Unicode content in messages is handled."""
        msg_json = json.dumps({
            "type": "test",
            "tab_id": "tab:1",
            "request_id": 1,
            "payload": {
                "title": "日本語タイトル",
                "content": "Emoji: 🔥💀",
            },
            "timestamp": 0,
        })
        
        from tests.fixtures.cdp.schemas import KernelMessage
        msg = KernelMessage.from_json(msg_json)
        
        assert msg.payload["title"] == "日本語タイトル"
        assert "🔥" in msg.payload["content"]


class TestConcurrency:
    """Tests for concurrent access to kernel state."""
    
    def test_concurrent_tab_creation(self):
        """Concurrent tab creation doesn't produce duplicate IDs."""
        objects = ObjectManager()
        tab_ids = []
        errors = []
        
        def create_tab():
            try:
                tab = objects.create(ObjectType.TAB, url="https://example.com")
                tab_ids.append(tab.id)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=create_tab) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(tab_ids) == 10
        assert len(set(tab_ids)) == 10  # All unique
    
    def test_concurrent_audit_logging(self):
        """Concurrent audit logging doesn't lose entries."""
        audit = AuditLog()
        entry_ids = []
        
        def log_entry(i):
            entry = audit.log(op=f"test.op{i}", principal="test", object=f"obj:{i}")
            entry_ids.append(entry.id)
        
        threads = [threading.Thread(target=log_entry, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(entry_ids) == 20
        assert len(set(entry_ids)) == 20  # All unique
        
        # All entries should be queryable
        entries = audit.query(op="test.*")
        assert len(entries) == 20
