# AgentHarness Pi Contract-Check CLI

T037 adds a command wrapper around the T036 mock decision validator for static Pi-like fixture files.

This is a pre-execution contract check over committed AgentHarness fixtures. It is not live Pi integration, not a `beforeToolCall` implementation, not tool execution, not runtime approval, and not a safe-to-execute claim.

## Scope and non-goals

The command exists so reviewers and future runtime owners can run one deterministic check over:

- the T035 static Pi-like observation batch;
- the T035 expected mapping file;
- the registry-backed AgentHarness file bus fixture.

It does not:

- modify, import, depend on, test, or call Pi;
- observe live Pi runtime traffic;
- execute tools;
- emit runtime `allow` decisions;
- add output writer flags such as `--out`, `--write`, or `--save`;
- implement auth gateway, sandbox, signing, timestamping, attestation, trust-root, or governance enforcement.

## Command

```bash
./agentharness pi contract-check \
  examples/pi_tool_call_mapping/pi_tool_call_observations.json \
  examples/pi_tool_call_mapping/expected_mapping.json \
  examples/agent_bus_adapter_registry
```

The command accepts exactly three positional inputs:

1. `observations_path` — static Pi-like observation JSON.
2. `expectations_path` — static expected mapping JSON.
3. `bus_root` — registry-backed AgentHarness file-bus root.

It prints deterministic JSON to stdout only. Reviewers who want a saved artifact may use shell redirection outside AgentHarness.

## Output shape

The command reuses `build_pi_tool_call_mapping_report()` and preserves the T036 report shape:

```json
{
  "version": "0.1.0",
  "kind": "pi_tool_call_mapping_validation_report",
  "source": "build_pi_tool_call_mapping_report",
  "result_status": "not_executed",
  "ok": true,
  "summary": {},
  "decisions": [],
  "checks": [],
  "errors": [],
  "warnings": []
}
```

The actual `summary`, `decisions`, and `checks` are populated from the fixture and current AgentHarness evidence. All current outputs remain `result_status: not_executed`.

## Exit-code contract

- Exit `0` only when `ok` is `true`.
- Exit `1` when the report is valid JSON but `ok` is `false`.
- Exit `2` for argparse misuse such as unsupported flags.

Failure reports still print deterministic JSON to stdout unless the parser rejects invalid command syntax before running the report builder.

## Decision vocabulary

T037 preserves the T036 decision vocabulary exactly:

- `allow_candidate`
- `block`
- `unsupported`
- `error`

`allow_candidate` means only candidate evidence matching: the observation matched current AgentHarness export/manifest evidence and the expected mapping. It is not runtime allow, not runtime approval, and not safe-to-execute approval. Future code must not normalize `allow_candidate` into runtime `allow`.

## Evidence binding and safety posture

For `allow_candidate`, the underlying validator proves that:

- the request candidate exists in the registry-backed handoff export package;
- the same request exists in the digest manifest;
- export and manifest evidence remain `result_status: not_executed`;
- the gate says the handoff is ready;
- the observation request fields semantically match the exported request fields;
- returned report strings are sanitized so host-specific paths do not leak.

Unknown, malformed, unsupported, shell-like, tampered, stale, or semantically mismatched inputs fail closed and do not become `allow_candidate`.

## Relationship to T034-T036

- T034 defines the AgentHarness ↔ Pi boundary contract as planning only.
- T035 adds static Pi-like observations and expected mappings.
- T036 adds the pure AgentHarness-side mock decision validator.
- T037 exposes that validator through a stdout-only CLI contract check.

This sequence still does not modify Pi or implement a live hook.

## Next loop

If T037 is accepted, the next likely task is T038: a Pi-side opt-in dry-run hook spike. T038 would require explicit approval to modify Pi and must remain dry-run/block-oriented by default. T037 itself does not grant that approval.
