# Python Code Standards

## Type Hints & Docs
- Type hints on ALL functions
- Docstrings with examples for public APIs
- Use Literal types for enums: `Literal['markdown', 'forms']` 

## Code Quality
- Functions under 50 lines
- Max nesting: 3 levels
- No magic numbers (use constants)
- Early returns preferred
- Self-documenting variable names

## Patterns
```python
# Good: Capability check pattern
def read_tab(tab_id: str) -> Content:
    if not caps.has(f'cap.tab.read:{tab_id}'):
        raise CapabilityError(f"Missing cap.tab.read:{tab_id}")
    return _read_tab_internal(tab_id)

# Good: Audit logging
@audit_log
def submit_form(form_id: str, data: dict) -> Result:
    # Implementation
    pass

# Good: Transaction usage
with transaction() as tx:
    tx.checkpoint('before-action')
    result = risky_operation()
    tx.commit()
```
