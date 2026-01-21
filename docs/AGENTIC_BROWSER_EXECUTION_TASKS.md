# The Agentic Browser — Execution Tasks (End-to-End)

**Purpose**: Convert the Project Bible into an implementable plan with concrete workstreams, milestones, and acceptance criteria.

**Guiding constraint**: The novel value is the **kernel/object model/capabilities/transactions/audit**. Rendering is a runtime that must be isolated and maintainable.

---

## 0) Operating Assumptions (so the plan is coherent)

- **Renderer strategy**: embed Chromium (or comparable) as an untrusted web runtime.
- **Kernel strategy**: implement a privileged browser process (“kernel”) that mediates all privileged ops.
- **Agent runtime strategy**: sandboxed Python/TypeScript, no raw network/FS; only `browser` API.
- **Shipping strategy**: land value via 2–3 flagship workflows early; expand later.

---

## 1) Workstreams (teams/modules)

### A) Kernel (TCB)
- Capability Broker
- Object Manager
- Transaction Coordinator
- IPC Router

### B) Audit & Replay
- Append-only operation log
- Provenance + causality
- Replay engine + divergence reports

### C) Agent Runtime
- Sandbox execution
- API bindings + type system
- Timeouts, quotas, structured errors

### D) Web Runtime Integration
- Chromium embedding + process model
- Renderer sandbox enforcement
- Safe extraction APIs (forms/tables/links)

### E) UI/UX
- Terminal/code interface
- Supervisor panel
- Workspace UI

### F) Security & Policy
- Threat model + security reviews
- Prompt injection defenses
- Taint tracking + capability firewall
- Secrets handling (opaque handles)

### G) Integrations SDK
- OAuth + CredentialHandle
- Gmail/GitHub/Slack initial integrations
- Template library + testing harness

### H) Developer Experience & Testing
- Workflow test harness
- Deterministic fixtures
- CI, perf tests, rebase tests

---

## 2) Phase 0 — Pre-Flight (Weeks 0–2)

### 0.1 Decide core implementation choices
- **Task**: Choose language(s) and IPC strategy
  - Example options:
    - Kernel: C++/Rust (close to Chromium embedding)
    - Agent runtime: Python (sandboxed) + TS (later)
    - IPC: protobuf/flatbuffers + capability tokens

**Acceptance criteria**
- Documented choices and rationale.
- A “Hello Kernel” demo: UI process requests a privileged operation via IPC and gets a response.

### 0.2 Threat model v1
- **Task**: Write a threat model covering:
  - malicious web content
  - compromised agent prompts
  - credential misuse
  - data exfiltration
  - confused-deputy risks

**Acceptance criteria**
- Enumerated threat list + mitigations mapped to platform controls.

---

## 3) Phase 1 — Foundation (Months 0–6)

### 1.1 Kernel: Object Manager (v1)
**Tasks**
- Define canonical object schemas:
  - `Tab`, `Form`, `Download`, `Workspace`, `Transaction`, `Checkpoint`
- Implement stable ID generation + lifecycle events:
  - created/updated/destroyed
- Provide query APIs that are side-effect free.

**Acceptance criteria**
- You can create/list tabs and workspaces via API.
- All objects have stable IDs in logs.

### 1.2 Kernel: Capability Broker (v1)
**Tasks**
- Implement capability token format + storage
- Implement `check(op, resource, principal, constraints)`
- Implement grant/revoke/expire
- Implement policy hooks:
  - URL pattern constraints
  - time bounds
  - rate limits

**Acceptance criteria**
- 100% of privileged ops require capability checks.
- Denials are explicit and logged.

### 1.3 Kernel: Transaction Coordinator (browser-local)
**Tasks**
- Implement transactions with:
  - start/commit/abort
  - checkpoints
  - rollback to checkpoint
- Define what state is captured:
  - tab URLs, history position, scroll, form-fill buffers
- Enforce commit boundaries for irreversible operations.

