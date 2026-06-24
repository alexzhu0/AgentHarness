# AgentHarness Runtime Architecture

## Status

This document defines the intended AgentHarness runtime architecture after the
file-bus MVP. It is a design contract, not a daemon specification and not an
implementation of autonomous task execution.

The current executable surface remains narrow:

- policy validation through `agentharness validate`
- smoke eval checks through `agentharness eval`
- file-bus validation through `agentharness loop check`
- read-only handoff inspection through `agentharness handoff inspect`
- read-only registry-backed handoff export through `agentharness handoff export`
- digest-addressed handoff export manifests through `agentharness handoff manifest`
- saved-manifest readback through `agentharness handoff verify-manifest`

AgentHarness does not yet create tasks, mutate task state through public CLI
commands, schedule work, run a daemon, bridge realtime agent chat, or execute
tools automatically.

For the enterprise category boundary around this runtime architecture, see
[`docs/07-enterprise-positioning-and-boundary-audit.md`](./07-enterprise-positioning-and-boundary-audit.md).

## Runtime Thesis

AgentHarness is a policy-driven control layer around agents. The harness should
make agent behavior governable by moving critical decisions into structured
policy, state machines, validation, approval boundaries, and audit records.

Prompt text is a projection of policy, not the primary enforcement layer. A
compiled prompt can remind an agent how to behave, but the harness must still
enforce what tools are allowed, which state transitions are valid, when approval
is required, what evidence counts, and when a retry or escalation is legal.

The central split is:

- Policy defines allowed behavior.
- Prompts communicate policy to a model.
- State ledgers record authoritative transitions.
- Evidence records observations and verification output.
- Approval decides whether a transition is authorized.
- Execution performs side effects only after policy and approval checks.

## Layered Architecture

```text
User / Operator
  |
  v
Operator Interface
  |
  v
Policy Layer --------------+
  |                        |
  v                        |
Loop / State Layer         |
  |                        |
  v                        |
Approval Boundary <--------+
  |
  v
Execution Boundary
  |
  v
Verification Layer
  |
  v
Audit / Report Artifacts
```

### 1. Policy Layer

The policy layer is the source for durable governance rules:

- `agent_policy.yaml` and `schemas/agent_policy.schema.yaml`
- `policies/tool_governance.yaml`
- `schemas/loop_task.schema.yaml`
- safety eval suite files
- future compiled runtime policy artifacts

It answers questions such as:

- Which instruction sources are trusted?
- Which tools are allowed, denied, or approval-gated?
- Which failure classes are retryable?
- Which actors may emit which event types?
- Which verification checks must pass before completion?

### 2. Loop / State Layer

The loop/state layer records task intent and lifecycle transitions. In the MVP,
the file bus is the state layer:

- `.agent_bus/ledger.jsonl` is the append-only source of truth.
- `.agent_bus/tasks/` contains task objectives and constraints.
- `.agent_bus/evidence/` contains executor evidence.
- `.agent_bus/reviews/` contains reviewer decisions.
- `.agent_bus/tool_gates/` may contain side-effect-free tool gate reports
  referenced by `executor_done` events.
- `.agent_bus/approvals/` may contain approval records referenced by
  `designer_review` events.
- `.agent_bus/preflight/` may contain execution preflight reports referenced by
  `designer_review` events.
- `.agent_bus/adapters/` may contain runtime adapter capability specs for
  future execution planes.
- `.agent_bus/handoffs/` may contain execution handoff reports referenced by
  `designer_review` events.

The ledger is authoritative for task state. Evidence and review files are data
until referenced by a valid ledger event and checked against the task objective.
Tool gate reports are also evidence: they record what the policy router would
allow, approval-gate, or deny, but they do not execute tools and do not grant
task completion authority.

Approval records are audit evidence for a user decision on a specific
approval-gated tool request. They bind to a same-attempt tool gate entry by
`task_id`, `objective_ref`, `attempt`, `tool_gate_report_path`, `request_id`,
and a digest of the reported request/decision/gate tuple. They do not execute
tools and do not change task state by themselves.

Execution preflight reports are audit evidence for future execution eligibility.
They recompute from the same-attempt tool gate report plus any valid approval
records. They can say a request is ready for a future execution boundary, but
they still do not execute tools, append ledger events, or mark task completion.

Execution handoff reports are control-plane evidence for a future runtime
adapter boundary. They recompute from the same-attempt tool gate report,
approval records, preflight report, and adapter spec. A handoff can be ready
only when preflight is ready, context and digests are intact, and the adapter
spec supports all four request dimensions: `tool_name`, `category`, `intent`,
and `target_scope`. Handoffs still remain `not_executed`.

