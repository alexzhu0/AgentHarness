# File-Bus Loop MVP

## Purpose

The file-bus loop is the first AgentHarness coordination protocol for two
Codex terminals working in one repository. It keeps coordination in files, not
direct agent chat.

This MVP is protocol-first. It deliberately does not add daemon behavior,
realtime chat, or public CLI task commands.

## Actors

- `designer`: defines task objectives, reviews executor evidence, and decides
  whether to complete, retry, or escalate.
- `executor`: performs the assigned task and records evidence. The executor can
  provide facts and verification output, but cannot redefine the objective.
- `user`: supplies authority, scope changes, or escalation decisions when the
  protocol reaches a blocked boundary.

## Directory Layout

Runtime state uses `.agent_bus/`:

```text
.agent_bus/
  ledger.jsonl
  tasks/
  evidence/
  reviews/
  tool_gates/
  approvals/
  preflight/
  adapters/
  handoffs/
```

Versioned examples mirror that layout under `examples/agent_bus/`:

```text
examples/agent_bus/
  loop_policy.yaml
  ledger.jsonl
  tasks/T001-loop-smoke.yaml
  evidence/T001-attempt-1.md
  reviews/T001-review.md
```

Tool-gate and approval examples are committed as separate fixtures:

```text
examples/agent_bus_tool_gate/
  tool_gates/
examples/agent_bus_approval/
  tool_gates/
  approvals/
examples/agent_bus_preflight/
  tool_gates/
  approvals/
  preflight/
examples/agent_bus_handoff/
  tool_gates/
  approvals/
  preflight/
  adapters/
  handoffs/
```

The examples are committed fixtures. Live `.agent_bus/` state is workspace
runtime state.

## Source Of Truth

`ledger.jsonl` is the sole source of truth for MVP task transitions, approval
events, review outcomes, retries, and escalation decisions.

Task YAML files define objectives and constraints. Evidence and review files are
supporting data. They do not become authoritative until referenced by an
append-only ledger event and checked against the task objective.

A separate decisions log is deferred.

## Lifecycle States

- `assigned`: designer has assigned the task to an executor.
- `executor_done`: executor submitted evidence for the attempt.
- `reviewing`: designer is reviewing executor evidence.
- `retry_requested`: designer rejected the attempt and requested another attempt
  with a new failure hypothesis.
- `completed`: designer accepted the evidence and closed the task.
- `blocked_escalate`: work cannot continue without user authority or a scope
  change.

Allowed state transitions:

```text
assigned -> executor_done
executor_done -> reviewing
reviewing -> completed
reviewing -> retry_requested
reviewing -> blocked_escalate
retry_requested -> executor_done
```

`completed` and `blocked_escalate` are terminal states.

## Ledger Events

Every event is one JSON object per line. Required fields:

- `event_id`: unique stable event id.
- `ts`: ISO-like timestamp string.
- `task_id`: task id from `tasks/*.yaml`.
- `actor`: one of `designer`, `executor`, `user`.
- `event_type`: one of `task_assigned`, `executor_done`,
  `designer_review`, `task_completed`, `retry_requested`, or
  `blocked_escalate`.
- `status`: resulting lifecycle state.
- `attempt`: positive integer attempt number.
- `objective_ref`: stable reference to the original task objective.
- `summary`: short human-readable event summary.

Conditional fields:

- `evidence_path`: required when status is `executor_done`.
- `tool_gate_report_path`: optional when status is `executor_done`; forbidden
  on all other lifecycle events.
- `approval_record_paths`: optional when event type is `designer_review`;
  forbidden on all other lifecycle events.
- `preflight_report_path`: optional when event type is `designer_review`;
  forbidden on all other lifecycle events.
- `execution_handoff_report_path`: optional when event type is
  `designer_review`; forbidden on all other lifecycle events.
- `review_path`: required when status is `completed` or `retry_requested`.
- `failure_class`: required for `retry_requested` and `blocked_escalate`.
- `failure_hypothesis`: required for `retry_requested`.
- `evidence_path`, `review_path`, and `tool_gate_report_path` are resolved
  relative to the bus root. Absolute paths are valid only when they remain
  inside the bus root, and parent traversal outside the bus root is rejected.
