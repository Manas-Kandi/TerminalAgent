# Trust Decision Matrix

Maps operations → risk tiers → UI affordances for human governance.

---

## 1) Risk Tiers

| Tier | Label | Description | Reversible? |
|------|-------|-------------|-------------|
| **T1** | READ | Query state, no side effects | N/A |
| **T2** | STATEFUL | Modifies browser-local state | ✓ via rollback |
| **T3** | IRREVERSIBLE | External side effects | ✗ |

---

## 2) Operation → Tier Mapping

### Tab Operations
| Operation | Tier | Rationale |
|-----------|------|-----------|
| `tab.list` | T1 | Read-only enumeration |
| `tab.read` | T1 | Read tab properties |
| `tab.extract` | T1 | Content extraction |
| `tab.open` | T2 | Creates browser state |
| `tab.navigate` | T2 | Modifies tab URL |
| `tab.close` | T2 | Destroys tab state |

### Form Operations
| Operation | Tier | Rationale |
|-----------|------|-----------|
| `form.read` | T1 | Read form structure |
| `form.find` | T1 | Query for forms |
| `form.fill` | T2 | Modifies form buffer (rollback-safe) |
| `form.clear` | T2 | Clears form buffer |
| `form.submit` | **T3** | Sends data externally |

### Workspace Operations
| Operation | Tier | Rationale |
|-----------|------|-----------|
| `workspace.list` | T1 | Read-only |
| `workspace.read` | T1 | Read-only |
| `workspace.create` | T2 | Creates state |
| `workspace.delete` | T2 | Destroys state (local) |

### Credential Operations
| Operation | Tier | Rationale |
|-----------|------|-----------|
| `credential.list` | T1 | List handles only |
| `credential.use` | **T3** | Uses secret material |
| `credential.create` | T2 | Stores credential |
| `credential.delete` | T2 | Removes credential |

### Network Operations (future)
| Operation | Tier | Rationale |
|-----------|------|-----------|
| `net.fetch` (GET) | T2 | External request but idempotent |
| `net.fetch` (POST/PUT/DELETE) | **T3** | Mutating external state |
| `net.download` | T2 | Retrieves data |

### Human Interaction
| Operation | Tier | Rationale |
|-----------|------|-----------|
| `human.approve` | T1 | Blocks for input |
| `human.notify` | T1 | Display-only |

### Audit Operations
| Operation | Tier | Rationale |
|-----------|------|-----------|
| `audit.read` | T1 | Query log |
| `audit.export` | T2 | Creates file |

---

## 3) UI Affordances by Tier

### T1 (READ) — Silent Execution
- **Pre-execution**: No prompt
- **During execution**: Logged to audit (visible in `audit` command)
- **Post-execution**: No notification
- **Capability grant**: Auto-grantable by policy

### T2 (STATEFUL) — Notification + Logged
- **Pre-execution**: Capability preview in `caps` command
- **During execution**: Logged with transaction context
- **Post-execution**: State change visible in `objects` command
- **Capability grant**: Requires explicit `grant` command or policy match
- **Recovery**: `rollback` to checkpoint

### T3 (IRREVERSIBLE) — Blocking Approval
- **Pre-execution**: 
  - Highlighted in `caps` output (red)
  - Confirmation prompt before `run` executes
  - Must type `y` to proceed
- **During execution**: Logged with `IRREVERSIBLE` tag
- **Post-execution**: Audit entry marked as irreversible
- **Capability grant**: 
  - First time: Always prompts
  - Subsequent: Per-session or per-resource approval
- **Recovery**: None (show warning)

---

## 4) Approval Persistence Options

| Scope | Description | Use Case |
|-------|-------------|----------|
| **once** | Single operation | High-risk one-off |
| **session** | Until terminal closes | Repeated workflow |
| **resource** | For specific resource ID | `form.submit` on `form:42` |
| **pattern** | URL/resource pattern | `*.example.com` |
| **always** | Permanent (stored) | Trusted integration |

---

## 5) Capability Display Format

Terminal UI shows capabilities as:

```
═══ Required Capabilities ═══════════════════════════════════
  Principal: agent:interactive

  [READ]         tab.list on *           ... ✓ GRANTED
  [STATEFUL]     tab.open on *           ... ✓ GRANTED  
  [STATEFUL]     form.fill on form:*     ... ✗ MISSING
  [IRREVERSIBLE] form.submit on form:*   ... ✗ MISSING

  ⚠ 2 capabilities missing. Use 'grant' to add.
```

---

## 6) Approval Prompt Format (T3)

When running code with T3 operations:

```
═══ ⚠ IRREVERSIBLE OPERATIONS DETECTED ═══════════════════════
  • form.submit on form:1
  • credential.use on cred:gmail

These operations CANNOT be rolled back.

Proceed? [y/N]: 
```

---

## 7) Audit Entry Schema for Trust

```json
{
  "id": "uuid",
  "timestamp": 1234567890.123,
  "op": "form.submit",
  "principal": "agent:1",
  "object": "form:42",
  "args": {"redacted": true},
  "result": "success",
  "tx_id": "tx:abc123",
  "checkpoint_id": "cp:5",
  "provenance": "agent",
  "risk_tier": "T3",
  "approval": {
    "type": "explicit",
    "granted_at": 1234567880.0,
    "scope": "once"
  }
}
```

---

## 8) Policy File Format (Future)

```yaml
# ~/.agentic-browser/policies/default.yaml
version: 1

principals:
  agent:trusted:
    auto_grant:
      - tab.*:*:T1
      - tab.*:*:T2
    require_approval:
      - form.submit:*:T3
      - credential.use:*:T3

  agent:untrusted:
    auto_grant:
      - tab.list:*:T1
      - tab.read:*:T1
    deny:
      - credential.*:*:*
      - form.submit:*:*

resources:
  "https://internal.corp/*":
    require_approval: [T2, T3]
  
  "https://example.com/*":
    auto_grant: [T1, T2]
```

---

## 9) Implementation Checklist

- [x] Risk tier enum in `capabilities.py`
- [x] Risk display formatting in `terminal.py`
- [x] Capability preview (`caps` command)
- [x] T3 confirmation prompt before `run`
- [ ] Approval persistence (session scope)
- [ ] Policy file loading
- [ ] Audit entry risk_tier field
- [ ] Pattern-based capability grants
