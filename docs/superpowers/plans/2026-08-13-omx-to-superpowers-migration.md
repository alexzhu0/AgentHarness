# AgentHarness WSL OMX-to-Superpowers Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Superpowers the only active AgentHarness development workflow in WSL, remove active WSL OMX surfaces, preserve historical OMX evidence, and verify that no exact GSD installation exists.

**Architecture:** Install Superpowers before removing OMX so the replacement workflow remains available throughout the cutover. Use the OMX-owned uninstaller for ownership-aware global cleanup, remove the npm launcher only after validating preserved Codex state, and retire only active repository-local `.omx` runtime files while retaining plans, context, and logs as historical provenance.

**Tech Stack:** Codex CLI plugin registry, npm global packages, Bash, Git, Markdown, Python `unittest`, AgentHarness CLI.

## Global Constraints

- Scope is WSL Codex and the AgentHarness repository only; do not modify Windows Codex, Windows Claude, or WSL Claude.
- Superpowers is the sole active workflow for new AgentHarness development.
- Preserve historical OMX release records and ignored `.omx/plans`, `.omx/context`, and `.omx/logs` content.
- Do not change AgentHarness runtime behavior, package version, evidence schemas, or release status.
- Remove only exact GSD registrations or installations; incidental substring matches are not deletion targets.
- Preserve unrelated user configuration and do not record credentials or raw configuration values.
- Do not push, tag, publish, deploy, or enable runtime tool execution.

---

### Task 1: Lock the WSL-only migration design and baseline

**Files:**
- Modify: `docs/superpowers/specs/2026-08-13-omx-to-superpowers-migration-design.md`
- Create: `docs/superpowers/plans/2026-08-13-omx-to-superpowers-migration.md`

**Interfaces:**
- Consumes: current WSL `codex`, `omx`, npm, Git, and repository state.
- Produces: a reviewed WSL-only design and this executable plan.

- [ ] **Step 1: Confirm that Windows and Claude are outside the design**

Run:

```bash
rg -n "Windows|Claude" \
  docs/superpowers/specs/2026-08-13-omx-to-superpowers-migration-design.md
```

Expected: matches occur only in the explicit non-goal saying those hosts are not changed.

- [ ] **Step 2: Validate plan and design formatting**

Run:

```bash
rg -n "T[B]D|T[O]DO|implement l[a]ter|fill in d[e]tails|Similar to T[a]sk" \
  docs/superpowers/specs/2026-08-13-omx-to-superpowers-migration-design.md \
  docs/superpowers/plans/2026-08-13-omx-to-superpowers-migration.md
git diff --check
```

Expected: `rg` returns no matches and `git diff --check` exits zero.

- [ ] **Step 3: Commit the WSL-only design and plan**

```bash
git add \
  docs/superpowers/specs/2026-08-13-omx-to-superpowers-migration-design.md \
  docs/superpowers/plans/2026-08-13-omx-to-superpowers-migration.md
git diff --cached --check
git diff --cached --name-only
git commit -m "Plan WSL Superpowers workflow migration"
```

Expected: the staged list contains exactly the two Superpowers documents.

### Task 2: Install and verify Superpowers in WSL Codex

**Files:**
- Modify outside repository: WSL Codex plugin registry under `/home/alex/.codex/`

**Interfaces:**
- Consumes: configured `openai-curated` Codex marketplace.
- Produces: enabled `superpowers@openai-curated` plugin and discoverable core skills.

- [ ] **Step 1: Capture the pre-install registry result**

Run: `codex plugin list`

Expected: the baseline reports either not installed or installed/enabled.

- [ ] **Step 2: Install Superpowers only if missing**

Run when missing:

```bash
codex plugin add superpowers@openai-curated --json
```

Expected: JSON reports a successful install for `superpowers` from `openai-curated`.

- [ ] **Step 3: Verify registry and skill discovery**

Run:

```bash
codex plugin list
test -f /home/alex/.codex/plugins/cache/openai-curated/superpowers/11c74d6b/skills/using-superpowers/SKILL.md
test -f /home/alex/.codex/plugins/cache/openai-curated/superpowers/11c74d6b/skills/brainstorming/SKILL.md
test -f /home/alex/.codex/plugins/cache/openai-curated/superpowers/11c74d6b/skills/writing-plans/SKILL.md
test -f /home/alex/.codex/plugins/cache/openai-curated/superpowers/11c74d6b/skills/test-driven-development/SKILL.md
test -f /home/alex/.codex/plugins/cache/openai-curated/superpowers/11c74d6b/skills/requesting-code-review/SKILL.md
test -f /home/alex/.codex/plugins/cache/openai-curated/superpowers/11c74d6b/skills/verification-before-completion/SKILL.md
```

