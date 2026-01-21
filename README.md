# Agentic Browser Kernel

A proof-of-concept capability-secure browser kernel for LLM code generation.

## Overview

This is a **Phase 0 prototype** implementing the core ideas from the Agentic Browser Project Bible:

- **Capability Broker**: Every privileged operation requires an unforgeable capability token
- **Object Manager**: Stable IDs (`tab:42`, `form:1`) for all browser resources
- **Audit Log**: Append-only operation log with provenance tracking
- **Transaction Coordinator**: Checkpoints, rollback, and commit for browser-local state
- **Agent Runtime**: Sandboxed execution environment for LLM-generated code

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest -v
```

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│ Agent Code (Python)                                        │
│   import browser                                           │
│   browser.Tab.open(url)                                    │
└───────────────────────────────────────────────────────────┘
                      │
                      ▼
┌───────────────────────────────────────────────────────────┐
│            Browser Kernel (kernel/)                        │
│  - Capability Broker  - Object Manager  - Transactions    │
│  - Audit Log          - Agent Runtime                      │
└───────────────────────────────────────────────────────────┘
```

## Usage

### Capability Broker

```python
from kernel.capabilities import CapabilityBroker, CapabilityRisk

caps = CapabilityBroker()

# Grant capabilities
caps.grant(principal='agent:1', operation='tab.read', resource='tab:*')
caps.grant(principal='agent:1', operation='form.submit', resource='form:1', 
           risk=CapabilityRisk.IRREVERSIBLE)

# Check capabilities
caps.check('agent:1', 'tab.read', 'tab:42')  # True
caps.require('agent:1', 'tab.write', 'tab:42')  # Raises CapabilityDenied

# Revoke
caps.revoke_all('agent:1')
```

### Object Manager

```python
from kernel.objects import ObjectManager, ObjectType

objects = ObjectManager()

# Create objects with stable IDs
tab = objects.create(ObjectType.TAB, url='https://example.com')
print(tab.id)  # 'tab:1'

# Query and retrieve
tab = objects.get('tab:1')
tabs = objects.list_by_type(ObjectType.TAB)
```

### Audit Log

```python
from kernel.audit import AuditLog, Provenance

audit = AuditLog(db_path='audit.db')  # Or None for in-memory

# Log operations
audit.log(
    op='tab.navigate',
    principal='agent:1',
    object='tab:42',
    args={'url': 'https://example.com'},
    result='success',
    provenance=Provenance.AGENT
)

# Query
entries = audit.query(principal='agent:1', op='tab.*')
audit.export_json('audit_export.json')
```

### Transaction Coordinator

```python
from kernel.transactions import TransactionCoordinator

tx_coord = TransactionCoordinator(objects, audit)

with tx_coord.begin() as tx:
    tab.navigate('https://step1.com')
    tx.checkpoint('after-step1')
    
    tab.navigate('https://step2.com')
    
    if something_wrong:
        tx.rollback('after-step1')  # Back to step1 state
    else:
        tx.commit()
```

### Agent Runtime

```python
from kernel.runtime import AgentRuntime

runtime = AgentRuntime(caps, objects, audit, transactions)

# Validate code (blocks dangerous imports)
errors = runtime.validate_code(code)

# Execute with sandboxing
result = runtime.execute(code, principal='agent:1')
print(result.state)  # ExecutionState.COMPLETED
```

### End-to-End Example

```python
code = """
with browser.transaction() as tx:
    tab = browser.Tab.open('https://example.com/login')
    tab.wait_for('interactive')
    
    form = browser.Form.find(tab.id, type='login')
    tx.checkpoint('before-fill')
    
    form.fill({'email': 'user@example.com'})
    
    if browser.human.approve('Submit login form?'):
        form.submit()
        tx.commit()
    else:
        tx.rollback('before-fill')
"""

result = runtime.execute(code, principal='agent:1')
```

## Project Structure

```
kernel/
├── __init__.py          # Package exports
├── capabilities.py      # Capability Broker
├── objects.py           # Object Manager (Tab, Form, Workspace)
├── audit.py             # Audit Log (SQLite)
├── transactions.py      # Transaction Coordinator
└── runtime.py           # Agent Runtime + IPC

tests/
├── test_capabilities.py
├── test_objects.py
├── test_audit.py
├── test_transactions.py
└── test_runtime.py
```

## Next Steps (Phase 1)

- [ ] Chromium embedding for real web rendering
- [ ] IPC server deployment (Unix socket)
- [ ] Terminal/code UI
- [ ] Progressive trust UX

## License

MIT
