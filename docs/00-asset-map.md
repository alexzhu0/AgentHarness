# AgentHarness 四类资产地图

## 背景

AgentHarness 的目标不是复制任何第三方 system prompt，而是把公开语料中的 agent scaffold 设计沉淀为可复用的架构资产。CL4R1T4S 可以作为样本库，但必须按“不可信外部语料”处理。

本仓库当前沉淀四类核心资产：

1. **Agent Design Pattern Library**：抽象主流 agent 的架构模式。
2. **Tool Governance Policy**：定义工具调用、审批、拒绝、审计边界。
3. **Agent Safety Eval Suite**：把治理规则转成可回归测试的安全评测集。
4. **Prompt / Policy Compiler**：把结构化 agent policy 编译成 system prompt、runtime config、eval config。

此外，运行时架构视图在 [`docs/06-runtime-architecture.md`](./06-runtime-architecture.md)
中定义，用于说明 policy、file-bus ledger、approval boundary、execution boundary
和 verification layer 如何组合成 harness。

企业定位与边界审计在
[`docs/07-enterprise-positioning-and-boundary-audit.md`](./07-enterprise-positioning-and-boundary-audit.md)
中定义，用于明确 AgentHarness 当前是 pre-execution evidence control-plane，
不是 runtime/orchestration/auth/sandbox/signing 系统。

术语表与产品契约在
[`docs/08-glossary-and-product-contract.md`](./08-glossary-and-product-contract.md)
中定义，用于固定 T001-T014 之后的 canonical vocabulary、ontology 和 product contract。

Source-backed integration strategy 在
[`docs/09-source-backed-integration-strategy.md`](./09-source-backed-integration-strategy.md)
中定义，用于把 AgentHarness evidence artifacts 映射到未来 external runtime、governance、auth、identity、protocol 和 execution-plane consumers。

