# Pi Controlled Read-Only PoC

Last checked date: 2026-07-07

AgentHarness is a pre-execution evidence control-plane for agent actions.

## Scope

This document records the T040 controlled read-only allow/block proof of concept
between Pi and AgentHarness. It is a test-only seam demonstration:

- Pi calls local AgentHarness `pi contract-check` evidence.
- Pi may allow exactly one hermetic fake read-only test tool.
- Every other observed case blocks before fake tool execution.
- AgentHarness evidence remains `result_status: not_executed`.

This is not production runtime allow, safe-to-execute approval, auth, sandboxing,
signing, timestamping, attestation, trust-root, governance enforcement, shell
execution, network access, or a real filesystem write/read authorization.

## Environment contract

The PoC is disabled by default. The T039 dry-run block-only behavior remains active
unless this extra variable is set:

```bash
PI_AGENTHARNESS_READ_ONLY_POC=1
```

The full local E2E command from the Pi repo root is:

```bash
PI_AGENTHARNESS_E2E=1 \
AGENTHARNESS_REPO=/home/alex/DTAlex/learningGitHub/AgentHarness \
npm --workspace @earendil-works/pi-coding-agent test -- \
  test/agentharness-read-only-poc-e2e.test.ts
```

The Pi test derives AgentHarness paths from `AGENTHARNESS_REPO`; no local
checkout path is hardcoded in Pi source.

## Exact allow conditions

The fake read-only tool may execute only when all checks pass:

1. AgentHarness CLI exits `0`.
2. AgentHarness report JSON is valid.
3. `report.ok === true`.
4. `report.result_status === "not_executed"`.
5. The report includes `allow_candidate` evidence.
6. The current tool name is exactly `read_workspace`.
7. The current args are exactly `{ "path": "README.md" }`.
8. The path is repository-relative and contains no absolute path, `..`, glob,
   or shell semantics.

If any condition fails, Pi blocks before fake tool execution.

## Observed T040 result

Observed locally on 2026-07-07:

- `agentharness-read-only-poc-e2e.test.ts`: 6 tests passed with the E2E env.
- Positive case executed fake `read_workspace` exactly once.
- Default T039 compatibility still blocked when
  `PI_AGENTHARNESS_READ_ONLY_POC` was absent.
- Missing CLI, bad fixture, mismatched expectation, write-like tool,
  shell-like tool, and unsafe paths all blocked with zero fake executions.
- Existing dry-run E2E and dry-run gate tests still passed.
- Pi coding-agent build passed.

## Boundary reminder

T040 proves only that a narrow allow/block branch can be represented in tests.
It does not make AgentHarness a production permission system, does not
authorize real Pi tool execution, and does not create a generic
`allow_candidate` to runtime allow mapping.