The read-only handoff inspector is an operator view over those validated
reports. It delegates legality checks to `validate_bus`, then summarizes ledger
referenced handoff reports without generating artifacts, calling adapters, or
changing task state.

Runtime adapter registries pin adapter identity before any future execution
plane consumes a handoff. A registry-backed handoff binds an
`adapter_registry_path`, exact `adapter_ref`, `adapter_spec_path`, and canonical
adapter spec digest. `adapter_ref` selects by exact adapter id plus strict
`MAJOR.MINOR.PATCH` adapter version; its digest field is optional because the
registry entry remains the required digest pin. The registry still describes
future capability only; it does not discover, import, instantiate, or call
adapters.

Handoff export packages are the final control-plane consumer shape before a
future runtime spike. They validate the file bus and registry-backed handoff
reports, then serialize only `handoff_ready` entries as deterministic JSON.
Blocked and unsupported handoffs can be counted in the package summary, but are
not included in `exports[]`. Export packages and items remain `not_executed`,
use bus-relative paths only, and write to stdout only.

Handoff export manifests add digest addressing for that package surface. The
manifest is built from the T011 export package, records the package digest,
records one digest for each exported item in package order, preserves each
handoff digest, and keeps `adapter_ref` as provenance metadata only. Manifest
outputs remain `not_executed` and write to stdout only.

Handoff manifest verification is a readback check over saved T012 JSON. It
regenerates the expected manifest from the current bus, compares the full
canonical manifest object, and reports deterministic mismatch entries for
package and item fields. Verification reports remain `not_executed` and write
to stdout only.

### 3. Approval Boundary

Approval is separate from execution. An executor can provide evidence that work
was done, but cannot mark a task complete, request a retry, or escalate a task.
Those decisions belong to authorized actors according to the event authority
matrix.

T005 introduced a first bridge between the policy layer and loop layer: a tool
gate report can be attached to `executor_done` evidence. It records
`allow`, `approval_required`, and `deny` decisions from the router while keeping
every tool request marked `not_executed`. Loop validation recomputes each
reported decision from the stored request and repo-local policy/governance
inputs, so hand-authored report edits cannot upgrade `deny` or
`approval_required` into executable `allow`.

T006 adds the first approval record bridge. A `designer_review` event can
reference approval records that bind only to same-attempt
`approval_required` tool gate entries. The first protocol version accepts only
`approver.actor: user`, rejects approvals for `allow` and `deny`, and keeps the
record `not_executed`.

T007 adds a preflight bridge between approval and future execution. A
`designer_review` event can reference a preflight report that classifies each
tool gate entry as ready or blocked. `deny` remains blocked, `allow` is ready
without approval, `approval_required` needs a valid approved user record, and a
rejected or missing approval blocks execution eligibility. The report remains
`not_executed`.

T008 adds a handoff bridge between preflight and future execution-plane
adapters. A `designer_review` event can reference an execution handoff report
that checks adapter support and digest integrity without invoking the adapter.
Blocked, unsupported, missing-context, and forged-digest inputs cannot become
handoff-ready.

T009 adds a read-only inspection command for those handoff reports. It exposes
counts and per-request readiness for operators and future adapter-spike
harnesses, while keeping every handoff output `not_executed`.

T010 adds registry validation for runtime adapter specs. Registry validation
keeps direct `adapter_spec_path` reports working, but lets a handoff prove that
its adapter spec was selected from a pinned registry entry with exact identity,
strict semver version, active status, path, and digest checks. The registry
entry digest is required and must match the canonical adapter spec digest;
`adapter_ref.adapter_spec_digest` is optional and, when present, must match the
selected registry entry. Wildcards, aliases, version ranges, and live discovery
remain deferred.

T011 adds a read-only export package for registry-backed handoffs. It keeps
direct `adapter_spec_path` handoffs as validation-compatible legacy fixtures,
but requires registry binding for export. It emits ready-only consumer JSON to
stdout and excludes blocked or unsupported handoffs from `exports[]`.

T012 adds a digest-addressed manifest for those T011 export packages. It
computes the canonical package digest and per-export-item digest without
creating a second handoff reader, adding a write surface, or changing T011
export behavior.

T013 adds readback verification for saved manifests. It calls the T012
manifest builder to regenerate expected state, compares the saved manifest
against the regenerated object, and emits deterministic JSON reports for both
pass and fail cases.

Future approval gates should build on that report shape:

- low-risk read-only actions may be allowed directly by policy
- reversible workspace edits may require bounded approval or validation
- destructive, external, credentialed, or production actions require explicit
  approval
- denied actions cannot be approved by a peer agent