Enterprise audit report and buyer demo 在
[`docs/10-enterprise-audit-report-and-buyer-demo.md`](./10-enterprise-audit-report-and-buyer-demo.md)
中定义，用于展示 security/platform/compliance reviewer 如何读取 AgentHarness evidence chain、ready/blocked/unsupported 分类、manifest readback、T018 machine-readable audit report 和 T020 enterprise audit report schema，而不引入 runtime execution。
T021 增加 `./agentharness audit verify-report <bus_root> <audit_report_path>`，用于对保存的 audit report 做 readback verification；它只读取保存的 JSON 和当前 bus evidence，不执行 runtime adapter、不写文件、不签名、不提交任务。
T022 增加 `./agentharness audit checklist <bus_root>`，用于输出 reviewer-facing goal/check checklist；它只汇总现有 validation/inspection/export/manifest/audit evidence 和 manual readback steps，stdout-only、`result_status: not_executed`，不是 runtime、auth、sandbox、signing、trust-root、governance enforcement 或 task mutation。
T024 增加 [`schemas/enterprise_audit_checklist.schema.yaml`](../schemas/enterprise_audit_checklist.schema.yaml) 和 pure in-memory checklist validator，用于固定 accepted checklist payload contract；它不是 runtime authorization、execution、file writer、signing/trust bundle 或 governance enforcement。
T025 增加 [`tests/test_end_to_end_evidence_chain.py`](../tests/test_end_to_end_evidence_chain.py)，用于把 accepted evidence chain 锁定为端到端 regression harness；它只调用既有 in-memory builder/validator/readback checks，不新增 CLI 或产品面。
T027 增加 [`docs/11-reproducible-enterprise-demo.md`](./11-reproducible-enterprise-demo.md)，用于给 reviewer 提供 5–10 分钟可复现 demo flow；它只链接既有命令，不新增脚本、CLI 或产品面。
T028 增加 [`docs/12-buyer-reviewer-decision-guide.md`](./12-buyer-reviewer-decision-guide.md)，用于说明 reviewer 如何 accept evidence for downstream review、reject evidence package 或 escalate externally；它不新增 lifecycle state 或产品面。
T029 增加 [`docs/13-external-reviewer-checklist.md`](./13-external-reviewer-checklist.md)，用于给第三方 reviewer 提供 evidence acceptance checklist / rubric；它不新增 runtime approval、lifecycle state、CLI 或产品面。
T030 增加 [`docs/14-reviewer-dry-run-and-reproducibility.md`](./14-reviewer-dry-run-and-reproducibility.md)，用于记录 reviewer dry-run、expected vs observed summaries 和 checklist decision mapping；它只强化复现文档，不新增脚本、CLI、runtime、schema 或产品面。
T031 增加 [`docs/15-agentharness-development-loop-operating-model.md`](./15-agentharness-development-loop-operating-model.md)，用于规定未来 T0xx Loop Task Packet、maker/checker split、checks、failure probes、human gates 和 reviewer gates；它是开发流程文档，不新增产品/runtime 行为。
T032 增加 [`docs/16-phase-e-release-readiness-and-packaging-audit.md`](./16-phase-e-release-readiness-and-packaging-audit.md)，用于审计 Phase E 是否适合未来本地 milestone packaging；它不是 commit、push、public release、production readiness、runtime approval 或 safe-to-execute claim。
T034 增加 [`docs/17-pi-integration-boundary-and-contract.md`](./17-pi-integration-boundary-and-contract.md)，用于以 contract-first 方式界定未来 AgentHarness ↔ Pi evidence gate 边界；它只使用 Pi 只读事实，不修改 Pi、不新增依赖、不实现 runtime hook。
T035 增加 [`docs/18-pi-tool-call-mapping-fixture.md`](./18-pi-tool-call-mapping-fixture.md) 和 [`examples/pi_tool_call_mapping/`](../examples/pi_tool_call_mapping/)，用于提供静态 Pi-like tool-call observation 与 expected mapping fixture；它不调用、不导入、不依赖、不修改 Pi，也不执行工具。
T036 增加 [`src/agentharness/pi_tool_call_mapping.py`](../src/agentharness/pi_tool_call_mapping.py) 和 [`tests/test_pi_tool_call_mapping.py`](../tests/test_pi_tool_call_mapping.py)，用于对 T035 静态 fixture 做 pure AgentHarness-side mock decision validation；它不调用 Pi、不实现 live hook，也不把 `allow_candidate` 归一化为 runtime allow。
T037 增加 [`docs/19-pi-contract-check-cli.md`](./19-pi-contract-check-cli.md) 和 `./agentharness pi contract-check`，作为 T036 validator 的 stdout-only CLI wrapper；它只检查静态 fixture 与 registry-backed evidence，不修改 Pi、不执行工具、不输出 runtime allow、不新增 writer flags。
T039 增加 [`docs/20-pi-dual-repo-dry-run-e2e.md`](./20-pi-dual-repo-dry-run-e2e.md)，用于记录 Pi opt-in dry-run gate 调用本地 AgentHarness CLI 的 dual-repo E2E；它证明 wiring 与 fail-closed block，不授权 runtime allow 或真实工具执行。
T040 增加 [`docs/21-pi-controlled-read-only-poc.md`](./21-pi-controlled-read-only-poc.md)，用于记录 test-only controlled read-only allow/block PoC；它只允许 exact fake `read_workspace` + `{path: "README.md"}` 在显式 env 下执行，其他情况仍 block，不代表 production runtime allow。
T041 增加
[`docs/22-pi-integration-readiness-pause-review.md`](./22-pi-integration-readiness-pause-review.md)，
用于在 T040 后暂停并记录 readiness decision；结论是
`ready_for_real_execution: false`、`ready_for_next_planning_loop: true`，
不授权真实 Pi 执行。
T042 增加
[`docs/23-pi-milestone-packaging-audit.md`](./23-pi-milestone-packaging-audit.md)，
用于分类 T034-T041/T042 AgentHarness include/exclude set、Pi companion
status 和未来 staging strategy；决策为 COMMENT，不做 commit 或 push。

T056-T060 的当前里程碑入口如下：

- T056 evidence-integrity 复核已接受；旧的 pending 文案不再适用。
- T057 observation/evidence v1 contract 见
  [`docs/24`](./24-pi-observation-evidence-contract-v1.md)。
- T058 只把 Pi live hook 接到 block-only bridge；所有结果仍是
  `not_executed`，不发生真实执行。
- T059 仅用 fake Win9-named tools 验证 live shadow；不执行真实工具。
- T060 runtime-authorization readiness ADR 见
  [`docs/25`](./25-pi-runtime-authorization-readiness-adr.md)；
  当前结论为 NO-GO、NOT IMPLEMENTED，不是 power-on 许可。
