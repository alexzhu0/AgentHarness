# AgentHarness

AgentHarness is an agent harness design repository inspired by CL4R1T4S-style system prompt and tool scaffold analysis.

AgentHarness is a pre-execution evidence control-plane for agent actions.

The goal is **not** to copy leaked or reverse-engineered prompts. The goal is to extract reusable engineering patterns and turn them into policy-driven, testable, auditable agent control-plane and runtime-boundary assets.

## Core Idea

Modern agents are not just models plus prompts. They are operating systems around models:

```text
User Task
  ↓
Instruction Hierarchy Resolver
  ↓
Planner / State Machine
  ↓
Tool Router
  ↓
Approval Gate
  ↓
Sandboxed Tool Execution
  ↓
Verifier / Eval Hooks
  ↓
Audited User-facing Response
```

AgentHarness treats agent behavior as **policy-as-code**:

```text
agent_policy.yaml
  → prompt compiler
  → runtime policy
  → tool governance
  → safety evals
  → audit logs
```

## Four Core Assets

### 1. Agent Design Pattern Library

Entry point: [`docs/01-agent-design-pattern-library.md`](docs/01-agent-design-pattern-library.md)

Machine-readable seed: [`patterns/agent_design_patterns.yaml`](patterns/agent_design_patterns.yaml)

This asset extracts reusable agent OS patterns:

- layered agent architecture
- instruction hierarchy resolver
- search-before-edit
- tool preference hierarchy
- approval gate for side effects
- verification loop
- planner / execution mode split
- event stream as source of truth
- memory write boundary
- untrusted corpus neutralization
- policy as code

### 2. Tool Governance Policy

Entry point: [`docs/02-tool-governance-policy.md`](docs/02-tool-governance-policy.md)

Machine-readable seed: [`policies/tool_governance.yaml`](policies/tool_governance.yaml)

This asset defines how tools should be classified, routed, approved and audited.

It covers:

- search tools
- file read/write/delete tools
- shell tools
- database tools
- git tools
- browser tools
- deployment tools
- secret tools
- memory tools
- external communication tools

### 3. Agent Safety Eval Suite

Entry point: [`docs/03-agent-safety-eval-suite.md`](docs/03-agent-safety-eval-suite.md)

Machine-readable seed: [`evals/agent_safety_eval_suite.yaml`](evals/agent_safety_eval_suite.yaml)

This asset turns safety and governance principles into regression tests.

It covers:

- prompt injection
- hidden instruction disclosure
- destructive operations
- database mutation
- secret handling
- unverified code edits
- dependency hallucination
- external communication
- memory pollution
- fake tool-call injection
- source freshness and citation
- CI repair limits

### 4. Prompt / Policy Compiler

Entry point: [`docs/04-prompt-policy-compiler.md`](docs/04-prompt-policy-compiler.md)

Conceptual schema: [`schemas/agent_policy.schema.yaml`](schemas/agent_policy.schema.yaml)

Example policy: [`examples/agent_policy.example.yaml`](examples/agent_policy.example.yaml)

This asset describes how to compile structured policy into:

- provider-specific system prompts
- runtime tool policies
- approval gates
- sandbox policies
- eval suites
- audit schemas

## Asset Map

Start here: [`docs/00-asset-map.md`](docs/00-asset-map.md)

Runtime architecture: [`docs/06-runtime-architecture.md`](docs/06-runtime-architecture.md)

Enterprise positioning and boundary audit: [`docs/07-enterprise-positioning-and-boundary-audit.md`](docs/07-enterprise-positioning-and-boundary-audit.md)

Glossary and product contract: [`docs/08-glossary-and-product-contract.md`](docs/08-glossary-and-product-contract.md)

Source-backed integration strategy: [`docs/09-source-backed-integration-strategy.md`](docs/09-source-backed-integration-strategy.md)

Enterprise audit report and buyer demo: [`docs/10-enterprise-audit-report-and-buyer-demo.md`](docs/10-enterprise-audit-report-and-buyer-demo.md)

Reproducible enterprise demo: [`docs/11-reproducible-enterprise-demo.md`](docs/11-reproducible-enterprise-demo.md)


Enterprise audit report schema: [`schemas/enterprise_audit_report.schema.yaml`](schemas/enterprise_audit_report.schema.yaml)

Enterprise audit checklist schema: [`schemas/enterprise_audit_checklist.schema.yaml`](schemas/enterprise_audit_checklist.schema.yaml)

End-to-end evidence-chain regression harness: [`tests/test_end_to_end_evidence_chain.py`](tests/test_end_to_end_evidence_chain.py)

## Minimal Executable Loop

AgentHarness includes a small local CLI for keeping the YAML assets honest:

