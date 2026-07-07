# AgentHarness Pi Integration Boundary and Contract

AgentHarness is a pre-execution evidence control-plane for agent actions.

This document is a docs/spec-only boundary contract for possible future AgentHarness ↔ Pi work. It describes how AgentHarness evidence could someday gate Pi tool calls, but it does not implement runtime integration, modify Pi, import Pi, depend on Pi, invoke Pi tools, add schemas, add code, add CLI behavior, or add product writer flags.

## Scope and non-goals

Scope:

- record read-only Pi planning facts;
- define a conceptual future boundary between AgentHarness evidence and Pi tool-call preparation;
- sketch minimal request and decision shapes for a later mock/dry-run mapping task;
- list risks, required evidence, safe defaults, and no-go conditions.

Non-goals:

- no live hook implementation;
- no modification of the Pi repository;
- no AgentHarness source/test/schema/example/CLI/dependency changes;
- no runtime execution or runtime adapter invocation;
- no daemon, scheduler, watcher, queue, realtime chat, run, execute, dispatch, submit, or task mutation surface;
- no lifecycle state expansion;
- no sandbox, auth gateway, identity provider, signing, timestamping, attestation, trust-root, or governance enforcement;
- no claim that AgentHarness decides whether an action is safe to execute.

## Why Pi is a plausible future runtime candidate

Pi is a plausible future runtime/execution-plane candidate because its agent package exposes tool calling, state management, pre-tool-call hook concepts, and configurable tool execution ordering. Those are the kinds of runtime surfaces that could consume AgentHarness evidence later.

This does not make Pi an AgentHarness dependency. In this task, Pi is only a read-only source used to shape a future contract.

## Read-only Pi facts used for planning

The following facts were inspected read-only from the Pi repository:

| Fact | Source reference |
| --- | --- |
| Pi root README lists `@earendil-works/pi-coding-agent` as an interactive coding agent CLI. | Pi `README.md:23` |
| Pi root README lists `@earendil-works/pi-agent-core` as an agent runtime with tool calling and state management. | Pi `README.md:24` |
| Pi root README lists `@earendil-works/pi-ai` as a unified multi-provider LLM API. | Pi `README.md:25` |
| Pi root README states Pi does not include a built-in permission system for restricting filesystem, process, network, or credential access by default. | Pi `README.md:59-67` |
| `ToolExecutionMode` supports `sequential` and `parallel`; in parallel mode, tool calls are prepared sequentially and allowed tools execute concurrently. | Pi `packages/agent/src/types.ts:28-36`, `packages/agent/src/types.ts:245-254` |
| `BeforeToolCallResult` supports `{ block?: boolean; reason?: string }`. | Pi `packages/agent/src/types.ts:49-58` |
| Pi comments state returning `{ block: true }` prevents tool execution and emits an error tool result. | Pi `packages/agent/src/types.ts:49-54`, `packages/agent/src/types.ts:256-262` |
| `beforeToolCall` receives assistant message, raw tool call, validated args, and current agent context after argument validation. | Pi `packages/agent/src/types.ts:83-93`, `packages/agent/src/types.ts:256-262` |
| `AgentTool` extends a tool schema shape and includes `prepareArguments`, `execute`, and optional per-tool execution mode. | Pi `packages/agent/src/types.ts:360-384` |
| Pi README says `beforeToolCall` runs after `tool_execution_start` and validated argument parsing, and can block execution. | Pi `packages/agent/README.md:102-111` |
| Pi README example returns `{ block: true, reason: "bash is disabled" }` from `beforeToolCall`. | Pi `packages/agent/README.md:193-201` |
| Pi agent loop calls `beforeToolCall` after validation and treats `beforeResult.block` as an immediate error result instead of a prepared executable call. | Pi `packages/agent/src/agent-loop.ts:578-604` |

These facts are planning inputs only. They are not imported, tested, called, or depended on by AgentHarness.

## AgentHarness / Pi responsibility split

| Responsibility | AgentHarness | Pi / future runtime owner |
| --- | --- | --- |
| Evidence validation | Owns file-bus, tool gate, approval, preflight, handoff, registry, export, manifest, readback, audit report, and checklist evidence. | May consume the evidence but must not assume AgentHarness executed anything. |
| Tool execution | Does not execute tools. | Owns actual tool-call execution if a future integration is separately implemented. |
| Runtime hook wiring | Does not implement hooks in T034. | Would own hook installation and runtime behavior in a future approved task. |
| Permission/sandbox/auth | Does not provide sandbox, auth gateway, identity, signing, timestamping, attestation, trust-root, or governance enforcement. | Must supply or integrate external controls where required. |
| Decision records | May produce deterministic evidence and conceptual decisions in a future mock mapping task. | Must enforce any runtime block/allow behavior under its own runtime contract. |
| Safety approval | Does not decide that an action is safe to execute. | External runtime/governance/human owners decide under their policies. |

