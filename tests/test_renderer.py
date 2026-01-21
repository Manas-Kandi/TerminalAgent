"""Tests for the Mock Renderer."""

import pytest
from kernel.objects import ObjectManager, ObjectType, Tab
from kernel.audit import AuditLog
from kernel.renderer.mock import MockRenderer, MockPage, MockForm, MockSiteRegistry


class TestMockForm:
    """Tests for mock form creation."""
    
    def test_login_form(self):
        """Login form has email and password fields."""
        form = MockForm.login_form("form:1")
        assert form.form_type == "login"
        assert "email" in form.fields
        assert "password" in form.fields
        assert form.fields["password"]["type"] == "password"
    
    def test_search_form(self):
        """Search form has query field."""
        form = MockForm.search_form("form:1")
        assert form.form_type == "search"
        assert "q" in form.fields
        assert form.method == "GET"
    
    def test_contact_form(self):
        """Contact form has name, email, message fields."""
        form = MockForm.contact_form("form:1")
        assert form.form_type == "contact"
        assert "name" in form.fields
        assert "email" in form.fields
        assert "message" in form.fields


class TestMockPage:
    """Tests for mock page extraction."""
    
    def test_extract_readable(self):
        """extract_readable returns content and metadata."""
        page = MockPage(
            url="https://example.com/",
            title="Example",
            content="Hello world this is content",
        )
        result = page.extract_readable()
        
        assert result["url"] == "https://example.com/"
        assert result["title"] == "Example"
        assert result["word_count"] == 5
    
    def test_extract_forms(self):
        """extract_forms returns form metadata."""
        form = MockForm.login_form("form:1")
        page = MockPage(
            url="https://example.com/login",
            title="Login",
            content="Please log in",
            forms=[form],
        )
        
        result = page.extract_forms()
        assert len(result) == 1
        assert result[0]["type"] == "login"
        assert "email" in result[0]["fields"]
    
    def test_extract_links(self):
        """extract_links returns link list."""
        page = MockPage(
            url="https://example.com/",
            title="Example",
            content="Content",
            links=[
                {"text": "About", "href": "/about"},
                {"text": "Contact", "href": "/contact"},
            ],
        )
        
        result = page.extract_links()
        assert len(result) == 2
        assert result[0]["text"] == "About"


class TestMockSiteRegistry:
    """Tests for mock site registry."""
    
    def test_default_sites_registered(self):
        """Default sites are available."""
        registry = MockSiteRegistry()
        
        page = registry.get_page("https://example.com/")
        assert page is not None
        assert page.title == "Example Domain"
    
    def test_login_page_available(self):
        """Login page has login form."""
        registry = MockSiteRegistry()
        
        page = registry.get_page("https://example.com/login")
        assert page is not None
        assert len(page.forms) == 1
        assert page.forms[0].form_type == "login"
    
    def test_404_for_unknown_page(self):
        """generate_404 creates 404 page."""
        registry = MockSiteRegistry()
        
        page = registry.generate_404("https://unknown.com/missing")
        assert "404" in page.title
        assert "not found" in page.content.lower()
    
    def test_register_custom_page(self):
        """Can register custom pages."""
        registry = MockSiteRegistry()
        
        custom = MockPage(
            url="https://custom.site.com/page",
            title="Custom Page",
            content="Custom content",
        )
        registry.register_page(custom)
        
        retrieved = registry.get_page("https://custom.site.com/page")
        assert retrieved.title == "Custom Page"


