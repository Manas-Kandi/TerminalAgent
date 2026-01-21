"""Capability Broker - Manages capability tokens for privileged operations.

Every privileged operation requires an unforgeable capability token that binds:
- principal: which agent/workflow
- operation: what action
- resource: which object(s)
- constraints: URL pattern, time window, rate limit
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CapabilityRisk(Enum):
    """Risk levels for operations."""
    READ = "read"           # Low risk: read content, list tabs
    STATEFUL = "stateful"   # Medium risk: navigate, fill forms
    IRREVERSIBLE = "irreversible"  # High risk: submit, send, pay


@dataclass(frozen=True)
class Capability:
    """An unforgeable token permitting a principal to perform an operation."""
    token: str
    principal: str
    operation: str
    resource: str
    risk: CapabilityRisk = CapabilityRisk.READ
    constraints: dict = field(default_factory=dict)
    granted_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at
    
    def matches(self, operation: str, resource: str) -> bool:
        """Check if this capability grants the requested operation on resource."""
        if self.operation == "*":
            op_match = True
        elif self.operation.endswith(".*"):
            op_match = operation.startswith(self.operation[:-1])
        else:
            op_match = self.operation == operation
        
        if self.resource == "*":
            res_match = True
        elif self.resource.endswith(":*"):
            res_match = resource.startswith(self.resource[:-1])
        else:
            res_match = self.resource == resource
        
        return op_match and res_match


@dataclass
class CapabilityDenied(Exception):
    """Raised when a capability check fails."""
    principal: str
    operation: str
    resource: str
    reason: str = "no matching capability"
    
    def __str__(self) -> str:
        return f"CapabilityDenied: {self.principal} cannot {self.operation} on {self.resource} ({self.reason})"


class CapabilityBroker:
    """Validates every privileged operation and manages capability lifecycle."""
    
    def __init__(self, audit_log=None):
        self._capabilities: dict[str, list[Capability]] = {}  # principal -> caps
        self._tokens: dict[str, Capability] = {}  # token -> cap
        self._audit = audit_log
    
    def _generate_token(self) -> str:
        """Generate an unforgeable capability token."""
        return secrets.token_urlsafe(32)
    
    def grant(
        self,
        principal: str,
        operation: str,
        resource: str,
        risk: CapabilityRisk = CapabilityRisk.READ,
        constraints: Optional[dict] = None,
        ttl_seconds: Optional[float] = None,
    ) -> Capability:
        """Grant a capability to a principal.
        
        Args:
            principal: Identity performing actions (e.g., 'agent:1', 'user:alice')
            operation: Action to permit (e.g., 'tab.read', 'form.submit')
            resource: Target object (e.g., 'tab:42', 'form:*')
            risk: Risk level of the operation
            constraints: Additional constraints (url_pattern, rate_limit, etc.)
            ttl_seconds: Time-to-live; None means no expiry
            
        Returns:
            The granted Capability
        """
        token = self._generate_token()
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        
        cap = Capability(
            token=token,
            principal=principal,
            operation=operation,
            resource=resource,
            risk=risk,
            constraints=constraints or {},
            expires_at=expires_at,
        )
        
        if principal not in self._capabilities:
            self._capabilities[principal] = []
        self._capabilities[principal].append(cap)
        self._tokens[token] = cap
        
        if self._audit:
            self._audit.log(
                op="capability.grant",
                principal="system",
                object=f"cap:{token[:8]}",
                args={"to": principal, "operation": operation, "resource": resource},
                result="granted",
            )
        
        return cap
    
    def check(
        self,
        principal: str,
        operation: str,
        resource: str,
        raise_on_deny: bool = False,
    ) -> bool:
        """Check if principal has capability for operation on resource.
        
        Args:
            principal: Identity to check
            operation: Requested operation
            resource: Target resource
            raise_on_deny: If True, raise CapabilityDenied instead of returning False
            
        Returns:
            True if permitted, False otherwise
            
        Raises:
            CapabilityDenied: If raise_on_deny=True and check fails
        """
        caps = self._capabilities.get(principal, [])
        
        for cap in caps:
            if cap.is_expired():
                continue
            if cap.matches(operation, resource):
                if self._audit:
                    self._audit.log(
                        op="capability.check",
                        principal=principal,
                        object=resource,
                        args={"operation": operation},
                        result="allowed",
                    )
                return True
        
        if self._audit:
            self._audit.log(
                op="capability.check",
                principal=principal,
                object=resource,
                args={"operation": operation},
                result="denied",
            )
        
        if raise_on_deny:
            raise CapabilityDenied(principal, operation, resource)
        return False
    
    def revoke(self, token: str) -> bool:
        """Revoke a capability by its token.
        
        Returns:
            True if revoked, False if token not found
        """
        cap = self._tokens.pop(token, None)
        if cap is None:
            return False
        
        if cap.principal in self._capabilities:
            self._capabilities[cap.principal] = [
                c for c in self._capabilities[cap.principal] if c.token != token
            ]
        
        if self._audit:
            self._audit.log(
                op="capability.revoke",
                principal="system",
                object=f"cap:{token[:8]}",
                args={"was_for": cap.principal},
                result="revoked",
            )
        
        return True
    
    def revoke_all(self, principal: str) -> int:
        """Revoke all capabilities for a principal.
        
        Returns:
            Number of capabilities revoked
        """
        caps = self._capabilities.pop(principal, [])
        count = len(caps)
        
        for cap in caps:
            self._tokens.pop(cap.token, None)
        
        if self._audit and count > 0:
            self._audit.log(
                op="capability.revoke_all",
                principal="system",
                object=principal,
                args={},
                result=f"revoked:{count}",
            )
        
        return count
    
    def list_capabilities(self, principal: str) -> list[Capability]:
        """List all non-expired capabilities for a principal."""
        return [c for c in self._capabilities.get(principal, []) if not c.is_expired()]
    
    def require(self, principal: str, operation: str, resource: str) -> None:
        """Check capability and raise if denied. Convenience wrapper."""
        self.check(principal, operation, resource, raise_on_deny=True)
