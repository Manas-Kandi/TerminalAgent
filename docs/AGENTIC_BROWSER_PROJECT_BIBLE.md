# The Agentic Browser — Project Bible

**One-liner**: A capability-secure, programmable browser where LLMs generate **code** against stable browser APIs (not DOM selectors), and execution is **transactional, auditable, and human-governed**.

**Status**: Concept / Architecture v1

---

## 1) Executive Summary

We are building a browser designed for an agentic world.

Instead of automating the UI (clicks, selectors, screenshots), agents operate through a **stable, semantic programming interface** exposed by the browser itself. Users provide intent in natural language; an LLM generates Python/TypeScript code using first-class browser APIs; the system executes this code in a sandboxed runtime with:

- **Capability-based security** (least privilege, revocable permissions)
- **Transactional semantics** (checkpoints, rollback, explicit commit boundaries)
- **Full auditability** (append-only operation log, provenance, replay tooling)
- **Human-in-the-loop governance** (preview/approve high-risk actions)

This is not “better automation.” It is a **programmable operating environment for the web**, where **agents are first-class principals**.

---

## 2) The Core Problem

### Why multi-step agent workflows fail today
Most browser agents are built on a brittle pipeline:

1. LLM decides an action ("click login")
2. Automation maps to DOM selectors / coordinates
3. The browser executes input simulation
4. Repeat until success or drift

This fails because:

- **Selectors are unstable**: DOM structures change continuously.
- **Vision-to-action is error-prone**: mapping intent to pixels is noisy.
- **No transactional safety**: partial failures leave the system in unknown states.
- **Weak observability**: failures lack precise, replayable traces.
- **No principled security model**: agents often inherit “user-level” powers.

### Fundamental insight
**LLMs are better at writing code than navigating UIs.**

We should shift the failure mode from “UI manipulation brittleness” to “code correctness,” and make that correctness tractable through:

- typed APIs
- deterministic state queries
- strict permissions
- auditing and replay

---

## 3) Product Definition

### What this is
- A standalone browser whose core abstractions are **OS-like resources** (tabs, documents, downloads, credentials, workspaces).
- A **kernel-style privileged layer** that enforces permissions, routes IPC, and provides stable semantics.
- A built-in **terminal/code interface** for reviewing and executing agent-generated programs.
- A **supervisor panel** for approvals, rollback, and audit.

### What this is not
- Not a macro recorder.
- Not “Playwright with an LLM.”
- Not a general OS replacement.
- Not a promise of universal automation across adversarial websites.

### Target users (initial)
- **Power users / developers** doing repetitive web workflows.
- **Support / ops teams** doing high-volume triage across SaaS tools.
- **Researchers / analysts** doing extraction + summarization with citations.

---

## 4) Core Principles (Invariants)

- **APIs over selectors**: semantic operations are the default.
- **Capabilities everywhere**: every privileged action is gated and logged.
- **Transactions are explicit**: multi-step workflows are safe-by-design.
- **Provenance is mandatory**: the system distinguishes human vs agent vs web content.
- **LLM is not trusted**: it is a code generator, not an authority.
- **Small, typed API surface**: fewer primitives, composable by design.
- **Deterministic introspection**: query state without side effects.

---

## 5) User Experience (Primary Interfaces)

### 5.1 Terminal / Code Interface (primary)
- Displays generated Python/TypeScript.
- Shows required capabilities *before execution*.
- Allows:
  - edit
  - run
  - step
  - pause/resume
  - inspect variables

### 5.2 Supervisor Panel (trust & safety)
- Current workflow status
- Pending approvals for sensitive operations
- Transaction checkpoints and rollback controls
- Audit log timeline

### 5.3 Workspace UI (organization)
- Workspaces group:
  - tabs
  - downloads
  - storage
  - policies
  - workflows
  - credentials

---

## 6) System Architecture

### 6.1 Conceptual model: browser as operating system
Traditional browsers are **document viewers + scripting**.

We build an **operating environment** where web rendering is one runtime among others.

```
┌───────────────────────────────────────────────────────────┐
│ Human intent (NL) → LLM generates code → Review → Execute │
└───────────────────────────────────────────────────────────┘
                      │
                      ▼
┌───────────────────────────────────────────────────────────┐
│            Browser Kernel (Privileged / TCB)              │
│  - Capability Broker  - Object Manager  - Transactions    │
│  - Audit & Replay     - Policy Engine   - IPC Router      │
└───────────────┬───────────────────────────────┬───────────┘
                │                               │
                ▼                               ▼
┌──────────────────────────┐        ┌────────────────────────┐
│ Agent Runtime (Sandbox)  │        │ Web Runtime (Renderer)  │
│ Python/TS code execution │        │ Chromium (Blink + V8)   │
│ No net/FS except via API │        │ Untrusted + sandboxed    │
└──────────────────────────┘        └────────────────────────┘
```

