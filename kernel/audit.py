"""Audit Log - Append-only operation log with provenance tracking.

Every privileged operation is logged with:
- timestamp
- principal (who)
- operation (what)
- object (which resource)
- args (parameters)
- result (outcome)
- transaction context
- provenance (human|agent|web_content)
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Optional


class Provenance(Enum):
    """Origin of an action or content."""
    HUMAN = "human"
    AGENT = "agent"
    WEB_CONTENT = "web_content"
    SYSTEM = "system"


@dataclass
class AuditEntry:
    """A single entry in the audit log."""
    id: str
    timestamp: float
    op: str
    principal: str
    object: str
    args: dict
    result: str
    tx_id: Optional[str] = None
    checkpoint_id: Optional[str] = None
    provenance: Provenance = Provenance.SYSTEM
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d["provenance"] = self.provenance.value
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> AuditEntry:
        d = dict(d)
        d["provenance"] = Provenance(d["provenance"])
        return cls(**d)


class AuditLog:
    """Append-only audit log with SQLite persistence.
    
    Properties:
    - Append-only: entries cannot be modified or deleted
    - Every privileged op is logged
    - Secrets are never recorded (caller responsibility)
    - PII-safe: field names are hashed to prevent leaking schema info
    - Supports query/export for replay and debugging
    """
    
    def __init__(self, db_path: Optional[str | Path] = None, workspace_salt: Optional[str] = None):
        """Initialize the audit log.
        
        Args:
            db_path: Path to SQLite database. If None, uses in-memory DB.
            workspace_salt: Salt for hashing field names (PII protection).
                          If None, generates a random salt.
        """
        self._db_path = str(db_path) if db_path else ":memory:"
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._current_tx: Optional[str] = None
        self._current_checkpoint: Optional[str] = None
        self._redact_keys: set[str] = {"password", "secret", "token", "key", "credential"}
        self._pii_field_names: set[str] = {"ssn", "social_security", "dob", "date_of_birth", 
                                            "credit_card", "card_number", "cvv", "phone",
                                            "address", "zip", "postal"}
        self._workspace_salt = workspace_salt or uuid.uuid4().hex
        self._hash_field_names = True  # Enable PII protection by default
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    op TEXT NOT NULL,
                    principal TEXT NOT NULL,
                    object TEXT NOT NULL,
                    args TEXT NOT NULL,
                    result TEXT NOT NULL,
                    tx_id TEXT,
                    checkpoint_id TEXT,
                    provenance TEXT NOT NULL,
                    correlation_id TEXT
                )
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_principal ON audit_log(principal)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_op ON audit_log(op)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_tx ON audit_log(tx_id)
            """)
            self._conn.commit()
    
    def _hash_field_name(self, field_name: str) -> str:
        """Hash a field name for PII protection.
        
        Uses salted SHA256, truncated to 8 chars for readability.
        The salt is workspace-specific so hashes differ across workspaces.
        """
        import hashlib
        salted = f"{field_name}:{self._workspace_salt}"
        return hashlib.sha256(salted.encode()).hexdigest()[:8]
    
    def _is_pii_field(self, field_name: str) -> bool:
        """Check if a field name indicates PII."""
        name_lower = field_name.lower()
        return any(pii in name_lower for pii in self._pii_field_names)
    
    def _redact(self, args: dict, parent_key: str = "") -> dict:
        """Redact sensitive values and hash PII field names from args.
        
        - Sensitive values (passwords, tokens) are replaced with [REDACTED]
        - PII field names (ssn, credit_card) are hashed to prevent schema leakage
        """
        result = {}
        for k, v in args.items():
            key_lower = k.lower()
            
            # Check if value should be redacted
            is_sensitive = any(
                key_lower == sensitive or key_lower.endswith(f"_{sensitive}") or key_lower.endswith(sensitive)
                for sensitive in self._redact_keys
            )
            
            # Check if field name is PII and should be hashed
            should_hash_key = self._hash_field_names and self._is_pii_field(k)
            output_key = f"[PII:{self._hash_field_name(k)}]" if should_hash_key else k
            
            if is_sensitive:
                result[output_key] = "[REDACTED]"
            elif isinstance(v, dict):
                result[output_key] = self._redact(v, parent_key=k)
            elif isinstance(v, list) and parent_key in ("fields", "filled_fields"):
                # Hash field names in lists (e.g., form field lists)
                if self._hash_field_names:
                    result[output_key] = [
                        f"[PII:{self._hash_field_name(item)}]" if isinstance(item, str) and self._is_pii_field(item) else item
                        for item in v
                    ]
                else:
                    result[output_key] = v
            else:
                result[output_key] = v
        return result
    
    def log(
        self,
        op: str,
        principal: str,
        object: str,
        args: Optional[dict] = None,
        result: str = "success",
        provenance: Provenance = Provenance.SYSTEM,
        correlation_id: Optional[str] = None,
    ) -> AuditEntry:
        """Log an operation.
        
        Args:
            op: Operation name (e.g., 'tab.navigate', 'form.submit')
            principal: Identity performing the operation
            object: Target resource ID
            args: Operation arguments (sensitive values will be redacted)
            result: Operation result ('success', 'denied', 'error:...', etc.)
            provenance: Origin of the action
            correlation_id: Optional ID to correlate related operations
            
        Returns:
            The created AuditEntry
        """
        entry = AuditEntry(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            op=op,
            principal=principal,
            object=object,
            args=self._redact(args or {}),
            result=result,
            tx_id=self._current_tx,
            checkpoint_id=self._current_checkpoint,
            provenance=provenance,
            correlation_id=correlation_id,
        )
        
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO audit_log 
                (id, timestamp, op, principal, object, args, result, tx_id, checkpoint_id, provenance, correlation_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.timestamp,
                    entry.op,
                    entry.principal,
                    entry.object,
                    json.dumps(entry.args),
                    entry.result,
                    entry.tx_id,
                    entry.checkpoint_id,
                    entry.provenance.value,
                    entry.correlation_id,
                ),
            )
            self._conn.commit()
        
        return entry
    
    def set_transaction_context(self, tx_id: Optional[str], checkpoint_id: Optional[str] = None) -> None:
        """Set the current transaction context for subsequent logs."""
        self._current_tx = tx_id
        self._current_checkpoint = checkpoint_id
    
    def clear_transaction_context(self) -> None:
        """Clear the transaction context."""
        self._current_tx = None
        self._current_checkpoint = None
    
    def query(
        self,
        principal: Optional[str] = None,
        op: Optional[str] = None,
        object_id: Optional[str] = None,
        tx_id: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 1000,
    ) -> list[AuditEntry]:
        """Query the audit log.
        
        Args:
            principal: Filter by principal
            op: Filter by operation (supports prefix match with *)
            object_id: Filter by object ID
            tx_id: Filter by transaction ID
            since: Filter entries after this timestamp
            until: Filter entries before this timestamp
            limit: Maximum entries to return
            
        Returns:
            List of matching AuditEntry objects
        """
        conditions = []
        params = []
        
        if principal:
            conditions.append("principal = ?")
            params.append(principal)
        if op:
            if op.endswith("*"):
                conditions.append("op LIKE ?")
                params.append(op[:-1] + "%")
            else:
                conditions.append("op = ?")
                params.append(op)
        if object_id:
            conditions.append("object = ?")
            params.append(object_id)
        if tx_id:
            conditions.append("tx_id = ?")
            params.append(tx_id)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
        if until:
            conditions.append("timestamp <= ?")
            params.append(until)
        
        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        
        with self._lock:
            cursor = self._conn.execute(
                f"""
                SELECT id, timestamp, op, principal, object, args, result, 
                       tx_id, checkpoint_id, provenance, correlation_id
                FROM audit_log
                WHERE {where}
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                params,
            )
            rows = cursor.fetchall()
        
        return [
            AuditEntry(
                id=row[0],
                timestamp=row[1],
                op=row[2],
                principal=row[3],
                object=row[4],
                args=json.loads(row[5]),
                result=row[6],
                tx_id=row[7],
                checkpoint_id=row[8],
                provenance=Provenance(row[9]),
                correlation_id=row[10],
            )
            for row in rows
        ]
    
    def export_json(self, filepath: str | Path, **query_kwargs) -> int:
        """Export audit entries to a JSON file.
        
        Args:
            filepath: Output file path
            **query_kwargs: Filters passed to query()
            
        Returns:
            Number of entries exported
        """
        entries = self.query(**query_kwargs)
        with open(filepath, "w") as f:
            json.dump([e.to_dict() for e in entries], f, indent=2)
        return len(entries)
    
    def count(self, **query_kwargs) -> int:
        """Count entries matching the query."""
        return len(self.query(**query_kwargs))
    
    def get_transaction_log(self, tx_id: str) -> list[AuditEntry]:
        """Get all log entries for a transaction."""
        return self.query(tx_id=tx_id)
