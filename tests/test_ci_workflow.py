"""Contract guard for the read-only GitHub Actions verification workflow."""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/ci.yml"
SUBMITTED_WHITESPACE_SCRIPT = """if [ \"$EVENT_NAME\" = \"pull_request\" ]; then
  git diff --check \"$PR_BASE...$PR_HEAD\"
elif [ \"$EVENT_BEFORE\" = \"0000000000000000000000000000000000000000\" ]; then
  git diff --check \"$(git hash-object -t tree /dev/null)\" \"$EVENT_AFTER\"
else
  git diff --check \"$EVENT_BEFORE..$EVENT_AFTER\"
fi
"""
LOCAL_CI_SEQUENCE = """python -m pip install -e .
PYTHONDONTWRITEBYTECODE=1 ./agentharness validate examples/agent_policy.example.yaml
mkdir -p artifacts
PYTHONDONTWRITEBYTECODE=1 ./agentharness eval --all --format junit > artifacts/eval-results.xml
PYTHONDONTWRITEBYTECODE=1 ./agentharness eval --all --format json > artifacts/eval-results.json
PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check examples/agent_bus
PYTHONDONTWRITEBYTECODE=1 ./agentharness loop check examples/agent_bus_adapter_registry
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -q
git fetch origin main
git diff --check origin/main...HEAD
"""


def _load_workflow(path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _serialized_values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _serialized_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _serialized_values(item)
    else:
        yield str(value)


class CiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = _load_workflow(WORKFLOW_PATH)
        self.job = self.workflow["jobs"]["verify"]
        self.steps = self.job["steps"]

    def test_workflow_has_only_the_closed_ci_structure(self):
        self.assertEqual(["ci.yml"], sorted(path.name for path in WORKFLOW_PATH.parent.iterdir()))
        self.assertEqual({"name", "on", "permissions", "jobs"}, set(self.workflow))
        self.assertEqual("CI", self.workflow["name"])
        self.assertEqual(
            {"pull_request": "", "push": {"branches": ["main"]}}, self.workflow["on"]
        )
        self.assertEqual({"contents": "read"}, self.workflow["permissions"])
        self.assertEqual({"verify"}, set(self.workflow["jobs"]))
        self.assertEqual({"runs-on", "strategy", "env", "steps"}, set(self.job))
        self.assertEqual("ubuntu-latest", self.job["runs-on"])
        self.assertEqual(
            {
                "fail-fast": "false",
                "matrix": {"python-version": ["3.10", "3.11", "3.12"]},
            },
            self.job["strategy"],
        )
        self.assertEqual({"PYTHONDONTWRITEBYTECODE": "1"}, self.job["env"])

    def test_steps_actions_and_security_surface_are_closed(self):
        self.assertEqual(
            [
                "actions/checkout@v4",
                "actions/setup-python@v5",
                "Install package",
                "Validate policy",
                "Generate evaluation reports",
                "Check loop bus fixture",
                "Check adapter-registry loop fixture",
                "Run unit tests",
                "Check submitted whitespace",
                "Check evaluation reports exist on failure",
                "actions/upload-artifact@v4",
            ],
            [step.get("uses", step.get("name")) for step in self.steps],
        )
        self.assertEqual(
            ["actions/checkout@v4", "actions/setup-python@v5", "actions/upload-artifact@v4"],
            [step["uses"] for step in self.steps if "uses" in step],
        )
        self.assertEqual({"uses", "with"}, set(self.steps[0]))
        self.assertEqual({"fetch-depth": "0"}, self.steps[0]["with"])
        self.assertEqual({"uses", "with"}, set(self.steps[1]))
        self.assertEqual(
            {"python-version": "${{ matrix.python-version }}"}, self.steps[1]["with"]
        )
        for step in self.steps[2:8]:
            self.assertEqual({"name", "run"}, set(step))
        self.assertEqual({"name", "env", "run"}, set(self.steps[8]))
        self.assertEqual({"name", "if", "run"}, set(self.steps[9]))
        self.assertEqual("${{ failure() }}", self.steps[9]["if"])
        self.assertEqual(
            "test -f artifacts/eval-results.xml\ntest -f artifacts/eval-results.json\n",
            self.steps[9].get("run"),
        )
        self.assertEqual({"name", "if", "uses", "with"}, set(self.steps[-1]))
        self.assertEqual("${{ failure() }}", self.steps[-1]["if"])
        self.assertEqual(
            {
                "name": "agentharness-eval-${{ matrix.python-version }}",
                "path": "artifacts/eval-results.xml\nartifacts/eval-results.json\n",
                "retention-days": "14",
                "if-no-files-found": "error",
            },
            self.steps[-1]["with"],
        )
        forbidden = {"environment", "services", "container", "permissions", "continue-on-error"}
        self.assertFalse(forbidden.intersection(self.job))
        for step in self.steps:
            self.assertFalse(forbidden.intersection(step))
        self.assertFalse(any("secrets." in value for value in _serialized_values(self.workflow)))

    def test_verification_commands_and_whitespace_ranges_are_exact(self):
        self.assertEqual(
            "python -m pip install --upgrade pip\npython -m pip install -e .\n",
            self.steps[2]["run"],
        )
        self.assertEqual(
            "./agentharness validate examples/agent_policy.example.yaml",
            self.steps[3]["run"],
        )
        self.assertEqual(
            """mkdir -p artifacts
junit_status=0
./agentharness eval --all --format junit > artifacts/eval-results.xml || junit_status=$?
json_status=0
./agentharness eval --all --format json > artifacts/eval-results.json || json_status=$?
test \"$junit_status\" -eq 0 -a \"$json_status\" -eq 0
""",
            self.steps[4]["run"],
        )
        self.assertEqual("./agentharness loop check examples/agent_bus", self.steps[5]["run"])
        self.assertEqual(
            "./agentharness loop check examples/agent_bus_adapter_registry", self.steps[6]["run"]
        )
        self.assertEqual("python -m unittest discover -s tests -q", self.steps[7]["run"])
        self.assertEqual(
            {
                "EVENT_NAME": "${{ github.event_name }}",
                "EVENT_BEFORE": "${{ github.event.before }}",
                "EVENT_AFTER": "${{ github.sha }}",
                "PR_BASE": "${{ github.event.pull_request.base.sha }}",
                "PR_HEAD": "${{ github.event.pull_request.head.sha }}",
            },
            self.steps[8].get("env"),
        )
        self.assertEqual(SUBMITTED_WHITESPACE_SCRIPT, self.steps[8]["run"])
        self.assertEqual(
            "test -f artifacts/eval-results.xml\ntest -f artifacts/eval-results.json\n",
            self.steps[9].get("run"),
        )

    def test_readme_documents_the_copy_paste_ci_sequence(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        ci_section = readme.split("## Continuous Integration", 1)[1].split("\n## ", 1)[0]
        self.assertIn("actions/workflows/ci.yml", ci_section)
        self.assertIn("pull requests and pushes to `main`", ci_section)
        for version in ("Python 3.10", "Python 3.11", "Python 3.12"):
            self.assertIn(version, ci_section)
        self.assertIn("```bash\n" + LOCAL_CI_SEQUENCE + "```", ci_section)
        normalized_ci_section = " ".join(ci_section.split())
        self.assertIn(
            "Failure-only 14-day report artifacts are retained when both reports were generated.",
            normalized_ci_section,
        )
        self.assertIn(
            "If either report is missing, CI fails a missing-evidence check before upload.",
            normalized_ci_section,
        )
        self.assertIn("CI is not runtime authorization and does not execute Agent Runtime tools.", ci_section)


if __name__ == "__main__":
    unittest.main()
