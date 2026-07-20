# AgentHarness/Pi Shadow Milestone Packaging Handoff

## Decision and boundary

T061 is an explicit **no-commit handoff**. It records the dirty milestone for
review and possible later path-scoped staging. It does not stage, commit, tag,
push, publish, release, reset, clean, or stash anything. It grants no commit
approval.

AgentHarness is evidence-only. Pi or another external runtime owns runtime
authorization and execution. `allow_candidate` never permits execution. The
current bridge is block-only, every result remains
`result_status: not_executed`, and no real tool execution occurs.

T060 remains **NO-GO for real execution** and **NOT IMPLEMENTED**. Its ADR is a
readiness contract for future review, not permission to power on any runtime
allow path.

## Accepted milestone summary

- **T056:** evidence-integrity review was accepted. Fail-closed digest and path
  handling, host-path redaction, tests, and package-artifact checks are clean.
  Earlier T056-pending wording is stale and has been corrected.
- **T057:** the observation/evidence v1 request, evaluator, response, and exact
  binding verification are deterministic evidence contracts. They do not
  authenticate or authorize runtime execution.
- **T058:** Pi live `beforeToolCall` wiring uses the v1 evidence evaluator and
  verifies current-call correlation. The production bridge remains block-only,
  including for a correlated `allow_candidate`.
- **T059:** fake Win9-named tools exercise live-shadow transport, correlation,
  rejection, redaction, and fail-closed behavior. Execution sentinels remain at
  zero; this is not evidence of real Win9 tool execution.
- **T060:** the runtime-authorization readiness ADR identifies runtime-owned
  trust, activation, permit, sandbox, revocation, audit, and rollback gates.
  None is implemented by AgentHarness, and the decision remains NO-GO.

## Base anchors, not release pins

The repository HEADs below do not contain the dirty T056-T060 or T056-T059
milestone changes. They are review anchors only, not reproducible release pins.

### AgentHarness

- HEAD: `d9c1c8e0a6a171dada07d42979802cba982915ce`
- merge-base with `origin/main`:
  `8a657d2609eb58dd32dd18e702b407cab8c1d4bf`
- ahead of `origin/main`: 9

### Pi

- HEAD: `d658f55a7ccefdf4b59f6e3e89c7268611141c48`
- merge-base with `origin/main`:
  `0ab2aa86af862ca1cf4b0b86fcbee14d00e1441f`
- ahead/behind `origin/main`: 30 ahead, 402 behind

## Exact AgentHarness T056-T060 dirty manifest

This manifest reflects `git status --short` before T061 documentation edits.
Generated `src/agentharness/__pycache__/` content is excluded.

- `README.md`
- `docs/21-pi-controlled-read-only-poc.md`
- `docs/22-pi-integration-readiness-pause-review.md`
- `docs/24-pi-observation-evidence-contract-v1.md`
- `docs/25-pi-runtime-authorization-readiness-adr.md`
- `release/2026.07.07.md`
- `schemas/ah_args_c14n_1.vectors.json`
- `schemas/pi_tool_call_evidence_response_batch.v1.schema.json`
- `schemas/pi_tool_call_observation_batch.v1.schema.json`
- `src/agentharness/cli.py`
- `src/agentharness/loop_bus.py`
- `src/agentharness/pi_evidence_contract_v1.py`
- `src/agentharness/pi_tool_call_mapping.py`
- `tests/test_handoff_exporter.py`
- `tests/test_handoff_manifest.py`
- `tests/test_loop_bus.py`
- `tests/test_pi_evidence_contract_cli_v1.py`
- `tests/test_pi_evidence_contract_v1.py`
- `tests/test_pi_tool_call_mapping.py`

T061 documentation ownership includes the T061 hunks in `README.md` and
`docs/00-asset-map.md`, this document, and `release/2026.07.13.md`. Other
pre-existing content in `README.md` and `docs/00-asset-map.md` remains outside
T061 ownership.

## Exact Pi T056-T059 dirty manifest

This manifest reflects Pi `git status --short`. Generated caches and the
unrelated `docs/others/` tree are excluded.

- `packages/coding-agent/package.json`
- `packages/coding-agent/scripts/verify-agentharness-artifact.mjs`
- `packages/coding-agent/src/core/agentharness-contract-v1.ts`
- `packages/coding-agent/src/core/agentharness-dry-run-gate.ts`
- `packages/coding-agent/test/agentharness-contract-v1.test.ts`
- `packages/coding-agent/test/agentharness-dry-run-e2e.test.ts`
- `packages/coding-agent/test/agentharness-dry-run-gate.test.ts`
- `packages/coding-agent/test/agentharness-live-v1-test-helper.ts`
- `packages/coding-agent/test/agentharness-read-only-poc-e2e.test.ts`
- `packages/coding-agent/test/agentharness-win9-dry-run-bridge.test.ts`
- `packages/coding-agent/test/fixtures/agentharness-contract-v1/`
- `scripts/publish.mjs`

