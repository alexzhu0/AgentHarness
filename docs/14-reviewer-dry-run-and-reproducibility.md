# AgentHarness Reviewer Dry-Run and Reproducibility

AgentHarness is a pre-execution evidence control-plane for agent actions.

This document records a local reviewer-style dry-run showing that the golden `examples/agent_bus_adapter_registry` evidence package can be reproduced from committed fixtures and checked against the external reviewer checklist.

This is evidence acceptance, not runtime approval. AgentHarness does not execute tools, invoke runtime adapters, approve runtime action, write product artifacts, or decide whether anything is safe to execute. All current evidence/report outputs remain `result_status: not_executed`.

## Baseline and scope

| Field | Value |
| --- | --- |
| baseline commit | `2f12bc9ad40f739dde9a64c21e6f4fddb4bf9428` (`Give external reviewers an evidence acceptance rubric`) |
| fixture | `examples/agent_bus_adapter_registry` |
| dry-run date | 2026-07-05 |
| reviewer-owned saved artifacts | `/tmp/agentharness-t030-*.json` and `/tmp/agentharness-t030-*.txt` |
| product output behavior | stdout-only; `/tmp` files are created by reviewer shell redirection, not by AgentHarness output-writer flags |
| decision documents | [`docs/11-reproducible-enterprise-demo.md`](./11-reproducible-enterprise-demo.md), [`docs/12-buyer-reviewer-decision-guide.md`](./12-buyer-reviewer-decision-guide.md), [`docs/13-external-reviewer-checklist.md`](./13-external-reviewer-checklist.md) |

The observed counts in this document are for the current golden demo fixture. They are not universal requirements for every future evidence package.

## Reviewer copy-paste dry-run

Run from the AgentHarness repository root. No network is required; the commands use committed fixtures and the local Python environment.

```bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
rm -f /tmp/agentharness-t030-*.json /tmp/agentharness-t030-*.txt

./agentharness validate examples/agent_policy.example.yaml | tee /tmp/agentharness-t030-policy.txt
./agentharness eval --cases PI-001,PD-001,SEC-001 | tee /tmp/agentharness-t030-eval.txt
./agentharness loop check examples/agent_bus_adapter_registry | tee /tmp/agentharness-t030-loop.txt
./agentharness handoff inspect examples/agent_bus_adapter_registry | tee /tmp/agentharness-t030-inspect.txt
./agentharness handoff export examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-t030-export.json
./agentharness handoff manifest examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-t030-manifest.json
./agentharness handoff verify-manifest examples/agent_bus_adapter_registry /tmp/agentharness-t030-manifest.json | python3 -m json.tool >/tmp/agentharness-t030-verify-manifest.json
./agentharness audit report examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-t030-audit-report.json
./agentharness audit verify-report examples/agent_bus_adapter_registry /tmp/agentharness-t030-audit-report.json | python3 -m json.tool >/tmp/agentharness-t030-verify-report.json
./agentharness audit checklist examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-t030-checklist.json
python3 -m unittest -q tests.test_end_to_end_evidence_chain | tee /tmp/agentharness-t030-e2e.txt
```

The `/tmp/agentharness-t030-*` files are reviewer-owned saved artifacts. They are useful for readback checks, but they are not written by AgentHarness product output flags.

## Expected vs observed

| Evidence link | Expected | Observed dry-run result |
| --- | --- | --- |
| Policy validation | pass | `PASS policy validation: examples/agent_policy.example.yaml` |
| Smoke eval | `3/3` pass | `Summary: 3/3 smoke evals passed` |
| Loop check | pass | `PASS loop bus validation: examples/agent_bus_adapter_registry` |
| Handoff inspection | `reports=1`, `total=5`, `handoff_ready=2`, `blocked=2`, `unsupported=1`, `result_status=not_executed` | matched exactly |
| Export package | `total_handoffs=5`, `exported=2`, `blocked=2`, `unsupported=1`, `result_status=not_executed` | matched; exported IDs: `TR-read`, `TR-approve-delete` |
| Digest manifest | `items=2`, same ready request IDs, `result_status=not_executed` | matched; items: `TR-read`, `TR-approve-delete` |
| Manifest verification | `ok=true`, `matched=2`, `missing=0`, `extra=0`, `result_status=not_executed` | matched; `errors=[]` |
| Enterprise audit report | `reports=1`, `total_handoffs=5`, `handoff_ready=2`, `exported=2`, `blocked=2`, `unsupported=1`, `result_status=not_executed` | matched |
| Audit report verification | `ok=true`, `matched_handoffs=5`, `missing_handoffs=0`, `extra_handoffs=0`, `result_status=not_executed` | matched; `errors=[]`, `warnings=[]` |
| Enterprise audit checklist | `checks=7`, `passed=5`, `manual=2`, `failed=0`, `blocked=0` | matched; check IDs listed below |
| T025 harness | `7 tests OK` | `Ran 7 tests ... OK` |

Stable fixture totals observed: `reports=1`, `total_handoffs=5`, `handoff_ready=2`, `exported=2`, `blocked=2`, `unsupported=1`, checklist `checks=7`, checklist `passed=5`, checklist `manual=2`.

## Request ID coverage

| Request ID | Dry-run status | Reviewer interpretation |
| --- | --- | --- |
| `TR-read` | ready/exported | Read-only request is eligible evidence for downstream review; it is not executed. |
| `TR-approve-delete` | approval-backed ready/exported | Approval evidence is present, so it is eligible evidence for downstream review; it is not executed. |
| `TR-read-unsupported-intent` | unsupported/excluded | Adapter support is insufficient for this intent, so it is not exported. |
| `TR-missing-approval-delete` | blocked/excluded | Required approval evidence is missing, so it is not exported. |
| `TR-deny-unknown` | policy-denied blocked/excluded | Policy blocks the unknown/shell-like request, so it is not exported. |