- `review_path` files must include a whitelisted verdict:
  `accepted`, `retry_requested`, or `blocked_escalate`.
- `evidence_path` and `review_path` files must identify the same `task_id` and
  `objective_ref` as the ledger event.
- `tool_gate_report_path` files must identify the same `task_id`,
  `objective_ref`, and `attempt` as the ledger event.
- `approval_record_paths` files must remain inside the bus root and must bind
  the same `task_id`, `objective_ref`, `attempt`, and same-attempt
  `tool_gate_report_path`.
- `preflight_report_path` files must remain inside the bus root, must identify
  the same task context, and must bind the same-attempt
  `tool_gate_report_path`.
- `execution_handoff_report_path` files must remain inside the bus root, must
  identify the same task context, and must bind the same-attempt tool gate
  report, preflight report, approval records, and adapter spec.
- `adapter_spec_path` inside an execution handoff report is resolved relative
  to the bus root and must not escape the bus root.

## Tool Gate Reports

Tool gate reports are structured evidence attachments. They describe proposed
tool requests and the side-effect-free router decisions for those requests:
`allow`, `approval_required`, or `deny`.

They do not execute tools and do not authorize lifecycle transitions. The
ledger remains the task source of truth, and the designer still decides whether
evidence is accepted, retried, or escalated.

Every tool gate report must:

- use `kind: tool_gate_report`;
- use `source: route_tool_request`;
- include decisions that match fresh `route_tool_request` recomputation from
  each stored request using the repo-local policy and governance references,
  including every current `ToolDecision` field;
- count `allow`, `approval_required`, and `deny` decisions accurately;
- mark every audit and gate result as `not_executed`;
- set `execution_allowed_by_policy: false` for `approval_required` and `deny`;
- keep `approval_required` separate from `allow`.

## Approval Records

Approval records are structured audit attachments referenced from
`designer_review` events. They bind a user decision to one approval-gated entry
inside the same attempt's tool gate report.

They do not execute tools, do not mutate task lifecycle, do not create new
lifecycle states, and do not upgrade `allow` or `deny` semantics.

Every approval record must:

- use `kind: approval_record`;
- use `result_status: not_executed`;
- use `approver.actor: user` in the first protocol version;
- bind `task_id`, `objective_ref`, `attempt`, `tool_gate_report_path`,
  `request_id`, and `decision_digest`;
- reference a `request_id` whose recomputed tool gate decision is
  `approval_required`;
- include `subject.expected_decision: approval_required`;
- use a `decision_digest` computed from the tool gate entry's `request_id`,
  `request`, `decision`, and `gate`;
- preserve the approved scope without broadening the tool name, category,
  intent, or target scope.

Approvals for `allow` entries are unnecessary and invalid. Approvals for `deny`
entries are invalid; denied actions require policy or scope changes, not an
approval record.

## Execution Preflight

Execution preflight reports are structured audit attachments referenced from
`designer_review` events. They answer whether a future execution boundary would
be eligible to consider a tool request after policy and approval checks.

They do not execute tools, do not mutate task lifecycle, do not append ledger
events, and do not convert approval into execution. Every report and decision
must use `result_status: not_executed`.

The preflight decision vocabulary is:

- `ready_without_approval`: policy allowed the request and no approval record
  was used.
- `ready_with_approval`: policy required approval and a valid user approval
  record is bound to the request.
- `blocked_missing_approval`: policy required approval but no valid approval
  record is bound to the request.
- `blocked_rejected_approval`: policy required approval and the bound approval
  record says `rejected`.
- `blocked_by_policy`: policy denied the request; approval cannot override it.
- `invalid_subject`: the reported subject, approval, scope, digest, or decision
  does not match the trusted tool gate entry.

Every preflight report must:

- use `kind: execution_preflight_report`;
- use `source: build_execution_preflight_decision`;
- bind the same `task_id`, `objective_ref`, `attempt`, and
  `tool_gate_report_path` as the same-attempt tool gate report;
- include one preflight decision for each tool gate report entry;
- recompute each decision from the tool gate entry plus any valid approval
  record;
- reject hand-authored changes that make `deny` executable;
- reject hand-authored changes that make `approval_required` executable
  without an approved approval record;