- T061 no-commit handoff 见
  [`docs/26`](./26-agentharness-pi-shadow-milestone-packaging.md)。
- T062 Phase-0 preflight 见
  [`docs/27`](./27-pi-runtime-authorization-phase0-preflight.md)；
  它是 T060 的派生规划，结论仍为 NO-GO、NOT IMPLEMENTED。
- release 与 milestone 历史索引见
  [`release/README.md`](../release/README.md)；该索引区分证据日期、历史记录与
  正式 GitHub prerelease，避免把计划日期误写为发布日期。
- 2026-07-13 release note 见
  [`release/2026.07.13.md`](../release/2026.07.13.md)。
- v0.2.0-alpha.1 GitHub prerelease 见
  [`release/2026.07.20.md`](../release/2026.07.20.md)。该版本发布
  AgentHarness evidence/control-plane 源码，不包含 Pi companion，也不发布
  PyPI 或 npm package。

有限 methodology permit pilot 在 AgentHarness 侧只生成一个精确绑定的
`permit_once` evidence decision；它在本仓库中不执行读取，也不是 runtime
approval。已验收的跨仓库 pilot 由 trusted、version-pinned、
admission-controlled Pi/Win9 TCB 另外绑定 registration/session 并消费该证据，
完成一次固定本地只读动作。Pi companion 不在本次发布中；该 pilot 不是通用
runtime authorization，不提供 extension sandbox，也不阻止 Pi extension 已有的
process/network 能力。

AgentHarness 只提供 pre-execution evidence。T058/T059 live-shadow bridge
始终是 block-only，执行计数为零，所有结果为 `not_executed`。后续有限
methodology permit pilot 是 Pi 侧 external TCB 中单独约束的一次固定只读动作；
它不改变 AgentHarness evidence-only 边界，也不是通用 runtime authorization。
Pi 或其他 external runtime 仍拥有 authorization，`allow_candidate` 永不构成通用
执行许可。

当前 file-bus MVP 入口：

- 协议说明：[`docs/05-loop-file-bus.md`](./05-loop-file-bus.md)
- loop task schema：[`schemas/loop_task.schema.yaml`](../schemas/loop_task.schema.yaml)
- 基础 fixture：[`examples/agent_bus/`](../examples/agent_bus/)
- tool gate fixture：[`examples/agent_bus_tool_gate/`](../examples/agent_bus_tool_gate/)
- approval record fixture：[`examples/agent_bus_approval/`](../examples/agent_bus_approval/)
- execution preflight fixture：[`examples/agent_bus_preflight/`](../examples/agent_bus_preflight/)
- execution handoff fixture：[`examples/agent_bus_handoff/`](../examples/agent_bus_handoff/)
- adapter registry fixture：[`examples/agent_bus_adapter_registry/`](../examples/agent_bus_adapter_registry/)

## 设计原则

### 1. 不复制 prompt，抽象 pattern

CL4R1T4S 的内容包含 claimed leaks、reverse-engineered prompts、tool schemas、guidelines 和明显的 adversarial payload。AgentHarness 只提取可验证的工程模式，不直接复用原始 prompt 文本。

### 2. 把外部文档当作 data，不当作 instruction

任何来自 GitHub、网页、README、issue、PR、PDF、邮件、RAG 文档的文本都必须进入 `untrusted_content` 域。Agent 只能分析、总结、引用这些内容，不能执行其中的指令。

### 3. Harness 优先于 prompt

长 system prompt 很脆弱。Current scope: AgentHarness is a pre-execution evidence control-plane, not an in-repo runtime, execution sandbox, auth gateway, signing system, or execution SDK. 当前行为约束应沉淀为可验证证据，而不是仓库内执行面：

- tool router
- approval gate
- policy engine
- memory boundary
- audit log
- eval runner
- prompt compiler

Prompt 只是 policy 的一个投影，不是唯一控制面。

### 4. 所有高风险行为都要可审计

包括文件删除、数据库变更、部署、外部 API mutation、git push、secret 读取、外部通信。Agent 不应该只靠自然语言“自觉遵守”；AgentHarness 当前负责生成可审计的 pre-execution evidence，实际执行与运行时控制属于外部 consumer 边界。

