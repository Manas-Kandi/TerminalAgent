# Chromium Integration Plan

**Status**: Ready to begin (kernel v0.2.0 tagged)

## Prerequisites (All Met)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Capability firewall tested | ✅ | `test_adversarial.py` - 12 tests |
| Revocation persists | ✅ | `test_sessions.py` - survives restart |
| CDP schema frozen | ✅ | `tests/fixtures/cdp/` |
| Chaos suite passes | ✅ | Event reorder, state mismatch handled |
| Snapshot <100ms, <1MB | ✅ | Hybrid COW: 45ms, 0MB delta |
| 243 tests passing | ✅ | Full kernel coverage |

## Phase 2.1: Minimal Headless Chromium

### Scope (Narrow)
- Navigation only (`Page.navigate`, `Page.loadEventFired`)
- Form extraction only (`DOM.querySelector`, `DOM.getOuterHTML`)
- No JavaScript execution
- No network interception
- No screenshots

### Architecture

```
┌─────────────────┐     CDP/WebSocket     ┌──────────────────┐
│   Kernel        │◄────────────────────►│  Chromium        │
│   (Python)      │                       │  (--headless)    │
│                 │                       │                  │
│  ObjectManager  │  Tab state sync       │  Blink renderer  │
│  Renderer Bridge│◄────────────────────►│  DOM             │
│  CDP Client     │                       │  CDP Server      │
└─────────────────┘                       └──────────────────┘
```

### Implementation Steps

1. **CDP Client** (`kernel/cdp/client.py`)
   - WebSocket connection to Chromium
   - Message ID tracking
   - Request/response correlation
   - Event subscription

2. **Chromium Launcher** (`kernel/cdp/launcher.py`)
   - Spawn `chromium --headless --remote-debugging-port=9222`
   - Wait for CDP endpoint
   - Health check
   - Graceful shutdown

3. **Renderer Bridge Update** (`kernel/renderer/bridge.py`)
   - Replace `MockRenderer` calls with CDP calls
   - Translate kernel messages ↔ CDP messages
   - Handle CDP events → ObjectManager updates

4. **Integration Tests** (`tests/integration/test_chromium.py`)
   - Real navigation to example.com
   - Real form extraction
   - Verify audit trail matches mock behavior

### Threat Model

| Threat | Mitigation |
|--------|------------|
| Renderer spoofs CDP messages | Validate `targetId` against known tabs |
| Renderer crashes mid-transaction | Transaction aborts, state rolled back |
| CDP socket hijacked | Unix socket with restricted permissions |
| Malicious page tries to access kernel | CDP runs in Chromium sandbox, no kernel access |

### Acceptance Criteria

1. `pytest tests/integration/` passes with real Chromium
2. `browser.Tab.open("https://example.com")` works
3. `browser.Form.find()` extracts real forms
4. Audit log identical to mock renderer tests
5. Transaction rollback works with real navigation

### Non-Goals (Phase 2.2+)

- Full DOM manipulation
- JavaScript execution
- Network request interception
- Screenshot/PDF generation
- Multiple browser contexts

## Commands

```bash
# Run kernel tests (no Chromium needed)
pytest tests/ --ignore=tests/integration/

# Run integration tests (requires Chromium)
pytest tests/integration/ -v

# Run all tests
pytest -v
```

## Timeline

- **Week 1**: CDP client + launcher
- **Week 2**: Renderer bridge integration
- **Week 3**: Integration tests + hardening