- keep scope fields equal to the tool gate decision.

## Execution Handoff Reports

Execution handoff reports are structured control-plane artifacts referenced
from `designer_review` events. They answer whether a future execution plane may
receive a request after tool routing, approval, preflight, adapter support, and
digest checks.

They do not execute tools, do not call runtime adapters, do not mutate task
lifecycle, do not append ledger events, and do not convert preflight readiness
into execution. Every report and handoff must use `result_status:
not_executed`.

Every execution handoff report must:

- use `kind: execution_handoff_report`;
- use `source: build_execution_handoff`;
- bind the same `task_id`, `objective_ref`, `attempt`,
  `tool_gate_report_path`, and `preflight_report_path` as the same-attempt
  source artifacts;
- reference an `adapter_spec_path` that remains inside the bus root;
- include one or more `execution_handoff` entries in `handoffs[]`;
- derive each handoff selection from `handoffs[].request_id`;
- reject duplicate or unknown `request_id` values;
- recompute tool gate, approval, preflight, and handoff digests from source
  artifacts;
- require adapter support for all four dimensions: `tool_name`, `category`,
  `intent`, and `target_scope`;
- reject partial adapter support as `unsupported_by_adapter`;
- reject hand-authored changes that make blocked or unsupported requests
  handoff-ready;
- keep every report, handoff, gate, and decision result `not_executed`.

Runtime adapter specs are declarations of future execution-plane capability,
not executable adapters. A spec can say that a future `tool_call` hook supports
specific tools, categories, intents, and target scopes. The file-bus validator
only checks whether the declared support matches the handoff request; it does
not import, instantiate, or call the adapter.

## Runtime Adapter Registry

A runtime adapter registry is an optional control-plane artifact for pinning
adapter identity before any future runtime spike consumes a handoff. It is not
an adapter registry service, does not discover live adapters, and does not call
an execution plane.

Registry shape:

```yaml
version: 0.1.0
kind: runtime_adapter_registry
entries:
  - adapter_id: pi-tool-call-v0
    adapter_kind: tool_call_hook
    adapter_version: 0.1.0
    execution_plane: external
    status: active
    adapter_spec_path: adapters/pi-tool-call-v0.yaml
    adapter_spec_digest: sha256:<canonical-spec-digest>
```

Registry-backed handoff reports add both fields:

```yaml
adapter_registry_path: adapters/registry.yaml
adapter_ref:
  adapter_id: pi-tool-call-v0
  adapter_version: 0.1.0
  adapter_spec_digest: sha256:<canonical-spec-digest>  # optional echo of registry digest
```

The binding is all-or-nothing. If either `adapter_registry_path` or
`adapter_ref` is present, both must be present. `adapter_ref` requires exact
`adapter_id` and exact `adapter_version`; `adapter_ref.adapter_spec_digest` is
optional. If an adapter-ref digest is present, it must be a `sha256:<hex>`
digest and must match the selected registry entry. If it is absent, selection
still uses exact `(adapter_id, adapter_version)`, and the selected registry
entry's required `adapter_spec_digest` still validates against the canonical
adapter spec digest.

The validator resolves `adapter_registry_path` and every registry
`adapter_spec_path` relative to the bus root, rejects path traversal outside
the bus root, validates each selected adapter spec with the same runtime
adapter spec validator used by direct handoff reports, and compares the
canonical spec digest.

Adapter selection is exact: no wildcard, version range, alias, live discovery,
or environment-dependent lookup is allowed. `adapter_version` values in both
registry entries and `adapter_ref` must use strict `MAJOR.MINOR.PATCH` semver,
for example `0.1.0`; aliases and ranges such as `0.1.x`, `latest`,
`>=0.1.0`, `^0.1.0`, `~0.1.0`, and `*` fail closed. A handoff can select only
an `active` entry whose `(adapter_id, adapter_version)` matches `adapter_ref`,
and the handoff report's `adapter_spec_path` must match the selected registry
entry.

### Read-Only Handoff Inspection

`agentharness handoff inspect <bus_root>` is an operator inspection surface for
validated execution handoff reports. It first runs the same file-bus validation
as `agentharness loop check`, then reads `execution_handoff_report_path`
references from `designer_review` ledger events and prints:

- report count;
- total handoff entries;
- handoff-ready, blocked, and unsupported counts;
- report and handoff `result_status`;
- per-request readiness, preflight decision, and request scope.

`agentharness handoff inspect <bus_root> --json` emits the same information as
a deterministic JSON payload for future spike scripts.

The inspector is read-only. It does not generate handoff reports, call runtime
adapters, execute tools, append ledger events, mutate task files, or create new
lifecycle states. If the bus has no handoff report reference, or if validation
rejects a forged digest, blocked-ready edit, unsupported-ready edit,
`result_status: executed`, duplicate request id, unknown request id, or path
escape, the command fails closed.

### Registry-Backed Handoff Export Package

`agentharness handoff export <bus_root>` is a read-only dry-run consumer
package surface for future runtime adapter spikes. It first runs the same
file-bus validation as `agentharness loop check`, then reads
`execution_handoff_report_path` references from `designer_review` ledger events.

Export is registry-backed only. A direct legacy handoff report with only
`adapter_spec_path` can still pass file-bus validation, but it fails export
because future consumers need a pinned `adapter_registry_path` plus exact
`adapter_ref` identity. The exporter reuses registry binding validation and
does not create a weaker adapter-selection path.

Export packages use:

```yaml
kind: handoff_export_package
source: build_handoff_export_package
result_status: not_executed
summary:
  reports: 1
  total_handoffs: 5
  exported: 2
  blocked: 2
  unsupported: 1
  result_status: not_executed
exports:
  - kind: handoff_export_item
    result_status: not_executed
    handoff_report_path: handoffs/T008-handoff-report.yaml
    adapter_registry_path: adapters/registry.yaml
    adapter_spec_path: adapters/pi-tool-call-v0.yaml
    adapter_ref:
      adapter_id: pi-tool-call-v0
      adapter_version: 0.1.0
      adapter_spec_digest: sha256:<selected-registry-digest>
    request_id: TR-read
    handoff_digest: sha256:<canonical-handoff-digest>
```

Only handoffs whose `gate.handoff_ready` is `true` are serialized in
`exports[]`. Blocked and unsupported handoffs may be counted in `summary`, but
they must not appear as consumer items. Package and item outputs remain
`result_status: not_executed`.

The exporter emits deterministic JSON to stdout only. It does not write package
files, call runtime adapters, execute tools, append ledger events, mutate task
files, add lifecycle states, or add run/execute/dispatch/submit semantics. All
paths in export items are bus-relative paths, not absolute host paths.

### Digest-Addressed Handoff Export Manifest

`agentharness handoff manifest <bus_root>` is a read-only manifest surface over
the T011 export package. It calls `build_handoff_export_package(bus_root)` first
and uses that package as the only item source, so registry-backed validation,
ready-only filtering, blocked/unsupported exclusion, and export order all stay
owned by the export layer.

The manifest uses the same canonical digest rule as execution handoffs:
`json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`,
UTF-8 SHA-256, and a `sha256:` prefix. `package_digest` is the digest of the
full T011 export package. Each `export_item_digest` is the digest of the
matching T011 export item, and each manifest item preserves the export item's
`handoff_digest`.

Manifest payloads use:

```yaml
kind: handoff_export_manifest
source: build_handoff_export_manifest
result_status: not_executed
package_kind: handoff_export_package
package_digest: sha256:<canonical-export-package-digest>
summary:
  reports: 1
  total_handoffs: 5
  exported: 2
  blocked: 2
  unsupported: 1
  result_status: not_executed
items:
  - kind: handoff_export_manifest_item
    result_status: not_executed
    request_id: TR-read
    handoff_id: HOFF-TR-read
    handoff_digest: sha256:<canonical-handoff-digest>
    export_item_digest: sha256:<canonical-export-item-digest>
    adapter_ref:
      adapter_id: pi-tool-call-v0
      adapter_version: 0.1.0
      adapter_spec_digest: sha256:<selected-registry-digest>
```

