"""Contract guard for the read-only GitHub Actions verification workflow."""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _load_workflow(path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _verification_steps(workflow):
    return [
        step
        for step in workflow["jobs"]["verify"]["steps"]
        if "run" in step and step.get("name") != "Install package"
    ]


def _run_commands(workflow):
    commands = []
    for step in _verification_steps(workflow):
        if step["name"] == "Generate evaluation reports":
            commands.append(
                "\n".join(
                    line.split(" || ", 1)[0]
                    for line in step["run"].splitlines()
                    if line == "mkdir -p artifacts" or line.startswith("./agentharness eval")
                )
            )
        else:
            commands.append(step["run"])
    return commands


def _artifact_step(workflow):
    return next(
        step
        for step in workflow["jobs"]["verify"]["steps"]
        if step.get("uses") == "actions/upload-artifact@v4"
    )


def _verification_commands(run_commands):
    return [
        line
        for command in run_commands
        for line in command.splitlines()
        if line.strip() and line.strip() != "mkdir -p artifacts"
    ]


def _serialized_verify_job(workflow):
    return yaml.dump(workflow["jobs"]["verify"])


class CiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = _load_workflow(ROOT / ".github/workflows/ci.yml")

    def test_trigger_permissions_and_matrix(self):
        self.assertEqual({"pull_request", "push"}, set(self.workflow["on"]))
        self.assertEqual({"branches": ["main"]}, self.workflow["on"]["push"])
        self.assertEqual({"contents": "read"}, self.workflow["permissions"])
        job = self.workflow["jobs"]["verify"]
        self.assertEqual("ubuntu-latest", job["runs-on"])
        self.assertNotIn("permissions", job)
        self.assertEqual(["3.10", "3.11", "3.12"], job["strategy"]["matrix"]["python-version"])
        self.assertEqual("1", job["env"]["PYTHONDONTWRITEBYTECODE"])

    def test_setup_and_artifact_contract(self):
        steps = self.workflow["jobs"]["verify"]["steps"]
        self.assertEqual("actions/checkout@v4", steps[0]["uses"])
        self.assertEqual("actions/setup-python@v5", steps[1]["uses"])
        self.assertEqual("${{ matrix.python-version }}", steps[1]["with"]["python-version"])
        self.assertEqual(
            "python -m pip install --upgrade pip\npython -m pip install -e .\n",
            steps[2]["run"],
        )
        upload = _artifact_step(self.workflow)
        self.assertEqual("${{ failure() }}", upload["if"])
        self.assertEqual("agentharness-eval-${{ matrix.python-version }}", upload["with"]["name"])
        self.assertEqual(
            "artifacts/eval-results.xml\nartifacts/eval-results.json\n",
            upload["with"]["path"],
        )
        self.assertEqual("14", upload["with"]["retention-days"])
        self.assertEqual("error", upload["with"]["if-no-files-found"])

    def test_evaluation_reports_are_both_written_before_failure(self):
        report_step = next(
            step
            for step in self.workflow["jobs"]["verify"]["steps"]
            if step.get("name") == "Generate evaluation reports"
        )
        self.assertEqual(
            "\n".join(
                [
                    "mkdir -p artifacts",
                    "junit_status=0",
                    "./agentharness eval --all --format junit > artifacts/eval-results.xml || junit_status=$?",
                    "json_status=0",
                    "./agentharness eval --all --format json > artifacts/eval-results.json || json_status=$?",
                    "test \"$junit_status\" -eq 0 -a \"$json_status\" -eq 0",
                ]
            ) + "\n",
            report_step["run"],
        )

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


if __name__ == "__main__":
    unittest.main()