**Acceptance criteria**
- Demonstrate:
  - open tab → fill form → rollback restores pre-fill state
  - navigation rollback restores prior URL state

### 1.4 Audit Log (v1)
**Tasks**
- Append-only log schema:
  - `timestamp`, `principal`, `operation`, `object`, `args`, `result`, `tx`, `checkpoint`, `source`
- Ensure log emission for:
  - allow/deny
  - state transitions
  - errors/timeouts
- Redaction rules:
  - never log secrets
  - configurable redaction for form values

**Acceptance criteria**
- 100% privileged ops appear in the log.
- Secrets are never recorded.

### 1.5 Agent Runtime (v1): Sandboxed execution
**Tasks**
- Implement a restricted interpreter environment:
  - only `import browser`
  - no `os`, no sockets, no subprocess
- Implement quotas:
  - wall-clock timeouts
  - memory limit
  - operation budget per minute
- Implement structured exceptions with actionable messages.

**Acceptance criteria**
- Untrusted code cannot read local disk or open sockets.
- A basic script can:
  - open tab
  - wait for load
  - extract markdown
  - fill a semantic form

### 1.6 Web runtime integration (v1)
**Tasks**
- Integrate Chromium and enforce strict isolation:
  - renderer cannot call kernel directly except via controlled IPC
- Implement `Tab.open`, `Tab.navigate`, `Tab.wait_for`.

**Acceptance criteria**
- Stability test: open 20 tabs, navigate, close, no leaks/crashes.

### 1.7 Terminal/Code UI (v1)
**Tasks**
- Editor panel with run/stop
- Output/console
- Capability preview:
  - dry-run compute of required permissions
- Minimal workspace selector

**Acceptance criteria**
- A user can paste a script, see required capabilities, and run it.

### Phase 1 demo workflows (hand-written)
- **Workflow A**: open docs page → extract → save to workspace storage
- **Workflow B**: open a login page → find login form → fill (no submit) → rollback

---

## 4) Phase 2 — LLM Integration + Supervisor (Months 6–12)

### 2.1 NL → code pipeline (v1)
**Tasks**
- Prompt + constraints:
  - only use `browser.*` APIs
  - no arbitrary imports
  - include capability requirements as comments/metadata
- Code validation:
  - parse + lint
  - static capability inference
- Execution modes:
  - run
  - step (operation-level)

**Acceptance criteria**
- Given a set of curated intents, LLM produces syntactically valid code ≥ 80%.

### 2.2 Supervisor panel (v1)
**Tasks**
- Live view of:
  - current operation
  - transaction state
  - pending approvals
- Approval UX:
  - approve once/session/always
  - deny
  - rollback

**Acceptance criteria**
- High-risk operations cannot execute without explicit approval (unless pre-approved by policy).

### 2.3 Capability UX (progressive trust)
**Tasks**
- Capability request prompts
- Capability management UI:
  - list grants
  - revoke
  - expire
- Scoped “always allow” templates

**Acceptance criteria**
- Users can revoke an agent mid-run and see subsequent denials.

### 2.4 Structured extraction (v2)
**Tasks**
- Implement extraction endpoints returning JSON-like structures:
  - `extract(forms)`
  - `extract(tables)`
  - `extract(links)`
  - `extract(readable_markdown)`
- Add metadata:
  - provenance, confidence, source frame

**Acceptance criteria**
- Agents can reliably identify login/search forms without CSS selectors on a curated set of sites.

### 2.5 Replay tooling (v1)
**Tasks**
- Reconstruct session state from audit log
- Replay privileged operations in order
- Divergence reporting

**Acceptance criteria**
- A failed run can be replayed and produces a clear divergence point.

### Phase 2 flagship workflows (human-in-loop)
Pick 2–3 that best match your market:
- **Support triage** (Zendesk + GitHub + docs)
- **Expense processing** (downloads + extraction + form fill)
- **Research report** (navigation + extraction + citations)

---

## 5) Phase 3 — Security + Reliability Hardening (Months 12–18)

