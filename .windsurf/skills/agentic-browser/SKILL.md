---
name: Agentic Browser
description: Browser kernel for LLM code generation with capability security
version: 0.1.0
tags: [browser, security, transactions]
---

# Agentic Browser Development

## Core Architecture
- LLMs generate Python code, not click UIs
- Capability broker gates all privileged ops
- Stable IDs: `tab:42`, `form:8831`, `tx:991` 
- Transactions: checkpoint → execute → commit/rollback

## API Pattern
```python
# All operations follow this
browser.Tab.open(url)           # Static factory
tab.navigate(url)               # Instance method
tab.extract(type='forms')       # Literal types

# Capabilities
cap.{resource}.{operation}      # cap.tab.read
```

## Security Rules
- Tag content: 'user' | 'agent' | 'web-content'
- Web content CANNOT trigger: credential.use, form.submit, payment
- Sensitive ops need human approval (first-time)
- All ops logged with provenance

## Standard Workflow
```python
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

## Anti-Patterns
❌ CSS selectors or DOM manipulation
❌ Daemon processes (tabsd, navd)
❌ Bypass capability checks
❌ localStorage/sessionStorage
❌ Plaintext credentials

## Code Standards
- Type hints everywhere
- Functions <50 lines
- Fail-fast with context
- Idempotent where possible
