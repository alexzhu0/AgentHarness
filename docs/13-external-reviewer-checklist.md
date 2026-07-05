# AgentHarness External Reviewer Checklist

AgentHarness remains a pre-execution evidence control-plane.

This checklist is for security, platform, and compliance reviewers evaluating AgentHarness evidence before any downstream owner acts. It turns the current evidence chain into an operational rubric for deciding whether an evidence package should be accepted for downstream review, rejected, or escalated externally.

This is evidence acceptance, not runtime approval. AgentHarness does not approve runtime action, does not execute tools, and does not make safety guarantees for downstream execution.

Ready does not mean executed. Ready does not mean safe to execute. All current result_status outputs remain not_executed.

## Scope and audience

Use this checklist when reviewing the evidence generated from an AgentHarness file-bus fixture, especially the `examples/agent_bus_adapter_registry` demo flow.

The reviewer is checking whether the evidence package is complete, deterministic, internally consistent, traceable, and boundary-safe enough for an external owner to review. The checklist is not a runtime authorization process, not a governance decision engine, not an auth or identity system, not a sandbox policy, and not a signing, timestamp, attestation, certificate, or trust-root flow.

## Reviewer outcome definitions

Outcomes are:

1. **Accept evidence for downstream review**
   - The evidence package is complete, deterministic, internally consistent, and traceable enough for external owner review.
   - This is not execution approval and not runtime approval.
   - The package still represents pre-execution evidence; all current outputs remain `result_status: not_executed`.

2. **Reject evidence package**
   - Evidence is missing, malformed, stale, inconsistent, path-leaking, non-deterministic, contains wrong `result_status`, exports blocked or unsupported items, or violates the schema/product contract.
   - This is not a runtime failure; it is an evidence decision.

3. **Escalate externally**
   - The question belongs to a runtime, governance, auth, identity, sandbox, signing, timestamp, attestation, trust-root, deployment, or operations owner.
   - This is not an AgentHarness lifecycle state.

## Reviewer checklist table

