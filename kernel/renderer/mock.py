"""Mock Renderer - Simulates web pages without Chromium.

This renderer serves hardcoded HTML responses and simulates state changes,
allowing validation of:
- Object model correctness
- Transaction checkpoint/rollback
- Audit trail completeness
- Capability enforcement

No actual network requests or DOM parsing - just enough simulation
to exercise the kernel's semantics.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from kernel.objects import ObjectManager, ObjectType, Tab, Form
from kernel.audit import AuditLog, Provenance


class LoadState(Enum):
    """Page load states."""
    IDLE = "idle"
    LOADING = "loading"
    INTERACTIVE = "interactive"
    COMPLETE = "complete"


@dataclass
class MockForm:
    """A simulated form on a page."""
    id: str
    form_type: str
    action: str
    method: str = "POST"
    fields: dict[str, dict] = field(default_factory=dict)
    
    @classmethod
    def login_form(cls, form_id: str) -> "MockForm":
        """Create a standard login form."""
        return cls(
            id=form_id,
            form_type="login",
            action="/login",
            fields={
                "email": {"type": "email", "required": True, "label": "Email"},
                "password": {"type": "password", "required": True, "label": "Password"},
            },
        )
    
    @classmethod
    def search_form(cls, form_id: str) -> "MockForm":
        """Create a standard search form."""
        return cls(
            id=form_id,
            form_type="search",
            action="/search",
            method="GET",
            fields={
                "q": {"type": "text", "required": True, "label": "Search"},
            },
        )
    
    @classmethod
    def contact_form(cls, form_id: str) -> "MockForm":
        """Create a contact form."""
        return cls(
            id=form_id,
            form_type="contact",
            action="/contact",
            fields={
                "name": {"type": "text", "required": True, "label": "Name"},
                "email": {"type": "email", "required": True, "label": "Email"},
                "message": {"type": "textarea", "required": True, "label": "Message"},
            },
        )


@dataclass
class MockPage:
    """A simulated web page."""
    url: str
    title: str
    content: str
    forms: list[MockForm] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    load_time_ms: float = 100.0
    
    def extract_readable(self) -> dict:
        """Extract readable content."""
        return {
            "type": "readable",
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "word_count": len(self.content.split()),
        }
    
    def extract_forms(self) -> list[dict]:
        """Extract form metadata."""
        return [
            {
                "id": f.id,
                "type": f.form_type,
                "action": f.action,
                "method": f.method,
                "fields": list(f.fields.keys()),
            }
            for f in self.forms
        ]
    
    def extract_links(self) -> list[dict]:
        """Extract links."""
        return self.links
    
    def extract_tables(self) -> list[dict]:
        """Extract tables."""
        return self.tables


class MockSiteRegistry:
    """Registry of mock sites with their pages."""
    
    def __init__(self):
        self._sites: dict[str, dict[str, MockPage]] = {}
        self._register_default_sites()
    
    def _register_default_sites(self) -> None:
        """Register default mock sites for testing."""
        
        # Example.com - basic site
        self.register_page(MockPage(
            url="https://example.com/",
            title="Example Domain",
            content="This domain is for use in illustrative examples in documents.",
            links=[
                {"text": "More information...", "href": "https://www.iana.org/domains/example"},
            ],
        ))
        
        # Example.com login page
        login_form = MockForm.login_form("form:login")
        self.register_page(MockPage(
            url="https://example.com/login",
            title="Login - Example",
            content="Please log in to continue.",
            forms=[login_form],
        ))
        
        # Example.com dashboard (post-login)
        self.register_page(MockPage(
            url="https://example.com/dashboard",
            title="Dashboard - Example",
            content="Welcome back! Here's your dashboard.",
            links=[
                {"text": "Settings", "href": "/settings"},
                {"text": "Profile", "href": "/profile"},
                {"text": "Logout", "href": "/logout"},
            ],
        ))
        
        # Search engine
        search_form = MockForm.search_form("form:search")
        self.register_page(MockPage(
            url="https://search.example.com/",
            title="Example Search",
            content="Search the web.",
            forms=[search_form],
        ))
        
        # Search results
        self.register_page(MockPage(
            url="https://search.example.com/results",
            title="Search Results - Example Search",
            content="Results for your query.",
            links=[
                {"text": "Result 1", "href": "https://result1.example.com"},
                {"text": "Result 2", "href": "https://result2.example.com"},
                {"text": "Result 3", "href": "https://result3.example.com"},
            ],
        ))
        
        # Documentation site
        self.register_page(MockPage(
            url="https://docs.example.com/",
            title="Documentation",
            content="""
# Getting Started

Welcome to the documentation.

## Installation

Run `pip install example` to get started.

## Usage

```python
import example
example.do_thing()
```

## API Reference

