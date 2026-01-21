"""Tests for the Object Manager."""

import pytest
from kernel.objects import ObjectManager, ObjectType, Tab, Form, Workspace, ManagedObject


class TestObjectManager:
    """Tests for object creation, retrieval, and lifecycle."""
    
    def test_create_tab_with_stable_id(self):
        """Create a tab and verify stable ID format."""
        mgr = ObjectManager()
        
        tab = mgr.create(ObjectType.TAB, url="https://example.com")
        
        assert tab.id == "tab:1"
        assert isinstance(tab, Tab)
        assert tab.url == "https://example.com"
    
    def test_sequential_ids(self):
        """IDs are sequential within a type."""
        mgr = ObjectManager()
        
        tab1 = mgr.create(ObjectType.TAB, url="https://a.com")
        tab2 = mgr.create(ObjectType.TAB, url="https://b.com")
        form1 = mgr.create(ObjectType.FORM, tab_id="tab:1", form_type="login")
        
        assert tab1.id == "tab:1"
        assert tab2.id == "tab:2"
        assert form1.id == "form:1"
    
    def test_create_with_string_type(self):
        """Create using string type name."""
        mgr = ObjectManager()
        
        tab = mgr.create("tab", url="https://example.com")
        
        assert tab.id == "tab:1"
        assert tab.type == ObjectType.TAB
    
    def test_get_by_id(self):
        """Get an object by its stable ID."""
        mgr = ObjectManager()
        tab = mgr.create(ObjectType.TAB, url="https://example.com")
        
        retrieved = mgr.get("tab:1")
        
        assert retrieved is tab
    
    def test_get_nonexistent_returns_none(self):
        """Get returns None for nonexistent ID."""
        mgr = ObjectManager()
        
        assert mgr.get("tab:999") is None
    
    def test_require_raises_for_nonexistent(self):
        """require() raises KeyError for nonexistent ID."""
        mgr = ObjectManager()
        
        with pytest.raises(KeyError):
            mgr.require("tab:999")
    
    def test_delete_object(self):
        """Delete an object by ID."""
        mgr = ObjectManager()
        mgr.create(ObjectType.TAB, url="https://example.com")
        
        result = mgr.delete("tab:1")
        
        assert result is True
        assert mgr.get("tab:1") is None
    
    def test_delete_nonexistent(self):
        """Delete returns False for nonexistent ID."""
        mgr = ObjectManager()
        
        result = mgr.delete("tab:999")
        assert result is False
    
    def test_list_by_type(self):
        """List all objects of a type."""
        mgr = ObjectManager()
        mgr.create(ObjectType.TAB, url="https://a.com")
        mgr.create(ObjectType.TAB, url="https://b.com")
        mgr.create(ObjectType.FORM, tab_id="tab:1", form_type="login")
        
        tabs = mgr.list_by_type(ObjectType.TAB)
        
        assert len(tabs) == 2
        assert all(t.type == ObjectType.TAB for t in tabs)
    
    def test_query_with_filters(self):
        """Query objects with data filters."""
        mgr = ObjectManager()
        mgr.create(ObjectType.TAB, url="https://a.com", title="A")
        mgr.create(ObjectType.TAB, url="https://b.com", title="B")
        
        results = mgr.query(obj_type=ObjectType.TAB, url="https://a.com")
        
        assert len(results) == 1
        assert results[0].url == "https://a.com"


class TestTab:
    """Tests for Tab object."""
    
    def test_tab_properties(self):
        """Tab has url, title, load_state properties."""
        mgr = ObjectManager()
        tab = mgr.create(ObjectType.TAB, url="https://example.com", title="Example")
        
        assert tab.url == "https://example.com"
        assert tab.title == "Example"
        assert tab.load_state == "idle"
    
    def test_tab_navigate(self):
        """Tab.navigate updates URL and load state."""
        mgr = ObjectManager()
        tab = mgr.create(ObjectType.TAB, url="https://example.com")
        
        tab.navigate("https://new-url.com")
        
        assert tab.url == "https://new-url.com"
        assert tab.load_state == "loading"
    
    def test_tab_wait_for(self):
        """Tab.wait_for updates load state."""
        mgr = ObjectManager()
        tab = mgr.create(ObjectType.TAB, url="https://example.com")
        
        tab.wait_for("interactive")
        
        assert tab.load_state == "interactive"