| Check ID | Reviewer question | Evidence source / command | Accept condition | Reject condition | Escalate condition |
| --- | --- | --- | --- | --- | --- |
| `R1_artifact_completeness` | Are all expected evidence artifacts present? | Demo flow in [`docs/11-reproducible-enterprise-demo.md`](./11-reproducible-enterprise-demo.md), saved reviewer artifacts, and this checklist. | Required artifacts are present: validation/eval output, loop check, handoff inspection, export package, digest manifest, manifest readback, audit report, audit report readback, audit checklist, and T025 harness result when available. | Any required artifact is missing, unreadable, malformed, or from the wrong fixture/run. | Escalate if an external owner requires additional production records outside AgentHarness evidence. |
| `R2_policy_and_bus_validation` | Did policy validation, smoke evals, and file-bus validation pass? | `./agentharness validate`, `./agentharness eval --cases PI-001,PD-001,SEC-001`, `./agentharness loop check examples/agent_bus_adapter_registry`. | Policy validation passes, smoke evals are 3/3, and loop check passes for the reviewed bus. | Any validation fails, reports malformed input, or cannot be reproduced. | Escalate if policy acceptance itself belongs to a governance owner. |
| `R3_handoff_readiness_split` | Are ready, blocked, and unsupported handoffs separated? | `./agentharness handoff inspect examples/agent_bus_adapter_registry`, audit report handoff rows. | Ready/exported, blocked, and unsupported items are distinguishable and match the expected reviewed evidence. | Blocked or unsupported items are unclear, missing, or misclassified as ready. | Escalate if adapter coverage or production intent classification is owned externally. |
| `R4_approval_binding` | Is approval-required evidence present where needed? | Handoff inspection, preflight evidence, approval records, enterprise audit report rows. | Approval-backed readiness is present for approval-required ready items, and missing approval blocks the relevant item. | Approval-required item is ready/exported without required approval evidence, or approval evidence is malformed/stale. | Escalate if approval authority or approval policy belongs to an external governance owner. |
| `R5_adapter_registry_binding` | Is adapter/spec evidence registry-backed and digest-bound? | Registry-backed export package, adapter registry validation, digest manifest, audit report manifest section. | Adapter ref selects an active exact version, registry digest matches the canonical adapter spec, and paths remain within bus scope. | Registry entry is missing, disabled, deprecated for selection, digest-mismatched, path-traversing, or otherwise invalid. | Escalate if the runtime adapter coverage question exceeds current registry evidence. |
| `R6_export_exclusion_safety` | Did export include only ready handoffs? | `./agentharness handoff export examples/agent_bus_adapter_registry`, audit report export section. | Exported request IDs are only handoff-ready items; blocked and unsupported items are excluded. | Any blocked or unsupported request appears in the export package. | Escalate if an external owner asks whether an excluded item should be supported in a future adapter. |
| `R7_manifest_readback` | Does the saved digest manifest match regenerated evidence? | `agentharness handoff verify-manifest <bus_root> <manifest_path>`. | Verification report returns `ok: true`, matching item order and digests, with `result_status: not_executed`. | Saved manifest is stale, missing items, has extra/reordered/tampered items, malformed JSON, wrong digest, or wrong `result_status`. | Escalate if reviewer requires signing, timestamp, attestation, or trust-root material. |
| `R8_audit_report_contract` | Does the enterprise audit report match the accepted contract? | `./agentharness audit report examples/agent_bus_adapter_registry`, [`schemas/enterprise_audit_report.schema.yaml`](../schemas/enterprise_audit_report.schema.yaml). | Report is deterministic, schema-valid, path-sanitized, and preserves expected summary/export/manifest evidence. | Report is malformed, schema-drifted, contains unexpected writer/runtime fields, leaks raw local paths, or claims execution. | Escalate if a production audit system requires additional external fields or controls. |
| `R9_audit_report_readback` | Does the saved audit report match regenerated current evidence? | `agentharness audit verify-report <bus_root> <audit_report_path>`. | Verification report returns `ok: true`, matching canonical report digest and handoff rows. | Saved report is stale, tampered, missing/extra/reordered, schema-invalid, path-leaking, or has mismatched digest. | Escalate if long-term retention, signing, timestamp, or evidence custody is an external compliance concern. |
| `R10_checklist_goal_status` | Does the enterprise audit checklist summarize pass/fail/blocked/manual status correctly? | `./agentharness audit checklist examples/agent_bus_adapter_registry`, [`schemas/enterprise_audit_checklist.schema.yaml`](../schemas/enterprise_audit_checklist.schema.yaml). | Checklist has `ok: true`, goal status is pass, expected check IDs are ordered, passed/manual counts are coherent. | Checklist has failed/blocked checks, schema drift, unordered/missing IDs, malformed status, or unsanitized errors. | Escalate if manual reviewer context cannot be supplied inside AgentHarness evidence. |
| `R11_result_status_invariant` | Do all current outputs remain pre-execution evidence? | Handoff inspection, export, manifest, verification, audit report, audit verification, audit checklist, T025 harness. | Every current handoff/export/manifest/verification/audit/checklist output uses `result_status: not_executed`. | Any output contains executed/completed/runtime execution status or implies a side effect occurred. | Escalate if downstream runtime status is required; AgentHarness does not own it. |
| `R12_path_sanitization` | Do reviewer-facing outputs avoid raw local host paths? | `handoff inspect`, `handoff inspect --json`, audit report errors/warnings, verification reports. | Reviewer-facing artifacts contain no raw `/home`, `/tmp`, Windows drive, UNC, or host-specific path leaks except reviewer-owned shell paths outside the payload. | Any text/JSON payload leaks raw local paths, temp paths, or host-specific workspace paths. | Escalate if external evidence custody requires a separate redaction or DLP process. |
| `R13_manual_checks_recorded` | Are manual checks explicit and reviewer-owned? | Audit checklist manual rows and saved readback commands. | Manual items clearly list saved manifest and saved audit report readback commands, and the reviewer supplies paths. | Manual checks are hidden, skipped, or described as AgentHarness execution/approval. | Escalate if external context is required to interpret manual evidence. |
| `R14_boundary_non_claims` | Does the evidence avoid runtime, safety, and enforcement claims? | Product contract, docs/12, this checklist, audit report boundary fields. | Wording says accept evidence for downstream review, reject evidence package, or escalate externally; it does not claim execution approval or safety. | Output or docs claim AgentHarness executes, dispatches, submits, approves runtime action, guarantees safety, or enforces governance/auth/sandbox/signing/trust-root controls. | Escalate all execution, authorization, sandbox, signing, deployment, and operations decisions to external owners. |

## Evidence package completeness

