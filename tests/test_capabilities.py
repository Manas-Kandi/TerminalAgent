"""Tests for the Capability Broker."""

import time
import pytest
from kernel.capabilities import CapabilityBroker, CapabilityDenied, CapabilityRisk


class TestCapabilityBroker:
    """Tests for capability grant, check, and revoke."""
    
    def test_grant_and_check_basic(self):
        """Grant a capability and verify it can be checked."""
        broker = CapabilityBroker()
        
        cap = broker.grant(
            principal="agent:1",
            operation="tab.read",
            resource="tab:42",
        )
        
        assert cap.principal == "agent:1"
        assert cap.operation == "tab.read"
        assert cap.resource == "tab:42"
        assert broker.check("agent:1", "tab.read", "tab:42") is True
    
    def test_check_denied_no_capability(self):
        """Check returns False when no capability exists."""
        broker = CapabilityBroker()
        
        assert broker.check("agent:1", "tab.read", "tab:42") is False
    
    def test_check_denied_wrong_operation(self):
        """Check returns False for wrong operation."""
        broker = CapabilityBroker()
        broker.grant("agent:1", "tab.read", "tab:42")
        
        assert broker.check("agent:1", "tab.write", "tab:42") is False
    
    def test_check_denied_wrong_resource(self):
        """Check returns False for wrong resource."""
        broker = CapabilityBroker()
        broker.grant("agent:1", "tab.read", "tab:42")
        
        assert broker.check("agent:1", "tab.read", "tab:99") is False
    
    def test_require_raises_on_deny(self):
        """require() raises CapabilityDenied when check fails."""
        broker = CapabilityBroker()
        
        with pytest.raises(CapabilityDenied) as exc_info:
            broker.require("agent:1", "tab.read", "tab:42")
        
        assert exc_info.value.principal == "agent:1"
        assert exc_info.value.operation == "tab.read"
        assert exc_info.value.resource == "tab:42"
    
    def test_wildcard_operation(self):
        """Wildcard operation grants all operations."""
        broker = CapabilityBroker()
        broker.grant("agent:1", "*", "tab:42")
        
        assert broker.check("agent:1", "tab.read", "tab:42") is True
        assert broker.check("agent:1", "tab.write", "tab:42") is True
        assert broker.check("agent:1", "anything", "tab:42") is True
    
    def test_wildcard_resource(self):
        """Wildcard resource grants access to all resources."""
        broker = CapabilityBroker()
        broker.grant("agent:1", "tab.read", "*")
        
        assert broker.check("agent:1", "tab.read", "tab:1") is True
        assert broker.check("agent:1", "tab.read", "tab:99") is True
        assert broker.check("agent:1", "tab.read", "form:1") is True
    
    def test_prefix_operation_wildcard(self):
        """Operation prefix wildcard (tab.*) matches all tab operations."""
        broker = CapabilityBroker()
        broker.grant("agent:1", "tab.*", "tab:42")
        
        assert broker.check("agent:1", "tab.read", "tab:42") is True
        assert broker.check("agent:1", "tab.write", "tab:42") is True
        assert broker.check("agent:1", "form.read", "tab:42") is False
    
    def test_prefix_resource_wildcard(self):
        """Resource prefix wildcard (tab:*) matches all tabs."""
        broker = CapabilityBroker()
        broker.grant("agent:1", "tab.read", "tab:*")
        
        assert broker.check("agent:1", "tab.read", "tab:1") is True
        assert broker.check("agent:1", "tab.read", "tab:99") is True
        assert broker.check("agent:1", "tab.read", "form:1") is False
    
    def test_revoke_by_token(self):
        """Revoke a capability by its token."""
        broker = CapabilityBroker()
        cap = broker.grant("agent:1", "tab.read", "tab:42")
        
        assert broker.check("agent:1", "tab.read", "tab:42") is True
        
        result = broker.revoke(cap.token)
        assert result is True
        assert broker.check("agent:1", "tab.read", "tab:42") is False
    
    def test_revoke_nonexistent_token(self):
        """Revoke returns False for nonexistent token."""
        broker = CapabilityBroker()
        
        result = broker.revoke("nonexistent-token")
        assert result is False
    
    def test_revoke_all(self):
        """Revoke all capabilities for a principal."""
        broker = CapabilityBroker()
        broker.grant("agent:1", "tab.read", "tab:1")
        broker.grant("agent:1", "tab.read", "tab:2")
        broker.grant("agent:2", "tab.read", "tab:1")
        
        count = broker.revoke_all("agent:1")
        
        assert count == 2
        assert broker.check("agent:1", "tab.read", "tab:1") is False
        assert broker.check("agent:1", "tab.read", "tab:2") is False
        assert broker.check("agent:2", "tab.read", "tab:1") is True
    
    def test_capability_expiry(self):
        """Expired capabilities are not valid."""
        broker = CapabilityBroker()
        cap = broker.grant("agent:1", "tab.read", "tab:42", ttl_seconds=0.01)
        
        # Should be valid immediately
        assert broker.check("agent:1", "tab.read", "tab:42") is True
        
        # Wait for expiry
        time.sleep(0.02)
        assert broker.check("agent:1", "tab.read", "tab:42") is False
    
    def test_list_capabilities(self):
        """List all capabilities for a principal."""
        broker = CapabilityBroker()
        broker.grant("agent:1", "tab.read", "tab:1")
        broker.grant("agent:1", "tab.write", "tab:2")
        broker.grant("agent:2", "tab.read", "tab:1")
        
        caps = broker.list_capabilities("agent:1")
        
        assert len(caps) == 2
        operations = {c.operation for c in caps}
        assert operations == {"tab.read", "tab.write"}
    
    def test_risk_levels(self):
        """Capabilities can have different risk levels."""
        broker = CapabilityBroker()
        
        read_cap = broker.grant("agent:1", "tab.read", "*", risk=CapabilityRisk.READ)
        write_cap = broker.grant("agent:1", "form.submit", "*", risk=CapabilityRisk.IRREVERSIBLE)
        
        assert read_cap.risk == CapabilityRisk.READ
        assert write_cap.risk == CapabilityRisk.IRREVERSIBLE
    
    def test_constraints_stored(self):
        """Constraints are stored on capabilities."""
        broker = CapabilityBroker()
        
        cap = broker.grant(
            "agent:1", "tab.navigate", "*",
            constraints={"url_pattern": "https://example.com/*", "rate_limit": 10}
        )
        
        assert cap.constraints["url_pattern"] == "https://example.com/*"
        assert cap.constraints["rate_limit"] == 10