## Candidate hook point: Pi beforeToolCall as future boundary, not implemented now

Pi's `beforeToolCall` is a plausible future boundary because it is invoked after tool-call arguments have been validated and before the runtime proceeds to tool execution. Pi's documented result shape can block execution with a reason.

T034 does not implement that hook. A future task would first need a mock/dry-run adapter mapping that compares Pi tool-call observations against existing AgentHarness evidence without calling Pi tools.

## Minimal future request shape from Pi to AgentHarness

A future Pi → AgentHarness request should be treated as a candidate evidence lookup, not a runtime command:

```yaml
adapter_id: pi-agent-core
adapter_version: 0.0.0-placeholder
runtime_candidate: pi
tool_call_id: <pi tool call id>
tool_name: <pi tool name>
arguments_digest: sha256:<canonical normalized arguments digest>
arguments_summary:
  redacted: true
  shape: <field names/types only when safe>
category: <candidate AgentHarness category>
intent: <candidate AgentHarness intent>
target_scope: <candidate AgentHarness target scope>
session_ref: <pi session/task reference>
agentharness_refs:
  handoff_report: <bus-relative path if available>
  export_package_digest: <sha256 digest if available>
  manifest_digest: <sha256 digest if available>
result_status_required_before_runtime: not_executed
```

This shape is conceptual. It is not a schema file and not an implementation contract until separately planned.

## Minimal future decision shape from AgentHarness to Pi

A future AgentHarness → Pi decision should be deterministic evidence output, not proof of sandboxing or runtime safety:

```yaml
decision: allow | block | unsupported | error
reason: <human-readable deterministic reason>
evidence_refs:
  request_id: <AgentHarness request id if matched>
  handoff_digest: <sha256 digest if matched>
  export_item_digest: <sha256 digest if matched>
  manifest_digest: <sha256 digest if matched>
required_result_status: not_executed before execution
decision_digest: sha256:<canonical decision digest>
boundary_notes:
  - AgentHarness evidence is pre-execution only.
  - Pi/runtime owner remains responsible for actual execution controls.
  - This decision is not sandbox, auth, signing, timestamp, attestation, trust-root, runtime approval, or safe-to-execute approval.
```

Decision semantics for a future contract:

- `allow`: evidence matched a ready/exported request, digests match, and required provenance exists; runtime owner still decides whether to proceed.
- `block`: evidence is missing, stale, policy-denied, approval-missing, digest-mismatched, or explicitly blocked.
- `unsupported`: mapping cannot prove adapter/category/intent/scope support.
- `error`: malformed request, validation failure, or internal evidence readback failure.

## Mapping risks: Pi tool names/schemas vs AgentHarness request categories/intents/scopes

Risks to resolve before any live runtime task:

- Pi tool names may not map one-to-one to AgentHarness `tool_name` values.
- Pi tool schemas may expose argument fields that AgentHarness currently summarizes differently.
- Pi validated arguments may include sensitive values; future mapping must prefer digests or redacted summaries.
- AgentHarness categories, intents, and target scopes are policy concepts, while Pi tools are runtime capabilities.
- Adapter versions must be exact and stable; no `latest`, wildcard, or live discovery should select a runtime boundary.
- A tool name alone is insufficient; category, intent, target scope, approval status, handoff digest, export item digest, and manifest digest must all be considered.

## Batch/parallel tool-call considerations

Pi can prepare tool calls sequentially and execute allowed tools concurrently in parallel mode. That creates contract requirements:

- every tool call in a batch must receive an independent evidence decision;
- a block/unsupported/error decision for one call must not be hidden by allowed calls in the same batch;
- decision order should preserve Pi tool-call identifiers and AgentHarness request identifiers;
- future mock mapping should test mixed batches: all allowed, one blocked, one unsupported, and one malformed;
- if any tool requires sequential treatment, the future runtime owner must preserve Pi's ordering semantics while still consulting AgentHarness evidence before each execution.

## Digest/evidence requirements before any allow decision

A future `allow` decision must require at least:

- registry-backed handoff evidence;
- exact adapter id and strict adapter version;
- canonical handoff digest;
- export package item digest;
- manifest package digest or manifest item digest;
- bus-relative evidence references only;
- `result_status: not_executed` before runtime execution;
- deterministic decision digest over the decision payload;
- rejection of stale, missing, extra, reordered, or tampered evidence.

Without these, the safe default is `block` or `unsupported`, not `allow`.

## Approval/provenance requirements and current limitations

Approval/provenance requirements:

- approval-required requests must have same-attempt approval evidence;
- ready-without-approval requests must still have policy and preflight evidence;
- adapter registry provenance must bind adapter id, version, spec path, and digest;
- exported items must exclude blocked and unsupported requests;
- saved manifests and audit reports must be read back against regenerated current evidence before use.

Current limitations:

- AgentHarness has no Pi-specific adapter mapping schema;
- AgentHarness does not observe live Pi tool calls;
- AgentHarness does not install Pi hooks;
- AgentHarness does not provide identity authorization, sandboxing, credential isolation, signing, timestamping, attestation, trust-root, or governance enforcement;
- Pi README states Pi does not include a built-in permission system by default, so a future integration must not represent AgentHarness evidence as a permission system.

## Security boundary: AgentHarness is not sandbox/auth/trust-root

AgentHarness evidence can support a future runtime owner, but it is not:

- a sandbox guarantee;
- an auth gateway;
- an identity provider;
- a signing service;
- a timestamping service;
- an attestation service;
- a trust-root system;
- a production governance enforcement layer;
- runtime approval;
- safe-to-execute approval.

If those controls are needed, the future runtime owner must integrate them outside AgentHarness or propose a separate approved system.

## Failure modes and safe defaults

| Failure mode | Future default decision |
| --- | --- |
| Missing AgentHarness evidence | `block` |
| Handoff exists but is not registry-backed | `unsupported` or `block` |
| Adapter id/version mismatch | `block` |
| Digest mismatch | `block` |
| Approval-required request lacks valid approval | `block` |
| Tool name maps but category/intent/scope does not | `unsupported` |
| Arguments cannot be normalized or digested safely | `error` or `block` |
| Batch contains mixed allowed and blocked calls | independent decisions; blocked calls remain blocked |
| Pi hook times out or AgentHarness evidence lookup fails | `error` or `block` |
| Runtime owner needs sandbox/auth/signing/trust-root assurance | external escalation; no AgentHarness allow decision should claim that assurance |

Safe default: fail closed.

## Phased roadmap: T035/T036/T037 style next steps

Possible future tasks, each requiring separate planning and approval:

- **T035 static Pi-like tool-call mapping fixture**: [`docs/18-pi-tool-call-mapping-fixture.md`](./18-pi-tool-call-mapping-fixture.md) and [`examples/pi_tool_call_mapping/`](../examples/pi_tool_call_mapping/) define Pi-like observations and expected mapping outcomes without importing, calling, depending on, or modifying Pi.
- **T036 mock decision validator**: add a pure AgentHarness-side validator for the static fixture, preserving `allow_candidate` only as a candidate match to existing AgentHarness evidence and never emitting, inferring, or normalizing it into runtime allow. T036 is library/test-only, not CLI.
- **T037 dry-run contract CLI**: [`docs/19-pi-contract-check-cli.md`](./19-pi-contract-check-cli.md) exposes `./agentharness pi contract-check` over static fixture inputs only, still no live hook, no Pi modification, no runtime execution, and no runtime allow.

A live runtime integration remains out of scope until those earlier steps prove mapping, digest, approval, and safe-default behavior.

## Explicit no-go conditions for runtime implementation

Do not start live runtime implementation if any of these are true:

- the task would modify the Pi repository without explicit approval;
- AgentHarness would need to import, depend on, or call Pi directly;
- tool schemas/names cannot map to AgentHarness category/intent/target-scope evidence;
- the design requires AgentHarness to provide sandbox, auth, identity, signing, timestamping, attestation, trust-root, or governance enforcement;
- blocked or unsupported handoffs could become runtime-allowed;
- evidence is missing, stale, path-leaking, or not digest-addressed;
- `result_status: not_executed` is not preserved before runtime execution;
- a reviewer expects AgentHarness evidence to mean public release readiness, production readiness, runtime approval, or safe-to-execute approval.

## Readiness conclusion

| Question | Conclusion |
| --- | --- |
| Ready for contract design? | yes |
| Ready for live runtime integration? | no |
| Ready to modify Pi? | no |
| Ready for a mock/dry-run adapter mapping task after T034? | yes, if separately planned |

T034 ends at contract-first planning. It does not authorize implementation.
