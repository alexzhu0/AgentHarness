# Pi Observation/Evidence Contract v1

## Scope

T057 exposes only the pure contract, evaluator, and verifier APIs for
`AH-PI-EVIDENCE-BINDING-1`. The contract is deterministic and evidence-only. It
does not execute a tool, grant runtime permission, import Pi, authenticate a
response, or make `allow_candidate` equivalent to runtime allow.

## Current production boundary

T058 wires Pi production live mode at `beforeToolCall`. Pi builds the v1 request
from the current call data, invokes `pi evidence-evaluate-v1`, and requires exact
correlation of `tool_call_id`, `tool_name`, `observation_id`, and
`arguments_digest` before accepting an outcome as valid evidence. Pi owns this
runtime enforcement; AgentHarness remains the evidence/control-plane and never
executes the tool.

Every valid evaluator outcome is block-only in Pi, including a synthetic,
exactly correlated `allow_candidate`. Every request, response, result, and
evidence object remains `result_status: "not_executed"`. No live outcome permits
real tool execution.

The production request uses current `beforeToolCall` data only. Legacy
observations, expectations, and `contract-check` output are not runtime inputs.
The older fixture-aware observation builder is test-only.

The legacy command below remains fixture-oriented and expectation-driven:

```bash
./agentharness pi contract-check <observations> <expectations> <bus_root>
```

It remains **static, legacy/test-only** and is not used by the T057 APIs.
It is also not used by the T058 production live path.

## Frozen identifiers

| Purpose | Identifier |
| --- | --- |
| Contract | `AH-PI-EVIDENCE-BINDING-1` |
| Request schema | `urn:agentharness:schema:pi-tool-call-observation-batch:1` |
| Response | `urn:agentharness:schema:pi-tool-call-evidence-response-batch:1` |
| Argument canonicalization | `AH-ARGS-C14N-1` |
| Batch ordering | `AH-PI-BATCH-ORDER-1` |
| Batch identity | `AH-PI-BATCH-ID-1` |
| Evidence snapshot | `AH-EVIDENCE-SNAPSHOT-1` |

Changing semantics requires new identifiers and schema files.

## Request invariants

The authoritative request schema is
`schemas/pi_tool_call_observation_batch.v1.schema.json`.

- A batch contains 1 through 32 observations.
- Array position `i` must equal `order_index: i`; AgentHarness never sorts or
  repairs input.
- Observation IDs, tool-call IDs, and order indices are unique.
- Caller-controlled protocol identifiers are bounded opaque ASCII tokens. URL,
  path, bearer-token, cloud-key, and common repository-token forms are rejected
  rather than echoed into evidence or reviewer output.
- `batch_id` is `pi-batch:<sha256-hex>` over the canonical contract seed.
- Observation `i` is
  `pi-observation:<batch-hex>:<six-digit-index>`.
- `tool_name` is the exact runtime name. The pure builder derives the normalized
  tool, category, intent, and scope as a separate `mapping_claim` from internal
  arguments before serialization. Once serialized, that claim is untrusted and
  is never itself the selector for ready evidence.
- The exact `AH-ARGS-C14N-1` identifier and lowercase SHA-256 argument digest
  are bound and echoed; raw arguments are not included in protocol objects.
- Every protocol object has `result_status: "not_executed"`.

The strict schema and validator reject extra fields, including request-ID hints,
expectations, expected decisions, fixture identities or paths, and runtime allow
or authorization fields.

`AH-ARGS-C14N-1` vectors are in
`schemas/ah_args_c14n_1.vectors.json`. Objects are ordered by Unicode code point,
strings use deterministic ASCII escapes, numbers use the agreed safe binary64
rendering, and non-JSON, unsafe integer, non-finite, negative-zero, and invalid
Unicode values are rejected.

Path-derived mapping uses the T056 fail-closed classifier after bounded repeated
percent-decoding. Traversal, POSIX or Windows absolute paths, drive-relative
paths, UNC paths, tilde paths, empty segments, globs, shell metacharacters,
malformed/over-deep encodings, and encoded forms of those paths are classified
`outside_repository`; they cannot produce repository `allow_candidate`
evidence through the builder/evaluator path.

Because raw arguments are intentionally absent on the wire, AgentHarness can
independently derive only tool-name facts from the exact serialized `tool_name`.
An argument digest does not prove path, scope, or path-sensitive intent. If the
complete claim cannot be independently reproduced from contract-safe wire
information, evaluation returns `error` with
`mapping_claim_not_independently_derivable`; it never returns
`allow_candidate`. A strictly shaped claim may still be echoed for correlation.
Accordingly, the real digest-only evaluator currently returns
`mapping_claim_not_independently_derivable` for path-scoped live calls because
Pi does not transport raw arguments. The real path must not be described as
producing `allow_candidate`; that outcome appears only in synthetic contract and
consumer tests.

