# GitHub Actions CI Design

Date: 2026-08-17

## Status

Approved design for AgentHarness's first real continuous-integration gate.

## Goal

Run AgentHarness's deterministic policy, evaluation, loop-bus, and Python test
verification automatically on pull requests and pushes to `main`, retaining
machine-readable evaluation evidence whenever CI fails.

## Scope

This increment adds one GitHub Actions workflow, tests guarding its essential
properties, and concise README documentation. It does not publish packages,
deploy anything, call a model or Agent Runtime, execute an external tool,
change runtime authorization, or alter the meaning of `allow_candidate` or
`result_status: not_executed`.

## Trigger and permissions

The workflow runs on:

- every `pull_request`; and
- every push to `main`.

It has only `contents: read` permission. It does not request write scopes,
secrets, deployment credentials, GitHub API mutation rights, or pull-request
write access.

## Workflow structure

Create `.github/workflows/ci.yml` with one job named `verify`:

```text
pull_request / push(main)
          |
          v
Python 3.10, 3.11, 3.12 matrix
          |
          v
checkout + editable package install
          |
          v
policy validation
          |
          v
declarative eval -> JUnit and JSON artifacts
          |
          v
loop-bus checks
          |
          v
full unittest + Git whitespace check
          |
          v
on failure, upload evaluation artifacts for 14 days
```

The job runs on `ubuntu-latest`, checks out the exact triggering revision, and
uses `actions/setup-python` for a matrix of Python 3.10, 3.11, and 3.12.
Dependencies install through `python -m pip install -e .`; the workflow does
not publish the package or use a package-registry token.

Every command sets `PYTHONDONTWRITEBYTECODE=1`.

## Verification commands

The CI job executes, in order:

```bash
./agentharness validate examples/agent_policy.example.yaml
./agentharness eval --all --format junit > artifacts/eval-results.xml
./agentharness eval --all --format json > artifacts/eval-results.json
./agentharness loop check examples/agent_bus
./agentharness loop check examples/agent_bus_adapter_registry
python -m unittest discover -s tests -q
git diff --check
```

The declared commands intentionally mirror the repository's required local
checks, while upgrading the evaluation run to all currently executable cases
and saving JUnit/JSON output. Command failure fails the job. The workflow must
not suppress failures with `continue-on-error`.

## Evaluation artifact behavior

The JUnit and JSON commands create these paths before later checks run:

- `artifacts/eval-results.xml`
- `artifacts/eval-results.json`

An `actions/upload-artifact` step runs only when the job has failed, uploads
both files under a stable artifact name, retains them for 14 days, and treats
missing paths as an error. This preserves partial output from a failing eval
without making missing evidence appear successful.

The artifacts contain only the bounded machine-readable reports already
produced by AgentHarness. They do not contain raw tool arguments, credentials,
absolute host paths, exception text, or runtime execution evidence.

## Workflow guard tests

Add a focused Python test module that parses the workflow YAML and verifies:

- only the approved `pull_request` and push-to-`main` triggers exist;
- workflow and job permissions stay read-only;
- the Python matrix is exactly 3.10, 3.11, and 3.12;
- the `verify` job runs the required commands without `continue-on-error`;
- JUnit and JSON paths match this design;
- artifact upload is failure-only, has 14-day retention, and errors when files
  are missing.

The guard test prevents later workflow edits from silently weakening the
security gate.

## Documentation

README will add a compact CI section with:

- a GitHub Actions badge for the `CI` workflow on `main`;
- the PR/push trigger policy;
- the three Python versions;
- the all-case JUnit/JSON evaluation evidence behavior; and
- the equivalent local verification commands.

The documentation will state that CI validates deterministic evidence controls
only. It is not a real Agent Runtime integration and does not authorize tool
execution.

## Failure model

Any failed command fails the matrix entry. Failure artifacts support diagnosis
but never change the status to passing. A malformed workflow caught by the
guard tests is a repository test failure. No workflow step retries a command,
contacts an external runtime, or attempts autonomous repair.

## Non-goals and next milestone

This CI gate is the prerequisite for, but is distinct from, a future real Agent
Runtime shadow integration. The follow-on milestone may capture runtime
observations and compare them with AgentHarness evidence while retaining
`result_status: not_executed`; it needs a separate design, security review, and
approval before implementation.
