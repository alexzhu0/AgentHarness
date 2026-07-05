# AgentHarness Enterprise Audit Report and Buyer Demo

last checked date: 2026-06-24

AgentHarness is a pre-execution evidence control-plane for agent actions.

This document uses [`docs/08-glossary-and-product-contract.md`](./08-glossary-and-product-contract.md) as the normative glossary and product contract. It also follows the source-backed external-consumer boundaries in [`docs/09-source-backed-integration-strategy.md`](./09-source-backed-integration-strategy.md).

Current scope invariant: AgentHarness validates and exports evidence only. Runtime, governance, auth, identity, sandbox, signing, trust-root, and execution-plane systems are external consumers, not AgentHarness in-repo responsibilities. All handoff, export, manifest, and verification outputs remain `result_status: not_executed`.

## Audience

This narrative is for enterprise reviewers who need to understand an agent action before any downstream runtime owns execution:

- **Security reviewers** decide whether the proposed action has enough policy, approval, and digest evidence to be considered by a downstream owner.
- **Platform reviewers** decide whether the file-bus, handoff, export, and manifest surfaces are deterministic enough for platform intake.
- **Compliance reviewers** decide whether the evidence is replayable, reviewable, and bounded before operational systems act.
- **Runtime/governance/auth owners** decide, outside AgentHarness, whether their own runtime, governance, identity, authorization, sandbox, and operational controls will consume the evidence.

## One-page buyer-demo narrative

An agent wants to perform a tool action. In a normal runtime-first story, the buyer has to ask after the fact: what was requested, which policy applied, who approved it, whether the target runtime supported it, and whether the record can be replayed.

AgentHarness moves that discussion before execution. It reads a file-bus ledger, validates tool-gate reports, checks approval records, recomputes preflight eligibility, reads handoff reports, validates adapter registry bindings, exports only ready evidence, builds a digest manifest, and verifies manifest readback. The reviewer can see which requests are ready, blocked, or unsupported without any tool being executed.

For the current registry-backed fixture, the reviewer sees five proposed handoffs. Two are ready and exported, two are blocked, and one is unsupported. The exported items are the read-only request `TR-read` and the approval-backed delete request `TR-approve-delete`. The blocked and unsupported requests do not enter the export package.

The downstream runtime, governance, or auth owner remains external. AgentHarness does not replace LangGraph, OpenAI Agents SDK, CrewAI, Microsoft Agent Framework, Microsoft Agent Governance Toolkit, Open Agent Auth, MCP Authorization, or a future execution-plane system. It supplies deterministic pre-execution evidence that those owners may review under their own controls.

No execution has occurred. The current package, manifest, and verification report all keep `result_status: not_executed`.

## Reviewer workflow

A reviewer can follow this read-only workflow from the repository root:

1. **Validate policy**: `PYTHONDONTWRITEBYTECODE=1 ./agentharness validate examples/agent_policy.example.yaml`
2. **Run eval smoke checks**: `PYTHONDONTWRITEBYTECODE=1 ./agentharness eval --cases PI-001,PD-001,SEC-001`
3. **Loop check bus**: `PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check examples/agent_bus_adapter_registry`
4. **Inspect handoff**: `PYTHONDONTWRITEBYTECODE=1 ./agentharness handoff inspect examples/agent_bus_adapter_registry`
5. **Export ready-only package**: `PYTHONDONTWRITEBYTECODE=1 ./agentharness handoff export examples/agent_bus_adapter_registry`
6. **Manifest package**: `PYTHONDONTWRITEBYTECODE=1 ./agentharness handoff manifest examples/agent_bus_adapter_registry > /tmp/agentharness-manifest.json`
7. **Verify manifest readback**: `PYTHONDONTWRITEBYTECODE=1 ./agentharness handoff verify-manifest examples/agent_bus_adapter_registry /tmp/agentharness-manifest.json`
8. **Build machine-readable enterprise audit report**: `PYTHONDONTWRITEBYTECODE=1 ./agentharness audit report examples/agent_bus_adapter_registry > /tmp/agentharness-audit-report.json`
9. **Verify saved audit report readback**: `PYTHONDONTWRITEBYTECODE=1 ./agentharness audit verify-report examples/agent_bus_adapter_registry /tmp/agentharness-audit-report.json`
10. **Review goal/check checklist**: `PYTHONDONTWRITEBYTECODE=1 ./agentharness audit checklist examples/agent_bus_adapter_registry`
11. **Decide whether evidence is acceptable for external runtime owner review**: approve or reject the evidence package for downstream review without treating AgentHarness as the execution owner.