A reviewer should expect the evidence package to include:

- policy validation / smoke eval evidence;
- file-bus validation;
- handoff inspection summary;
- registry-backed export package;
- digest manifest;
- manifest verification/readback;
- enterprise audit report;
- audit report verification/readback;
- enterprise audit checklist;
- T025 end-to-end harness result, when available.

The copy-paste flow in [`docs/11-reproducible-enterprise-demo.md`](./11-reproducible-enterprise-demo.md) shows how to produce the current demo artifacts from existing commands.

## Accepted fixture counts

For the current golden demo fixture `examples/agent_bus_adapter_registry`, expected counts are:

| Field | Expected fixture value |
| --- | --- |
| `reports` | `1` |
| `total_handoffs` | `5` |
| ready / exported | `2` |
| blocked | `2` |
| unsupported | `1` |
| checklist checks | `7` |
| checklist passed | `5` |
| checklist manual | `2` |
| T025 harness | `7 tests OK` |

These are demo-fixture expectations, not universal requirements for every future evidence package.

## Reject triggers

Reject evidence package when any of these are true:

- a required artifact is missing;
- JSON or YAML is invalid, malformed, or schema-drifted;
- manifest or audit report readback is stale or mismatched;
- output is non-deterministic where determinism is expected;
- any current output has wrong `result_status`, especially anything other than `not_executed`;
- blocked or unsupported item appears in the export package;
- approval-required item is missing approval evidence;
- adapter registry binding is invalid, disabled for selection, deprecated for selection, digest-mismatched, or path-traversing;
- reviewer-facing output has a raw local path leak, host-specific path, or unsanitized temp path;
- output claims execution, dispatch, submission, runtime approval, or a safety guarantee.

## External escalation triggers

Escalate externally when the question is about:

- identity, auth, or authorization decision;
- sandbox policy;
- signing, timestamp, attestation, certificate, notarization, or trust-root material;
- deployment or production operations policy;
- runtime adapter coverage beyond current registry evidence;
- whether a downstream runtime should actually execute;
- any real-world side-effect risk not answerable from current evidence.

External escalation routes the question to the responsible runtime, governance, auth, identity, sandbox, signing, trust-root, deployment, or operations owner. It does not create a new AgentHarness lifecycle state.

## Manual checks

Manual means reviewer-supplied saved artifacts or external context, not AgentHarness execution or approval.

Current manual readback commands are:

```bash
agentharness handoff verify-manifest <bus_root> <manifest_path>
agentharness audit verify-report <bus_root> <audit_report_path>
```

A manual check can still be required even when all generated evidence is deterministic. The reviewer supplies the saved manifest or audit report path and compares it with regenerated current evidence.

## Copy-paste reviewer mini-loop

Run from the AgentHarness repository root:

```bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

./agentharness validate examples/agent_policy.example.yaml
./agentharness eval --cases PI-001,PD-001,SEC-001
./agentharness loop check examples/agent_bus_adapter_registry
./agentharness handoff inspect examples/agent_bus_adapter_registry
./agentharness handoff export examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-review-export.json
./agentharness handoff manifest examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-review-manifest.json
./agentharness handoff verify-manifest examples/agent_bus_adapter_registry /tmp/agentharness-review-manifest.json | python3 -m json.tool >/tmp/agentharness-review-verify-manifest.json
./agentharness audit report examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-review-audit-report.json
./agentharness audit verify-report examples/agent_bus_adapter_registry /tmp/agentharness-review-audit-report.json | python3 -m json.tool >/tmp/agentharness-review-verify-report.json
./agentharness audit checklist examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-review-checklist.json
python3 -m unittest -q tests.test_end_to_end_evidence_chain
```

The `/tmp/agentharness-review-*.json` files are created by reviewer shell redirection, not by an AgentHarness output-writer flag. They are reviewer-side saved artifacts for readback.

## Anti-claims / wording guardrail

Do not say:

- approved for execution;
- safe to execute;
- ready means executed;
- ready means safe to execute;
- AgentHarness approves execution;
- AgentHarness enforces governance, auth, identity, sandbox, signing, timestamping, attestation, trust-root, deployment, or operations controls;
- AgentHarness is a runtime, scheduler, adapter loader, queue, or execution plane.

Use evidence wording instead:

- Accept evidence for downstream review;
- Reject evidence package;
- Escalate externally.