Expected: the registry reports installed/enabled and every `test` exits zero.

### Task 3: Remove active WSL OMX global surfaces safely

**Files:**
- Modify outside repository: OMX-managed entries under `/home/alex/.codex/`
- Remove outside repository: global npm package `oh-my-codex`
- Create temporarily: `/tmp/agentharness-omx-migration-20260813/`

**Interfaces:**
- Consumes: OMX ownership metadata, global Codex configuration, and the npm global package registry.
- Produces: WSL Codex configuration without active OMX hooks/overlays and no `omx` executable.

- [ ] **Step 1: Record a metadata-only pre-removal snapshot**

Run:

```bash
mkdir -p /tmp/agentharness-omx-migration-20260813
find /home/alex/.codex -maxdepth 2 -type f \
  \( -name 'AGENTS.md' -o -name 'config.toml' -o -name 'hooks.json' \) \
  -print -exec sha256sum {} \;
npm ls -g --depth=0 oh-my-codex
command -v omx
```

Expected: output records paths and hashes only; npm and `command -v` confirm the pre-removal installation.

- [ ] **Step 2: Preview ownership-aware cleanup**

Run: `omx uninstall --dry-run --verbose`

Expected: the preview targets OMX-owned Codex files and configuration entries, does not target the `openai-curated` Superpowers plugin, and does not target unrelated user content.

- [ ] **Step 3: Run the OMX-owned uninstaller**

Run: `omx uninstall --verbose`

Expected: it reports successful removal of OMX-managed Codex surfaces without deleting foreign configuration.

- [ ] **Step 4: Restore and verify Superpowers before removing the launcher**

Run:

```bash
codex plugin list
codex plugin add superpowers@openai-curated --json
codex plugin list
test -f /home/alex/.codex/plugins/cache/openai-curated/superpowers/11c74d6b/skills/using-superpowers/SKILL.md
rg -n "OMX|oh-my-codex|omx" \
  /home/alex/.codex/AGENTS.md \
  /home/alex/.codex/config.toml \
  /home/alex/.codex/hooks.json 2>/dev/null
```

Expected: OMX cleanup may remove Codex's plugin registration while leaving the
plugin cache intact. Re-adding the official plugin after cleanup restores the
installed/enabled registration; the scan has no active managed OMX references,
and missing removed files are acceptable.

- [ ] **Step 5: Remove and verify the global npm package**

Run:

```bash
npm uninstall -g oh-my-codex
npm ls -g --depth=0 oh-my-codex
command -v omx
```

Expected: uninstall succeeds; the final two commands return non-zero because the package and executable are absent.

### Task 4: Retire AgentHarness OMX state and publish the workflow contract

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Move outside repository: `.omx/state`, `.omx/hud-config.json`, `.omx/setup-scope.json`, `.omx/metrics.json`
- Preserve: `.omx/plans`, `.omx/context`, `.omx/logs`

**Interfaces:**
- Consumes: the approved migration design and installed WSL Superpowers workflow.
- Produces: repository-local Superpowers-only guidance with inert historical OMX evidence.

- [ ] **Step 1: Add the Superpowers workflow contract to `AGENTS.md`**

Add this section:

```markdown
## Development workflow

- Superpowers is the only active development workflow for new AgentHarness work.
- Load `superpowers:using-superpowers` before task actions and apply the relevant Superpowers skills.
- Use brainstorming and an approved design before creative or behavior-changing work; use writing-plans for multi-step implementation.
- Use test-driven-development for behavior changes, systematic-debugging for failures, requesting-code-review before integration, and verification-before-completion before completion claims.
- Do not start OMX, `ralplan`, team-runtime, or new `.omx` task state for this repository unless the user explicitly reverses this migration.
- Existing `.omx` plans, context, logs, and historical release references are provenance only and do not define the active workflow.
```

- [ ] **Step 2: Add a concise contributor pointer to `README.md`**

Add immediately after the repository-guidance entry:

```markdown
Development workflow: new work uses Superpowers only. See
[`AGENTS.md`](AGENTS.md) and the
[WSL migration design](docs/superpowers/specs/2026-08-13-omx-to-superpowers-migration-design.md).
Historical OMX references document earlier work and are not active workflow instructions.
```

- [ ] **Step 3: Move active `.omx` runtime files to the retirement directory**

Resolve exact targets:

```bash
find .omx -maxdepth 1 \
  \( -name state -o -name hud-config.json -o -name setup-scope.json -o -name metrics.json \) \
  -print
mkdir -p /tmp/agentharness-omx-migration-20260813/repository-runtime
```

Move only printed targets into `/tmp/agentharness-omx-migration-20260813/repository-runtime/`. Do not move `.omx/plans`, `.omx/context`, or `.omx/logs`.

- [ ] **Step 4: Verify the repository-local cutover**

Run:

```bash
test -d .omx/plans
test -d .omx/context
test -d .omx/logs
test ! -e .omx/state
test ! -e .omx/hud-config.json
test ! -e .omx/setup-scope.json
test ! -e .omx/metrics.json
rg -n "Superpowers is the only active development workflow" AGENTS.md
rg -n "Historical OMX references" README.md
```

Expected: historical directories exist, active runtime targets do not, and both workflow statements match.

### Task 5: Record the migration and verify no exact GSD installation

**Files:**
- Create: `release/2026.08.13.md`
- Modify: `release/README.md`

**Interfaces:**
- Consumes: verified WSL global and repository-local migration results.
- Produces: a dated, non-release migration record with reproducible evidence.

- [ ] **Step 1: Run exact-name GSD checks**

Run:

```bash
find /home/alex/.codex -type f -o -type d | awk -F/ '{print $NF}' | \
  rg -i '^(gsd|get-shit-done)([-_.].*)?$'
npm ls -g --depth=0 | rg -i '(^|[[:space:]])(gsd|get-shit-done)(@|[[:space:]]|$)'
command -v gsd
git log --all --oneline --grep='(^|[[:space:]])(GSD|get-shit-done)([[:space:]]|$)'
```

Expected: no exact installed skill, plugin, package, executable, or matching AgentHarness commit is reported. Non-zero no-match exits are success evidence.

- [ ] **Step 2: Write the dated migration record**

Create `release/2026.08.13.md` containing:

- WSL-only scope and explicit Windows/Claude non-scope;
- installed Superpowers plugin identity;
- removed OMX surfaces and npm package;
- preserved historical `.omx` content and retired state location;
- exact GSD no-op result;
- repository verification commands and fresh pass counts/timings;
- a statement that the record is not a tag, publication, deployment, runtime authorization, or production certification.

- [ ] **Step 3: Index the record newest first**

Add this first list item to `release/README.md`:

```markdown
- [2026-08-13 — WSL Superpowers workflow migration](2026.08.13.md)
```

### Task 6: Run final verification and commit the completed migration

**Files:**
- Verify: `AGENTS.md`, `README.md`, `release/2026.08.13.md`, `release/README.md`
- Verify: all tracked repository files and the WSL plugin/package state

**Interfaces:**
- Consumes: all migration deliverables.
- Produces: fresh completion evidence and a clean, reviewable Git commit.

- [ ] **Step 1: Run repository-native functional verification**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 ./agentharness validate examples/agent_policy.example.yaml
PYTHONDONTWRITEBYTECODE=1 ./agentharness eval --cases PI-001,PD-001,SEC-001
PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check examples/agent_bus
PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check examples/agent_bus_adapter_registry
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Expected: validation passes, smoke evaluation is `3/3`, both loop checks pass, and the full test suite reports all tests passing.

- [ ] **Step 2: Run documentation and workspace checks**

Run the repository's existing Markdown-link checker if one is present; otherwise validate all tracked relative Markdown links with a read-only script. Then run:

```bash
git diff --check
git status --short
find . -maxdepth 3 \
  \( -name '__pycache__' -o -name '.pytest_cache' -o -name '*.egg-info' -o -name '*.whl' \) \
  -print
```

Expected: links resolve, whitespace check passes, status contains only intended migration documents, and no generated cache/build artifacts are present.

- [ ] **Step 3: Re-verify global completion claims**

Run:

```bash
codex plugin list
test -f /home/alex/.codex/plugins/cache/openai-curated/superpowers/11c74d6b/skills/using-superpowers/SKILL.md
npm ls -g --depth=0 oh-my-codex
command -v omx
command -v gsd
```

Expected: Superpowers is installed/enabled; the last three absence checks return non-zero.

- [ ] **Step 4: Commit only intended repository files**

```bash
git add AGENTS.md README.md \
  docs/superpowers/plans/2026-08-13-omx-to-superpowers-migration.md \
  release/2026.08.13.md release/README.md
git diff --cached --check
git diff --cached --name-only
git commit -m "Migrate AgentHarness workflow to Superpowers"
git status --short --branch
```

Expected: the staged list contains exactly five files, the commit succeeds, and the final working tree is clean.