### 3.1 Prompt injection defenses (platform-enforced)
**Tasks**
- Provenance tagging end-to-end
- Taint tracking:
  - track web-derived data flowing into sensitive sinks
- Capability firewall:
  - forbid `web_content` as direct trigger for high-risk operations

**Acceptance criteria**
- Red-team suite: prompt injection attempts cannot cause unauthorized sensitive operations.

### 3.2 Credential handling (production)
**Tasks**
- Opaque credential handles
- Passwords never exposed to agent runtime
- OAuth flows where possible
- Per-workspace credential scoping policies

**Acceptance criteria**
- Agent cannot print/export secrets.
- Credential use events are logged without secret leakage.

### 3.3 Reliability: pause/resume/recovery
**Tasks**
- Workflow state persistence
- Crash recovery:
  - restart kernel and restore workspaces
  - resume paused workflows where safe
- Backoff/retry policy for transient failures

**Acceptance criteria**
- Kill/restart the browser mid-workflow; system restores UI and offers safe resume.

### 3.4 Chromium fork maintenance pipeline
**Tasks**
- Automated rebase testing:
  - build + smoke tests
  - security patch fast-path
- Minimize diff strategy:
  - keep kernel integration points narrow

**Acceptance criteria**
- Upgrade Chromium baseline with ≤ 1–2 days of engineer time (target).

---

## 6) Phase 4 — Ecosystem & Scale (Months 18–24)

### 4.1 Integrations SDK
**Tasks**
- SDK for building domain integrations (OAuth + typed clients)
- Policy + capability templates per integration

**Acceptance criteria**
- A third-party integration can be added without kernel changes.

### 4.2 Workflow library + templates
**Tasks**
- Versioned workflow packages
- Signing/verification (optional but recommended)
- Sharing within org/workspace

**Acceptance criteria**
- Users can import a workflow template and run it with review + approvals.

### 4.3 Multi-agent orchestration (optional)
**Tasks**
- Coordinated agents with explicit roles/capabilities
- Shared workspace state + locking

**Acceptance criteria**
- Two agents can safely operate in separate workspaces concurrently.

---

## 7) Cross-Cutting Engineering Tasks

### 7.1 API finalization and typing
- Publish a definitive typed API spec for `browser.*`.
- Provide:
  - Python stubs (`.pyi`)
  - TypeScript types

### 7.2 Testing matrix
- Unit tests: capability broker, transaction coordinator
- Integration tests: renderer ↔ kernel IPC
- Workflow tests: curated sites/fixtures
- Security tests: prompt injection red-team suite

### 7.3 Performance targets
- Per-operation latency budgets (P50/P95)
- Memory per tab/process ceilings
- Log overhead constraints

---

## 8) Acceptance Metrics (per phase)

### Phase 1
- ≥ 30 core API functions
- 100% privileged ops gated + logged
- Rollback works for navigation + pre-submit form state

### Phase 2
- NL→code: ≥ 80% syntactically valid, ≥ 60% semantically correct on curated intents
- Workflow completion ≥ 70% on flagship tasks with human-in-loop

### Phase 3
- ≥ 90–95% completion on flagship tasks
- Zero critical prompt-injection escapes in testing
- Crash recovery + safe resume supported

### Phase 4
- 100+ workflows in active use
- 10+ integrations beyond core set

---

## 9) The “Do Not Build Yet” List (anti-scope)

To protect focus, explicitly defer:

- Universal general web automation across arbitrary sites
- Full OS-like networking/sockets for agent runtime
- Unrestricted plugin execution
- Chrome-parity UI features unrelated to workflows
- Marketplace before workflows are stable

---

## 10) Deliverables Checklist (what “done” looks like)

- Kernel enforces capabilities on every privileged op
- Stable object model with persistent IDs
- Transaction checkpoints + rollback for browser-local state
- Audit log with provenance + export
- Replay with divergence reporting
- Agent runtime sandboxed (no raw net/FS)
- Terminal/code UI + supervisor approvals
- 2–3 flagship workflows working reliably
