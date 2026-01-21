"""Tests for session and revocation management."""

import tempfile
import time
from pathlib import Path
import pytest

from kernel.sessions import (
    SessionManager, Session, SessionType, GrantScope,
    CapabilityGrant, RevocationRecord,
)


class TestSessionLifecycle:
    """Tests for session creation and termination."""
    
    def test_create_process_session(self):
        """Create a process-scoped session."""
        mgr = SessionManager()
        
        session = mgr.create_session(
            principal="agent:1",
            session_type=SessionType.PROCESS,
        )
        
        assert session.id.startswith("session:")
        assert session.type == SessionType.PROCESS
        assert session.principal == "agent:1"
    
    def test_create_timed_session(self):
        """Create a time-limited session."""
        mgr = SessionManager()
        
        session = mgr.create_session(
            principal="agent:1",
            session_type=SessionType.TIMED,
            ttl_seconds=3600,  # 1 hour
        )
        
        assert session.expires_at is not None
        assert not session.is_expired()
    
    def test_timed_session_expires(self):
        """Timed session expires after TTL."""
        mgr = SessionManager()
        
        session = mgr.create_session(
            principal="agent:1",
            session_type=SessionType.TIMED,
            ttl_seconds=0.01,  # 10ms
        )
        
        time.sleep(0.02)
        
        assert session.is_expired()
        # Getting expired session returns None
        assert mgr.get_session(session.id) is None
    
    def test_end_session(self):
        """End a session explicitly."""
        mgr = SessionManager()
        session = mgr.create_session("agent:1", SessionType.PROCESS)
        
        result = mgr.end_session(session.id)
        
        assert result is True
        assert mgr.get_session(session.id) is None
    
    def test_end_session_revokes_grants(self):
        """Ending a session revokes all its grants."""
        mgr = SessionManager()
        session = mgr.create_session("agent:1", SessionType.PROCESS)
        
        # Record grants for this session
        grant1 = mgr.record_grant(
            token="token1",
            principal="agent:1",
            operation="tab.read",
            resource="*",
            scope=GrantScope.SESSION,
            granted_by="user",
            session_id=session.id,
        )
        grant2 = mgr.record_grant(
            token="token2",
            principal="agent:1",
            operation="form.fill",
            resource="*",
            scope=GrantScope.SESSION,
            granted_by="user",
            session_id=session.id,
        )
        
        # End session
        mgr.end_session(session.id)
        
        # Both grants should be revoked
        assert not mgr._grants[grant1.id].is_active()
        assert not mgr._grants[grant2.id].is_active()


class TestGrantManagement:
    """Tests for capability grant tracking."""
    
    def test_record_grant(self):
        """Record a capability grant."""
        mgr = SessionManager()
        
        grant = mgr.record_grant(
            token="cap-token-123",
            principal="agent:1",
            operation="tab.read",
            resource="tab:*",
            scope=GrantScope.SESSION,
            granted_by="user",
        )
        
        assert grant.id.startswith("grant:")
        assert grant.is_active()
    
    def test_revoke_grant(self):
        """Revoke a grant."""
        mgr = SessionManager()
        
        grant = mgr.record_grant(
            token="cap-token-123",
            principal="agent:1",
            operation="tab.read",
            resource="*",
            scope=GrantScope.SESSION,
            granted_by="user",
        )
        
        result = mgr.revoke_grant(grant.id, revoked_by="user", reason="No longer needed")
        
        assert result is True
        assert not grant.is_active()
        assert grant.revoked_by == "user"
    
    def test_revoke_creates_record(self):
        """Revoking creates a revocation record."""
        mgr = SessionManager()
        
        grant = mgr.record_grant(
            token="cap-token-123",
            principal="agent:1",
            operation="tab.read",
            resource="*",
            scope=GrantScope.SESSION,
            granted_by="user",
        )
        
        mgr.revoke_grant(grant.id, revoked_by="user")
        
        revocations = mgr.list_revocations(principal="agent:1")
        assert len(revocations) == 1
        assert revocations[0].token == "cap-token-123"
    
    def test_is_token_revoked(self):
        """Check if a token has been revoked."""
        mgr = SessionManager()
        
        grant = mgr.record_grant(
            token="revokable-token",
            principal="agent:1",
            operation="tab.read",
            resource="*",
            scope=GrantScope.SESSION,
            granted_by="user",
        )
        
        assert not mgr.is_token_revoked("revokable-token")
        
        mgr.revoke_grant(grant.id, revoked_by="user")
        
        assert mgr.is_token_revoked("revokable-token")
    
    def test_list_active_grants(self):
        """List only active grants."""
        mgr = SessionManager()
        
        grant1 = mgr.record_grant(
            token="token1", principal="agent:1", operation="op1",
            resource="*", scope=GrantScope.SESSION, granted_by="user"
        )
        grant2 = mgr.record_grant(
            token="token2", principal="agent:1", operation="op2",
            resource="*", scope=GrantScope.SESSION, granted_by="user"
        )
        
        mgr.revoke_grant(grant1.id, revoked_by="user")
        
        active = mgr.list_grants(principal="agent:1", active_only=True)
        
        assert len(active) == 1
        assert active[0].token == "token2"
    
    def test_revoke_all_for_principal(self):
        """Revoke all grants for a principal."""
        mgr = SessionManager()
        
        mgr.record_grant(
            token="t1", principal="agent:bad", operation="op1",
            resource="*", scope=GrantScope.SESSION, granted_by="user"
        )
        mgr.record_grant(
            token="t2", principal="agent:bad", operation="op2",
            resource="*", scope=GrantScope.SESSION, granted_by="user"
        )
        mgr.record_grant(
            token="t3", principal="agent:good", operation="op3",
            resource="*", scope=GrantScope.SESSION, granted_by="user"
        )
        
        count = mgr.revoke_all_for_principal("agent:bad", revoked_by="admin")
        
        assert count == 2
        assert len(mgr.list_grants(principal="agent:bad", active_only=True)) == 0
        assert len(mgr.list_grants(principal="agent:good", active_only=True)) == 1