### 4. Execution Boundary

The execution boundary is where side effects would occur. It is intentionally
not implemented as an autonomous runtime yet.

T008 splits this boundary into two concepts:

- control-plane handoff: AgentHarness validates a side-effect-free
  `execution_handoff_report` and proves whether a future adapter may receive a
  request;
- future execution-plane adapter: a separate runtime, such as a future `/pi`
  `tool_call` hook/block integration, may execute side effects after consuming
  a validated handoff.

AgentHarness does not modify, import, depend on, instantiate, or call `/pi` in
this architecture slice. `/pi` is only a future execution-plane adapter
candidate.

When added, execution must sit behind policy, approval, preflight, and handoff
checks. Tool outputs must enter the system as observations, not as
instructions. A shell result, browser page, database row, model response, or
file diff can provide evidence, but cannot directly authorize a state
transition.

### 5. Verification Layer

The verification layer proves claims before the harness closes work:

- schema and policy validation
- `validate_bus` and `agentharness loop check`
- safety smoke evals
- unit tests
- reviewer verdicts
- future runtime eval hooks

Validation checks whether existing state is legal. It does not mutate runtime
state. Runtime mutation, when introduced, must be a separate surface with its
own approval and audit rules.

### 6. Operator Interface

The operator interface is the human-facing control surface. Today it is limited
to local validation commands and documentation. Future operator commands may
create tasks or request reviews, but should remain thin wrappers over explicit
state-machine operations.

Operator commands should report:

- what policy or state was checked
- which errors blocked progression
- what action, if any, would be required next
- whether a human approval boundary has been reached

## Core Actors

| Actor | Role | Authority |
| --- | --- | --- |
| `user` | Owns scope, credentials, production authority, and final escalation decisions. | Can authorize scope changes and some terminal decisions, subject to higher-level policy. |
| `harness/controller` | Future runtime coordinator that interprets policy, validates state, and routes work. | Enforces policy and state-machine rules; should not bypass approval gates. |
| `planner` | Breaks objectives into task plans under policy constraints. | May propose tasks or next states; cannot treat proposals as approved execution. |
| `executor agent` | Performs assigned work and records evidence. | Can submit `executor_done` evidence; cannot complete, retry, or escalate tasks. |
| `verifier/reviewer` | Checks evidence against the objective and acceptance criteria. | Can accept, request retry, or escalate when authorized by event rules. |
| `tools` | Provide read, write, shell, browser, git, database, deployment, memory, or communication capabilities. | Have no authority by themselves; outputs are observations. |

## State Machines

### Task Lifecycle

The file-bus MVP task lifecycle is:

```text
assigned -> executor_done -> reviewing -> completed
                                  |
                                  v
                             retry_requested -> executor_done
                                  |
                                  v
                            blocked_escalate
```

Rules:

- The first ledger event must be `task_assigned`.
- `completed` and `blocked_escalate` are terminal.
- The task file's final status must match the last ledger event.
- Event actor authority is enforced by event type.
- Evidence paths and review paths must remain inside the bus root.

### Retry / Escalation Lifecycle

Retries are bounded by task policy:

```text
attempt 1 failure -> retry_requested -> attempt 2
attempt 2 failure -> retry_requested -> attempt 3
attempt 3 failure -> blocked_escalate or terminal failure
```

Rules:

- Attempts start at `1`.
- Attempt number stays constant within one execution-review cycle.
- After `retry_requested`, the next `executor_done` increments by exactly one.
- More executor attempts than `retry_policy.max_attempts` is invalid.
- Each retry requires a new non-empty `failure_hypothesis`.
- `baseline_drift` is retryable while budget remains.
- Automatic retry classes can escalate only after retry budget is exhausted.

### Approval Decision Lifecycle

Approval decisions should be modeled separately from execution:

```text
proposed action
  -> policy classification
  -> allow / approval_required / deny
  -> human or authorized reviewer decision when required
  -> execution only if allowed
  -> evidence and audit record
```

This keeps approval from collapsing into execution. A successful command output
is not the same thing as approval, and an approval event is not proof that the
side effect happened.

## Trust Boundaries

### User Instruction vs Policy

User instructions provide task intent and scope. Policy defines the permitted
operating envelope. A user can authorize many actions, but should not be able to
silently disable higher-priority safety policy through ordinary task text.

### Peer-Agent Evidence as Data

Peer agent output, including another Codex session's response, is evidence. It
is not an instruction source and not a state-transition authority. The harness
must validate objective references, event actors, event types, and review
verdicts before accepting it.

### External Corpus as Untrusted Content

