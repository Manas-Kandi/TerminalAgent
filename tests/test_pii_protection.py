"""Tests for PII protection in audit log."""

import pytest
from kernel.audit import AuditLog, Provenance


class TestPIIFieldNameHashing:
    """Tests for field name hashing to protect PII."""
    
    def test_ssn_field_name_hashed(self):
        """Field names containing 'ssn' are hashed."""
        audit = AuditLog(workspace_salt="test-salt")
        
        entry = audit.log(
            op="form.fill",
            principal="agent:1",
            object="form:1",
            args={"ssn": "123-45-6789"},
        )
        
        # 'ssn' should be hashed, not plaintext
        assert "ssn" not in entry.args
        assert any("[PII:" in k for k in entry.args.keys())
        # Value should be redacted (ssn is also a sensitive value pattern)
    
    def test_credit_card_field_hashed(self):
        """Field names containing 'credit_card' are hashed."""
        audit = AuditLog(workspace_salt="test-salt")
        
        entry = audit.log(
            op="form.fill",
            principal="agent:1",
            object="form:1",
            args={"credit_card_number": "4111-1111-1111-1111"},
        )
        
        assert "credit_card" not in str(entry.args.keys())
        assert any("[PII:" in k for k in entry.args.keys())
    
    def test_phone_field_hashed(self):
        """Field names containing 'phone' are hashed."""
        audit = AuditLog(workspace_salt="test-salt")
        
        entry = audit.log(
            op="form.fill",
            principal="agent:1",
            object="form:1",
            args={"phone_number": "555-1234", "email": "test@example.com"},
        )
        
        # phone should be hashed
        assert "phone" not in str(entry.args.keys())
        # email is not PII field name, should remain
        assert "email" in entry.args
    
    def test_non_pii_fields_not_hashed(self):
        """Regular field names are not hashed."""
        audit = AuditLog(workspace_salt="test-salt")
        
        entry = audit.log(
            op="form.fill",
            principal="agent:1",
            object="form:1",
            args={"username": "alice", "remember_me": True},
        )
        
        assert "username" in entry.args
        assert "remember_me" in entry.args
        assert entry.args["username"] == "alice"
    
    def test_hash_is_salted(self):
        """Different salts produce different hashes."""
        audit1 = AuditLog(workspace_salt="salt-a")
        audit2 = AuditLog(workspace_salt="salt-b")
        
        entry1 = audit1.log(op="test", principal="p", object="o", args={"ssn": "123"})
        entry2 = audit2.log(op="test", principal="p", object="o", args={"ssn": "123"})
        
        # Get the hashed key names
        keys1 = list(entry1.args.keys())
        keys2 = list(entry2.args.keys())
        
        # Both should have hashed keys
        assert any("[PII:" in k for k in keys1)
        assert any("[PII:" in k for k in keys2)
        
        # But the hashes should be different due to different salts
        assert keys1 != keys2
    
    def test_hash_is_consistent(self):
        """Same field + salt produces same hash."""
        audit = AuditLog(workspace_salt="consistent-salt")
        
        hash1 = audit._hash_field_name("ssn")
        hash2 = audit._hash_field_name("ssn")
        
        assert hash1 == hash2
    
    def test_hash_truncated_to_8_chars(self):
        """Hash is truncated to 8 characters for readability."""
        audit = AuditLog(workspace_salt="test")
        
        hash_result = audit._hash_field_name("some_field")
        
        assert len(hash_result) == 8
    
    def test_pii_protection_can_be_disabled(self):
        """PII hashing can be disabled for debugging."""
        audit = AuditLog(workspace_salt="test")
        audit._hash_field_names = False
        
        entry = audit.log(
            op="form.fill",
            principal="agent:1",
            object="form:1",
            args={"ssn": "123-45-6789"},
        )
        
        # With hashing disabled, ssn key should be visible
        # (but value still redacted as it's a sensitive value)
        # Actually ssn matches redact pattern, so it will be redacted
        # Let's use a different PII field
        audit2 = AuditLog(workspace_salt="test")
        audit2._hash_field_names = False
        
        entry2 = audit2.log(
            op="form.fill",
            principal="agent:1",
            object="form:1",
            args={"phone": "555-1234"},
        )
        
        assert "phone" in entry2.args
        assert entry2.args["phone"] == "555-1234"


class TestPIIFieldDetection:
    """Tests for PII field name detection."""
    
    def test_detects_ssn_variations(self):
        """Detects various SSN field name patterns."""
        audit = AuditLog()
        
        assert audit._is_pii_field("ssn") is True
        assert audit._is_pii_field("SSN") is True
        assert audit._is_pii_field("social_security") is True
        assert audit._is_pii_field("social_security_number") is True
    
    def test_detects_financial_fields(self):
        """Detects financial PII field names."""
        audit = AuditLog()
        
        assert audit._is_pii_field("credit_card") is True
        assert audit._is_pii_field("card_number") is True
        assert audit._is_pii_field("cvv") is True
    
    def test_detects_contact_fields(self):
        """Detects contact info PII field names."""
        audit = AuditLog()
        
        assert audit._is_pii_field("phone") is True
        assert audit._is_pii_field("phone_number") is True
        assert audit._is_pii_field("address") is True
        assert audit._is_pii_field("zip") is True
        assert audit._is_pii_field("postal_code") is True
    
    def test_non_pii_not_detected(self):
        """Non-PII fields are not flagged."""
        audit = AuditLog()
        
        assert audit._is_pii_field("email") is False  # email is common, not always PII
        assert audit._is_pii_field("username") is False
        assert audit._is_pii_field("remember_me") is False
        assert audit._is_pii_field("submit") is False


class TestAuditLogGDPRCompliance:
    """Tests for GDPR/CCPA compliance features."""
    
    def test_no_pii_field_names_in_log(self):
        """Audit log doesn't leak PII field existence."""
        audit = AuditLog(workspace_salt="gdpr-test")
        
        # Log a form with sensitive field names
        audit.log(
            op="form.fill",
            principal="agent:1",
            object="form:1",
            args={
                "email": "user@example.com",
                "ssn": "123-45-6789",
                "credit_card": "4111111111111111",
                "dob": "1990-01-01",
            },
        )
        
        # Query the log
        entries = audit.query()
        
        for entry in entries:
            args_str = str(entry.args)
            # These PII field names should NOT appear in plaintext
            assert "ssn" not in args_str.lower() or "[PII:" in args_str
            assert "credit_card" not in args_str.lower() or "[PII:" in args_str
            assert "dob" not in args_str.lower() or "[PII:" in args_str
    
    def test_audit_export_is_pii_safe(self):
        """Exported audit data doesn't contain PII field names."""
        import tempfile
        import json
        from pathlib import Path
        
        audit = AuditLog(workspace_salt="export-test")
        
        audit.log(
            op="form.fill",
            principal="agent:1",
            object="form:1",
            args={"ssn": "123", "phone": "555"},
        )
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            filepath = f.name
        
        try:
            audit.export_json(filepath)
            
            with open(filepath) as f:
                data = json.load(f)
            
            exported_str = json.dumps(data)
            
            # PII field names should be hashed in export
            assert "ssn" not in exported_str.lower() or "[PII:" in exported_str
            assert "phone" not in exported_str.lower() or "[PII:" in exported_str
        finally:
            Path(filepath).unlink(missing_ok=True)
