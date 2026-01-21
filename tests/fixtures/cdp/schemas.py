"""CDP Message Schemas - Frozen contract between kernel and renderer.

These schemas are the TRUTH. If Chromium sends different shapes,
we adapt Chromium's output, not these schemas.

Based on Chrome DevTools Protocol: https://chromedevtools.github.io/devtools-protocol/
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional
import json


class CDPMethod(Enum):
    """CDP method names we handle."""
    # Page domain
    PAGE_NAVIGATE = "Page.navigate"
    PAGE_LOAD_EVENT_FIRED = "Page.loadEventFired"
    PAGE_FRAME_NAVIGATED = "Page.frameNavigated"
    PAGE_FRAME_STOPPED_LOADING = "Page.frameStoppedLoading"
    
    # DOM domain
    DOM_GET_DOCUMENT = "DOM.getDocument"
    DOM_QUERY_SELECTOR = "DOM.querySelector"
    DOM_QUERY_SELECTOR_ALL = "DOM.querySelectorAll"
    DOM_GET_OUTER_HTML = "DOM.getOuterHTML"
    
    # Runtime domain
    RUNTIME_EVALUATE = "Runtime.evaluate"
    RUNTIME_CALL_FUNCTION_ON = "Runtime.callFunctionOn"
    
    # Input domain
    INPUT_DISPATCH_KEY_EVENT = "Input.dispatchKeyEvent"
    INPUT_DISPATCH_MOUSE_EVENT = "Input.dispatchMouseEvent"
    
    # Target domain
    TARGET_CREATE_TARGET = "Target.createTarget"
    TARGET_CLOSE_TARGET = "Target.closeTarget"
    TARGET_GET_TARGETS = "Target.getTargets"
    TARGET_ATTACH_TO_TARGET = "Target.attachToTarget"


# ============================================================================
# Request/Response base types
# ============================================================================

@dataclass
class CDPRequest:
    """Base CDP request message."""
    id: int
    method: str
    params: dict = field(default_factory=dict)
    
    def to_json(self) -> str:
        return json.dumps({"id": self.id, "method": self.method, "params": self.params})
    
    @classmethod
    def from_json(cls, data: str) -> "CDPRequest":
        d = json.loads(data)
        return cls(id=d["id"], method=d["method"], params=d.get("params", {}))


@dataclass
class CDPResponse:
    """Base CDP response message."""
    id: int
    result: dict = field(default_factory=dict)
    error: Optional[dict] = None
    
    def to_json(self) -> str:
        d = {"id": self.id}
        if self.error:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return json.dumps(d)
    
    @classmethod
    def from_json(cls, data: str) -> "CDPResponse":
        d = json.loads(data)
        return cls(id=d["id"], result=d.get("result", {}), error=d.get("error"))


@dataclass
class CDPEvent:
    """Base CDP event message (no id, server-initiated)."""
    method: str
    params: dict = field(default_factory=dict)
    
    def to_json(self) -> str:
        return json.dumps({"method": self.method, "params": self.params})
    
    @classmethod
    def from_json(cls, data: str) -> "CDPEvent":
        d = json.loads(data)
        return cls(method=d["method"], params=d.get("params", {}))


# ============================================================================
# Page domain schemas
# ============================================================================

@dataclass
class PageNavigateParams:
    """Parameters for Page.navigate."""
    url: str
    referrer: Optional[str] = None
    transitionType: Optional[str] = None  # "link", "typed", "address_bar", etc.
    frameId: Optional[str] = None


@dataclass
class PageNavigateResult:
    """Result of Page.navigate."""
    frameId: str
    loaderId: Optional[str] = None
    errorText: Optional[str] = None


@dataclass
class FrameNavigatedParams:
    """Parameters for Page.frameNavigated event."""
    frame: dict  # Frame object
    type: str  # "Navigation", "BackForwardCacheRestore", etc.


@dataclass
class Frame:
    """CDP Frame object."""
    id: str
    parentId: Optional[str] = None
    loaderId: str = ""
    name: str = ""
    url: str = ""
    urlFragment: Optional[str] = None
    domainAndRegistry: str = ""
    securityOrigin: str = ""
    mimeType: str = "text/html"
    secureContextType: str = "Secure"
    crossOriginIsolatedContextType: str = "Isolated"
    gatedAPIFeatures: list = field(default_factory=list)


# ============================================================================
# DOM domain schemas
# ============================================================================

@dataclass
class DOMNode:
    """CDP DOM Node."""
    nodeId: int
    parentId: Optional[int] = None
    backendNodeId: int = 0
    nodeType: int = 1  # 1=ELEMENT, 3=TEXT, 9=DOCUMENT
    nodeName: str = ""
    localName: str = ""
    nodeValue: str = ""
    childNodeCount: int = 0
    children: list = field(default_factory=list)
    attributes: list = field(default_factory=list)  # ["name", "value", ...]
    documentURL: Optional[str] = None
    baseURL: Optional[str] = None
    contentDocument: Optional[dict] = None
    frameId: Optional[str] = None


@dataclass 
class GetDocumentResult:
    """Result of DOM.getDocument."""
    root: dict  # DOMNode


@dataclass
class QuerySelectorResult:
    """Result of DOM.querySelector."""
    nodeId: int


# ============================================================================
# Target domain schemas
# ============================================================================

@dataclass
class TargetInfo:
    """CDP TargetInfo object."""
    targetId: str
    type: str  # "page", "background_page", "service_worker", etc.
    title: str = ""
    url: str = ""
    attached: bool = False
    canAccessOpener: bool = False
    browserContextId: Optional[str] = None


@dataclass
class CreateTargetParams:
    """Parameters for Target.createTarget."""
    url: str
    width: Optional[int] = None
    height: Optional[int] = None
    browserContextId: Optional[str] = None
    enableBeginFrameControl: bool = False
    newWindow: bool = False
    background: bool = False


@dataclass
class CreateTargetResult:
    """Result of Target.createTarget."""
    targetId: str


@dataclass
class CloseTargetParams:
    """Parameters for Target.closeTarget."""
    targetId: str


@dataclass
class CloseTargetResult:
    """Result of Target.closeTarget."""
    success: bool


# ============================================================================
# Form-related schemas (custom, derived from DOM inspection)
# ============================================================================

@dataclass
class FormField:
    """Extracted form field."""
    name: str
    type: str  # "text", "email", "password", "hidden", etc.
    value: str = ""
    required: bool = False
    nodeId: Optional[int] = None


@dataclass
class ExtractedForm:
    """Extracted form data."""
    id: str  # Kernel-assigned ID
    action: str
    method: str
    formType: str  # "login", "search", "contact", "unknown"
    fields: list[FormField] = field(default_factory=list)
    nodeId: Optional[int] = None


# ============================================================================
# Kernel ↔ Renderer IPC messages (our protocol, built on CDP concepts)
# ============================================================================

class KernelMessageType(Enum):
    """Message types in kernel↔renderer IPC."""
    # Requests (kernel → renderer)
    NAVIGATE = "navigate"
    EXTRACT_CONTENT = "extract_content"
    FIND_FORM = "find_form"
    FILL_FORM = "fill_form"
    SUBMIT_FORM = "submit_form"
    CLOSE_TAB = "close_tab"
    
    # Responses (renderer → kernel)
    NAVIGATE_RESULT = "navigate_result"
    EXTRACT_RESULT = "extract_result"
    FORM_FOUND = "form_found"
    FILL_RESULT = "fill_result"
    SUBMIT_RESULT = "submit_result"
    
    # Events (renderer → kernel, unsolicited)
    TAB_UPDATED = "tab_updated"
    LOAD_STATE_CHANGED = "load_state_changed"
    FORM_DETECTED = "form_detected"
    ERROR = "error"


@dataclass
class KernelMessage:
    """Base message in kernel↔renderer IPC."""
    type: str
    tab_id: str
    request_id: Optional[int] = None
    payload: dict = field(default_factory=dict)
    timestamp: float = 0.0
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, data: str) -> "KernelMessage":
        d = json.loads(data)
        # Filter to known fields only (ignore extra fields)
        known_fields = {"type", "tab_id", "request_id", "payload", "timestamp"}
        filtered = {k: v for k, v in d.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class NavigateRequest(KernelMessage):
    """Navigate request."""
    def __init__(self, tab_id: str, url: str, request_id: int):
        super().__init__(
            type=KernelMessageType.NAVIGATE.value,
            tab_id=tab_id,
            request_id=request_id,
            payload={"url": url},
        )


@dataclass
class NavigateResult(KernelMessage):
    """Navigate response."""
    def __init__(self, tab_id: str, request_id: int, success: bool, url: str, title: str, error: str = ""):
        super().__init__(
            type=KernelMessageType.NAVIGATE_RESULT.value,
            tab_id=tab_id,
            request_id=request_id,
            payload={
                "success": success,
                "url": url,
                "title": title,
                "error": error,
            },
        )


@dataclass
class TabUpdatedEvent(KernelMessage):
    """Tab state update event."""
    def __init__(self, tab_id: str, url: str, title: str, load_state: str):
        super().__init__(
            type=KernelMessageType.TAB_UPDATED.value,
            tab_id=tab_id,
            payload={
                "url": url,
                "title": title,
                "load_state": load_state,
            },
        )


# ============================================================================
# Schema validation
# ============================================================================

def validate_cdp_response(response: CDPResponse, expected_fields: list[str]) -> list[str]:
    """Validate a CDP response has expected fields.
    
    Returns list of validation errors (empty if valid).
    """
    errors = []
    if response.error:
        return []  # Error responses don't need field validation
    
    for field_name in expected_fields:
        if field_name not in response.result:
            errors.append(f"Missing field: {field_name}")
    
    return errors


def validate_kernel_message(msg: KernelMessage, expected_payload: list[str]) -> list[str]:
    """Validate a kernel message has expected payload fields."""
    errors = []
    for field_name in expected_payload:
        if field_name not in msg.payload:
            errors.append(f"Missing payload field: {field_name}")
    return errors