class TestRevocationPersistence:
    """Tests for revocation persistence across restarts."""
    
    def test_revocations_persist_to_disk(self):
        """Revocations are saved to disk."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            # Create manager, add grant, revoke
            mgr1 = SessionManager(db_path=db_path)
            grant = mgr1.record_grant(
                token="persistent-token",
                principal="agent:1",
                operation="tab.read",
                resource="*",
                scope=GrantScope.ALWAYS,  # Persisted
                granted_by="user",
            )
            mgr1.revoke_grant(grant.id, revoked_by="user")
            
            # Create new manager (simulates restart)
            mgr2 = SessionManager(db_path=db_path)
            
            # Revocation should still be known
            assert mgr2.is_token_revoked("persistent-token")
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    def test_revoked_token_stays_revoked_after_restart(self):
        """Revoked tokens don't resurrect after restart."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            # First session: grant and revoke
            mgr1 = SessionManager(db_path=db_path)
            grant = mgr1.record_grant(
                token="zombie-token",
                principal="agent:1",
                operation="sensitive.op",
                resource="*",
                scope=GrantScope.ALWAYS,
                granted_by="user",
            )
            mgr1.revoke_grant(grant.id, revoked_by="security")
            
            # Second session: check revocation persisted
            mgr2 = SessionManager(db_path=db_path)
            
            # This is the critical check: revoked tokens must stay revoked
            assert mgr2.is_token_revoked("zombie-token")
            
            # The grant itself should show as inactive
            loaded_grant = mgr2.get_grant_by_token("zombie-token")
            assert loaded_grant is not None
            assert not loaded_grant.is_active()
        finally:
            Path(db_path).unlink(missing_ok=True)


class TestGrantScopes:
    """Tests for different grant scopes."""
    
    def test_once_scope(self):
        """ONCE scope grants are single-use."""
        mgr = SessionManager()
        
        grant = mgr.record_grant(
            token="once-token",
            principal="agent:1",
            operation="form.submit",
            resource="form:1",
            scope=GrantScope.ONCE,
            granted_by="user",
        )
        
        assert grant.scope == GrantScope.ONCE
        # In real implementation, ONCE grants would be auto-revoked after use
    
    def test_session_scope(self):
        """SESSION scope grants are tied to session."""
        mgr = SessionManager()
        session = mgr.create_session("agent:1", SessionType.PROCESS)
        
        grant = mgr.record_grant(
            token="session-token",
            principal="agent:1",
            operation="tab.read",
            resource="*",
            scope=GrantScope.SESSION,
            granted_by="user",
            session_id=session.id,
        )
        
        assert grant.session_id == session.id
    
    def test_always_scope_persists(self):
        """ALWAYS scope grants are persisted to disk."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            mgr1 = SessionManager(db_path=db_path)
            mgr1.record_grant(
                token="always-token",
                principal="agent:trusted",
                operation="tab.*",
                resource="*",
                scope=GrantScope.ALWAYS,
                granted_by="policy",
            )
            
            # Restart
            mgr2 = SessionManager(db_path=db_path)
            
            # Grant should be loaded
            grant = mgr2.get_grant_by_token("always-token")
            assert grant is not None
            assert grant.is_active()
        finally:
            Path(db_path).unlink(missing_ok=True)
