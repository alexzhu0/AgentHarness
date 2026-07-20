# AgentHarness Pi Tool-Call Mapping Fixture

AgentHarness is a pre-execution evidence control-plane for agent actions.

This document describes a static Pi-like tool-call mapping fixture. The fixture lets AgentHarness reason about future Pi `beforeToolCall`-style observations without importing Pi, depending on Pi, calling Pi, modifying Pi, or implementing a live hook.

## Scope and non-goals

Scope:

- add static JSON observations that resemble future Pi tool-call boundary inputs;
- add static expected AgentHarness mapping decisions;
- document how the fixture relates to existing AgentHarness evidence concepts;
- preserve order and independent decisions for a mixed batch.

T035 fixture non-goals at the time of fixture creation were:

- no schema file;
- no Pi repository modification;
- no Pi import, dependency, or call;
- no live hook implementation;
- no runtime adapter invocation;
- no tool execution;
- no runtime approval or safe-to-execute approval;
- no sandbox, auth gateway, signing, timestamping, attestation, trust-root, or governance enforcement.

T036 adds a library/test-only mock decision validator for these fixture files. T037 adds a stdout-only CLI wrapper around that validator. Neither task adds a schema, Pi dependency, live hook, runtime adapter invocation, tool execution, runtime approval, or safe-to-execute approval.

## Relationship to T034

T034 established the contract boundary in [`docs/17-pi-integration-boundary-and-contract.md`](./17-pi-integration-boundary-and-contract.md): contract design is ready, live runtime integration is not ready, Pi modification is not ready, and a mock/dry-run adapter mapping task is acceptable if separately planned.

T035 is that mock/dry-run fixture step. It turns the conceptual Pi → AgentHarness request and AgentHarness → Pi decision shapes into static JSON examples.

T036 adds a pure AgentHarness-side mock decision validator for these static files. T037 exposes that validator through `./agentharness pi contract-check` for static fixture inputs only. Neither calls Pi or implements `beforeToolCall`.

## Fixture files and purpose

| File | Purpose |
| --- | --- |
| [`examples/pi_tool_call_mapping/pi_tool_call_observations.json`](../examples/pi_tool_call_mapping/pi_tool_call_observations.json) | Static Pi-like observation batch with ordered tool-call candidates. |
| [`examples/pi_tool_call_mapping/expected_mapping.json`](../examples/pi_tool_call_mapping/expected_mapping.json) | Expected AgentHarness mapping outcome for each observation. |
| [`examples/pi_tool_call_mapping/README.md`](../examples/pi_tool_call_mapping/README.md) | Fixture-local boundary summary. |

The JSON files are deterministic, parse with `python3 -m json.tool`, and remain `result_status: not_executed`.

## Pi-like observation shape

Each observation is static data with fields such as:

- `observation_id`
- `order_index`
- `tool_call_id`
- `tool_name`
- `arguments_digest` or malformed/null placeholder for error cases
- redacted `arguments_summary`
- `category_candidate`
- `intent_candidate`
- `target_scope_candidate`
- `session_ref`
- `task_ref`
- optional existing AgentHarness fixture references

The batch-level metadata uses:

- `kind: pi_tool_call_observation_batch`
- `schema_version: 0.1.0`
- `source: static_fixture_not_from_pi_runtime`
- `result_status: not_executed`
- `pi_facts_source` pointing to T034/docs17 planning facts, not live runtime capture.

## Expected mapping shape

Each expectation maps one observation to one static decision:

- `allow_candidate`
- `block`
- `unsupported`
- `error`

The expectation includes a deterministic reason and evidence references to existing AgentHarness fixture concepts only. `allow_candidate` means only "candidate match to existing AgentHarness evidence"; it is not execution approval, runtime approval, or safe-to-execute approval. T035 fixture review and any future T036 fixture validation must not emit, infer, or normalize `allow_candidate` into runtime allow.

## Mapping case table

| Observation | Pi-like case | Expected decision | Existing AgentHarness concept |
| --- | --- | --- | --- |
| `pi-obs-001-read-workspace` | read-like repository inspection | `allow_candidate` | `TR-read`, `file_read`, `inspect_workspace`, `repository`, `handoff_ready` |
| `pi-obs-002-read-unsupported-intent` | read-like unsupported intent | `unsupported` | `TR-read-unsupported-intent`, unsupported `inspect_config` |
| `pi-obs-003-edit-write-like` | write/edit-like call | `unsupported` | no current Pi mapping fixture support; fail closed until future adapter support exists |
| `pi-obs-004-bash-shell` | bash/shell-like call | `block` | `TR-deny-unknown`, `shell`, `run_tests`, blocked by policy/no safe mapping |
| `pi-obs-005-malformed-missing-tool` | malformed observation | `error` | no mapping; required fields absent |
| `pi-obs-006-read-outside-scope` | read-like unsupported scope | `unsupported` | no repository-scoped ready match for outside scope |

All six observations are in one mixed batch so a future validator can prove order preservation and independent decisions.

## Known gaps beyond the T036 mock validator

T036 validates the static fixture against current export/manifest evidence, but future tasks must still refine:

- canonical argument normalization and digest generation;
- exact mapping from Pi tool names to AgentHarness categories/intents/scopes;
- how malformed observations are reported;
- how batch ordering is checked;
- how evidence refs bind to export item and manifest digests;
- how to keep sensitive arguments redacted;
- what fixture expansions are needed for approval-backed write/delete cases;
- whether a conceptual schema is needed after the fixture shape is accepted.

## T036 invariant checklist

A future T036 mock decision validator must not treat digest/provenance binding as already solved. It must explicitly validate or continue to fail closed on:

- canonical argument normalization;
- argument digest generation;
- evidence binding to registry-backed handoff/export/manifest evidence;
- redaction rules;
- tamper rejection;
- `result_status: not_executed`;
- preservation of `allow_candidate` as a candidate evidence match only, never runtime allow.

## Why this still does not modify or depend on Pi

The fixture is hand-authored from T034 planning facts. It is not captured from a live Pi runtime and it does not require Pi files at runtime.

T035 does not:

- modify the Pi repository;
- import Pi packages;
- add a Pi dependency;
- call Pi code;
- implement `beforeToolCall`;
- execute tools;
- add AgentHarness source, schema, test, or CLI behavior.

## T036 mock decision validator

T036 adds a pure in-memory validator that reads these static JSON fixtures and checks:

- JSON kind/schema version;
- `result_status: not_executed`;
- one expectation per observation;
- order preservation;
- allowed decision vocabulary;
- no `allow_candidate` for malformed, blocked, unsupported, or unknown cases.

T036 still avoids Pi modification/import/dependency/calls and does not implement live Pi integration.

## T037 dry-run contract CLI

T037 adds `./agentharness pi contract-check` as a thin CLI wrapper around the T036 validator for static fixture inputs only. It prints `pi_tool_call_mapping_validation_report` JSON to stdout, exits `0` only when `ok:true`, and rejects writer/action flags through argparse. It is still not live Pi integration, runtime approval, or safe-to-execute approval. See [`docs/19-pi-contract-check-cli.md`](./19-pi-contract-check-cli.md).

## Next loop: T038 Pi-side dry-run hook spike

If T037 is accepted, T038 may be planned as a Pi-side opt-in dry-run hook spike only after explicit approval to modify Pi. T038 must remain dry-run/block-oriented by default and must not reinterpret `allow_candidate` as runtime allow.
