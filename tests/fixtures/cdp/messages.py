"""CDP Message fixtures - Exact byte-compatible test data.

These are the CANONICAL messages. Mock renderer must emit these exactly.
"""

import json
from tests.fixtures.cdp.schemas import (
    CDPRequest, CDPResponse, CDPEvent, KernelMessage,
    Frame, DOMNode, TargetInfo, ExtractedForm, FormField,
)


# ============================================================================
# Page.navigate fixtures
# ============================================================================

PAGE_NAVIGATE_REQUEST = {
    "id": 1,
    "method": "Page.navigate",
    "params": {
        "url": "https://example.com/login",
    }
}

PAGE_NAVIGATE_RESPONSE_SUCCESS = {
    "id": 1,
    "result": {
        "frameId": "frame-main-1",
        "loaderId": "loader-123",
    }
}

PAGE_NAVIGATE_RESPONSE_ERROR = {
    "id": 1,
    "result": {
        "frameId": "frame-main-1",
        "errorText": "net::ERR_NAME_NOT_RESOLVED",
    }
}

# ============================================================================
# Page events fixtures
# ============================================================================

PAGE_FRAME_NAVIGATED_EVENT = {
    "method": "Page.frameNavigated",
    "params": {
        "frame": {
            "id": "frame-main-1",
            "loaderId": "loader-123",
            "url": "https://example.com/login",
            "domainAndRegistry": "example.com",
            "securityOrigin": "https://example.com",
            "mimeType": "text/html",
            "secureContextType": "Secure",
            "crossOriginIsolatedContextType": "Isolated",
            "gatedAPIFeatures": [],
        },
        "type": "Navigation",
    }
}

PAGE_LOAD_EVENT_FIRED = {
    "method": "Page.loadEventFired",
    "params": {
        "timestamp": 1234567890.123,
    }
}

# ============================================================================
# DOM fixtures
# ============================================================================

DOM_GET_DOCUMENT_RESPONSE = {
    "id": 2,
    "result": {
        "root": {
            "nodeId": 1,
            "backendNodeId": 1,
            "nodeType": 9,  # DOCUMENT
            "nodeName": "#document",
            "localName": "",
            "nodeValue": "",
            "childNodeCount": 1,
            "children": [
                {
                    "nodeId": 2,
                    "backendNodeId": 2,
                    "nodeType": 1,  # ELEMENT
                    "nodeName": "HTML",
                    "localName": "html",
                    "nodeValue": "",
                    "childNodeCount": 2,
                    "attributes": [],
                }
            ],
            "documentURL": "https://example.com/login",
            "baseURL": "https://example.com/login",
        }
    }
}

# ============================================================================
# Target fixtures
# ============================================================================

TARGET_CREATE_TARGET_REQUEST = {
    "id": 3,
    "method": "Target.createTarget",
    "params": {
        "url": "about:blank",
    }
}

TARGET_CREATE_TARGET_RESPONSE = {
    "id": 3,
    "result": {
        "targetId": "target-abc123",
    }
}

TARGET_CLOSE_TARGET_REQUEST = {
    "id": 4,
    "method": "Target.closeTarget",
    "params": {
        "targetId": "target-abc123",
    }
}

TARGET_CLOSE_TARGET_RESPONSE = {
    "id": 4,
    "result": {
        "success": True,
    }
}

TARGET_GET_TARGETS_RESPONSE = {
    "id": 5,
    "result": {
        "targetInfos": [
            {
                "targetId": "target-abc123",
                "type": "page",
                "title": "Example Login",
                "url": "https://example.com/login",
                "attached": True,
                "canAccessOpener": False,
            }
        ]
    }
}

# ============================================================================
# Kernel ↔ Renderer IPC fixtures
# ============================================================================

KERNEL_NAVIGATE_REQUEST = {
    "type": "navigate",
    "tab_id": "tab:1",
    "request_id": 1,
    "payload": {
        "url": "https://example.com/login",
    },
    "timestamp": 1234567890.0,
}

KERNEL_NAVIGATE_RESULT_SUCCESS = {
    "type": "navigate_result",
    "tab_id": "tab:1",
    "request_id": 1,
    "payload": {
        "success": True,
        "url": "https://example.com/login",
        "title": "Example Login",
        "error": "",
    },
    "timestamp": 1234567890.1,
}

KERNEL_NAVIGATE_RESULT_ERROR = {
    "type": "navigate_result",
    "tab_id": "tab:1",
    "request_id": 1,
    "payload": {
        "success": False,
        "url": "https://example.com/login",
        "title": "",
        "error": "net::ERR_NAME_NOT_RESOLVED",
    },
    "timestamp": 1234567890.1,
}

KERNEL_TAB_UPDATED_EVENT = {
    "type": "tab_updated",
    "tab_id": "tab:1",
    "request_id": None,
    "payload": {
        "url": "https://example.com/login",
        "title": "Example Login",
        "load_state": "complete",
    },
    "timestamp": 1234567890.2,
}

KERNEL_FORM_FOUND = {
    "type": "form_found",
    "tab_id": "tab:1",
    "request_id": 2,
    "payload": {
        "form_id": "form:1",
        "form_type": "login",
        "action": "/login",
        "method": "POST",
        "fields": [
            {"name": "email", "type": "email", "required": True},
            {"name": "password", "type": "password", "required": True},
        ],
    },
    "timestamp": 1234567890.3,
}

KERNEL_FILL_RESULT = {
    "type": "fill_result",
    "tab_id": "tab:1",
    "request_id": 3,
    "payload": {
        "success": True,
        "form_id": "form:1",
        "filled_fields": ["email", "password"],
    },
    "timestamp": 1234567890.4,
}

KERNEL_SUBMIT_RESULT = {
    "type": "submit_result",
    "tab_id": "tab:1",
    "request_id": 4,
    "payload": {
        "success": True,
        "form_id": "form:1",
        "response_status": 200,
        "redirect_url": "https://example.com/dashboard",
    },
    "timestamp": 1234567890.5,
}

# ============================================================================
# Malicious message fixtures (for security testing)
# ============================================================================

MALICIOUS_CLOSE_TARGET_SPOOF = {
    "id": 999,
    "method": "Target.closeTarget",
    "params": {
        "targetId": "target-kernel-process",  # Attempt to close kernel
    }
}

MALICIOUS_EVALUATE_SPOOF = {
    "id": 998,
    "method": "Runtime.evaluate",
    "params": {
        "expression": "process.exit(1)",  # Attempt to crash
    }
}

MALICIOUS_EXTRA_FIELDS = {
    "type": "navigate_result",
    "tab_id": "tab:1",
    "request_id": 1,
    "payload": {
        "success": True,
        "url": "https://example.com/",
        "title": "Example",
        "error": "",
        "__proto__": {"admin": True},  # Prototype pollution attempt
        "constructor": {"name": "evil"},
    },
    "timestamp": 1234567890.1,
}

MALICIOUS_WRONG_TYPE = {
    "type": "navigate_result",
    "tab_id": ["tab:1"],  # Should be string, not list
    "request_id": "not-an-int",  # Should be int
    "payload": "not-a-dict",  # Should be dict
    "timestamp": "not-a-float",
}


# ============================================================================
# Helper functions
# ============================================================================

def to_json_bytes(obj: dict) -> bytes:
    """Convert to JSON bytes for byte-compatible comparison."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')


def messages_byte_equal(a: dict, b: dict) -> bool:
    """Check if two messages are byte-equal when serialized."""
    return to_json_bytes(a) == to_json_bytes(b)
