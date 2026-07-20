# AgentHarness Development Loop Operating Model

AgentHarness is a pre-execution evidence control-plane for agent actions.

This document governs the **development workflow** for future AgentHarness `T0xx` tasks. It does not add AgentHarness product behavior, runtime behavior, CLI behavior, schemas, fixtures, dependencies, or execution-plane integration.

The operating model exists to make every development loop auditable: each task should state its goal, scope, checks, failure probes, stop condition, human gates, reviewer gates, and next-loop handoff before anyone claims acceptance.

## Scope and non-goals

This document owns process discipline for AgentHarness development tasks:

- how a task is packaged for execution;
- how the executor reports evidence;
- how the reviewer accepts, comments, or rejects;
- how failures become the next loop instead of silent scope drift.

Non-goals:

- no runtime execution, runtime adapter invocation, or execution-plane integration;
- no daemon, scheduler, watcher, queue, or realtime chat surface;
- no run, execute, dispatch, submit, or task-mutation CLI;
- no lifecycle state expansion;
- no auth, sandbox, signing, timestamp, attestation, trust-root, or governance implementation;
- no new product output writer flags;
- no dependency adoption;
- no replacement for human review.

If a future task needs product behavior, it must be proposed as a separate task with explicit allowed scope and reviewer approval. This operating model by itself is documentation only.

## Roles and responsibilities

| Role | Responsibility | Must not do |
| --- | --- | --- |
| Human gate / project designer | Defines intent, hard boundaries, acceptance criteria, and whether commits or external actions are allowed. | Delegate destructive, credentialed, external-production, or materially scope-changing decisions implicitly. |
| Executor / maker | Implements the allowed task, records evidence, runs checks, and reports exact outputs. | Self-approve completion, widen scope silently, hide failures, commit/push without explicit approval. |
| Reviewer / checker | Inspects actual repo state, diffs, outputs, and probes before deciding ACCEPT / COMMENT / REJECT. | Accept from summary alone, skip changed-file review, or treat executor confidence as approval. |
| Future external owner | Owns runtime, governance, auth, identity, sandbox, signing, trust-root, deployment, or operations decisions when those questions appear. | Treat AgentHarness evidence acceptance as runtime approval. |

The maker/checker split is mandatory: the executor can report that checks passed, but the executor cannot self-approve the task as accepted.

## Loop Task Packet schema

Every future `T0xx` task should arrive as a Loop Task Packet. The packet may be a markdown task plan, JSON handoff, or user message, but it should contain these fields.

```yaml
Task ID: T0xx-short-name
Goal: >
  One or two sentences describing the outcome, not the implementation details.
Context:
  - Current accepted baseline or prerequisite task.
  - Relevant planning artifacts and current repo assumptions.
Allowed scope:
  - Explicit file paths or path classes the executor may modify.
Forbidden scope:
  - Paths, behaviors, dependencies, integrations, and side effects that are out of scope.
TODO list:
  - Ordered implementation steps.
Checks:
  - Commands or inspections that must pass before reporting completion.
Failure probes:
  - Negative/static probes that prove boundaries were not crossed.
Stop condition: >
  The exact condition under which the executor stops and reports, including blockers.
Human gate: >
  Decisions requiring explicit human approval before proceeding.
Executor report format:
  - Changed files.
  - What changed.
  - Check outputs.
  - Failure-probe outputs and interpretation.
  - Known gaps.
Reviewer gate:
  - ACCEPT, COMMENT, or REJECT criteria.
Next loop hint: >
  If accepted or rejected, the likely follow-up task shape.
```

A packet is incomplete if it lacks allowed scope, forbidden scope, checks, failure probes, or a reviewer gate.

## T0xx lifecycle: plan → execute → report → review → fix → accept → next-loop

1. **Plan**: Human gate or planner defines the Loop Task Packet.
2. **Execute**: Executor modifies only allowed paths and preserves existing accepted work.
3. **Report**: Executor gives evidence in the required format, including exact command outputs and probe interpretation.
4. **Review**: Reviewer inspects actual repo state, diffs, tests, and boundary probes.
5. **Fix**: If review returns COMMENT or REJECT, executor performs only the requested repair scope.
6. **Accept**: Reviewer or human gate marks the task accepted after inspecting evidence.
7. **Next-loop**: Accepted output becomes context for the next Loop Task Packet; unresolved gaps become explicit follow-up tasks.

