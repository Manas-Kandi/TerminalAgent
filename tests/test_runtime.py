"""Tests for the Agent Runtime."""

import pytest
from kernel.capabilities import CapabilityBroker, CapabilityRisk
from kernel.objects import ObjectManager, ObjectType
from kernel.audit import AuditLog
from kernel.transactions import TransactionCoordinator
from kernel.runtime import AgentRuntime, ExecutionState, BrowserAPI


class TestAgentRuntime:
    """Tests for sandboxed code execution."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.audit = AuditLog()
        self.caps = CapabilityBroker(audit_log=self.audit)
        self.objects = ObjectManager(audit_log=self.audit)
        self.transactions = TransactionCoordinator(self.objects, self.audit)
        self.runtime = AgentRuntime(
            caps=self.caps,
            objects=self.objects,
            audit=self.audit,
            transactions=self.transactions,
            timeout_seconds=5.0,
        )
    
    def test_validate_valid_code(self):
        """Valid code passes validation."""
        code = """
tab = browser.Tab.open('https://example.com')
print(tab.id)
"""
        errors = self.runtime.validate_code(code)
        assert len(errors) == 0
    
    def test_validate_blocks_os_import(self):
        """os import is blocked."""
        code = "import os"
        errors = self.runtime.validate_code(code)
        assert any("os" in e for e in errors)
    
    def test_validate_blocks_subprocess(self):
        """subprocess import is blocked."""
        code = "import subprocess"
        errors = self.runtime.validate_code(code)
        assert any("subprocess" in e for e in errors)
    
    def test_validate_blocks_socket(self):
        """socket import is blocked."""
        code = "from socket import socket"
        errors = self.runtime.validate_code(code)
        assert any("socket" in e for e in errors)
    
    def test_validate_catches_syntax_error(self):
        """Syntax errors are caught."""
        code = "def broken("
        errors = self.runtime.validate_code(code)
        assert any("Syntax" in e for e in errors)
    
    def test_execute_simple_code(self):
        """Simple code executes successfully."""
        # Grant capabilities
        self.caps.grant("agent:default", "tab.*", "*")
        
        code = """
tab = browser.Tab.open('https://example.com')
print(f"Opened tab: {tab.id}")
"""
        result = self.runtime.execute(code)
        
        assert result.state == ExecutionState.COMPLETED
        assert result.error is None
    
    def test_execute_denied_without_capability(self):
        """Execution fails without required capability."""
        code = """
