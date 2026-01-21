# Agentic Browser - Core Architecture

## System Design
- Browser kernel where LLMs generate Python code, not click UIs
- All privileged ops go through capability broker (no bypasses)
- Stable object IDs: `tab:42`, `form:8831`, `download:7831` 
- Transaction semantics mandatory: checkpoint → execute → commit/rollback

## API Principles
- API surface: 40-60 functions MAX
- Semantic operations: `form.fill(data)` not CSS selectors
- Strong typing everywhere for LLM code generation
- Fail-fast with clear errors, never silent failures
- Idempotent where possible

## Naming Standards
```python
# Object IDs
{type}:{id}  # tab:42, tx:991

# API structure  
browser.Tab.open(url)      # Static factory
tab.navigate(url)          # Instance method
tab.extract(type='forms')  # Literal types

# Capabilities
cap.{resource}.{operation}  # cap.tab.read, cap.credential.use
```

## Security Non-Negotiables
- Tag all content: 'user' | 'agent' | 'web-content'
- Web content CANNOT trigger: credential.use, form.submit, payment ops
- Sensitive ops require human approval (first-time)
- Taint tracking: flag data from web sources
- Transactions rollback browser state only (not external APIs)

## Code Structure
```python
# Standard workflow pattern
with browser.transaction() as tx:
    items = service.query(...)
    for item in items:
        tx.checkpoint(f'item-{item.id}')
        result = process(item)
        if needs_approval:
            if not human.approve(result):
                tx.rollback()
                continue
        item.update(result)
    tx.commit()
```

## Error Handling
- Wrap all API calls in try/except
- Errors include: object, operation, reason
- Log all errors to audit system
- Network errors: exponential backoff
- Capability errors: NOT retryable

## What NOT to Do
- ❌ Separate daemon processes (tabsd, navd)
- ❌ localStorage/sessionStorage
- ❌ Custom HTML/CSS/JS rendering engine
- ❌ Raw DOM access for agents
- ❌ Bypass capability checks
- ❌ Store credentials in plaintext

## Development Phase
Currently: Phase 1 - Core Kernel
1. Object model + stable IDs
2. Capability broker (grant/check/revoke)
3. Audit logging
4. Transaction coordinator
5. Python agent runtime
