"""Transaction Coordinator - Checkpoints, commit, and rollback for browser-local state.

Provides transactional semantics for multi-step workflows:
- Checkpoint: save current browser state
- Rollback: restore to a checkpoint
- Commit: finalize changes

What CAN be rolled back (browser-local):
- Tab URLs / navigation state
- Form fill buffers (before submit)
- Workspace ephemeral state

What CANNOT be rolled back (external side effects):
- Submitted forms
- Sent emails
- API calls
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from kernel.objects import ObjectManager, ObjectState
    from kernel.audit import AuditLog


class TransactionState(Enum):
    """State of a transaction."""
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    ABORTED = "aborted"


@dataclass
class Checkpoint:
    """A saved state snapshot within a transaction."""
    id: str
    name: str
    tx_id: str
    timestamp: float
    state: dict[str, "ObjectState"]
    
    def __repr__(self) -> str:
        return f"Checkpoint({self.name!r}, objects={len(self.state)})"


@dataclass
class Transaction:
    """A transaction with checkpoints and commit/rollback semantics."""
    id: str
    state: TransactionState = TransactionState.ACTIVE
    checkpoints: dict[str, Checkpoint] = field(default_factory=dict)
    operations: list[dict] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    
    def is_active(self) -> bool:
        return self.state == TransactionState.ACTIVE


class TransactionError(Exception):
    """Base exception for transaction errors."""
    pass


class TransactionNotActive(TransactionError):
    """Raised when operating on a non-active transaction."""
    pass


class CheckpointNotFound(TransactionError):
    """Raised when a checkpoint doesn't exist."""
    pass


