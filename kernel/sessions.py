"""Session and Revocation Management.

Defines:
- What is a "session" (process lifetime, workspace, UI instance)
- How capabilities are scoped to sessions
- Revocation persistence (survives restart)
- Grant lifecycle tracking

Answers the critical questions:
1. What exactly is a session?
2. How does a user revoke a grant issued 3h ago?
3. Do revoked caps persist to disk so restart doesn't resurrect them?
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
from typing import Optional, Callable


class SessionType(Enum):
    """Types of capability sessions."""
    PROCESS = "process"      # Lives until kernel process exits
    WORKSPACE = "workspace"  # Lives until workspace is closed
    TIMED = "timed"          # Lives for specified duration
    PERSISTENT = "persistent"  # Survives restarts (stored on disk)


class GrantScope(Enum):
    """Scope of a capability grant."""
    ONCE = "once"            # Single operation
    SESSION = "session"      # Until session ends
    RESOURCE = "resource"    # For specific resource pattern
    ALWAYS = "always"        # Permanent (persisted)


@dataclass
class Session:
    """A capability session."""
    id: str
    type: SessionType
    principal: str
    created_at: float
    expires_at: Optional[float] = None
    workspace_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        d = dict(d)
        d["type"] = SessionType(d["type"])
        return cls(**d)


@dataclass
class CapabilityGrant:
    """A recorded capability grant with lifecycle tracking."""
    id: str
    token: str  # Reference to Capability.token
    principal: str
    operation: str
    resource: str
    scope: GrantScope
    session_id: Optional[str]
    granted_at: float
    granted_by: str  # "user", "policy", "auto"
    expires_at: Optional[float] = None
    revoked_at: Optional[float] = None
    revoked_by: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and time.time() > self.expires_at:
            return False
        return True
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d["scope"] = self.scope.value
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> "CapabilityGrant":
        d = dict(d)
        d["scope"] = GrantScope(d["scope"])
        return cls(**d)


@dataclass
class RevocationRecord:
    """A record of a revoked capability (persisted to prevent resurrection)."""
    id: str
    grant_id: str
    token: str
    principal: str
    operation: str
    resource: str
    revoked_at: float
    revoked_by: str
    reason: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: dict) -> "RevocationRecord":
        return cls(**d)


class SessionManager:
    """Manages capability sessions and revocation persistence.
    
    Key guarantees:
    1. Sessions have clear boundaries (process, workspace, timed, persistent)
    2. Revocations are persisted to disk and survive restart
    3. All grants are tracked with full lifecycle metadata
    4. Users can query and revoke grants by various criteria
    """
    
    def __init__(self, db_path: Optional[str | Path] = None):
        """Initialize session manager.
        
        Args:
            db_path: Path to SQLite database for persistence.
                    If None, uses in-memory (no persistence).
        """
        self._db_path = str(db_path) if db_path else ":memory:"
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._lock = threading.Lock()
        
        self._sessions: dict[str, Session] = {}
        self._grants: dict[str, CapabilityGrant] = {}
        self._revocations: dict[str, RevocationRecord] = {}
        
        self._init_db()
        self._load_persisted_data()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    principal TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    workspace_id TEXT,
                    metadata TEXT NOT NULL
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS grants (
                    id TEXT PRIMARY KEY,
                    token TEXT NOT NULL,
                    principal TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    session_id TEXT,
                    granted_at REAL NOT NULL,
                    granted_by TEXT NOT NULL,
                    expires_at REAL,
                    revoked_at REAL,
                    revoked_by TEXT,
                    metadata TEXT NOT NULL
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS revocations (
                    id TEXT PRIMARY KEY,
                    grant_id TEXT NOT NULL,
                    token TEXT NOT NULL,
                    principal TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    revoked_at REAL NOT NULL,
                    revoked_by TEXT NOT NULL,
                    reason TEXT
                )
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_grants_principal ON grants(principal)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_grants_token ON grants(token)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_revocations_token ON revocations(token)
            """)
            self._conn.commit()
    
    def _load_persisted_data(self) -> None:
        """Load persisted sessions, grants, and revocations from disk."""
        with self._lock:
            # Load sessions (only persistent ones matter after restart)
            cursor = self._conn.execute(
                "SELECT * FROM sessions WHERE type = ?",
                (SessionType.PERSISTENT.value,)
            )
            for row in cursor:
                session = Session(
                    id=row[0],
                    type=SessionType(row[1]),
                    principal=row[2],
                    created_at=row[3],
                    expires_at=row[4],
                    workspace_id=row[5],
                    metadata=json.loads(row[6]),
                )
                self._sessions[session.id] = session
            
            # Load grants (all, including revoked for audit)
            cursor = self._conn.execute("SELECT * FROM grants")
            for row in cursor:
                grant = CapabilityGrant(
                    id=row[0],
                    token=row[1],
                    principal=row[2],
                    operation=row[3],
                    resource=row[4],
                    scope=GrantScope(row[5]),
                    session_id=row[6],
                    granted_at=row[7],
                    granted_by=row[8],
                    expires_at=row[9],
                    revoked_at=row[10],
                    revoked_by=row[11],
                    metadata=json.loads(row[12]),
                )
                self._grants[grant.id] = grant
            
            # Load revocations
            cursor = self._conn.execute("SELECT * FROM revocations")
            for row in cursor:
                revocation = RevocationRecord(
                    id=row[0],
                    grant_id=row[1],
                    token=row[2],
                    principal=row[3],
                    operation=row[4],
                    resource=row[5],
                    revoked_at=row[6],
                    revoked_by=row[7],
                    reason=row[8] or "",
                )
                self._revocations[revocation.id] = revocation
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    def create_session(
        self,
        principal: str,
        session_type: SessionType,
        workspace_id: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> Session:
        """Create a new session.
        
        Args:
            principal: Identity owning the session
            session_type: Type of session (process, workspace, timed, persistent)
            workspace_id: Associated workspace (for workspace sessions)
            ttl_seconds: Time-to-live (for timed sessions)
            metadata: Additional session metadata
            
        Returns:
            The created Session
        """
        session_id = f"session:{uuid.uuid4().hex[:8]}"
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        
        session = Session(
            id=session_id,
            type=session_type,
            principal=principal,
            created_at=time.time(),
            expires_at=expires_at,
            workspace_id=workspace_id,
            metadata=metadata or {},
        )
        
        self._sessions[session_id] = session
        
        # Persist if persistent type
        if session_type == SessionType.PERSISTENT:
            self._persist_session(session)
        
        return session
    
    def _persist_session(self, session: Session) -> None:
        """Persist a session to disk."""
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO sessions 
                (id, type, principal, created_at, expires_at, workspace_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.type.value,
                    session.principal,
                    session.created_at,
                    session.expires_at,
                    session.workspace_id,
                    json.dumps(session.metadata),
                ),
            )
            self._conn.commit()
    
    def end_session(self, session_id: str) -> bool:
        """End a session and revoke all its grants.
        
        Returns:
            True if session existed and was ended
        """
        session = self._sessions.pop(session_id, None)
        if not session:
            return False
        
        # Revoke all grants for this session
        for grant in list(self._grants.values()):
            if grant.session_id == session_id and grant.is_active():
                self.revoke_grant(grant.id, revoked_by="session_end")
        
        # Remove from DB if persisted
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._conn.commit()
        
        return True
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        session = self._sessions.get(session_id)
        if session and session.is_expired():
            self.end_session(session_id)
            return None
        return session
    
    # =========================================================================
    # Grant Management
    # =========================================================================
    
    def record_grant(
        self,
        token: str,
        principal: str,
        operation: str,
        resource: str,
        scope: GrantScope,
        granted_by: str,
        session_id: Optional[str] = None,
        expires_at: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> CapabilityGrant:
        """Record a capability grant.
        
        Args:
            token: Capability token from CapabilityBroker
            principal: Identity receiving the grant
            operation: Permitted operation
            resource: Permitted resource
            scope: Grant scope (once, session, resource, always)
            granted_by: Who granted (user, policy, auto)
            session_id: Associated session (for session-scoped grants)
            expires_at: Expiration timestamp
            metadata: Additional grant metadata
            
        Returns:
            The recorded CapabilityGrant
        """
        grant_id = f"grant:{uuid.uuid4().hex[:8]}"
        
        grant = CapabilityGrant(
            id=grant_id,
            token=token,
            principal=principal,
            operation=operation,
            resource=resource,
            scope=scope,
            session_id=session_id,
            granted_at=time.time(),
            granted_by=granted_by,
            expires_at=expires_at,
            metadata=metadata or {},
        )
        
        self._grants[grant_id] = grant
        
        # Persist if always scope
        if scope == GrantScope.ALWAYS:
            self._persist_grant(grant)
        
        return grant
    
    def _persist_grant(self, grant: CapabilityGrant) -> None:
        """Persist a grant to disk."""
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO grants 
                (id, token, principal, operation, resource, scope, session_id,
                 granted_at, granted_by, expires_at, revoked_at, revoked_by, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    grant.id,
                    grant.token,
                    grant.principal,
                    grant.operation,
                    grant.resource,
                    grant.scope.value,
                    grant.session_id,
                    grant.granted_at,
                    grant.granted_by,
                    grant.expires_at,
                    grant.revoked_at,
                    grant.revoked_by,
                    json.dumps(grant.metadata),
                ),
            )
            self._conn.commit()
    
    def revoke_grant(
        self,
        grant_id: str,
        revoked_by: str,
        reason: str = "",
    ) -> bool:
        """Revoke a grant.
        
        Args:
            grant_id: ID of grant to revoke
            revoked_by: Who revoked (user, system, session_end)
            reason: Reason for revocation
            
        Returns:
            True if grant was found and revoked
        """
        grant = self._grants.get(grant_id)
        if not grant or not grant.is_active():
            return False
        
        grant.revoked_at = time.time()
        grant.revoked_by = revoked_by
        
        # Create revocation record (always persisted)
        revocation = RevocationRecord(
            id=f"revoke:{uuid.uuid4().hex[:8]}",
            grant_id=grant_id,
            token=grant.token,
            principal=grant.principal,
            operation=grant.operation,
            resource=grant.resource,
            revoked_at=grant.revoked_at,
            revoked_by=revoked_by,
            reason=reason,
        )
        
        self._revocations[revocation.id] = revocation
        self._persist_revocation(revocation)
        
        # Update grant in DB if persisted
        if grant.scope == GrantScope.ALWAYS:
            self._persist_grant(grant)
        
        return True
    
    def _persist_revocation(self, revocation: RevocationRecord) -> None:
        """Persist a revocation to disk."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO revocations 
                (id, grant_id, token, principal, operation, resource, 
                 revoked_at, revoked_by, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revocation.id,
                    revocation.grant_id,
                    revocation.token,
                    revocation.principal,
                    revocation.operation,
                    revocation.resource,
                    revocation.revoked_at,
                    revocation.revoked_by,
                    revocation.reason,
                ),
            )
            self._conn.commit()
    
    def is_token_revoked(self, token: str) -> bool:
        """Check if a capability token has been revoked.
        
        This is the key check that prevents resurrection after restart.
        """
        for revocation in self._revocations.values():
            if revocation.token == token:
                return True
        return False
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def list_grants(
        self,
        principal: Optional[str] = None,
        active_only: bool = True,
        since: Optional[float] = None,
    ) -> list[CapabilityGrant]:
        """List grants with optional filters."""
        results = []
        for grant in self._grants.values():
            if principal and grant.principal != principal:
                continue
            if active_only and not grant.is_active():
                continue
            if since and grant.granted_at < since:
                continue
            results.append(grant)
        return sorted(results, key=lambda g: g.granted_at, reverse=True)
    
    def list_revocations(
        self,
        principal: Optional[str] = None,
        since: Optional[float] = None,
    ) -> list[RevocationRecord]:
        """List revocations with optional filters."""
        results = []
        for revocation in self._revocations.values():
            if principal and revocation.principal != principal:
                continue
            if since and revocation.revoked_at < since:
                continue
            results.append(revocation)
        return sorted(results, key=lambda r: r.revoked_at, reverse=True)
    
    def get_grant_by_token(self, token: str) -> Optional[CapabilityGrant]:
        """Get a grant by its capability token."""
        for grant in self._grants.values():
            if grant.token == token:
                return grant
        return None
    
    def revoke_all_for_principal(self, principal: str, revoked_by: str) -> int:
        """Revoke all active grants for a principal.
        
        Returns:
            Number of grants revoked
        """
        count = 0
        for grant in list(self._grants.values()):
            if grant.principal == principal and grant.is_active():
                if self.revoke_grant(grant.id, revoked_by):
                    count += 1
        return count