Acceptance is a reviewer decision, not an executor claim. A task is not accepted merely because the executor reports passing checks.

## Maker/checker split

The maker/checker split prevents verifier theater and accidental self-approval.

Executor responsibilities:

- implement only the approved scope;
- run the smallest complete verification set required by the packet;
- preserve raw evidence or exact summarized output;
- clearly label failures, skipped checks, and interpretations;
- stop instead of widening scope when a required fix would leave the allowed scope.

Reviewer responsibilities:

- inspect `git status`, changed files, and relevant diffs;
- verify that changed files match the allowed scope;
- read enough output to confirm checks actually passed;
- confirm static probes are interpreted correctly;
- decide ACCEPT / COMMENT / REJECT.

## Required executor report format

Every executor report should include:

1. **Changed files**: exact paths, separated by task-owned and pre-existing/unrelated when needed.
2. **Implementation summary**: concise behavior or documentation change summary.
3. **Checks run**: commands and exact pass/fail output summaries.
4. **Failure probes**: negative/static probes and interpretation.
5. **Boundary confirmation**: no prohibited scope, no hidden runtime/product surface, no unexpected dependencies.
6. **Known gaps**: anything not tested, deferred, or requiring reviewer/human decision.
7. **Commit/push state**: whether no commit/no push was required and preserved, or exact commit hash if explicitly approved.

For docs-only tasks, the report must still include the no-code diff probe.

## Reviewer gate and ACCEPT / COMMENT / REJECT decisions

Reviewer decisions are explicit:

- **ACCEPT**: The reviewer inspected repo state, changed files, diffs, checks, and failure probes; the task meets its packet and no blocking issue remains.
- **COMMENT**: The task is directionally correct but needs small bounded changes. The reviewer must specify the allowed repair scope.
- **REJECT**: The task violates scope, fails required checks, hides a blocker, changes forbidden files, introduces prohibited behavior, or cannot be accepted without a new plan.

The reviewer must inspect actual repo state before accepting. A summary-only review is not enough.

## Standard checks library

Use the smallest relevant subset, but define it explicitly in the packet.

| Check | Typical command |
| --- | --- |
| Policy validation | `PYTHONDONTWRITEBYTECODE=1 ./agentharness validate examples/agent_policy.example.yaml` |
| Smoke eval | `PYTHONDONTWRITEBYTECODE=1 ./agentharness eval --cases PI-001,PD-001,SEC-001` |
| Golden loop check | `PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check examples/agent_bus_adapter_registry` |
| Handoff inspection | `PYTHONDONTWRITEBYTECODE=1 ./agentharness handoff inspect examples/agent_bus_adapter_registry` |
| Manifest readback | build manifest to reviewer-owned `/tmp` path, then `handoff verify-manifest` |
| Audit report readback | build audit report to reviewer-owned `/tmp` path, then `audit verify-report` |
| Enterprise checklist | `PYTHONDONTWRITEBYTECODE=1 ./agentharness audit checklist examples/agent_bus_adapter_registry` |
| Targeted tests | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest <module>` |
| Full tests | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q` |
| Formatting whitespace | `git diff --check` |

Reviewer-owned `/tmp` paths are shell redirection artifacts, not AgentHarness product writer behavior.

## Standard failure probes library

Use these probes when relevant to the task:

| Probe | Purpose |
| --- | --- |
| `git diff -- src tests schemas examples pyproject.toml agentharness` | Prove docs-only or no-product-change scope when required. |
| `git status --short -- agent.md` | Prove `agent.md` was not touched or staged. |
| Forbidden local runtime-candidate reference probe, using the project-approved path/import patterns for the task. | Prove no forbidden local integration, import, dependency, or test references. |
| `rg -n -e "daemon|scheduler|watcher|realtime chat|runtime adapter invocation|execute tools|task mutation|submit|dispatch|auto-merge|safe to execute" <changed docs> || true` | Find runtime/product-surface wording that must be boundary-negative or removed. |
| `find . \( -name 'pycache' -o -name '__pycache__' -o -name '*.pyc' \) -print` | Prove generated Python cache is absent after verification. |
| `git diff --check` | Catch whitespace and conflict-marker issues. |
| result-status scan | For evidence outputs, prove current handoff/export/manifest/report/checklist outputs remain `result_status: not_executed`. |
| staged-file check | Before commit, prove only approved paths are staged and `agent.md` is absent. |