class TestForm:
    """Tests for Form object."""
    
    def test_form_fill(self):
        """Form.fill stores values."""
        mgr = ObjectManager()
        form = mgr.create(ObjectType.FORM, tab_id="tab:1", form_type="login")
        
        form.fill({"email": "test@example.com", "password": "secret"})
        
        assert form._data["filled"]["email"] == "test@example.com"
        assert form._data["filled"]["password"] == "secret"
    
    def test_form_clear(self):
        """Form.clear removes filled values."""
        mgr = ObjectManager()
        form = mgr.create(ObjectType.FORM, tab_id="tab:1", form_type="login")
        form.fill({"email": "test@example.com"})
        
        form.clear()
        
        assert form._data["filled"] == {}


class TestWorkspace:
    """Tests for Workspace object."""
    
    def test_workspace_add_tab(self):
        """Workspace.add_tab tracks tabs."""
        mgr = ObjectManager()
        ws = mgr.create(ObjectType.WORKSPACE, name="work")
        
        ws.add_tab("tab:1")
        ws.add_tab("tab:2")
        
        assert ws.tabs == ["tab:1", "tab:2"]
    
    def test_workspace_remove_tab(self):
        """Workspace.remove_tab removes a tab."""
        mgr = ObjectManager()
        ws = mgr.create(ObjectType.WORKSPACE, name="work")
        ws.add_tab("tab:1")
        ws.add_tab("tab:2")
        
        ws.remove_tab("tab:1")
        
        assert ws.tabs == ["tab:2"]
    
    def test_workspace_no_duplicate_tabs(self):
        """Adding same tab twice doesn't duplicate."""
        mgr = ObjectManager()
        ws = mgr.create(ObjectType.WORKSPACE, name="work")
        
        ws.add_tab("tab:1")
        ws.add_tab("tab:1")
        
        assert ws.tabs == ["tab:1"]


class TestSnapshot:
    """Tests for object snapshots (for transactions)."""
    
    def test_snapshot_captures_state(self):
        """snapshot() captures current object state."""
        mgr = ObjectManager()
        tab = mgr.create(ObjectType.TAB, url="https://example.com")
        
        snapshot = tab.snapshot()
        
        assert snapshot.id == "tab:1"
        assert snapshot.type == ObjectType.TAB
        assert snapshot.data["url"] == "https://example.com"
    
    def test_restore_from_snapshot(self):
        """restore() restores object state from snapshot."""
        mgr = ObjectManager()
        tab = mgr.create(ObjectType.TAB, url="https://example.com")
        
        snapshot = tab.snapshot()
        tab.navigate("https://changed.com")
        assert tab.url == "https://changed.com"
        
        tab.restore(snapshot)
        assert tab.url == "https://example.com"
    
    def test_snapshot_all_objects(self):
        """ObjectManager.snapshot_all captures all objects."""
        mgr = ObjectManager()
        mgr.create(ObjectType.TAB, url="https://a.com")
        mgr.create(ObjectType.TAB, url="https://b.com")
        
        snapshot = mgr.snapshot_all()
        
        assert "tab:1" in snapshot
        assert "tab:2" in snapshot
    
    def test_restore_all_objects(self):
        """ObjectManager.restore_snapshot restores all objects."""
        mgr = ObjectManager()
        tab1 = mgr.create(ObjectType.TAB, url="https://a.com")
        tab2 = mgr.create(ObjectType.TAB, url="https://b.com")
        
        snapshot = mgr.snapshot_all()
        
        tab1.navigate("https://changed-a.com")
        tab2.navigate("https://changed-b.com")
        
        mgr.restore_snapshot(snapshot)
        
        assert tab1.url == "https://a.com"
        assert tab2.url == "https://b.com"
