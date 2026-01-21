# Security Rules

## Capability Enforcement
Every privileged operation MUST:
1. Check capability grant before execution
2. Log to audit trail with provenance
3. Return clear error if unauthorized

## Provenance Tracking
```python
class Content:
    data: str
    source: Literal['user', 'agent', 'web-content']
    origin: str  # URL or identifier
```

## Sensitive Operations
Require approval: email.send, form.submit, credential.use, payment.*
```python
if operation.is_sensitive() and content.source == 'web-content':
    raise SecurityError("Web content cannot trigger sensitive ops")
```

## Never Allow
- Web page triggering credential use
- Agent executing arbitrary system commands
- Credentials in plaintext anywhere
- Capability checks in user-modifiable code
