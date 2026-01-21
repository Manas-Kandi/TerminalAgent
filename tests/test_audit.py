"""Tests for the Audit Log."""

import json
import tempfile
from pathlib import Path
import pytest
from kernel.audit import AuditLog, Provenance


class TestAuditLog:
    """Tests for audit log operations."""
    
    def test_log_creates_entry(self):
        """log() creates an audit entry."""
        audit = AuditLog()
        
        entry = audit.log(
            op="tab.navigate",
            principal="agent:1",
            object="tab:42",
            args={"url": "https://example.com"},
            result="success",
        )
        
        assert entry.op == "tab.navigate"
        assert entry.principal == "agent:1"
        assert entry.object == "tab:42"
        assert entry.args["url"] == "https://example.com"
        assert entry.result == "success"
    
    def test_log_assigns_unique_id(self):
        """Each log entry gets a unique ID."""
        audit = AuditLog()
        
        entry1 = audit.log(op="op1", principal="p", object="o")
        entry2 = audit.log(op="op2", principal="p", object="o")
        
        assert entry1.id != entry2.id
    
    def test_log_timestamps(self):
        """Entries have timestamps."""
        audit = AuditLog()
        
        entry = audit.log(op="test", principal="p", object="o")
        
        assert entry.timestamp > 0
    
    def test_provenance_tracking(self):
        """Entries track provenance (origin of action)."""
        audit = AuditLog()
        
        human_entry = audit.log(
            op="click", principal="user:alice", object="button:1",
            provenance=Provenance.HUMAN
        )
        agent_entry = audit.log(
            op="navigate", principal="agent:1", object="tab:1",
            provenance=Provenance.AGENT
        )
        
        assert human_entry.provenance == Provenance.HUMAN
        assert agent_entry.provenance == Provenance.AGENT
    
    def test_redacts_sensitive_fields(self):
        """Sensitive fields are redacted in args."""
        audit = AuditLog()
        
        entry = audit.log(
            op="form.fill",
            principal="agent:1",
            object="form:1",
            args={
                "email": "test@example.com",
                "password": "supersecret",
                "api_key": "sk-12345",
                "token": "jwt-token",
            },
        )
        
        assert entry.args["email"] == "test@example.com"
        assert entry.args["password"] == "[REDACTED]"
        assert entry.args["api_key"] == "[REDACTED]"
        assert entry.args["token"] == "[REDACTED]"
    
    def test_redacts_nested_sensitive_fields(self):
        """Nested sensitive fields are also redacted."""
        audit = AuditLog()
        
        entry = audit.log(
            op="test",
            principal="p",
            object="o",
            args={"credentials": {"password": "secret", "username": "alice"}},
        )
        
        assert entry.args["credentials"]["password"] == "[REDACTED]"
        assert entry.args["credentials"]["username"] == "alice"
    
    def test_query_all(self):
        """query() returns all entries when no filters."""
        audit = AuditLog()
        audit.log(op="op1", principal="p1", object="o1")
        audit.log(op="op2", principal="p2", object="o2")
        
        entries = audit.query()
        
        assert len(entries) == 2
    
    def test_query_by_principal(self):
        """query() filters by principal."""
        audit = AuditLog()
        audit.log(op="op1", principal="agent:1", object="o1")
        audit.log(op="op2", principal="agent:2", object="o2")
        
        entries = audit.query(principal="agent:1")
        
        assert len(entries) == 1
        assert entries[0].principal == "agent:1"
    
    def test_query_by_operation(self):
        """query() filters by operation."""
        audit = AuditLog()
        audit.log(op="tab.navigate", principal="p", object="o")
        audit.log(op="tab.close", principal="p", object="o")
        audit.log(op="form.fill", principal="p", object="o")
        
        entries = audit.query(op="tab.navigate")
        
        assert len(entries) == 1
        assert entries[0].op == "tab.navigate"
    
    def test_query_by_operation_prefix(self):
        """query() supports operation prefix match with *."""
        audit = AuditLog()
        audit.log(op="tab.navigate", principal="p", object="o")
        audit.log(op="tab.close", principal="p", object="o")
        audit.log(op="form.fill", principal="p", object="o")
        
        entries = audit.query(op="tab.*")
        
        assert len(entries) == 2
        assert all(e.op.startswith("tab.") for e in entries)
    
    def test_query_by_object(self):
        """query() filters by object ID."""
        audit = AuditLog()
        audit.log(op="op", principal="p", object="tab:1")
        audit.log(op="op", principal="p", object="tab:2")
        
        entries = audit.query(object_id="tab:1")
        
        assert len(entries) == 1
        assert entries[0].object == "tab:1"
    
    def test_query_by_time_range(self):
        """query() filters by time range."""
        import time
        audit = AuditLog()
        
        entry1 = audit.log(op="old", principal="p", object="o")
        time.sleep(0.01)
        midpoint = time.time()
        time.sleep(0.01)
        entry2 = audit.log(op="new", principal="p", object="o")
        
        entries = audit.query(since=midpoint)
        
        assert len(entries) == 1
        assert entries[0].op == "new"
    
    def test_query_respects_limit(self):
        """query() respects limit parameter."""
        audit = AuditLog()
        for i in range(10):
            audit.log(op=f"op{i}", principal="p", object="o")
        
        entries = audit.query(limit=5)
        
        assert len(entries) == 5
    
    def test_transaction_context(self):
        """Entries include transaction context when set."""
        audit = AuditLog()
        
        audit.set_transaction_context("tx:1", "cp:1")
        entry = audit.log(op="test", principal="p", object="o")
        
        assert entry.tx_id == "tx:1"
        assert entry.checkpoint_id == "cp:1"
    
    def test_clear_transaction_context(self):
        """clear_transaction_context removes context."""
        audit = AuditLog()
        
        audit.set_transaction_context("tx:1")
        audit.clear_transaction_context()
        entry = audit.log(op="test", principal="p", object="o")
        
        assert entry.tx_id is None
    
    def test_query_by_transaction(self):
        """query() filters by transaction ID."""
        audit = AuditLog()
        
        audit.set_transaction_context("tx:1")
        audit.log(op="op1", principal="p", object="o")
        audit.log(op="op2", principal="p", object="o")
        
        audit.set_transaction_context("tx:2")
        audit.log(op="op3", principal="p", object="o")
        
        entries = audit.query(tx_id="tx:1")
        
        assert len(entries) == 2
    
    def test_get_transaction_log(self):
        """get_transaction_log returns all entries for a tx."""
        audit = AuditLog()
        
        audit.set_transaction_context("tx:1")
        audit.log(op="op1", principal="p", object="o")
        audit.log(op="op2", principal="p", object="o")
        
        entries = audit.get_transaction_log("tx:1")
        
        assert len(entries) == 2
    
    def test_persistence_to_file(self):
        """Audit log persists to SQLite file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            # Write
            audit1 = AuditLog(db_path=db_path)
            audit1.log(op="test", principal="p", object="o", args={"url": "https://example.com"})
            
            # Read with new instance
            audit2 = AuditLog(db_path=db_path)
            entries = audit2.query()
            
            assert len(entries) == 1
            assert entries[0].op == "test"
            assert entries[0].args["url"] == "https://example.com"
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    def test_export_json(self):
        """export_json writes entries to JSON file."""
        audit = AuditLog()
        audit.log(op="op1", principal="p", object="o")
        audit.log(op="op2", principal="p", object="o")
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            filepath = f.name
        
        try:
            count = audit.export_json(filepath)
            
            assert count == 2
            with open(filepath) as f:
                data = json.load(f)
            assert len(data) == 2
            assert data[0]["op"] == "op1"
        finally:
            Path(filepath).unlink(missing_ok=True)
    
    def test_count(self):
        """count() returns number of matching entries."""
        audit = AuditLog()
        audit.log(op="tab.x", principal="p", object="o")
        audit.log(op="tab.y", principal="p", object="o")
        audit.log(op="form.x", principal="p", object="o")
        
        assert audit.count() == 3
        assert audit.count(op="tab.*") == 2
