"""Tests for the Terminal UI."""

import pytest
from kernel.capabilities import CapabilityBroker, CapabilityRisk
from kernel.objects import ObjectManager, ObjectType
from kernel.audit import AuditLog
from kernel.transactions import TransactionCoordinator
from kernel.runtime import AgentRuntime
from kernel.ui.terminal import TerminalUI, CodeBuffer, RiskDisplay


class TestCodeBuffer:
    """Tests for code buffer management."""
    
    def test_code_buffer_creation(self):
        """CodeBuffer stores source code."""
        buf = CodeBuffer(source="print('hello')")
        assert buf.source == "print('hello')"
        assert buf.principal == "agent:interactive"
        assert buf.validated is False
    
    def test_code_buffer_with_principal(self):
        """CodeBuffer accepts custom principal."""
        buf = CodeBuffer(source="x = 1", principal="agent:custom")
        assert buf.principal == "agent:custom"


class TestRiskDisplay:
    """Tests for risk level display formatting."""
    
    def test_read_risk_green(self):
        """READ risk displays in green."""
        display = RiskDisplay.format(CapabilityRisk.READ)
        assert "READ" in display
    
    def test_stateful_risk_yellow(self):
        """STATEFUL risk displays in yellow."""
        display = RiskDisplay.format(CapabilityRisk.STATEFUL)
        assert "STATEFUL" in display
    
    def test_irreversible_risk_red(self):
        """IRREVERSIBLE risk displays in red."""
        display = RiskDisplay.format(CapabilityRisk.IRREVERSIBLE)
        assert "IRREVERSIBLE" in display


class TestTerminalUI:
    """Tests for Terminal UI commands."""
    
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
        self.ui = TerminalUI(
            caps=self.caps,
            objects=self.objects,
            audit=self.audit,
            transactions=self.transactions,
            runtime=self.runtime,
        )
    
    def test_analyze_required_caps_tab_open(self):
        """Analyzes browser.Tab.open() as stateful."""
        code = "tab = browser.Tab.open('https://example.com')"
        caps = self.ui._analyze_required_caps(code)
        
        assert len(caps) == 1
        assert caps[0]["operation"] == "tab.open"
        assert caps[0]["risk"] == CapabilityRisk.STATEFUL
    
    def test_analyze_required_caps_form_submit(self):
        """Analyzes browser.Form.submit() as irreversible."""
        code = "browser.Form.submit('form:1')"
        caps = self.ui._analyze_required_caps(code)
        
        assert len(caps) == 1
        assert caps[0]["operation"] == "form.submit"
        assert caps[0]["risk"] == CapabilityRisk.IRREVERSIBLE
    
    def test_analyze_required_caps_multiple(self):
        """Analyzes multiple API calls."""
        code = """
tab = browser.Tab.open('https://example.com')
form = browser.Form.find(tab.id, form_type='login')
browser.Form.fill(form.id, {'email': 'test@example.com'})
"""
        caps = self.ui._analyze_required_caps(code)
        
        ops = [c["operation"] for c in caps]
        assert "tab.open" in ops
        assert "form.find" in ops
        assert "form.fill" in ops
    
    def test_analyze_required_caps_syntax_error(self):
        """Returns empty list for invalid syntax."""
        code = "def broken("
        caps = self.ui._analyze_required_caps(code)
        assert caps == []
    
    def test_cmd_grant(self):
        """Grant command adds capabilities."""
        self.ui._code_buffer = CodeBuffer(source="x=1", principal="agent:test")
        self.ui._cmd_grant(["tab.*", "*", "READ"])
        
        assert self.caps.check("agent:test", "tab.read", "tab:1")
        assert self.caps.check("agent:test", "tab.open", "tab:99")
    
    def test_cmd_grant_with_risk(self):
        """Grant command respects risk level."""
        self.ui._code_buffer = CodeBuffer(source="x=1", principal="agent:test")
        self.ui._cmd_grant(["form.submit", "form:*", "IRREVERSIBLE"])
        
        caps = self.caps.list_capabilities("agent:test")
        assert len(caps) == 1
        assert caps[0].risk == CapabilityRisk.IRREVERSIBLE


class TestAuditAPI:
    """Tests for browser.Audit API."""
    
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
        
        # Grant audit.read capability
        self.caps.grant("agent:default", "audit.read", "*")
        self.caps.grant("agent:default", "tab.*", "*")
    
    def test_audit_query_via_code(self):
        """browser.Audit.query() works in agent code."""
        # First create some audit entries
        code1 = "tab = browser.Tab.open('https://example.com')"
        self.runtime.execute(code1, principal="agent:default")
        
        # Then query them
        code2 = """
entries = browser.Audit.query(limit=10)
__result__ = len(entries)
"""
        result = self.runtime.execute(code2, principal="agent:default")
        
        assert result.state.value == "completed"
    
    def test_audit_query_requires_capability(self):
        """browser.Audit.query() requires audit.read capability."""
        code = "entries = browser.Audit.query()"
        result = self.runtime.execute(code, principal="agent:no-audit-cap")
        
        assert result.state.value == "failed"
        assert "CapabilityDenied" in result.error_type
    
    def test_audit_count(self):
        """browser.Audit.count() returns entry count."""
        # Create some entries
        self.runtime.execute("browser.Tab.open('https://a.com')", principal="agent:default")
        self.runtime.execute("browser.Tab.open('https://b.com')", principal="agent:default")
        
        # Count via API
        browser_api = self.runtime.create_browser_api("agent:default")
        count = browser_api.Audit.count(op="tab.*")
        
        assert count >= 2
