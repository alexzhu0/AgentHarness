# Pi-like Tool-Call Mapping Fixture

This directory contains a static, side-effect-free fixture for future AgentHarness/Pi boundary work.

Files:

- `pi_tool_call_observations.json` — hand-authored Pi-like tool-call observations based on T034 planning facts, not captured from a live Pi runtime.
- `expected_mapping.json` — expected AgentHarness mapping outcomes for each observation.

The fixture is intentionally not a runtime integration:

- it does not call Pi;
- it does not modify Pi;
- it does not import or depend on Pi;
- it does not implement a live hook;
- it does not execute tools;
- it does not grant runtime approval or safety approval;
- the fixture files/top-level evidence remain `result_status: not_executed`.

The decision vocabulary is limited to `allow_candidate`, `block`, `unsupported`, and `error`. `allow_candidate` means the observation is a candidate match to existing AgentHarness evidence only; it is not execution approval, runtime approval, safe-to-execute approval, or a value that future validation may normalize into runtime allow.