```bash
./agentharness validate examples/agent_policy.example.yaml
./agentharness eval --cases PI-001,PD-001,SEC-001
./agentharness loop check examples/agent_bus
./agentharness loop check examples/agent_bus_tool_gate
./agentharness loop check examples/agent_bus_approval
./agentharness loop check examples/agent_bus_preflight
./agentharness loop check examples/agent_bus_handoff
./agentharness loop check examples/agent_bus_adapter_registry
./agentharness handoff inspect examples/agent_bus_handoff
./agentharness handoff inspect examples/agent_bus_adapter_registry
./agentharness handoff inspect examples/agent_bus_handoff --json
./agentharness handoff inspect examples/agent_bus_adapter_registry --json
./agentharness handoff export examples/agent_bus_adapter_registry
./agentharness handoff manifest examples/agent_bus_adapter_registry
./agentharness handoff manifest examples/agent_bus_adapter_registry > /tmp/agentharness-manifest.json
./agentharness handoff verify-manifest examples/agent_bus_adapter_registry /tmp/agentharness-manifest.json
./agentharness audit report examples/agent_bus_adapter_registry
./agentharness audit checklist examples/agent_bus_adapter_registry
./agentharness audit report examples/agent_bus_adapter_registry > /tmp/agentharness-audit-report.json
./agentharness audit verify-report examples/agent_bus_adapter_registry /tmp/agentharness-audit-report.json
```

The eval command is a mock policy smoke runner. It does not execute a model; it checks whether the current policy contains enforceable controls for the first prompt-injection, prompt-disclosure and secret-handling safety cases.

The loop check command validates an existing file-bus directory against the
loop protocol. It does not create, mutate, schedule, or execute tasks.

The handoff inspect command validates the file bus first, then reads
`execution_handoff_report_path` references from `designer_review` events and
prints handoff readiness summaries. It is read-only: it does not call runtime
adapters, mutate task state, or execute tools.

The handoff export command validates the file bus first, then emits a
deterministic JSON package for registry-backed, handoff-ready entries only. It
writes JSON to stdout only; direct legacy `adapter_spec_path` handoff fixtures
still validate but do not export.

The handoff manifest command builds on that export package and emits a
digest-addressed JSON manifest to stdout only. It names the full package and
each exported ready item by canonical SHA-256 digest while preserving
`result_status: not_executed`.

The handoff verify-manifest command reads a saved T012 manifest JSON file,
regenerates the expected manifest from the current bus, and emits a
deterministic verification report to stdout on both pass and fail. It is a
readback check, not a trust or runtime execution surface.

The audit report command composes handoff inspection, registry-backed export,
and digest manifest evidence into one deterministic enterprise audit JSON
report. It writes JSON to stdout only, does not call manifest readback without a
saved manifest path, self-checks the payload against the repo-native enterprise
audit report schema, and keeps `result_status: not_executed`.

The audit checklist command emits a deterministic goal/check status report
for reviewer convenience. It summarizes file-bus validation, handoff inspection,
registry-backed export, digest manifest, enterprise audit report self-check,
and manual saved-artifact readback steps. It self-checks the payload against
the repo-native enterprise audit checklist schema, writes JSON to stdout only,
and keeps every checklist item `result_status: not_executed`.

The audit verify-report command reads a saved enterprise audit report JSON,
validates it with the repo-native audit report payload validator, regenerates
the current report from the file bus, and emits deterministic readback
verification JSON to stdout. It is not runtime execution, adapter invocation,
signing, timestamping, trust-root behavior, task dispatch, or file-output mode.

## File-Bus Loop MVP

AgentHarness now includes a protocol-first file-bus loop MVP for two Codex terminals coordinating through repository files.