Manifest items are ready exports only. For the registry fixture, the manifest
includes `TR-read` and `TR-approve-delete`; it excludes
`TR-read-unsupported-intent`, `TR-missing-approval-delete`, and
`TR-deny-unknown`. `adapter_ref` is copied only as provenance metadata. The
manifest emits deterministic JSON to stdout only and does not write artifacts,
call adapters, add key/trust material, append ledger events, mutate task files,
or add lifecycle states.

### Handoff Manifest Verification / Readback

`agentharness handoff verify-manifest <bus_root> <manifest_path>` is a
read-only readback command for saved T012 manifest JSON files. It regenerates
the expected manifest by calling `build_handoff_export_manifest(bus_root)`, so
all registry-backed export validation still flows through T011 and T012. It
then compares the saved manifest object against the regenerated object before
reporting deterministic per-field mismatches.

Verification reports use:

```yaml
kind: handoff_manifest_verification_report
source: verify_handoff_export_manifest
result_status: not_executed
ok: true
package_kind: handoff_export_package
manifest_kind: handoff_export_manifest
expected_package_digest: sha256:<canonical-export-package-digest>
manifest_package_digest: sha256:<manifest-package-digest>
summary:
  items: 2
  matched: 2
  mismatched: 0
  missing: 0
  extra: 0
  result_status: not_executed
items:
  - kind: handoff_manifest_verification_item
    result_status: not_executed
    request_id: TR-read
    ok: true
    expected_handoff_digest: sha256:<digest>
    manifest_handoff_digest: sha256:<digest>
    expected_export_item_digest: sha256:<digest>
    manifest_export_item_digest: sha256:<digest>
errors: []
```

A matching manifest exits `0`. Malformed JSON, non-object JSON, wrong kind,
wrong source, wrong package kind, `result_status: executed`, forged package or
item digests, missing items, extra items, reordered items, stale bus state, or
a direct legacy handoff fixture exit `1` with deterministic JSON errors. CLI
misuse exits `2` through argparse. The command emits reports to stdout only and
does not write product files, call adapters, add key/trust material, append
ledger events, mutate task files, or add lifecycle states.

## Event Authority

Each `event_type` has an allowed actor set:

| event_type | allowed actors |
| --- | --- |
| `task_assigned` | `designer` |
| `executor_done` | `executor` |
| `designer_review` | `designer` |
| `task_completed` | `designer`, `user` |
| `retry_requested` | `designer` |
| `blocked_escalate` | `designer`, `user` |

The executor can submit evidence, but cannot complete a task, request a retry,
or escalate the task. The designer can review and decide, but cannot submit
executor evidence.

## Retry Policy

Retries are bounded by task policy. The MVP default is:

```yaml
retry_policy:
  max_attempts: 3
  require_new_failure_hypothesis: true
```

Each retry must include a non-empty `failure_hypothesis`, and repeated retries
must not reuse the same hypothesis.

Attempts start at `1` and stay constant throughout one assigned -> evidence ->
review cycle. After a `retry_requested` event, the next `executor_done` event
must increment the attempt by exactly one. The number of executor attempts must
not exceed `retry_policy.max_attempts`, even when each retry has a new failure
hypothesis.

## Failure Classes

The MVP failure classes are:

- `verification_failed`
- `baseline_drift`
- `policy_violation`
- `missing_evidence`
- `objective_mismatch`
- `invalid_ledger`
- `repeated_failure_without_new_hypothesis`

Automatic retry classes are retryable until `retry_policy.max_attempts` is
exhausted:

- `baseline_drift`
- `verification_failed`
- `missing_evidence`

Escalation classes are the subset that should stop autonomous continuation
without another automatic retry:

- `policy_violation`
- `objective_mismatch`
- `invalid_ledger`
- `repeated_failure_without_new_hypothesis`

`baseline_drift` is automatic retry while retry budget remains. It escalates
only when the current attempt has exhausted `max_attempts`.

## Trust Boundary

Executor evidence is data until reviewed. It cannot change the task objective,
relax constraints, grant approval, or mark the task complete. Only ledger events
from the designer or user can close, retry, or escalate a task.

## Deferred Work

- `agentharness loop check examples/agent_bus`
- task creation/status CLI commands
- daemon scheduling
- realtime chat bridge
- separate decisions log
