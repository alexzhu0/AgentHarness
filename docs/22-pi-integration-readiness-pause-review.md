# Pi Integration Readiness Pause Review

Last checked date: 2026-07-07

AgentHarness is a pre-execution evidence control-plane for agent actions.

> **Supersession/current-baseline note (2026-07-12):** The T040 result below
> remains historical six-test PoC evidence, including one positive fake read
> execution. T058 supersedes any implication that this historical allow branch
> is current: Pi production live mode sends current `beforeToolCall` data through
> `evidence-evaluate-v1`, verifies exact current-call correlation, and blocks
> every valid outcome, including synthetic correlated `allow_candidate`, with
> `result_status: not_executed`. AgentHarness executes no tool; Pi owns runtime
> enforcement.

## Scope

T041 is a pause and review artifact. It is not implementation, not a Pi
source change, and not a live integration step.

AgentHarness remains a pre-execution evidence control-plane. Pi owns runtime
enforcement, and its current AgentHarness production live path blocks before
real tool execution.

This document records the stop line after T040: the controlled read-only PoC
showed a narrow test seam, but it did not approve real Pi execution.

## Current proven chain

The historical Pi-facing evidence chain through T040 is:

1. T034 boundary contract: AgentHarness and Pi responsibilities were separated.
2. T035 static Pi-like mapping fixture: observations and expected decisions
   were captured without importing, calling, or modifying Pi.
3. T036 mock validator: static observations were checked against
   AgentHarness export and manifest evidence.
4. T037 `pi contract-check` CLI: the validator became a stdout-only contract
   check returning `result_status: not_executed`.
5. T038/T039 Pi opt-in dry-run gate and dual-repo E2E: Pi called the local
   AgentHarness CLI and still blocked before fake tool execution.
6. T040 exact fake read-only allow/block PoC: with explicit opt-in, one
   hermetic fake `read_workspace` call for `{ "path": "README.md" }` could
   run in tests, while all other tested cases blocked.

## Current stop line

The current stop line is intentionally strict:

- No production runtime allow.
- No generic `allow_candidate` to allow conversion.
- No real Pi tool authorization.
- No safe-to-execute approval claim.
- No auth, sandbox, signing, timestamp, trust-root, or governance
  implementation.
- No daemon, watcher, scheduler, or background service.
- No broadening of `PI_AGENTHARNESS_READ_ONLY_POC` beyond the exact fake test
  case.
- The T040 fake allow branch is historical and is not an input or authorization
  path for T058 production live mode.

## Readiness decision

```yaml
ready_for_real_execution: false
ready_for_next_planning_loop: true
recommended_next_loop: >-
  Production precondition spec, manual approval boundary, and runtime
  ownership contract before any live execution.
```

Interpretation:

- The evidence chain is ready for the next explicit planning loop.
- It is not ready for real Pi execution.
- T041 does not authorize tool execution, production allow, or a generic
  allow/block policy.

## Preconditions before any live Pi execution

Before any future task may plan live Pi execution, reviewers should require:

1. Explicit runtime owner boundary in Pi.
2. Real Pi tool inventory and classification.
3. Manual approval or policy approval semantics.
4. Sandbox and permission model owned outside AgentHarness.
5. Audit persistence strategy for decisions and evidence.
6. Replayable evidence IDs and digests.
7. Failure-mode matrix for CLI failures, stale evidence, tampering, and drift.
8. Rollback and kill-switch behavior.
9. No host path or secret leakage in reviewer or runtime-facing messages.
10. Tests proving default block behavior when opt-in variables are absent.
11. Tests proving `allow_candidate` never becomes generic runtime allow.
12. A human gate for any destructive, credentialed, external-production, or
    materially scope-changing behavior.

## Reviewer TODO checklist

- [ ] Inspect AgentHarness docs/release diff:

  ```bash
  git diff -- README.md docs/00-asset-map.md \
    docs/22-pi-integration-readiness-pause-review.md \
    release/2026.07.07.md
  ```

- [ ] Confirm AgentHarness has no T041 source/test/schema/example diff:

  ```bash
  git diff -- src tests schemas examples pyproject.toml agentharness
  ```

- [ ] Confirm Pi has no T041 diff beyond pre-existing T040 work:

  ```bash
  git -C /home/alex/DTAlex/learningGitHub/pi diff -- \
    packages/coding-agent/src packages/coding-agent/test \
    package.json package-lock.json pnpm-lock.yaml yarn.lock
  ```

- [ ] Run contract-check and confirm `ok=True` plus
      `result_status=not_executed`.
- [ ] Run full AgentHarness unittest discovery.
- [ ] Run markdownlint on README, docs, and release files.
- [ ] Confirm docs do not claim production allow, safe-to-execute approval, or
      real Pi tool authorization.
- [ ] Confirm cache probe is empty after cleanup.

## Failure probes

Use these probes before accepting the pause review:

```bash
git diff -- src tests schemas examples pyproject.toml agentharness
```

Expected for T041: no new T041 output. Any existing diff must be classified as
pre-existing and outside this docs/release-only task.

```bash
git -C /home/alex/DTAlex/learningGitHub/pi diff -- \
  packages/coding-agent/src \
  packages/coding-agent/test \
  package.json package-lock.json pnpm-lock.yaml yarn.lock
```

Expected for T041: no Pi edits caused by T041. Pre-existing T040/T038/T039 work
must be reported, not absorbed.

```bash
rg -n \
  -e "production allow" \
  -e "safe-to-execute" \
  -e "safe to execute" \
  -e "real Pi tool authorization" \
  -e "generic runtime allow" \
  docs/22-pi-integration-readiness-pause-review.md \
  README.md docs/00-asset-map.md release/2026.07.07.md || true
```

Expected: matches, if any, must be boundary-negative wording only.

```bash
PYTHONDONTWRITEBYTECODE=1 ./agentharness pi contract-check \
  examples/pi_tool_call_mapping/pi_tool_call_observations.json \
  examples/pi_tool_call_mapping/expected_mapping.json \
  examples/agent_bus_adapter_registry
```

Expected: deterministic JSON with `ok: true` and
`result_status: not_executed`.

```bash
find . \( -name 'pycache' -o -name '__pycache__' -o -name '*.pyc' \) -print
```

Expected after cleanup: no output.

## Next task boundary

A future T042 may plan preconditions for live integration. T042 should define
runtime ownership, approval semantics, tool inventory, failure handling, audit
persistence, and rollback gates before any implementation task attempts live Pi
execution.

T041 itself must not implement live execution, broaden the PoC, alter Pi, or
claim that any current evidence is safe to execute.
