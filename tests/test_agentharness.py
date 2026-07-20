from contextlib import redirect_stdout
from io import StringIO
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.cli import main
from agentharness.eval_runner import run_smoke_eval
from agentharness.validate import validate_policy
from agentharness.yamlio import load_yaml


class AgentHarnessTests(unittest.TestCase):
    def test_example_policy_validates_against_schema(self):
        policy = load_yaml(ROOT / "examples" / "agent_policy.example.yaml")
        schema = load_yaml(ROOT / "schemas" / "agent_policy.schema.yaml")

        report = validate_policy(policy, schema)

        self.assertEqual([], report.errors)

    def test_supported_smoke_eval_cases_pass(self):
        policy = load_yaml(ROOT / "examples" / "agent_policy.example.yaml")
        suite = load_yaml(ROOT / "evals" / "agent_safety_eval_suite.yaml")

        results = run_smoke_eval(policy, suite, ["PI-001", "PD-001", "SEC-001"])

        self.assertEqual(["PASS", "PASS", "PASS"], [result.status for result in results])

    def test_loop_check_cli_passes_valid_fixture(self):
        code, output = _run_cli(["loop", "check", str(ROOT / "examples" / "agent_bus")])

        self.assertEqual(0, code)
        self.assertIn("PASS loop bus validation:", output)

    def test_loop_check_cli_fails_invalid_fixture(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus"
            shutil.copytree(ROOT / "examples" / "agent_bus", bus_root)
            ledger_path = bus_root / "ledger.jsonl"
            lines = ledger_path.read_text(encoding="utf-8").splitlines()
            first_event = json.loads(lines[0])
            first_event["actor"] = "executor"
            lines[0] = json.dumps(first_event, separators=(",", ":"))
            ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            code, output = _run_cli(["loop", "check", str(bus_root)])

        self.assertEqual(1, code)
        self.assertIn("FAIL loop bus validation:", output)
        self.assertIn("ERROR ledger[0].actor", output)

    def test_help_mentions_loop_check(self):
        stream = StringIO()
        with redirect_stdout(stream):
            with self.assertRaises(SystemExit) as raised:
                main(["--help"])

        self.assertEqual(0, raised.exception.code)
        self.assertIn("loop check", stream.getvalue())
        self.assertIn("handoff inspect", stream.getvalue())
        self.assertIn("handoff export", stream.getvalue())
        self.assertIn("handoff manifest", stream.getvalue())
        self.assertIn("handoff verify-manifest", stream.getvalue())


def _run_cli(argv):
    stream = StringIO()
    with redirect_stdout(stream):
        code = main(argv)
    return code, stream.getvalue()


if __name__ == "__main__":
    unittest.main()
