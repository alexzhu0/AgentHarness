# GitHub Actions CI Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only GitHub Actions CI gate for AgentHarness policy, executable evaluations, loop fixtures, tests, and whitespace across Python 3.10–3.12.

**Architecture:** A single `CI` workflow owns a matrix `verify` job. A Python guard test parses the workflow and freezes its trigger, permission, command, and artifact contract so later edits cannot silently weaken the gate.

**Tech Stack:** GitHub Actions YAML, Python 3.10+, PyYAML, `unittest`, existing `agentharness` CLI.

## Global Constraints

- Trigger only on `pull_request` and push to `main`.
- Declare only `contents: read`; no secrets, write scopes, deployment, PR mutation, Agent Runtime, tool execution, model, or runtime authorization.
- One `verify` job on `ubuntu-latest`; Python matrix exactly 3.10, 3.11, 3.12; local editable install only.
- Every verification command uses `PYTHONDONTWRITEBYTECODE=1`, has no `continue-on-error`, and runs in this order: policy validation, JUnit eval, JSON eval, both loop checks, full unittest, Git whitespace check.
- Save `artifacts/eval-results.xml` and `artifacts/eval-results.json`; on failure upload both for 14 days and fail if either is absent.
- CI validates deterministic evidence controls only; retain `result_status: not_executed` semantics and do not modify product eval/runtime logic.

---

## File Structure

- Create `.github/workflows/ci.yml`: `CI` workflow with a matrix `verify` job.
- Create `tests/test_ci_workflow.py`: workflow security/verification contract guard.
- Modify `README.md`: CI badge, scope, trigger, Python matrix, artifacts, local equivalent, and non-runtime boundary.

### Task 1: CI workflow and contract guard

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `tests/test_ci_workflow.py`

**Interfaces:**
- Consumes: `./agentharness`, `examples/agent_policy.example.yaml`, `examples/agent_bus`, `examples/agent_bus_adapter_registry`, and the existing `eval --all --format` contract.
- Produces: workflow name `CI`, job ID `verify`, and failure artifacts under `artifacts/`.

- [ ] **Step 1: Write failing workflow guard tests**

```python
class CiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = _load_workflow(ROOT / ".github/workflows/ci.yml")

    def test_trigger_permissions_and_matrix(self):
        self.assertEqual({"pull_request", "push"}, set(self.workflow["on"]))
        self.assertEqual({"branches": ["main"]}, self.workflow["on"]["push"])
        self.assertEqual({"contents": "read"}, self.workflow["permissions"])
        job = self.workflow["jobs"]["verify"]
        self.assertEqual("ubuntu-latest", job["runs-on"])
        self.assertEqual(["3.10", "3.11", "3.12"], job["strategy"]["matrix"]["python-version"])

    def test_commands_and_artifact_contract(self):
        commands = "\n".join(_run_commands(self.workflow))
        self.assertIn("./agentharness eval --all --format junit > artifacts/eval-results.xml", commands)
        self.assertIn("./agentharness eval --all --format json > artifacts/eval-results.json", commands)
        upload = _artifact_step(self.workflow)
        self.assertEqual("${{ failure() }}", upload["if"])
        self.assertEqual("14", upload["with"]["retention-days"])
        self.assertEqual("error", upload["with"]["if-no-files-found"])
```

Implement `_load_workflow` with `yaml.BaseLoader`, not `safe_load`, so YAML key
`on` remains a string. Add assertions for job-level
`PYTHONDONTWRITEBYTECODE: "1"`, exact artifact paths, no extra permissions, no
`continue-on-error`, and all seven required commands.

- [ ] **Step 2: Run guard tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_ci_workflow.py' -v`

Expected: FAIL because `.github/workflows/ci.yml` does not exist.

- [ ] **Step 3: Implement the minimal workflow**

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    env:
      PYTHONDONTWRITEBYTECODE: "1"
```

Add `actions/checkout`, `actions/setup-python`, `python -m pip install -e .`,
then explicit steps for the seven commands. Create `artifacts/` before the two
eval commands. Add `actions/upload-artifact` with
`if: ${{ failure() }}`, name `agentharness-eval-${{ matrix.python-version }}`,
both artifact paths, `retention-days: 14`, and `if-no-files-found: error`.

Use this complete workflow body so a failing first report still permits the
second report to be written before the job fails:

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    env:
      PYTHONDONTWRITEBYTECODE: "1"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install package
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e .
      - name: Validate policy
        run: ./agentharness validate examples/agent_policy.example.yaml
      - name: Generate evaluation reports
        run: |
          mkdir -p artifacts
          junit_status=0
          ./agentharness eval --all --format junit > artifacts/eval-results.xml || junit_status=$?
          json_status=0
          ./agentharness eval --all --format json > artifacts/eval-results.json || json_status=$?
          test "$junit_status" -eq 0 -a "$json_status" -eq 0
      - name: Check loop bus fixture
        run: ./agentharness loop check examples/agent_bus
      - name: Check adapter-registry loop fixture
        run: ./agentharness loop check examples/agent_bus_adapter_registry
      - name: Run unit tests
        run: python -m unittest discover -s tests -q
      - name: Check whitespace
        run: git diff --check
      - name: Upload evaluation reports on failure
        if: ${{ failure() }}
        uses: actions/upload-artifact@v4
        with:
          name: agentharness-eval-${{ matrix.python-version }}
          path: |
            artifacts/eval-results.xml
            artifacts/eval-results.json
          retention-days: 14
          if-no-files-found: error
```