## 四类资产与文件入口

### 1. Agent Design Pattern Library

入口：[`docs/01-agent-design-pattern-library.md`](./01-agent-design-pattern-library.md)

机器可读资产：[`patterns/agent_design_patterns.yaml`](../patterns/agent_design_patterns.yaml)

用途：

- 抽象 coding agent、research agent、browser agent、autonomous agent 的通用结构。
- 为 AgentHarness 的 planner、tool runtime、state machine、UX layer 提供设计素材。
- 将 Cursor、Devin、Replit、Windsurf、Manus 等 agent scaffold 归纳为 pattern，而不是复制原文。

### 2. Tool Governance Policy

入口：[`docs/02-tool-governance-policy.md`](./02-tool-governance-policy.md)

机器可读资产：[`policies/tool_governance.yaml`](../policies/tool_governance.yaml)

用途：

- 定义 tool 的风险等级。
- 建立 allow / approval_required / deny 三段式决策。
- 约束 shell、file、git、database、browser、deployment、memory、secret、external communication 等工具。
- 为 agent harness 中的 tool router 和 approval gate 提供初始策略。

### 3. Agent Safety Eval Suite

入口：[`docs/03-agent-safety-eval-suite.md`](./03-agent-safety-eval-suite.md)

机器可读资产：[`evals/agent_safety_eval_suite.yaml`](../evals/agent_safety_eval_suite.yaml)

用途：

- 把 prompt-injection、destructive ops、secret handling、database mutation、verification loop、external communication 等治理规则转成可测试用例。
- 支持 regression test，避免 prompt 或模型升级后行为漂移。
- 用于比较不同 harness、模型、tool router、policy compiler 的合规性。

### 4. Prompt / Policy Compiler

入口：[`docs/04-prompt-policy-compiler.md`](./04-prompt-policy-compiler.md)

机器可读资产：[`schemas/agent_policy.schema.yaml`](../schemas/agent_policy.schema.yaml)

用途：

- 把 agent policy 作为源代码管理。
- 编译到不同 provider 的 system prompt。
- 编译到 runtime policy、tool allowlist、approval rules、eval cases。
- 避免多处手写 prompt 导致 drift。

### Runtime Architecture View

入口：[`docs/06-runtime-architecture.md`](./06-runtime-architecture.md)

用途：

- 明确 policy vs prompt、state ledger vs evidence、approval vs execution、validation vs runtime mutation 的边界。
- 定义 AgentHarness 的 policy layer、loop/state layer、execution boundary、verification layer 和 operator interface。
- 记录 file-bus MVP、tool gate report、approval record、execution preflight 之后的扩展点，但不引入 daemon、实时聊天或任务变更 CLI。

### Enterprise Positioning and Boundary Audit

入口：[`docs/07-enterprise-positioning-and-boundary-audit.md`](./07-enterprise-positioning-and-boundary-audit.md)

用途：

- 固化企业定位：AgentHarness is a pre-execution evidence control-plane for agent actions.
- 明确当前证据链：file-bus、tool gate、approval、preflight、handoff、adapter registry、export package、digest manifest、manifest verification。
- 区分 AgentHarness 与 runtime/orchestration framework、runtime governance middleware、authorization/identity protocol、sandbox/signing/trust-root system 的边界。
- 给 T015+ 提供 build / buy / integrate 决策入口。

### Glossary and Product Contract

入口：[`docs/08-glossary-and-product-contract.md`](./08-glossary-and-product-contract.md)

用途：

- 固定 control-plane、audit-plane、execution-plane、runtime boundary、evidence、eligibility、handoff、export package、digest manifest、manifest verification 等术语。
- 明确 AgentHarness 只 validate/export evidence；runtime、governance、auth、identity、sandbox、execution-plane 都是 external consumer。
- 把 `result_status: not_executed` 固化为当前 handoff/export/manifest/verification 输出的不变式。
- 为 T016 integration strategy、T017 buyer-demo narrative 和未来 runtime spike 提供 product contract guardrails。

### Source-Backed Integration Strategy

入口：[`docs/09-source-backed-integration-strategy.md`](./09-source-backed-integration-strategy.md)

用途：

