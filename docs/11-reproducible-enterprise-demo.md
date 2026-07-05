# AgentHarness Reproducible Enterprise Demo

AgentHarness is a pre-execution evidence control-plane for agent actions.

This document is a 5–10 minute copy-paste demo for showing the accepted AgentHarness evidence chain with the committed `examples/agent_bus_adapter_registry` fixture. It is factual demo guidance only; it does not add a command, script, fixture, schema, or product behavior.

## Who this demo is for

- Security reviewers who need to inspect evidence before high-impact agent actions.
- Platform reviewers who need to understand the boundary between evidence and downstream runtime ownership.
- Compliance reviewers who need repeatable audit artifacts and readback checks.
- Agent/runtime owners evaluating whether AgentHarness evidence is sufficient input for their own external controls.

## What the demo proves

The demo proves that AgentHarness can validate and export reviewable evidence before any downstream runtime owner acts:

- policy and smoke checks can be run from the repository;
- the file-bus fixture validates;
- ready requests are distinguishable from blocked and unsupported requests;
- registry-backed ready requests enter the export package while blocked and unsupported requests do not;
- the export package, digest manifest, manifest readback, enterprise audit report, report readback, checklist, and T025 harness are deterministic/reviewable;
- all relevant outputs remain `result_status: not_executed`.

## What the demo does not do

This demo does not:

- execute tools;
- invoke a runtime adapter;
- depend on an external `pi` repository;
- mutate task lifecycle state;
- enforce governance, auth, sandbox, signing, timestamp, attestation, certificate, notarization, or trust-root controls;
- start a daemon, scheduler, watcher, queue, or realtime chat surface;
- add a product output writer, script, helper, CLI command, or CLI flag.

## Prerequisites

- Run from the AgentHarness repository root.
- Use the same Python environment used for the project tests.
- No network is required for the demo commands.
- The commands write temporary readback artifacts under `/tmp`; they do not write product artifacts into the repository.

## Copy-paste command flow

```bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

./agentharness validate examples/agent_policy.example.yaml
./agentharness eval --cases PI-001,PD-001,SEC-001
./agentharness loop check examples/agent_bus_adapter_registry
./agentharness handoff inspect examples/agent_bus_adapter_registry
./agentharness handoff export examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-demo-export.json
./agentharness handoff manifest examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-demo-manifest.json
./agentharness handoff verify-manifest examples/agent_bus_adapter_registry /tmp/agentharness-demo-manifest.json | python3 -m json.tool >/tmp/agentharness-demo-verify-manifest.json
./agentharness audit report examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-demo-audit-report.json
./agentharness audit verify-report examples/agent_bus_adapter_registry /tmp/agentharness-demo-audit-report.json | python3 -m json.tool >/tmp/agentharness-demo-verify-report.json
./agentharness audit checklist examples/agent_bus_adapter_registry | python3 -m json.tool >/tmp/agentharness-demo-checklist.json
python3 -m unittest -q tests.test_end_to_end_evidence_chain
```

The `/tmp/agentharness-demo-*.json` files are reviewer-side saved artifacts for readback. They can be removed before a rerun if the reviewer wants a clean workspace; the commands overwrite them with fresh JSON when rerun.

## Expected summary counts

| Step | Expected summary |
| --- | --- |
| Handoff inspection | `reports=1`, `total=5`, `handoff_ready=2`, `blocked=2`, `unsupported=1`, `result_status=not_executed` |
| Export package | `total_handoffs=5`, `exported=2`, `blocked=2`, `unsupported=1`, `result_status=not_executed` |
| Digest manifest | `items=2` exported entries, `result_status=not_executed` |
| Manifest verification | `ok=true`, `matched=2`, `missing=0`, `extra=0`, `result_status=not_executed` |
| Enterprise audit report | `total_handoffs=5`, `handoff_ready=2`, `exported=2`, `blocked=2`, `unsupported=1`, `result_status=not_executed` |
| Audit report verification | `ok=true`, `matched_handoffs=5`, `missing_handoffs=0`, `extra_handoffs=0`, `result_status=not_executed` |
| Enterprise audit checklist | `checks=7`, `passed=5`, `manual=2`, `failed=0`, `blocked=0`, `result_status=not_executed` |
| T025 harness | `7 tests OK` |

Stable fixture totals to remember: `reports=1`, `total_handoffs=5`, ready/exported `2`, blocked `2`, unsupported `1`, checklist checks `7`, checklist passed `5`, checklist manual `2`.

## Ready, blocked, and unsupported case interpretation

The demo fixture intentionally includes more than a happy path:

| Request ID | Case | Interpretation |
| --- | --- | --- |
| `TR-read` | ready without approval | A read request passes policy and preflight without an approval record. It may enter export evidence, but it has still not run. |
| `TR-approve-delete` | ready with approval | A delete request requires and has matching approval evidence. It may enter export evidence, but it has still not run. |
| `TR-read-unsupported-intent` | unsupported | The selected adapter spec does not support the request intent, so it is excluded from export. |
| `TR-missing-approval-delete` | blocked missing approval | The request requires approval, but the required approval evidence is missing, so it is excluded from export. |
| `TR-deny-unknown` | blocked by policy | Policy blocks the unknown/shell-like request, so it is excluded from export. |

Ready means evidence is eligible for external owner review; it does not mean the action already happened or is automatically safe.

## Brief review questions answered

| Reviewer question | Demo evidence |
| --- | --- |
| What was requested? | Handoff inspection and audit report list the request IDs, tool names, categories, intents, and target scopes. |
| Was it policy-allowed? | Tool gate, preflight, handoff status, and audit report rows distinguish ready, blocked, and unsupported outcomes. |
| Was approval required and present? | `TR-approve-delete` shows approval-backed readiness; `TR-missing-approval-delete` shows blocked missing approval. |
| Was adapter/spec support checked? | Registry-backed handoff export and manifest include adapter reference and digest-bound evidence. |
| Which requests are ready vs blocked vs unsupported? | The inspection summary and audit report show ready/exported `2`, blocked `2`, unsupported `1`. |
| Can the package, manifest, and report be regenerated and compared? | Manifest verification and audit report verification return `ok=true` when saved `/tmp` artifacts match regenerated evidence. |
| What remains manual? | Checklist manual items are saved manifest readback and saved audit report readback, because reviewers must provide the saved paths. |
| Who owns actual execution? | The external runtime owner; AgentHarness only validates and exports pre-execution evidence. |

## Failure interpretation

- If a command fails, stop at the first failure; the failed step identifies the first broken evidence link.
- If JSON parsing fails, treat the output as malformed for review and rerun the command from the repository root.
- If manifest readback fails, the saved manifest does not match regenerated current evidence; inspect the verification report errors before trusting the saved artifact.
- If audit report readback fails, the saved audit report does not match regenerated current evidence or violates the report contract.
- If the T025 harness fails, treat the end-to-end evidence chain as not release-ready and run a separate repair task.
- If a `/tmp/agentharness-demo-*.json` file exists from a previous run, delete it or rerun the command flow to overwrite it with current evidence before review.

## Boundary reminder

This demo proves reviewable pre-execution evidence. It does not approve, dispatch, or execute the tool action.
