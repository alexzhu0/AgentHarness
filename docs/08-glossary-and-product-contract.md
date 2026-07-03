# AgentHarness Glossary and Product Contract

last checked date: 2026-06-24

AgentHarness is a pre-execution evidence control-plane for agent actions.

## Scope invariant

AgentHarness validates and exports evidence only; runtimes, governance systems, auth systems, identity systems, sandboxes, and execution planes are external consumers, not AgentHarness in-repo responsibilities.

## Evidence chain

```text
file-bus → tool gate → approval → preflight → handoff → adapter registry → export package → digest manifest → manifest verification
```

This chain is the current product contract for AgentHarness artifacts. Each step remains a validation, summary, inspection, export, digest, or readback surface; none of these steps is runtime execution.

## Glossary

| Canonical term | Definition | Owned by AgentHarness? | Must not mean | Current artifact/source anchor |
| --- | --- | --- | --- | --- |
| control-plane | The pre-execution decision/evidence layer that validates policy, ledger references, approvals, handoffs, exports, manifests, and readback reports. | yes | A runtime, executor, dispatcher, daemon, or live tool caller. | `docs/07-enterprise-positioning-and-boundary-audit.md`, `docs/06-runtime-architecture.md`, `src/agentharness/` validators |
| audit-plane | The reporting surface that makes evidence reviewable and reproducible for platform/security/compliance review. | yes | A trust root, signing system, external compliance product, or source of operational authority. | `docs/07-enterprise-positioning-and-boundary-audit.md`, `src/agentharness/handoff_inspector.py`, `src/agentharness/handoff_manifest.py` |
| execution-plane | The external system that may actually run tools, operate adapters, enforce runtime controls, or perform side effects after consuming evidence. | no | An in-repo AgentHarness responsibility or current CLI surface. | `docs/07-enterprise-positioning-and-boundary-audit.md` external consumer boundary |
| runtime boundary | The separation between AgentHarness evidence eligibility and any downstream system that performs execution, runtime enforcement, identity, authorization, or operations. | boundary-only | A hidden adapter call, live discovery mechanism, or implicit execution permission. | `docs/06-runtime-architecture.md`, `docs/07-enterprise-positioning-and-boundary-audit.md` |
| file-bus | The repository-file protocol used by fixtures to represent tasks, ledger events, evidence, reviews, and referenced reports. | yes | A daemon, queue service, scheduler, or realtime chat bus. | `docs/05-loop-file-bus.md`, `examples/agent_bus/`, `src/agentharness/loop_bus.py` |
| ledger | The append-only JSONL event source used by file-bus validation to determine referenced task/review/evidence state. | yes | A mutable runtime database, task executor, or lifecycle mutation API. | `examples/agent_bus/ledger.jsonl`, `src/agentharness/loop_bus.py` |
| tool request | A structured proposed tool action described as data for routing, approval, preflight, and handoff checks. | boundary-only | A tool call, adapter invocation, subprocess, HTTP request, or side effect. | `examples/agent_bus_tool_gate/tool_gates/`, `src/agentharness/tool_gate.py` |
| tool gate | The side-effect-free routing report that classifies tool requests as allow, approval-required, or deny under current policy. | yes | Permission to execute a tool or proof that a tool already ran. | `src/agentharness/tool_gate.py`, `src/agentharness/tool_router.py`, `examples/agent_bus_tool_gate/` |
| approval record | A user approval/rejection artifact bound to a specific same-attempt approval-required tool request and its digest context. | yes | A lifecycle transition, tool execution receipt, or broad standing authorization. | `src/agentharness/approval_record.py`, `examples/agent_bus_approval/approvals/` |
| preflight | A recomputed readiness report that combines tool-gate status and approval records before any future execution boundary. | yes | An execution command, adapter call, or runtime readiness guarantee. | `src/agentharness/execution_preflight.py`, `examples/agent_bus_preflight/preflight/` |
| eligibility | The control-plane conclusion that a proposed request has enough valid evidence to be considered by a downstream execution-plane consumer. | yes | A command to run, execute, dispatch, submit, or mutate task state. | `src/agentharness/execution_preflight.py`, `src/agentharness/execution_handoff.py` |
| evidence | Validated data artifacts, references, digests, summaries, and reports used to support eligibility review. | yes | Live execution, external identity proof, cryptographic attestation, or trust-root material. | `examples/agent_bus*/evidence/`, `docs/05-loop-file-bus.md` |
| handoff | A read-only control-plane report that binds preflight output to adapter support/digest checks for a future runtime boundary. | yes | A runtime adapter invocation, task submission, or execution-plane dispatch. | `src/agentharness/execution_handoff.py`, `examples/agent_bus_handoff/handoffs/` |
| adapter spec | A static capability document describing what a future adapter can support for `tool_name`, `category`, `intent`, and `target_scope`. | boundary-only | Adapter implementation code, live discovery, import target, or callable runtime object. | `examples/agent_bus_adapter_registry/adapters/pi-tool-call-v0.yaml`, `src/agentharness/execution_handoff.py` |
| adapter registry | A pinned mapping from exact adapter identity/version to adapter spec path and canonical digest. | yes | A plugin manager, package registry, service discovery layer, or adapter loader. | `src/agentharness/adapter_registry.py`, `examples/agent_bus_adapter_registry/adapters/registry.yaml` |
| adapter ref | The handoff reference selecting an adapter registry entry by exact adapter id and strict semantic version, with optional digest cross-check. | yes | A live runtime handle, import path, dependency, or execution target. | `src/agentharness/adapter_registry.py`, `examples/agent_bus_adapter_registry/handoffs/` |
| export package | Deterministic JSON written to stdout for registry-backed, handoff-ready items only. | yes | A file writer, runtime package install, queued job, or task submission. | `src/agentharness/handoff_exporter.py`, `./agentharness handoff export` |
| digest manifest | Deterministic JSON written to stdout that records the canonical export package digest and per-item digests. | yes | A signature, timestamp, attestation, trust root, certificate, or notarization record. | `src/agentharness/handoff_manifest.py`, `./agentharness handoff manifest` |
| manifest verification | A readback report that regenerates the manifest from the current bus and compares the full canonical object plus deterministic mismatch entries. | yes | External trust verification, signature validation, runtime execution, or adapter execution. | `src/agentharness/handoff_manifest.py`, `./agentharness handoff verify-manifest` |
| ready | A control-plane status meaning the evidence chain for a request is valid enough to enter export or manifest surfaces. | yes | Already executed, safe by default, or authorized for any future runtime without external owner review. | `src/agentharness/execution_preflight.py`, `src/agentharness/handoff_exporter.py` |
| blocked | A control-plane status meaning required evidence, approval, policy, digest, or context is missing or invalid. | yes | Runtime failure, tool failure, or a retry command. | `src/agentharness/execution_preflight.py`, `src/agentharness/execution_handoff.py` |
| unsupported | A control-plane status meaning the selected adapter spec does not support one or more request dimensions. | yes | A tool execution error, missing implementation import, or runtime crash. | `src/agentharness/execution_handoff.py`, `examples/agent_bus_adapter_registry/handoffs/` |
| `result_status: not_executed` | The invariant marker that current reports/packages/manifests/verification/audit/readback outputs are evidence-only and did not execute tools or adapters. | yes | A partial execution marker, dry-run side effect, or deferred job id. | `src/agentharness/tool_gate.py`, `src/agentharness/handoff_exporter.py`, `src/agentharness/handoff_manifest.py`, `src/agentharness/enterprise_audit_report.py` |
| external consumer | A downstream runtime, governance, auth, identity, sandbox, or execution-plane system that may read AgentHarness evidence under its own controls. | no | An in-repo AgentHarness module, dependency, or responsibility to run tools. | `docs/07-enterprise-positioning-and-boundary-audit.md` |
| product contract | The accepted boundary that AgentHarness validates/exports evidence while external consumers own execution, enforcement, identity, authorization, and operations. | yes | A promise to build runtime execution, auth gateway, sandboxing, signing, timestamps, attestations, or trust roots in-repo. | This document, `README.md`, `docs/07-enterprise-positioning-and-boundary-audit.md` |

