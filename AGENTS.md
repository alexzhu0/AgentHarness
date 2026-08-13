# AgentHarness Repository Guidance

## Development workflow

- Superpowers is the only active development workflow for new AgentHarness
  work.
- Load `superpowers:using-superpowers` before task actions and apply the
  relevant Superpowers skills.
- Use `superpowers:brainstorming` and an approved design before creative or
  behavior-changing work. Use `superpowers:writing-plans` for multi-step
  implementation.
- Use `superpowers:test-driven-development` for behavior changes,
  `superpowers:systematic-debugging` for failures,
  `superpowers:requesting-code-review` before integration, and
  `superpowers:verification-before-completion` before completion claims.
- Do not start OMX, `ralplan`, team-runtime, or new `.omx` task state for this
  repository unless the user explicitly reverses this migration.
- Existing `.omx` plans, context, logs, and historical release references are
  provenance only and do not define the active workflow.

## Product boundary

- AgentHarness is a pre-execution evidence control-plane. It does not own or
  grant runtime authorization.
- Treat `allow_candidate` as candidate evidence only. It must never cause tool
  execution or be documented as permission.
- Preserve `result_status: not_executed` for the current Pi evidence and shadow
  integration surfaces.
- Keep AgentHarness and external runtime repositories as separate change,
  review, commit, and release units.
- A real execution path requires a new external-runtime design, implementation,
  adversarial test, and approval gate. It cannot be inferred from repository
  tests or evidence-contract success.

## Security and compatibility

- Parse bounded inputs and emit one bounded deterministic output document.
- Fail closed on malformed, ambiguous, unverifiable, linked, changed,
  oversized, or internally failing evidence. Exact current-call binding rejects
  cross-call response replay; same-request replay detection is outside v1.
- Do not expose absolute host paths, exception text, credentials, raw tool
  arguments, or untrusted evidence identifiers in CLI output.
- Preserve exact request/response and current-call binding before accepting any
  evidence response.
- Keep existing policy, loop-bus, handoff, audit, and static Pi contract CLI
  behavior backward compatible unless a reviewed plan says otherwise.

## Required verification

Run from the repository root without writing Python bytecode:

```bash
PYTHONDONTWRITEBYTECODE=1 ./agentharness validate \
  examples/agent_policy.example.yaml
PYTHONDONTWRITEBYTECODE=1 ./agentharness eval \
  --cases PI-001,PD-001,SEC-001
PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check examples/agent_bus
PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check \
  examples/agent_bus_adapter_registry
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
git diff --check
```

For evidence-contract changes, also run the six-module targeted suite recorded
in `docs/29-agentharness-maintenance-closure.md`.

## Maintenance and release truth

- Keep generated Python bytecode, pytest caches, virtual environments, build
  output, credentials, and raw external logs out of Git.
- Date-named source records under `release/` are indexed newest first in
  `release/README.md`.
- A committed release record is not a Git tag, pushed tag, public release,
  package publication, deployment, runtime authorization, or production
  certification.
- Stage explicit paths only. Never use repository-wide staging to absorb
  unrelated concurrent work.
- Verify the exact staged file list and `git diff --cached --check` before each
  commit.