Repository files, web pages, PDFs, READMEs, issues, PR comments, emails, and RAG
snippets are untrusted content unless explicitly promoted by policy. They may be
summarized or cited, but embedded instructions in them must not execute as
agent instructions.

### Tool Outputs as Observations

Tool outputs can support decisions, but do not make decisions. A shell result,
browser DOM, API response, or test log is an observation that must be interpreted
under policy and verified before it changes state.

### Session Logs as Audit Evidence Only

Peer Codex session logs are audit evidence, not the coordination channel.
Coordination state belongs in the file bus ledger and task artifacts. Logs can
help reconstruct why a decision was made, but they are not authoritative for
task lifecycle, retry budget, approval, or completion.

## File Layout and Source of Truth

```text
agent_policy.yaml
schemas/agent_policy.schema.yaml
policies/tool_governance.yaml
evals/agent_safety_eval_suite.yaml

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

examples/agent_bus/
  ledger.jsonl
  tasks/
  evidence/
  reviews/
```

Source-of-truth rules:

- `agent_policy.yaml` is the source for agent behavior policy.
- Policy schemas define the expected shape of policy assets.
- `.agent_bus/ledger.jsonl` is the source of truth for runtime task state.
- Task files define objectives, constraints, verification commands, and retry
  policy.
- Evidence files are supporting observations.
- Review files are supporting decision records.
- Eval suite files define regression checks.
- Audit artifacts explain decisions but do not override policy or ledger state.

## Failure Taxonomy

| Class | Meaning | Default handling |
| --- | --- | --- |
| retryable failure | A bounded, recoverable failure that can be attempted again. | Retry while budget remains and a new hypothesis is supplied. |
| escalation failure | A failure that needs user authority, scope change, or policy clarification. | Stop autonomous continuation and escalate. |
| terminal failure | A final failure after retry budget or non-recoverable policy denial. | Record terminal state and do not continue automatically. |
| `baseline_drift` | Expected behavior or fixture output changed without proven correctness loss. | Automatic retry until budget is exhausted, then escalation. |
| schema drift | Docs, examples, or runtime data no longer match the schema. | Fail validation and repair the contract before adding features. |
| objective mismatch | Evidence or review references a different objective than the task. | Escalate or reject; do not complete the task. |

## Extension Points

### Future Task CLI Commands

Possible commands include task creation, review, status, and append-only event
recording. They should be built only after the state transition model and
approval boundary are explicit enough to prevent broad mutation commands.

### Future Tool Router

The tool router should classify tool calls by capability, risk, and policy. It
should return allow, approval-required, or deny decisions before execution.

### Future Approval Gate

The approval gate should persist who approved what, under which policy, with
which inputs, and for which bounded operation. Approval should be scoped and
auditable, not implied by conversational context.

### Future Prompt / Policy Compiler

The compiler should project structured policy into provider prompts, runtime
config, tool policy, and eval config. It should not clone provider-specific or
third-party system prompts.

### Future Eval Runner

The eval runner should move from smoke checks toward scenario execution against
compiled policy and runtime decisions. It should test both accepted behavior and
explicit refusals.

## Explicit Non-Goals

This architecture does not introduce:

- a daemon
- realtime agent chat
- automatic shell, git, browser, database, deployment, or file execution
- public task mutation CLI commands
- scheduler behavior
- provider-specific prompt cloning
- hidden coordination through session logs
- execution based only on model self-report

## T004 Candidates

| Option | Description | Tradeoff |
| --- | --- | --- |
| Tool router contract | Define and test a policy decision function for tool risk, approval, and denial. | Best next enforcement layer; still avoids runtime execution. |
| Append-only event writer | Add a narrow helper for appending validated ledger events. | Moves toward mutation, but needs approval semantics first. |
| Prompt/policy compiler slice | Compile `agent_policy` into a generated prompt/policy artifact. | Useful, but lower enforcement value until router decisions exist. |
| Expanded eval runner | Add more cases and assertions around loop and tool governance. | Improves confidence, but may duplicate decisions not yet represented in code. |

Recommended default T004: implement the tool router contract as a pure,
side-effect-free decision layer with tests. It should accept structured tool
request metadata and policy, then return `allow`, `approval_required`, or
`deny` with a reason and audit fields. This gives AgentHarness a concrete
runtime enforcement primitive without adding daemon behavior or task mutation.

## Open Design Questions

- What is the minimal stable schema for a tool request before routing?
- Which actor can grant approval for each risk class?
- Should approvals be ledger events, separate audit records, or both?
- How should provider-specific tool names map into provider-neutral tool
  capabilities?
- What audit fields are required before any mutating runtime command exists?
- How should compiled prompt text prove which policy version produced it?