Failure probes are not optional decoration. If a probe matches, the executor must interpret whether it is boundary-negative wording, existing negative test coverage, or an actual new surface.

## Human gate triggers

Stop and request explicit human approval before any of these:

- destructive file or repository operations beyond the approved task;
- credentialed access, secret handling, or external account changes;
- production or external-environment actions;
- runtime, adapter, execution-plane, governance, auth, sandbox, signing, timestamp, attestation, or trust-root work;
- adding dependencies or adopting an SDK/framework;
- expanding lifecycle states or adding task mutation surfaces;
- committing, pushing, rebasing, resetting, or staging broad file sets unless explicitly requested;
- materially changing the accepted task scope.

When in doubt, preserve local state and report the blocker rather than improvising a broader task.

## Stop conditions and escalation rules

Stop and report instead of continuing when:

- required verification fails and the repair would exceed allowed scope;
- a product bug is discovered during a docs-only task;
- a change would touch forbidden paths;
- the task would require runtime integration, external production action, credentials, or destructive behavior;
- the packet lacks enough information to avoid a materially different product decision;
- local repo state contains unrelated changes that cannot be separated safely.

Escalate to the reviewer for bounded repair instructions after COMMENT/REJECT. Escalate to the human gate for destructive, credentialed, runtime, external-production, or materially scope-changing decisions.

## State and memory rules

Development state must be repo-observable whenever possible:

- keep planning artifacts read-only unless the task explicitly authorizes editing them;
- preserve accepted uncommitted work from prior tasks unless explicitly told to revert it;
- separate new task changes from pre-existing work in reports;
- do not use hidden memory as proof of completion;
- use `git status`, `git diff`, command output, and committed files as the source of truth;
- after context compaction or long pauses, re-check current repo state before editing.

If state is ambiguous, inspect before changing. Do not assume stale context is still true.

## Commit/no-commit decision rules

Default: do not commit and do not push.

Commit only when the human explicitly asks for a local commit and provides or accepts the scope. Before committing:

- run the requested checks;
- remove generated cache files;
- stage only approved paths, never `git add .`;
- inspect `git diff --cached --name-only`;
- confirm `agent.md` is not staged;
- use the Lore commit message format when requested by the repo contract.

Push only when explicitly requested. A local commit does not imply permission to push.

## Long-task mode with checkpoint cadence

For long tasks, use checkpoints to prevent state rot:

- checkpoint after reading the packet and before editing;
- checkpoint after baseline observations or saved dry-run outputs;
- checkpoint after implementation before verification;
- checkpoint after verification with exact failures or pass evidence;
- checkpoint before any commit request.

A checkpoint should include current goal, changed files, completed checks, open blockers, and the next safe action. If a task spans multiple review cycles, each COMMENT/REJECT becomes a narrowed repair packet.

## Anti-patterns / failure modes

Avoid these failure modes:

- self-approval by the executor;
- passing tests but skipping boundary probes;
- expanding docs-only tasks into source or CLI changes;
- adding product surfaces while describing them as process cleanup;
- claiming runtime approval or safety from evidence readiness;
- hiding pycache, generated files, or unrelated local changes;
- using broad staging commands that capture unrelated files;
- treating reviewer-owned `/tmp` shell redirection as a product writer;
- interpreting manual checks as automated product behavior;
- burying failed commands behind a summary that says “mostly passed”.

## Next-loop generation rules

At the end of a task, generate the next loop only from evidence:

- Accepted gaps become optional future tasks, not silent follow-up work.
- Failed checks become bounded repair packets with allowed files and exact repro commands.
- Boundary questions become human-gated planning tasks.
- Runtime or external-owner questions remain deferred unless a future task explicitly approves that spike.
- A next-loop hint should include the likely task ID, goal, allowed scope, checks, and stop condition.

The next loop should make progress easier without weakening the AgentHarness product boundary.

For the Phase E packaging decision aid that applies this operating model to the current milestone, see [`docs/16-phase-e-release-readiness-and-packaging-audit.md`](./16-phase-e-release-readiness-and-packaging-audit.md).