This workflow validates, inspects, exports, digests, verifies, and summarizes evidence only. The checklist is a reviewer convenience report over existing evidence builders, not a new runtime step. It does not call adapters, execute tools, mutate task lifecycle, or write product artifacts from AgentHarness export/manifest/audit commands.

## Evidence-chain walkthrough

| Evidence step | What the reviewer learns | Current boundary |
| --- | --- | --- |
| file-bus | The ledger-backed request and report references exist in a deterministic bus layout. | Validation source of truth, not a scheduler or live queue. |
| tool gate | The requested tool action is classified as allowed, approval-required, or denied by policy. | Side-effect-free report, not permission to execute. |
| approval record | Approval-required requests are bound to a same-attempt approval decision and digest context. | Evidence binding, not broad standing authorization. |
| preflight | Tool-gate and approval facts are recomputed into ready or blocked eligibility. | Pre-execution readiness, not runtime execution. |
| handoff | Preflight output is bound to adapter support checks and `result_status: not_executed`. | Read-only boundary report, not adapter invocation. |
| adapter registry | Adapter refs are selected by exact id/version and checked against registry/spec digests. | Versioned evidence binding, not package discovery or runtime loading. |
| export package | Only registry-backed, handoff-ready items are emitted to deterministic stdout JSON. | Ready-only evidence, not task submission. |
| digest manifest | The export package and each item are named by canonical SHA-256 digest. | Digest readback material, not signing, timestamping, attestation, or trust-root proof. |
| manifest verification | A saved manifest is regenerated from current bus state and compared deterministically. | Readback check, not external trust verification or execution. |

## Embedded audit report examples

These examples use `examples/agent_bus_adapter_registry` and are illustrative documentation, not a new audit-report schema or fixture. T018 added the separate read-only `audit report` CLI described below; the embedded examples remain explanatory narrative.

### Summary

| Field | Value |
| --- | --- |
| reports | 1 |
| total_handoffs | 5 |
| handoff_ready/exported | 2 |
| blocked | 2 |
| unsupported | 1 |
| result_status | not_executed |

Compact report line: `reports=1 total_handoffs=5 handoff_ready/exported=2 blocked=2 unsupported=1 result_status=not_executed`.

### ready/no-approval: TR-read

- Request id: `TR-read`
- Tool: `read_file`
- Category: `file_read`
- Intent: `inspect_workspace`
- Target scope: `repository`
- Handoff status: `handoff_ready`
- Preflight status: `ready_without_approval`
- Exported: yes
- Result status: `not_executed`

Buyer interpretation: this request is ready because policy and adapter support allow a read-only handoff without an approval record. It is still evidence-only; no file read has been executed by AgentHarness.

### ready/approval-backed: TR-approve-delete

- Request id: `TR-approve-delete`
- Tool: `delete_file`
- Category: `file_delete`
- Intent: `delete_file`
- Target scope: `repository`
- Handoff status: `handoff_ready`
- Preflight status: `ready_with_approval`
- Exported: yes
- Result status: `not_executed`

Buyer interpretation: this request is ready because the approval-required delete action has matching approval evidence and adapter support. It is still evidence-only; a downstream runtime owner must separately decide whether to execute under its own controls.

### unsupported: TR-read-unsupported-intent

- Request id: `TR-read-unsupported-intent`
- Tool: `read_file`
- Category: `file_read`
- Intent: `inspect_config`
- Target scope: `repository`
- Handoff status: `unsupported`
- Preflight status: `ready_without_approval`
- Exported: no
- Result status: `not_executed`