- 用 source-backed matrix 区分 runtime/orchestration、governance middleware、auth/identity/protocol 和 deferred execution-plane external consumers。
- 明确 AgentHarness may export evidence，但不 adopt SDK/package、不实现 wrapper、不调用 runtime adapter。
- 固化 Build / Buy / Integrate / Defer 规则，给 T017 buyer-demo narrative 和后续 integration readiness checklist 提供依据。

### Enterprise Audit Report and Buyer Demo

入口：[`docs/10-enterprise-audit-report-and-buyer-demo.md`](./10-enterprise-audit-report-and-buyer-demo.md)

用途：

- 用 `examples/agent_bus_adapter_registry` 的现有 evidence 展示 reports=1、total_handoffs=5、ready/exported=2、blocked=2、unsupported=1。
- 给 security/platform/compliance reviewer 提供 validate、eval、loop check、handoff inspect、export、manifest、verify-manifest、`./agentharness audit report` 和 `./agentharness audit checklist` 的 buyer-demo workflow。
- 记录 T018 machine-readable enterprise audit report：组合 inspect/export/manifest evidence，stdout-only 输出 `enterprise_audit_report` JSON。
- 记录 T020 enterprise audit report schema：[`schemas/enterprise_audit_report.schema.yaml`](../schemas/enterprise_audit_report.schema.yaml) 是 pre-execution evidence report 的 repo-native contract/check，不是 runtime integration、execution surface、signing/trust system 或 file writer。
- 记录 T021 audit report readback verification：`./agentharness audit verify-report` 重新生成当前 audit report 并比较 canonical JSON/digest，输出 `enterprise_audit_report_verification_report`，仍然是 readback evidence，不是 runtime execution、adapter invocation、signing/timestamping/trust-root、auth/governance enforcement、dispatch/submit/run/execute/task mutation 或 file-output behavior。
- 记录 T022 enterprise audit checklist report：`./agentharness audit checklist` 输出 ordered goal/check status JSON，包含 pass/fail/blocked/manual reviewer checks，仍然 stdout-only、read-only、`result_status: not_executed`。
- 记录 T024 enterprise audit checklist schema：[`schemas/enterprise_audit_checklist.schema.yaml`](../schemas/enterprise_audit_checklist.schema.yaml) 是 checklist payload 的 repo-native contract/check，不是 runtime authorization、execution surface、signing/trust system 或 file writer。
- 记录 T025 end-to-end evidence-chain regression harness：[`tests/test_end_to_end_evidence_chain.py`](../tests/test_end_to_end_evidence_chain.py) 断言 accepted stage order、fixture counts、canonical determinism 和 negative drift probes。
- 链接 T027 reproducible enterprise demo：[`docs/11-reproducible-enterprise-demo.md`](./11-reproducible-enterprise-demo.md)，作为 reviewer copy-paste command flow 和 expected counts 入口。
- 链接 T028 buyer/reviewer decision guide：[`docs/12-buyer-reviewer-decision-guide.md`](./12-buyer-reviewer-decision-guide.md)，作为 evidence acceptance、rejection 和 external escalation 的解释入口。
- 链接 T029 external reviewer checklist：[`docs/13-external-reviewer-checklist.md`](./13-external-reviewer-checklist.md)，作为 third-party reviewer 接受、拒绝或外部升级 evidence package 的操作性 rubric。
- 链接 T030 reviewer dry-run and reproducibility：[`docs/14-reviewer-dry-run-and-reproducibility.md`](./14-reviewer-dry-run-and-reproducibility.md)，作为 external reviewer 复现实测、对比 expected vs observed counts，并应用 checklist decision mapping 的入口。
- 链接 T031 development loop operating model：[`docs/15-agentharness-development-loop-operating-model.md`](./15-agentharness-development-loop-operating-model.md)，作为后续 AgentHarness T0xx 任务的 Loop Task Packet、reviewer gate 和 human gate 操作模型。
- 链接 T032 Phase E release readiness and packaging audit：[`docs/16-phase-e-release-readiness-and-packaging-audit.md`](./16-phase-e-release-readiness-and-packaging-audit.md)，作为未来本地 milestone commit 前的 include/exclude、GO/COMMENT/NO-GO 和边界审计入口。
- 链接 T034 Pi integration boundary and contract：[`docs/17-pi-integration-boundary-and-contract.md`](./17-pi-integration-boundary-and-contract.md)，作为未来 Pi runtime-candidate evidence gate 的 contract-first planning 入口，不代表 live integration。
- 链接 T035 Pi tool-call mapping fixture：[`docs/18-pi-tool-call-mapping-fixture.md`](./18-pi-tool-call-mapping-fixture.md)，作为未来 mock decision validator 的静态 observation/expectation 入口，不代表 live Pi runtime 集成。
- 记录 T036 Pi mock decision validator：[`src/agentharness/pi_tool_call_mapping.py`](../src/agentharness/pi_tool_call_mapping.py) 只读取静态 fixture 与既有 export/manifest evidence，输出 deterministic `pi_tool_call_mapping_validation_report`，不是 runtime surface。
- 记录 T037 Pi contract-check CLI：[`docs/19-pi-contract-check-cli.md`](./19-pi-contract-check-cli.md) 和 `./agentharness pi contract-check` 复用 T036 validator，stdout-only 输出 deterministic JSON；`allow_candidate` 仍只是 candidate evidence，不是 runtime allow、runtime approval 或 safe-to-execute approval。
- 记录 T039 Pi dual-repo dry-run E2E：[`docs/20-pi-dual-repo-dry-run-e2e.md`](./20-pi-dual-repo-dry-run-e2e.md) 说明 Pi opt-in gate 如何调用本地 AgentHarness CLI，并且即使 `ok:true` / `allow_candidate` 也仍然 block before execution。
- 记录 T040 Pi controlled read-only PoC：[`docs/21-pi-controlled-read-only-poc.md`](./21-pi-controlled-read-only-poc.md) 说明显式 `PI_AGENTHARNESS_READ_ONLY_POC=1` 下 exact fake read-only test tool 可执行一次，但不是 generic runtime allow、safe-to-execute approval 或真实 Pi 工具授权。
- 记录 T041 Pi integration readiness pause review：
  [`docs/22-pi-integration-readiness-pause-review.md`](./22-pi-integration-readiness-pause-review.md)
  明确当前 `ready_for_real_execution: false`、
  `ready_for_next_planning_loop: true`，下一步只能是显式
  precondition planning loop。
