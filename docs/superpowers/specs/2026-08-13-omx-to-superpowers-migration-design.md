# AgentHarness OMX-to-Superpowers Migration Design

Date: 2026-08-13

## Goal

Make Superpowers the only active development workflow for AgentHarness while
preserving truthful historical evidence that earlier milestones used OMX and
`ralplan`.

This migration changes development process only. It does not change the
AgentHarness product boundary, runtime behavior, evidence schemas, package
version, or release status.

## Confirmed baseline

- AgentHarness release records and the ignored local `.omx/plans/` directory
  prove that early and middle milestones used OMX planning, architecture,
  review, and handoff workflows.
- AgentHarness source, tests, package metadata, policies, schemas, and CLI do
  not depend on OMX at runtime.
- The latest maintenance closure was completed using Superpowers.
- No AgentHarness file, Git history entry, WSL user skill directory, Windows
  user skill directory, plugin registry, global npm package, or executable on
  `PATH` identifies an installed GSD workflow.
- The current Codex App session exposes Superpowers skills. Standalone WSL and
  Windows `codex plugin list` currently report
  `superpowers@openai-curated` as not installed.
- WSL Claude reports `superpowers@claude-plugins-official` installed and
  enabled. Windows Claude requires an installation-state check before any
  mutation.

## Chosen approach

Use an explicit workflow cutover with historical preservation.

1. Add a Superpowers workflow section to repository `AGENTS.md`.
2. State that new AgentHarness work must start with
   `superpowers:using-superpowers` and follow the applicable Superpowers
   design, planning, TDD, review, and verification skills.
3. Prohibit new OMX, `ralplan`, team-runtime, or `.omx` task state for this
   repository unless the user explicitly reverses the migration.
4. Preserve existing release records and ignored `.omx` plans/logs as
   historical local evidence. Do not rewrite them to pretend Superpowers was
   used originally, and do not commit raw runtime logs.
5. Add a dated migration record and update the release index.
6. Install and enable Superpowers in standalone Codex/Claude hosts where the
   host's own plugin registry reports it missing. Do not duplicate an already
   enabled installation.
7. Treat GSD removal as an evidence-based operation: remove only exact GSD
   plugin, skill, marketplace, command, or package registrations. Substring
   matches in hashed bundles, third-party tools, session history, or unrelated
   names are not deletion targets.

## Alternatives rejected

### Documentation-only migration

Updating `AGENTS.md` without checking host plugin registration would leave
standalone CLI sessions unable to follow the documented workflow reliably.

### Delete all OMX history

Deleting plans, release references, and old logs would erase provenance and
make dated maintenance records less reproducible. Historical presence is not
an active dependency.

### Keep OMX as an automatic fallback

An automatic fallback would make the active workflow ambiguous and conflict
with the user's Superpowers-only direction. A future exception requires an
explicit user decision.

## Active workflow contract

For every new AgentHarness task:

1. Load `superpowers:using-superpowers` before other task actions.
2. Use `superpowers:brainstorming` before creative or behavior-changing work.
3. Write an approved design and then use `superpowers:writing-plans` for
   multi-step implementation.
4. Use `superpowers:test-driven-development` for behavior changes and
   `superpowers:systematic-debugging` for failures.
5. Use the appropriate execution skill, request review, and run
   `superpowers:verification-before-completion` before completion claims.
6. Use `superpowers:finishing-a-development-branch` when branch integration is
   required.

Repository-native product and security rules in `AGENTS.md` remain mandatory.
Superpowers selects the engineering process; it does not weaken AgentHarness
evidence-only or `not_executed` boundaries.

## Host installation and state handling

Each host is handled independently because Codex App, standalone Codex CLI,
WSL Claude, and Windows Claude can maintain separate registries.

- Query the host registry first.
- Install the official marketplace Superpowers plugin only when reported
  missing.
- Re-query the same registry after installation.
- Confirm that `using-superpowers`, `brainstorming`, `writing-plans`, TDD,
  review, and verification skills are discoverable.
- Do not infer installation from a cache directory alone.
- Do not remove OMX globally as part of this repository migration. The project
  policy makes it inactive for AgentHarness; global removal would affect other
  repositories and requires a separate explicit decision.

## Historical `.omx` handling

The ignored `.omx/` directory is classified as local historical provenance.

- Existing plans, context, and logs may remain locally.
- No new AgentHarness plan, task state, or handoff may be written there.
- `.omx/` remains excluded from Git.
- Raw logs must not be copied into tracked documentation.
- Historical release documents retain their existing `.omx/plans` references.

This provides a clean process cutover without falsifying the development
record.

## Documentation changes

Implementation will update:

- `AGENTS.md` with the active Superpowers workflow contract;
- `README.md` with a short contributor workflow pointer;
- `release/2026.08.13.md` with migration scope and verification truth; and
- `release/README.md` with the new record in newest-first order.

Historical release files remain unchanged unless a broken factual statement is
found during verification.

## Failure handling

- If a host plugin install fails, leave repository migration changes intact,
  report that host as incomplete, and do not claim global coverage.
- If a GSD-like match is not an exact registered component, preserve it.
- If an exact GSD installation appears, inventory its registry entry and path
  before removal, remove through the owning host's package/plugin command when
  available, then verify the path and registration are gone.
- If project tests fail after documentation-only changes, investigate before
  committing the migration record.

## Verification

The migration is complete only when all applicable checks pass:

1. AgentHarness `AGENTS.md` names Superpowers as the active workflow and
   rejects implicit OMX use.
2. Current source, tests, package metadata, and contributor entry points contain
   no active OMX invocation.
3. Historical OMX references remain clearly labeled as historical.
4. WSL and Windows Codex plugin registries report Superpowers installed and
   enabled.
5. WSL and Windows Claude plugin registries report Superpowers installed and
   enabled when those CLIs are available.
6. Exact GSD registrations and executable/package installations are absent;
   incidental substring matches are documented as non-targets.
7. Repository-native validation, smoke evaluation, loop-bus checks, full tests,
   Markdown link checks, and Git whitespace checks pass.
8. The final working tree contains only the intended migration commit(s), with
   no generated cache or build output.

## Non-goals

- Removing OMX globally from the machine.
- Rewriting historical commits or release records.
- Committing `.omx` plans or logs.
- Changing AgentHarness product behavior or package version.
- Pushing, tagging, publishing packages, deploying, or enabling runtime tool
  execution.