See the API docs for more details.
            """.strip(),
            links=[
                {"text": "Installation", "href": "/installation"},
                {"text": "API Reference", "href": "/api"},
                {"text": "Examples", "href": "/examples"},
            ],
        ))
        
        # Contact page
        contact_form = MockForm.contact_form("form:contact")
        self.register_page(MockPage(
            url="https://example.com/contact",
            title="Contact Us - Example",
            content="Get in touch with our team.",
            forms=[contact_form],
        ))
        
        # Data table page
        self.register_page(MockPage(
            url="https://data.example.com/",
            title="Data Table",
            content="Sample data table.",
            tables=[
                {
                    "headers": ["Name", "Email", "Status"],
                    "rows": [
                        ["Alice", "alice@example.com", "Active"],
                        ["Bob", "bob@example.com", "Pending"],
                        ["Charlie", "charlie@example.com", "Active"],
                    ],
                },
            ],
        ))
    
    def register_page(self, page: MockPage) -> None:
        """Register a mock page."""
        parsed = urlparse(page.url)
        host = parsed.netloc
        path = parsed.path or "/"
        
        if host not in self._sites:
            self._sites[host] = {}
        self._sites[host][path] = page
    
    def get_page(self, url: str) -> Optional[MockPage]:
        """Get a mock page by URL."""
        parsed = urlparse(url)
        host = parsed.netloc
        path = parsed.path or "/"
        
        site = self._sites.get(host, {})
        return site.get(path)
    
    def generate_404(self, url: str) -> MockPage:
        """Generate a 404 page."""
        return MockPage(
            url=url,
            title="404 Not Found",
            content=f"The page at {url} was not found.",
            load_time_ms=50.0,
        )


class MockRenderer:
    """Mock renderer that simulates web page loading and interaction.
    
    Integrates with the kernel's ObjectManager to update Tab and Form
    objects as navigation and form interactions occur.
    """
    
    def __init__(
        self,
        objects: ObjectManager,
        audit: Optional[AuditLog] = None,
    ):
        self._objects = objects
        self._audit = audit
        self._registry = MockSiteRegistry()
        self._tab_pages: dict[str, MockPage] = {}  # tab_id -> current page
        self._form_data: dict[str, dict] = {}  # form_id -> filled data
        self._submit_callback: Optional[Callable[[str, dict], dict]] = None
    
    def set_submit_callback(self, callback: Callable[[str, dict], dict]) -> None:
        """Set a callback for form submissions (for testing)."""
        self._submit_callback = callback
    
    def register_page(self, page: MockPage) -> None:
        """Register a custom mock page."""
        self._registry.register_page(page)
    
    def navigate(self, tab_id: str, url: str) -> dict:
        """Navigate a tab to a URL.
        
        Returns:
            Navigation result with page info
        """
        tab = self._objects.get(tab_id)
        if not tab or not isinstance(tab, Tab):
            return {"success": False, "error": f"Tab not found: {tab_id}"}
        
        # Update tab state
        tab._data["url"] = url
        tab._data["load_state"] = LoadState.LOADING.value
        tab._updated_at = time.time()
        
        # Get mock page
        page = self._registry.get_page(url)
        if not page:
            page = self._registry.generate_404(url)
        
        # Simulate load time
        time.sleep(page.load_time_ms / 1000)
        
        # Update tab with page data
        tab._data["title"] = page.title
        tab._data["load_state"] = LoadState.COMPLETE.value
        tab._updated_at = time.time()
        
        # Store page reference
        self._tab_pages[tab_id] = page
        
        # Log navigation
        if self._audit:
            self._audit.log(
                op="renderer.navigate",
                principal="renderer",
                object=tab_id,
                args={"url": url, "title": page.title},
                result="success",
                provenance=Provenance.SYSTEM,
            )
        
        return {
            "success": True,
            "url": url,
            "title": page.title,
            "load_time_ms": page.load_time_ms,
        }
    
    def wait_for(self, tab_id: str, state: str = "interactive") -> bool:
        """Wait for tab to reach a load state.
        
        In mock renderer, this is instant since we don't have real loading.
        """
        tab = self._objects.get(tab_id)
        if not tab:
            return False
        
        # Mock: just set the state
        tab._data["load_state"] = state
        return True
    
    def extract(self, tab_id: str, extract_type: str = "readable") -> dict:
        """Extract content from a tab.
        
        Args:
            tab_id: Tab to extract from
            extract_type: One of 'readable', 'forms', 'links', 'tables'
            
        Returns:
            Extracted content
        """
        page = self._tab_pages.get(tab_id)
        if not page:
            return {"error": f"No page loaded for tab {tab_id}"}
        
        if extract_type == "readable":
            return page.extract_readable()
        elif extract_type == "forms":
            return {"forms": page.extract_forms()}
        elif extract_type == "links":
            return {"links": page.extract_links()}
        elif extract_type == "tables":
            return {"tables": page.extract_tables()}
        else:
            return {"error": f"Unknown extract type: {extract_type}"}
    
    def find_form(self, tab_id: str, form_type: str = "") -> Optional[str]:
        """Find a form on a page.
        
        Args:
            tab_id: Tab to search in
            form_type: Optional form type filter ('login', 'search', etc.)
            
        Returns:
            Form ID if found, None otherwise
        """
        page = self._tab_pages.get(tab_id)
        if not page:
            return None
        
        for mock_form in page.forms:
            if not form_type or mock_form.form_type == form_type:
                # Create a Form object in ObjectManager
                form = self._objects.create(
                    ObjectType.FORM,
                    tab_id=tab_id,
                    form_type=mock_form.form_type,
                )
                form._data["fields"] = mock_form.fields
                form._data["action"] = mock_form.action
                form._data["method"] = mock_form.method
                
                # Track filled data separately
                self._form_data[form.id] = {}
                
                if self._audit:
                    self._audit.log(
                        op="renderer.find_form",
                        principal="renderer",
                        object=form.id,
                        args={"tab_id": tab_id, "type": mock_form.form_type},
                        result="found",
                        provenance=Provenance.SYSTEM,
                    )
                
                return form.id
        
        return None
    
    def fill_form(self, form_id: str, values: dict[str, str]) -> dict:
        """Fill form fields.
        
        Args:
            form_id: Form to fill
            values: Field name → value mapping
            
        Returns:
            Fill result
        """
        form = self._objects.get(form_id)
        if not form or not isinstance(form, Form):
            return {"success": False, "error": f"Form not found: {form_id}"}
        
        # Store filled values
        if form_id not in self._form_data:
            self._form_data[form_id] = {}
        self._form_data[form_id].update(values)
        
        # Update form object
        form._data["filled"] = dict(self._form_data[form_id])
        form._updated_at = time.time()
        
        if self._audit:
            self._audit.log(
                op="renderer.fill_form",
                principal="renderer",
                object=form_id,
                args={"fields": list(values.keys())},
                result="success",
                provenance=Provenance.SYSTEM,
            )
        
        return {"success": True, "filled_fields": list(values.keys())}
    
    def clear_form(self, form_id: str) -> dict:
        """Clear form fields."""
        form = self._objects.get(form_id)
        if not form:
            return {"success": False, "error": f"Form not found: {form_id}"}
        
        self._form_data[form_id] = {}
        form._data["filled"] = {}
        form._updated_at = time.time()
        
        return {"success": True}
    
    def submit_form(self, form_id: str) -> dict:
        """Submit a form.
        
        This is an IRREVERSIBLE operation - it simulates sending
        data to an external server.
        
        Returns:
            Submission result
        """
        form = self._objects.get(form_id)
        if not form:
            return {"success": False, "error": f"Form not found: {form_id}"}
        
        filled = self._form_data.get(form_id, {})
        action = form._data.get("action", "/")
        method = form._data.get("method", "POST")
        
        if self._audit:
            self._audit.log(
                op="renderer.submit_form",
                principal="renderer",
                object=form_id,
                args={"action": action, "method": method, "field_count": len(filled)},
                result="submitted",
                provenance=Provenance.SYSTEM,
            )
        
        # Call submit callback if set (for testing)
        if self._submit_callback:
            return self._submit_callback(form_id, filled)
        
        # Default mock response
        return {
            "success": True,
            "submitted": True,
            "form_id": form_id,
            "action": action,
            "method": method,
            "response": {
                "status": 200,
                "body": "Form submitted successfully (mock)",
            },
        }
    
    def get_page_for_tab(self, tab_id: str) -> Optional[MockPage]:
        """Get the current page for a tab."""
        return self._tab_pages.get(tab_id)


class RendererBridge:
    """Bridges the BrowserAPI to the MockRenderer.
    
    This intercepts browser.Tab and browser.Form operations and
    routes them through the mock renderer for realistic simulation.
    """
    
    def __init__(self, renderer: MockRenderer, objects: ObjectManager):
        self._renderer = renderer
        self._objects = objects
    
    def on_tab_navigate(self, tab_id: str, url: str) -> dict:
        """Handle tab navigation."""
        return self._renderer.navigate(tab_id, url)
    
    def on_tab_wait_for(self, tab_id: str, state: str) -> bool:
        """Handle wait_for."""
        return self._renderer.wait_for(tab_id, state)
    
    def on_tab_extract(self, tab_id: str, extract_type: str) -> dict:
        """Handle content extraction."""
        return self._renderer.extract(tab_id, extract_type)
    
    def on_form_find(self, tab_id: str, form_type: str) -> Optional[str]:
        """Handle form finding."""
        return self._renderer.find_form(tab_id, form_type)
    
    def on_form_fill(self, form_id: str, values: dict) -> dict:
        """Handle form filling."""
        return self._renderer.fill_form(form_id, values)
    
    def on_form_clear(self, form_id: str) -> dict:
        """Handle form clearing."""
        return self._renderer.clear_form(form_id)
    
    def on_form_submit(self, form_id: str) -> dict:
        """Handle form submission."""
        return self._renderer.submit_form(form_id)