## Checklist result details

The enterprise audit checklist returned `ok=true` and these ordered checks:

| Check ID | Status |
| --- | --- |
| `file_bus_validation` | `pass` |
| `handoff_inspection` | `pass` |
| `registry_backed_export` | `pass` |
| `digest_manifest` | `pass` |
| `enterprise_audit_report` | `pass` |
| `saved_manifest_readback` | `manual` |
| `saved_audit_report_readback` | `manual` |

The two manual checks are expected: reviewers provide the saved manifest and saved audit report paths, then run the readback commands.

## Reviewer decision mapping

Use [`docs/13-external-reviewer-checklist.md`](./13-external-reviewer-checklist.md) to map the dry-run to one of three outcomes. This section applies the checklist from docs/13; docs/13 remains the canonical reviewer rubric.

### Accept evidence for downstream review

For the golden dry-run, the correct result is: **Accept evidence for downstream review**.

Reason: validation, smoke evals, loop check, handoff inspection, registry-backed export, digest manifest, manifest readback, enterprise audit report, audit report readback, checklist, and T025 harness all reproduced the expected evidence. Ready/exported items are separated from blocked and unsupported items, and all current outputs remain `result_status: not_executed`.

This means the evidence package is acceptable as input for external runtime/governance/auth/sandbox/signing/trust-root owner review. It is not runtime approval, not execution approval, and not a safety guarantee.

### Reject evidence package

Reject the evidence package if the same dry-run shows any of these conditions:

- policy validation, smoke eval, or loop check fails;
- handoff inspection cannot separate ready, blocked, and unsupported outcomes;
- export includes `TR-read-unsupported-intent`, `TR-missing-approval-delete`, `TR-deny-unknown`, or any other blocked/unsupported item;
- manifest readback or audit report readback returns `ok=false`;
- audit report or checklist schema validation fails;
- counts, request IDs, item order, or digests drift unexpectedly;
- reviewer-facing output leaks raw local host paths;
- any current output changes away from `result_status: not_executed`;
- docs or artifacts claim AgentHarness executed, dispatched, submitted, approved, or made a runtime safety decision.

### Escalate externally

Escalate externally when the question is outside AgentHarness evidence ownership, including:

- whether a downstream runtime should actually execute a ready request;
- whether the action is safe in a production environment;
- identity, authorization, approval authority, sandbox, deployment, operations, signing, timestamp, attestation, certificate, trust-root, or long-term evidence custody;
- whether unsupported adapter coverage should be added in a future external runtime/adapter plan.

External escalation does not create a new AgentHarness lifecycle state.

## Failure triage

| Failed link | First thing to inspect | Evidence decision |
| --- | --- | --- |
| Policy validation failure | `examples/agent_policy.example.yaml` and validation output | Reject evidence package until policy input is valid. |
| Smoke eval failure | Failed `PI-001`, `PD-001`, or `SEC-001` line | Reject evidence package; safety controls are not demonstrated. |
| Loop check failure | `.agent_bus` files and loop validation error | Reject evidence package; bus evidence is not trustworthy. |
| Handoff inspect failure | Handoff report references and sanitized inspect errors | Reject evidence package if inspection cannot classify handoffs. |
| Export failure | Registry-backed handoff and adapter registry validation | Reject if ready-only export cannot be produced; escalate only for external adapter coverage questions. |
| Manifest readback failure | `/tmp/agentharness-t030-verify-manifest.json` errors | Reject saved manifest as stale/tampered/malformed until readback passes. |
| Audit report failure | Audit report error JSON and schema validator errors | Reject evidence package if the report cannot be built or validated. |
| Audit report readback failure | `/tmp/agentharness-t030-verify-report.json` errors | Reject saved report as stale/tampered/malformed until readback passes. |
| Checklist fail or blocked | Failed/blocked checklist rows | Reject evidence package unless the row clearly points to an external-owner question. |
| Checklist manual rows | Saved manifest/report paths supplied by reviewer | Continue manual readback; do not treat manual as AgentHarness execution. |
| T025 harness failure | `tests.test_end_to_end_evidence_chain` failure | Treat the evidence chain as not release-ready and open a separate repair task. |
| Path leak | Raw `/home`, `/tmp`, Windows, or UNC path inside reviewer-facing payload | Reject reviewer artifact; fix sanitization in a separate task. |
| Wrong `result_status` | Any `executed`, `completed`, or runtime-like status | Reject evidence package; current outputs must remain `not_executed`. |

## Remaining gaps

- The dry-run is based on the current golden fixture only; it does not certify future fixtures.
- `/tmp` files are reviewer-owned saved artifacts; AgentHarness still has no product writer flag.
- Manual readback remains manual because reviewers must choose saved manifest/report paths.
- Runtime execution, safety approval, authorization, sandboxing, signing, timestamping, attestation, trust-root, deployment, and operations remain external-owner responsibilities.
- An independent external human reviewer trial has not happened yet unless separately recorded.
- Commit/push/release packaging is a separate decision.
- Runtime-boundary or `/pi` integration remains a separate future spike and is not part of T030.

## Boundary reminder

T030 hardens reproducibility documentation only. It does not add scripts, helpers, source code, tests, schemas, fixtures, CLI flags, runtime adapter invocation, daemon/scheduler/watcher/realtime chat, task mutation, lifecycle state, auth gateway, sandbox, signing, timestamp, attestation, trust-root, or governance enforcement.

For the development-loop process used by future T0xx tasks, see [`docs/15-agentharness-development-loop-operating-model.md`](./15-agentharness-development-loop-operating-model.md).
