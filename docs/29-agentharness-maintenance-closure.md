# AgentHarness Local Maintenance Closure

Date: 2026-08-11

## Decision

The previously dirty T056-T062 AgentHarness milestone is ready for scoped local
commits after fresh repository-native verification and final review. The
historical T061 no-commit handoff remains a truthful record of its original
state; the user's later explicit directive authorizes this AgentHarness-only
maintenance closure.

This closure does not modify the Pi repository. It does not authorize or claim
a tag, push, public release, package publication, deployment, runtime power-on,
real tool execution, or production certification.

## Included behavior

- The versioned Pi observation/evidence contract validates bounded canonical
  requests, builds one-read evidence snapshots, emits deterministic bounded
  responses, and verifies exact current-call binding.
- The evidence evaluator remains evidence-only. Every result has
  `result_status: not_executed`; `allow_candidate` is never execution
  permission.
- Ambiguous, unprovable, malformed, oversized, symlinked, changed, or
  disclosure-bearing evidence fails closed without leaking host paths,
  exception text, credentials, or untrusted identifiers. Exact current-call
  binding rejects cross-call response replay; same-request freshness and replay
  detection remain outside v1.
- Snapshot capture binds a no-follow directory descriptor, rejects root swaps,
  and bounds YAML depth, node count, anchors, aliases, and merge keys.
- Handoff export, manifest, loop-bus, and Pi mapping failures redact absolute
  host paths while preserving useful relative-path diagnostics.
- Pi mapping validates the exact lowercase `sha256:<64 hex>` argument-digest
  shape, exact integer positional order, and duplicate-free JSON before it can
  produce candidate evidence.

## Included repository assets

The scoped milestone consists of:

- AgentHarness source under `src/agentharness/` for the evidence contract, CLI,
  loop-bus redaction, and Pi mapping validation;
- the six directly changed or added test modules under `tests/`;
- the request schema, response schema, and canonicalization vectors under
  `schemas/`;
- the updated README, asset map, historical boundary corrections, ADR,
  preflight, continuity, handoff, and dated release records; and
- repository guidance plus Python cache ignore rules in `AGENTS.md` and
  `.gitignore`.

Generated Python bytecode and test caches are not milestone assets and are
excluded from Git.

## Fresh verification

The final pre-commit verification used Python 3.10.12 and did not access the
network or the Pi repository.

```text
./agentharness validate examples/agent_policy.example.yaml
PASS policy validation

./agentharness eval --cases PI-001,PD-001,SEC-001
PASS: 3/3 smoke evaluations

./agentharness loop check examples/agent_bus
./agentharness loop check examples/agent_bus_adapter_registry
PASS: both loop-bus fixtures

python3 -m unittest -q \
  tests.test_handoff_exporter \
  tests.test_handoff_manifest \
  tests.test_loop_bus \
  tests.test_pi_tool_call_mapping \
  tests.test_pi_evidence_contract_v1 \
  tests.test_pi_evidence_contract_cli_v1
PASS: 150/150 tests in 17.961s

python3 -m unittest discover -s tests -q
PASS: 389/389 tests in 34.527s

python3 -m pip wheel --no-deps --no-build-isolation .
PASS: agentharness-0.1.0-py3-none-any.whl, 86,477 bytes
```

Additional checks passed for Python source syntax, all three JSON assets,
local Markdown links, line lengths in the closure-owned documentation, and Git
whitespace. The wheel used the declared build requirement through isolated
temporary setuptools 84.0.0 and wheel 0.47.0 tooling. Its archive contains the
new evidence-contract module and the `agentharness` entry point. Its SHA-256 is
`0952364b7ae0614a1947ef4198d04341f1f9e6f02088f16694a74aaa764ba1f1`.
No generated cache or build output is included in the repository. Installing
that wheel into a separate temporary target and running its generated
`agentharness --help` entry point from outside the repository also passed.

## Runtime and release truth

- AgentHarness remains a pre-execution evidence control-plane.
- Runtime authorization and execution remain owned by an external runtime.
- The current integration boundary remains block-only and `not_executed`.
- T060/T062 runtime authorization remains `NO-GO` and `NOT IMPLEMENTED`.
- This maintenance closure permits scoped local commits only.
- No tag, push, public release, package publication, or deployment is performed
  by this closure.

## Future work

Future AgentHarness work must preserve deterministic evidence, exact call
binding, path and secret redaction, fail-closed error handling, and the strict
separation between candidate evidence and runtime authorization. Any real
execution path requires a new, separately reviewed external-runtime gate.