class TestMockRenderer:
    """Tests for mock renderer operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.audit = AuditLog()
        self.objects = ObjectManager(audit_log=self.audit)
        self.renderer = MockRenderer(self.objects, self.audit)
    
    def test_navigate_success(self):
        """Navigation updates tab state."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        
        result = self.renderer.navigate(tab.id, "https://example.com/")
        
        assert result["success"] is True
        assert result["title"] == "Example Domain"
        assert tab.url == "https://example.com/"
        assert tab._data["load_state"] == "complete"
    
    def test_navigate_404(self):
        """Navigation to unknown page returns 404."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        
        result = self.renderer.navigate(tab.id, "https://unknown.example.com/missing")
        
        assert result["success"] is True
        assert "404" in result["title"]
    
    def test_navigate_nonexistent_tab(self):
        """Navigation fails for nonexistent tab."""
        result = self.renderer.navigate("tab:999", "https://example.com/")
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()
    
    def test_wait_for_updates_state(self):
        """wait_for updates load state."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        self.renderer.navigate(tab.id, "https://example.com/")
        
        result = self.renderer.wait_for(tab.id, "interactive")
        
        assert result is True
        assert tab._data["load_state"] == "interactive"
    
    def test_extract_readable(self):
        """Extract readable content from page."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        self.renderer.navigate(tab.id, "https://docs.example.com/")
        
        result = self.renderer.extract(tab.id, "readable")
        
        assert result["title"] == "Documentation"
        assert "Installation" in result["content"]
    
    def test_extract_forms(self):
        """Extract forms from login page."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        self.renderer.navigate(tab.id, "https://example.com/login")
        
        result = self.renderer.extract(tab.id, "forms")
        
        assert len(result["forms"]) == 1
        assert result["forms"][0]["type"] == "login"
    
    def test_find_form(self):
        """find_form creates Form object."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        self.renderer.navigate(tab.id, "https://example.com/login")
        
        form_id = self.renderer.find_form(tab.id, "login")
        
        assert form_id is not None
        assert form_id.startswith("form:")
        
        form = self.objects.get(form_id)
        assert form is not None
        assert form._data["form_type"] == "login"
    
    def test_fill_form(self):
        """fill_form updates form state."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        self.renderer.navigate(tab.id, "https://example.com/login")
        form_id = self.renderer.find_form(tab.id, "login")
        
        result = self.renderer.fill_form(form_id, {
            "email": "test@example.com",
            "password": "secret",
        })
        
        assert result["success"] is True
        form = self.objects.get(form_id)
        assert form._data["filled"]["email"] == "test@example.com"
    
    def test_clear_form(self):
        """clear_form empties form state."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        self.renderer.navigate(tab.id, "https://example.com/login")
        form_id = self.renderer.find_form(tab.id, "login")
        self.renderer.fill_form(form_id, {"email": "test@example.com"})
        
        result = self.renderer.clear_form(form_id)
        
        assert result["success"] is True
        form = self.objects.get(form_id)
        assert form._data["filled"] == {}
    
    def test_submit_form(self):
        """submit_form returns success."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        self.renderer.navigate(tab.id, "https://example.com/login")
        form_id = self.renderer.find_form(tab.id, "login")
        self.renderer.fill_form(form_id, {"email": "test@example.com"})
        
        result = self.renderer.submit_form(form_id)
        
        assert result["success"] is True
        assert result["submitted"] is True
    
    def test_submit_callback(self):
        """submit_form calls callback if set."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        self.renderer.navigate(tab.id, "https://example.com/login")
        form_id = self.renderer.find_form(tab.id, "login")
        self.renderer.fill_form(form_id, {"email": "test@example.com"})
        
        callback_called = {"called": False, "data": None}
        
        def callback(fid, data):
            callback_called["called"] = True
            callback_called["data"] = data
            return {"success": True, "custom": "response"}
        
        self.renderer.set_submit_callback(callback)
        result = self.renderer.submit_form(form_id)
        
        assert callback_called["called"]
        assert callback_called["data"]["email"] == "test@example.com"
        assert result["custom"] == "response"


class TestRendererKernelIntegration:
    """Integration tests for renderer↔kernel boundary."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.audit = AuditLog()
        self.objects = ObjectManager(audit_log=self.audit)
        self.renderer = MockRenderer(self.objects, self.audit)
    
    def test_navigation_audit_trail(self):
        """Navigation is logged to audit."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        self.renderer.navigate(tab.id, "https://example.com/")
        
        entries = self.audit.query(op="renderer.*")
        assert any(e.op == "renderer.navigate" for e in entries)
    
    def test_form_operations_audit_trail(self):
        """Form operations are logged to audit."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        self.renderer.navigate(tab.id, "https://example.com/login")
        form_id = self.renderer.find_form(tab.id, "login")
        self.renderer.fill_form(form_id, {"email": "test@example.com"})
        self.renderer.submit_form(form_id)
        
        entries = self.audit.query(op="renderer.*")
        ops = [e.op for e in entries]
        
        assert "renderer.navigate" in ops
        assert "renderer.find_form" in ops
        assert "renderer.fill_form" in ops
        assert "renderer.submit_form" in ops
    
    def test_object_state_consistency(self):
        """Object state is consistent after renderer operations."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        
        self.renderer.navigate(tab.id, "https://example.com/login")
        form_id = self.renderer.find_form(tab.id, "login")
        self.renderer.fill_form(form_id, {"email": "test@example.com"})
        
        # Verify objects via ObjectManager queries
        tabs = self.objects.list_by_type(ObjectType.TAB)
        forms = self.objects.list_by_type(ObjectType.FORM)
        
        assert len(tabs) == 1
        assert tabs[0].url == "https://example.com/login"
        
        assert len(forms) == 1
        assert forms[0]._data["filled"]["email"] == "test@example.com"
    
    def test_snapshot_captures_renderer_state(self):
        """Snapshots capture renderer-driven state changes."""
        tab = self.objects.create(ObjectType.TAB, url="about:blank")
        
        # Take initial snapshot
        initial_snapshot = self.objects.snapshot_all()
        
        # Make changes via renderer
        self.renderer.navigate(tab.id, "https://example.com/login")
        form_id = self.renderer.find_form(tab.id, "login")
        self.renderer.fill_form(form_id, {"email": "changed@example.com"})
        
        # Restore to initial
        self.objects.restore_snapshot(initial_snapshot)
        
        # Tab should be back to about:blank
        assert tab.url == "about:blank"
        
        # Form object still exists but its filled state is restored
        # (Note: form was created after snapshot, so it won't be in snapshot)