## Snapshot and evidence derivation

One evaluator API call captures exactly one immutable
`AH-EVIDENCE-SNAPSHOT-1`:

1. Bus-relative regular files are ordered deterministically.
2. Each file is opened without following symlinks and read once through a file
   descriptor under bounded file-count and byte limits. Device, inode, mode,
   size, and nanosecond mtime are checked against enumeration metadata and
   checked again after reading, so replacement or mutation fails closed.
3. The snapshot digest binds sorted relative paths to raw-byte SHA-256 digests;
   absolute paths are excluded.
4. Parsing, adapter validation, handoff indexing, export/package digest
   derivation, and all observation evaluation use only captured bytes.

`bus_root` selects this evidence snapshot input. It is not an oracle for the
identity, arguments, or mapping of the current Pi tool call; current-call
identity comes only from the correlated v1 request and response fields.

Duplicate `request_id`, duplicate `handoff_id`, duplicate/conflicting adapter
entries, malformed adapter bindings, or inconsistent gate evidence reject the
entire snapshot. Every registry entry and every pinned adapter spec is validated
from frozen bytes, including required fields, strict semver, status, digest, and
entry/spec binding; a malformed unselected entry or spec rejects the snapshot.
No index uses last-write-wins behavior.

Candidate enumeration uses only:

```text
adapter_id + adapter_version + mapped tool + category + intent + target scope
```

No request-ID hint participates. Only an independently derived complete mapping
may select this index. After that provenance gate, a unique ready match produces
`allow_candidate`; a unique blocked match produces `block`; a unique unsupported
or absent match produces `unsupported`; ambiguous matches produce `error`.
Unprovable mapping claims produce `error`; snapshot-invalid requests and
sanitized internal evaluator failures (`evaluation.internal_error`) are rejected
as a batch. This abstract decision vocabulary does not imply that the current
real digest-only path can derive a path-scoped `allow_candidate`.

## Response and exact binding

The authoritative response schema is
`schemas/pi_tool_call_evidence_response_batch.v1.schema.json`.

A complete response preserves request cardinality and order and exactly echoes:

- batch and observation identities;
- `tool_call_id` and raw `tool_name`;
- `AH-ARGS-C14N-1` and `arguments_digest`;
- the complete mapping claim.

Evidence bindings are AgentHarness-derived and include handoff, export-item,
export-package, and adapter-spec digests. `allow_candidate` means only that one
ready evidence record is structurally eligible after independent mapping
provenance validation. Pi's verifier repeats that provenance check and rejects a
self-consistent forged mapping even when its batch and observation IDs were
recomputed. Pi or any future caller must not interpret `allow_candidate` as
permission to execute.

Handled malformed requests, snapshot failures, and unexpected evaluator failures
return a deterministic rejected response with empty results and without request
identity, exception text, token material, filesystem paths, or tracebacks.

Pi's block-only consumer exposes only stable reason codes, booleans, counts,
and bounded status summaries. It does not copy raw tool names, tool-call IDs,
argument keys, subprocess stdout/stderr, exception text, URLs, paths, or token
material into user-visible block reasons.

Exact current-call verification rejects a response replayed across distinct
tool calls. V1 does not provide same-request freshness, nonces, response
authentication, signatures, or replay state, so it does not claim protection
against replay within the same request identity.

The public Python and TypeScript request/response verifiers are total over
cyclic and over-deep values. They return at most one diagnostic from the stable
vocabulary `request.invalid`, `request.depth_exceeded`,
`request.cycle_detected`, `response.invalid`, `response.depth_exceeded`, or
`response.cycle_detected`. Protocol error arrays have schema-fixed cardinality
and uniqueness, and integer fields reject booleans.

## T057/T058 ownership boundary

- T057 stops at pure contract, evaluator, and verifier APIs.
- T058 adds bounded transport and Pi `beforeToolCall` hook wiring while keeping
  every valid outcome block-only.
- Pi owns runtime enforcement; AgentHarness supplies evidence and correlation
  only.
- Neither task changes the T057 decision vocabulary into runtime authorization
  or executes a real tool.

## Trust and non-goals

The protocol provides deterministic correlation, not response authenticity. It
does not add runtime authorization, approvals, signatures, timestamps, replay
state, daemons, queues, watchers, schedulers, dependencies, or execution. Every
`result_status` field remains `"not_executed"`. T058 rejects cross-call replay
through exact correlation and supplies the always-block Pi bridge; same-request
freshness, nonces, authentication, and consume-once replay state remain outside
v1.