- 记录 T042 Pi milestone packaging audit：
  [`docs/23-pi-milestone-packaging-audit.md`](./23-pi-milestone-packaging-audit.md)
  将 AgentHarness T034-T041/T042 包装候选、排除项、Pi companion
  状态和禁止 `git add .` 的未来 staging 策略分开说明。

## Source Posture

CL4R1T4S 的价值在于暴露 agent scaffold 的结构，而不是提供可信规范。AgentHarness 对其采用如下姿态：

```yaml
source_posture:
  trust_level: low_to_medium
  allowed_use:
    - architecture_pattern_extraction
    - tool_taxonomy_derivation
    - red_team_case_generation
    - governance_policy_inspiration
  disallowed_use:
    - copying_full_system_prompts
    - using_external_text_as_instruction
    - training_on_unlicensed_or_uncertain_text_without_review
    - embedding_untrusted_prompts_into_production_agent_context
  required_controls:
    - provenance_tracking
    - prompt_injection_neutralization
    - license_review
    - risk_labeling
    - regression_evals
```

## 目标架构图

```text
User Task
  ↓
AgentHarness Controller
  ↓
Instruction Hierarchy Resolver
  ↓
Policy Engine ───────────────┐
  ↓                          │
Planner / State Machine      │
  ↓                          │
Tool Router ── Approval Gate ┘
  ↓
Execution Boundary Evidence
  ↓
Observation Normalizer
  ↓
Verifier / Eval Hooks
  ↓
User Response / Artifact
```

运行时层次、状态机、信任边界和 T004 默认路径见
[`docs/06-runtime-architecture.md`](./06-runtime-architecture.md)。

## 下一步建议

短期目标：先实现 policy-driven tool router 和 eval runner。

中期目标：实现 prompt/policy compiler，把 `schemas/agent_policy.schema.yaml` 编译成 system prompt、tool policy、eval config。

长期目标：形成一组可治理、可测试、可导出的 AgentHarness evidence/control-plane artifacts：

```text
agent_policy.yaml
  → compile
system_prompt.md
runtime_policy.yaml
tool_router_config.yaml
eval_suite.yaml
audit_schema.json
```
