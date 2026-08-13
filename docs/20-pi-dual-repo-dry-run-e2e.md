# Pi Dual-Repo Dry-Run E2E

Last checked date: 2026-07-07

AgentHarness is a pre-execution evidence control-plane for agent actions.

## Scope

This document records the T039 local dual-repo dry-run E2E between Pi and
AgentHarness. It proves wiring only:

1. Pi reaches its opt-in AgentHarness dry-run gate before tool execution.
2. Pi invokes the local AgentHarness CLI as a subprocess.
3. AgentHarness returns deterministic `pi contract-check` evidence.
4. Pi still blocks before any fake tool execution.

This is true local wiring with fake execution. It is not runtime allow, production
approval, safe-to-execute approval, auth, sandboxing, signing, timestamping,
attestation, trust-root, governance enforcement, daemonization, or scheduling.

## Environment contract

The E2E is opt-in and uses reviewer-owned environment variables:

```bash
PI_AGENTHARNESS_E2E=1
AGENTHARNESS_REPO=/path/to/AgentHarness
```

The Pi test derives the dry-run gate variables from `AGENTHARNESS_REPO`:

```text
PI_AGENTHARNESS_DRY_RUN=1
PI_AGENTHARNESS_CLI=$AGENTHARNESS_REPO/agentharness
PI_AGENTHARNESS_OBSERVATIONS=$AGENTHARNESS_REPO/examples/pi_tool_call_mapping/pi_tool_call_observations.json
PI_AGENTHARNESS_EXPECTATIONS=$AGENTHARNESS_REPO/examples/pi_tool_call_mapping/expected_mapping.json
PI_AGENTHARNESS_BUS_ROOT=$AGENTHARNESS_REPO/examples/agent_bus_adapter_registry
```

No AgentHarness source path is hardcoded in Pi source or test files; the local path
comes from the reviewer-provided environment.

## Copy-paste local command

From the Pi repo root:

```bash
: "${AGENTHARNESS_REPO:?set it to the local AgentHarness checkout}"
PI_AGENTHARNESS_E2E=1 \
AGENTHARNESS_REPO="$AGENTHARNESS_REPO" \
npm --workspace @earendil-works/pi-coding-agent test -- test/agentharness-dry-run-e2e.test.ts
```

From the AgentHarness repo root, the evidence command used by the gate is equivalent
to:

```bash
PYTHONDONTWRITEBYTECODE=1 ./agentharness pi contract-check \
  examples/pi_tool_call_mapping/pi_tool_call_observations.json \
  examples/pi_tool_call_mapping/expected_mapping.json \
  examples/agent_bus_adapter_registry
```

## Expected evidence

The AgentHarness command emits deterministic JSON with:

- `kind: pi_tool_call_mapping_validation_report`
- `result_status: not_executed`
- `ok: true`
- ordered decisions including one `allow_candidate`

`allow_candidate` means candidate evidence binding only. Pi must not normalize it
into runtime allow.

## Expected Pi behavior

For the positive case:

- Pi invokes the real local AgentHarness CLI.
- Pi receives `ok:true` evidence.
- Pi returns a blocked tool result before fake tool `execute()` runs.
- The block reason includes an AgentHarness report summary such as `report_ok=true`
  and `allow_candidate=1`.
- The block reason states that evidence is not execution approval.

For failure cases:

- missing AgentHarness CLI path fails closed and blocks;
- bad fixture path fails closed and blocks;
- mismatched expectation fixture fails closed and blocks;
- fake tool `execute()` remains uncalled in every enabled dry-run case.

## Observed T039 review result

Observed locally on 2026-07-07:

- `agentharness-dry-run-e2e.test.ts`: 4 tests passed with `PI_AGENTHARNESS_E2E=1`.
- The same E2E test file skipped all 4 tests when `PI_AGENTHARNESS_E2E` was absent.
- Existing `agentharness-dry-run-gate.test.ts`: 7 tests passed.
- Pi coding-agent build passed.
- AgentHarness `pi contract-check` emitted `result_status: not_executed` and
  `ok: true`.

## Boundary reminder

T039 does not authorize real Pi tool execution. The next safe loop, if separately
planned, is a controlled read-only allow/block proof of concept. Until that exists,
Pi-side AgentHarness integration remains dry-run evidence wiring only.
