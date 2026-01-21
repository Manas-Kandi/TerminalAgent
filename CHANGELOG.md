# Changelog

## [0.2.0] - 2026-01-20

### Added
- **Terminal/Code UI** - Human governance interface with code review, capability preview, audit viewer
- **Mock Renderer** - Simulates web pages for kernel validation without Chromium
- **Session Management** - Process/workspace/timed/persistent sessions with revocation persistence
- **Kernel Versioning** - Semver contract with `min_kernel_version` workflow headers
- **PII Protection** - Salted hash of sensitive field names in audit log (GDPR/CCPA)
- **CDP Schema Fixtures** - Frozen message shapes for byte-compatible testing
- **Chaos Test Suite** - Event reordering, state mismatch, concurrency tests
- **Adversarial Tests** - Prompt injection defense, capability firewall validation

### Changed
- **Snapshot System** - Hybrid copy-on-write: small data copied, large data (>10KB) referenced
  - RAM delta: 0.00 MB for 5MB DOM (was 1.52MB with deepcopy)
  - Time: <100ms for 5MB DOM

### Security
- Revocations persist to SQLite and survive restart (no zombie tokens)
- Capability denials logged to audit trail
- Form field names hashed to prevent PII schema leakage

## [0.1.0] - 2026-01-20

### Added
- **Capability Broker** - Grant/check/revoke with wildcards, expiry, risk tiers
- **Object Manager** - Stable IDs (`tab:42`), Tab/Form/Workspace types
- **Audit Log** - Append-only SQLite, provenance tracking, secret redaction
- **Transaction Coordinator** - Checkpoint/commit/rollback for browser-local state
- **Agent Runtime** - Sandboxed execution, blocked imports, IPC server/client