### 6.2 Components

#### A) Browser Kernel (privileged)
**Purpose**: trusted enforcement boundary (the “mini-OS core”).

- **Capability Broker**
  - Validates every privileged operation
  - Issues, revokes, expires capabilities
  - Enforces constraints (URL patterns, time bounds, rate limits)

- **Object Manager**
  - Canonical registry of browser resources
  - Stable IDs (`tab:42`, `download:7831`, `form:8831`)
  - Queryable state without side effects

- **Transaction Coordinator**
  - Checkpoints, rollback, explicit commit
  - Browser-local atomicity for multi-step workflows
  - Clear boundaries for irreversible operations

- **Audit & Replay System**
  - Append-only operation log
  - Provenance + causality chain
  - Replay tooling and divergence reporting

#### B) System services (user-space daemons; still trusted)
Examples:
- `ptyd`: PTYs, terminal sessions
- `storaged`: workspace storage, secrets policy hooks
- `netd`: network policy + observability (where feasible)
- `downloadsd`: download lifecycle, extraction

#### C) Web runtime (untrusted)
- Embedded renderer engine (e.g., Chromium)
- Sandbox per tab/site
- No direct access to kernel beyond tightly scoped IPC

#### D) Agent runtime (privileged but sandboxed)
- Executes LLM-generated code
- Only imports `browser` (and a small standard library)
- No direct network/FS; all operations go through capability-checked IPC

---

## 7) Canonical Object Model

### 7.1 Stable IDs
- Human-readable and stable across a session; optionally stable across restarts via persistence.
- Examples:
  - `tab:42`
  - `doc:8831`
  - `form:9901`
  - `download:7831`
  - `tx:991`, `cp:5`

### 7.2 Core objects
- **Tab**: URL, title, load state, workspace association
- **Document**: extracted representation (readable text, tables, links, forms)
- **Form**: semantic fields, validation metadata, preview/submit semantics
- **Download**: type, path, extraction utilities
- **CredentialHandle**: opaque reference; secrets are never exposed to agent code
- **Workspace**: tabs + storage + policies + credentials
- **Transaction**: checkpoints, operations, commit/rollback

---

## 8) The Stable API Surface

### 8.1 API design principles
- **Small surface area**: target ~40–60 core functions.
- **Semantic operations**: what the user means, not DOM mechanics.
- **Strong typing**: Python type hints / TypeScript types for LLM reliability.
- **Fail-fast**: explicit errors; no silent fallbacks.
- **Idempotent where possible**: safe retries.
- **Composable**: primitives interoperate cleanly.

### 8.2 Core modules (v1)
- `browser.Tab`
- `browser.Form`
- `browser.Download`
- `browser.Credential`
- `browser.Workspace`
- `browser.transaction()` / `browser.Transaction`
- `browser.Audit` (query/export)

### 8.3 Example (semantic; no selectors)
```python
import browser

with browser.transaction() as tx:
    tab = browser.Tab.open('https://example.com/login', workspace='work')
    tab.wait_for('interactive')

    form = browser.Form.find(tab, type='login')
    form.fill({'email': 'user@example.com'})

    tx.checkpoint('before-submit')

    # Sensitive: requires approval + capability
    if browser.human.approve('Submit login form?'):
        form.submit()
        tx.commit()
    else:
        tx.rollback('before-submit')
```

---

## 9) Agent Runtime & Execution Model

### 9.1 Flow
1. Human provides intent (NL)
2. LLM generates code against typed APIs
3. System performs static checks:
   - syntax
   - allowed imports
   - requested capabilities (dry-run)
4. Human reviews/edits code
5. Execution occurs in sandboxed agent runtime
6. Every privileged operation is capability-checked + logged

### 9.2 Key runtime constraints
- No raw socket access.
- No arbitrary filesystem access.
- No secret material in memory unless explicitly permitted (prefer handles).
- Budgeting:
  - timeouts
  - CPU/memory quotas
  - rate limits

---

## 10) Security Model

### 10.1 Capabilities (least privilege)
Every privileged operation requires an unforgeable capability token.

A capability binds:
- **principal** (which agent/workflow)
- **operation** (what)
- **resource** (which object(s))
- **constraints** (URL pattern, time window, rate limit)

Operations are categorized:
- **Read-only** (low risk): read content, list tabs/downloads
- **Stateful** (medium risk): navigate, open/close tabs, fill forms
- **Irreversible** (high risk): submit forms, send emails, authorize payments