## Product contract

AgentHarness may validate, summarize, inspect, export, digest, and verify evidence.

AgentHarness must not execute tools, call adapters, mutate task lifecycle through public execution commands, run daemons/watchers/schedulers/realtime chat, or act as auth/sandbox/signing/trust-root system.

All current handoff/export/manifest/verification/audit/readback outputs remain `result_status: not_executed`.

Adapter references are versioned evidence bindings, not live runtime discovery.

Downstream runtimes/governance/auth systems are external consumers.

## Naming guidance

Prefer these words when describing AgentHarness-owned behavior:

- evidence
- eligibility
- readback
- manifest verification
- external consumer

Avoid words that imply execution ownership unless explicitly marked external, deferred, or non-goal:

- runner
- executor
- dispatcher
- submission
- daemon
- scheduler
- watcher
- sandbox
- signer
- authority

When these avoided terms appear, they should describe external consumers, deferred work, or non-goals rather than current AgentHarness in-repo responsibilities.

## Future-task guardrails

- T016 integration strategy must cite this glossary:
  [`docs/09-source-backed-integration-strategy.md`](./09-source-backed-integration-strategy.md).
- T017 buyer-demo narrative must use this glossary:
  [`docs/10-enterprise-audit-report-and-buyer-demo.md`](./10-enterprise-audit-report-and-buyer-demo.md).
- Any future runtime spike must first preserve this product contract.
- T018 machine-readable audit report must remain a validate/inspect/export/digest evidence surface, not an execution, auth, sandbox, signing, or trust-root surface.
- T020 enterprise audit report schema must remain a repo-native contract/check for pre-execution evidence payloads, not runtime integration, execution, signing, timestamping, attestation, trust-root, auth, governance enforcement, or file-output behavior.
- T021 audit report readback verification must remain saved-report readback only: it may read a saved JSON report and current bus evidence, but must not become runtime execution, adapter invocation, file-output behavior, signing/timestamping/attestation/trust-root, auth/governance enforcement, dispatch/submit/run/execute, or task mutation.
- T022 audit checklist must remain reviewer-facing goal/check evidence summarization only: it may mark checks pass/fail/blocked/manual, but must not execute manual readbacks without saved paths, write product files, call adapters, or become runtime/governance/auth/sandbox/signing/trust-root enforcement.
- T024 checklist schema validation must remain pure payload contract validation only: it may reject drift in `enterprise_audit_checklist_report`, but must not authorize execution, call adapters, write artifacts, add dependencies, or become signing/trust/governance enforcement.
- T025 end-to-end regression must remain a test harness for the accepted evidence chain: it may compare stage order, counts, canonical digests, and negative drift probes, but must not add a new product command or broaden AgentHarness ownership.
- Future runtime, governance, auth, identity, sandbox, signing, timestamp, attestation, trust-root, daemon, scheduler, watcher, realtime chat, run, execute, dispatch, submit, or task-mutation work must stay behind explicit adapter/spec boundaries until separately approved.