- [ ] **Step 4: Expand tests to freeze exact command order**

```python
def test_required_commands_have_exact_order_and_no_suppression(self):
    self.assertEqual(
        [
            "./agentharness validate examples/agent_policy.example.yaml",
            "./agentharness eval --all --format junit > artifacts/eval-results.xml",
            "./agentharness eval --all --format json > artifacts/eval-results.json",
            "./agentharness loop check examples/agent_bus",
            "./agentharness loop check examples/agent_bus_adapter_registry",
            "python -m unittest discover -s tests -q",
            "git diff --check",
        ],
        _verification_commands(_run_commands(self.workflow)),
    )
    self.assertNotIn("continue-on-error", _serialized_verify_job(self.workflow))
```

The helper may remove only `mkdir -p artifacts` before comparison. It must not
accept commands solely by substring.

- [ ] **Step 5: Run guard tests GREEN and compose the workflow YAML**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_ci_workflow.py' -v
python3 -c "from pathlib import Path; import yaml; yaml.compose(Path('.github/workflows/ci.yml').read_text(encoding='utf-8'))"
```

Expected: all guard tests pass and YAML composes.

- [ ] **Step 6: Run repository-required verification**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 ./agentharness validate examples/agent_policy.example.yaml
PYTHONDONTWRITEBYTECODE=1 ./agentharness eval --cases PI-001,PD-001,SEC-001
PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check examples/agent_bus
PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check examples/agent_bus_adapter_registry
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
git diff --check
```

Expected: all commands pass and discovery includes the workflow guard.

- [ ] **Step 7: Commit workflow and guard**

```bash
git add .github/workflows/ci.yml tests/test_ci_workflow.py
git diff --cached --check
git commit -m "ci: add deterministic verification gate"
```

### Task 2: CI documentation and final local proof

**Files:**
- Modify: `README.md`
- Modify: `tests/test_ci_workflow.py`

**Interfaces:**
- Consumes: Task 1's `CI` workflow.
- Produces: contributor-facing CI documentation which describes the exact workflow behavior.

- [ ] **Step 1: Write failing README alignment test**

```python
def test_readme_documents_ci_contract(self):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for value in (
        "actions/workflows/ci.yml",
        "Python 3.10",
        "Python 3.11",
        "Python 3.12",
        "./agentharness eval --all --format junit",
        "./agentharness eval --all --format json",
        "CI is not runtime authorization",
    ):
        self.assertIn(value, readme)
```

- [ ] **Step 2: Run README test and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_ci_workflow.py' -v`

Expected: FAIL because the README has no CI section.

- [ ] **Step 3: Document the CI gate exactly**

Add `## Continuous Integration` after `## Declarative Safety Evaluations`, with:

```markdown
[![CI](https://github.com/alexzhu0/AgentHarness/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/alexzhu0/AgentHarness/actions/workflows/ci.yml)
```

State the PR/push-to-main triggers, Python 3.10/3.11/3.12 matrix, policy/all-eval/
loop/test scope, failure-only 14-day JUnit/JSON artifacts, two all-case local
eval commands, and this exact boundary sentence: `CI is not runtime authorization
and does not execute Agent Runtime tools.`

- [ ] **Step 4: Run full guard and repository verification GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_ci_workflow.py' -v
PYTHONDONTWRITEBYTECODE=1 ./agentharness validate examples/agent_policy.example.yaml
PYTHONDONTWRITEBYTECODE=1 ./agentharness eval --cases PI-001,PD-001,SEC-001
PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check examples/agent_bus
PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check examples/agent_bus_adapter_registry
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
git diff --check
```

Expected: workflow/README guards, legacy behavior, both fixtures, full suite, and whitespace check pass.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md tests/test_ci_workflow.py
git diff --cached --check
git commit -m "docs: explain CI verification gate"
```

- [ ] **Step 6: Request review and final verification**

Invoke `superpowers:requesting-code-review` for the complete CI range. Resolve
Critical/Important findings with `superpowers:receiving-code-review`, then invoke
`superpowers:verification-before-completion` and rerun Task 2 Step 4 before any
completion claim.