Buyer interpretation: the policy/preflight side may be ready, but the selected adapter spec does not support the request dimensions. AgentHarness excludes it from the ready-only export package.

### blocked/missing approval: TR-missing-approval-delete

- Request id: `TR-missing-approval-delete`
- Tool: `delete_file`
- Category: `file_delete`
- Intent: `delete_file`
- Target scope: `repository`
- Handoff status: `blocked`
- Preflight status: `blocked_missing_approval`
- Exported: no
- Result status: `not_executed`

Buyer interpretation: the delete request is blocked because approval-required evidence is missing or invalid. It cannot enter export until the evidence chain is repaired.

### blocked/policy-denied: TR-deny-unknown

- Request id: `TR-deny-unknown`
- Tool: `mystery_shell`
- Category: `shell`
- Intent: `run_tests`
- Target scope: `repository`
- Handoff status: `blocked`
- Preflight status: `blocked_by_policy`
- Exported: no
- Result status: `not_executed`

Buyer interpretation: the proposed shell-like request is policy-denied. AgentHarness reports it as blocked and excludes it from export.

### manifest/readback: package digest and verify ok:true

The current registry-backed manifest names the ready-only export package with this canonical digest:

```text
package_digest: sha256:63806cd94fb4a5b012a2b79e7bbef1c5068009a972a73ae26dc72ef04a010965
```

The manifest items preserve the ready request order:

1. `TR-read`
2. `TR-approve-delete`

A matching saved manifest verifies with `ok: true`, an empty errors list, and `result_status: not_executed`. That means the reviewer can regenerate the manifest from current bus state and prove the saved readback still matches the expected package and item structure.

## T018/T020 machine-readable enterprise audit report

T018 adds a read-only command for this narrative:

```bash
./agentharness audit report examples/agent_bus_adapter_registry
```

The command emits deterministic JSON to stdout with `kind: enterprise_audit_report`. It composes existing handoff inspection, registry-backed export package, and digest manifest evidence. It does not call `handoff verify-manifest`, because saved-manifest readback requires a separate manifest path. Instead, the report includes `manifest_verification` as a boundary note with `performed: false`, `reason: requires_saved_manifest_path`, and `result_status: not_executed`.

Failure output uses `kind: enterprise_audit_report_error`, exits 1, and keeps sanitized errors/warnings free of absolute host paths. The command has no `--out`, `--write`, `--save`, `--execute`, `--dispatch`, `--submit`, `--run`, `--mutate`, `--sign`, or `--timestamp` flags.

T020 adds the repo-native enterprise audit report schema at
[`schemas/enterprise_audit_report.schema.yaml`](../schemas/enterprise_audit_report.schema.yaml)
and a pure in-memory payload validator. The schema is a contract/check for the
pre-execution evidence report; it is not runtime integration, not execution,
not signing, not timestamping, not attestation, not a trust-root system, and not
file-output behavior. Successful audit payloads continue to omit top-level
`ok`, and both success/error payloads continue to require
`result_status: not_executed`.

T021 adds saved-report readback verification:

```bash
./agentharness audit report examples/agent_bus_adapter_registry > /tmp/agentharness-audit-report.json
./agentharness audit verify-report examples/agent_bus_adapter_registry /tmp/agentharness-audit-report.json
```

The verifier reads the saved `enterprise_audit_report` JSON, validates it with
the T020 payload validator, regenerates the current report from the file bus,
and compares canonical JSON/digests. It emits
`enterprise_audit_report_verification_report` JSON to stdout on pass and fail.
This is readback verification only: it is not runtime execution, not runtime
adapter invocation, not file-output behavior, not signing/timestamping,
attestation, certificate, notarization, or trust-root proof, not auth/identity/
sandbox/governance enforcement, and not dispatch, submit, run, execute, or task
mutation.

T022 adds a read-only reviewer checklist:

```bash
./agentharness audit checklist examples/agent_bus_adapter_registry
```

