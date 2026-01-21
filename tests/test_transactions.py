"""Tests for the Transaction Coordinator."""

import pytest
from kernel.objects import ObjectManager, ObjectType
from kernel.audit import AuditLog
from kernel.transactions import (
    TransactionCoordinator,
    TransactionState,
    TransactionError,
    TransactionNotActive,
    CheckpointNotFound,
)


class TestTransactionCoordinator:
    """Tests for transaction lifecycle and checkpoints."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.audit = AuditLog()
        self.objects = ObjectManager(audit_log=self.audit)
        self.tx_coord = TransactionCoordinator(self.objects, self.audit)
    
    def test_begin_creates_transaction(self):
        """begin() creates an active transaction."""
        with self.tx_coord.begin() as tx:
            assert tx.id.startswith("tx:")
            assert tx.is_active
    
    def test_commit_finalizes_transaction(self):
        """commit() marks transaction as committed."""
        with self.tx_coord.begin() as tx:
            tx_id = tx.id
            tx.commit()
        
        stored_tx = self.tx_coord.get_transaction(tx_id)
        assert stored_tx.state == TransactionState.COMMITTED
    
    def test_abort_reverts_to_initial(self):
        """abort() restores initial state."""
        tab = self.objects.create(ObjectType.TAB, url="https://original.com")
        
        with self.tx_coord.begin() as tx:
            tab.navigate("https://changed.com")
            assert tab.url == "https://changed.com"
            tx.abort()
        
        assert tab.url == "https://original.com"
    
    def test_context_manager_aborts_on_no_commit(self):
        """Transaction without explicit commit is aborted."""
        tab = self.objects.create(ObjectType.TAB, url="https://original.com")
        
        with self.tx_coord.begin() as tx:
            tab.navigate("https://changed.com")
            # No commit
        
        assert tab.url == "https://original.com"
    
    def test_context_manager_aborts_on_exception(self):
        """Transaction aborts on exception."""
        tab = self.objects.create(ObjectType.TAB, url="https://original.com")
        
        with pytest.raises(ValueError):
            with self.tx_coord.begin() as tx:
                tab.navigate("https://changed.com")
                raise ValueError("test error")
        
        assert tab.url == "https://original.com"
    
    def test_checkpoint_saves_state(self):
        """checkpoint() saves current state."""
        tab = self.objects.create(ObjectType.TAB, url="https://original.com")
        
        with self.tx_coord.begin() as tx:
            tx.checkpoint("before-nav")
            tab.navigate("https://changed.com")
            
            checkpoints = self.tx_coord.list_checkpoints()
            assert "before-nav" in checkpoints
            tx.commit()
    
    def test_rollback_to_checkpoint(self):
        """rollback() restores state to checkpoint."""
        tab = self.objects.create(ObjectType.TAB, url="https://original.com")
        
        with self.tx_coord.begin() as tx:
            tab.navigate("https://step1.com")
            tx.checkpoint("after-step1")
            
            tab.navigate("https://step2.com")
            assert tab.url == "https://step2.com"
            
            tx.rollback("after-step1")
            assert tab.url == "https://step1.com"
            tx.commit()
    
    def test_rollback_to_initial(self):
        """rollback('__initial__') restores to start state."""
        tab = self.objects.create(ObjectType.TAB, url="https://original.com")
        
        with self.tx_coord.begin() as tx:
            tab.navigate("https://changed.com")
            tx.rollback("__initial__")
            
            assert tab.url == "https://original.com"
            tx.commit()
    
    def test_rollback_nonexistent_checkpoint_raises(self):
        """Rollback to nonexistent checkpoint raises."""
        with self.tx_coord.begin() as tx:
            with pytest.raises(CheckpointNotFound):
                tx.rollback("nonexistent")
            tx.abort()
    
    def test_multiple_checkpoints(self):
        """Multiple checkpoints can be created and used."""
        tab = self.objects.create(ObjectType.TAB, url="https://start.com")
        
        with self.tx_coord.begin() as tx:
            tab.navigate("https://step1.com")
            tx.checkpoint("step1")
            
            tab.navigate("https://step2.com")
            tx.checkpoint("step2")
            
            tab.navigate("https://step3.com")
            
            tx.rollback("step1")
            assert tab.url == "https://step1.com"
            
            tx.commit()
    
    def test_form_fill_rollback(self):
        """Form fill can be rolled back before submit."""
        form = self.objects.create(ObjectType.FORM, tab_id="tab:1", form_type="login")
        
        with self.tx_coord.begin() as tx:
            tx.checkpoint("before-fill")
            
            form.fill({"email": "test@example.com", "password": "secret"})
            assert form._data["filled"]["email"] == "test@example.com"
            
            tx.rollback("before-fill")
            assert form._data["filled"] == {}
            tx.commit()
    
    def test_operations_outside_transaction(self):
        """Operations outside transactions are not reversible."""
        tab = self.objects.create(ObjectType.TAB, url="https://original.com")
        tab.navigate("https://changed.com")
        
        # No transaction - change is permanent
        assert tab.url == "https://changed.com"
    
    def test_get_active_transaction(self):
        """get_active_transaction returns current tx."""
        assert self.tx_coord.get_active_transaction() is None
        
        with self.tx_coord.begin() as tx:
            active = self.tx_coord.get_active_transaction()
            assert active is not None
            assert active.id == tx.id
            tx.commit()
        
        assert self.tx_coord.get_active_transaction() is None


class TestTransactionAuditIntegration:
    """Tests for transaction + audit log integration."""
    
    def test_transaction_events_logged(self):
        """Transaction begin/commit/abort are logged."""
        audit = AuditLog()
        objects = ObjectManager(audit_log=audit)
        tx_coord = TransactionCoordinator(objects, audit)
        
        with tx_coord.begin() as tx:
            tx.checkpoint("cp1")
            tx.commit()
        
        entries = audit.query(op="transaction.*")
        ops = [e.op for e in entries]
        
        assert "transaction.begin" in ops
        assert "transaction.checkpoint" in ops
        assert "transaction.commit" in ops
    
    def test_entries_tagged_with_transaction_id(self):
        """Log entries during tx are tagged with tx_id."""
        audit = AuditLog()
        objects = ObjectManager(audit_log=audit)
        tx_coord = TransactionCoordinator(objects, audit)
        
        with tx_coord.begin() as tx:
            tx_id = tx.id
            objects.create(ObjectType.TAB, url="https://example.com")
            tx.commit()
        
        entries = audit.query(tx_id=tx_id)
        assert len(entries) >= 2  # begin, create, commit