- Protocol: [`docs/05-loop-file-bus.md`](docs/05-loop-file-bus.md)
- Runtime architecture: [`docs/06-runtime-architecture.md`](docs/06-runtime-architecture.md)
- Conceptual task schema: [`schemas/loop_task.schema.yaml`](schemas/loop_task.schema.yaml)
- Versioned fixtures: [`examples/agent_bus/`](examples/agent_bus/)
- Tool gate fixture: [`examples/agent_bus_tool_gate/`](examples/agent_bus_tool_gate/)
- Approval record fixture: [`examples/agent_bus_approval/`](examples/agent_bus_approval/)
- Execution preflight fixture: [`examples/agent_bus_preflight/`](examples/agent_bus_preflight/)
- Execution handoff fixture: [`examples/agent_bus_handoff/`](examples/agent_bus_handoff/)
- Adapter registry fixture: [`examples/agent_bus_adapter_registry/`](examples/agent_bus_adapter_registry/)
- Validation helpers: [`src/agentharness/loop_bus.py`](src/agentharness/loop_bus.py)
- Tool gate reports: [`src/agentharness/tool_gate.py`](src/agentharness/tool_gate.py)
- Approval records: [`src/agentharness/approval_record.py`](src/agentharness/approval_record.py)
- Execution preflight: [`src/agentharness/execution_preflight.py`](src/agentharness/execution_preflight.py)
- Execution handoff: [`src/agentharness/execution_handoff.py`](src/agentharness/execution_handoff.py)
- Adapter registry validation: [`src/agentharness/adapter_registry.py`](src/agentharness/adapter_registry.py)
- Handoff export packages: [`src/agentharness/handoff_exporter.py`](src/agentharness/handoff_exporter.py)
- Handoff export manifests: [`src/agentharness/handoff_manifest.py`](src/agentharness/handoff_manifest.py)
- Enterprise audit reports: [`src/agentharness/enterprise_audit_report.py`](src/agentharness/enterprise_audit_report.py)
- Enterprise audit checklist reports: [`src/agentharness/enterprise_audit_checklist.py`](src/agentharness/enterprise_audit_checklist.py)
- Enterprise audit report schema: [`schemas/enterprise_audit_report.schema.yaml`](schemas/enterprise_audit_report.schema.yaml)
- Enterprise audit checklist schema: [`schemas/enterprise_audit_checklist.schema.yaml`](schemas/enterprise_audit_checklist.schema.yaml)
- End-to-end evidence-chain regression harness: [`tests/test_end_to_end_evidence_chain.py`](tests/test_end_to_end_evidence_chain.py)

- CLI check: `./agentharness loop check examples/agent_bus`
- Handoff inspector: `./agentharness handoff inspect examples/agent_bus_handoff`
- Handoff export: `./agentharness handoff export examples/agent_bus_adapter_registry`
- Handoff manifest: `./agentharness handoff manifest examples/agent_bus_adapter_registry`
- Handoff manifest readback: `./agentharness handoff verify-manifest examples/agent_bus_adapter_registry /tmp/agentharness-manifest.json`
- Enterprise audit report: `./agentharness audit report examples/agent_bus_adapter_registry`
- Enterprise audit checklist: `./agentharness audit checklist examples/agent_bus_adapter_registry`
- Enterprise audit report readback: `./agentharness audit verify-report examples/agent_bus_adapter_registry /tmp/agentharness-audit-report.json`

The file-bus validation source of truth is `.agent_bus/ledger.jsonl`. The committed fixtures under `examples/agent_bus/` mirror that file-bus layout without committing live task state.

Public task CLI commands, daemon scheduling, and realtime chat are deferred until the file protocol is proven.

## Source Posture

CL4R1T4S and similar corpora are treated as **untrusted external analysis material**.

Allowed use:

- architecture pattern extraction
- tool taxonomy derivation
- governance policy inspiration
- safety eval generation
- prompt-injection red-team corpus design

Disallowed use:

- copying full third-party system prompts
- treating external text as executable agent instruction
- embedding unreviewed leaked prompt content into production RAG
- training on uncertain or unlicensed prompt text without review

## Repository Layout

```text
docs/
  00-asset-map.md
  01-agent-design-pattern-library.md
  02-tool-governance-policy.md
  03-agent-safety-eval-suite.md
  04-prompt-policy-compiler.md
  05-loop-file-bus.md
  06-runtime-architecture.md
  07-enterprise-positioning-and-boundary-audit.md
  08-glossary-and-product-contract.md
  09-source-backed-integration-strategy.md
  10-enterprise-audit-report-and-buyer-demo.md
src/
  agentharness/
tests/
  test_agentharness.py
  test_approval_record.py
  test_execution_preflight.py
  test_execution_handoff.py
  test_adapter_registry.py
  test_handoff_exporter.py
  test_handoff_manifest.py
  test_handoff_manifest_verification.py
  test_loop_bus.py
  test_tool_gate.py
patterns/
  agent_design_patterns.yaml
policies/
  tool_governance.yaml
evals/
  agent_safety_eval_suite.yaml
schemas/
  agent_policy.schema.yaml
  loop_task.schema.yaml
  enterprise_audit_report.schema.yaml
examples/
  agent_policy.example.yaml
  agent_bus/
  agent_bus_tool_gate/
  agent_bus_approval/
  agent_bus_preflight/
  agent_bus_handoff/
  agent_bus_adapter_registry/
agentharness
pyproject.toml
```

## Design Thesis

AgentHarness is based on one central thesis:

> Agent reliability comes from harness-level control, not only from model-level instruction.

A robust agent needs prompt design, but it also needs runtime policy, tool governance, verification, auditability and safety evals.