The checklist emits `enterprise_audit_checklist_report` JSON to stdout only.
It orders the reviewer goals as file-bus validation, handoff inspection,
registry-backed export, digest manifest, enterprise audit report self-check,
and two manual saved-artifact readback checks. Manual means the readback needs a
reviewer-provided saved manifest or audit report path; AgentHarness does not
create that file through a product output flag. Checklist statuses are limited
to `pass`, `fail`, `blocked`, and `manual`, and every check keeps
`result_status: not_executed`. T024 adds the repo-native checklist schema at
[`schemas/enterprise_audit_checklist.schema.yaml`](../schemas/enterprise_audit_checklist.schema.yaml)
and a pure in-memory validator; this is payload drift protection, not runtime
authorization, signing, trust-root, governance enforcement, or file output.

For a copy-paste reviewer demo using the existing commands and fixture, see [`docs/11-reproducible-enterprise-demo.md`](./11-reproducible-enterprise-demo.md).

## Buyer-demo talk track

1. **Start with the buyer pain**: agent systems can propose high-impact tool actions, but reviewers need deterministic evidence before a runtime acts.
2. **Show the boundary**: AgentHarness is not the runtime; it is the pre-execution evidence control-plane that prepares a reviewable package.
3. **Walk the evidence chain**: file-bus, tool gate, approval, preflight, handoff, adapter registry, export package, digest manifest, and manifest verification.
4. **Highlight the split outcome**: in the example, two requests are ready/exported, two are blocked, and one is unsupported; blocked and unsupported items do not leak into the export package.
5. **Explain replayability**: the manifest can be saved and verified later; if the bus or registry changes, readback detects drift.
6. **Name external owners**: runtime, governance, auth, identity, sandbox, and execution-plane teams keep their own enforcement responsibilities.
7. **Close with value**: AgentHarness gives platform/security/compliance reviewers deterministic pre-execution evidence, approval binding, ready-only export, and replayable manifests without expanding into execution.

## Objections and answers

| Objection | Answer |
| --- | --- |
| Is this a runtime? | No. AgentHarness validates and exports pre-execution evidence only. |
| Does it replace LangGraph/OpenAI Agents SDK/CrewAI/MAF? | No. Those are external runtime/orchestration consumers; AgentHarness can supply evidence before their owners act. |
| Does it enforce auth/governance/sandboxing? | No. It supplies evidence to external governance, auth, identity, sandbox, and runtime owners. |
| Can it execute tools? | No. Current handoff/export/manifest/verification output remains `result_status: not_executed`. |
| Why is it valuable? | It gives deterministic pre-execution evidence, ready-only exclusion, approval binding, and replayable manifests that reviewers can inspect before downstream systems decide anything. |

## Red-line boundaries

T017 did not add runtime behavior. T018 adds only a read-only, stdout-only machine-readable audit report command. T020 adds only a repo-native conceptual schema and pure payload validation. T021 adds only saved-report readback verification. T022 adds only a read-only, stdout-only goal/check checklist report. T024 adds only repo-native checklist schema validation. T025 adds only a regression harness for the accepted evidence chain. They still do not add or imply:

- audit-report file writing, saved output flag, or product example artifact;
- runtime execution;
- runtime adapter invocation;
- future execution-plane repository modification, import, dependency, test, or call;
- daemon, scheduler, watcher, queue, or realtime chat;
- run, execute, dispatch, submit, or task-mutation CLI;
- lifecycle state expansion;
- auth gateway, identity provider, sandbox, signing, timestamp, attestation, or trust-root implementation;
- SDK/package adoption or framework wrapper implementation.

## Future follow-ups

- Add a later evidence-envelope schema only if buyers and reviewers need a stable external interchange contract beyond the accepted enterprise audit report schema.
- Keep runtime spikes deferred behind explicit adapter/spec boundaries and the product contract in [`docs/08-glossary-and-product-contract.md`](./08-glossary-and-product-contract.md).
- Use the T025 end-to-end evidence-chain regression harness as a guard before accepting later contract changes.
- T016 and T017 may be committed together later only after user acceptance.