The fixture directory contains exactly these dirty paths:

- `packages/coding-agent/test/fixtures/agentharness-contract-v1/`
  `ah_args_c14n_1.vectors.json`
- `packages/coding-agent/test/fixtures/agentharness-contract-v1/`
  `pi_tool_call_evidence_response_batch.v1.schema.json`
- `packages/coding-agent/test/fixtures/agentharness-contract-v1/`
  `pi_tool_call_observation_batch.v1.schema.json`

## Acceptance checkpoint note

G004 and G005 acceptance checks were clean. Their OMX checkpoint writes failed
only because `get_goal` returned `usageLimited` or unknown state. The
implementation and design checks did not fail. This is checkpoint telemetry
degradation, not milestone evidence failure.

## Staging and rollback boundaries

- No staging or commit action is approved by this handoff.
- Never use `git add .`, an implicit pathspec, or a repository-wide staging
  command for this milestone.
- If a later owner grants commit approval, stage only an independently reviewed,
  explicit path list from the manifests above.
- Keep AgentHarness and Pi as separate review and staging units.
- Exclude generated caches, Pi `docs/others/`, and every unrelated dirty path.
- Do not use `reset`, `clean`, or `stash` to prepare this milestone.
- Preserve pre-existing `README.md` and `docs/00-asset-map.md` content. A T061
  rollback must reverse only T061 hunks; a whole-file restore would discard
  earlier accepted work.
- Remove either new T061 file only after explicit rollback approval. Do not
  broaden rollback to source, tests, schemas, fixtures, dependencies, or locks.

## T061 verification

All evidence below is from the final fresh verification pass.

### AgentHarness evidence

- Policy validation: **PASS**.
- Evaluation: **3/3**.
- Loop checks for `agent_bus` and `adapter_registry`: **PASS**.
- Targeted tests: **144/144** in **17.472s**.
- Full tests: **381/381** in **34.265s**.
- Diff check: **PASS**.
- External Pi import, path, and process findings: **0**.
- Handoff package: **6**; manifest: **4**; mapping: **20**.
- Evidence response covered **7** `result_status` values; bad results: **0**.
- Instruction-file diff: none.

### Pi evidence

- The focused five AgentHarness files passed **211** tests with **0 skipped**
  and **0 failed** under `PI_AGENTHARNESS_E2E=1` using the real AgentHarness
  evaluator. Cleanup removed **51** duplicate legacy helper tests after their
  unique production-contract assertions were migrated.
- All tool fake sentinels and execution counters remained **0**.
- One focused synthetic `allow_candidate` block probe passed.
- Prepack: **PASS**.
- Root `npm run check`: **PASS** over **668 files**.
- Diff check: **PASS**.
- Status and hashes were unchanged; `docs/others/` was untouched.

### Target-package evidence and observation

The requested command below resolved the repository root package under the
current npm behavior and is not target-package evidence:

```bash
npm --prefix packages/coding-agent pack
```

It reported **1,272 files**, **6.1 MB packed**, and **18.2 MB unpacked**.

The correct target-package command was:

```bash
cd packages/coding-agent && npm pack --dry-run --ignore-scripts
```

It verified `@earendil-works/pi-coding-agent@0.79.1` with **874 files**,
**5,053,559 bytes packed**, and **13,435,171 bytes unpacked**. No tarball was
created.

The target package includes compiled `agentharness-contract-v1`,
`agentharness-dry-run-gate`, and `agent-session` JS, `.d.ts`, and map artifacts.
Package inspection found **0** stale fixture paths, **0** legacy runtime
strings, and **0** `block:false` branches.

The current tarball has **0** standalone AgentHarness schema JSON files. Schema
IDs and validators are compiled into contract artifacts. This is an explicit
packaging observation for final review, not proof of standalone schema assets.

### Cleanup and scoped documentation checks

The initial `ai-slop-cleaner` review found four behavior-neutral smells. The
repair removed the duplicate test-only implementation after migrating its
unique assertions, removed dead fields, simplified the one-item verifier loop,
and renamed the runner. The post-repair cleaner result was **PASS**. Grounded,
fail-closed fallbacks were preserved, and generated caches were absent.

Excluded, pre-existing Pi `docs/others/` content remained checksum-unchanged
and is not T061 scope.

The final scoped checks cover T061-added/changed hunks in `README.md` and
`docs/00-asset-map.md`, plus this document and
`release/2026.07.13.md`: diff checks, local-link resolution, line lengths, and
stale-term searches. All scoped documentation remains at or below 80
characters per line.

## Stop line

This handoff stops at documentation and package review. The milestone remains
dirty and uncommitted. No runtime power-on, real execution, staging, commit,
push, publish, or release is authorized.