class TransactionCoordinator:
    """Coordinates transactions with checkpoints and rollback.
    
    Usage:
        with coordinator.begin() as tx:
            tx.checkpoint('before-nav')
            # ... do work ...
            if something_wrong:
                tx.rollback('before-nav')
            else:
                tx.commit()
    """
    
    def __init__(self, object_manager: "ObjectManager", audit_log: Optional["AuditLog"] = None):
        self._objects = object_manager
        self._audit = audit_log
        self._transactions: dict[str, Transaction] = {}
        self._active_tx: Optional[str] = None
        self._checkpoint_counter = 0
    
    def _next_checkpoint_id(self) -> str:
        self._checkpoint_counter += 1
        return f"cp:{self._checkpoint_counter}"
    
    def begin(self) -> "TransactionContext":
        """Begin a new transaction.
        
        Returns:
            A TransactionContext for use with 'with' statement
        """
        tx_id = f"tx:{uuid.uuid4().hex[:8]}"
        tx = Transaction(id=tx_id)
        self._transactions[tx_id] = tx
        self._active_tx = tx_id
        
        # Create initial checkpoint (start state)
        initial_state = self._objects.snapshot_all()
        initial_cp = Checkpoint(
            id=self._next_checkpoint_id(),
            name="__initial__",
            tx_id=tx_id,
            timestamp=time.time(),
            state=initial_state,
        )
        tx.checkpoints["__initial__"] = initial_cp
        
        if self._audit:
            self._audit.set_transaction_context(tx_id)
            self._audit.log(
                op="transaction.begin",
                principal="system",
                object=tx_id,
                args={},
                result="started",
            )
        
        return TransactionContext(self, tx)
    
    def checkpoint(self, name: str, tx_id: Optional[str] = None) -> Checkpoint:
        """Create a named checkpoint in the current or specified transaction.
        
        Args:
            name: Human-readable checkpoint name
            tx_id: Transaction ID (uses active tx if None)
            
        Returns:
            The created Checkpoint
        """
        tx_id = tx_id or self._active_tx
        if not tx_id:
            raise TransactionError("No active transaction")
        
        tx = self._transactions.get(tx_id)
        if not tx or not tx.is_active():
            raise TransactionNotActive(f"Transaction {tx_id} is not active")
        
        state = self._objects.snapshot_all()
        cp = Checkpoint(
            id=self._next_checkpoint_id(),
            name=name,
            tx_id=tx_id,
            timestamp=time.time(),
            state=state,
        )
        tx.checkpoints[name] = cp
        
        if self._audit:
            self._audit.set_transaction_context(tx_id, cp.id)
            self._audit.log(
                op="transaction.checkpoint",
                principal="system",
                object=tx_id,
                args={"name": name, "checkpoint_id": cp.id},
                result="created",
            )
        
        return cp
    
    def rollback(self, checkpoint_name: str, tx_id: Optional[str] = None) -> None:
        """Roll back to a named checkpoint.
        
        Args:
            checkpoint_name: Name of checkpoint to restore
            tx_id: Transaction ID (uses active tx if None)
        """
        tx_id = tx_id or self._active_tx
        if not tx_id:
            raise TransactionError("No active transaction")
        
        tx = self._transactions.get(tx_id)
        if not tx or not tx.is_active():
            raise TransactionNotActive(f"Transaction {tx_id} is not active")
        
        cp = tx.checkpoints.get(checkpoint_name)
        if not cp:
            raise CheckpointNotFound(f"Checkpoint '{checkpoint_name}' not found")
        
        # Restore object state
        self._objects.restore_snapshot(cp.state)
        
        if self._audit:
            self._audit.log(
                op="transaction.rollback",
                principal="system",
                object=tx_id,
                args={"to_checkpoint": checkpoint_name},
                result="restored",
            )
    
    def commit(self, tx_id: Optional[str] = None) -> None:
        """Commit the transaction, finalizing all changes.
        
        Args:
            tx_id: Transaction ID (uses active tx if None)
        """
        tx_id = tx_id or self._active_tx
        if not tx_id:
            raise TransactionError("No active transaction")
        
        tx = self._transactions.get(tx_id)
        if not tx or not tx.is_active():
            raise TransactionNotActive(f"Transaction {tx_id} is not active")
        
        tx.state = TransactionState.COMMITTED
        tx.ended_at = time.time()
        
        if self._audit:
            self._audit.log(
                op="transaction.commit",
                principal="system",
                object=tx_id,
                args={},
                result="committed",
            )
            self._audit.clear_transaction_context()
        
        if self._active_tx == tx_id:
            self._active_tx = None
    
    def abort(self, tx_id: Optional[str] = None) -> None:
        """Abort the transaction and restore initial state.
        
        Args:
            tx_id: Transaction ID (uses active tx if None)
        """
        tx_id = tx_id or self._active_tx
        if not tx_id:
            raise TransactionError("No active transaction")
        
        tx = self._transactions.get(tx_id)
        if not tx:
            raise TransactionError(f"Transaction {tx_id} not found")
        
        if tx.is_active():
            # Restore to initial state
            initial_cp = tx.checkpoints.get("__initial__")
            if initial_cp:
                self._objects.restore_snapshot(initial_cp.state)
        
        tx.state = TransactionState.ABORTED
        tx.ended_at = time.time()
        
        if self._audit:
            self._audit.log(
                op="transaction.abort",
                principal="system",
                object=tx_id,
                args={},
                result="aborted",
            )
            self._audit.clear_transaction_context()
        
        if self._active_tx == tx_id:
            self._active_tx = None
    
    def get_transaction(self, tx_id: str) -> Optional[Transaction]:
        """Get a transaction by ID."""
        return self._transactions.get(tx_id)
    
    def get_active_transaction(self) -> Optional[Transaction]:
        """Get the currently active transaction."""
        if self._active_tx:
            return self._transactions.get(self._active_tx)
        return None
    
    def list_checkpoints(self, tx_id: Optional[str] = None) -> list[str]:
        """List checkpoint names in a transaction."""
        tx_id = tx_id or self._active_tx
        if not tx_id:
            return []
        tx = self._transactions.get(tx_id)
        if not tx:
            return []
        return [name for name in tx.checkpoints.keys() if name != "__initial__"]


class TransactionContext:
    """Context manager for transactions."""
    
    def __init__(self, coordinator: TransactionCoordinator, transaction: Transaction):
        self._coordinator = coordinator
        self._tx = transaction
        self._committed = False
    
    @property
    def id(self) -> str:
        return self._tx.id
    
    @property
    def is_active(self) -> bool:
        return self._tx.is_active()
    
    def checkpoint(self, name: str) -> Checkpoint:
        """Create a named checkpoint."""
        return self._coordinator.checkpoint(name, self._tx.id)
    
    def rollback(self, checkpoint_name: str = "__initial__") -> None:
        """Roll back to a checkpoint (default: initial state)."""
        self._coordinator.rollback(checkpoint_name, self._tx.id)
    
    def commit(self) -> None:
        """Commit the transaction."""
        self._coordinator.commit(self._tx.id)
        self._committed = True
    
    def abort(self) -> None:
        """Abort the transaction."""
        self._coordinator.abort(self._tx.id)
    
    def __enter__(self) -> "TransactionContext":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            # Exception occurred - abort
            if self._tx.is_active():
                self.abort()
            return False
        
        if not self._committed and self._tx.is_active():
            # No explicit commit - abort
            self.abort()
        
        return False