### 10.2 Progressive trust
- First-time sensitive op triggers an approval prompt.
- User can approve once / session / always (scoped by constraints).
- Capabilities are revocable and auditable.

### 10.3 Prompt injection defenses (required)
The web is adversarial. Defenses must exist at the platform layer:

- **Content provenance tagging**
  - `user_instruction` vs `web_content` vs `system`

- **Structured extraction by default**
  - tables/forms/links as JSON, not raw text dumps

- **Capability firewall**
  - untrusted web content cannot directly trigger sensitive operations

- **Taint tracking**
  - if arguments are derived from web content, require confirmation for sensitive sinks

- **Safe tool design**
  - prefer `CredentialHandle` over exposing secrets

---

## 11) Transaction System

### 11.1 Goals
- Reduce multi-step workflows to a controlled state machine.
- Provide rollback to known-good browser state.
- Make “partial completion” visible and recoverable.

### 11.2 What can be rolled back
**Browser-local state**:
- tab URLs / navigation state
- scroll positions
- in-progress form fills (before submit)
- workspace ephemeral state

### 11.3 What cannot be rolled back
**External side effects**:
- sent emails
- submitted payments
- irreversible API calls

Therefore:
- high-risk operations require explicit approval
- support “draft mode” integrations where possible

---

## 12) Audit & Replay

### 12.1 Audit log properties
- Append-only
- Every privileged op logged
- Includes provenance (`human|agent|page`), principal, object IDs, transaction context

### 12.2 Replay
Replay is a debugging tool, not a guarantee:
- Web content changes
- external services change
- time-dependent flows diverge

Replay output should report:
- matched ops
- divergence point
- state diff snapshot

### 12.3 Privacy controls
- Never log secrets.
- Redact or hash sensitive form values by policy.
- Configurable retention and export.

---

## 13) Domain Integrations (Gmail/GitHub/Slack/etc.)

### 13.1 Philosophy
- Prefer official APIs over UI automation.
- Use browser UI only for authentication flows and unsupported actions.

### 13.2 Integration shape
- Implement integrations as libraries built on:
  - `CredentialHandle` + OAuth
  - `netd` policies
  - typed domain objects

Example intent:
- `browser.Gmail.connect()` yields a client whose operations are still capability-gated.

---

## 14) Reliability & Observability

- Clear error taxonomy:
  - `CapabilityDenied`
  - `Timeout`
  - `NavigationFailed`
  - `ExtractionFailed`
  - `DivergenceDetected` (replay)
- Structured logs with correlation IDs (`tx`, `tab`, `principal`).
- Deterministic “dry-run” to compute required capabilities.

---

## 15) Roadmap (High Level)

### Phase 1: Foundation (0–6 months)
- Kernel: object model + capabilities + audit + basic transactions
- Agent runtime: sandboxed Python/TS + IPC
- Renderer integration: Chromium embedding + strict isolation
- Terminal/code UI: edit/run/inspect + capability preview

**Success**: hand-written scripts can reliably run with full audit + rollback for navigation.

### Phase 2: LLM Integration (6–12 months)
- NL → code generation
- Supervisor UI (approvals, checkpoints)
- First integrations (Gmail/GitHub/Slack)
- Progressive trust + revocation UX

**Success**: users can complete 2–3 flagship workflows end-to-end with review + approvals.

### Phase 3: Production hardening (12–18 months)
- Security hardening + threat modeling
- Prompt injection defenses
- Reliability: pause/resume, recovery, backoff
- Enterprise audit/export/retention

### Phase 4: Ecosystem (18–24 months)
- Integration SDK + templates marketplace
- Multi-agent coordination
- Background/scheduled workflows

---

## 16) Key Risks (and what we do about them)

- **Chromium maintenance burden**
  - Mitigation: keep fork minimal; invest in automated rebase testing.

- **Prompt injection / data exfiltration**
  - Mitigation: provenance, taint tracking, capability firewalls, approvals.

- **Website adversarial response**
  - Mitigation: favor official APIs, rate limiting, user-owned auth, policy compliance.

- **LLM code quality**
  - Mitigation: typed APIs, linting/validation, human review, smaller initial scope.

---

## 17) Glossary

- **Principal**: an identity that performs actions (human, agent, service).
- **Capability**: an unforgeable token permitting a principal to perform an operation.
- **TCB**: trusted computing base (the minimal privileged core we must trust).
- **Checkpoint**: a saved browser-local state snapshot inside a transaction.
- **Rollback**: restoring browser-local state to a checkpoint.
- **Provenance**: metadata describing the origin of content (web vs user vs system).
