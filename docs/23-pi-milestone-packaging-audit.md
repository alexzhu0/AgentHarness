# Pi Milestone Packaging Audit

Last checked date: 2026-07-07

AgentHarness is a pre-execution evidence control-plane for agent actions.

## Scope

T042 is a packaging audit only. It is not a commit, push, release, or
implementation task.

This document does not make AgentHarness or Pi production-ready. It does not
authorize real Pi tool execution, production runtime allow, safe-to-execute
approval, or a generic `allow_candidate` to runtime allow mapping.

The purpose is to classify the T034-T041 Pi-facing milestone so a future human
reviewer can decide whether to package AgentHarness locally without mixing in Pi
companion work or unrelated dirty files.

## Milestone covered

This audit covers the Pi-facing milestone chain:

1. T034 Pi boundary contract.
2. T035 Pi-like mapping fixture.
3. T036 mock decision validator.
4. T037 `pi contract-check` CLI.
5. T038/T039 Pi-side opt-in dry-run gate and dual-repo E2E.
6. T040 controlled read-only PoC.
7. T041 readiness pause review.
8. T042 packaging audit.

The milestone is still pre-execution and reviewer-facing. T040 proved only a
controlled fake read-only test path, not production readiness.

## AgentHarness include set

A future human-approved local AgentHarness milestone package should include only
reviewed AgentHarness files needed for T034-T042:

- `README.md` navigation and command notes for the Pi-facing docs and CLI.
- `docs/00-asset-map.md` entries for T034-T042.
- `docs/17-pi-integration-boundary-and-contract.md`.
- `docs/18-pi-tool-call-mapping-fixture.md`.
- `docs/19-pi-contract-check-cli.md`.
- `docs/20-pi-dual-repo-dry-run-e2e.md`.
- `docs/21-pi-controlled-read-only-poc.md`.
- `docs/22-pi-integration-readiness-pause-review.md`.
- `docs/23-pi-milestone-packaging-audit.md`.
- `release/2026.07.07.md` release index and stop-line notes.
- `examples/pi_tool_call_mapping/` static observation and expectation fixtures.
- `src/agentharness/pi_tool_call_mapping.py` pure AgentHarness-side validator.
- `src/agentharness/cli.py` only for the accepted `pi contract-check`
  entrypoint.
- `tests/test_pi_tool_call_mapping.py`.
- `tests/test_pi_tool_call_mapping_cli.py`.

This include set is for AgentHarness packaging only. It does not include Pi
source or tests.

## AgentHarness exclude set

A future AgentHarness milestone package must exclude:

- Unrelated local files.
- `pycache`, `__pycache__`, and `*.pyc` files.
- `agent.md`, `Agent.md`, or `AGENTS.md` unless a later reviewer explicitly
  approves a tracked agent-file change.
- Dependency or lockfile changes not part of accepted plans.
- Any broad markdownlint cleanup not reviewed as part of this milestone.
- Any new runtime adapter, daemon, watcher, scheduler, auth, sandbox, signing,
  timestamp, trust-root, governance, or live execution surface.

## Pi companion status

Pi is a companion repo for this milestone, but T042 does not edit Pi and should
not package Pi files into an AgentHarness commit.

Classify Pi state separately:

- Pi T039/T040 companion files that may belong to a separate Pi-side package
  later:
  - `packages/coding-agent/src/core/agent-session.ts` composition diff.
  - `packages/coding-agent/src/core/agentharness-dry-run-gate.ts`.
  - `packages/coding-agent/test/agentharness-dry-run-e2e.test.ts`.
  - `packages/coding-agent/test/agentharness-dry-run-gate.test.ts`.
  - `packages/coding-agent/test/agentharness-read-only-poc-e2e.test.ts`.
- Pi unrelated Win9/settings dirty files that must not be bundled with
  AgentHarness milestone packaging:
  - `.pi/agents/win9-main.md`.
  - `.pi/extensions/win9-orchestrator/index.ts`.
  - `packages/coding-agent/src/core/settings-manager.ts`.
  - `packages/coding-agent/src/win9/evidence-packet.ts`.
  - `packages/coding-agent/src/win9/prompt-guard.ts`.
  - `packages/coding-agent/test/settings-manager.test.ts`.
  - `packages/coding-agent/test/win9-assets.test.ts`.
  - `packages/coding-agent/test/win9-orchestrator.test.ts`.
  - `scripts/win9-eval-runner.mjs`.

No Pi commit or push is allowed in T042.

## Future commit strategy

If a later user explicitly approves packaging, use a narrow staging strategy:

1. Do not run `git add .`.
2. Stage by explicit file list or patch staging.
3. Verify staged names before committing:

   ```bash
   git diff --cached --name-only
   git diff --cached -- src tests schemas examples pyproject.toml agentharness
   git status --short -- agent.md Agent.md AGENTS.md
   ```

4. Package AgentHarness milestone work separately from any Pi-side package.
5. Keep Pi companion files out of AgentHarness commits.
6. Use the Lore commit protocol if a later user explicitly approves a local
   commit.
7. Do not push unless separately approved.

## Verification checklist

Before accepting a future package, rerun at least:

```bash
PYTHONDONTWRITEBYTECODE=1 ./agentharness pi contract-check \
  examples/pi_tool_call_mapping/pi_tool_call_observations.json \
  examples/pi_tool_call_mapping/expected_mapping.json \
  examples/agent_bus_adapter_registry
```

Expected: `ok: true` and `result_status: not_executed`.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

Expected: full AgentHarness tests pass.

```bash
git diff -- src tests schemas examples pyproject.toml agentharness
```

Expected for T042: no new T042 edits. Existing pre-T042 milestone diffs must be
classified before staging.

```bash
git -C /home/alex/DTAlex/learningGitHub/pi status --short -- \
  .pi scripts packages/coding-agent/src packages/coding-agent/test \
  package.json package-lock.json pnpm-lock.yaml yarn.lock
```

Expected: Pi dirty work is classified, not edited by T042.

```bash
find . \( -name 'pycache' -o -name '__pycache__' -o -name '*.pyc' \) -print
```

Expected after cleanup: no output.

## Decision

`COMMENT`: packageable after explicit reviewer classification, but current repos
are not merge-clean and Pi has unrelated dirty work.

This is not `GO` because AgentHarness and Pi both have dirty work that needs
explicit classification before staging. It is not `NO-GO` because the accepted
AgentHarness Pi-facing evidence chain still verifies and remains
`result_status: not_executed`.

## Next boundary

After T042, the project should either:

- package the AgentHarness milestone locally after explicit approval; or
- plan T043 production precondition spec.

Do not start live Pi execution without a separate approved plan. Do not treat
T040's fake read-only test path as production allow, safe-to-execute approval,
or generic runtime policy.