tab = browser.Tab.open('https://example.com')
"""
        result = self.runtime.execute(code)
        
        assert result.state == ExecutionState.FAILED
        assert result.error_type == "CapabilityDenied"
    
    def test_execute_with_validation_error(self):
        """Blocked imports fail during execution."""
        code = "import os"
        result = self.runtime.execute(code)
        
        assert result.state == ExecutionState.FAILED
        assert "Blocked import" in result.error
    
    def test_execute_returns_duration(self):
        """Execution result includes duration."""
        self.caps.grant("agent:default", "*", "*")
        
        code = "x = 1 + 1"
        result = self.runtime.execute(code)
        
        assert result.duration_ms > 0
    
    def test_execute_different_principals(self):
        """Different principals have different capabilities."""
        self.caps.grant("agent:alice", "tab.*", "*")
        # agent:bob has no capabilities
        
        code = "tab = browser.Tab.open('https://example.com')"
        
        alice_result = self.runtime.execute(code, principal="agent:alice")
        bob_result = self.runtime.execute(code, principal="agent:bob")
        
        assert alice_result.state == ExecutionState.COMPLETED
        assert bob_result.state == ExecutionState.FAILED


class TestBrowserAPI:
    """Tests for the browser API exposed to agents."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.audit = AuditLog()
        self.caps = CapabilityBroker(audit_log=self.audit)
        self.objects = ObjectManager(audit_log=self.audit)
        self.transactions = TransactionCoordinator(self.objects, self.audit)
        
        # Grant all capabilities for testing
        self.caps.grant("test-agent", "*", "*")
        
        self.browser = BrowserAPI(
            principal="test-agent",
            caps=self.caps,
            objects=self.objects,
            audit=self.audit,
            transactions=self.transactions,
        )
    
    def test_tab_open(self):
        """browser.Tab.open creates a tab."""
        tab = self.browser.Tab.open("https://example.com")
        
        assert tab.id == "tab:1"
        assert tab.url == "https://example.com"
    
    def test_tab_get(self):
        """browser.Tab.get retrieves a tab."""
        self.browser.Tab.open("https://example.com")
        
        tab = self.browser.Tab.get("tab:1")
        
        assert tab.url == "https://example.com"
    
    def test_tab_list(self):
        """browser.Tab.list returns all tabs."""
        self.browser.Tab.open("https://a.com")
        self.browser.Tab.open("https://b.com")
        
        tabs = self.browser.Tab.list()
        
        assert len(tabs) == 2
    
    def test_tab_navigate(self):
        """browser.Tab.navigate changes URL."""
        tab = self.browser.Tab.open("https://example.com")
        
        self.browser.Tab.navigate("tab:1", "https://new-url.com")
        
        assert tab.url == "https://new-url.com"
    
    def test_tab_close(self):
        """browser.Tab.close removes a tab."""
        self.browser.Tab.open("https://example.com")
        
        result = self.browser.Tab.close("tab:1")
        
        assert result is True
        assert self.objects.get("tab:1") is None
    
    def test_tab_extract(self):
        """browser.Tab.extract returns content."""
        self.browser.Tab.open("https://example.com")
        
        content = self.browser.Tab.extract("tab:1", "readable")
        
        assert content["type"] == "readable"
        assert "example.com" in content["url"]
    
    def test_form_find(self):
        """browser.Form.find creates a form reference."""
        self.browser.Tab.open("https://example.com")
        
        form = self.browser.Form.find("tab:1", form_type="login")
        
        assert form.id == "form:1"
        assert form.form_type == "login"
    
    def test_form_fill(self):
        """browser.Form.fill populates form fields."""
        self.browser.Tab.open("https://example.com")
        form = self.browser.Form.find("tab:1", form_type="login")
        
        self.browser.Form.fill("form:1", {"email": "test@example.com"})
        
        assert form._data["filled"]["email"] == "test@example.com"
    
    def test_form_clear(self):
        """browser.Form.clear empties form fields."""
        self.browser.Tab.open("https://example.com")
        form = self.browser.Form.find("tab:1", form_type="login")
        self.browser.Form.fill("form:1", {"email": "test@example.com"})
        
        self.browser.Form.clear("form:1")
        
        assert form._data["filled"] == {}
    
    def test_form_submit(self):
        """browser.Form.submit returns result."""
        self.browser.Tab.open("https://example.com")
        self.browser.Form.find("tab:1", form_type="login")
        
        result = self.browser.Form.submit("form:1")
        
        assert result["submitted"] is True
    
    def test_workspace_create(self):
        """browser.Workspace.create makes a workspace."""
        ws = self.browser.Workspace.create("work")
        
        assert ws.id == "workspace:1"
        assert ws.name == "work"
    
    def test_workspace_list(self):
        """browser.Workspace.list returns all workspaces."""
        self.browser.Workspace.create("work")
        self.browser.Workspace.create("personal")
        
        workspaces = self.browser.Workspace.list()
        
        assert len(workspaces) == 2
    
    def test_human_approve_defaults_false(self):
        """browser.human.approve returns False by default."""
        result = self.browser.human.approve("Submit form?")
        
        assert result is False
    
    def test_human_approve_auto_mode(self):
        """browser.human.approve respects auto_approve."""
        self.browser.human.set_auto_approve(True)
        
        result = self.browser.human.approve("Submit form?")
        
        assert result is True
    
    def test_transaction_context_manager(self):
        """browser.transaction() provides context manager."""
        with self.browser.transaction() as tx:
            assert tx.is_active
            tx.commit()


class TestEndToEndWorkflow:
    """Tests for complete agent workflows."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.audit = AuditLog()
        self.caps = CapabilityBroker(audit_log=self.audit)
        self.objects = ObjectManager(audit_log=self.audit)
        self.transactions = TransactionCoordinator(self.objects, self.audit)
        self.runtime = AgentRuntime(
            caps=self.caps,
            objects=self.objects,
            audit=self.audit,
            transactions=self.transactions,
        )
        
        # Grant typical agent capabilities
        self.caps.grant("agent:default", "tab.*", "*")
        self.caps.grant("agent:default", "form.*", "*")
        self.caps.grant("agent:default", "workspace.*", "*")
    
    def test_open_tab_extract_workflow(self):
        """Workflow A: open docs page → extract → verify."""
        code = """
# Open documentation page
tab = browser.Tab.open('https://docs.example.com')
tab.wait_for('interactive')

# Extract content
content = browser.Tab.extract(tab.id, 'readable')

# Verify extraction worked
assert 'docs.example.com' in content['url']
print(f"Extracted content from {content['url']}")
"""
        result = self.runtime.execute(code)
        assert result.state == ExecutionState.COMPLETED
    
    def test_login_form_rollback_workflow(self):
        """Workflow B: find form → fill → rollback."""
        code = """
# Open login page
tab = browser.Tab.open('https://example.com/login')

# Start transaction
with browser.transaction() as tx:
    # Find and fill form
    form = browser.Form.find(tab.id, form_type='login')
    tx.checkpoint('before-fill')
    
    browser.Form.fill(form.id, {'email': 'test@example.com'})
    
    # Rollback instead of submit
    tx.rollback('before-fill')
    tx.commit()

print("Form fill rolled back successfully")
"""
        result = self.runtime.execute(code)
        assert result.state == ExecutionState.COMPLETED
        
        # Verify form was cleared
        form = self.objects.get("form:1")
        assert form._data["filled"] == {}
    
    def test_audit_trail_complete(self):
        """All operations are logged to audit trail."""
        code = """
tab = browser.Tab.open('https://example.com')
browser.Tab.navigate(tab.id, 'https://new-url.com')
"""
        self.runtime.execute(code)
        
        entries = self.audit.query(principal="agent:default")
        ops = [e.op for e in entries]
        
        assert "tab.open" in ops
        assert "tab.navigate" in ops
