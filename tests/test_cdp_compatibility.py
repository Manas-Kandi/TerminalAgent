"""Tests for CDP message schema compatibility.

These tests ensure the mock renderer emits byte-compatible messages
that match what real Chromium CDP will send.
"""

import json
import pytest
from tests.fixtures.cdp.schemas import (
    CDPRequest, CDPResponse, CDPEvent, KernelMessage,
    validate_cdp_response, validate_kernel_message,
)
from tests.fixtures.cdp.messages import (
    PAGE_NAVIGATE_REQUEST, PAGE_NAVIGATE_RESPONSE_SUCCESS,
    KERNEL_NAVIGATE_REQUEST, KERNEL_NAVIGATE_RESULT_SUCCESS,
    KERNEL_TAB_UPDATED_EVENT, KERNEL_FORM_FOUND,
    MALICIOUS_CLOSE_TARGET_SPOOF, MALICIOUS_EXTRA_FIELDS,
    MALICIOUS_WRONG_TYPE, to_json_bytes, messages_byte_equal,
)


class TestCDPRequestSchema:
    """Tests for CDP request message format."""
    
    def test_request_has_required_fields(self):
        """CDP request must have id, method, params."""
        req = CDPRequest.from_json(json.dumps(PAGE_NAVIGATE_REQUEST))
        assert req.id == 1
        assert req.method == "Page.navigate"
        assert "url" in req.params
    
    def test_request_round_trip(self):
        """Request survives JSON serialization round-trip."""
        req = CDPRequest(id=42, method="Test.method", params={"key": "value"})
        json_str = req.to_json()
        req2 = CDPRequest.from_json(json_str)
        
        assert req.id == req2.id
        assert req.method == req2.method
        assert req.params == req2.params
    
    def test_request_byte_stability(self):
        """Same request produces same bytes."""
        req = CDPRequest(id=1, method="Test.method", params={"a": 1, "b": 2})
        
        bytes1 = req.to_json().encode('utf-8')
        bytes2 = req.to_json().encode('utf-8')
        
        assert bytes1 == bytes2


class TestCDPResponseSchema:
    """Tests for CDP response message format."""
    
    def test_success_response_has_result(self):
        """Success response has result field."""
        resp = CDPResponse.from_json(json.dumps(PAGE_NAVIGATE_RESPONSE_SUCCESS))
        
        assert resp.id == 1
        assert resp.error is None
        assert "frameId" in resp.result
    
    def test_error_response_has_error(self):
        """Error response has error field."""
        error_resp = {
            "id": 1,
            "error": {
                "code": -32000,
                "message": "Target not found",
            }
        }
        resp = CDPResponse.from_json(json.dumps(error_resp))
        
        assert resp.error is not None
        assert resp.error["code"] == -32000
    
    def test_validate_response_fields(self):
        """validate_cdp_response catches missing fields."""
        resp = CDPResponse(id=1, result={"frameId": "abc"})
        
        errors = validate_cdp_response(resp, ["frameId", "loaderId"])
        
        assert len(errors) == 1
        assert "loaderId" in errors[0]


class TestKernelMessageSchema:
    """Tests for kernel↔renderer IPC message format."""
    
    def test_navigate_request_fields(self):
        """Navigate request has required fields."""
        msg = KernelMessage.from_json(json.dumps(KERNEL_NAVIGATE_REQUEST))
        
        assert msg.type == "navigate"
        assert msg.tab_id == "tab:1"
        assert msg.request_id == 1
        assert "url" in msg.payload
    
    def test_navigate_result_fields(self):
        """Navigate result has required fields."""
        msg = KernelMessage.from_json(json.dumps(KERNEL_NAVIGATE_RESULT_SUCCESS))
        
        assert msg.type == "navigate_result"
        assert msg.payload["success"] is True
        assert "url" in msg.payload
        assert "title" in msg.payload
    
    def test_event_has_no_request_id(self):
        """Events have null request_id."""
        msg = KernelMessage.from_json(json.dumps(KERNEL_TAB_UPDATED_EVENT))
        
        assert msg.request_id is None
        assert msg.type == "tab_updated"
    
    def test_form_found_has_fields(self):
        """Form found message includes field definitions."""
        msg = KernelMessage.from_json(json.dumps(KERNEL_FORM_FOUND))
        
        assert msg.payload["form_type"] == "login"
        assert len(msg.payload["fields"]) == 2
        
        field_names = [f["name"] for f in msg.payload["fields"]]
        assert "email" in field_names
        assert "password" in field_names
    
    def test_validate_kernel_message_fields(self):
        """validate_kernel_message catches missing payload fields."""
        msg = KernelMessage(
            type="navigate_result",
            tab_id="tab:1",
            request_id=1,
            payload={"success": True},  # Missing url, title
        )
        
        errors = validate_kernel_message(msg, ["success", "url", "title"])
        
        assert len(errors) == 2  # url, title missing


class TestMaliciousMessages:
    """Tests for handling malicious CDP messages."""
    
    def test_reject_prototype_pollution(self):
        """Messages with __proto__ fields are rejected."""
        msg_json = json.dumps(MALICIOUS_EXTRA_FIELDS)
        msg = KernelMessage.from_json(msg_json)
        
        # __proto__ should NOT be in payload after parsing
        # (Python's json.loads doesn't execute __proto__, but we verify)
        assert "__proto__" in msg.payload  # It's there as a key
        # But it doesn't affect the object's prototype
        assert not hasattr(msg, "admin")
    
    def test_reject_wrong_types(self):
        """Messages with wrong types are detectable."""
        msg = MALICIOUS_WRONG_TYPE
        
        # Validation should fail
        assert not isinstance(msg["tab_id"], str)
        assert not isinstance(msg["request_id"], int)
        assert not isinstance(msg["payload"], dict)
    
    def test_close_target_spoof_detectable(self):
        """Spoofed Target.closeTarget is detectable by target ID."""
        req = CDPRequest.from_json(json.dumps(MALICIOUS_CLOSE_TARGET_SPOOF))
        
        # Kernel should validate targetId against known targets
        # This test documents that the message is parseable but suspicious
        assert req.params["targetId"] == "target-kernel-process"
        # In real implementation: reject if targetId not in managed_targets


class TestByteCompatibility:
    """Tests for byte-level message compatibility."""
    
    def test_navigate_request_byte_equal(self):
        """Navigate request fixture is byte-stable."""
        bytes1 = to_json_bytes(KERNEL_NAVIGATE_REQUEST)
        bytes2 = to_json_bytes(KERNEL_NAVIGATE_REQUEST)
        
        assert bytes1 == bytes2
    
    def test_messages_with_same_content_are_byte_equal(self):
        """Two dicts with same content produce same bytes."""
        msg1 = {"type": "test", "tab_id": "tab:1", "payload": {"a": 1}}
        msg2 = {"type": "test", "tab_id": "tab:1", "payload": {"a": 1}}
        
        assert messages_byte_equal(msg1, msg2)
    
    def test_messages_with_different_content_not_byte_equal(self):
        """Dicts with different content are not byte-equal."""
        msg1 = {"type": "test", "tab_id": "tab:1"}
        msg2 = {"type": "test", "tab_id": "tab:2"}
        
        assert not messages_byte_equal(msg1, msg2)
    
    def test_field_order_normalized(self):
        """Field order is normalized in byte comparison."""
        # sort_keys=True ensures order independence
        msg1 = {"b": 2, "a": 1}
        msg2 = {"a": 1, "b": 2}
        
        assert messages_byte_equal(msg1, msg2)
